"""Биржевой курс CNY/RUB с Московской биржи (ISS, без ключа).

Курс ЦБ — это вчерашняя фиксация, а платите вы по рынку. Для юаня биржевой
курс доступен (инструмент CNYRUB_TOM), для доллара и евро торгов на MOEX
с июня 2024 года нет, поэтому модуль работает только по юаню.
"""

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

ISS_URL = (
    "https://iss.moex.com/iss/engines/currency/markets/selt/boards/CETS"
    "/securities/{secid}.json"
)
SECID = {"CNY": "CNYRUB_TOM"}

_TIMEOUT = aiohttp.ClientTimeout(total=20)


@dataclass(frozen=True)
class MoexQuote:
    char_code: str
    last: float
    prev: float | None
    updated_at: str | None

    @property
    def change_pct(self) -> float | None:
        if not self.prev:
            return None
        return (self.last - self.prev) / self.prev * 100.0


def _column(block: dict, row: list, name: str):
    try:
        return row[block["columns"].index(name)]
    except (KeyError, ValueError, IndexError):
        return None


async def fetch(session: aiohttp.ClientSession, char_code: str) -> MoexQuote | None:
    """Возвращает None при любой проблеме — биржевой блок необязательный."""
    secid = SECID.get(char_code.upper())
    if not secid:
        return None

    url = ISS_URL.format(secid=secid)
    params = {"iss.meta": "off", "iss.only": "marketdata,securities"}
    try:
        async with session.get(url, params=params, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log.warning("MOEX %s недоступна: %s", secid, exc)
        return None

    market = payload.get("marketdata") or {}
    securities = payload.get("securities") or {}
    market_rows = market.get("data") or []
    security_rows = securities.get("data") or []
    if not market_rows:
        return None

    row = market_rows[0]
    last = None
    for field in ("LAST", "MARKETPRICE", "LCURRENTPRICE", "WAPRICE"):
        candidate = _column(market, row, field)
        if isinstance(candidate, (int, float)) and candidate > 0:
            last = float(candidate)
            break

    prev = None
    if security_rows:
        for field in ("PREVPRICE", "PREVWAPRICE", "PREVLEGALCLOSEPRICE"):
            candidate = _column(securities, security_rows[0], field)
            if isinstance(candidate, (int, float)) and candidate > 0:
                prev = float(candidate)
                break

    if last is None:
        # Вне торговой сессии LAST пустой — показываем вчерашнее закрытие.
        last = prev
    if last is None:
        return None

    return MoexQuote(
        char_code=char_code.upper(),
        last=last,
        prev=prev,
        updated_at=_column(market, row, "UPDATETIME"),
    )
