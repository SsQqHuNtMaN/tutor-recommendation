from __future__ import annotations

import json
import os
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRIVATE_PROFILE = PROJECT_ROOT / "user_private/profile/student_profile.json"
LEGACY_PRIVATE_PROFILE = PROJECT_ROOT / "data/private/student_profile.json"
DEFAULT_TEMPLATE_PROFILE = PROJECT_ROOT / "data/templates/student_profile.example.json"
ALLOW_TEMPLATE_ENV = "TUTOR_ALLOW_TEMPLATE_PROFILE"


DEFAULT_PROFILE: dict[str, Any] = {
    "resume_match_context": (
        "通用示例画像：请在 user_private/profile/student_profile.json 中替换为申请者真实背景、"
        "目标方向、关键词权重和强信号词；公开仓库不内置任何个人简历画像。"
    ),
    "keyword_weights": [
        ["artificial intelligence", 10],
        ["machine learning", 10],
        ["data mining", 8],
        ["software engineering", 6],
        ["人工智能", 10],
        ["机器学习", 10],
    ],
    "institute_bonus": [
        ["人工智能", 4],
        ["计算机", 3],
    ],
    "high_signal_terms": [
        "artificial intelligence",
        "machine learning",
        "人工智能",
        "机器学习",
    ],
}


@dataclass(frozen=True)
class StudentProfile:
    resume_match_context: str
    keyword_weights: list[tuple[str, int]]
    institute_bonus: list[tuple[str, int]]
    high_signal_terms: set[str]
    source_path: Path
    profile_hash: str
    is_demo: bool
    concept_alias_groups: tuple[tuple[str, ...], ...] = ()


class ProfileConfigurationError(RuntimeError):
    """Raised when a formal run has no valid private student profile."""


def _coerce_weight_pairs(value: Any, field_name: str) -> list[tuple[str, int]]:
    if not isinstance(value, list):
        raise ProfileConfigurationError(f"{field_name} must be a list of [keyword, weight] pairs")
    output: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ProfileConfigurationError(f"invalid {field_name} entry: {item!r}")
        keyword, weight = item
        keyword = str(keyword).strip()
        if not keyword:
            raise ProfileConfigurationError(f"{field_name} contains an empty keyword")
        try:
            numeric_weight = int(weight)
        except (TypeError, ValueError) as exc:
            raise ProfileConfigurationError(f"invalid weight for {keyword!r}: {weight!r}") from exc
        if numeric_weight < 0:
            raise ProfileConfigurationError(f"negative weights are not supported: {keyword!r}")
        output.append((keyword, numeric_weight))
    return output


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_configured_profile_path(profile_path: Path | str | None = None) -> Path | None:
    configured = profile_path if profile_path is not None else os.environ.get("STUDENT_PROFILE_PATH")
    if not configured:
        return None
    path = Path(configured).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _load_profile_data(
    profile_path: Path | str | None = None,
    allow_template: bool | None = None,
) -> tuple[dict[str, Any], Path, bool]:
    configured_path = _resolve_configured_profile_path(profile_path)
    if configured_path is not None:
        if not configured_path.is_file():
            raise ProfileConfigurationError(f"configured student profile does not exist: {configured_path}")
        try:
            data = json.loads(configured_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ProfileConfigurationError(f"student profile root must be a JSON object: {configured_path}")
            return data, configured_path, False
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileConfigurationError(f"unable to load student profile {configured_path}: {exc}") from exc

    allow_demo = _env_flag(ALLOW_TEMPLATE_ENV) if allow_template is None else allow_template
    if allow_demo and DEFAULT_TEMPLATE_PROFILE.is_file():
        data = json.loads(DEFAULT_TEMPLATE_PROFILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ProfileConfigurationError(f"student profile root must be a JSON object: {DEFAULT_TEMPLATE_PROFILE}")
        return data, DEFAULT_TEMPLATE_PROFILE, True

    path = DEFAULT_PRIVATE_PROFILE if DEFAULT_PRIVATE_PROFILE.is_file() else LEGACY_PRIVATE_PROFILE
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ProfileConfigurationError(f"student profile root must be a JSON object: {path}")
            return data, path, False
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfileConfigurationError(f"unable to load student profile {path}: {exc}") from exc

    raise ProfileConfigurationError(
        "private student profile is required for a formal run; "
        f"not found at {DEFAULT_PRIVATE_PROFILE}. Ask the Coding Agent to prepare user_private/profile/student_profile.json "
        f"(legacy path: {LEGACY_PRIVATE_PROFILE}) or use --demo-profile explicitly."
    )


def load_student_profile(
    profile_path: Path | str | None = None,
    allow_template: bool | None = None,
) -> StudentProfile:
    raw_data, source_path, is_demo = _load_profile_data(profile_path, allow_template)
    data = raw_data
    if data.get("_draft_requires_confirmation"):
        raise ProfileConfigurationError("student profile is still a draft and requires user confirmation")
    resume_context = str(data.get("resume_match_context") or "").strip()
    if not resume_context:
        raise ProfileConfigurationError("resume_match_context must not be empty")
    keyword_weights = _coerce_weight_pairs(data.get("keyword_weights"), "keyword_weights")
    institute_bonus = _coerce_weight_pairs(data.get("institute_bonus"), "institute_bonus")
    high_signal_terms = {
        str(term).strip().lower()
        for term in data.get("high_signal_terms", [])
        if str(term).strip()
    }
    if not keyword_weights or not high_signal_terms:
        raise ProfileConfigurationError("keyword_weights and high_signal_terms must not be empty")
    positive_terms = {keyword.lower() for keyword, weight in keyword_weights if weight > 0}
    unknown_core = sorted(high_signal_terms - positive_terms)
    if unknown_core:
        raise ProfileConfigurationError(
            "high_signal_terms must reference positive keyword weights: " + ", ".join(unknown_core)
        )
    alias_groups_raw = data.get("concept_alias_groups", [])
    if alias_groups_raw is None:
        alias_groups_raw = []
    if not isinstance(alias_groups_raw, list):
        raise ProfileConfigurationError("concept_alias_groups must be a list of keyword lists")
    alias_groups: list[tuple[str, ...]] = []
    used_aliases: set[str] = set()
    known_terms = {keyword.lower() for keyword, _ in keyword_weights}
    for group in alias_groups_raw:
        if not isinstance(group, list) or len(group) < 2:
            raise ProfileConfigurationError("each concept_alias_groups entry must contain at least two aliases")
        aliases = tuple(str(alias).strip() for alias in group if str(alias).strip())
        lowered = {alias.lower() for alias in aliases}
        unknown = lowered - known_terms
        if unknown:
            raise ProfileConfigurationError("unknown concept aliases: " + ", ".join(sorted(unknown)))
        duplicates = lowered & used_aliases
        if duplicates:
            raise ProfileConfigurationError("concept aliases appear in multiple groups: " + ", ".join(sorted(duplicates)))
        used_aliases.update(lowered)
        alias_groups.append(aliases)
    canonical = json.dumps(raw_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return StudentProfile(
        resume_match_context=resume_context,
        keyword_weights=keyword_weights,
        institute_bonus=institute_bonus,
        high_signal_terms=high_signal_terms,
        source_path=source_path,
        profile_hash=sha256(canonical.encode("utf-8")).hexdigest(),
        is_demo=is_demo,
        concept_alias_groups=tuple(alias_groups),
    )


PROFILE = load_student_profile()
RESUME_MATCH_CONTEXT = PROFILE.resume_match_context
BASE_MATCH_CONTEXT = PROFILE.resume_match_context
KEYWORD_WEIGHTS = PROFILE.keyword_weights
INSTITUTE_BONUS = PROFILE.institute_bonus
HIGH_SIGNAL_TERMS = PROFILE.high_signal_terms
CORE_TERMS = PROFILE.high_signal_terms
PROFILE_HASH = PROFILE.profile_hash
PROFILE_SOURCE = PROFILE.source_path
PROFILE_IS_DEMO = PROFILE.is_demo
