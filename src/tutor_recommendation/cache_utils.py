from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def configured_max_age_days(env_name: str, default: int) -> int:
    value = os.environ.get(env_name, "").strip()
    if not value:
        return default
    try:
        return max(int(value), 0)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer number of days") from exc


def cache_is_fresh(path: Path, max_age_days: int) -> bool:
    if not path.is_file():
        return False
    if max_age_days == 0:
        return False
    age_seconds = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    return age_seconds <= max_age_days * 86400


def read_cached_text(path: Path, max_age_days: int) -> str | None:
    if not cache_is_fresh(path, max_age_days):
        return None
    return path.read_text(encoding="utf-8", errors="replace")
