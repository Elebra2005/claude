"""Диагностика стейкинга STRK: docker exec wallet-watch python -m bot.diag_starknet

Показывает, докуда просканирована история, куда уходил STRK с кошелька и
что отвечают эти адреса на запросы пула стейкинга.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from .config import env, load_config
from .net import RetryTransport
from .store import Store
from .wallet_watch import STARKNET_RPC, STARKNET_STRK, _rpc, _starknet_token_balance

SELECTORS = {
    "pool_member_info_v1": "0x2568ae59c943c8367eb5c7690be688385a1100f8ee3d14db8e693dec9aec585",
    "get_pool_member_info_v1": "0xa0ec7d248e7cac7ad635c76ae431955a3ded9d7d9da3f80ee03c5c2383d9bf",
    "pool_member_info": "0xcf37a862e5bf34bd0e858865ea02d4ba6db9cc722f3424eb452c94d4ea567f",
    "get_pool_member_info": "0x39e4ef1193f67dfc08989c1e5a563cfd2d66c9483df72d581c2d02974351266",
}


async def main() -> None:
    cfg = load_config()
    wallets = [w for w in cfg["wallet_watch"]["wallets"] if w.get("chain") == "starknet"]
    store = Store(env("WALLET_WATCH_DB", "data/state.db"))
    async with httpx.AsyncClient(timeout=60, transport=RetryTransport()) as client:
        head = await _rpc(client, STARKNET_RPC, "starknet_blockNumber", [])
        for w in wallets:
            address = w["address"]
            key = f"wallet_tokens_starknet_{address.lower()}"
            scanned = store.get_cursor(f"{key}_scanned_block")
            print(f"== {w.get('label')} {address}")
            print(f"история просканирована до блока {scanned} из {head}")
            bal = await _starknet_token_balance(client, STARKNET_STRK, address)
            print(f"STRK на кошельке: {bal}")
            print(f"найденные пулы: {sorted(store.get_snapshot(f'{key}_pools') or [])}")
            recipients = sorted(store.get_snapshot(f"{key}_strk_out") or [])
            print(f"куда уходил STRK ({len(recipients)}):")
            for r in recipients:
                print(f"  {r}")
                for name, sel in SELECTORS.items():
                    try:
                        res = await _rpc(client, STARKNET_RPC, "starknet_call", [
                            {"contract_address": r, "entry_point_selector": sel, "calldata": [address]}, "latest"])
                        print(f"    {name}: {res}")
                    except Exception as exc:
                        print(f"    {name}: ошибка {str(exc)[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
