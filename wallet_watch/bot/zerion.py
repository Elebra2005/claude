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
# Количества позиций меняются, только когда вы сами что-то делаете, поэтому
# сохранённые данные годятся надолго: цены к ним каждый отчёт берутся свежие.
CACHE_MAX_AGE_S = 48 * 3600
STALE_NOTE_S = 6 * 3600
# Бесплатный (demo) ключ: 75 запросов позиций в сутки (заголовок
# ratelimit-limit: "75;w=86400"). Поэтому у Zerion берём только СОСТАВ
# кошелька — какие позиции и в каком количестве — и не чаще раза в
# REFRESH_S на адрес; а цены к этим количествам в каждом отчёте берём у
# DefiLlama (бесплатно, без ключа и суточного лимита). Так отчёт может
# приходить сколь угодно часто, а изменения в $ и % по Rabby актуальны.
REFRESH_S = 3 * 3600
DAILY_BUDGET = 60  # из 75 — с запасом на перезапуски и ручные проверки
LLAMA_PRICES = "https://coins.llama.fi/prices/current/"
# Сеть Zerion -> сеть DefiLlama (где названия различаются).
LLAMA_CHAIN = {
    "avalanche": "avax", "binance-smart-chain": "bsc", "zksync-era": "era", "xdai": "xdai",
    "gnosis": "xdai", "manta-pacific": "manta", "polygon-zkevm": "polygon_zkevm",
}
# Нативные монеты сетей (у них нет адреса контракта) -> id CoinGecko.
NATIVE_PRICE = {
    "ETH": "coingecko:ethereum", "AVAX": "coingecko:avalanche-2", "BNB": "coingecko:binancecoin",
    "POL": "coingecko:polygon-ecosystem-token", "MATIC": "coingecko:matic-network",
    "MNT": "coingecko:mantle", "XDAI": "coingecko:xdai", "CELO": "coingecko:celo",
    "FTM": "coingecko:fantom", "S": "coingecko:sonic-3", "BERA": "coingecko:berachain-bera",
    "SOL": "coingecko:solana",
}
# Сколько адресов считается через Zerion (выставляет wallet_watch.check_once):
# чем их больше, тем реже обновляется каждый, чтобы уложиться в DAILY_BUDGET.
ADDRESS_COUNT = 1


def refresh_s() -> float:
    return max(REFRESH_S, 86400 * ADDRESS_COUNT / DAILY_BUDGET)

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


def _price_key(p: dict) -> str | None:
    """Ключ цены DefiLlama для позиции: сеть:адрес контракта токена, а для
    нативной монеты сети — её id CoinGecko."""
    a = p.get("attributes") or {}
    fi = a.get("fungible_info") or {}
    chain = ((p.get("relationships") or {}).get("chain") or {}).get("data", {}).get("id", "")
    for impl in fi.get("implementations") or []:
        if impl.get("chain_id") == chain and impl.get("address"):
            return f"{LLAMA_CHAIN.get(chain, chain)}:{impl['address']}"
    return NATIVE_PRICE.get((fi.get("symbol") or "").upper())


def _parse(positions: list[dict]) -> list[dict]:
    """Позиции Zerion -> компактный список: что, сколько, откуда брать цену."""
    items = []
    for p in _drop_receipt_tokens(positions):
        a = p.get("attributes") or {}
        value = a.get("value")
        if value is None:
            continue  # нет цены — не оцениваем
        symbol = _safe((a.get("fungible_info") or {}).get("symbol") or "", 12).upper() or "?"
        ptype = a.get("position_type") or "wallet"
        protocol = _safe(a.get("protocol") or "")
        sign = -1.0 if ptype == "loan" else 1.0  # долг уменьшает стоимость кошелька
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
        items.append({
            "key": f"zerion:{protocol}:{ptype}:{symbol}",
            "label": label,
            "qty": float(((a.get("quantity") or {}).get("float")) or 0),
            "sign": sign,
            "price_key": _price_key(p),
            "usd": sign * float(value),
        })
    return items


async def _llama_prices(client: httpx.AsyncClient, keys: set[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    keys_l = sorted(k for k in keys if k)
    for i in range(0, len(keys_l), 80):
        try:
            resp = await client.get(LLAMA_PRICES + ",".join(keys_l[i:i + 80]))
            resp.raise_for_status()
            for k, v in (resp.json().get("coins") or {}).items():
                if v.get("price"):
                    prices[k] = float(v["price"])
        except Exception as exc:
            # Без свежей цены позиция просто останется по последней цене Zerion.
            log.info("DefiLlama: цены недоступны (%s)", exc)
    return prices


def _aggregate(items: list[dict], prices: dict[str, float]) -> dict[str, dict]:
    breakdown: dict[str, dict] = {}
    for it in items:
        price = prices.get(it["price_key"]) if it.get("price_key") else None
        usd = it["sign"] * it["qty"] * price if price and it["qty"] else it["usd"]
        if it["key"] in breakdown:
            breakdown[it["key"]]["usd"] += usd
        else:
            breakdown[it["key"]] = {"symbol": it["label"], "usd": usd}
    return breakdown


def _note(wallet_label: str, reason: str, ts: float) -> None:
    at = datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
    note = f"ℹ️ {wallet_label}: Zerion {reason}, состав кошелька на {at} (цены свежие)"
    if note not in NOTES:
        NOTES.append(note)


async def _fetch_positions(client: httpx.AsyncClient, address: str, auth: str) -> list[dict]:
    global _last_request
    url: str | None = POSITIONS_URL.format(address=address)
    params: dict | None = {
        "filter[positions]": "no_filter",   # и обычные токены, и DeFi-позиции
        "filter[trash]": "only_non_trash",
        "currency": "usd",
        "sort": "value",
        "page[size]": "100",
    }
    positions: list[dict] = []
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
    return positions


async def total_usd_zerion(
    client: httpx.AsyncClient, address: str, store: Store, wallet_label: str = "Zerion"
) -> dict[str, dict] | None:
    key = env("ZERION_API_KEY")
    if not key:
        log.warning("wallet_watch: кошелёк chain=zerion, но ZERION_API_KEY не задан в .env")
        return None
    auth = "Basic " + base64.b64encode(f"{key}:".encode()).decode()

    cache_key = f"zerion_pos_{address.lower()}"
    raw = store.get_cursor(cache_key)
    cached = json.loads(raw) if raw else None
    age = time.time() - cached["ts"] if cached else None
    blocked = time.time() < float(store.get_cursor("zerion_blocked_until") or 0)

    if cached and age < CACHE_MAX_AGE_S and (age < refresh_s() or blocked):
        items, reason = cached["items"], "ограничил запросы" if blocked else None
    else:
        reason = None
        try:
            if blocked:
                raise _RateLimited(0)
            items = _parse(await _fetch_positions(client, address, auth))
            store.set_cursor(cache_key, json.dumps({"ts": time.time(), "items": items}))
            return _aggregate(items, {})  # только что от Zerion — цены в нём свежие
        except _RateLimited as exc:
            if exc.retry_after:
                store.set_cursor("zerion_blocked_until", str(time.time() + exc.retry_after))
            reason = "ограничил запросы"
        except Exception as exc:
            reason = f"не ответил ({type(exc).__name__})"
        if not cached or age > CACHE_MAX_AGE_S:
            log.warning("Zerion: %s для %s, а сохранённого состава кошелька нет", reason, address)
            return None
        items = cached["items"]
        log.info("Zerion: %s для %s, беру сохранённый состав кошелька", reason, address)

    if reason and age > STALE_NOTE_S:
        _note(wallet_label, reason, cached["ts"])
    prices = await _llama_prices(client, {it.get("price_key") for it in items})
    return _aggregate(items, prices)
