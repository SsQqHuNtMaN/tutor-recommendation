from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def private_file(
    relative_name: str,
    *,
    env_name: str | None = None,
    legacy_relative_name: str | None = None,
) -> Path:
    if env_name and os.environ.get(env_name):
        configured = Path(os.environ[env_name]).expanduser()
        return configured if configured.is_absolute() else (PROJECT_ROOT / configured).resolve()
    preferred = PROJECT_ROOT / "user_private/overrides" / relative_name
    legacy = PROJECT_ROOT / (legacy_relative_name or f"data/private/{relative_name}")
    return preferred if preferred.is_file() or not legacy.is_file() else legacy
