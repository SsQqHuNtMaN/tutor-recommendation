from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = PROJECT_ROOT / "user_private"
PROFILES_ROOT = PRIVATE_ROOT / "profiles"
ACTIVE_PROFILE_PATH = PRIVATE_ROOT / "active_profile.json"
LEGACY_PROFILE_ID = "legacy-default"
LEGACY_PROFILE_PATHS = (
    PRIVATE_ROOT / "profile/student_profile.json",
    PROJECT_ROOT / "data/private/student_profile.json",
)
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ProfileRef:
    profile_id: str
    display_name: str
    path: Path
    source_dir: Path
    is_legacy: bool = False
    is_custom_path: bool = False

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def output_root(self) -> Path:
        return output_root_for_profile_id(self.profile_id)

    @property
    def contact_status_path(self) -> Path:
        return self.output_root / "contact_status.json"


def validate_profile_id(profile_id: str) -> str:
    normalized = str(profile_id or "").strip().lower()
    if not PROFILE_ID_PATTERN.fullmatch(normalized):
        raise ValueError("profile_id must use lowercase letters, digits, hyphens or underscores")
    return normalized


def _profile_metadata(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def named_profile(profile_id: str) -> ProfileRef:
    profile_id = validate_profile_id(profile_id)
    profile_dir = PROFILES_ROOT / profile_id
    path = profile_dir / "student_profile.json"
    metadata = _profile_metadata(path)
    display_name = str(metadata.get("display_name") or profile_id).strip() or profile_id
    return ProfileRef(profile_id, display_name, path, profile_dir / "source")


def legacy_profile() -> ProfileRef:
    path = next((candidate for candidate in LEGACY_PROFILE_PATHS if candidate.is_file()), LEGACY_PROFILE_PATHS[0])
    metadata = _profile_metadata(path)
    display_name = str(metadata.get("display_name") or "原有画像").strip() or "原有画像"
    return ProfileRef(LEGACY_PROFILE_ID, display_name, path, path.parent.parent / "source", is_legacy=True)


def _custom_profile(path: Path) -> ProfileRef:
    resolved = path.expanduser().resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    metadata = _profile_metadata(resolved)
    raw_id = str(metadata.get("_profile_id") or "").strip().lower()
    profile_id = raw_id if PROFILE_ID_PATTERN.fullmatch(raw_id) else f"custom-{digest}"
    display_name = str(metadata.get("display_name") or resolved.stem).strip() or resolved.stem
    return ProfileRef(profile_id, display_name, resolved, resolved.parent / "source", is_custom_path=True)


def list_profiles(*, include_incomplete: bool = False) -> list[ProfileRef]:
    profiles: list[ProfileRef] = []
    if PROFILES_ROOT.is_dir():
        for directory in sorted(PROFILES_ROOT.iterdir(), key=lambda item: item.name.lower()):
            if not directory.is_dir() or not PROFILE_ID_PATTERN.fullmatch(directory.name):
                continue
            ref = named_profile(directory.name)
            if include_incomplete or ref.exists:
                profiles.append(ref)
    legacy = legacy_profile()
    if legacy.exists and all(item.path.resolve() != legacy.path.resolve() for item in profiles):
        profiles.insert(0, legacy)
    return profiles


def active_profile_id() -> str:
    try:
        data = json.loads(ACTIVE_PROFILE_PATH.read_text(encoding="utf-8"))
        profile_id = validate_profile_id(str(data.get("profile_id") or ""))
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, AttributeError):
        profile_id = ""
    if profile_id and resolve_profile(profile_id, require_exists=False).exists:
        return profile_id
    profiles = list_profiles()
    if any(profile.profile_id == LEGACY_PROFILE_ID for profile in profiles):
        return LEGACY_PROFILE_ID
    return profiles[0].profile_id if profiles else LEGACY_PROFILE_ID


def resolve_profile(value: str | Path | None = None, *, require_exists: bool = True) -> ProfileRef:
    if value is None or not str(value).strip():
        value = active_profile_id()
    raw = str(value).strip()
    candidate = Path(raw).expanduser()
    looks_like_path = candidate.suffix.lower() == ".json" or any(separator in raw for separator in ("/", "\\"))
    if looks_like_path:
        path = candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve()
        for legacy_path in LEGACY_PROFILE_PATHS:
            if path == legacy_path.resolve():
                ref = legacy_profile()
                break
        else:
            try:
                relative = path.relative_to(PROFILES_ROOT.resolve())
            except ValueError:
                ref = _custom_profile(path)
            else:
                ref = named_profile(relative.parts[0]) if len(relative.parts) >= 2 else _custom_profile(path)
    elif raw == LEGACY_PROFILE_ID:
        ref = legacy_profile()
    else:
        ref = named_profile(raw)
    if require_exists and not ref.exists:
        raise FileNotFoundError(f"student profile not found: {ref.path}")
    return ref


def create_profile(profile_id: str, display_name: str = "") -> ProfileRef:
    ref = named_profile(profile_id)
    ref.path.parent.mkdir(parents=True, exist_ok=True)
    ref.source_dir.mkdir(parents=True, exist_ok=True)
    if display_name and ref.path.is_file():
        data = _profile_metadata(ref.path)
        data["display_name"] = display_name.strip()
        temp = ref.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(ref.path)
    return named_profile(profile_id)


def set_active_profile(value: str | Path) -> ProfileRef:
    ref = resolve_profile(value)
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"profile_id": ref.profile_id}
    temp = ACTIVE_PROFILE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(ACTIVE_PROFILE_PATH)
    return ref


def output_root_for_profile_id(profile_id: str) -> Path:
    profile_id = validate_profile_id(profile_id)
    if profile_id == LEGACY_PROFILE_ID:
        return PROJECT_ROOT / "outputs"
    return PROJECT_ROOT / "outputs/by_profile" / profile_id


def configured_profile_id() -> str:
    raw = os.environ.get("TUTOR_PROFILE_ID", "").strip()
    if raw:
        return validate_profile_id(raw)
    return LEGACY_PROFILE_ID


def configured_output_root() -> Path:
    configured = os.environ.get("TUTOR_OUTPUT_ROOT", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    return output_root_for_profile_id(configured_profile_id())


def configure_profile_environment(value: str | Path | None = None) -> ProfileRef:
    ref = resolve_profile(value)
    os.environ.pop("TUTOR_ALLOW_TEMPLATE_PROFILE", None)
    os.environ["STUDENT_PROFILE_PATH"] = str(ref.path)
    os.environ["TUTOR_PROFILE_ID"] = ref.profile_id
    os.environ["TUTOR_OUTPUT_ROOT"] = str(ref.output_root)
    return ref
