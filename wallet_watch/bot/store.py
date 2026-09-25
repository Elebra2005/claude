"""Минимальное хранилище состояния на SQLite: курсоры (строки) и снапшоты (множества).

Нужно, чтобы между перезапусками помнить прошлые балансы (иначе после
рестарта не с чем сравнивать) и уже просканированные блоки (иначе полный
скан истории токенов заново при каждом старте).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("CREATE TABLE IF NOT EXISTS cursors (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._db.commit()

    def get_cursor(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM cursors WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_cursor(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO cursors (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._db.commit()

    def get_snapshot(self, key: str) -> set[str] | None:
        row = self._db.execute("SELECT value FROM snapshots WHERE key = ?", (key,)).fetchone()
        return set(json.loads(row[0])) if row else None

    def save_snapshot(self, key: str, items: set[str]) -> None:
        self._db.execute(
            "INSERT INTO snapshots (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(sorted(items))),
        )
        self._db.commit()
