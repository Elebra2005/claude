"""Отрисовка PNG-графика для Telegram.

Верхняя панель — курс ЦБ и курс Долгова одной шкалой (две шкалы на одном
графике врут о масштабе, поэтому производная величина живёт отдельно).
Нижняя панель — наценка Долгова к ЦБ в процентах.
"""

import io
import logging
from datetime import date

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

log = logging.getLogger(__name__)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e3e2df"
CBR_COLOR = "#2a78d6"      # категориальный слот 1
DOLGOV_COLOR = "#eb6834"   # категориальный слот 2

Series = list[tuple[date, float]]


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
        ax.spines[side].set_linewidth(1.0)
    ax.tick_params(colors=INK_SOFT, labelsize=9, length=0)


def _label_last(ax, days, values, color: str, suffix: str = " ₽") -> None:
    """Подпись последнего значения прямо у линии — идентичность не только цветом."""
    if not days:
        return
    text = f"{values[-1]:.2f}{suffix}".replace(".", ",")
    ax.annotate(
        text,
        xy=(days[-1], values[-1]),
        xytext=(6, 0),
        textcoords="offset points",
        va="center",
        ha="left",
        fontsize=9.5,
        fontweight="bold",
        color=color,
    )


def render(
    cbr: Series,
    dolgov: Series,
    *,
    days: int,
    title: str = "Юань к рублю",
) -> bytes | None:
    """PNG или None, если рисовать нечего."""
    if not cbr and not dolgov:
        return None

    has_spread = len(dolgov) >= 2 and len(cbr) >= 2
    if has_spread:
        figure, (ax_rate, ax_spread) = plt.subplots(
            2, 1, figsize=(9.0, 6.4), dpi=130, sharex=True,
            gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12},
        )
    else:
        figure, ax_rate = plt.subplots(figsize=(9.0, 5.0), dpi=130)
        ax_spread = None

    figure.patch.set_facecolor(SURFACE)

    if cbr:
        xs = [d for d, _ in cbr]
        ys = [v for _, v in cbr]
        ax_rate.plot(xs, ys, color=CBR_COLOR, linewidth=2.0, label="Курс ЦБ", zorder=3)
        _label_last(ax_rate, xs, ys, CBR_COLOR)

    if dolgov:
        xs = [d for d, _ in dolgov]
        ys = [v for _, v in dolgov]
        # Точек поначалу мало — показываем маркеры, чтобы линия не выглядела пустой.
        marker = "o" if len(xs) < 25 else None
        ax_rate.plot(
            xs, ys, color=DOLGOV_COLOR, linewidth=2.0, label="Курс Долгова",
            marker=marker, markersize=4.5, zorder=4,
        )
        _label_last(ax_rate, xs, ys, DOLGOV_COLOR)

    ax_rate.set_title(
        f"{title} · {days} дней", color=INK, fontsize=13, fontweight="bold",
        loc="left", pad=28,
    )
    ax_rate.set_ylabel("рублей за юань", color=INK_SOFT, fontsize=9.5)
    _style(ax_rate)

    if cbr and dolgov:
        # Легенда в шапке, а не поверх поля: линия никогда её не перекроет.
        legend = ax_rate.legend(
            loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2,
            frameon=False, fontsize=9.5, labelcolor=INK_SOFT,
            handlelength=1.6, columnspacing=1.6, borderaxespad=0.2,
        )
        legend.set_zorder(5)

    if has_spread and ax_spread is not None:
        by_date = dict(cbr)
        xs, ys = [], []
        for day, value in dolgov:
            base = by_date.get(day)
            if base:
                xs.append(day)
                ys.append((value - base) / base * 100.0)
        if len(xs) >= 2:
            ax_spread.plot(xs, ys, color=DOLGOV_COLOR, linewidth=2.0, zorder=3)
            ax_spread.fill_between(xs, ys, color=DOLGOV_COLOR, alpha=0.12, zorder=2)
            _label_last(ax_spread, xs, ys, DOLGOV_COLOR, suffix="%")
            ax_spread.axhline(0, color=GRID, linewidth=1.0, zorder=1)
            ax_spread.set_ylabel("наценка, %", color=INK_SOFT, fontsize=9.5)
            _style(ax_spread)
        else:
            ax_spread.remove()
            ax_spread = None

    bottom = ax_spread if ax_spread is not None else ax_rate
    bottom.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    bottom.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))

    # Место справа под подписи последних значений.
    for axis in (ax_rate, ax_spread):
        if axis is not None:
            left, right = axis.get_xlim()
            axis.set_xlim(left, right + (right - left) * 0.08)

    figure.autofmt_xdate(rotation=0, ha="center")

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(figure)
    return buffer.getvalue()
