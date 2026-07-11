from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ranking_policy import POLICY_VERSION, SCHEMA_VERSION, norm_text
from .student_profile import PROFILE_HASH, PROFILE_IS_DEMO, PROFILE_SOURCE
from .teacher_identity import teacher_id_for_row


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_NAME = "run_manifest.json"


def recent_years(current_year: int | None = None, count: int = 3) -> tuple[str, ...]:
    year = current_year or date.today().year
    return tuple(str(year - offset) for offset in range(count))


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_revision() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    stage: str
    target_key: str
    generated_at: str
    schema_version: int
    policy_version: str
    profile_hash: str
    profile_is_demo: bool
    profile_source: str
    code_revision: str
    recent_years: tuple[str, ...]
    input_hashes: dict[str, str]

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_run_context(stage: str, target_key: str, input_paths: Iterable[Path] = ()) -> RunContext:
    hashes = {str(path): file_sha256(path) for path in input_paths}
    return RunContext(
        run_id=f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}",
        stage=stage,
        target_key=target_key,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        schema_version=SCHEMA_VERSION,
        policy_version=POLICY_VERSION,
        profile_hash=PROFILE_HASH,
        profile_is_demo=PROFILE_IS_DEMO,
        profile_source=str(PROFILE_SOURCE),
        code_revision=code_revision(),
        recent_years=recent_years(),
        input_hashes=hashes,
    )


def manifest_path(output_dir: Path) -> Path:
    return output_dir / MANIFEST_NAME


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = manifest_path(output_dir)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "stages": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"run manifest is unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("stages", {}), dict):
        raise RuntimeError(f"invalid run manifest structure: {path}")
    return data


def write_stage_manifest(output_dir: Path, context: RunContext) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_manifest(output_dir)
    data["schema_version"] = SCHEMA_VERSION
    data.setdefault("stages", {})[context.stage] = {**asdict(context), "fingerprint": context.fingerprint}
    path = manifest_path(output_dir)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return path


def context_source_rows(context: RunContext) -> list[dict[str, str]]:
    return [
        {"项目": "运行ID", "内容": context.run_id},
        {"项目": "数据Schema版本", "内容": str(context.schema_version)},
        {"项目": "评分规则版本", "内容": context.policy_version},
        {"项目": "画像哈希", "内容": context.profile_hash},
        {"项目": "画像模式", "内容": "公开示例" if context.profile_is_demo else "本地私有画像"},
        {"项目": "代码版本", "内容": context.code_revision},
        {"项目": "近三年口径", "内容": "/".join(context.recent_years)},
        {"项目": "输入哈希", "内容": json.dumps(context.input_hashes, ensure_ascii=False, sort_keys=True)},
    ]


def checkpoint_fingerprint(row: Any, school_slug: str, college_slug: str, context: RunContext) -> str:
    fields = [
        "姓名",
        "教师主页链接",
        "个人主页",
        "邮箱",
        "研究方向",
        "导师信息库研究方向",
        "团队PDF证据",
        "个人简介摘要",
        "DBLP匹配置信度",
        "DBLP作者链接",
        "DBLP近三年关键词",
        "DBLP近三年代表论文",
    ]
    payload = {
        "teacher_id": teacher_id_for_row(school_slug, college_slug, row),
        "row": {field: norm_text(row.get(field, "")) for field in fields},
        "schema_version": context.schema_version,
        "policy_version": context.policy_version,
        "profile_hash": context.profile_hash,
        "recent_years": context.recent_years,
        "input_hashes": context.input_hashes,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
