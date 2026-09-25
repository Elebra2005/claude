"""Баланс на бирже Bybit через API V5 (ключ только на чтение).

На бирже деньги не лежат на вашем ончейн-адресе: адрес депозита только
принимает монеты, биржа сразу сметает их в свои кошельки. Поэтому
балансы берутся из API аккаунта, а не из блокчейна.

Считаются три места, где на Bybit лежат монеты:
  - Единый торговый аккаунт (UNIFIED) — Bybit сам отдаёт usdValue по монете;
  - Финансовый аккаунт (FUND) — только количество, цена берётся со спота Bybit;
  - Bybit Earn (гибкие сбережения и ончейн-стейкинг) — тоже по цене спота.
Любая из частей может не ответить (нет прав у ключа, нет такого аккаунта) —
тогда она пропускается, остальные считаются.

Ключ: bybit.com → Профиль → API → Создать новый ключ → «Системный» →
права только «Только чтение» (Read-Only). Торговлю и вывод НЕ включать.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

import httpx

from .config import env

log = logging.getLogger(__name__)

RECV_WINDOW = "10000"
STABLES = {"USDT": 1.0}


def _base_url() -> str:
    # api.bybit.com; для отдельных регионов — api.bybit.kz / api.bybit.nl и т.п.
    return (env("BYBIT_API_URL", "https://api.bybit.com") or "").rstrip("/")


async def _private_get(client: httpx.AsyncClient, key: str, secret: str, path: str, params: dict) -> dict:
    query = urlencode(sorted(params.items()))
    ts = str(int(time.time() * 1000))
    sign = hmac.new(secret.encode(), (ts + key + RECV_WINDOW + query).encode(), hashlib.sha256).hexdigest()
    resp = await client.get(
        f"{_base_url()}{path}?{query}",
        headers={
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "X-BAPI-SIGN": sign,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("retCode") != 0:
        raise RuntimeError(f"{path}: {data.get('retCode')} {data.get('retMsg')}")
    return data["result"]


async def _spot_prices(client: httpx.AsyncClient) -> dict[str, float]:
    """Цена монеты в USDT по споту Bybit (публичный эндпоинт, без ключа)."""
    resp = await client.get(f"{_base_url()}/v5/market/tickers", params={"category": "spot"})
    resp.raise_for_status()
    prices = dict(STABLES)
    for t in resp.json()["result"]["list"]:
        sym = t["symbol"]
        if sym.endswith("USDT") and t.get("lastPrice"):
            prices.setdefault(sym[:-4], float(t["lastPrice"]))
    return prices


def _f(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def total_usd_bybit(client: httpx.AsyncClient) -> dict[str, dict] | None:
    """Разбивка {coin_id: {"symbol", "usd"}} по всем аккаунтам Bybit —
    тот же формат, что и у ончейн-бэкендов в wallet_watch.py."""
    key, secret = env("BYBIT_API_KEY"), env("BYBIT_API_SECRET")
    if not key or not secret:
        log.warning("wallet_watch: кошелёк chain=bybit, но BYBIT_API_KEY/BYBIT_API_SECRET не заданы в .env")
        return None

    usd: dict[str, float] = {}
    amounts: dict[str, float] = {}  # то, что нужно оценить по споту
    ok = False

    try:
        result = await _private_get(client, key, secret, "/v5/account/wallet-balance", {"accountType": "UNIFIED"})
        for acc in result.get("list", []):
            for c in acc.get("coin", []):
                if _f(c.get("usdValue")):
                    usd[c["coin"]] = usd.get(c["coin"], 0.0) + _f(c["usdValue"])
        ok = True
    except Exception as exc:
        log.warning("Bybit: единый торговый аккаунт недоступен: %s", exc)

    try:
        result = await _private_get(
            client, key, secret, "/v5/asset/transfer/query-account-coins-balance", {"accountType": "FUND"}
        )
        for c in result.get("balance", []):
            if _f(c.get("walletBalance")):
                amounts[c["coin"]] = amounts.get(c["coin"], 0.0) + _f(c["walletBalance"])
        ok = True
    except Exception as exc:
        log.warning("Bybit: финансовый аккаунт недоступен: %s", exc)

    for category in ("FlexibleSaving", "OnChain"):
        try:
            result = await _private_get(client, key, secret, "/v5/earn/position", {"category": category})
            for p in result.get("list", []):
                if _f(p.get("amount")):
                    amounts[p["coin"]] = amounts.get(p["coin"], 0.0) + _f(p["amount"])
            ok = True
        except Exception as exc:
            log.debug("Bybit Earn (%s) недоступен: %s", category, exc)

    if not ok:
        return None

    if amounts:
        try:
            prices = await _spot_prices(client)
        except Exception as exc:
            log.warning("Bybit: цены спота недоступны: %s", exc)
            prices = dict(STABLES)
        for coin, amount in amounts.items():
            price = prices.get(coin)
            if price:
                usd[coin] = usd.get(coin, 0.0) + amount * price
            else:
                log.debug("Bybit: нет цены для %s, не учитываю", coin)

    return {f"bybit:{coin}": {"symbol": coin, "usd": value} for coin, value in usd.items()}
