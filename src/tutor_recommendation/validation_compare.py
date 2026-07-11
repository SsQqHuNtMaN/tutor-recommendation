from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .ranking_policy import evaluate_legacy_row
from .teacher_identity import ensure_teacher_identity


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DIR = PROJECT_ROOT / "docs/private"
LEVEL_RANK = {"暂不优先": 0, "可以考虑": 1, "强烈建议": 2}


def load_json(name: str) -> dict[str, Any]:
    return json.loads((PRIVATE_DIR / name).read_text(encoding="utf-8"))


def current_decisions(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in queue["samples"]:
        by_target.setdefault(item["target"], []).append(item)
    decisions: dict[str, dict[str, Any]] = {}
    for target, items in by_target.items():
        school, college = target.split("/")
        path = PROJECT_ROOT / "outputs" / school / college / f"{school}_{college}_teacher_match_full_research.xlsx"
        df = pd.read_excel(path, sheet_name="全量教师名录")
        rows = [ensure_teacher_identity(school, college, row.to_dict()) for _, row in df.iterrows()]
        indexed = {row["教师ID"]: row for row in rows}
        for item in items:
            row = indexed[item["teacher_id"]]
            decision = evaluate_legacy_row(row)
            decisions[item["sample_id"]] = {
                "new_level": decision.level,
                "new_score": decision.score,
                "anchor": decision.explicit_anchor,
                "reason": "；".join(decision.reasons),
                "warnings": "；".join(decision.warnings),
            }
    return decisions


def dataset_names(dataset: str) -> tuple[str, str, str, str]:
    suffix = "-holdout" if dataset == "holdout" else ""
    return (
        f"p1-validation{suffix}-queue.local.json",
        f"p1-validation{suffix}-baseline.local.json",
        f"p1-validation{suffix}-manual.local.json",
        f"p1-validation{suffix}-comparison.local",
    )


def compare(dataset: str = "calibration") -> dict[str, Any]:
    queue_name, baseline_name, manual_name, _ = dataset_names(dataset)
    queue = load_json(queue_name)
    baseline = load_json(baseline_name)
    manual = load_json(manual_name)
    current = current_decisions(queue)
    old_by_id = {item["sample_id"]: item for item in baseline["samples"]}
    manual_by_id = {item["sample_id"]: item for item in manual["samples"]}
    rows = []
    for queue_item in queue["samples"]:
        sample_id = queue_item["sample_id"]
        old = old_by_id[sample_id]
        human = manual_by_id[sample_id]
        new = current[sample_id]
        old_error = abs(LEVEL_RANK[old["old_level"]] - LEVEL_RANK[human["manual_level"]])
        new_error = abs(LEVEL_RANK[new["new_level"]] - LEVEL_RANK[human["manual_level"]])
        rows.append(
            {
                "sample_id": sample_id,
                "category": old["category"],
                "target": queue_item["target"],
                "manual_level": human["manual_level"],
                "manual_score": human["total"],
                "old_level": old["old_level"],
                "old_score": old["old_score"],
                "new_level": new["new_level"],
                "new_score": new["new_score"],
                "new_anchor": new["anchor"],
                "old_error": old_error,
                "new_error": new_error,
                "new_reason": new["reason"],
                "new_warnings": new["warnings"],
            }
        )
    main_rows = [row for row in rows if row["category"] != "zero_weight_sentinel"]
    return {
        "dataset": dataset,
        "samples": rows,
        "metrics": {
            "main_samples": len(main_rows),
            "old_exact": sum(row["old_error"] == 0 for row in main_rows),
            "new_exact": sum(row["new_error"] == 0 for row in main_rows),
            "old_weighted_error": sum(row["old_error"] for row in main_rows),
            "new_weighted_error": sum(row["new_error"] for row in main_rows),
            "new_within_one_level": sum(row["new_error"] <= 1 for row in main_rows),
            "new_severe_false_promotions": sum(
                row["manual_level"] == "暂不优先" and row["new_level"] == "强烈建议" for row in main_rows
            ),
            "priority_without_anchor": sum(
                row["new_level"] in {"强烈建议", "可以考虑"} and not row["new_anchor"] for row in rows
            ),
        },
    }


def write_report(dataset: str = "calibration") -> tuple[Path, Path]:
    result = compare(dataset)
    _, _, _, output_stem = dataset_names(dataset)
    json_path = PRIVATE_DIR / f"{output_stem}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metrics = result["metrics"]
    lines = [
        f"# P1 新旧 Workflow 私有{'留出集' if dataset == 'holdout' else '校准集'}验证报告",
        "",
        "该报告只记录 sample_id 和聚合结论；教师姓名与来源映射保存在同目录的私有 queue 文件中。",
        "",
        "## 聚合指标",
        "",
        f"- 主样本：{metrics['main_samples']}",
        f"- 旧 workflow 完全一致：{metrics['old_exact']}/{metrics['main_samples']}",
        f"- 新 policy 完全一致：{metrics['new_exact']}/{metrics['main_samples']}",
        f"- 旧 workflow 等级误差：{metrics['old_weighted_error']}",
        f"- 新 policy 等级误差：{metrics['new_weighted_error']}",
        f"- 新 policy 相差不超过一级：{metrics['new_within_one_level']}/{metrics['main_samples']}",
        f"- 新 policy 严重误升：{metrics['new_severe_false_promotions']}",
        f"- 新 policy 无锚点进入优先名单：{metrics['priority_without_anchor']}",
        "",
        "## 样本对比",
        "",
        "| Sample | 类别 | 人工 | 旧版 | 新版 | 新锚点 |",
        "|---|---|---|---|---|---|",
    ]
    for row in result["samples"]:
        lines.append(
            f"| {row['sample_id']} | {row['category']} | {row['manual_level']} | "
            f"{row['old_level']} | {row['new_level']} | {'是' if row['new_anchor'] else '否'} |"
        )
    md_path = PRIVATE_DIR / f"{output_stem}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare manual validation labels with old and current ranking policy.")
    parser.add_argument("--dataset", choices=("calibration", "holdout"), default="calibration")
    args = parser.parse_args()
    json_path, md_path = write_report(args.dataset)
    result = json.loads(json_path.read_text(encoding="utf-8"))
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
