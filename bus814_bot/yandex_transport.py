"""Прогнозы прибытия по остановке из Яндекс.Карт.

Используется неофициальный JSON-эндпоинт, которым пользуется сам сайт
yandex.ru/maps. Первый запрос без csrfToken возвращает {"csrfToken": ...},
второй — с токеном и теми же cookies — отдаёт данные остановки.
"""

import json
import logging
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import aiohttp
from yarl import URL

log = logging.getLogger(__name__)

STOP_INFO_URL = "https://yandex.ru/maps/api/masstransit/getStopInfo"
MAPS_PAGE_URL = "https://yandex.ru/maps/213/moscow/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://yandex.ru/maps/213/moscow/",
}


class YandexError(Exception):
    pass


@dataclass
class Arrival:
    eta_sec: int          # через сколько секунд машина будет на остановке
    vehicle_id: str | None


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def _find_route_nodes(obj, route: str):
    """Все словари вида {"name": "814", ...} в ответе — структура у Яндекса
    менялась, поэтому ищем маршрут рекурсивно, а не по жёсткому пути."""
    if isinstance(obj, dict):
        if _norm(str(obj.get("name", ""))) == route and (
            "threads" in obj or "type" in obj
        ):
            yield obj
            return
        for v in obj.values():
            yield from _find_route_nodes(v, route)
    elif isinstance(obj, list):
        for v in obj:
            yield from _find_route_nodes(v, route)


def _collect_events(obj, out: list):
    """Собирает события с прогнозом (Estimated) внутри узла маршрута."""
    if isinstance(obj, dict):
        est = obj.get("Estimated")
        if isinstance(est, dict) and "value" in est:
            out.append((est["value"], obj.get("vehicleId")))
        for v in obj.values():
            _collect_events(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_events(v, out)


def parse_arrivals(payload: dict, route: str, now: float | None = None) -> list[Arrival]:
    """Прогнозы прибытия маршрута route, отсортированные по времени."""
    now = time.time() if now is None else now
    route = _norm(route)
    raw: list = []
    for node in _find_route_nodes(payload, route):
        _collect_events(node, raw)

    arrivals: dict[tuple, Arrival] = {}
    for value, vehicle_id in raw:
        try:
            eta = int(float(value) - now)
        except (TypeError, ValueError):
            continue
        if eta < -60:  # устаревший прогноз
            continue
        key = (vehicle_id, value) if vehicle_id is None else (vehicle_id,)
        prev = arrivals.get(key)
        if prev is None or eta < prev.eta_sec:
            arrivals[key] = Arrival(max(eta, 0), vehicle_id)
    return sorted(arrivals.values(), key=lambda a: a.eta_sec)


def sign(query: str) -> int:
    """Подпись запроса (параметр s), как её считает JS сайта Яндекс.Карт."""
    n = 5381
    for ch in query:
        n = ((33 * n) ^ ord(ch)) & 0xFFFFFFFF
    return n


# Способы запроса по порядку: с подписью по закодированной строке,
# по сырой строке, без подписи. Первый сработавший запоминаем.
SIGN_MODES = ("encoded", "raw", None)


class YandexTransport:
    def __init__(self, timeout: float = 15):
        self._session: aiohttp.ClientSession | None = None
        self._csrf: str | None = None
        self._session_id = f"{int(time.time() * 1000)}_{random.randint(100000, 999999)}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._bootstrapped = False
        self._mode: str | None | bool = False  # False — ещё не подобрали
        self.debug: list[str] = []

    async def close(self):
        if self._session:
            await self._session.close()

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
            self._session = aiohttp.ClientSession(
                headers=HEADERS, timeout=self._timeout, cookie_jar=jar
            )
        return self._session

    def _log(self, msg: str):
        log.info("yandex: %s", msg)
        self.debug.append(msg)
        del self.debug[:-20]

    async def _bootstrap(self):
        """Открываем страницу Карт, как браузер: получаем cookies,
        csrfToken и sessionId из конфига страницы."""
        async with self._http().get(MAPS_PAGE_URL) as resp:
            html = await resp.text()
            self._log(f"страница карт: HTTP {resp.status}, {len(html)} байт, url={resp.url}")
            if "showcaptcha" in str(resp.url) or "showcaptcha" in html[:5000]:
                raise YandexError("Яндекс показал капчу на странице карт (IP сервера под подозрением)")
        m = re.search(r'"csrfToken":"([^"]+)"', html)
        if m:
            self._csrf = m.group(1)
        m = re.search(r'"sessionId":"([^"]+)"', html)
        if m:
            self._session_id = m.group(1)
        self._log(f"csrfToken {'найден' if self._csrf else 'НЕ найден'}, sessionId={self._session_id}")
        self._bootstrapped = True

    async def _request(self, stop_id: str, mode: str | None) -> dict:
        params = {
            "ajax": "1",
            "id": stop_id,
            "lang": "ru",
            "locale": "ru_RU",
            "mode": "prognosis",
            "sessionId": self._session_id,
        }
        if self._csrf:
            params["csrfToken"] = self._csrf
        items = sorted(params.items())
        query = urlencode(items, quote_via=quote)
        if mode == "encoded":
            query += f"&s={sign(query)}"
        elif mode == "raw":
            query += "&s=" + str(sign("&".join(f"{k}={v}" for k, v in items)))
        url = URL(f"{STOP_INFO_URL}?{query}", encoded=True)
        async with self._http().get(url) as resp:
            text = await resp.text()
            snippet = text[:300].replace("\n", " ")
            self._log(f"getStopInfo [подпись={mode}]: HTTP {resp.status}: {snippet}")
            if "showcaptcha" in str(resp.url) or "showcaptcha" in text[:2000]:
                raise YandexError("Яндекс показал капчу — запросы слишком частые или IP под подозрением")
            if resp.status != 200:
                raise YandexError(f"HTTP {resp.status}: {text[:200]}")
            try:
                return json.loads(text)
            except ValueError as e:
                raise YandexError(f"не JSON: {text[:200]}") from e

    async def _try_mode(self, stop_id: str, mode) -> dict | None:
        for _ in range(2):
            data = await self._request(stop_id, mode)
            if "data" in data:
                return data
            if "csrfToken" in data:
                # токен выдан заново или протух — повторяем с новым
                self._csrf = data["csrfToken"]
                continue
            if "error" in data:
                self._log(f"ошибка API: {str(data['error'])[:200]}")
            return None
        return None

    async def stop_info(self, stop_id: str) -> dict:
        if not self._bootstrapped:
            await self._bootstrap()
        modes = SIGN_MODES if self._mode is False else (self._mode,)
        for mode in modes:
            data = await self._try_mode(stop_id, mode)
            if data is not None:
                if self._mode is False:
                    self._log(f"рабочий способ запроса: подпись={mode}")
                self._mode = mode
                return data
        # всё сломалось — в следующий раз начнём заново: страница, токен, подбор способа
        self._bootstrapped = False
        self._mode = False
        self._csrf = None
        if self._session:
            self._session.cookie_jar.clear()
        last = self.debug[-1] if self.debug else "нет ответа"
        raise YandexError(f"Яндекс не отдал данные остановки. Последний ответ: {last}")

    async def arrivals(self, stop_id: str, route: str) -> list[Arrival]:
        return parse_arrivals(await self.stop_info(stop_id), route)


async def _diagnose(stop_id: str, route: str):
    """Запуск: python yandex_transport.py [stop_id] [маршрут] — печатает всё, что ответил Яндекс."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    yt = YandexTransport()
    try:
        data = await yt.stop_info(stop_id)
        print("\nОтвет (начало):", json.dumps(data, ensure_ascii=False)[:1500])
        arr = parse_arrivals(data, route)
        print(f"\nПрогнозы {route}:", [(a.eta_sec, a.vehicle_id) for a in arr] or "нет")
    except YandexError as e:
        print("\nОШИБКА:", e)
    finally:
        await yt.close()


if __name__ == "__main__":
    import asyncio
    import sys

    args = sys.argv[1:]
    asyncio.run(_diagnose(args[0] if args else "stop__9646450", args[1] if len(args) > 1 else "814"))
