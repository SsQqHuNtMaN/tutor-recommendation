from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ").replace("\xa0", " ")).strip()


def normalized_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", norm_text(value).lower())


def normalized_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", norm_text(value).lower())


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

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("authors", "classifications", "topics"):
            data[key] = list(data[key])
        return data


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

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["classifications"] = list(self.classifications)
        data["works"] = [work.to_dict() for work in self.works]
        return data


class PublicationEvidenceAdapter(Protocol):
    source: str

    def collect(self, row: dict[str, Any], *, start_year: int, end_year: int) -> PublicationEvidenceResult: ...


def official_publications(row: dict[str, Any]) -> tuple[PublicationRecord, ...]:
    source_url = norm_text(row.get("官方论文来源") or row.get("教师主页链接"))
    records: list[PublicationRecord] = []
    for line in str(row.get("官方论文列表") or "").splitlines():
        text = norm_text(line)
        if not text:
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
