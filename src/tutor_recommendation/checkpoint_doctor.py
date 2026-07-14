from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .run_manifest import checkpoint_fingerprint, create_run_context
from .teacher_identity import ensure_teacher_identity, teacher_record_key
from .teacher_match_targets import TARGETS, TargetConfig, get_target


def load_latest_checkpoint(path: Path) -> tuple[dict[str, dict[str, Any]], int, int]:
    latest_by_index: dict[int, dict[str, Any]] = {}
    lines = 0
    invalid = 0
    if not path.exists():
        return {}, lines, invalid
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            lines += 1
            try:
                item = json.loads(line)
                latest_by_index[int(item["index"])] = item
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                invalid += 1
    keyed: dict[str, dict[str, Any]] = {}
    for item in latest_by_index.values():
        row = item.get("row", {})
        key = str(row.get("教师ID") or "")
        if key:
            keyed[key] = item
    return keyed, lines, invalid


def audit_target(target: TargetConfig) -> dict[str, Any]:
    input_path = target.evidence_path
    checkpoint_path = target.output_dir / "full_research_checkpoint.jsonl"
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    context = create_run_context(
        "final", target.key, [input_path], recent_year_count=target.publication_window_years
    )
    df = pd.read_excel(input_path, sheet_name="全量教师名录")
    rows = [ensure_teacher_identity(target.school_slug, target.college_slug, row.to_dict()) for _, row in df.iterrows()]
    checkpoint_by_id, lines, invalid = load_latest_checkpoint(checkpoint_path)
    valid = 0
    missing = 0
    stale = 0
    for row in rows:
        teacher_id = row["教师ID"]
        item = checkpoint_by_id.get(teacher_id)
        if not item:
            missing += 1
            continue
        expected = checkpoint_fingerprint(row, target.school_slug, target.college_slug, context)
        if item.get("fingerprint") == expected:
            valid += 1
        else:
            stale += 1
    return {
        "target": target.key,
        "input_rows": len(rows),
        "checkpoint_lines": lines,
        "invalid_json_lines": invalid,
        "valid": valid,
        "stale": stale,
        "missing": missing,
        "coverage": round(valid / len(rows), 4) if rows else 1.0,
        "ok_for_finalize_only": valid == len(rows) and invalid == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit final-stage checkpoint coverage and fingerprints.")
    parser.add_argument("targets", nargs="+", help=f"Targets. Available: {', '.join(TARGETS)}")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    reports = [audit_target(get_target(key)) for key in args.targets]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return
    for report in reports:
        print(
            f"{report['target']}: valid={report['valid']}/{report['input_rows']} "
            f"stale={report['stale']} missing={report['missing']} invalid={report['invalid_json_lines']} "
            f"finalize_only={'yes' if report['ok_for_finalize_only'] else 'no'}"
        )


if __name__ == "__main__":
    main()
