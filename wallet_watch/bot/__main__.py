"""Точка входа: python -m bot"""

from __future__ import annotations

import asyncio
import logging

from .config import env, load_config
from .store import Store
from .wallet_watch import run_wallet_watch


def main() -> None:
    logging.basicConfig(
        level=env("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()
    if not (cfg.get("wallet_watch") or {}).get("enabled", False):
        logging.getLogger(__name__).warning("wallet_watch.enabled = false в config.yaml — выходим")
        return
    store = Store(env("WALLET_WATCH_DB", "data/state.db"))
    asyncio.run(run_wallet_watch(cfg, store))


if __name__ == "__main__":
    main()
