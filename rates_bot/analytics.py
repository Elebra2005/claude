"""Статистика по ряду курсов: изменения, положение в диапазоне, просадки,
сезонность по календарным месяцам."""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

Series = list[tuple[date, float]]


@dataclass(frozen=True)
class Stats:
    char_code: str
    on_date: date
    value: float
    prev_value: float | None
    change_1d_pct: float | None
    change_7d_pct: float | None
    change_30d_pct: float | None
    low_90: float | None
    high_90: float | None
    position_90: float | None   # 0 — у минимума диапазона, 100 — у максимума
    ma_value: float | None
    ma_window: int
    below_ma_pct: float | None  # насколько курс ниже средней, %
    low_window_days: int
    is_window_low: bool


def _value_on_or_before(series: Series, target: date) -> float | None:
    found = None
    for day, value in series:
        if day <= target:
            found = value
        else:
            break
    return found


def _pct(new: float, old: float | None) -> float | None:
    if not old:
        return None
    return (new - old) / old * 100.0


def compute(char_code: str, series: Series, *, ma_window: int, low_window: int) -> Stats | None:
    """series — по возрастанию даты."""
    if not series:
        return None

    on_date, value = series[-1]
    prev_value = series[-2][1] if len(series) > 1 else None

    window_90 = [v for d, v in series if d >= on_date - timedelta(days=90)]
    low_90 = min(window_90) if window_90 else None
    high_90 = max(window_90) if window_90 else None
    position = None
    if low_90 is not None and high_90 is not None and high_90 > low_90:
        position = (value - low_90) / (high_90 - low_90) * 100.0
    elif low_90 is not None:
        position = 50.0

    ma_slice = [v for d, v in series if d >= on_date - timedelta(days=ma_window)]
    ma_value = statistics.fmean(ma_slice) if len(ma_slice) >= 3 else None
    below_ma = None
    if ma_value:
        below_ma = (ma_value - value) / ma_value * 100.0

    low_slice = [v for d, v in series if d >= on_date - timedelta(days=low_window)]
    # Минимум окна с допуском на копейки округления.
    is_low = bool(low_slice) and len(low_slice) >= 5 and value <= min(low_slice) + 1e-9

    return Stats(
        char_code=char_code,
        on_date=on_date,
        value=value,
        prev_value=prev_value,
        change_1d_pct=_pct(value, prev_value),
        change_7d_pct=_pct(value, _value_on_or_before(series, on_date - timedelta(days=7))),
        change_30d_pct=_pct(value, _value_on_or_before(series, on_date - timedelta(days=30))),
        low_90=low_90,
        high_90=high_90,
        position_90=position,
        ma_value=ma_value,
        ma_window=ma_window,
        below_ma_pct=below_ma,
        low_window_days=low_window,
        is_window_low=is_low,
    )


@dataclass(frozen=True)
class Dip:
    char_code: str
    rule: str        # daily_drop | window_low | below_ma | target
    ref: str         # ключ дедупликации, обычно дата курса
    headline: str
    detail: str


def detect(
    stats: Stats,
    *,
    daily_drop_pct: float,
    below_ma_pct: float,
) -> list[Dip]:
    """Просадки по данным ЦБ. Цели пользователя проверяются отдельно."""
    dips: list[Dip] = []
    ref = stats.on_date.isoformat()

    if stats.change_1d_pct is not None and stats.change_1d_pct <= -abs(daily_drop_pct):
        dips.append(
            Dip(
                char_code=stats.char_code,
                rule="daily_drop",
                ref=ref,
                headline="упал на {:.2f}% за день".format(abs(stats.change_1d_pct)).replace(".", ","),
                detail=f"{stats.prev_value:.4f} → {stats.value:.4f} ₽".replace(".", ","),
            )
        )

    if stats.is_window_low:
        dips.append(
            Dip(
                char_code=stats.char_code,
                rule="window_low",
                ref=ref,
                headline=f"минимум за {stats.low_window_days} дней",
                detail=f"курс {stats.value:.4f} ₽".replace(".", ","),
            )
        )

    if stats.below_ma_pct is not None and stats.below_ma_pct >= abs(below_ma_pct):
        dips.append(
            Dip(
                char_code=stats.char_code,
                rule="below_ma",
                ref=ref,
                headline="ниже средней за {} дней на {:.2f}%".format(
                    stats.ma_window, stats.below_ma_pct
                ).replace(".", ","),
                detail=f"средняя {stats.ma_value:.4f} ₽, сейчас {stats.value:.4f} ₽".replace(".", ","),
            )
        )

    return dips


@dataclass(frozen=True)
class MonthStat:
    month: int
    samples: int
    mean_pct: float
    median_pct: float
    share_down: float   # доля лет, когда валюта дешевела к рублю, %
    best_pct: float
    worst_pct: float


MONTH_NAMES = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)


def monthly_seasonality(series: Series, *, since_year: int | None = None) -> list[MonthStat]:
    """Изменение курса за календарный месяц: последний рабочий день месяца
    к последнему рабочему дню предыдущего. Отрицательное значение = валюта
    подешевела к рублю (для покупателя юаня это хорошо)."""
    if not series:
        return []

    # Последнее значение каждого месяца.
    month_close: dict[tuple[int, int], float] = {}
    for day, value in series:
        month_close[(day.year, day.month)] = value

    keys = sorted(month_close)
    buckets: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for prev_key, key in zip(keys, keys[1:]):
        # Пропускаем разрывы в данных.
        expected = (prev_key[0] + 1, 1) if prev_key[1] == 12 else (prev_key[0], prev_key[1] + 1)
        if key != expected:
            continue
        if since_year and key[0] < since_year:
            continue
        prev_value = month_close[prev_key]
        if not prev_value:
            continue
        buckets[key[1]].append((month_close[key] - prev_value) / prev_value * 100.0)

    result: list[MonthStat] = []
    for month in range(1, 13):
        changes = buckets[month]
        if not changes:
            continue
        result.append(
            MonthStat(
                month=month,
                samples=len(changes),
                mean_pct=statistics.fmean(changes),
                median_pct=statistics.median(changes),
                share_down=sum(1 for c in changes if c < 0) / len(changes) * 100.0,
                best_pct=min(changes),
                worst_pct=max(changes),
            )
        )
    return result
