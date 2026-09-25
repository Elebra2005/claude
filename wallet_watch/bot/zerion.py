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

import base64
import logging

import httpx

from .config import env

log = logging.getLogger(__name__)

POSITIONS_URL = "https://api.zerion.io/v1/wallets/{address}/positions/"
MAX_PAGES = 10

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


def _chain_name(chain_id: str) -> str:
    return " ".join(part.capitalize() for part in (chain_id or "").split("-"))


async def total_usd_zerion(client: httpx.AsyncClient, address: str) -> dict[str, dict] | None:
    key = env("ZERION_API_KEY")
    if not key:
        log.warning("wallet_watch: кошелёк chain=zerion, но ZERION_API_KEY не задан в .env")
        return None
    auth = "Basic " + base64.b64encode(f"{key}:".encode()).decode()

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
            resp = await client.get(url, params=params, headers={"Authorization": auth, "accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
            positions += data.get("data", [])
            url = (data.get("links") or {}).get("next")
            params = None  # в ссылке next параметры уже есть
            if not url:
                break
    except Exception as exc:
        log.warning("Zerion: не удалось получить позиции %s: %s", address, exc)
        return None

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
        where = _chain_name(chain)
        if ptype != "wallet" or protocol:
            what = " ".join(x for x in (TYPE_LABEL.get(ptype, ptype), protocol) if x)
            where = f"{what}, {where}" if where else what
        label = f"{symbol} ({where})" if where else symbol

        key_ = f"zerion:{chain}:{protocol}:{ptype}:{symbol}"
        if key_ in breakdown:
            breakdown[key_]["usd"] += usd
        else:
            breakdown[key_] = {"symbol": label, "usd": usd}
    return breakdown
