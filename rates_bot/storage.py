"""SQLite-хранилище: история курсов, подписчики, цели, отметки об отправке.

Все обращения синхронные, но короткие; вызываются из корутин через
asyncio.to_thread, поэтому держим одно соединение с блокировкой.
"""

import asyncio
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rates (
    char_code TEXT NOT NULL,
    on_date   TEXT NOT NULL,
    value     REAL NOT NULL,
    PRIMARY KEY (char_code, on_date)
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id        INTEGER PRIMARY KEY,
    active         INTEGER NOT NULL DEFAULT 1,
    digest_enabled INTEGER NOT NULL DEFAULT 1,
    alerts_enabled INTEGER NOT NULL DEFAULT 1,
    digest_hour    INTEGER,
    digest_minute  INTEGER,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS targets (
    chat_id    INTEGER NOT NULL,
    char_code  TEXT NOT NULL,
    level      REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, char_code)
);

-- Ключ включает ref (обычно дата курса): одно и то же событие не уйдёт дважды.
CREATE TABLE IF NOT EXISTS alerts_sent (
    chat_id   INTEGER NOT NULL,
    char_code TEXT NOT NULL,
    rule      TEXT NOT NULL,
    ref       TEXT NOT NULL,
    sent_at   TEXT NOT NULL,
    PRIMARY KEY (chat_id, char_code, rule, ref)
);

CREATE TABLE IF NOT EXISTS digests_sent (
    chat_id INTEGER NOT NULL,
    on_date TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, on_date)
);

CREATE INDEX IF NOT EXISTS idx_rates_code_date ON rates (char_code, on_date DESC);
"""


@dataclass(frozen=True)
class Subscriber:
    chat_id: int
    active: bool
    digest_enabled: bool
    alerts_enabled: bool
    digest_hour: int | None
    digest_minute: int | None


class Storage:
    def __init__(self, path: str) -> None:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- курсы -----------------------------------------------------------

    def save_rates(self, char_code: str, rows: list[tuple[date, float]]) -> int:
        if not rows:
            return 0
        payload = [(char_code.upper(), day.isoformat(), float(value)) for day, value in rows]
        with self._lock:
            cur = self._conn.executemany(
                "INSERT INTO rates (char_code, on_date, value) VALUES (?, ?, ?) "
                "ON CONFLICT (char_code, on_date) DO UPDATE SET value = excluded.value",
                payload,
            )
            self._conn.commit()
        return cur.rowcount

    def series(self, char_code: str, limit: int | None = None) -> list[tuple[date, float]]:
        """История по возрастанию даты; limit отсчитывается от свежих."""
        sql = "SELECT on_date, value FROM rates WHERE char_code = ? ORDER BY on_date DESC"
        params: list = [char_code.upper()]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [(date.fromisoformat(r["on_date"]), r["value"]) for r in reversed(rows)]

    def latest(self, char_code: str) -> tuple[date, float] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT on_date, value FROM rates WHERE char_code = ? ORDER BY on_date DESC LIMIT 1",
                (char_code.upper(),),
            ).fetchone()
        return (date.fromisoformat(row["on_date"]), row["value"]) if row else None

    def count(self, char_code: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM rates WHERE char_code = ?", (char_code.upper(),)
            ).fetchone()
        return int(row["n"])

    # --- подписчики ------------------------------------------------------

    def upsert_subscriber(self, chat_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO subscribers (chat_id, active, created_at) VALUES (?, 1, ?) "
                "ON CONFLICT (chat_id) DO UPDATE SET active = 1",
                (chat_id, datetime.utcnow().isoformat(timespec="seconds")),
            )
            self._conn.commit()

    def set_flag(self, chat_id: int, field: str, value: bool) -> None:
        if field not in ("active", "digest_enabled", "alerts_enabled"):
            raise ValueError(field)
        with self._lock:
            self._conn.execute(
                f"UPDATE subscribers SET {field} = ? WHERE chat_id = ?", (int(value), chat_id)
            )
            self._conn.commit()

    def set_digest_time(self, chat_id: int, hour: int, minute: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE subscribers SET digest_hour = ?, digest_minute = ? WHERE chat_id = ?",
                (hour, minute, chat_id),
            )
            self._conn.commit()

    def _row_to_subscriber(self, row: sqlite3.Row) -> Subscriber:
        return Subscriber(
            chat_id=row["chat_id"],
            active=bool(row["active"]),
            digest_enabled=bool(row["digest_enabled"]),
            alerts_enabled=bool(row["alerts_enabled"]),
            digest_hour=row["digest_hour"],
            digest_minute=row["digest_minute"],
        )

    def subscriber(self, chat_id: int) -> Subscriber | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        return self._row_to_subscriber(row) if row else None

    def active_subscribers(self) -> list[Subscriber]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM subscribers WHERE active = 1 ORDER BY chat_id"
            ).fetchall()
        return [self._row_to_subscriber(r) for r in rows]

    # --- цели ------------------------------------------------------------

    def set_target(self, chat_id: int, char_code: str, level: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO targets (chat_id, char_code, level, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (chat_id, char_code) DO UPDATE SET level = excluded.level",
                (
                    chat_id,
                    char_code.upper(),
                    float(level),
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )
            self._conn.commit()

    def drop_target(self, chat_id: int, char_code: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM targets WHERE chat_id = ? AND char_code = ?",
                (chat_id, char_code.upper()),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def targets(self, chat_id: int | None = None) -> list[tuple[int, str, float]]:
        sql = "SELECT chat_id, char_code, level FROM targets"
        params: list = []
        if chat_id is not None:
            sql += " WHERE chat_id = ?"
            params.append(chat_id)
        sql += " ORDER BY char_code"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [(r["chat_id"], r["char_code"], r["level"]) for r in rows]

    # --- дедупликация отправок -------------------------------------------

    def mark_alert(self, chat_id: int, char_code: str, rule: str, ref: str) -> bool:
        """True, если отметка поставлена впервые (значит, можно слать)."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO alerts_sent (chat_id, char_code, rule, ref, sent_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    chat_id,
                    char_code.upper(),
                    rule,
                    ref,
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def mark_digest(self, chat_id: int, on_date: date) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO digests_sent (chat_id, on_date, sent_at) VALUES (?, ?, ?)",
                (chat_id, on_date.isoformat(), datetime.utcnow().isoformat(timespec="seconds")),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def purge_old_marks(self, keep_days: int = 120) -> None:
        cutoff = datetime.utcnow().date().toordinal() - keep_days
        cutoff_iso = date.fromordinal(cutoff).isoformat()
        with self._lock:
            self._conn.execute("DELETE FROM alerts_sent WHERE sent_at < ?", (cutoff_iso,))
            self._conn.execute("DELETE FROM digests_sent WHERE on_date < ?", (cutoff_iso,))
            self._conn.commit()


async def run(func, *args):
    """Выполнить синхронный вызов хранилища, не блокируя цикл событий."""
    return await asyncio.to_thread(func, *args)
