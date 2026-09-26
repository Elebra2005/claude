"""EVM-кошелёк целиком (все сети + DeFi) через Zerion API.

Свои силы здесь не годятся: EVM-сетей десятки, и у каждого лендинга,
стейкинга или пула свой контракт со своей логикой. Zerion собирает всё
это сам: токены во всех сетях, депозиты и займы в лендингах (Aave, Compound,
Morpho…), стейкинг, пулы ликвидности, награды — примерно то же, что
показывает DeBank или сам Rabby.

Ключ бесплатный: https://developers.zerion.io → войти → скопировать
API key (вида zk_dev_…) в .env как ZERION_API_KEY.

Займы (position_type = loan) идут с минусом: это долг, он уменьшает
стоимость кошелька.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime

import httpx

from .config import env
from .net import NO_RETRY
from .store import Store

log = logging.getLogger(__name__)

POSITIONS_URL = "https://api.zerion.io/v1/wallets/{address}/positions/"
MAX_PAGES = 10
# Лимиты бесплатного ключа. На 429 Zerion не долбим повторами (повторы
# только выбирают лимит дальше и продлевают блокировку): ждём столько,
# сколько он просит, а пока ждём — показываем последние полученные данные.
MIN_GAP_S = 1.2
DEFAULT_BLOCK_S = 15 * 60
CACHE_MAX_AGE_S = 3 * 3600
# Бесплатный (demo) ключ: 75 запросов позиций в сутки (заголовок
# ratelimit-limit: "75;w=86400"). Отчёт каждые 30 минут по двум адресам —
# это 96 запросов, лимит кончался к вечеру. Поэтому каждый адрес
# запрашиваем не чаще раза в REFRESH_S (двум адресам — 48 в сутки), а в
# отчётах между запросами — данные последнего запроса.
REFRESH_S = 55 * 60

# Пояснения для отчёта (например, «данные Zerion на 21:30»); wallet_watch
# очищает список в начале проверки и дописывает его в конец сообщения.
NOTES: list[str] = []
_last_request = 0.0

TYPE_LABEL = {
    "deposit": "депозит",
    "loan": "долг",
    "staked": "стейкинг",
    "locked": "заблокировано",
    "reward": "награды",
    "investment": "инвестиция",
    "airdrop": "аирдроп",
}


def _safe(text: str, limit: int = 20) -> str:
    """Текст из внешнего источника — без ссылок и мусора (см. _safe_symbol
    в wallet_watch.py: у фишинговых токенов в названиях бывают ссылки)."""
    clean = "".join(ch for ch in (text or "") if ch.isalnum() or ch in " .-")
    return clean.strip()[:limit]


def _parts(p: dict) -> tuple[str, str, str, str, float | None]:
    a = p.get("attributes") or {}
    symbol = _safe((a.get("fungible_info") or {}).get("symbol") or "", 12).upper()
    chain = ((p.get("relationships") or {}).get("chain") or {}).get("data", {}).get("id", "")
    return symbol, chain, a.get("position_type") or "wallet", a.get("protocol") or "", a.get("value")


def _drop_receipt_tokens(positions: list[dict]) -> list[dict]:
    """Убирает токены-квитанции, которые дублируют DeFi-позицию.

    Депозит в Aave Zerion отдаёт дважды: как позицию протокола ("WETH,
    депозит Aave V3") и как токен на кошельке (aToken, например AETHWETH) —
    это одни и те же деньги. Квитанцию узнаём так: обычный токен без
    протокола в той же сети, в символе которого есть символ депозита
    (aBasWETH ⊃ WETH), и стоимость почти та же (±5%: курс квитанции и
    депозита считается чуть по-разному).
    """
    defi = [
        (sym, chain, float(value)) for sym, chain, ptype, protocol, value in map(_parts, positions)
        if (ptype != "wallet" or protocol) and ptype != "loan" and value and sym
    ]
    used: set[int] = set()
    kept = []
    for p in positions:
        sym, chain, ptype, protocol, value = _parts(p)
        if ptype == "wallet" and not protocol and value and sym:
            match = next(
                (i for i, (dsym, dchain, dval) in enumerate(defi)
                 if i not in used and dchain == chain and dsym != sym and dsym in sym
                 and abs(float(value) - dval) <= 0.05 * dval),
                None,
            )
            if match is not None:
                used.add(match)
                continue
        kept.append(p)
    return kept


class _RateLimited(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"429, ждать {retry_after:.0f}с")
        self.retry_after = retry_after


def _from_cache(store: Store, address: str, reason: str, wallet_label: str) -> dict[str, dict] | None:
    raw = store.get_cursor(f"zerion_last_{address.lower()}")
    if raw:
        cached = json.loads(raw)
        if time.time() - cached["ts"] < CACHE_MAX_AGE_S:
            at = datetime.fromtimestamp(cached["ts"]).strftime("%H:%M")
            note = f"ℹ️ {wallet_label}: Zerion {reason}, данные на {at}"
            if note not in NOTES:
                NOTES.append(note)
            log.info("Zerion: %s для %s, беру данные на %s", reason, address, at)
            return cached["breakdown"]
    log.warning("Zerion: %s для %s, а свежих сохранённых данных нет", reason, address)
    return None


async def total_usd_zerion(
    client: httpx.AsyncClient, address: str, store: Store, wallet_label: str = "Zerion"
) -> dict[str, dict] | None:
    global _last_request
    key = env("ZERION_API_KEY")
    if not key:
        log.warning("wallet_watch: кошелёк chain=zerion, но ZERION_API_KEY не задан в .env")
        return None
    auth = "Basic " + base64.b64encode(f"{key}:".encode()).decode()

    blocked_until = float(store.get_cursor("zerion_blocked_until") or 0)
    if time.time() < blocked_until:
        return _from_cache(store, address, "ограничил запросы", wallet_label)
    raw = store.get_cursor(f"zerion_last_{address.lower()}")
    if raw:
        cached = json.loads(raw)
        if time.time() - cached["ts"] < REFRESH_S:
            return cached["breakdown"]

    url: str | None = POSITIONS_URL.format(address=address)
    params: dict | None = {
        "filter[positions]": "no_filter",   # и обычные токены, и DeFi-позиции
        "filter[trash]": "only_non_trash",
        "currency": "usd",
        "sort": "value",
        "page[size]": "100",
    }
    positions: list[dict] = []
    try:
        for _ in range(MAX_PAGES):
            wait = _last_request + MIN_GAP_S - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            _last_request = time.monotonic()
            resp = await client.get(
                url, params=params, headers={"Authorization": auth, "accept": "application/json"},
                extensions={NO_RETRY: True},
            )
            if resp.status_code == 429:
                # Zerion пишет, когда снимет ограничение, в ratelimit-reset
                # (секунды); Retry-After он не присылает.
                wait = next(
                    (float(v) for v in (resp.headers.get("retry-after", ""), resp.headers.get("ratelimit-reset", ""))
                     if v.isdigit()),
                    DEFAULT_BLOCK_S,
                )
                raise _RateLimited(wait)
            resp.raise_for_status()
            data = resp.json()
            positions += data.get("data", [])
            url = (data.get("links") or {}).get("next")
            params = None  # в ссылке next параметры уже есть
            if not url:
                break
    except _RateLimited as exc:
        store.set_cursor("zerion_blocked_until", str(time.time() + exc.retry_after))
        return _from_cache(store, address, "ограничил запросы", wallet_label)
    except Exception as exc:
        return _from_cache(store, address, f"не ответил ({type(exc).__name__})", wallet_label)

    positions = _drop_receipt_tokens(positions)
    breakdown: dict[str, dict] = {}
    for p in positions:
        a = p.get("attributes") or {}
        value = a.get("value")
        if value is None:
            continue  # нет цены — не оцениваем
        symbol = _safe((a.get("fungible_info") or {}).get("symbol") or "", 12).upper() or "?"
        chain = ((p.get("relationships") or {}).get("chain") or {}).get("data", {}).get("id", "")
        ptype = a.get("position_type") or "wallet"
        protocol = _safe(a.get("protocol") or "")

        usd = -float(value) if ptype == "loan" else float(value)
        # Сеть в ключ не входит: один и тот же токен в разных сетях — одна
        # строка (ETH в Ethereum + Base + Arbitrum = ETH). По той же причине
        # одинаковые токены с разных адресов кошелька складываются в
        # wallet_watch._merge. DeFi-позиции остаются отдельными строками по
        # протоколу и типу (депозит, стейкинг, долг).
        if ptype != "wallet" or protocol:
            what = " ".join(x for x in (TYPE_LABEL.get(ptype, ptype), protocol) if x)
            label = f"{symbol} ({what})"
        else:
            label = symbol

        key_ = f"zerion:{protocol}:{ptype}:{symbol}"
        if key_ in breakdown:
            breakdown[key_]["usd"] += usd
        else:
            breakdown[key_] = {"symbol": label, "usd": usd}
    store.set_cursor(f"zerion_last_{address.lower()}", json.dumps({"ts": time.time(), "breakdown": breakdown}))
    return breakdown
