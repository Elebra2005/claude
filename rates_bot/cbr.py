"""Клиент официального API Банка России (www.cbr.ru/scripts).

Два endpoint-а:
  XML_daily.asp   — все курсы на дату;
  XML_dynamic.asp — история по одной валюте за период.

Оба отдают windows-1251, десятичный разделитель — запятая. expat такую
кодировку не знает, поэтому декодируем сами и срезаем XML-декларацию.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta

import aiohttp

log = logging.getLogger(__name__)

DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
DYNAMIC_URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"

_XML_DECL = re.compile(rb"^\s*<\?xml[^>]*\?>")
_TIMEOUT = aiohttp.ClientTimeout(total=30)
_RETRIES = 4


@dataclass(frozen=True)
class Currency:
    """Справочная запись о валюте из XML_daily."""

    cbr_id: str      # напр. R01375
    char_code: str   # напр. CNY
    name: str        # напр. Китайский юань


@dataclass(frozen=True)
class Quote:
    char_code: str
    on_date: date
    value: float     # рублей за ОДНУ единицу валюты


class CbrError(RuntimeError):
    pass


def _parse_xml(raw: bytes) -> ET.Element:
    body = _XML_DECL.sub(b"", raw, count=1)
    return ET.fromstring(body.decode("cp1251", errors="replace"))


def _num(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.strip().replace(",", ".").replace("\xa0", "").replace(" ", ""))
    except ValueError:
        return None


def _unit_rate(node: ET.Element) -> float | None:
    """Курс за одну единицу валюты.

    У VunitRate он уже пересчитан; если тега нет — делим Value на Nominal
    (у иены Nominal=100, у юаня до 2023 года был 10).
    """
    unit = _num(node.findtext("VunitRate"))
    if unit is not None and unit > 0:
        return unit
    value = _num(node.findtext("Value"))
    nominal = _num(node.findtext("Nominal")) or 1.0
    if value is None or nominal <= 0:
        return None
    return value / nominal


def _fmt(day: date) -> str:
    return day.strftime("%d/%m/%Y")


class CbrClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._directory: dict[str, Currency] = {}

    async def _get(self, url: str, params: dict[str, str]) -> bytes:
        last: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                async with self._session.get(url, params=params, timeout=_TIMEOUT) as resp:
                    resp.raise_for_status()
                    return await resp.read()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last = exc
                delay = 2 ** attempt
                log.warning("ЦБ %s: попытка %s не удалась (%s), жду %sс", url, attempt + 1, exc, delay)
                await asyncio.sleep(delay)
        raise CbrError(f"ЦБ недоступен: {last}")

    async def directory(self, refresh: bool = False) -> dict[str, Currency]:
        """CharCode -> Currency. Коды валют берём из ответа ЦБ, а не хардкодим."""
        if self._directory and not refresh:
            return self._directory

        root = _parse_xml(await self._get(DAILY_URL, {}))
        found: dict[str, Currency] = {}
        for valute in root.findall("Valute"):
            char_code = (valute.findtext("CharCode") or "").strip().upper()
            cbr_id = (valute.get("ID") or "").strip()
            if not char_code or not cbr_id:
                continue
            found[char_code] = Currency(
                cbr_id=cbr_id,
                char_code=char_code,
                name=(valute.findtext("Name") or char_code).strip(),
            )
        if not found:
            raise CbrError("ЦБ вернул пустой справочник валют")
        self._directory = found
        return found

    async def daily(self, on_date: date | None = None) -> tuple[date, dict[str, float]]:
        """Курсы на дату. ЦБ сам отдаёт ближайшую предыдущую дату публикации."""
        params = {"date_req": _fmt(on_date)} if on_date else {}
        root = _parse_xml(await self._get(DAILY_URL, params))

        raw_date = (root.get("Date") or "").strip()
        try:
            actual = date(int(raw_date[6:10]), int(raw_date[3:5]), int(raw_date[0:2]))
        except (ValueError, IndexError):
            actual = on_date or date.today()

        rates: dict[str, float] = {}
        for valute in root.findall("Valute"):
            char_code = (valute.findtext("CharCode") or "").strip().upper()
            rate = _unit_rate(valute)
            if char_code and rate:
                rates[char_code] = rate
        if not rates:
            raise CbrError(f"ЦБ не вернул курсов на {actual}")
        return actual, rates

    async def history(self, char_code: str, since: date, until: date) -> list[Quote]:
        """История по одной валюте. ЦБ ограничивает период — режем по годам."""
        directory = await self.directory()
        currency = directory.get(char_code.upper())
        if currency is None:
            raise CbrError(f"ЦБ не знает валюту {char_code}")

        quotes: list[Quote] = []
        chunk_start = since
        while chunk_start <= until:
            chunk_end = min(date(chunk_start.year, 12, 31), until)
            raw = await self._get(
                DYNAMIC_URL,
                {
                    "date_req1": _fmt(chunk_start),
                    "date_req2": _fmt(chunk_end),
                    "VAL_NM_RQ": currency.cbr_id,
                },
            )
            root = _parse_xml(raw)
            for record in root.findall("Record"):
                raw_date = (record.get("Date") or "").strip()
                rate = _unit_rate(record)
                if rate is None or len(raw_date) != 10:
                    continue
                try:
                    day = date(int(raw_date[6:10]), int(raw_date[3:5]), int(raw_date[0:2]))
                except ValueError:
                    continue
                quotes.append(Quote(char_code=currency.char_code, on_date=day, value=rate))

            chunk_start = chunk_end + timedelta(days=1)
            await asyncio.sleep(0.2)  # не долбим ЦБ

        quotes.sort(key=lambda q: q.on_date)
        return quotes
