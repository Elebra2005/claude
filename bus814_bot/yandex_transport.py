"""Прогнозы прибытия по остановке из Яндекс.Карт.

Используется неофициальный JSON-эндпоинт, которым пользуется сам сайт
yandex.ru/maps. Первый запрос без csrfToken возвращает {"csrfToken": ...},
второй — с токеном и теми же cookies — отдаёт данные остановки.
"""

import logging
import random
import time
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

STOP_INFO_URL = "https://yandex.ru/maps/api/masstransit/getStopInfo"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
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


class YandexTransport:
    def __init__(self, timeout: float = 15):
        self._session: aiohttp.ClientSession | None = None
        self._csrf: str | None = None
        self._session_id = f"{int(time.time() * 1000)}_{random.randint(100000, 999999)}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def close(self):
        if self._session:
            await self._session.close()

    async def _get(self, params: dict) -> dict:
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout)
        async with self._session.get(STOP_INFO_URL, params=params) as resp:
            text = await resp.text()
            if "captcha" in str(resp.url) or "showcaptcha" in text[:2000]:
                raise YandexError("Яндекс показал капчу — запросы слишком частые или IP под подозрением")
            if resp.status != 200:
                raise YandexError(f"HTTP {resp.status}: {text[:200]}")
            try:
                return await resp.json(content_type=None)
            except Exception as e:
                raise YandexError(f"не JSON: {text[:200]}") from e

    async def stop_info(self, stop_id: str) -> dict:
        for _ in range(3):
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
            data = await self._get(params)
            if "csrfToken" in data and "data" not in data:
                # токен выдан или протух — повторяем с новым
                self._csrf = data["csrfToken"]
                continue
            if "error" in data and "data" not in data:
                raise YandexError(f"ошибка API: {str(data['error'])[:200]}")
            return data
        raise YandexError("не удалось получить csrfToken")

    async def arrivals(self, stop_id: str, route: str) -> list[Arrival]:
        return parse_arrivals(await self.stop_info(stop_id), route)
