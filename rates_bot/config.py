import os
from dataclasses import dataclass, field
from datetime import timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

# Фиксированное смещение, а не ZoneInfo — в контейнере может не быть tzdata.
MSK = timezone(timedelta(hours=3), "MSK")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "да")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").replace(",", ".") or default)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raw = default
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _time(name: str, default: str) -> tuple[int, int]:
    raw = (os.getenv(name) or default).strip()
    try:
        hour, _, minute = raw.partition(":")
        return max(0, min(23, int(hour))), max(0, min(59, int(minute or 0)))
    except ValueError:
        hour, minute = default.split(":")
        return int(hour), int(minute)


@dataclass(frozen=True)
class Config:
    token: str
    admin_chat_ids: list[int]
    currencies: list[str]
    primary_currency: str

    digest_enabled: bool
    digest_hour: int
    digest_minute: int

    dip_alerts_enabled: bool
    dip_daily_drop_pct: float
    dip_low_window_days: int
    dip_below_ma_pct: float
    dip_ma_window_days: int

    moex_enabled: bool
    moex_intraday_drop_pct: float

    dolgov_enabled: bool
    dolgov_url: str
    dolgov_catalog_url: str
    dolgov_regex: str | None
    dolgov_min: float
    dolgov_max: float

    chart_in_digest: bool
    chart_days: int

    poll_interval: int
    backfill_years: int
    db_path: str
    log_level: str

    send_delay: float = field(default=0.1)

    @classmethod
    def load(cls) -> "Config":
        token = (os.getenv("RATES_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise RuntimeError(
                "Не задан RATES_BOT_TOKEN. Возьмите токен у @BotFather и положите в .env"
            )

        admins: list[int] = []
        for chunk in _csv("ADMIN_CHAT_IDS", ""):
            try:
                admins.append(int(chunk))
            except ValueError:
                continue

        currencies = _csv("CURRENCIES", "CNY,USD,EUR")
        primary = (os.getenv("PRIMARY_CURRENCY") or "").strip().upper()
        if primary not in currencies:
            primary = currencies[0]

        digest_hour, digest_minute = _time("DIGEST_TIME", "10:00")

        return cls(
            token=token,
            admin_chat_ids=admins,
            currencies=currencies,
            primary_currency=primary,
            digest_enabled=_bool("DIGEST_ENABLED", True),
            digest_hour=digest_hour,
            digest_minute=digest_minute,
            dip_alerts_enabled=_bool("DIP_ALERTS_ENABLED", True),
            dip_daily_drop_pct=_float("DIP_DAILY_DROP_PCT", 0.8),
            dip_low_window_days=_int("DIP_LOW_WINDOW_DAYS", 30),
            dip_below_ma_pct=_float("DIP_BELOW_MA_PCT", 2.0),
            dip_ma_window_days=_int("DIP_MA_WINDOW_DAYS", 30),
            moex_enabled=_bool("MOEX_ENABLED", True),
            moex_intraday_drop_pct=_float("MOEX_INTRADAY_DROP_PCT", 1.0),
            dolgov_enabled=_bool("DOLGOV_ENABLED", True),
            dolgov_url=(
                os.getenv("DOLGOV_URL")
                or "https://catalog.dolgov-auto.ru/china-used/mercedes-benz/c-class/2_12021338/"
            ).strip(),
            dolgov_catalog_url=(
                os.getenv("DOLGOV_CATALOG_URL")
                or "https://catalog.dolgov-auto.ru/china-used/"
            ).strip(),
            dolgov_regex=(os.getenv("DOLGOV_REGEX") or "").strip() or None,
            dolgov_min=_float("DOLGOV_MIN", 5.0),
            dolgov_max=_float("DOLGOV_MAX", 30.0),
            chart_in_digest=_bool("CHART_IN_DIGEST", True),
            chart_days=max(14, min(1825, _int("CHART_DAYS", 90))),
            poll_interval=max(60, _int("POLL_INTERVAL", 900)),
            backfill_years=max(1, min(25, _int("BACKFILL_YEARS", 8))),
            db_path=os.getenv("DB_PATH", "/data/rates.db"),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        )
