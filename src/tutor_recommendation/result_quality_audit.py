from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIORITY_LEVELS = {"强烈建议", "可以考虑"}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def audit_outputs(outputs_dir: Path) -> dict[str, Any]:
    from .ranking_policy import POLICY_VERSION, evaluate_legacy_row
    from .teacher_identity import ensure_teacher_identity

    workbook_paths = sorted(outputs_dir.glob("*/*/*_teacher_match_full_research.xlsx"))
    old_levels: Counter[str] = Counter()
    new_levels: Counter[str] = Counter()
    transitions: Counter[str] = Counter()
    violations: Counter[str] = Counter()
    workbook_errors: list[dict[str, str]] = []
    total_rows = 0

    for path in workbook_paths:
        try:
            df = pd.read_excel(path, sheet_name="全量教师名录")
        except (OSError, ValueError) as exc:
            workbook_errors.append({"workbook": display_path(path), "error": type(exc).__name__})
            continue

        school_slug = path.parent.parent.name
        college_slug = path.parent.name
        for _, source_row in df.iterrows():
            row = ensure_teacher_identity(school_slug, college_slug, source_row.to_dict())
            decision = evaluate_legacy_row(row)
            old_level = str(row.get("推荐等级") or "未标注").strip()
            old_levels[old_level] += 1
            new_levels[decision.level] += 1
            transitions[f"{old_level} -> {decision.level}"] += 1
            total_rows += 1

            if decision.level in PRIORITY_LEVELS and not decision.explicit_anchor:
                violations["priority_without_anchor"] += 1
            if decision.level in PRIORITY_LEVELS and not decision.reasons:
                violations["priority_without_reason"] += 1
            if not row.get("教师ID"):
                violations["missing_teacher_id"] += 1

    return {
        "policy_version": POLICY_VERSION,
        "workbooks": len(workbook_paths),
        "audited_workbooks": len(workbook_paths) - len(workbook_errors),
        "rows": total_rows,
        "old_levels": dict(sorted(old_levels.items())),
        "new_levels": dict(sorted(new_levels.items())),
        "transitions": dict(sorted(transitions.items())),
        "violations": {
            "priority_without_anchor": violations["priority_without_anchor"],
            "priority_without_reason": violations["priority_without_reason"],
            "missing_teacher_id": violations["missing_teacher_id"],
        },
        "workbook_errors": workbook_errors,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Shadow-score existing workbooks and report aggregate quality checks.")
    parser.add_argument("--outputs-dir", type=Path, default=PROJECT_ROOT / "outputs")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--fail-on-violations", action="store_true")
    args = parser.parse_args(argv)

    report = audit_outputs(args.outputs_dir.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    violation_count = sum(report["violations"].values()) + len(report["workbook_errors"])
    if args.fail_on_violations and violation_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
