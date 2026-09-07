"""Две фоновые задачи: опрос ЦБ с проверкой просадок и ежеминутная
проверка, кому пора отправить сводку."""

import asyncio
import logging

from .service import RatesService

log = logging.getLogger(__name__)


async def poll_rates(service: RatesService) -> None:
    """ЦБ публикует курс раз в рабочий день (около 15:00 МСК), поэтому
    частый опрос дешёвый и почти всегда бесполезный — зато не пропустим."""
    while True:
        try:
            on_date = await service.refresh()
            if on_date:
                log.info("Курсы ЦБ обновлены на %s", on_date)
                await service.run_dip_alerts()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой в цикле опроса курсов")
        await asyncio.sleep(service.config.poll_interval)


async def poll_digests(service: RatesService) -> None:
    while True:
        try:
            await service.run_digests()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой в цикле рассылки сводок")
        await asyncio.sleep(60)


async def housekeeping(service: RatesService) -> None:
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            from . import storage

            await storage.run(service.store.purge_old_marks, 120)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой при очистке отметок")
