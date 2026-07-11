from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .teacher_research_completion import style_workbook
from .contact_status import STATUS_COLUMN, apply_contact_statuses
from .migrate_contact_status_column import migrate_workbook
from .student_profile import CORE_TERMS, KEYWORD_WEIGHTS
from .teacher_match_targets import TARGETS, TargetConfig, get_target
from .ranking_policy import evaluate_legacy_row
from .teacher_identity import TEACHER_ID_COLUMN, ensure_teacher_identity
from .cache_utils import configured_max_age_days, read_cached_text
from .run_manifest import create_run_context, recent_years, write_stage_manifest


SEARCH_COLUMNS = [
    "WebSearch状态",
    "WebSearch置信度",
    "WebSearch证据条数",
    "WebSearch关键词",
    "WebSearch代表证据",
    "WebSearch来源URL",
    "WebSearch建议",
]

WEB_SEARCH_DETAIL_COLUMNS = [
    "姓名",
    TEACHER_ID_COLUMN,
    STATUS_COLUMN,
    "学校",
    "学院",
    "WebSearch置信度",
    "查询",
    "来源类型",
    "标题",
    "证据",
    "关键词",
    "来源URL",
    "教师主页链接",
]

RECENT_YEARS = set(recent_years())
DEFAULT_CURATED_WEB_SEARCH_PATH = Path(os.environ.get("CURATED_WEB_SEARCH_PATH", "data/private/web_search_curated.json"))


def compile_term_pattern(terms: list[str] | set[str], fallback: list[str]) -> re.Pattern[str]:
    cleaned = [
        str(term).strip()
        for term in terms
        if str(term).strip() and "请替换" not in str(term) and "placeholder" not in str(term).lower()
    ]
    if not cleaned:
        cleaned = fallback
    pattern = "|".join(re.escape(term) for term in sorted(set(cleaned), key=len, reverse=True))
    return re.compile(pattern, re.I)


SEARCH_RELEVANT_PATTERN = compile_term_pattern(
    [keyword for keyword, weight in KEYWORD_WEIGHTS if weight > 0],
    ["artificial intelligence", "machine learning", "deep learning", "人工智能", "机器学习"],
)
CORE_PATTERN = compile_term_pattern(
    CORE_TERMS,
    ["artificial intelligence", "machine learning", "人工智能", "机器学习"],
)
VENUE_PATTERN = re.compile(
    r"\b(CVPR|ICCV|ECCV|NeurIPS|ICLR|ICML|AAAI|IJCAI|ACL|EMNLP|CoRL|RSS|IROS|ICRA|"
    r"SIGGRAPH|KDD|WWW|WSDM|CIKM|SIGIR|MM|ACM MM|TPAMI|IJCV|TRO|TASE|TMI|MICCAI|"
    r"OSDI|ASPLOS|SOSP|USENIX|CCS|NDSS|S&P)\b",
    re.I,
)
SCHOOL_TERMS = {
    "sjtu": ["上海交通大学", "上海交大", "sjtu", "shanghai jiao tong"],
    "nju": ["南京大学", "nju", "nanjing university"],
    "ruc": ["中国人民大学", "人大", "ruc", "renmin university"],
    "fudan": ["复旦大学", "fudan"],
    "seu": ["东南大学", "seu", "southeast university"],
}
BLOCKED_HOST_PARTS = [
    "baidu.com",
    "bing.com",
    "duckduckgo.com",
    "google.com/search",
    "sogou.com",
    "so.com",
]
TARGET_OFFICIAL_HOST_PARTS = {
    "sjtu": ["sjtu.edu.cn", "sjtu.edu"],
    "nju": ["nju.edu.cn"],
    "ruc": ["ruc.edu.cn"],
    "fudan": ["fudan.edu.cn"],
    "seu": ["seu.edu.cn"],
}

def load_curated_web_search(path: Path = DEFAULT_CURATED_WEB_SEARCH_PATH) -> dict[str, list[dict[str, str]]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    output: dict[str, list[dict[str, str]]] = {}
    for target_key, items in data.items():
        if not isinstance(items, list):
            continue
        rows = [item for item in items if isinstance(item, dict)]
        if rows:
            output[str(target_key)] = rows
    return output


@dataclass
class SearchEvidence:
    name: str
    status: str
    confidence: str
    query: str
    title: str
    snippet: str
    url: str
    source_type: str
    keywords: str


def norm_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\u3000", " ").replace("\xa0", " ")).strip()


def cache_path(cache_dir: Path, key: str, suffix: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.{suffix}"


def fetch_cached(session: requests.Session, url: str, cache_dir: Path, suffix: str, timeout: int = 20) -> str:
    path = cache_path(cache_dir, url, suffix)
    cached = read_cached_text(path, configured_max_age_days("WEB_SEARCH_CACHE_MAX_AGE_DAYS", 7))
    if cached is not None:
        return cached
    response = session.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 teacher-match-web-search/1.0"})
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    path.write_text(response.text, encoding="utf-8", errors="replace")
    return response.text


def clean_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/a"):
        query = parse_qs(parsed.query)
        for key in ("u", "r"):
            if key in query:
                raw = query[key][0]
                if raw.startswith("a1"):
                    raw = raw[2:]
                try:
                    return unquote(raw)
                except Exception:
                    return raw
    return url


def clean_duckduckgo_url(url: str) -> str:
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        if "uddg" in query:
            return unquote(query["uddg"][0])
    return url


def results_contain_quoted_terms(query: str, results: list[dict[str, str]]) -> bool:
    quoted_terms = [term for term in re.findall(r'"([^"]+)"', query) if len(term) >= 2]
    if not quoted_terms:
        return bool(results)
    combined = " ".join(f"{item.get('title', '')} {item.get('snippet', '')} {item.get('url', '')}" for item in results)
    return any(term in combined for term in quoted_terms)


def search_bing(session: requests.Session, query: str, cache_dir: Path) -> list[dict[str, str]]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    html = fetch_cached(session, url, cache_dir, "html", timeout=20)
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for item in soup.select("li.b_algo"):
        link = item.select_one("h2 a[href]")
        if not link:
            continue
        title = norm_text(link.get_text(" ", strip=True))
        href = clean_bing_url(link.get("href", ""))
        snippet = norm_text(item.select_one(".b_caption p").get_text(" ", strip=True) if item.select_one(".b_caption p") else "")
        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet, "query": query})
    return results[:8]


def search_duckduckgo(session: requests.Session, query: str, cache_dir: Path) -> list[dict[str, str]]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    html = fetch_cached(session, url, cache_dir, "html", timeout=20)
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    for item in soup.select(".result"):
        link = item.select_one(".result__a")
        if not link:
            continue
        title = norm_text(link.get_text(" ", strip=True))
        href = clean_duckduckgo_url(link.get("href", ""))
        snippet_node = item.select_one(".result__snippet")
        snippet = norm_text(snippet_node.get_text(" ", strip=True) if snippet_node else "")
        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet, "query": query})
    return results[:8]


def search_web(session: requests.Session, query: str, cache_dir: Path) -> list[dict[str, str]]:
    try:
        results = search_bing(session, query, cache_dir)
        if results and results_contain_quoted_terms(query, results):
            return results
    except Exception:
        pass
    try:
        return search_duckduckgo(session, query, cache_dir)
    except Exception:
        return []


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    meta_parts = [
        norm_text(meta.get("content", ""))
        for meta in soup.find_all("meta")
        if meta.get("content") and meta.get("name", "").lower() in {"description", "keywords"}
    ]
    return norm_text(" ".join(meta_parts + [soup.get_text(" ", strip=True)]))


def host_type(url: str, school_slug: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if any(part in url.lower() for part in BLOCKED_HOST_PARTS):
        return "blocked"
    if school_slug == "sjtu" and (host.endswith("sjtu.edu.cn") or host.endswith("sjtu.edu")):
        return "official"
    if host.endswith("edu.cn") or host.endswith(".edu"):
        return "official"
    if host.endswith("github.io") or host in {"github.com", "sites.google.com"}:
        return "personal_or_project"
    if any(token in host for token in ["dblp", "arxiv", "aclanthology", "openreview", "ieee", "acm.org", "springer"]):
        return "paper"
    return "other"


def is_target_official_url(url: str, school_slug: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return any(part in host for part in TARGET_OFFICIAL_HOST_PARTS.get(school_slug, []))


def identity_confidence(text: str, row: pd.Series, target: TargetConfig, url: str) -> str:
    text_lower = text.lower()
    name = norm_text(row.get("姓名"))
    school_hits = [term for term in SCHOOL_TERMS.get(target.school_slug, []) if term.lower() in text_lower]
    name_hit = bool(name and name in text)
    source_type = host_type(url, target.school_slug)
    if is_target_official_url(url, target.school_slug) and (name_hit or school_hits):
        return "高"
    if source_type == "official" and name_hit and school_hits:
        return "高"
    if name_hit and school_hits:
        return "高"
    if source_type in {"personal_or_project", "paper"} and (name_hit or school_hits):
        return "中"
    if name_hit or school_hits:
        return "低"
    return ""


def extract_keywords(text: str) -> str:
    matches = []
    for pattern in [CORE_PATTERN, SEARCH_RELEVANT_PATTERN, VENUE_PATTERN]:
        matches.extend(match.group(0) for match in pattern.finditer(text))
    seen = []
    for item in matches:
        item = norm_text(item)
        if item and item.lower() not in {value.lower() for value in seen}:
            seen.append(item)
    return "; ".join(seen[:12])


def extract_snippet(text: str) -> str:
    sentences = re.split(r"(?<=[。！？；;.!?])\s*", text)
    candidates = []
    for sentence in sentences:
        sentence = norm_text(sentence)
        if len(sentence) < 24:
            continue
        if YEAR_PATTERN(sentence) or SEARCH_RELEVANT_PATTERN.search(sentence) or VENUE_PATTERN.search(sentence):
            candidates.append(sentence[:500])
        if len(candidates) >= 3:
            break
    return "；".join(candidates)[:900]


def YEAR_PATTERN(text: str) -> bool:
    return any(year in text for year in RECENT_YEARS)


def build_queries(row: pd.Series, target: TargetConfig) -> list[str]:
    name = norm_text(row.get("姓名"))
    school = target.school_name
    quoted_name = f'"{name}"'
    quoted_school = f'"{school}"'
    keywords = norm_text(row.get("命中关键词"))
    keyword_parts = [part.strip() for part in re.split(r"[;；,，]", keywords) if part.strip()]
    query_keywords = " ".join(keyword_parts[:3]) or "人工智能 论文"
    queries = [
        f"{quoted_name} {quoted_school} 个人主页 实验室 publications",
        f"{quoted_name} {quoted_school} {query_keywords} 2025 论文",
    ]
    if target.school_slug == "sjtu":
        queries.insert(1, f"site:sjtu.edu.cn {quoted_name} {query_keywords}")
    return queries


def should_search(row: pd.Series) -> bool:
    status = norm_text(row.get("WebSearch状态"))
    if status.startswith("已搜索"):
        return False
    level = norm_text(row.get("推荐等级"))
    contact = norm_text(row.get("是否建议套磁"))
    score = float(row.get("匹配分") or 0)
    dblp_count = float(row.get("DBLP近三年论文数") or 0)
    arxiv_count = float(row.get("arXiv近三年论文数") or 0)
    web_count = float(row.get("网页证据条数") or 0)
    text = " ".join(
        norm_text(row.get(col))
        for col in ["研究方向", "个人简介摘要", "综合研究方向（主页+DBLP+arXiv+网页）", "命中关键词", "推荐理由"]
    )
    weak_evidence = dblp_count + arxiv_count + web_count <= 1 or web_count == 0
    if contact == "是" and weak_evidence:
        return True
    if level == "暂不优先" and 10 <= score <= 45 and SEARCH_RELEVANT_PATTERN.search(text):
        return True
    if not norm_text(row.get("个人主页")) and score >= 10 and SEARCH_RELEVANT_PATTERN.search(text):
        return True
    return False


def fetch_result_page(session: requests.Session, url: str, cache_dir: Path) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if any(part in url.lower() for part in BLOCKED_HOST_PARTS):
        return ""
    html = fetch_cached(session, url, cache_dir, "html", timeout=15)
    return html_to_text(html)[:20000]


def evaluate_result(
    session: requests.Session,
    result: dict[str, str],
    row: pd.Series,
    target: TargetConfig,
    cache_dir: Path,
) -> SearchEvidence | None:
    url = result["url"]
    source_type = host_type(url, target.school_slug)
    if source_type == "blocked":
        return None
    search_text = norm_text(f"{result['title']} {result['snippet']}")
    page_text = ""
    if source_type in {"official", "personal_or_project", "paper"}:
        try:
            page_text = fetch_result_page(session, url, cache_dir)
        except Exception:
            page_text = ""
    combined = norm_text(f"{search_text} {page_text[:5000]}")
    confidence = identity_confidence(combined, row, target, url)
    if confidence not in {"高", "中"}:
        return None
    keywords = extract_keywords(combined)
    if not keywords and not YEAR_PATTERN(combined):
        return None
    snippet = extract_snippet(page_text) or norm_text(result["snippet"])[:600] or search_text[:600]
    return SearchEvidence(
        name=norm_text(row.get("姓名")),
        status=norm_text(row.get(STATUS_COLUMN)),
        confidence=confidence,
        query=result["query"],
        title=norm_text(result["title"]),
        snippet=snippet,
        url=url,
        source_type=source_type,
        keywords=keywords,
    )


def search_teacher(
    session: requests.Session,
    row: pd.Series,
    target: TargetConfig,
    cache_dir: Path,
) -> list[SearchEvidence]:
    evidence: list[SearchEvidence] = []
    seen_urls = set()
    for query in build_queries(row, target):
        for result in search_web(session, query, cache_dir):
            url = result["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            item = evaluate_result(session, result, row, target, cache_dir)
            if item:
                evidence.append(item)
            if len(evidence) >= 4:
                break
        if len(evidence) >= 4:
            break
        time.sleep(0.3)
    return evidence


def confidence_rank(confidence: str) -> int:
    return {"高": 3, "中": 2, "低": 1}.get(confidence, 0)


def summarize_search(row: pd.Series, evidence: list[SearchEvidence]) -> dict[str, Any]:
    if not evidence:
        return {
            "WebSearch状态": "已搜索-无可靠补充",
            "WebSearch置信度": "",
            "WebSearch证据条数": 0,
            "WebSearch关键词": "",
            "WebSearch代表证据": "",
            "WebSearch来源URL": "",
            "WebSearch建议": "未发现可交叉校验的新增证据",
        }
    best_confidence = max((item.confidence for item in evidence), key=confidence_rank)
    keywords = "; ".join(dict.fromkeys(part for item in evidence for part in item.keywords.split("; ") if part))
    representative = "；".join(
        f"{item.title}: {item.snippet}" for item in evidence[:3] if item.title or item.snippet
    )[:1500]
    urls = "; ".join(dict.fromkeys(item.url for item in evidence[:6]))
    suggestion = "作为补充证据，需人工复核来源归属"
    if best_confidence in {"高", "中"} and (CORE_PATTERN.search(keywords) or CORE_PATTERN.search(representative)):
        suggestion = "可增强核心方向证据；不单独驱动强烈建议"
    elif best_confidence in {"高", "中"}:
        suggestion = "可增强相关方向证据；适合备选复核"
    return {
        "WebSearch状态": "已搜索",
        "WebSearch置信度": best_confidence,
        "WebSearch证据条数": len(evidence),
        "WebSearch关键词": keywords[:600],
        "WebSearch代表证据": representative,
        "WebSearch来源URL": urls,
        "WebSearch建议": suggestion,
    }


def conservative_recommendation_update(row: pd.Series, summary: dict[str, Any]) -> dict[str, Any]:
    return evaluate_legacy_row(row, web_search_override=summary).to_columns()


def evidence_to_rows(target: TargetConfig, row: pd.Series, evidence: list[SearchEvidence]) -> list[dict[str, Any]]:
    return [
        {
            "姓名": item.name,
            TEACHER_ID_COLUMN: row.get(TEACHER_ID_COLUMN, ""),
            STATUS_COLUMN: item.status,
            "学校": target.school_name,
            "学院": target.college_name,
            "WebSearch置信度": item.confidence,
            "查询": item.query,
            "来源类型": item.source_type,
            "标题": item.title,
            "证据": item.snippet,
            "关键词": item.keywords,
            "来源URL": item.url,
            "教师主页链接": row.get("教师主页链接"),
        }
        for item in evidence
    ]


def apply_curated_evidence(target: TargetConfig, full: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    items = load_curated_web_search().get(target.key, [])
    if not items:
        return full, rows
    for item in items:
        teacher_id = norm_text(item.get(TEACHER_ID_COLUMN))
        if teacher_id and TEACHER_ID_COLUMN in full.columns:
            matches = full[full[TEACHER_ID_COLUMN].astype(str) == teacher_id]
        else:
            matches = full[full["姓名"].astype(str) == item["姓名"]]
        if len(matches) != 1:
            continue
        idx = matches.index[0]
        try:
            current_count = int(float(full.at[idx, "WebSearch证据条数"] or 0)) if "WebSearch证据条数" in full.columns else 0
        except Exception:
            current_count = 0
        urls = norm_text(item["来源URL"])
        evidence_text = norm_text(item["证据"])
        keywords = norm_text(item["关键词"])
        full.at[idx, "WebSearch状态"] = "人工确认-本地证据"
        full.at[idx, "WebSearch置信度"] = item["置信度"]
        full.at[idx, "WebSearch证据条数"] = max(current_count, len([url for url in urls.split("; ") if url]))
        full.at[idx, "WebSearch关键词"] = keywords
        full.at[idx, "WebSearch代表证据"] = evidence_text
        full.at[idx, "WebSearch来源URL"] = urls
        full.at[idx, "WebSearch建议"] = item["建议"]
        policy_update = conservative_recommendation_update(
            full.loc[idx],
            {
                "WebSearch状态": "人工确认-本地证据",
                "WebSearch置信度": item["置信度"],
                "WebSearch证据条数": full.at[idx, "WebSearch证据条数"],
                "WebSearch关键词": keywords,
                "WebSearch代表证据": evidence_text,
                "人工确认": True,
            },
        )
        for column, value in policy_update.items():
            full.at[idx, column] = value
        for url in [part.strip() for part in urls.split(";") if part.strip()]:
            rows.append(
                {
                    "姓名": item["姓名"],
                    TEACHER_ID_COLUMN: full.at[idx, TEACHER_ID_COLUMN] if TEACHER_ID_COLUMN in full.columns else "",
                    STATUS_COLUMN: full.at[idx, STATUS_COLUMN] if STATUS_COLUMN in full.columns else "",
                    "学校": target.school_name,
                    "学院": target.college_name,
                    "WebSearch置信度": item["置信度"],
                    "查询": "curated:local-json",
                    "来源类型": host_type(url, target.school_slug),
                    "标题": item["标题"],
                    "证据": evidence_text,
                    "关键词": keywords,
                    "来源URL": url,
                    "教师主页链接": full.at[idx, "教师主页链接"] if "教师主页链接" in full.columns else "",
                }
            )
    return full, rows


def run_target(target: TargetConfig, max_candidates: int | None = None, force: bool = False) -> None:
    if not target.final_path.exists():
        raise FileNotFoundError(target.final_path)
    run_context = create_run_context("web_search", target.key, [target.final_path])
    cache_dir = target.output_dir / "web_search_cache"
    xls = pd.ExcelFile(target.final_path)
    sheets = {sheet: pd.read_excel(target.final_path, sheet_name=sheet) for sheet in xls.sheet_names}
    full_sheet_name = "全量教师名录"
    full = pd.DataFrame(
        ensure_teacher_identity(target.school_slug, target.college_slug, row.to_dict())
        for _, row in sheets[full_sheet_name].iterrows()
    )
    full = apply_contact_statuses(full, target.school_slug, target.college_slug)
    for column in SEARCH_COLUMNS:
        if column not in full.columns:
            full[column] = ""
        full[column] = full[column].astype("object")

    candidates = full if force else full[full.apply(should_search, axis=1)]
    if max_candidates is not None:
        candidates = candidates.head(max_candidates)

    session = requests.Session()
    detail_rows: list[dict[str, Any]] = []
    processed = 0
    for idx, row in candidates.iterrows():
        processed += 1
        print(f"{target.key} web search {processed}/{len(candidates)} {row.get('姓名')}", flush=True)
        evidence = search_teacher(session, row, target, cache_dir)
        summary = summarize_search(row, evidence)
        rec_update = conservative_recommendation_update(row, summary)
        for key, value in {**summary, **rec_update}.items():
            full.at[idx, key] = value
        detail_rows.extend(evidence_to_rows(target, row, evidence))
        time.sleep(0.4)

    full, curated_rows = apply_curated_evidence(target, full)
    detail_rows.extend(curated_rows)

    if "WebSearch证据明细" in sheets:
        existing_detail = sheets["WebSearch证据明细"]
        detail = pd.concat([existing_detail, pd.DataFrame(detail_rows)], ignore_index=True)
        if not detail.empty:
            detail = detail[detail["WebSearch置信度"].isin(["高", "中"])].copy()
            detail = detail.drop_duplicates(subset=[TEACHER_ID_COLUMN, "来源URL", "标题"], keep="last")
    else:
        detail = pd.DataFrame(detail_rows, columns=WEB_SEARCH_DETAIL_COLUMNS)
    if detail.empty:
        detail = pd.DataFrame(columns=WEB_SEARCH_DETAIL_COLUMNS)
    else:
        detail = detail.reindex(columns=WEB_SEARCH_DETAIL_COLUMNS)

    priority_order = {"强烈建议": 0, "可以考虑": 1, "暂不优先": 2}
    full["_order"] = full["推荐等级"].map(priority_order).fillna(9)
    full = full.sort_values(["_order", "匹配分", "名录序号"], ascending=[True, False, True]).drop(columns=["_order"])
    priority = full[full["是否建议套磁"] == "是"].copy()

    sheets["优先套磁名单"] = priority
    sheets["全量教师名录"] = full
    sheets["WebSearch证据明细"] = detail

    with pd.ExcelWriter(target.final_path, engine="openpyxl") as writer:
        for sheet_name, sheet in sheets.items():
            sheet.to_excel(writer, sheet_name=sheet_name, index=False)

    style_workbook(target.final_path)
    migrate_workbook(target.final_path, {})
    write_stage_manifest(target.output_dir, run_context)
    print(f"{target.key} candidates={len(candidates)} web_search_rows={len(detail)} output={target.final_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded web-search supplementation for final teacher workbooks.")
    parser.add_argument("targets", nargs="*", help=f"Targets. Available: {', '.join(TARGETS)}")
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Search every row instead of bounded low-evidence candidates.")
    args = parser.parse_args()
    if not args.targets:
        parser.error("Please pass at least one target key, e.g. python supplement_web_search_research.py <target>.")
    target_keys = args.targets
    for target_key in target_keys:
        run_target(get_target(target_key), max_candidates=args.max_candidates, force=args.force)


if __name__ == "__main__":
    main()
