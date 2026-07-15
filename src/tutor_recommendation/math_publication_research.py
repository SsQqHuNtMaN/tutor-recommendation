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
from .publication_evidence import PublicationRecord, canonicalize_publications
from .publication_identity import (
    PUBLICATION_IDENTITY_OVERRIDES_PATH,
    build_publication_identity_seed,
    load_publication_identity_overrides,
)
from .ranking_policy import PROFILE, direction_groups_for_keywords, evaluate_teacher, score_text, unique_join
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


def resolve_stage_output_dir(formal_output_dir: Path, shadow_root: str = "") -> Path:
    if not shadow_root:
        return formal_output_dir
    root = Path(shadow_root).expanduser().resolve()
    if "_shadow" not in {part.casefold() for part in root.parts}:
        raise RuntimeError("TUTOR_MATH_SHADOW_ROOT must point inside a directory named _shadow")
    return root / SCHOOL_SLUG / COLLEGE_SLUG


STAGE_OUTPUT_DIR = resolve_stage_output_dir(
    OUTPUT_DIR,
    os.environ.get("TUTOR_MATH_SHADOW_ROOT", "").strip(),
)
OUTPUT_PATH = STAGE_OUTPUT_DIR / f"{OUTPUT_PREFIX}_publications.xlsx"
CACHE_DIR = STAGE_OUTPUT_DIR / "math_publication_cache"
AUDIT_DIR = STAGE_OUTPUT_DIR / "math_publication_audit"
SHADOW_CACHE_READ_DIR_TEXT = os.environ.get("TUTOR_PUBLICATION_CACHE_READ_DIR", "").strip()
SHADOW_CACHE_READ_DIR = Path(SHADOW_CACHE_READ_DIR_TEXT).expanduser().resolve() if SHADOW_CACHE_READ_DIR_TEXT else None
if SHADOW_CACHE_READ_DIR is not None and "_shadow" not in {
    part.casefold() for part in SHADOW_CACHE_READ_DIR.parts
}:
    raise RuntimeError("TUTOR_PUBLICATION_CACHE_READ_DIR must point inside a directory named _shadow")
CACHE_VERSION = "2026-07-14-v5-identity-discovery"
CACHEABLE_PUBLICATION_STATUSES = {
    "success",
    "no_record",
    "no_recent_record",
    "no_candidate",
    "identity_uncertain",
    "identity_confirmed",
    "identity_probable",
    "identity_rejected",
}

RELEVANCE_LABEL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "formal_math_reasoning",
        ("formal mathematics", "formalized mathematics", "theorem proving", "automated reasoning", "形式化数学", "定理证明"),
    ),
    (
        "scientific_machine_learning",
        ("scientific machine learning", "physics-informed", "neural operator", "科学机器学习", "物理信息神经"),
    ),
    (
        "statistical_machine_learning",
        ("statistical learning", "machine learning theory", "learning theory", "high-dimensional statistics", "统计学习", "机器学习理论"),
    ),
    (
        "privacy_preserving_learning",
        ("federated learning", "differential privacy", "privacy-preserving", "联邦学习", "差分隐私", "隐私保护"),
    ),
    (
        "distributed_learning",
        ("distributed learning", "decentralized learning", "federated learning", "分布式学习", "去中心化学习", "联邦学习"),
    ),
)
OPTIMIZATION_TERMS = (
    "optimization",
    "optimisation",
    "mathematical programming",
    "最优化",
    "优化",
    "数学规划",
)
LEARNING_TERMS = ("machine learning", " learning", "neural", "人工智能", "机器学习", "学习")


def _cache_path(source: str, row: dict[str, Any], *, discovery_only: bool = False) -> Path:
    identity = str(row.get(TEACHER_ID_COLUMN) or row.get("姓名") or "unknown")
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in identity)
    suffix = ".identity.json" if discovery_only else ".json"
    return CACHE_DIR / source / f"{safe}{suffix}"


def _collect_cached(
    adapter: Any,
    row: dict[str, Any],
    *,
    discovery_only: bool = False,
) -> dict[str, Any]:
    path = _cache_path(adapter.source, row, discovery_only=discovery_only)
    relevant = {
        key: str(row.get(key) or "")
        for key in (
            "姓名",
            "英文姓名",
            "英文姓名别名",
            "教师主页链接",
            "个人主页",
            "ORCID",
            "OpenAlex作者ID",
            "zbMATH作者ID",
            "DBLP PID",
            "拒绝OpenAlex作者ID",
            "拒绝zbMATH作者ID",
            "已知论文题名",
            "已知合作者",
            "论文身份机构",
            "论文身份审核状态",
            "论文身份种子哈希",
            "官方论文列表",
            "官方论文来源",
        )
    }
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "mode": "identity" if discovery_only else "works",
                "adapter_version": str(getattr(adapter, "cache_version", "unknown")),
                "fields": relevant,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    cache_paths = [path]
    if SHADOW_CACHE_READ_DIR is not None:
        cache_paths.append(SHADOW_CACHE_READ_DIR / adapter.source / path.name)
    for candidate_path in cache_paths:
        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
            if (
                payload.get("version") == CACHE_VERSION
                and payload.get("window") == [START_YEAR, END_YEAR]
                and payload.get("input_hash") == input_hash
                and isinstance(payload.get("result"), dict)
                and payload["result"].get("status") in CACHEABLE_PUBLICATION_STATUSES
            ):
                if candidate_path != path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temp = path.with_suffix(".tmp")
                    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    temp.replace(path)
                return payload["result"]
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
    result = adapter.collect(
        row,
        start_year=START_YEAR,
        end_year=END_YEAR,
        discovery_only=discovery_only,
    ).to_dict()
    if result.get("status") in CACHEABLE_PUBLICATION_STATUSES:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "version": CACHE_VERSION,
                    "adapter_version": str(getattr(adapter, "cache_version", "unknown")),
                    "window": [START_YEAR, END_YEAR],
                    "input_hash": input_hash,
                    "result": result,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)
    return result


def _accepted_works(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[PublicationRecord] = []
    for result in results:
        if result.get("status") != "success":
            continue
        if result.get("source") != "official" and result.get("confidence") not in {"high", "medium"}:
            continue
        for work in result.get("works") or []:
            try:
                records.append(PublicationRecord.from_dict(work))
            except (TypeError, ValueError):
                continue
    return [work.to_dict() for work in canonicalize_publications(records)]


def publication_relevance_labels(work: dict[str, Any], *, profile: Any = PROFILE) -> tuple[str, ...]:
    """Return deterministic descriptive labels; labels never change ranking by themselves."""
    title = str(work.get("title") or "")
    auxiliary = " ".join(
        [
            *(str(value) for value in work.get("classifications") or []),
            *(str(value) for value in work.get("topics") or []),
        ]
    )
    text = f"{title} {auxiliary}".casefold()
    _, matched_keywords = score_text(title, profile=profile, max_terms=12)
    labels = [label for label, terms in RELEVANCE_LABEL_RULES if any(term.casefold() in text for term in terms)]
    has_optimization = any(term.casefold() in text for term in OPTIMIZATION_TERMS)
    has_learning = any(term.casefold() in text for term in LEARNING_TERMS)
    if has_optimization and has_learning:
        labels.append("optimization_for_ai")
    elif has_optimization:
        labels.append("mathematical_optimization")
    if not matched_keywords:
        labels.append("uncertain")
    return tuple(dict.fromkeys(labels))


def publication_profile_keywords(work: dict[str, Any], *, profile: Any = PROFILE) -> tuple[str, ...]:
    # Classifications/topics remain explanatory metadata and cannot create a profile keyword match.
    _, matched = score_text(str(work.get("title") or ""), profile=profile, max_terms=12)
    return tuple(matched)


def _evidence_columns(results: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = _accepted_works(results)
    external = [item for item in results if item.get("source") != "official"]
    identified = [
        item
        for item in external
        if item.get("status") in {"success", "no_recent_record"}
        and item.get("confidence") in {"high", "medium"}
    ]
    identified.sort(key=lambda item: {"high": 2, "medium": 1}.get(item.get("confidence"), 0), reverse=True)
    official = next((item for item in results if item.get("source") == "official" and item.get("status") == "success"), {})
    best = identified[0] if identified else official
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
    ai_group_names = {"ai_methods", "math_ai_bridges"}
    ai_matches = [
        keyword
        for keyword in matched_keywords
        if set(direction_groups_for_keywords([keyword], PROFILE)) & ai_group_names
    ]
    math_matches = [keyword for keyword in matched_keywords if keyword not in ai_matches]
    relevance_labels = list(
        dict.fromkeys(label for work in accepted for label in publication_relevance_labels(work))
    )
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
        "论文相关性标签": unique_join(relevance_labels, "；"),
        "近五年代表论文": "；".join(str(work.get("title") or "") for work in accepted[:5]),
        "论文证据来源": unique_join(
            [source for work in accepted for source in work.get("sources") or []], "；"
        ),
        "论文证据摘要": reasons,
    }


def _safe_score(value: Any) -> float:
    try:
        score = float(value or 0)
        return 0.0 if pd.isna(score) else score
    except (TypeError, ValueError):
        return 0.0


def _discovery_allows_deep_query(result: dict[str, Any]) -> bool:
    return result.get("status") in {"identity_confirmed", "identity_probable"} and result.get(
        "confidence"
    ) in {"high", "medium"}


def _row_with_discovered_source_id(row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    author_id = str(result.get("author_id") or "")
    if result.get("source") == "zbmath" and author_id:
        updated["zbMATH作者ID"] = author_id
    elif result.get("source") == "openalex" and author_id:
        updated["OpenAlex作者ID"] = author_id
    return updated


def _identity_decision(result: dict[str, Any]) -> str:
    status = str(result.get("status") or "")
    confidence = str(result.get("confidence") or "")
    if status in {"identity_confirmed"} or (
        status in {"success", "no_recent_record"} and confidence == "high"
    ):
        return "confirmed"
    if status in {"identity_probable"} or (
        status in {"success", "no_recent_record"} and confidence == "medium"
    ):
        return "probable"
    if status == "identity_uncertain":
        return "review"
    if status == "identity_rejected":
        return "rejected"
    return "unresolved"


def _source_health(status: str) -> str:
    if status == "not_configured":
        return "not_configured"
    if status in {"request_failed", "schema_changed", "terms_required"}:
        return "degraded"
    return "ok"


def _stable_json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(
        json.dumps(_json_safe(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    content = "".join(
        json.dumps(_json_safe(row), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        for row in rows
    )
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def main() -> None:
    if not INPUT_PATH.is_file():
        raise FileNotFoundError(f"未找到数学文献阶段输入表：{INPUT_PATH}")
    input_paths = [INPUT_PATH]
    if PUBLICATION_IDENTITY_OVERRIDES_PATH.is_file():
        input_paths.append(PUBLICATION_IDENTITY_OVERRIDES_PATH)
    session = requests.Session()
    session.trust_env = False
    adapters = [OfficialPublicationAdapter(), ZbMathAdapter(session), OpenAlexAdapter(session)]
    run_context = create_run_context(
        "math_publications",
        TARGET_KEY,
        input_paths,
        recent_year_count=WINDOW_YEARS,
        stage_metadata={
            "publication_cache_version": CACHE_VERSION,
            "enabled_sources": [adapter.source for adapter in adapters],
            "source_adapter_versions": {
                adapter.source: str(getattr(adapter, "cache_version", "unknown")) for adapter in adapters
            },
            "identity_override_configured": PUBLICATION_IDENTITY_OVERRIDES_PATH.is_file(),
            "source_policy": "official+zbmath_primary;openalex_optional;arxiv_auxiliary",
        },
    )
    assert_stage_profile_compatible(OUTPUT_DIR, "first_pass", run_context)
    df = pd.read_excel(INPUT_PATH, sheet_name="全量教师名录")
    identity_overrides = load_publication_identity_overrides()
    output_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    author_candidates: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []
    query_plans: list[dict[str, Any]] = []
    for _, series in df.iterrows():
        row = series.to_dict()
        identity_seed = build_publication_identity_seed(
            row,
            school_slug=SCHOOL_SLUG,
            college_slug=COLLEGE_SLUG,
            overrides=identity_overrides,
        )
        query_row = {**row, **identity_seed.query_fields()}
        row.update(identity_seed.query_fields())
        should_query_external = bool(str(row.get("显式核心锚点") or "") == "是" or _safe_score(row.get("匹配分")) > 0)
        query_plans.append(
            {
                TEACHER_ID_COLUMN: row.get(TEACHER_ID_COLUMN, ""),
                "教师姓名": row.get("姓名", ""),
                "身份种子哈希": identity_seed.fingerprint,
                "查询姓名": list(identity_seed.query_names()),
                "启用来源": [adapter.source for adapter in adapters],
                "画像或官方锚点允许深查": should_query_external,
                "稳定来源ID": {
                    "openalex": identity_seed.openalex_id,
                    "zbmath": identity_seed.zbmath_author_id,
                    "dblp": identity_seed.dblp_pid,
                },
            }
        )
        results: list[dict[str, Any]] = []
        for adapter in adapters:
            if adapter.source != "official" and not should_query_external:
                discovery = _collect_cached(adapter, query_row, discovery_only=True)
                if _discovery_allows_deep_query(discovery):
                    result = _collect_cached(
                        adapter,
                        _row_with_discovered_source_id(query_row, discovery),
                    )
                else:
                    result = discovery
            else:
                result = _collect_cached(adapter, query_row)
            results.append(result)
        accepted_works = _accepted_works(results)
        row.update(_evidence_columns(results))
        row["论文身份决策哈希"] = _stable_json_hash(
            [
                {
                    "source": result.get("source"),
                    "status": result.get("status"),
                    "confidence": result.get("confidence"),
                    "author_id": result.get("author_id"),
                }
                for result in results
            ]
        )
        row["论文来源报告哈希"] = _stable_json_hash(
            [
                {
                    "source": result.get("source"),
                    "status": result.get("status"),
                    "metadata": result.get("metadata") or {},
                }
                for result in results
            ]
        )
        row["规范论文摘要哈希"] = _stable_json_hash(
            [
                {
                    "canonical_id": work.get("canonical_id"),
                    "year": work.get("year"),
                    "sources": work.get("sources") or [],
                }
                for work in accepted_works
            ]
        )
        decision = evaluate_teacher(row, publication={
            "status": row.get("学术作者匹配状态", ""),
            "confidence": row.get("学术作者匹配置信度", ""),
            "keywords": row.get("近五年关键词", ""),
            "titles": row.get("近五年代表论文", ""),
            "classifications": row.get("主要数学分类", ""),
        })
        row.update(decision.to_columns())
        output_rows.append(row)
        identity_status = (
            "confirmed"
            if row.get("学术作者匹配置信度") == "high"
            else "probable"
            if row.get("学术作者匹配置信度") == "medium"
            else "official"
        )
        for work in accepted_works:
            source_ids = list(work.get("source_ids") or [])
            id_by_source = {
                value.split(":", 1)[0]: value.split(":", 1)[1]
                for value in source_ids
                if ":" in value
            }
            details.append(
                {
                    TEACHER_ID_COLUMN: row.get(TEACHER_ID_COLUMN, ""),
                    "姓名": row.get("姓名", ""),
                    "来源": unique_join(work.get("sources") or [], "；"),
                    "作者身份置信度": row.get("学术作者匹配置信度", "") or "high",
                    "是否计入匹配": "是",
                    "年份": work.get("year", ""),
                    "题名": work.get("title", ""),
                    "DOI": work.get("doi", ""),
                    "分类": unique_join(work.get("classifications") or [], "；"),
                    "主题": unique_join(work.get("topics") or [], "；"),
                    "命中画像词": unique_join(publication_profile_keywords(work), "；"),
                    "相关性标签": unique_join(publication_relevance_labels(work), "；"),
                    "证据URL": work.get("url", ""),
                    "规范论文ID": work.get("canonical_id", ""),
                    "来源IDs": unique_join(source_ids, "；"),
                    "合并来源": unique_join(work.get("sources") or [], "；"),
                    "作者身份状态": identity_status,
                    "是否计分": "是",
                    "拒绝原因": "",
                    "arXiv ID": work.get("arxiv_id", ""),
                    "OpenAlex ID": id_by_source.get("openalex", ""),
                    "zbMATH ID": id_by_source.get("zbmath", ""),
                    "DBLP Key": id_by_source.get("dblp", ""),
                    "期刊会议": work.get("venue", ""),
                    "发表日期": work.get("publication_date", ""),
                    "是否预印本": "是" if work.get("is_preprint") else "否",
                    "追溯记录ID": unique_join(
                        [record.get("raw_ref") for record in work.get("records") or []], "；"
                    ),
                }
            )
        for result in results:
            metadata = result.get("metadata") or {}
            source_health = (
                "degraded" if metadata.get("truncated") else _source_health(str(result.get("status") or ""))
            )
            source_reports.append(
                {
                    TEACHER_ID_COLUMN: row.get(TEACHER_ID_COLUMN, ""),
                    "教师姓名": row.get("姓名", ""),
                    "来源": result.get("source", ""),
                    "阶段": "identity_discovery" if metadata.get("discovery_only") else "works",
                    "状态": result.get("status", ""),
                    "来源健康度": source_health,
                    "原始记录数": metadata.get("raw_count", len(result.get("works") or [])),
                    "接受记录数": metadata.get(
                        "accepted_count",
                        len(result.get("works") or []) if result.get("status") == "success" else 0,
                    ),
                    "拒绝记录数": max(
                        0,
                        int(metadata.get("raw_count", len(result.get("works") or [])) or 0)
                        - int(metadata.get("accepted_count", 0) or 0),
                    ),
                    "页数": metadata.get("pages", ""),
                    "是否截断": "是" if metadata.get("truncated") else "否",
                    "错误类型": (
                        result.get("status", "")
                        if source_health == "degraded" and not metadata.get("truncated")
                        else ""
                    ),
                    "降级说明": "达到来源分页上限，结果可能截断" if metadata.get("truncated") else "",
                    "原因": result.get("reason", ""),
                    "缓存策略版本": CACHE_VERSION,
                }
            )
            if result.get("source") != "official":
                candidates = list(result.get("author_candidates") or [])
                if not candidates:
                    candidates = [
                        {
                            "author_id": result.get("author_id", ""),
                            "author_url": result.get("author_url", ""),
                            "orcid": result.get("orcid", ""),
                            "decision": _identity_decision(result),
                            "signals": [result.get("reason", "")],
                            "conflicts": (
                                [result.get("reason", "")]
                                if result.get("status") == "identity_rejected"
                                else []
                            ),
                        }
                    ]
                for candidate_rank, candidate in enumerate(candidates, start=1):
                    candidate_decision = candidate.get("decision") or _identity_decision(result)
                    author_candidates.append(
                        {
                            TEACHER_ID_COLUMN: row.get(TEACHER_ID_COLUMN, ""),
                            "教师姓名": row.get("姓名", ""),
                            "来源": result.get("source", ""),
                            "候选作者ID": candidate.get("author_id", ""),
                            "候选作者姓名": candidate.get("display_name", ""),
                            "候选作者URL": candidate.get("author_url", ""),
                            "ORCID": candidate.get("orcid", ""),
                            "候选机构": unique_join(candidate.get("affiliations") or [], "；"),
                            "候选状态": result.get("status", ""),
                            "身份置信度": result.get("confidence", ""),
                            "候选决策": candidate_decision,
                            "候选排名": candidate_rank,
                            "是否需人工复核": (
                                "是"
                                if candidate_rank == 1
                                and (
                                    candidate_decision == "rejected"
                                    or (
                                    candidate_decision in {"review", "unresolved"}
                                    and should_query_external
                                    and _safe_score(candidate.get("score")) > 4
                                    )
                                )
                                else "否"
                            ),
                            "候选得分": candidate.get("score", ""),
                            "候选数量": metadata.get("candidate_count", ""),
                            "证据信号": unique_join(candidate.get("signals") or [], "；"),
                            "冲突原因": unique_join(candidate.get("conflicts") or [], "；"),
                            "候选说明": candidate.get("reason", ""),
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
    author_candidates_df = pd.DataFrame(author_candidates)
    source_report_df = pd.DataFrame(source_reports)
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
    STAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        priority.to_excel(writer, sheet_name="优先套磁名单", index=False)
        out.to_excel(writer, sheet_name="全量教师名录", index=False)
        detail_df.to_excel(writer, sheet_name="数学文献近五年明细", index=False)
        author_candidates_df.to_excel(writer, sheet_name="学术作者候选", index=False)
        source_report_df.to_excel(writer, sheet_name="论文来源报告", index=False)
        source.to_excel(writer, sheet_name="匹配依据", index=False)
    style_workbook(OUTPUT_PATH)
    _write_json(AUDIT_DIR / "publication_query_plan.json", query_plans)
    _write_json(AUDIT_DIR / "publication_source_report.json", source_reports)
    _write_jsonl(AUDIT_DIR / "publication_author_candidates.jsonl", author_candidates)
    _write_jsonl(
        AUDIT_DIR / "publication_review_queue.jsonl",
        [item for item in author_candidates if item.get("是否需人工复核") == "是"],
    )
    _write_jsonl(AUDIT_DIR / "merged_publications.jsonl", details)
    write_stage_manifest(STAGE_OUTPUT_DIR, run_context)
    print(f"rows={len(out)}")
    print(f"publication_details={len(detail_df)}")
    print(f"output={OUTPUT_PATH.resolve()}")
    print(f"shadow={'yes' if STAGE_OUTPUT_DIR != OUTPUT_DIR else 'no'}")
    print(out["学术作者匹配状态"].value_counts().to_string())


if __name__ == "__main__":
    main()
