"""Точка входа: python -m rates_bot"""

import asyncio
import logging
import sys

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import handlers, scheduler, storage
from .config import Config
from .service import RatesService
from .storage import Storage

log = logging.getLogger("rates_bot")


async def amain() -> None:
    config = Config.load()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Валюты: %s, основная: %s", ", ".join(config.currencies), config.primary_currency)

    store = Storage(config.db_path)
    for chat_id in config.admin_chat_ids:
        await storage.run(store.upsert_subscriber, chat_id)

    bot = Bot(token=config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(handlers.router)

    timeout = aiohttp.ClientTimeout(total=45)
    headers = {"User-Agent": "rates-bot/1.0 (+telegram)"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        service = RatesService(config, store, session, bot)
        dispatcher["service"] = service

        # Справочник и свежий курс нужны до первой команды пользователя.
        try:
            await service.cbr.directory()
            await service.refresh()
        except Exception:
            log.exception("Первичная загрузка курсов не удалась — продолжаю, повторю в цикле")

        tasks = [
            asyncio.create_task(scheduler.poll_rates(service), name="poll_rates"),
            asyncio.create_task(scheduler.poll_digests(service), name="poll_digests"),
            asyncio.create_task(scheduler.housekeeping(service), name="housekeeping"),
            asyncio.create_task(service.backfill(), name="backfill"),
        ]
        try:
            await dispatcher.start_polling(bot, service=service)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await storage.run(store.close)


def main() -> None:
    try:
        asyncio.run(amain())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановлен")
    except RuntimeError as exc:
        print(f"Ошибка запуска: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
