"""Курс юаня с сайта Dolgov Auto.

Это курс с наценкой перевозчика — та цифра, по которой реально платят за
машину, в отличие от фиксации ЦБ. Разметку страницы мы не контролируем,
поэтому парсер эвристический и умеет объяснять, что он нашёл: см. команду
/dolgov_debug и переменную DOLGOV_REGEX для ручного переопределения.
"""

import asyncio
import html
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import aiohttp

log = logging.getLogger(__name__)

CODE = "CNYD"  # псевдокод валюты в таблице rates

_TIMEOUT = aiohttp.ClientTimeout(total=25)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_DROP_BLOCKS = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[\s ]+")
# Маркеры юаня: слово, код, символ.
_MARKER = re.compile(r"юан|cny|¥|женьминьби|жэньминьби", re.I)
# Число вида 11,85 / 11.85 / 12 — с необязательным разделителем тысяч не работаем:
# курс юаня заведомо двузначный.
_NUMBER = re.compile(r"\d{1,3}(?:[.,]\d{1,4})?")

# Основной формат Долгова на карточке авто:
#   Курс валют ЦБ на сегодня:            1$ - 86,1910₽   1¥ - 12,8540₽
#   Курс валют в коммерческих банках:    1$ - 89,25₽     1¥ - 13,43₽
# Платят по банковскому, поэтому берём его, а курс ЦБ оставляем для сверки.
_YUAN_RATE = re.compile(r"1\s*¥\s*[-–—−]?\s*(\d{1,3}(?:[.,]\d{1,4})?)\s*₽")
_BANK_SECTION = re.compile(r"коммерческ", re.I)
_CBR_SECTION = re.compile(r"валют\s+ЦБ", re.I)
_CAR_LINK = re.compile(r"""href=["']([^"']*/china-used/[^"']+)["']""", re.I)


@dataclass
class DolgovQuote:
    value: float          # курс коммерческих банков — по нему и платят
    context: str          # фрагмент страницы, из которого взято число
    url: str
    cbr_quoted: float | None = None   # курс ЦБ, как его показывает сам сайт
    source: str = "банки"             # какой веткой парсера получено


@dataclass
class DolgovDebug:
    url: str
    status: int | None = None
    html_len: int = 0
    text_len: int = 0
    marker_hits: int = 0
    marker_hits_raw: int = 0
    candidates: list[tuple[float, str]] = field(default_factory=list)
    picked: float | None = None
    error: str | None = None
    used_regex: bool = False
    scanned_scripts: bool = False
    script_urls: list[str] = field(default_factory=list)
    yuan_hits: int = 0
    discovered_url: str | None = None
    source: str | None = None
    cbr_quoted: float | None = None


def to_text(raw_html: str, *, keep_scripts: bool = False) -> str:
    """Текст страницы. keep_scripts оставляет содержимое <script>: курс часто
    лежит там в JSON, а не в видимой разметке."""
    body = raw_html if keep_scripts else _DROP_BLOCKS.sub(" ", raw_html)
    body = _TAGS.sub(" ", body)
    return _SPACES.sub(" ", html.unescape(body)).strip()


def _last_before(pattern: re.Pattern[str], text: str, limit: int) -> int | None:
    """Позиция последнего совпадения левее limit."""
    found = None
    for match in pattern.finditer(text, 0, limit):
        found = match.start()
    return found


def extract_pair(text: str) -> tuple[float | None, float | None]:
    """(курс банков, курс ЦБ) из блока «Полная стоимость авто».

    Каждый курс относим к ближайшему заголовку СЛЕВА от него, а не к первому
    на странице: слово «коммерческ» вполне может встретиться выше — в меню
    или описании услуг — и тогда привязка к первому вхождению отдала бы под
    видом банковского курс ЦБ.

    Если заголовков нет вовсе, при двух курсах банковским считается второй:
    так свёрстано у них.
    """
    hits = [
        (match.start(), _as_float(match.group(1)))
        for match in _YUAN_RATE.finditer(text)
    ]
    hits = [(pos, value) for pos, value in hits if value is not None]
    if not hits:
        return None, None

    bank = cbr = None
    for pos, value in hits:
        bank_at = _last_before(_BANK_SECTION, text, pos)
        cbr_at = _last_before(_CBR_SECTION, text, pos)
        if bank_at is not None and (cbr_at is None or bank_at > cbr_at):
            bank = value if bank is None else bank
        elif cbr_at is not None:
            cbr = value if cbr is None else cbr

    if bank is None:
        bank = hits[1][1] if len(hits) >= 2 else hits[0][1]
        if cbr is None and len(hits) >= 2:
            cbr = hits[0][1]
    return bank, cbr


def car_links(raw_html: str, base_url: str) -> list[str]:
    """Ссылки на карточки авто — курс печатается только на них."""
    found: list[str] = []
    for href in _CAR_LINK.findall(raw_html):
        url = urljoin(base_url, html.unescape(href))
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        # Карточка авто оканчивается идентификатором с цифрами, раздел — нет.
        if any(ch.isdigit() for ch in tail) and url not in found:
            found.append(url)
    return found[:10]


def api_urls(raw_html: str) -> list[str]:
    """Адреса из скриптов, похожие на источник курса, — подсказка для наладки."""
    found = {
        url
        for url in re.findall(r'["\'](https?://[^"\'\s]{6,160}|/[^"\'\s]{4,160})["\']', raw_html)
        if re.search(r"kurs|курс|valut|currenc|rate|exchange|cny|yuan|juan", url, re.I)
    }
    return sorted(found)[:12]


def _as_float(token: str) -> float | None:
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def extract(
    text: str,
    *,
    low: float,
    high: float,
    pattern: str | None = None,
    raw: str | None = None,
) -> tuple[float | None, list[tuple[float, str]], bool]:
    """Возвращает (курс, кандидаты, сработал_ли_ручной_regex).

    Кандидаты — все правдоподобные числа рядом со словом «юань», в порядке
    близости к маркеру: первый и есть ответ.

    Ручной DOLGOV_REGEX ищется по исходному HTML (там живут атрибуты и JSON),
    а если не задан — работает эвристика по очищенному тексту. Заданный, но
    не сработавший regex к эвристике не откатывается: молчаливый откат
    маскировал бы опечатку в шаблоне.
    """
    if pattern:
        for source in (raw, text):
            if not source:
                continue
            match = re.search(pattern, source, re.I)
            if not match:
                continue
            value = _as_float(match.group(match.lastindex or 0))
            if value is None:
                continue
            window = source[max(0, match.start() - 40) : match.end() + 40]
            return value, [(value, _SPACES.sub(" ", window).strip())], True
        return None, [], True

    scored: list[tuple[int, float, str]] = []
    for marker in _MARKER.finditer(text):
        start, end = marker.span()
        window = text[max(0, start - 90) : end + 90]
        offset = start - max(0, start - 90)
        for number in _NUMBER.finditer(window):
            value = _as_float(number.group(0))
            if value is None or not (low <= value <= high):
                continue
            distance = min(abs(number.start() - offset), abs(number.end() - offset))
            # Дробные числа предпочтительнее целых: курс почти всегда с копейками.
            penalty = 0 if "." in number.group(0) or "," in number.group(0) else 25
            scored.append((distance + penalty, value, window.strip()))

    scored.sort(key=lambda item: item[0])
    candidates = [(value, window) for _, value, window in scored]
    return (candidates[0][0] if candidates else None), candidates, False


async def _load(session: aiohttp.ClientSession, url: str, debug: DolgovDebug) -> str | None:
    try:
        async with session.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _UA}, allow_redirects=True
        ) as resp:
            debug.status = resp.status
            resp.raise_for_status()
            return await resp.text(errors="replace")
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError) as exc:
        debug.error = f"{type(exc).__name__}: {exc}"
        log.debug("Dolgov: %s не открылась (%s)", url, debug.error)
        return None


async def fetch_page(
    session: aiohttp.ClientSession,
    url: str,
    *,
    low: float,
    high: float,
    pattern: str | None,
) -> tuple[DolgovQuote | None, DolgovDebug]:
    """Разбор одной страницы. Исключений не бросает — блок необязательный."""
    debug = DolgovDebug(url=url)
    raw = await _load(session, url, debug)
    if raw is None:
        return None, debug

    debug.html_len = len(raw)
    text = to_text(raw)
    debug.text_len = len(text)
    debug.marker_hits = len(_MARKER.findall(text))
    debug.marker_hits_raw = len(_MARKER.findall(raw))
    debug.script_urls = api_urls(raw)
    debug.yuan_hits = len(_YUAN_RATE.findall(text))

    # 1. Ручной шаблон, если задан, — он главнее всего.
    if pattern:
        value, candidates, _ = extract(text, low=low, high=high, pattern=pattern, raw=raw)
        debug.used_regex = True
        if value is not None:
            debug.picked, debug.source, debug.candidates = value, "regex", candidates[:8]
            return DolgovQuote(value=value, context=candidates[0][1][:200], url=url,
                               source="regex"), debug
        return None, debug

    # 2. Штатный формат Долгова: два курса, берём банковский.
    bank, cbr_quoted = extract_pair(text)
    if bank is not None and low <= bank <= high:
        window = ""
        match = _YUAN_RATE.search(text)
        if match:
            window = text[max(0, match.start() - 70) : match.end() + 70].strip()
        debug.picked, debug.source, debug.cbr_quoted = bank, "банки", cbr_quoted
        debug.candidates = [(bank, window)]
        return DolgovQuote(value=bank, context=window[:200], url=url,
                           cbr_quoted=cbr_quoted, source="банки"), debug

    # 3. Запасная эвристика: число рядом с любым упоминанием юаня.
    value, candidates, _ = extract(text, low=low, high=high)
    if value is None and debug.marker_hits_raw:
        # В видимом тексте пусто, но в исходнике маркеры есть — курс в <script>.
        value, candidates, _ = extract(to_text(raw, keep_scripts=True), low=low, high=high)
        debug.scanned_scripts = True

    debug.candidates = candidates[:8]
    debug.picked = value
    if value is None:
        return None, debug

    debug.source = "эвристика"
    return DolgovQuote(value=value, context=candidates[0][1][:200], url=url,
                       source="эвристика"), debug


async def fetch(
    session: aiohttp.ClientSession,
    url: str,
    *,
    low: float = 5.0,
    high: float = 30.0,
    pattern: str | None = None,
    catalog_url: str | None = None,
) -> tuple[DolgovQuote | None, DolgovDebug]:
    """Курс печатается на карточке конкретного авто, а карточки уходят в
    продажу и отдают 404. Поэтому при неудаче берём из каталога первую живую
    карточку и пробуем её — так ссылка чинит себя сама."""
    quote, debug = await fetch_page(session, url, low=low, high=high, pattern=pattern)
    if quote is not None or not catalog_url:
        return quote, debug

    catalog_debug = DolgovDebug(url=catalog_url)
    raw = await _load(session, catalog_url, catalog_debug)
    if raw is None:
        debug.error = debug.error or catalog_debug.error
        return None, debug

    for candidate_url in car_links(raw, catalog_url):
        if candidate_url.rstrip("/") == url.rstrip("/"):
            continue
        quote, fresh = await fetch_page(
            session, candidate_url, low=low, high=high, pattern=pattern
        )
        fresh.discovered_url = candidate_url
        if quote is not None:
            log.info("Dolgov: курс снят с найденной карточки %s", candidate_url)
            return quote, fresh
        debug = fresh

    return None, debug
