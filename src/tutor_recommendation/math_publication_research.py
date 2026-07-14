from __future__ import annotations

import json
import os
import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from .contact_status import apply_contact_statuses
from .first_pass_research import style_workbook
from .profile_registry import configured_output_root
from .publication_adapters import OpenAlexAdapter, OfficialPublicationAdapter, ZbMathAdapter
from .ranking_policy import PROFILE, evaluate_teacher, score_text, unique_join
from .run_manifest import (
    assert_stage_profile_compatible,
    context_source_rows,
    create_run_context,
    write_stage_manifest,
)
from .teacher_identity import TEACHER_ID_COLUMN


SCHOOL_SLUG = os.environ.get("SCHOOL_SLUG", "ruc")
COLLEGE_SLUG = os.environ.get("COLLEGE_SLUG", "isbd")
TARGET_KEY = os.environ.get("TARGET_KEY", f"{SCHOOL_SLUG}_{COLLEGE_SLUG}")
WINDOW_YEARS = max(1, int(os.environ.get("PUBLICATION_WINDOW_YEARS", "5")))
END_YEAR = date.today().year
START_YEAR = END_YEAR - WINDOW_YEARS + 1
OUTPUT_DIR = configured_output_root() / SCHOOL_SLUG / COLLEGE_SLUG
OUTPUT_PREFIX = f"{SCHOOL_SLUG}_{COLLEGE_SLUG}_teacher_match"
INPUT_PATH = OUTPUT_DIR / f"{OUTPUT_PREFIX}.xlsx"
OUTPUT_PATH = OUTPUT_DIR / f"{OUTPUT_PREFIX}_publications.xlsx"
CACHE_DIR = OUTPUT_DIR / "math_publication_cache"
CACHE_VERSION = "2026-07-14-v3"


def _cache_path(source: str, row: dict[str, Any]) -> Path:
    identity = str(row.get(TEACHER_ID_COLUMN) or row.get("姓名") or "unknown")
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in identity)
    return CACHE_DIR / source / f"{safe}.json"


def _collect_cached(adapter: Any, row: dict[str, Any]) -> dict[str, Any]:
    path = _cache_path(adapter.source, row)
    relevant = {
        key: str(row.get(key) or "")
        for key in ("姓名", "英文姓名", "教师主页链接", "个人主页", "ORCID", "官方论文列表", "官方论文来源")
    }
    input_hash = hashlib.sha256(
        json.dumps(relevant, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("version") == CACHE_VERSION
            and payload.get("window") == [START_YEAR, END_YEAR]
            and payload.get("input_hash") == input_hash
            and isinstance(payload.get("result"), dict)
            and payload["result"].get("status") not in {"not_configured", "request_failed"}
        ):
            return payload["result"]
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    result = adapter.collect(row, start_year=START_YEAR, end_year=END_YEAR).to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {"version": CACHE_VERSION, "window": [START_YEAR, END_YEAR], "input_hash": input_hash, "result": result},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)
    return result


def _accepted_works(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    works: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in results:
        if result.get("source") != "official" and not (
            result.get("status") == "success" and result.get("confidence") in {"high", "medium"}
        ):
            continue
        for work in result.get("works") or []:
            key = (str(work.get("doi") or "").lower(), str(work.get("title") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            works.append(work)
    works.sort(key=lambda item: int(item.get("year") or 0), reverse=True)
    return works


def _evidence_columns(results: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = _accepted_works(results)
    external = [item for item in results if item.get("source") != "official"]
    confirmed = [item for item in external if item.get("status") == "success"]
    confirmed.sort(key=lambda item: {"high": 2, "medium": 1}.get(item.get("confidence"), 0), reverse=True)
    official = next((item for item in results if item.get("source") == "official" and item.get("status") == "success"), {})
    best = confirmed[0] if confirmed else official
    zbmath = next((item for item in results if item.get("source") == "zbmath"), {})
    openalex = next((item for item in results if item.get("source") == "openalex"), {})
    classifications = list(
        dict.fromkeys(
            str(value)
            for result in results
            if result.get("status") == "success"
            for value in result.get("classifications") or []
            if value
        )
    )
    title_text = " ".join(str(work.get("title") or "") for work in accepted)
    _, matched_keywords = score_text(title_text, profile=PROFILE, max_terms=12)
    weight_by_keyword = {keyword.lower(): weight for keyword, weight in PROFILE.keyword_weights}
    ai_matches = [keyword for keyword in matched_keywords if weight_by_keyword.get(keyword.lower(), 0) >= 20]
    math_matches = [keyword for keyword in matched_keywords if keyword not in ai_matches]
    status_text = "; ".join(
        f"{item.get('source')}:{item.get('status')}" + (f"/{item.get('confidence')}" if item.get("confidence") else "")
        for item in results
    )
    reasons = "; ".join(
        f"{item.get('source')}:{item.get('reason')}" for item in results if item.get("reason")
    )
    return {
        "学术作者匹配状态": status_text,
        "学术作者匹配置信度": best.get("confidence", ""),
        "学术作者ID": best.get("author_id", ""),
        "zbMATH作者链接": zbmath.get("author_url", ""),
        "OpenAlex作者ID": openalex.get("author_id", ""),
        "OpenAlex作者链接": openalex.get("author_url", ""),
        "ORCID": best.get("orcid", "") or zbmath.get("orcid", "") or openalex.get("orcid", ""),
        "主要数学分类": unique_join(classifications[:12], "；"),
        "数学统计核心匹配": unique_join(math_matches, "；"),
        "AI交叉匹配": unique_join(ai_matches, "；"),
        "AI桥接证据": unique_join(ai_matches, "；"),
        "近五年论文数": len(accepted),
        "近五年关键词": unique_join(matched_keywords, "；"),
        "近五年代表论文": "；".join(str(work.get("title") or "") for work in accepted[:5]),
        "论文证据来源": unique_join(
            [item.get("source") for item in results if item.get("status") == "success"], "；"
        ),
        "论文证据摘要": reasons,
    }


def _safe_score(value: Any) -> float:
    try:
        score = float(value or 0)
        return 0.0 if pd.isna(score) else score
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"未找到数学文献阶段输入表：{INPUT_PATH}")
    run_context = create_run_context(
        "math_publications", TARGET_KEY, [INPUT_PATH], recent_year_count=WINDOW_YEARS
    )
    assert_stage_profile_compatible(OUTPUT_DIR, "first_pass", run_context)
    df = pd.read_excel(INPUT_PATH, sheet_name="全量教师名录")
    session = requests.Session()
    session.trust_env = False
    adapters = [OfficialPublicationAdapter(), ZbMathAdapter(session), OpenAlexAdapter(session)]
    output_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        row = series.to_dict()
        should_query_external = bool(str(row.get("显式核心锚点") or "") == "是" or _safe_score(row.get("匹配分")) > 0)
        results: list[dict[str, Any]] = []
        for adapter in adapters:
            if adapter.source != "official" and not should_query_external:
                result = {
                    "source": adapter.source,
                    "status": "not_queried_low_match",
                    "confidence": "",
                    "author_id": "",
                    "author_url": "",
                    "orcid": "",
                    "classifications": [],
                    "works": [],
                    "reason": "第一阶段未命中当前画像，未执行外部作者检索",
                    "metadata": {},
                }
            else:
                result = _collect_cached(adapter, row)
            results.append(result)
        row.update(_evidence_columns(results))
        decision = evaluate_teacher(row, publication={
            "status": row.get("学术作者匹配状态", ""),
            "confidence": row.get("学术作者匹配置信度", ""),
            "keywords": row.get("近五年关键词", ""),
            "titles": row.get("近五年代表论文", ""),
            "classifications": row.get("主要数学分类", ""),
        })
        row.update(decision.to_columns())
        output_rows.append(row)
        for result in results:
            for work in result.get("works") or []:
                accepted = result.get("source") == "official" or (
                    result.get("status") == "success"
                    and result.get("confidence") in {"high", "medium"}
                )
                details.append(
                    {
                        TEACHER_ID_COLUMN: row.get(TEACHER_ID_COLUMN, ""),
                        "姓名": row.get("姓名", ""),
                        "来源": result.get("source", ""),
                        "作者身份置信度": result.get("confidence", ""),
                        "是否计入匹配": "是" if accepted else "否",
                        "年份": work.get("year", ""),
                        "题名": work.get("title", ""),
                        "DOI": work.get("doi", ""),
                        "分类": unique_join(work.get("classifications") or [], "；"),
                        "主题": unique_join(work.get("topics") or [], "；"),
                        "证据URL": work.get("url", ""),
                    }
                )

    out = apply_contact_statuses(pd.DataFrame(output_rows), SCHOOL_SLUG, COLLEGE_SLUG)
    priority_order = {"强烈建议": 0, "可以考虑": 1, "暂不优先": 2}
    out["_order"] = out["推荐等级"].map(priority_order).fillna(9)
    out = out.sort_values(["_order", "匹配分", "名录序号"], ascending=[True, False, True]).drop(columns=["_order"])
    priority = out[out["是否建议套磁"] == "是"].copy()
    detail_df = pd.DataFrame(details)
    if not detail_df.empty:
        detail_df = detail_df.drop_duplicates(subset=[TEACHER_ID_COLUMN, "来源", "DOI", "题名"], keep="first")
        detail_df = apply_contact_statuses(detail_df, SCHOOL_SLUG, COLLEGE_SLUG)
    try:
        source = pd.read_excel(INPUT_PATH, sheet_name="匹配依据")
    except ValueError:
        source = pd.DataFrame(columns=["项目", "内容"])
    source = pd.concat(
        [
            source,
            pd.DataFrame(
                [
                    {"项目": "数学论文证据", "内容": "官方 publication list + zbMATH Open + OpenAlex（配置时）"},
                    {"项目": "数学论文窗口", "内容": f"{START_YEAR}-{END_YEAR}"},
                    {"项目": "作者消歧", "内容": "姓名只用于召回；ORCID、官方主页、机构和官网论文题名重合用于确认"},
                ]
                + context_source_rows(run_context)
            ),
        ],
        ignore_index=True,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        priority.to_excel(writer, sheet_name="优先套磁名单", index=False)
        out.to_excel(writer, sheet_name="全量教师名录", index=False)
        detail_df.to_excel(writer, sheet_name="数学文献近五年明细", index=False)
        source.to_excel(writer, sheet_name="匹配依据", index=False)
    style_workbook(OUTPUT_PATH)
    write_stage_manifest(OUTPUT_DIR, run_context)
    print(f"rows={len(out)}")
    print(f"publication_details={len(detail_df)}")
    print(f"output={OUTPUT_PATH.resolve()}")
    print(out["学术作者匹配状态"].value_counts().to_string())


if __name__ == "__main__":
    main()
