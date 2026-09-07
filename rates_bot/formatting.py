"""Сборка текстов сообщений. Разметка — HTML (aiogram ParseMode.HTML)."""

from datetime import date
from html import escape

from .analytics import MONTH_NAMES, Dip, MonthStat, Stats
from .moex import MoexQuote

FLAGS = {
    "CNY": "🇨🇳", "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "KZT": "🇰🇿", "TRY": "🇹🇷", "AED": "🇦🇪", "HKD": "🇭🇰", "CHF": "🇨🇭",
    "BYN": "🇧🇾", "KRW": "🇰🇷", "INR": "🇮🇳", "AMD": "🇦🇲", "GEL": "🇬🇪",
}

TITLES = {
    "CNY": "Юань", "USD": "Доллар", "EUR": "Евро", "GBP": "Фунт",
    "JPY": "Иена", "KZT": "Тенге", "TRY": "Лира", "AED": "Дирхам",
}


def money(value: float, digits: int = 4) -> str:
    text = f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")
    return text


def signed_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ("−" if value < 0 else "")
    return f"{sign}{abs(value):.{digits}f}%".replace(".", ",")


def arrow(value: float | None) -> str:
    if value is None:
        return "▫️"
    if value <= -0.15:
        return "🟢"   # валюта дешевеет — покупать выгоднее
    if value >= 0.15:
        return "🔴"
    return "⚪️"


def title(char_code: str) -> str:
    flag = FLAGS.get(char_code, "💱")
    name = TITLES.get(char_code, char_code)
    return f"{flag} {escape(name)} <b>{escape(char_code)}</b>"


def range_bar(position: float | None, width: int = 10) -> str:
    """Где курс внутри 90-дневного коридора: слева дёшево, справа дорого."""
    if position is None:
        return ""
    index = max(0, min(width - 1, int(position / 100 * width)))
    return "".join("●" if i == index else "·" for i in range(width))


def verdict(position: float | None) -> str:
    if position is None:
        return ""
    if position <= 15:
        return "дёшево — низ коридора"
    if position <= 35:
        return "ниже среднего"
    if position <= 65:
        return "середина коридора"
    if position <= 85:
        return "выше среднего"
    return "дорого — верх коридора"


def stats_block(stats: Stats) -> str:
    lines = [f"{title(stats.char_code)}  <b>{money(stats.value)} ₽</b>"]
    lines.append(
        f"   {arrow(stats.change_1d_pct)} день {signed_pct(stats.change_1d_pct)}"
        f" · неделя {signed_pct(stats.change_7d_pct)}"
        f" · месяц {signed_pct(stats.change_30d_pct)}"
    )
    if stats.low_90 is not None and stats.high_90 is not None:
        bar = range_bar(stats.position_90)
        lines.append(
            f"   90 дней: {money(stats.low_90, 2)} … {money(stats.high_90, 2)} ₽"
        )
        lines.append(f"   <code>{bar}</code> {escape(verdict(stats.position_90))}")
    return "\n".join(lines)


def moex_block(quote: MoexQuote) -> str:
    change = quote.change_pct
    stamp = f" (обновлено {escape(quote.updated_at)})" if quote.updated_at else ""
    return (
        f"📈 Биржа MOEX, {escape(quote.char_code)}/RUB: <b>{money(quote.last)} ₽</b> "
        f"{signed_pct(change)}{stamp}"
    )


def digest(
    on_date: date,
    blocks: list[Stats],
    moex: MoexQuote | None,
    targets: list[tuple[str, float]],
) -> str:
    head = f"📅 <b>Курсы ЦБ на {on_date.strftime('%d.%m.%Y')}</b>"
    parts = [head, ""]
    parts.append("\n\n".join(stats_block(s) for s in blocks))
    if moex:
        parts.extend(["", moex_block(moex)])
    if targets:
        rows = ", ".join(f"{escape(code)} ≤ {money(level, 2)}" for code, level in targets)
        parts.extend(["", f"🎯 Ваши цели: {rows}"])
    parts.extend(["", "<i>Зелёный — валюта дешевеет, покупать выгоднее.</i>"])
    return "\n".join(parts)


def dip_alert(dips: list[Dip], stats_by_code: dict[str, Stats]) -> str:
    parts = ["🟢 <b>Просадка</b>", ""]
    for dip in dips:
        parts.append(f"{title(dip.char_code)} — {escape(dip.headline)}")
        parts.append(f"   {escape(dip.detail)}")
        stats = stats_by_code.get(dip.char_code)
        if stats and stats.low_90 is not None and stats.high_90 is not None:
            parts.append(
                f"   90 дней: {money(stats.low_90, 2)} … {money(stats.high_90, 2)} ₽"
                f" · {escape(verdict(stats.position_90))}"
            )
        parts.append("")
    return "\n".join(parts).rstrip()


def target_alert(char_code: str, level: float, value: float, on_date: date) -> str:
    return (
        f"🎯 <b>Цель достигнута</b>\n\n"
        f"{title(char_code)} — <b>{money(value)} ₽</b> на {on_date.strftime('%d.%m.%Y')}\n"
        f"Вы ждали {money(level, 2)} ₽ или ниже.\n\n"
        f"<i>Цель снята. Чтобы поставить новую: /target {escape(char_code)} &lt;курс&gt;</i>"
    )


def seasonality(char_code: str, months: list[MonthStat], span: str) -> str:
    if not months:
        return "Пока мало истории для расчёта сезонности — попробуйте позже."

    parts = [
        f"📊 <b>Сезонность {escape(char_code)}/RUB</b> ({escape(span)})",
        "",
        "Изменение курса за календарный месяц, по данным ЦБ.",
        "Минус = валюта дешевела к рублю (хорошо для покупки).",
        "",
        "<pre>месяц      средн.  медиана  вниз  лет",
    ]
    for month in months:
        name = MONTH_NAMES[month.month - 1]
        parts.append(
            f"{name:<10}{month.mean_pct:+6.2f}%  {month.median_pct:+6.2f}%"
            f"  {month.share_down:3.0f}%  {month.samples:3d}"
        )
    parts.append("</pre>")

    ranked = sorted(months, key=lambda m: m.mean_pct)
    best = ", ".join(f"{MONTH_NAMES[m.month - 1]} ({m.mean_pct:+.2f}%)" for m in ranked[:3])
    worst = ", ".join(f"{MONTH_NAMES[m.month - 1]} ({m.mean_pct:+.2f}%)" for m in ranked[-3:][::-1])
    parts.extend(
        [
            f"🟢 Дешевле всего исторически: {escape(best)}",
            f"🔴 Дороже всего: {escape(worst)}",
            "",
            "<i>Это статистика прошлого, а не прогноз: структура рынка "
            "после 2022 года сильно изменилась.</i>",
        ]
    )
    return "\n".join(parts)


HELP = """<b>Что умеет бот</b>

/rates — курсы прямо сейчас
/dip — есть ли просадка на сегодня
/history CNY 90 — минимум, максимум и динамика за N дней
/seasonality CNY — по каким месяцам валюта исторически дешевела
/target CNY 10.9 — уведомить, когда курс упадёт до значения
/targets — список целей, /untarget CNY — снять
/settings — время рассылки и переключатели
/digest_time 09:30 — своё время ежедневной сводки
/mute, /unmute — выключить/включить уведомления о просадках
/stop — отписаться, /start — подписаться снова"""
