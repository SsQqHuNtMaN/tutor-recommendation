from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .ranking_policy import PROFILE, evaluate_legacy_row, keyword_in_text, score_text
from .run_manifest import file_sha256
from .teacher_identity import ensure_teacher_identity


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
PRIVATE_DIR = PROJECT_ROOT / "docs/private"
SEED = "p1-validation-2026-07-11"
HOLDOUT_SEED = "p1-validation-holdout-2026-07-11"
CORE_COLUMNS = ["研究方向", "导师信息库研究方向", "团队PDF证据"]
EXTERNAL_COLUMNS = [
    "DBLP近三年关键词",
    "DBLP近三年代表论文",
    "arXiv关键词",
    "arXiv代表论文",
    "网页关键词",
    "网页近三年/发表证据",
    "WebSearch关键词",
    "WebSearch代表证据",
]


def norm(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def stable_rank(teacher_id: str) -> str:
    return hashlib.sha256(f"{SEED}|{teacher_id}".encode("utf-8")).hexdigest()


def holdout_rank(teacher_id: str) -> str:
    return hashlib.sha256(f"{HOLDOUT_SEED}|{teacher_id}".encode("utf-8")).hexdigest()


def load_rows() -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for path in sorted(OUTPUT_DIR.glob("*/*/*_teacher_match_full_research.xlsx")):
        school_slug, college_slug = path.parent.parts[-2:]
        target = f"{school_slug}/{college_slug}"
        hashes[str(path.relative_to(PROJECT_ROOT))] = file_sha256(path)
        df = pd.read_excel(path, sheet_name="全量教师名录")
        for _, source in df.iterrows():
            row = ensure_teacher_identity(school_slug, college_slug, source.to_dict())
            decision = evaluate_legacy_row(row)
            explicit = " ".join(norm(row.get(column)) for column in CORE_COLUMNS)
            external = " ".join(norm(row.get(column)) for column in EXTERNAL_COLUMNS)
            _, external_positive = score_text(external)
            zero_terms = [
                keyword
                for keyword, weight in PROFILE.keyword_weights
                if weight == 0 and keyword_in_text(keyword, f"{explicit} {external}".lower())
            ]
            row.update(
                {
                    "_target": target,
                    "_school": school_slug,
                    "_old_level": norm(row.get("推荐等级")),
                    "_old_score": row.get("匹配分", 0),
                    "_new_level": decision.level,
                    "_new_score": decision.score,
                    "_anchor": decision.explicit_anchor,
                    "_external_positive": bool(external_positive),
                    "_zero_terms": zero_terms,
                    "_multi_source": (
                        norm(row.get("DBLP匹配置信度")) == "高"
                        or norm(row.get("arXiv置信度")) == "中-DBLP交叉确认"
                        or bool(norm(row.get("网页关键词")))
                    ),
                    "_ambiguous_identity": (
                        norm(row.get("DBLP匹配置信度")) in {"中", "低"}
                        or "歧义" in norm(row.get("DBLP匹配状态"))
                        or "低" in norm(row.get("arXiv置信度"))
                    ),
                }
            )
            rows.append(row)
    return rows, hashes


def select_samples(rows: list[dict[str, Any]]) -> list[tuple[str, str, dict[str, Any]]]:
    categories: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("strong_without_anchor_1", lambda row: row["_old_level"] == "强烈建议" and not row["_anchor"]),
        ("strong_without_anchor_2", lambda row: row["_old_level"] == "强烈建议" and not row["_anchor"]),
        (
            "stable_strong_multisource",
            lambda row: row["_old_level"] == "强烈建议" and row["_anchor"] and row["_multi_source"],
        ),
        (
            "stable_strong_official",
            lambda row: row["_old_level"] == "强烈建议" and row["_anchor"] and not row["_multi_source"],
        ),
        (
            "consider_with_anchor",
            lambda row: row["_old_level"] == "可以考虑" and row["_anchor"],
        ),
        (
            "consider_without_anchor",
            lambda row: row["_old_level"] == "可以考虑" and not row["_anchor"],
        ),
        (
            "low_with_external_signal",
            lambda row: row["_old_level"] == "暂不优先" and not row["_anchor"] and row["_external_positive"],
        ),
        (
            "anchor_with_identity_ambiguity",
            lambda row: row["_anchor"] and row["_ambiguous_identity"],
        ),
        (
            "zero_weight_sentinel",
            lambda row: row["_old_level"] in {"强烈建议", "可以考虑"}
            and not row["_anchor"]
            and bool(row["_zero_terms"]),
        ),
    ]
    selected: list[tuple[str, str, dict[str, Any]]] = []
    used_ids: set[str] = set()
    used_targets: set[str] = set()
    school_counts: dict[str, int] = {}
    for category, predicate in categories:
        candidates = sorted(
            (row for row in rows if predicate(row) and row["教师ID"] not in used_ids),
            key=lambda row: stable_rank(row["教师ID"]),
        )
        candidate = next(
            (
                row
                for row in candidates
                if row["_target"] not in used_targets and school_counts.get(row["_school"], 0) < 2
            ),
            None,
        )
        if candidate is None:
            candidate = next((row for row in candidates if school_counts.get(row["_school"], 0) < 2), None)
        if candidate is None:
            raise RuntimeError(f"unable to select validation sample for {category}")
        sample_id = f"sample_{len(selected) + 1:02d}"
        selected.append((sample_id, category, candidate))
        used_ids.add(candidate["教师ID"])
        used_targets.add(candidate["_target"])
        school_counts[candidate["_school"]] = school_counts.get(candidate["_school"], 0) + 1
    return selected


def write_samples() -> tuple[Path, Path]:
    rows, workbook_hashes = load_rows()
    selected = select_samples(rows)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    queue = []
    baseline = []
    for sample_id, category, row in selected:
        queue.append(
            {
                "sample_id": sample_id,
                "target": row["_target"],
                "teacher_id": row["教师ID"],
                "name": norm(row.get("姓名")),
                "official_url": norm(row.get("教师主页链接")),
                "personal_url": norm(row.get("个人主页")),
                "dblp_url": norm(row.get("DBLP作者链接")),
            }
        )
        baseline.append(
            {
                "sample_id": sample_id,
                "category": category,
                "target": row["_target"],
                "teacher_id": row["教师ID"],
                "old_level": row["_old_level"],
                "old_score": row["_old_score"],
                "new_level": row["_new_level"],
                "new_score": row["_new_score"],
                "new_anchor": row["_anchor"],
            }
        )
    queue_path = PRIVATE_DIR / "p1-validation-queue.local.json"
    baseline_path = PRIVATE_DIR / "p1-validation-baseline.local.json"
    queue_path.write_text(json.dumps({"seed": SEED, "samples": queue}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline_path.write_text(
        json.dumps(
            {"seed": SEED, "workbook_hashes": workbook_hashes, "samples": baseline},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return queue_path, baseline_path


def write_holdout_samples() -> tuple[Path, Path]:
    rows, workbook_hashes = load_rows()
    initial = json.loads((PRIVATE_DIR / "p1-validation-queue.local.json").read_text(encoding="utf-8"))
    excluded = {item["teacher_id"] for item in initial["samples"]}
    rows = [row for row in rows if row["教师ID"] not in excluded]
    categories: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        (
            "old_priority_without_anchor",
            lambda row: row["_old_level"] in {"强烈建议", "可以考虑"} and not row["_anchor"],
        ),
        (
            "new_strong_with_anchor",
            lambda row: row["_new_level"] == "强烈建议" and row["_anchor"],
        ),
        (
            "new_consider_with_anchor",
            lambda row: row["_new_level"] == "可以考虑" and row["_anchor"],
        ),
    ]
    selected: list[tuple[str, str, dict[str, Any]]] = []
    used_schools: set[str] = set()
    used_targets: set[str] = set()
    for category, predicate in categories:
        candidates = sorted((row for row in rows if predicate(row)), key=lambda row: holdout_rank(row["教师ID"]))
        candidate = next(
            (row for row in candidates if row["_school"] not in used_schools and row["_target"] not in used_targets),
            None,
        )
        if candidate is None:
            raise RuntimeError(f"unable to select holdout sample for {category}")
        sample_id = f"holdout_{len(selected) + 1:02d}"
        selected.append((sample_id, category, candidate))
        used_schools.add(candidate["_school"])
        used_targets.add(candidate["_target"])
    queue = []
    baseline = []
    for sample_id, category, row in selected:
        queue.append(
            {
                "sample_id": sample_id,
                "target": row["_target"],
                "teacher_id": row["教师ID"],
                "name": norm(row.get("姓名")),
                "official_url": norm(row.get("教师主页链接")),
                "personal_url": norm(row.get("个人主页")),
                "dblp_url": norm(row.get("DBLP作者链接")),
            }
        )
        baseline.append(
            {
                "sample_id": sample_id,
                "category": category,
                "target": row["_target"],
                "teacher_id": row["教师ID"],
                "old_level": row["_old_level"],
                "old_score": row["_old_score"],
                "new_level": row["_new_level"],
                "new_score": row["_new_score"],
                "new_anchor": row["_anchor"],
            }
        )
    queue_path = PRIVATE_DIR / "p1-validation-holdout-queue.local.json"
    baseline_path = PRIVATE_DIR / "p1-validation-holdout-baseline.local.json"
    queue_path.write_text(json.dumps({"seed": HOLDOUT_SEED, "samples": queue}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline_path.write_text(
        json.dumps({"seed": HOLDOUT_SEED, "workbook_hashes": workbook_hashes, "samples": baseline}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return queue_path, baseline_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze private validation samples from current workbooks.")
    parser.add_argument("--holdout", action="store_true", help="Create a three-sample post-calibration holdout set.")
    args = parser.parse_args()
    queue, baseline = write_holdout_samples() if args.holdout else write_samples()
    data = json.loads(queue.read_text(encoding="utf-8"))
    print(f"samples={len(data['samples'])}")
    for item in data["samples"]:
        print(f"{item['sample_id']} target={item['target']} teacher_id={item['teacher_id']}")
    print(f"queue={queue}")
    print(f"baseline={baseline}")


if __name__ == "__main__":
    main()
