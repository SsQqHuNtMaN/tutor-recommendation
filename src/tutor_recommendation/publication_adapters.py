from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from .publication_evidence import (
    PublicationEvidenceResult,
    PublicationRecord,
    norm_text,
    normalized_name,
    official_publications,
    title_overlap,
)


def _json(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("publication API returned a non-object response")
    return data


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return norm_text(value)
    if isinstance(value, dict):
        for key in ("title", "text", "name", "display_name"):
            if value.get(key):
                return norm_text(value[key])
    return ""


class OfficialPublicationAdapter:
    source = "official"

    def collect(self, row: dict[str, Any], *, start_year: int, end_year: int) -> PublicationEvidenceResult:
        works = tuple(
            work for work in official_publications(row)
            if work.year is None or start_year <= work.year <= end_year
        )
        return PublicationEvidenceResult(
            source=self.source,
            status="success" if works else "no_record",
            confidence="high" if works else "",
            works=works,
            reason="教师官方页面 publication list" if works else "官方页面未提供可结构化论文条目",
        )


class ZbMathAdapter:
    source = "zbmath"
    base_url = "https://api.zbmath.org/v1"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def _authors(self, name: str) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{self.base_url}/author/_search",
            params={"search_string": f'au:"{name}"', "page": 0, "results_per_page": 8},
            timeout=35,
            headers={"User-Agent": "tutor-recommendation/1.0"},
        )
        if getattr(response, "status_code", None) == 404:
            return []
        return list(_json(response).get("result") or [])

    def _works(self, author_code: str, start_year: int, end_year: int) -> tuple[PublicationRecord, ...]:
        response = self.session.get(
            f"{self.base_url}/document/_search",
            params={
                "search_string": f"ia:{author_code} py:{start_year}-{end_year}",
                "page": 0,
                "results_per_page": 100,
            },
            timeout=45,
            headers={"User-Agent": "tutor-recommendation/1.0"},
        )
        items = list(_json(response).get("result") or [])
        records: list[PublicationRecord] = []
        for item in items:
            title = _string_value(item.get("title"))
            if not title:
                continue
            links = item.get("links") or []
            doi = next((norm_text(link.get("identifier")) for link in links if link.get("type") == "doi"), "")
            url = next((norm_text(link.get("url")) for link in links if link.get("url")), "")
            msc = tuple(norm_text(entry.get("code")) for entry in item.get("msc") or [] if entry.get("code"))
            authors = tuple(
                norm_text(author.get("name"))
                for author in (item.get("contributors") or {}).get("authors") or []
                if author.get("name")
            )
            year_value = item.get("year") or item.get("publication_year")
            try:
                year = int(year_value)
            except (TypeError, ValueError):
                year = None
            records.append(
                PublicationRecord(self.source, title, year, doi, url, authors, msc)
            )
        return tuple(records)

    @staticmethod
    def _candidate_names(candidate: dict[str, Any]) -> set[str]:
        names = {norm_text(candidate.get("name"))}
        names.update(norm_text(item.get("name")) for item in candidate.get("further_spellings") or [])
        return {normalized_name(name) for name in names if name}

    def collect(self, row: dict[str, Any], *, start_year: int, end_year: int) -> PublicationEvidenceResult:
        names = [norm_text(row.get("英文姓名")), norm_text(row.get("姓名"))]
        names = list(dict.fromkeys(name for name in names if name))
        if not names:
            return PublicationEvidenceResult(self.source, "no_record", reason="教师姓名为空")
        try:
            candidates: list[dict[str, Any]] = []
            for name in names:
                candidates.extend(self._authors(name))
            unique = {norm_text(item.get("code")): item for item in candidates if item.get("code")}
            candidates = list(unique.values())
            if not candidates:
                return PublicationEvidenceResult(self.source, "no_record", reason="zbMATH 未找到作者候选")
            official = official_publications(row)
            official_homepages = {norm_text(row.get("个人主页")), norm_text(row.get("教师主页链接"))}
            official_orcid = norm_text(row.get("ORCID")).replace("https://orcid.org/", "")
            scored: list[tuple[int, int, dict[str, Any], tuple[PublicationRecord, ...], str]] = []
            requested_names = {normalized_name(name) for name in names}
            for candidate in candidates[:5]:
                code = norm_text(candidate.get("code"))
                works = self._works(code, start_year, end_year)
                overlap = title_overlap(official, works)
                score = 4 if requested_names & self._candidate_names(candidate) else 0
                external = candidate.get("external_ids") or []
                orcid = next((norm_text(item.get("external_id")) for item in external if item.get("type") == "orcid"), "")
                homepages = {norm_text(item.get("external_id")) for item in external if item.get("type") == "homepage"}
                if official_orcid and orcid == official_orcid:
                    score += 12
                if any(homepage and homepage in official_homepages for homepage in homepages):
                    score += 10
                score += min(overlap, 3) * 5
                scored.append((score, overlap, candidate, works, orcid))
            scored.sort(key=lambda item: (item[0], item[1], len(item[3])), reverse=True)
            score, overlap, candidate, works, orcid = scored[0]
            confidence = "high" if score >= 12 or overlap >= 2 else "medium" if score >= 8 and overlap >= 1 else "low"
            code = norm_text(candidate.get("code"))
            fields = tuple(norm_text(item.get("field")) for item in candidate.get("main_fields") or [] if item.get("field"))
            status = "success" if confidence in {"high", "medium"} else "identity_uncertain"
            return PublicationEvidenceResult(
                self.source,
                status,
                confidence,
                code,
                f"https://zbmath.org/authors/?q=ai:{quote(code)}",
                orcid,
                fields,
                works,
                f"姓名/外部标识/官网论文交叉得分 {score}，官网题名重合 {overlap}",
            )
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            return PublicationEvidenceResult(self.source, "request_failed", reason=f"{type(exc).__name__}: {exc}")


class OpenAlexAdapter:
    source = "openalex"
    base_url = "https://api.openalex.org"

    def __init__(self, session: requests.Session | None = None, api_key: str | None = None) -> None:
        self.session = session or requests.Session()
        self.api_key = api_key if api_key is not None else os.environ.get("OPENALEX_API_KEY", "").strip()

    def _params(self, **values: Any) -> dict[str, Any]:
        return {**values, "api_key": self.api_key}

    def _authors(self, name: str) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{self.base_url}/authors",
            params=self._params(search=name, per_page=10),
            timeout=35,
            headers={"User-Agent": "tutor-recommendation/1.0"},
        )
        return list(_json(response).get("results") or [])

    def _works(self, author_id: str, start_year: int, end_year: int) -> tuple[PublicationRecord, ...]:
        short_id = author_id.rsplit("/", 1)[-1]
        response = self.session.get(
            f"{self.base_url}/works",
            params=self._params(
                filter=f"authorships.author.id:{short_id},publication_year:{start_year}-{end_year}",
                sort="publication_date:desc",
                per_page=100,
            ),
            timeout=45,
            headers={"User-Agent": "tutor-recommendation/1.0"},
        )
        records: list[PublicationRecord] = []
        for item in list(_json(response).get("results") or []):
            title = norm_text(item.get("display_name") or item.get("title"))
            if not title:
                continue
            authors = tuple(
                norm_text((authorship.get("author") or {}).get("display_name"))
                for authorship in item.get("authorships") or []
                if (authorship.get("author") or {}).get("display_name")
            )
            topics = tuple(
                norm_text(topic.get("display_name"))
                for topic in item.get("topics") or []
                if topic.get("display_name")
            )
            primary = item.get("primary_topic") or {}
            if primary.get("display_name") and norm_text(primary.get("display_name")) not in topics:
                topics = (norm_text(primary.get("display_name")), *topics)
            records.append(
                PublicationRecord(
                    self.source,
                    title,
                    int(item["publication_year"]) if item.get("publication_year") else None,
                    norm_text(item.get("doi")).replace("https://doi.org/", ""),
                    norm_text(item.get("id")),
                    authors,
                    (),
                    topics[:8],
                )
            )
        return tuple(records)

    def collect(self, row: dict[str, Any], *, start_year: int, end_year: int) -> PublicationEvidenceResult:
        if not self.api_key:
            return PublicationEvidenceResult(self.source, "not_configured", reason="OPENALEX_API_KEY 未配置")
        names = [norm_text(row.get("英文姓名")), norm_text(row.get("姓名"))]
        names = list(dict.fromkeys(name for name in names if name))
        try:
            candidates: list[dict[str, Any]] = []
            for name in names:
                candidates.extend(self._authors(name))
            unique = {norm_text(item.get("id")): item for item in candidates if item.get("id")}
            candidates = list(unique.values())
            if not candidates:
                return PublicationEvidenceResult(self.source, "no_record", reason="OpenAlex 未找到作者候选")
            requested = {normalized_name(name) for name in names}
            official = official_publications(row)
            official_orcid = norm_text(row.get("ORCID")).replace("https://orcid.org/", "")
            affiliation_terms = ("renmin university", "中国人民大学", "ruc")
            scored: list[tuple[int, int, dict[str, Any], tuple[PublicationRecord, ...]]] = []
            for candidate in candidates[:5]:
                works = self._works(norm_text(candidate.get("id")), start_year, end_year)
                overlap = title_overlap(official, works)
                score = 4 if normalized_name(candidate.get("display_name")) in requested else 0
                orcid = norm_text(candidate.get("orcid")).replace("https://orcid.org/", "")
                if official_orcid and orcid == official_orcid:
                    score += 12
                affiliation_text = " ".join(
                    norm_text((entry.get("institution") or {}).get("display_name"))
                    for entry in candidate.get("affiliations") or candidate.get("last_known_institutions") or []
                ).lower()
                if any(term in affiliation_text for term in affiliation_terms):
                    score += 5
                score += min(overlap, 3) * 5
                scored.append((score, overlap, candidate, works))
            scored.sort(key=lambda item: (item[0], item[1], len(item[3])), reverse=True)
            score, overlap, candidate, works = scored[0]
            confidence = "high" if score >= 12 or overlap >= 2 else "medium" if score >= 9 else "low"
            status = "success" if confidence in {"high", "medium"} else "identity_uncertain"
            topics = tuple(dict.fromkeys(topic for work in works for topic in work.topics))[:12]
            return PublicationEvidenceResult(
                self.source,
                status,
                confidence,
                norm_text(candidate.get("id")).rsplit("/", 1)[-1],
                norm_text(candidate.get("id")),
                norm_text(candidate.get("orcid")).replace("https://orcid.org/", ""),
                topics,
                works,
                f"姓名/机构/官网论文交叉得分 {score}，官网题名重合 {overlap}",
            )
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            return PublicationEvidenceResult(self.source, "request_failed", reason=f"{type(exc).__name__}: {exc}")
