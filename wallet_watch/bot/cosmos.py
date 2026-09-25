"""Сети Cosmos (кошелёк Keplr) через публичные REST (LCD) эндпоинты.

Keplr для каждой сети показывает свой адрес (cosmos1…, osmo1…, celestia1…),
но у сетей с одинаковым типом монеты (118) это один и тот же ключ, просто
с другим префиксом. Поэтому достаточно одного адреса cosmos1… — адреса
в остальных сетях получаются перекодированием bech32. Для сетей с другим
типом монеты (Injective, 60) адрес нужно указать отдельно.

По каждой сети учитывается: свободный баланс, застейканное, выводимое из
стейкинга (unbonding) и невыведенные награды. IBC-токены (ibc/…) на
балансе распознаются через denom trace, если базовый токен есть в таблице
ниже. Пулы ликвидности Osmosis (gamm/…) не оцениваются.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

# сеть -> (префикс адреса, REST-эндпоинт)
NETWORKS: dict[str, tuple[str, str]] = {
    "cosmoshub": ("cosmos", "https://cosmos-rest.publicnode.com"),
    "osmosis": ("osmo", "https://osmosis-rest.publicnode.com"),
    "celestia": ("celestia", "https://celestia-rest.publicnode.com"),
    "dydx": ("dydx", "https://dydx-rest.publicnode.com"),
    "akash": ("akash", "https://akash-rest.publicnode.com"),
    "stride": ("stride", "https://stride-rest.publicnode.com"),
    "neutron": ("neutron", "https://neutron-rest.publicnode.com"),
    "noble": ("noble", "https://noble-rest.publicnode.com"),
    "injective": ("inj", "https://injective-rest.publicnode.com"),
}
# Сети, адрес в которых нельзя получить из cosmos1… (другой тип монеты).
DIFFERENT_KEY = {"injective"}

# базовый denom -> (id CoinGecko, символ, знаков после запятой)
DENOMS: dict[str, tuple[str, str, int]] = {
    "uatom": ("cosmos", "ATOM", 6),
    "uosmo": ("osmosis", "OSMO", 6),
    "utia": ("celestia", "TIA", 6),
    "adydx": ("dydx-chain", "DYDX", 18),
    "uakt": ("akash-network", "AKT", 6),
    "ustrd": ("stride", "STRD", 6),
    "untrn": ("neutron-3", "NTRN", 6),
    "uusdc": ("usd-coin", "USDC", 6),
    "inj": ("injective-protocol", "INJ", 18),
}

# --- bech32 (BIP-173) ---

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values: list[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (b >> i) & 1 else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def convert_prefix(address: str, new_prefix: str) -> str:
    """cosmos1abc… -> osmo1…: те же данные, другой префикс и контрольная сумма."""
    address = address.lower()
    pos = address.rfind("1")
    hrp, data = address[:pos], [_CHARSET.index(c) for c in address[pos + 1:]]
    if _polymod(_hrp_expand(hrp) + data) != 1:
        raise ValueError(f"неверный bech32-адрес: {address}")
    payload = data[:-6]
    values = _hrp_expand(new_prefix) + payload
    mod = _polymod(values + [0] * 6) ^ 1
    checksum = [(mod >> 5 * (5 - i)) & 31 for i in range(6)]
    return new_prefix + "1" + "".join(_CHARSET[d] for d in payload + checksum)


# --- REST ---

async def _get(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.json()


async def _resolve_ibc(client: httpx.AsyncClient, rest: str, denom: str, cache: dict) -> str | None:
    """ibc/HASH -> базовый denom (uatom и т.п.). В новых версиях ibc-go
    эндпоинт переименован, поэтому пробуем оба."""
    if denom in cache:
        return cache[denom]
    h = denom.split("/", 1)[1]
    base = None
    for path in (f"/ibc/apps/transfer/v1/denom_traces/{h}", f"/ibc/apps/transfer/v1/denoms/{h}"):
        try:
            data = await _get(client, rest + path)
            base = (data.get("denom_trace") or {}).get("base_denom") or (data.get("denom") or {}).get("base")
            if base:
                break
        except Exception:
            continue
    cache[denom] = base
    return base


def _add(amounts: dict, denom: str, raw: float) -> None:
    info = DENOMS.get(denom)
    if info and raw:
        coin_id, symbol, decimals = info
        prev = amounts.get(coin_id, (symbol, 0.0))[1]
        amounts[coin_id] = (symbol, prev + raw / 10 ** decimals)


async def _network_amounts(client: httpx.AsyncClient, rest: str, address: str, amounts: dict, ibc_cache: dict) -> None:
    async def add(denom: str, raw: float) -> None:
        # ibc/… — токен другой сети (например, USDC в наградах dYdX).
        if denom.startswith("ibc/"):
            denom = await _resolve_ibc(client, rest, denom, ibc_cache) or denom
        _add(amounts, denom, raw)

    try:
        data = await _get(client, f"{rest}/cosmos/bank/v1beta1/balances/{address}?pagination.limit=500")
        for c in data.get("balances", []):
            await add(c["denom"], float(c["amount"]))
    except Exception as exc:
        log.warning("cosmos: баланс %s недоступен: %s", address, exc)

    try:
        data = await _get(client, f"{rest}/cosmos/staking/v1beta1/delegations/{address}")
        for d in data.get("delegation_responses", []):
            await add(d["balance"]["denom"], float(d["balance"]["amount"]))
    except Exception as exc:
        log.warning("cosmos: стейкинг %s недоступен: %s", address, exc)

    try:
        data = await _get(client, f"{rest}/cosmos/staking/v1beta1/delegators/{address}/unbonding_delegations")
        bond_denom = None
        for u in data.get("unbonding_responses", []):
            if bond_denom is None:
                params = await _get(client, f"{rest}/cosmos/staking/v1beta1/params")
                bond_denom = params["params"]["bond_denom"]
            for e in u.get("entries", []):
                await add(bond_denom, float(e["balance"]))
    except Exception as exc:
        log.warning("cosmos: unbonding %s недоступен: %s", address, exc)

    try:
        data = await _get(client, f"{rest}/cosmos/distribution/v1beta1/delegators/{address}/rewards")
        for c in data.get("total", []):
            await add(c["denom"], float(c["amount"]))
    except Exception as exc:
        log.warning("cosmos: награды %s недоступны: %s", address, exc)


async def cosmos_amounts(client: httpx.AsyncClient, wallet: dict) -> dict[str, tuple[str, float]]:
    """{coin_id: (symbol, количество)} по всем сетям кошелька.

    wallet (из config.yaml):
      address: cosmos1…           — основной адрес
      networks: [cosmoshub, …]    — опционально, по умолчанию все из NETWORKS
                                     кроме тех, где нужен отдельный адрес
      addresses: {injective: inj1…} — адреса для сетей с другим ключом
    """
    base = wallet.get("address", "")
    extra = wallet.get("addresses") or {}
    names = wallet.get("networks") or [n for n in NETWORKS if n not in DIFFERENT_KEY or n in extra]

    amounts: dict[str, tuple[str, float]] = {}
    for name in names:
        if name not in NETWORKS:
            log.warning("cosmos: неизвестная сеть %s (есть: %s)", name, ", ".join(NETWORKS))
            continue
        prefix, rest = NETWORKS[name]
        try:
            address = extra.get(name) or convert_prefix(base, prefix)
        except Exception as exc:
            log.warning("cosmos: не получить адрес в сети %s: %s", name, exc)
            continue
        await _network_amounts(client, rest, address, amounts, {})
    return amounts
