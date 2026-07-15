from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .student_profile import PROFILE, StudentProfile


POLICY_VERSION = "2026.07.15-math-ai-exploration-v3"
SCHEMA_VERSION = 5
CONSIDER_THRESHOLD = 24
STRONG_THRESHOLD = 44
DIRECTION_GROUP_LABELS = {
    "math_methods": "数学方法",
    "statistics_methods": "统计方法",
    "ai_methods": "AI方法",
    "math_ai_bridges": "数学-AI桥接",
}

EXPLICIT_ANCHOR_COLUMNS = (
    "研究方向",
    "导师信息库研究方向",
    "团队PDF证据",
)
OFFICIAL_CONTEXT_COLUMNS = EXPLICIT_ANCHOR_COLUMNS + (
    "个人简介摘要",
    "名录研究所",
    "主页研究所",
    "官方系别",
)
DIRECTION_CUE_PATTERN = re.compile(
    r"研究方向|研究兴趣|研究领域|主要从事|主要聚焦|当前主要|research interests?|research focuses?|focus(?:ed|es)? on",
    re.I,
)


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ")
    if text.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", text).strip()


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def keyword_in_text(keyword: str, text_lower: str) -> bool:
    keyword_lower = keyword.lower().strip()
    if not keyword_lower:
        return False
    if has_cjk(keyword_lower):
        return keyword_lower in text_lower
    special_patterns = {
        "robot": r"\brobots?\b|\brobotics?\b",
        "robotic": r"\brobotic(s)?\b",
        "agent": r"\bagents?\b",
        "llm": r"\bllms?\b",
        "rl": r"\brl\b",
        "nlp": r"\bnlp\b",
        "3d": r"\b3d\b",
        "video": r"\bvideos?\b",
        "control": r"\bcontrol(s|led|ling)?\b",
        "policy": r"\bpolic(y|ies)\b",
    }
    if keyword_lower in special_patterns:
        return bool(re.search(special_patterns[keyword_lower], text_lower))
    pattern = re.escape(keyword_lower).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text_lower))


def _deduplicate_overlapping_matches(matches: list[tuple[str, int]]) -> list[tuple[str, int]]:
    selected: list[tuple[str, int]] = []
    for keyword, weight in sorted(matches, key=lambda item: (len(item[0]), item[1]), reverse=True):
        lower = keyword.lower()
        if any(lower in kept.lower() and has_cjk(lower) == has_cjk(kept) for kept, _ in selected):
            continue
        selected.append((keyword, weight))
    return selected


def score_text(
    text: Any,
    *,
    profile: StudentProfile = PROFILE,
    max_terms: int = 4,
) -> tuple[int, list[str]]:
    text_lower = norm_text(text).lower()
    matches = [
        (keyword, weight)
        for keyword, weight in profile.keyword_weights
        if weight > 0 and keyword_in_text(keyword, text_lower)
    ]
    matched_by_key = {keyword.lower(): (keyword, weight) for keyword, weight in matches}
    selected: list[tuple[str, int]] = []
    grouped_aliases: set[str] = set()
    for group in profile.concept_alias_groups:
        group_matches = [matched_by_key[alias.lower()] for alias in group if alias.lower() in matched_by_key]
        if not group_matches:
            continue
        selected.append(max(group_matches, key=lambda item: (item[1], len(item[0]))))
        grouped_aliases.update(alias.lower() for alias in group)
    selected.extend((keyword, weight) for keyword, weight in matches if keyword.lower() not in grouped_aliases)
    selected = _deduplicate_overlapping_matches(selected)[:max_terms]
    return sum(weight for _, weight in selected), [keyword for keyword, _ in selected]


def unique_join(values: Iterable[Any], sep: str = "; ") -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = norm_text(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return sep.join(output)


@dataclass(frozen=True)
class RankingDecision:
    score: int
    level: str
    can_contact: str
    explicit_anchor: bool
    matched_keywords: tuple[str, ...]
    matched_direction_groups: tuple[str, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    breakdown: dict[str, int]

    def to_columns(self) -> dict[str, Any]:
        return {
            "推荐等级": self.level,
            "是否建议套磁": self.can_contact,
            "匹配分": self.score,
            "命中关键词": unique_join(self.matched_keywords),
            "画像方向分组": unique_join(
                DIRECTION_GROUP_LABELS.get(group, group) for group in self.matched_direction_groups
            ),
            "推荐理由": "；".join(self.reasons),
            "显式核心锚点": "是" if self.explicit_anchor else "否",
            "评分规则版本": POLICY_VERSION,
            "官方证据分": self.breakdown.get("official", 0),
            "DBLP证据分": self.breakdown.get("dblp", 0),
            "论文证据分": self.breakdown.get("publication", 0),
            "arXiv证据分": self.breakdown.get("arxiv", 0),
            "网页证据分": self.breakdown.get("web", 0),
            "WebSearch证据分": self.breakdown.get("web_search", 0),
            "评分警告": "；".join(self.warnings),
        }


def _row_text(row: Any, columns: Iterable[str]) -> str:
    return " ".join(norm_text(row.get(column, "")) for column in columns)


def _explicit_anchor_text(row: Any) -> str:
    parts = [_row_text(row, EXPLICIT_ANCHOR_COLUMNS)]
    biography = norm_text(row.get("个人简介摘要", ""))
    if biography:
        sentences = re.split(r"(?<=[。！？.!?；;])\s*", biography)
        for index, sentence in enumerate(sentences):
            if not DIRECTION_CUE_PATTERN.search(sentence):
                continue
            excerpt = " ".join(sentences[index : index + 2])[:600]
            parts.append(excerpt)
    return " ".join(parts)


def _core_matches(text: str, profile: StudentProfile) -> list[str]:
    lower = text.lower()
    return sorted(term for term in profile.high_signal_terms if keyword_in_text(term, lower))


def direction_groups_for_keywords(keywords: Iterable[Any], profile: StudentProfile = PROFILE) -> tuple[str, ...]:
    lowered = {norm_text(keyword).lower() for keyword in keywords if norm_text(keyword)}
    return tuple(
        group_name
        for group_name, terms in profile.direction_term_groups.items()
        if lowered & set(terms)
    )


def _institute_bonus(row: Any, profile: StudentProfile) -> tuple[int, list[str]]:
    text = _row_text(row, ("名录研究所", "主页研究所", "官方系别")).lower()
    matches = [(keyword, bonus) for keyword, bonus in profile.institute_bonus if bonus > 0 and keyword.lower() in text]
    matches = _deduplicate_overlapping_matches(matches)
    return min(sum(bonus for _, bonus in matches), 10), [keyword for keyword, _ in matches]


def _confidence(value: Any) -> str:
    return norm_text(value).lower()


def _publication_source_statuses(value: Any) -> set[str]:
    statuses: set[str] = set()
    for raw_part in norm_text(value).split(";"):
        part = raw_part.strip()
        if not part:
            continue
        state = part.split(":", 1)[1] if ":" in part else part
        statuses.add(state.split("/", 1)[0].strip().lower())
    return statuses


def evaluate_teacher(
    row: Any,
    *,
    profile: StudentProfile = PROFILE,
    dblp: dict[str, Any] | None = None,
    publication: dict[str, Any] | None = None,
    arxiv: dict[str, Any] | None = None,
    web: dict[str, Any] | None = None,
    web_search: dict[str, Any] | None = None,
) -> RankingDecision:
    dblp = dblp or {}
    publication = publication or {}
    arxiv = arxiv or {}
    web = web or {}
    web_search = web_search or {}

    explicit_text = _explicit_anchor_text(row)
    official_text = _row_text(row, OFFICIAL_CONTEXT_COLUMNS)
    explicit_core = _core_matches(explicit_text, profile)
    excluded_matches = sorted(
        term for term in profile.excluded_terms if keyword_in_text(term, official_text.lower())
    )
    official_score, official_keywords = score_text(official_text, profile=profile)
    bonus_score, bonus_keywords = _institute_bonus(row, profile)
    official_score = min(official_score + (bonus_score if explicit_core else 0), 80)

    breakdown = {
        "official": official_score,
        "dblp": 0,
        "publication": 0,
        "arxiv": 0,
        "web": 0,
        "web_search": 0,
    }
    matched = list(official_keywords) + bonus_keywords
    reasons: list[str] = []
    warnings: list[str] = []
    if excluded_matches:
        warnings.append(f"当前画像排除方向命中：{unique_join(excluded_matches[:4])}")

    dblp_confidence = _confidence(dblp.get("confidence") or row.get("DBLP匹配置信度", ""))
    dblp_text = " ".join(
        [
            norm_text(dblp.get("keywords") or row.get("DBLP近三年关键词", "")),
            norm_text(dblp.get("titles") or row.get("DBLP近三年代表论文", "")),
        ]
    )
    dblp_raw, dblp_keywords = score_text(dblp_text, profile=profile)
    if explicit_core and dblp_confidence == "高":
        breakdown["dblp"] = min(round(dblp_raw * 0.45), 24)
        matched.extend(dblp_keywords)
        if breakdown["dblp"]:
            reasons.append("高置信DBLP近三年论文增强了已确认的核心方向")
    elif dblp_raw:
        warnings.append("DBLP存在相关词，但身份置信度或官方核心锚点不足，未计入排名")

    publication_confidence = _confidence(
        publication.get("confidence") or row.get("学术作者匹配置信度", "")
    )
    publication_status = norm_text(
        publication.get("status") or row.get("学术作者匹配状态", "")
    ).lower()
    publication_text = " ".join(
        [
            norm_text(publication.get("keywords") or row.get("近五年关键词", "")),
            norm_text(publication.get("titles") or row.get("近五年代表论文", "")),
            norm_text(publication.get("classifications") or row.get("主要数学分类", "")),
        ]
    )
    publication_raw, publication_keywords = score_text(publication_text, profile=profile, max_terms=8)
    publication_confirmed = (
        publication_confidence in {"high", "medium", "高", "中"}
        and "success" in _publication_source_statuses(publication_status)
    )
    if explicit_core and publication_confirmed:
        breakdown["publication"] = min(round(publication_raw * 0.35), 18)
        matched.extend(publication_keywords)
        if breakdown["publication"]:
            reasons.append("经身份消歧确认的近年数学论文增强了官网核心方向")
    elif publication_raw:
        warnings.append("数学论文存在相关词，但作者身份或官方核心锚点不足，未计入排名")

    arxiv_confidence = _confidence(arxiv.get("置信度") or row.get("arXiv置信度", ""))
    arxiv_text = " ".join(
        [
            norm_text(arxiv.get("关键词") or row.get("arXiv关键词", "")),
            " ".join(norm_text(item.get("title")) for item in arxiv.get("论文", [])),
        ]
    )
    arxiv_raw, arxiv_keywords = score_text(arxiv_text, profile=profile)
    if explicit_core and arxiv_confidence in {"高", "中-dblp交叉确认"}:
        breakdown["arxiv"] = min(round(arxiv_raw * 0.2), 10)
        matched.extend(arxiv_keywords)
        if breakdown["arxiv"]:
            reasons.append("经身份交叉确认的arXiv论文提供补充证据")
    elif arxiv_raw:
        warnings.append("arXiv仅按姓名或方向命中，未作为作者身份确认或排名依据")

    web_status = norm_text(web.get("状态") or row.get("网页状态", ""))
    web_text = " ".join(
        [
            norm_text(web.get("关键词") or row.get("网页关键词", "")),
            " ".join(norm_text(item) for item in web.get("证据", [])),
        ]
    )
    web_raw, web_keywords = score_text(web_text, profile=profile)
    if explicit_core and web_status == "已抓取":
        breakdown["web"] = min(round(web_raw * 0.18), 8)
        matched.extend(web_keywords)
        if breakdown["web"]:
            reasons.append("已知教师或个人主页补充了核心方向证据")

    search_confidence = norm_text(web_search.get("WebSearch置信度") or row.get("WebSearch置信度", ""))
    search_status = norm_text(web_search.get("WebSearch状态") or row.get("WebSearch状态", ""))
    search_reviewed = bool(web_search.get("人工确认")) or search_status.startswith("人工确认")
    search_text = " ".join(
        [
            norm_text(web_search.get("WebSearch关键词") or row.get("WebSearch关键词", "")),
            norm_text(web_search.get("WebSearch代表证据") or row.get("WebSearch代表证据", "")),
        ]
    )
    search_raw, search_keywords = score_text(search_text, profile=profile)
    if explicit_core and search_reviewed and search_confidence in {"高", "中"}:
        breakdown["web_search"] = min(round(search_raw * 0.15), 6)
        matched.extend(search_keywords)
        if breakdown["web_search"]:
            reasons.append("人工确认的WebSearch来源提供补充证据")
    elif search_raw:
        warnings.append("自动WebSearch仅用于发现来源，未直接影响排名")

    score = sum(breakdown.values())
    matched_direction_groups = direction_groups_for_keywords(dict.fromkeys(matched), profile)
    auxiliary_score = sum(value for key, value in breakdown.items() if key != "official")
    grouped_strong_evidence = (
        not profile.direction_term_groups
        or len(matched_direction_groups) >= 2
        or auxiliary_score > 0
    )
    excluded_without_primary = bool(excluded_matches) and not explicit_core
    if excluded_without_primary:
        score = min(score, CONSIDER_THRESHOLD - 1)
        level = "暂不优先"
        can_contact = "否"
        reasons.append("教师当前方向命中画像明确排除的方向，且缺少更高优先级核心锚点")
    elif not explicit_core:
        score = min(score, CONSIDER_THRESHOLD - 1)
        level = "暂不优先"
        can_contact = "否"
        reasons.append("官方名录、教师主页或官方PDF中缺少当前画像的显式核心方向锚点")
    elif score >= STRONG_THRESHOLD and grouped_strong_evidence:
        level = "强烈建议"
        can_contact = "是"
        reasons.insert(0, f"官方方向明确命中核心方向：{unique_join(explicit_core[:4])}")
    elif score >= CONSIDER_THRESHOLD:
        level = "可以考虑"
        can_contact = "是"
        reasons.insert(0, f"官方方向命中核心方向：{unique_join(explicit_core[:4])}")
    else:
        level = "暂不优先"
        can_contact = "否"
        reasons.append("虽有核心方向词，但当前证据强度尚未达到优先名单门槛")
    if score >= STRONG_THRESHOLD and not grouped_strong_evidence:
        level = "可以考虑"
        can_contact = "是"
        reasons.insert(0, f"官方方向命中核心方向：{unique_join(explicit_core[:4])}")
        reasons.append("当前命中集中在单一画像方向组且缺少可信辅助证据，暂不提升为强烈建议")

    if not reasons:
        reasons.append("当前可核查证据与学生画像关联较弱")
    return RankingDecision(
        score=score,
        level=level,
        can_contact=can_contact,
        explicit_anchor=bool(explicit_core),
        matched_keywords=tuple(dict.fromkeys(matched)),
        matched_direction_groups=matched_direction_groups,
        reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(dict.fromkeys(warnings)),
        breakdown=breakdown,
    )


def legacy_dblp_evidence(row: Any, summary: dict[str, Any] | None = None, match: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = summary or {}
    match = match or {}
    return {
        "confidence": match.get("confidence") or row.get("DBLP匹配置信度", ""),
        "keywords": summary.get("keywords") or row.get("DBLP近三年关键词", ""),
        "titles": summary.get("titles") or row.get("DBLP近三年代表论文", ""),
    }


def legacy_publication_evidence(row: Any) -> dict[str, Any]:
    return {
        "status": row.get("学术作者匹配状态", ""),
        "confidence": row.get("学术作者匹配置信度", ""),
        "keywords": row.get("近五年关键词", ""),
        "titles": row.get("近五年代表论文", ""),
        "classifications": row.get("主要数学分类", ""),
    }


def evaluate_legacy_row(
    row: Any,
    *,
    profile: StudentProfile = PROFILE,
    web_search_override: dict[str, Any] | None = None,
) -> RankingDecision:
    arxiv = {
        "置信度": row.get("arXiv置信度", ""),
        "关键词": row.get("arXiv关键词", ""),
        "论文": [],
    }
    web = {
        "状态": row.get("网页状态", ""),
        "关键词": row.get("网页关键词", ""),
        "证据": [part for part in norm_text(row.get("网页近三年/发表证据", "")).split("；") if part],
    }
    web_search = web_search_override or {
        "WebSearch状态": row.get("WebSearch状态", ""),
        "WebSearch置信度": row.get("WebSearch置信度", ""),
        "WebSearch关键词": row.get("WebSearch关键词", ""),
        "WebSearch代表证据": row.get("WebSearch代表证据", ""),
    }
    return evaluate_teacher(
        row,
        profile=profile,
        dblp=legacy_dblp_evidence(row),
        publication=legacy_publication_evidence(row),
        arxiv=arxiv,
        web=web,
        web_search=web_search,
    )
