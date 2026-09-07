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


@dataclass
class DolgovQuote:
    value: float
    context: str          # фрагмент страницы, из которого взято число
    url: str


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


def to_text(raw_html: str, *, keep_scripts: bool = False) -> str:
    """Текст страницы. keep_scripts оставляет содержимое <script>: курс часто
    лежит там в JSON, а не в видимой разметке."""
    body = raw_html if keep_scripts else _DROP_BLOCKS.sub(" ", raw_html)
    body = _TAGS.sub(" ", body)
    return _SPACES.sub(" ", html.unescape(body)).strip()


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


async def fetch(
    session: aiohttp.ClientSession,
    url: str,
    *,
    low: float = 5.0,
    high: float = 30.0,
    pattern: str | None = None,
) -> tuple[DolgovQuote | None, DolgovDebug]:
    """Никогда не бросает исключений — блок необязательный."""
    debug = DolgovDebug(url=url)
    try:
        async with session.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _UA}, allow_redirects=True
        ) as resp:
            debug.status = resp.status
            resp.raise_for_status()
            raw = await resp.text(errors="replace")
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeDecodeError) as exc:
        debug.error = f"{type(exc).__name__}: {exc}"
        log.debug("Dolgov: страница не открылась (%s)", debug.error)
        return None, debug

    debug.html_len = len(raw)
    text = to_text(raw)
    debug.text_len = len(text)
    debug.marker_hits = len(_MARKER.findall(text))
    debug.marker_hits_raw = len(_MARKER.findall(raw))
    debug.script_urls = api_urls(raw)

    value, candidates, used_regex = extract(
        text, low=low, high=high, pattern=pattern, raw=raw
    )

    if value is None and not pattern and debug.marker_hits_raw:
        # В видимом тексте пусто, но в исходнике маркеры есть — значит курс
        # внутри <script>. Второй заход, уже без выбрасывания скриптов.
        deep = to_text(raw, keep_scripts=True)
        value, candidates, _ = extract(deep, low=low, high=high)
        debug.scanned_scripts = True

    debug.candidates = candidates[:8]
    debug.picked = value
    debug.used_regex = used_regex

    if value is None:
        log.debug(
            "Dolgov: курс не найден (маркеров %s, длина текста %s)",
            debug.marker_hits,
            debug.text_len,
        )
        return None, debug

    return DolgovQuote(value=value, context=candidates[0][1][:200], url=url), debug
