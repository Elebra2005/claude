"""Команды бота."""

import logging
from datetime import date, timedelta
from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from . import analytics, formatting, storage
from .service import RatesService

log = logging.getLogger(__name__)
router = Router()


async def _reply(message: Message, text: str) -> None:
    await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def _known(service: RatesService, code: str) -> str | None:
    code = code.strip().upper()
    return code if code in service.config.currencies else None


def _parse_amount(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None
    return value if value > 0 else None


@router.message(CommandStart())
async def cmd_start(message: Message, service: RatesService) -> None:
    await storage.run(service.store.upsert_subscriber, message.chat.id)
    config = service.config
    codes = ", ".join(config.currencies)
    await _reply(
        message,
        f"Подписка оформлена.\n\n"
        f"Каждый день в {config.digest_hour:02d}:{config.digest_minute:02d} по Москве "
        f"буду присылать курсы: <b>{escape(codes)}</b>.\n"
        f"Отдельно напишу, когда поймаю просадку: падение за день от "
        f"{config.dip_daily_drop_pct:.1f}%, минимум за {config.dip_low_window_days} дней "
        f"или курс ниже средней на {config.dip_below_ma_pct:.1f}%.\n\n"
        f"{formatting.HELP}",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await _reply(message, formatting.HELP)


@router.message(Command("rates"))
async def cmd_rates(message: Message, service: RatesService) -> None:
    text = await service.digest_text(message.chat.id)
    await _reply(message, text or "Курсы ещё не загружены, попробуйте через минуту.")


@router.message(Command("dip"))
async def cmd_dip(message: Message, service: RatesService) -> None:
    config = service.config
    stats_by_code = {}
    dips = []
    for code in config.currencies:
        item = await service.stats(code)
        if not item:
            continue
        stats_by_code[code] = item
        dips.extend(
            analytics.detect(
                item,
                daily_drop_pct=config.dip_daily_drop_pct,
                below_ma_pct=config.dip_below_ma_pct,
            )
        )
    if dips:
        await _reply(message, formatting.dip_alert(dips, stats_by_code))
        return

    primary = stats_by_code.get(config.primary_currency)
    tail = ""
    if primary:
        tail = (
            f"\n\n{formatting.title(primary.char_code)} — {formatting.money(primary.value)} ₽, "
            f"{escape(formatting.verdict(primary.position_90))}."
        )
    await _reply(message, f"Просадок по текущим порогам нет.{tail}")


@router.message(Command("history"))
async def cmd_history(message: Message, service: RatesService, command) -> None:
    args = (command.args or "").split()
    code = _known(service, args[0]) if args else service.config.primary_currency
    if code is None:
        await _reply(
            message,
            f"Не отслеживаю {escape(args[0].upper())}. "
            f"Доступно: {escape(', '.join(service.config.currencies))}",
        )
        return

    days = 90
    if len(args) > 1:
        try:
            days = max(7, min(3650, int(args[1])))
        except ValueError:
            pass

    series = await storage.run(service.store.series, code, days * 2)
    cutoff = date.today() - timedelta(days=days)
    window = [(d, v) for d, v in series if d >= cutoff]
    if len(window) < 2:
        await _reply(message, "Мало данных за этот период.")
        return

    values = [v for _, v in window]
    low, high = min(values), max(values)
    low_date = next(d for d, v in window if v == low)
    high_date = next(d for d, v in window if v == high)
    first, last = values[0], values[-1]
    change = (last - first) / first * 100.0

    await _reply(
        message,
        f"{formatting.title(code)} за {days} дней\n\n"
        f"начало   {formatting.money(first)} ₽ ({window[0][0].strftime('%d.%m.%Y')})\n"
        f"сейчас   <b>{formatting.money(last)} ₽</b> ({window[-1][0].strftime('%d.%m.%Y')})\n"
        f"итог     {formatting.signed_pct(change)}\n\n"
        f"минимум  {formatting.money(low)} ₽ — {low_date.strftime('%d.%m.%Y')}\n"
        f"максимум {formatting.money(high)} ₽ — {high_date.strftime('%d.%m.%Y')}\n"
        f"средний  {formatting.money(sum(values) / len(values))} ₽\n"
        f"наблюдений: {len(window)}",
    )


@router.message(Command("seasonality"))
async def cmd_seasonality(message: Message, service: RatesService, command) -> None:
    args = (command.args or "").split()
    code = _known(service, args[0]) if args else service.config.primary_currency
    if code is None:
        code = service.config.primary_currency

    since_year = None
    if len(args) > 1:
        try:
            since_year = int(args[1])
        except ValueError:
            since_year = None

    series = await storage.run(service.store.series, code, None)
    months = analytics.monthly_seasonality(series, since_year=since_year)
    if not months:
        await _reply(message, "История ещё загружается, попробуйте через пару минут.")
        return

    span = f"{series[0][0].year}–{series[-1][0].year}"
    if since_year:
        span = f"с {since_year} года"
    await _reply(message, formatting.seasonality(code, months, span))


@router.message(Command("target"))
async def cmd_target(message: Message, service: RatesService, command) -> None:
    args = (command.args or "").split()
    if len(args) < 2:
        await _reply(
            message,
            "Формат: <code>/target CNY 10.9</code> — напишу, когда курс "
            "опустится до этого значения или ниже.",
        )
        return

    code = _known(service, args[0])
    if code is None:
        await _reply(
            message,
            f"Не отслеживаю {escape(args[0].upper())}. "
            f"Доступно: {escape(', '.join(service.config.currencies))}",
        )
        return

    level = _parse_amount(args[1])
    if level is None:
        await _reply(message, "Курс должен быть положительным числом, например 10.9")
        return

    await storage.run(service.store.upsert_subscriber, message.chat.id)
    await storage.run(service.store.set_target, message.chat.id, code, level)

    stats = await service.stats(code)
    now = ""
    if stats:
        distance = (stats.value - level) / stats.value * 100.0
        gap = f"{abs(distance):.2f}".replace(".", ",")
        side = "выше" if distance > 0 else "ниже"
        now = f"\nСейчас {formatting.money(stats.value)} ₽ — это на {gap}% {side} цели."
    await _reply(message, f"🎯 Цель: {escape(code)} ≤ {formatting.money(level, 2)} ₽{now}")


@router.message(Command("targets"))
async def cmd_targets(message: Message, service: RatesService) -> None:
    rows = await storage.run(service.store.targets, message.chat.id)
    if not rows:
        await _reply(message, "Целей нет. Поставить: <code>/target CNY 10.9</code>")
        return
    lines = [f"• {escape(code)} ≤ {formatting.money(level, 2)} ₽" for _, code, level in rows]
    await _reply(message, "🎯 <b>Ваши цели</b>\n\n" + "\n".join(lines) + "\n\nСнять: /untarget CNY")


@router.message(Command("untarget"))
async def cmd_untarget(message: Message, service: RatesService, command) -> None:
    args = (command.args or "").split()
    if not args:
        await _reply(message, "Формат: <code>/untarget CNY</code>")
        return
    removed = await storage.run(service.store.drop_target, message.chat.id, args[0].upper())
    await _reply(message, "Цель снята." if removed else "Такой цели не было.")


@router.message(Command("digest_time"))
async def cmd_digest_time(message: Message, service: RatesService, command) -> None:
    raw = (command.args or "").strip()
    try:
        hour_raw, _, minute_raw = raw.partition(":")
        hour, minute = int(hour_raw), int(minute_raw or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        await _reply(message, "Формат: <code>/digest_time 09:30</code> (время московское)")
        return

    await storage.run(service.store.upsert_subscriber, message.chat.id)
    await storage.run(service.store.set_digest_time, message.chat.id, hour, minute)
    await _reply(message, f"Сводка будет приходить в {hour:02d}:{minute:02d} по Москве.")


@router.message(Command("mute"))
async def cmd_mute(message: Message, service: RatesService) -> None:
    await storage.run(service.store.set_flag, message.chat.id, "alerts_enabled", False)
    await _reply(message, "Уведомления о просадках выключены. Вернуть: /unmute")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, service: RatesService) -> None:
    await storage.run(service.store.upsert_subscriber, message.chat.id)
    await storage.run(service.store.set_flag, message.chat.id, "alerts_enabled", True)
    await _reply(message, "Уведомления о просадках включены.")


@router.message(Command("settings"))
async def cmd_settings(message: Message, service: RatesService) -> None:
    config = service.config
    sub = await storage.run(service.store.subscriber, message.chat.id)
    hour = sub.digest_hour if sub and sub.digest_hour is not None else config.digest_hour
    minute = sub.digest_minute if sub and sub.digest_minute is not None else config.digest_minute
    await _reply(
        message,
        "⚙️ <b>Настройки</b>\n\n"
        f"валюты: {escape(', '.join(config.currencies))}\n"
        f"сводка: {'вкл' if (not sub or sub.digest_enabled) else 'выкл'}, "
        f"{hour:02d}:{minute:02d} МСК\n"
        f"просадки: {'вкл' if (not sub or sub.alerts_enabled) else 'выкл'}\n\n"
        "<b>Пороги просадки</b>\n"
        f"за день: −{config.dip_daily_drop_pct:.1f}%\n"
        f"минимум за: {config.dip_low_window_days} дней\n"
        f"ниже средней ({config.dip_ma_window_days} дн.): {config.dip_below_ma_pct:.1f}%\n"
        f"биржа MOEX: {'вкл' if config.moex_enabled else 'выкл'}"
        + (f", внутри дня −{config.moex_intraday_drop_pct:.1f}%" if config.moex_enabled else "")
        + f"\nопрос ЦБ: раз в {config.poll_interval // 60} мин",
    )


@router.message(Command("stop"))
async def cmd_stop(message: Message, service: RatesService) -> None:
    await storage.run(service.store.set_flag, message.chat.id, "active", False)
    await _reply(message, "Отписал. Вернуться — /start")


@router.message(F.text & ~F.text.startswith("/"))
async def fallback(message: Message) -> None:
    await _reply(message, formatting.HELP)
