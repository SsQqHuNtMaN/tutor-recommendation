from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from numbers import Real
from typing import Any, Protocol


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
ARXIV_PATTERN = re.compile(r"\barxiv\s*:?\s*\d{4}\.\d{4,5}(?:v\d+)?\b", re.I)
NUMBERED_ENTRY_PATTERN = re.compile(r"(?=(?<!\S)\d{1,2}[、.)）]\s+)")
PUBLICATION_SIGNAL_PATTERN = re.compile(
    r"(?:"
    r"journal|proceedings|conference|transactions|letters|annals|biometrika|econometrica|"
    r"statistica|springer|wiley|elsevier|siam|ieee|acm|accepted|forthcoming|in\s+press|"
    r"to\s+appear|submitted|preprint|volume|\bvol\.?\s*\d|\bissue\s*\d|\bpp?\.\s*\d|"
    r"期刊|学报|杂志|会议|出版社|出版|第\s*\d+\s*[卷期]|(?:19|20)\d{2}年\s*第?\s*\d+\s*期|"
    r"\d+\s*\(\s*\d+\s*\)|"
    r"录用|接收|发表|预印本|论著|专著|论文链接|paper\s+link"
    r")",
    re.I,
)
CAREER_OR_BIOGRAPHY_PATTERN = re.compile(
    r"(?:"
    r"教育经历|工作经历|任职经历|学习经历|个人经历|毕业于|加入.{0,30}(?:大学|学院|研究院)|"
    r"(?:获得?|获).{0,12}(?:学位|博士|硕士|学士)|\d{4}[-/.年]\d{1,2}.{0,30}至|"
    r"\d{4}.{0,20}至今|准聘|长聘|副主任|现任|assistant\s+professor|associate\s+professor"
    r")",
    re.I,
)
PROJECT_PATTERN = re.compile(r"(?:基金|项目|课题|横向|纵向).{0,80}(?:主持|负责人|资助|编号|项目)", re.I)
AWARD_PATTERN = re.compile(r"(?:获奖|奖励|荣誉|成果奖|教学奖|一等奖|二等奖|三等奖|award)", re.I)


def is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Real):
        try:
            return math.isnan(float(value))
        except (TypeError, ValueError):
            return False
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "nat", "none", "<na>"}
    return False


def norm_text(value: Any) -> str:
    if is_missing_value(value):
        return ""
    return re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ").replace("\xa0", " ")).strip()


def normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", norm_text(value).lower())


def normalized_title(value: Any) -> str:
    text = unicodedata.normalize("NFKC", norm_text(value)).casefold()
    text = re.sub(r"\\(?:emph|textit|textbf|mathrm|mathbf)\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"[{}$]", "", text)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", text)


def normalize_doi(value: Any) -> str:
    text = norm_text(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi\s*:\s*", "", text)
    match = DOI_PATTERN.search(text)
    return match.group(0).rstrip(".,;)") if match else ""


def normalize_arxiv_id(value: Any) -> str:
    text = norm_text(value).lower()
    text = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", text)
    text = re.sub(r"^arxiv\s*:\s*", "", text)
    text = re.sub(r"\.pdf$", "", text)
    match = re.search(r"(?:[a-z.-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", text, re.I)
    return re.sub(r"v\d+$", "", match.group(0), flags=re.I) if match else ""


@dataclass(frozen=True)
class PublicationRecord:
    source: str
    title: str
    year: int | None = None
    doi: str = ""
    url: str = ""
    authors: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    source_id: str = ""
    author_ids: tuple[str, ...] = ()
    affiliations: tuple[str, ...] = ()
    arxiv_id: str = ""
    openalex_id: str = ""
    dblp_key: str = ""
    zbmath_id: str = ""
    venue: str = ""
    publication_date: str = ""
    is_preprint: bool = False
    raw_ref: str = ""
    matched_query_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PublicationRecord":
        tuple_fields = {
            "authors",
            "author_ids",
            "affiliations",
            "classifications",
            "topics",
            "matched_query_ids",
        }
        allowed = cls.__dataclass_fields__
        values: dict[str, Any] = {}
        for key, value in data.items():
            if key not in allowed:
                continue
            values[key] = tuple(value or ()) if key in tuple_fields else value
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["doi"] = normalize_doi(data.get("doi"))
        data["arxiv_id"] = normalize_arxiv_id(data.get("arxiv_id"))
        data["normalized_title"] = normalized_title(self.title)
        for key in (
            "authors",
            "author_ids",
            "affiliations",
            "classifications",
            "topics",
            "matched_query_ids",
        ):
            data[key] = list(data[key])
        return data


@dataclass(frozen=True)
class CanonicalWork:
    canonical_id: str
    title: str
    normalized_title: str
    year: int | None = None
    doi: str = ""
    arxiv_id: str = ""
    authors: tuple[str, ...] = ()
    venue: str = ""
    publication_date: str = ""
    url: str = ""
    sources: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    classifications: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    is_preprint: bool = False
    records: tuple[PublicationRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("authors", "sources", "source_ids", "classifications", "topics"):
            data[key] = list(data[key])
        data["records"] = [record.to_dict() for record in self.records]
        return data


@dataclass(frozen=True)
class PublicationAuthorCandidate:
    source: str
    author_id: str
    display_name: str = ""
    author_url: str = ""
    orcid: str = ""
    aliases: tuple[str, ...] = ()
    affiliations: tuple[str, ...] = ()
    score: int = 0
    signals: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    decision: str = "review"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("aliases", "affiliations", "signals", "conflicts"):
            data[key] = list(data[key])
        return data


def _unique_text(values: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = norm_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return tuple(output)


def _author_overlap(first: PublicationRecord, second: PublicationRecord) -> bool:
    first_names = {normalized_name(name) for name in first.authors if normalized_name(name)}
    second_names = {normalized_name(name) for name in second.authors if normalized_name(name)}
    return bool(first_names and second_names and first_names & second_names)


def records_represent_same_work(first: PublicationRecord, second: PublicationRecord) -> bool:
    first_doi = normalize_doi(first.doi)
    second_doi = normalize_doi(second.doi)
    if first_doi and second_doi:
        return first_doi == second_doi
    first_arxiv = normalize_arxiv_id(first.arxiv_id)
    second_arxiv = normalize_arxiv_id(second.arxiv_id)
    if first_arxiv and second_arxiv:
        return first_arxiv == second_arxiv
    if first.source == second.source and first.source_id and second.source_id:
        return first.source_id == second.source_id
    first_title = normalized_title(first.title)
    second_title = normalized_title(second.title)
    if len(first_title) < 12 or len(second_title) < 12:
        return False
    year_close = first.year is None or second.year is None or abs(first.year - second.year) <= 1
    if not year_close:
        return False
    if first_title == second_title:
        return _author_overlap(first, second) or not first.authors or not second.authors
    similarity = SequenceMatcher(None, first_title, second_title).ratio()
    return similarity >= 0.94 and _author_overlap(first, second)


def canonicalize_publications(records: Iterable[PublicationRecord]) -> tuple[CanonicalWork, ...]:
    groups: list[list[PublicationRecord]] = []
    for record in records:
        if not norm_text(record.title):
            continue
        group = next(
            (candidate for candidate in groups if any(records_represent_same_work(record, item) for item in candidate)),
            None,
        )
        if group is None:
            groups.append([record])
        else:
            group.append(record)

    canonical: list[CanonicalWork] = []
    source_priority = {"official": 4, "openalex": 3, "zbmath": 2, "arxiv": 1}
    for group in groups:
        ordered = sorted(
            group,
            key=lambda item: (
                bool(normalize_doi(item.doi)),
                not item.is_preprint,
                source_priority.get(item.source, 0),
                len(norm_text(item.title)),
            ),
            reverse=True,
        )
        primary = ordered[0]
        doi = next((normalize_doi(item.doi) for item in ordered if normalize_doi(item.doi)), "")
        arxiv_id = next(
            (normalize_arxiv_id(item.arxiv_id) for item in ordered if normalize_arxiv_id(item.arxiv_id)),
            "",
        )
        source_ids = _unique_text(
            f"{item.source}:{item.source_id}" for item in ordered if item.source_id
        )
        canonical_id = (
            f"doi:{doi}"
            if doi
            else f"arxiv:{arxiv_id}"
            if arxiv_id
            else source_ids[0]
            if source_ids
            else f"title:{normalized_title(primary.title)}"
        )
        years = [item.year for item in ordered if item.year is not None]
        canonical.append(
            CanonicalWork(
                canonical_id=canonical_id,
                title=norm_text(primary.title),
                normalized_title=normalized_title(primary.title),
                year=max(years) if years else None,
                doi=doi,
                arxiv_id=arxiv_id,
                authors=_unique_text(author for item in ordered for author in item.authors),
                venue=next((norm_text(item.venue) for item in ordered if norm_text(item.venue)), ""),
                publication_date=next(
                    (norm_text(item.publication_date) for item in ordered if norm_text(item.publication_date)),
                    "",
                ),
                url=next((norm_text(item.url) for item in ordered if norm_text(item.url)), ""),
                sources=_unique_text(item.source for item in ordered),
                source_ids=source_ids,
                classifications=_unique_text(
                    value for item in ordered for value in item.classifications
                ),
                topics=_unique_text(value for item in ordered for value in item.topics),
                is_preprint=all(item.is_preprint for item in ordered),
                records=tuple(ordered),
            )
        )
    canonical.sort(key=lambda item: (item.year or 0, item.title.casefold()), reverse=True)
    return tuple(canonical)


@dataclass(frozen=True)
class PublicationEvidenceResult:
    source: str
    status: str
    confidence: str = ""
    author_id: str = ""
    author_url: str = ""
    orcid: str = ""
    classifications: tuple[str, ...] = ()
    works: tuple[PublicationRecord, ...] = ()
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    identity_status: str = ""
    author_candidates: tuple[PublicationAuthorCandidate, ...] = ()
    source_report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["classifications"] = list(self.classifications)
        data["works"] = [work.to_dict() for work in self.works]
        data["author_candidates"] = [candidate.to_dict() for candidate in self.author_candidates]
        return data


class PublicationEvidenceAdapter(Protocol):
    source: str

    def collect(
        self,
        row: dict[str, Any],
        *,
        start_year: int,
        end_year: int,
        discovery_only: bool = False,
    ) -> PublicationEvidenceResult: ...


def split_publication_entries(value: Any) -> tuple[str, ...]:
    if is_missing_value(value):
        return ()
    entries: list[str] = []
    for raw_line in str(value).splitlines():
        line = norm_text(raw_line)
        if not line:
            continue
        parts = [norm_text(part) for part in NUMBERED_ENTRY_PATTERN.split(line)]
        entries.extend(part for part in parts if part)
    return tuple(entries)


def looks_like_publication_record(value: Any) -> bool:
    text = norm_text(value)
    if len(text) < 12:
        return False
    has_identifier = bool(DOI_PATTERN.search(text) or ARXIV_PATTERN.search(text))
    if not has_identifier and (
        CAREER_OR_BIOGRAPHY_PATTERN.search(text)
        or PROJECT_PATTERN.search(text)
        or AWARD_PATTERN.search(text)
    ):
        return False
    if has_identifier:
        return True
    if not YEAR_PATTERN.search(text):
        return False
    if PUBLICATION_SIGNAL_PATTERN.search(text) or ("《" in text and "》" in text):
        return True
    latin_words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text)
    return len(latin_words) >= 4 and bool(re.search(r"[.,;:()]", text))


def official_publications(row: dict[str, Any]) -> tuple[PublicationRecord, ...]:
    source_url = norm_text(row.get("官方论文来源") or row.get("教师主页链接"))
    records: list[PublicationRecord] = []
    for text in split_publication_entries(row.get("官方论文列表")):
        if not looks_like_publication_record(text):
            continue
        year_match = YEAR_PATTERN.search(text)
        doi_match = DOI_PATTERN.search(text)
        records.append(
            PublicationRecord(
                source="official",
                title=text,
                year=int(year_match.group(0)) if year_match else None,
                doi=doi_match.group(0).rstrip(".,;)") if doi_match else "",
                url=source_url,
            )
        )
    return tuple(records)


def title_overlap(official: tuple[PublicationRecord, ...], candidate: tuple[PublicationRecord, ...]) -> int:
    official_titles = [normalized_title(item.title) for item in official if len(normalized_title(item.title)) >= 16]
    candidate_titles = [normalized_title(item.title) for item in candidate if len(normalized_title(item.title)) >= 16]
    matches = 0
    for first in official_titles:
        if any(first in second or second in first for second in candidate_titles):
            matches += 1
    return matches
