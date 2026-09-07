"""Связующий слой: тянет курсы у ЦБ, кладёт в SQLite, считает статистику
и рассылает сообщения подписчикам."""

import asyncio
import logging
from datetime import date, datetime, timedelta

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from . import analytics, chart, dolgov, formatting, moex, storage
from .analytics import Stats
from .cbr import CbrClient, CbrError
from .dolgov import DolgovDebug, DolgovQuote
from .config import MSK, Config
from .storage import Storage

log = logging.getLogger(__name__)


class RatesService:
    def __init__(
        self,
        config: Config,
        store: Storage,
        session: aiohttp.ClientSession,
        bot: Bot,
    ) -> None:
        self.config = config
        self.store = store
        self.session = session
        self.bot = bot
        self.cbr = CbrClient(session)
        self._refresh_lock = asyncio.Lock()
        self.last_dolgov: DolgovQuote | None = None
        self.last_dolgov_debug: DolgovDebug | None = None

    # --- загрузка данных --------------------------------------------------

    async def backfill(self) -> None:
        """Однократно при старте: подтянуть историю, которой ещё нет в базе."""
        until = datetime.now(MSK).date()
        since = until.replace(year=until.year - self.config.backfill_years)
        for code in self.config.currencies:
            have = await storage.run(self.store.count, code)
            if have > 200:
                log.info("%s: в базе %s записей, история уже есть", code, have)
                continue
            log.info("%s: загружаю историю с %s", code, since)
            try:
                quotes = await self.cbr.history(code, since, until)
            except CbrError as exc:
                log.error("%s: история не загрузилась (%s)", code, exc)
                continue
            saved = await storage.run(
                self.store.save_rates, code, [(q.on_date, q.value) for q in quotes]
            )
            log.info("%s: сохранено %s значений", code, saved)

    async def refresh(self) -> date | None:
        """Забрать свежую публикацию ЦБ. Возвращает дату курса."""
        async with self._refresh_lock:
            try:
                on_date, rates = await self.cbr.daily()
            except CbrError as exc:
                log.error("Свежие курсы не получены: %s", exc)
                return None

            for code in self.config.currencies:
                value = rates.get(code)
                if value is None:
                    log.warning("ЦБ не отдал курс %s", code)
                    continue
                await storage.run(self.store.save_rates, code, [(on_date, value)])

            await self.refresh_dolgov()
            return on_date

    async def refresh_dolgov(self) -> DolgovQuote | None:
        """Курс перевозчика меняется в течение дня — пишем последнее значение
        за сегодня, перезаписывая предыдущее."""
        if not self.config.dolgov_enabled:
            return None
        quote, debug = await dolgov.fetch(
            self.session,
            self.config.dolgov_url,
            low=self.config.dolgov_min,
            high=self.config.dolgov_max,
            pattern=self.config.dolgov_regex,
        )
        self.last_dolgov_debug = debug
        if quote is None:
            return None
        self.last_dolgov = quote
        await storage.run(
            self.store.save_rates, dolgov.CODE, [(datetime.now(MSK).date(), quote.value)]
        )
        return quote

    # --- расчёты ----------------------------------------------------------

    async def stats(self, code: str, days: int = 400) -> Stats | None:
        series = await storage.run(self.store.series, code, days)
        return analytics.compute(
            code,
            series,
            ma_window=self.config.dip_ma_window_days,
            low_window=self.config.dip_low_window_days,
        )

    async def all_stats(self) -> list[Stats]:
        result = []
        for code in self.config.currencies:
            item = await self.stats(code)
            if item:
                result.append(item)
        return result

    async def alert_codes(self) -> list[str]:
        """Валюты ЦБ плюс курс Долгова — по нему просадка важнее всего."""
        codes = list(self.config.currencies)
        if self.config.dolgov_enabled:
            codes.append(dolgov.CODE)
        return codes

    async def chart_png(self, days: int | None = None) -> tuple[bytes | None, int]:
        days = days or self.config.chart_days
        cutoff = datetime.now(MSK).date() - timedelta(days=days)
        cbr_series = [
            row for row in await storage.run(self.store.series, "CNY", days * 2)
            if row[0] >= cutoff
        ]
        dolgov_series = [
            row for row in await storage.run(self.store.series, dolgov.CODE, days * 2)
            if row[0] >= cutoff
        ]
        return chart.render(cbr_series, dolgov_series, days=days), days

    async def moex_quote(self) -> moex.MoexQuote | None:
        if not self.config.moex_enabled:
            return None
        return await moex.fetch(self.session, self.config.primary_currency)

    async def digest_text(self, chat_id: int | None = None) -> str | None:
        blocks = await self.all_stats()
        if not blocks:
            return None
        targets: list[tuple[str, float]] = []
        if chat_id is not None:
            targets = [
                (code, level)
                for _, code, level in await storage.run(self.store.targets, chat_id)
            ]
        quote = await self.moex_quote()
        return formatting.digest(
            blocks[0].on_date, blocks, quote, targets, self.last_dolgov
        )

    # --- отправка ---------------------------------------------------------

    async def send(self, chat_id: int, text: str) -> bool:
        """True — доставлено. Заблокировавших бота отключаем."""
        for _ in range(3):
            try:
                await self.bot.send_message(
                    chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
                )
                return True
            except TelegramRetryAfter as exc:
                log.warning("Telegram просит подождать %sс", exc.retry_after)
                await asyncio.sleep(exc.retry_after + 1)
            except TelegramForbiddenError:
                log.info("chat %s заблокировал бота — отключаю", chat_id)
                await storage.run(self.store.set_flag, chat_id, "active", False)
                return False
            except TelegramBadRequest as exc:
                log.error("chat %s: сообщение отклонено (%s)", chat_id, exc)
                return False
        return False

    async def send_photo(self, chat_id: int, png: bytes, caption: str = "") -> bool:
        photo = BufferedInputFile(png, filename="cny.png")
        try:
            await self.bot.send_photo(chat_id, photo, caption=caption[:1024])
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            await storage.run(self.store.set_flag, chat_id, "active", False)
        except TelegramBadRequest as exc:
            log.error("chat %s: график отклонён (%s)", chat_id, exc)
        return False

    async def broadcast(self, recipients: list[int], text: str) -> int:
        delivered = 0
        for chat_id in recipients:
            if await self.send(chat_id, text):
                delivered += 1
            await asyncio.sleep(self.config.send_delay)
        return delivered

    # --- рассылки ---------------------------------------------------------

    async def run_digests(self) -> None:
        """Раз в минуту: кому пора отправить ежедневную сводку."""
        if not self.config.digest_enabled:
            return
        now = datetime.now(MSK)
        today = now.date()

        for sub in await storage.run(self.store.active_subscribers):
            if not sub.digest_enabled:
                continue
            hour = sub.digest_hour if sub.digest_hour is not None else self.config.digest_hour
            minute = sub.digest_minute if sub.digest_minute is not None else self.config.digest_minute
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # Окно в 30 минут: перезапуск контейнера не должен съедать рассылку.
            if not (due <= now < due + timedelta(minutes=30)):
                continue
            if not await storage.run(self.store.mark_digest, sub.chat_id, today):
                continue
            await self.send_digest(sub.chat_id)
            await asyncio.sleep(self.config.send_delay)

    async def send_digest(self, chat_id: int) -> None:
        text = await self.digest_text(chat_id)
        if not text:
            return
        await self.send(chat_id, text)
        if not self.config.chart_in_digest:
            return
        png, _ = await self.chart_png()
        if png:
            await self.send_photo(chat_id, png)

    async def run_dip_alerts(self) -> None:
        """После каждого обновления курсов: проверить пороги и цели."""
        subscribers = [s for s in await storage.run(self.store.active_subscribers) if s.alerts_enabled]
        if not subscribers:
            return

        stats_by_code: dict[str, Stats] = {}
        dips: list[analytics.Dip] = []
        for code in await self.alert_codes():
            item = await self.stats(code)
            if not item:
                continue
            stats_by_code[code] = item
            if self.config.dip_alerts_enabled:
                dips.extend(
                    analytics.detect(
                        item,
                        daily_drop_pct=self.config.dip_daily_drop_pct,
                        below_ma_pct=self.config.dip_below_ma_pct,
                    )
                )

        for sub in subscribers:
            fresh = [
                dip
                for dip in dips
                if await storage.run(
                    self.store.mark_alert, sub.chat_id, dip.char_code, dip.rule, dip.ref
                )
            ]
            if fresh:
                await self.send(sub.chat_id, formatting.dip_alert(fresh, stats_by_code))
                await asyncio.sleep(self.config.send_delay)

        await self._check_targets(stats_by_code)
        await self._check_moex_intraday(subscribers)

    async def _check_targets(self, stats_by_code: dict[str, Stats]) -> None:
        for chat_id, code, level in await storage.run(self.store.targets, None):
            item = stats_by_code.get(code)
            if not item or item.value > level:
                continue
            if not await storage.run(
                self.store.mark_alert, chat_id, code, "target", f"{level}:{item.on_date}"
            ):
                continue
            await storage.run(self.store.drop_target, chat_id, code)
            await self.send(
                chat_id, formatting.target_alert(code, level, item.value, item.on_date)
            )
            await asyncio.sleep(self.config.send_delay)

    async def _check_moex_intraday(self, subscribers) -> None:
        """Курс ЦБ обновляется раз в сутки, биржа — постоянно. Резкое
        внутридневное падение юаня ловим отдельно."""
        if not self.config.moex_enabled:
            return
        quote = await self.moex_quote()
        if not quote:
            return
        change = quote.change_pct
        if change is None or change > -abs(self.config.moex_intraday_drop_pct):
            return

        ref = datetime.now(MSK).date().isoformat()
        text = (
            f"🟢 <b>Просадка на бирже</b>\n\n"
            f"{formatting.title(quote.char_code)} — {formatting.signed_pct(change)} "
            f"к вчерашнему закрытию\n"
            f"   сейчас {formatting.money(quote.last)} ₽"
        )
        for sub in subscribers:
            if await storage.run(
                self.store.mark_alert, sub.chat_id, quote.char_code, "moex_intraday", ref
            ):
                await self.send(sub.chat_id, text)
                await asyncio.sleep(self.config.send_delay)
