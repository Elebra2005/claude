"""Загрузка config.yaml и секретов из .env."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) and value.strip() else default


def load_config(path: str | None = None) -> dict:
    path = path or env("WALLET_WATCH_CONFIG", "config.yaml")
    with Path(path).open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
