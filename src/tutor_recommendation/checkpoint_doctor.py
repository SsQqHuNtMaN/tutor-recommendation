from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .run_manifest import checkpoint_fingerprint, create_run_context
from .teacher_identity import ensure_teacher_identity, teacher_record_key
from .teacher_match_targets import TARGETS, TargetConfig, get_target


def audit_publication_workbook(path: Path) -> dict[str, Any]:
    try:
        workbook = pd.ExcelFile(path)
    except (OSError, ValueError):
        return {"applicable": False, "error": "unreadable_workbook"}
    if "数学文献近五年明细" not in workbook.sheet_names:
        return {"applicable": False}
    main = pd.read_excel(workbook, sheet_name="全量教师名录")
    detail = pd.read_excel(workbook, sheet_name="数学文献近五年明细")
    candidates = (
        pd.read_excel(workbook, sheet_name="学术作者候选")
        if "学术作者候选" in workbook.sheet_names
        else pd.DataFrame()
    )
    source_report = (
        pd.read_excel(workbook, sheet_name="论文来源报告")
        if "论文来源报告" in workbook.sheet_names
        else pd.DataFrame()
    )
    workbook.close()
    def column_text(frame: pd.DataFrame, name: str) -> pd.Series:
        series = frame[name] if name in frame else pd.Series([""] * len(frame), index=frame.index)
        return series.fillna("").astype(str).str.strip()

    seed_series = column_text(main, "论文身份种子哈希")
    titles = column_text(detail, "题名")
    canonical_ids = column_text(detail, "规范论文ID")
    teacher_ids = column_text(detail, "教师ID")
    trace_ids = column_text(detail, "追溯记录ID")
    urls = column_text(detail, "证据URL")
    duplicate_canonical = 0
    if len(canonical_ids) and len(teacher_ids):
        duplicate_canonical = int(
            pd.DataFrame({"teacher": teacher_ids, "canonical": canonical_ids})
            .query("canonical != ''")
            .duplicated(["teacher", "canonical"], keep=False)
            .sum()
        )
    statuses = {}
    if not source_report.empty and {"来源", "状态"}.issubset(source_report.columns):
        statuses = {
            f"{source}|{status}": int(count)
            for (source, status), count in source_report.fillna("").groupby(["来源", "状态"]).size().items()
        }
    review_count = 0
    if not candidates.empty and "是否需人工复核" in candidates:
        review_count = int((candidates["是否需人工复核"].fillna("") == "是").sum())
    elif not candidates.empty and "候选决策" in candidates:
        review_count = int(candidates["候选决策"].fillna("").isin(["review", "unresolved"]).sum())
    report = {
        "applicable": True,
        "identity_seed_coverage": int((seed_series != "").sum()),
        "teacher_rows": int(len(main)),
        "publication_rows": int(len(detail)),
        "blank_titles": int((titles == "").sum()),
        "duplicate_canonical_rows": duplicate_canonical,
        "missing_trace_rows": int(((trace_ids == "") & (urls == "")).sum()) if len(detail) else 0,
        "review_queue": review_count,
        "source_status": statuses,
    }
    report["ok"] = (
        report["identity_seed_coverage"] == report["teacher_rows"]
        and report["blank_titles"] == 0
        and report["duplicate_canonical_rows"] == 0
        and report["missing_trace_rows"] == 0
    )
    return report


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
    report = {
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
    publication_audit = audit_publication_workbook(input_path)
    report["publication_audit"] = publication_audit
    report["publication_ok"] = publication_audit.get("ok") if publication_audit.get("applicable") else None
    return report


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
