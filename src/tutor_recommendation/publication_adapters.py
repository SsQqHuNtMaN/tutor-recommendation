from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from .publication_evidence import (
    PublicationAuthorCandidate,
    PublicationEvidenceResult,
    PublicationRecord,
    norm_text,
    normalized_name,
    official_publications,
    title_overlap,
)
from .publication_identity import identity_query_names
from .publication_http import (
    PublicationHttpClient,
    PublicationRequestFailed,
    PublicationSchemaChanged,
    PublicationTermsRequired,
)


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return norm_text(value)
    if isinstance(value, dict):
        for key in ("title", "text", "name", "display_name"):
            if value.get(key):
                return norm_text(value[key])
    return ""


def _affiliation_terms(row: dict[str, Any]) -> tuple[str, ...]:
    values = str(row.get("论文身份机构") or "").replace("；", ";").split(";")
    return tuple(norm_text(value).casefold() for value in values if norm_text(value))


def _rejected_ids(row: dict[str, Any], field: str) -> set[str]:
    values = str(row.get(field) or "").replace("；", ";").split(";")
    return {norm_text(value).casefold().rsplit("/", 1)[-1] for value in values if norm_text(value)}


class OfficialPublicationAdapter:
    source = "official"
    cache_version = "official-v2-record-gate"

    def collect(
        self,
        row: dict[str, Any],
        *,
        start_year: int,
        end_year: int,
        discovery_only: bool = False,
    ) -> PublicationEvidenceResult:
        available = official_publications(row)
        works = tuple(work for work in available if work.year is not None and start_year <= work.year <= end_year)
        if works:
            status = "success"
            reason = "教师官方页面 publication list"
        elif available:
            status = "no_recent_record"
            reason = "教师官方页面存在可结构化学术成果，但没有年份明确且落入当前窗口的论文"
        else:
            status = "no_record"
            reason = "官方页面未提供可结构化论文条目"
        return PublicationEvidenceResult(
            source=self.source,
            status=status,
            confidence="high" if works else "",
            works=works,
            reason=reason,
            metadata={"available_records": len(available)},
        )


class ZbMathAdapter:
    source = "zbmath"
    base_url = "https://api.zbmath.org/v1"
    cache_version = "zbmath-v3-candidate-vector"

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.http = PublicationHttpClient(self.session, source=self.source)
        self.max_work_pages = max(1, int(os.environ.get("ZBMATH_MAX_WORK_PAGES", "3")))
        self.last_work_metadata: dict[str, Any] = {}
        self.schema_confirmed = False
        self.works_schema_confirmed = False

    def _authors(self, name: str) -> list[dict[str, Any]]:
        try:
            data = self.http.get_json(
                f"{self.base_url}/author/_search",
                params={"search_string": f'au:"{name}"', "page": 0, "results_per_page": 8},
                timeout=(10.0, 35.0),
                expected_keys=("result",),
            )
        except PublicationRequestFailed as exc:
            if exc.status_code == 404:
                if self.schema_confirmed:
                    return []
                try:
                    probe = self.http.get_json(
                        f"{self.base_url}/author/_search",
                        params={
                            "search_string": 'au:"Tao, Terence"',
                            "page": 0,
                            "results_per_page": 1,
                        },
                        timeout=(10.0, 35.0),
                        expected_keys=("result",),
                    )
                    self.schema_confirmed = isinstance(probe.get("result"), list)
                except PublicationRequestFailed:
                    pass
                if self.schema_confirmed:
                    return []
                raise PublicationSchemaChanged(
                    self.source,
                    "schema_changed",
                    "zbMATH author search endpoint returned 404",
                    404,
                ) from exc
            raise
        self.schema_confirmed = True
        return list(data.get("result") or [])

    def _works(self, author_code: str, start_year: int, end_year: int) -> tuple[PublicationRecord, ...]:
        records: list[PublicationRecord] = []
        raw_count = 0
        pages = 0
        truncated = False
        for page in range(self.max_work_pages):
            try:
                data = self.http.get_json(
                    f"{self.base_url}/document/_search",
                    params={
                        "search_string": f"ia:{author_code} py:{start_year}-{end_year}",
                        "page": page,
                        "results_per_page": 100,
                    },
                    timeout=(10.0, 45.0),
                    expected_keys=("result",),
                )
            except PublicationRequestFailed as exc:
                if exc.status_code != 404:
                    raise
                if not self.works_schema_confirmed:
                    try:
                        probe = self.http.get_json(
                            f"{self.base_url}/document/_search",
                            params={"search_string": "py:2024", "page": 0, "results_per_page": 1},
                            timeout=(10.0, 45.0),
                            expected_keys=("result",),
                        )
                        self.works_schema_confirmed = isinstance(probe.get("result"), list)
                    except PublicationRequestFailed:
                        pass
                if not self.works_schema_confirmed:
                    raise
                data = {"result": []}
            self.works_schema_confirmed = True
            items = list(data.get("result") or [])
            pages += 1
            raw_count += len(items)
            for item in items:
                title = _string_value(item.get("title"))
                if not title:
                    continue
                links = item.get("links") or []
                doi = next((norm_text(link.get("identifier")) for link in links if link.get("type") == "doi"), "")
                arxiv_id = next(
                    (norm_text(link.get("identifier")) for link in links if link.get("type") == "arxiv"),
                    "",
                )
                url = next((norm_text(link.get("url")) for link in links if link.get("url")), "")
                msc = tuple(norm_text(entry.get("code")) for entry in item.get("msc") or [] if entry.get("code"))
                author_entries = (item.get("contributors") or {}).get("authors") or []
                authors = tuple(norm_text(author.get("name")) for author in author_entries if author.get("name"))
                author_ids = tuple(norm_text(author.get("code")) for author in author_entries if author.get("code"))
                year_value = item.get("year") or item.get("publication_year")
                try:
                    year = int(year_value)
                except (TypeError, ValueError):
                    year = None
                source_id = norm_text(item.get("id") or item.get("document_id") or item.get("zbl_id"))
                records.append(
                    PublicationRecord(
                        self.source,
                        title,
                        year,
                        doi,
                        url,
                        authors,
                        msc,
                        source_id=source_id,
                        author_ids=author_ids,
                        arxiv_id=arxiv_id,
                        zbmath_id=source_id,
                        venue=_string_value(item.get("source")),
                        publication_date=norm_text(item.get("publication_date")),
                        raw_ref=f"zbmath:{source_id}" if source_id else "",
                    )
                )
            if len(items) < 100:
                break
        else:
            truncated = bool(items)
        dedup: dict[tuple[str, str], PublicationRecord] = {}
        for record in records:
            dedup[(record.source_id, norm_text(record.title).casefold())] = record
        records = list(dedup.values())
        self.last_work_metadata = {
            "pages": pages,
            "raw_count": raw_count,
            "accepted_count": len(records),
            "truncated": truncated,
        }
        return tuple(records)

    @staticmethod
    def _candidate_names(candidate: dict[str, Any]) -> set[str]:
        names = {norm_text(candidate.get("name"))}
        names.update(norm_text(item.get("name")) for item in candidate.get("further_spellings") or [])
        return {normalized_name(name) for name in names if name}

    def collect(
        self,
        row: dict[str, Any],
        *,
        start_year: int,
        end_year: int,
        discovery_only: bool = False,
    ) -> PublicationEvidenceResult:
        if norm_text(row.get("论文身份审核状态")).casefold() == "rejected":
            return PublicationEvidenceResult(
                self.source,
                "identity_rejected",
                reason="教师级私有 override 已明确拒绝该外部身份候选",
            )
        names = list(identity_query_names(row))
        if not names:
            return PublicationEvidenceResult(self.source, "missing_identity_seed", reason="教师姓名为空")
        try:
            confirmed_code = norm_text(row.get("zbMATH作者ID"))
            if confirmed_code:
                if discovery_only:
                    return PublicationEvidenceResult(
                        self.source,
                        "identity_confirmed",
                        "high",
                        confirmed_code,
                        f"https://zbmath.org/authors/?q=ai:{quote(confirmed_code)}",
                        norm_text(row.get("ORCID")).replace("https://orcid.org/", ""),
                        reason="使用教师级私有覆盖或既有证据中的 zbMATH author ID",
                        metadata={"discovery_only": True, "candidate_count": 1},
                    )
                works = self._works(confirmed_code, start_year, end_year)
                return PublicationEvidenceResult(
                    self.source,
                    "success" if works else "no_recent_record",
                    "high",
                    confirmed_code,
                    f"https://zbmath.org/authors/?q=ai:{quote(confirmed_code)}",
                    norm_text(row.get("ORCID")).replace("https://orcid.org/", ""),
                    works=works,
                    reason=(
                        "使用已确认 zbMATH author ID 拉取当前窗口论文"
                        if works
                        else "已确认 zbMATH author ID，但当前年份窗口内没有论文记录"
                    ),
                    metadata={"confirmed_source_id": True, **self.last_work_metadata},
                )
            candidates: list[dict[str, Any]] = []
            for name in names:
                candidates.extend(self._authors(name))
            unique = {norm_text(item.get("code")): item for item in candidates if item.get("code")}
            candidates = list(unique.values())
            rejected_ids = _rejected_ids(row, "拒绝zbMATH作者ID")
            rejected_candidates = [
                item for item in candidates if norm_text(item.get("code")).casefold() in rejected_ids
            ]
            candidates = [
                item for item in candidates if norm_text(item.get("code")).casefold() not in rejected_ids
            ]
            if not candidates:
                if rejected_candidates:
                    rejected_rows = tuple(
                        PublicationAuthorCandidate(
                            source=self.source,
                            author_id=norm_text(item.get("code")),
                            display_name=norm_text(item.get("name")),
                            decision="rejected",
                            conflicts=("private_override_rejected_source_id",),
                            reason="教师级私有 override 已拒绝该 zbMATH author ID",
                        )
                        for item in rejected_candidates
                    )
                    return PublicationEvidenceResult(
                        self.source,
                        "identity_rejected",
                        reason="所有召回的 zbMATH 作者候选均已被教师级私有 override 拒绝",
                        identity_status="rejected",
                        author_candidates=rejected_rows,
                    )
                return PublicationEvidenceResult(
                    self.source,
                    "no_candidate",
                    reason="zbMATH 未找到作者候选；该状态不代表作者没有论文",
                )
            official = official_publications(row)
            official_homepages = {norm_text(row.get("个人主页")), norm_text(row.get("教师主页链接"))}
            official_orcid = norm_text(row.get("ORCID")).replace("https://orcid.org/", "")
            scored: list[tuple[int, int, bool, bool, dict[str, Any], tuple[PublicationRecord, ...], str]] = []
            requested_names = {normalized_name(name) for name in names}
            for candidate in candidates[:5]:
                code = norm_text(candidate.get("code"))
                works = () if discovery_only else self._works(code, start_year, end_year)
                overlap = title_overlap(official, works)
                score = 4 if requested_names & self._candidate_names(candidate) else 0
                external = candidate.get("external_ids") or []
                orcid = next((norm_text(item.get("external_id")) for item in external if item.get("type") == "orcid"), "")
                homepages = {norm_text(item.get("external_id")) for item in external if item.get("type") == "homepage"}
                strong_signal = False
                conflict = bool(official_orcid and orcid and orcid != official_orcid)
                if official_orcid and orcid == official_orcid:
                    score += 12
                    strong_signal = True
                if any(homepage and homepage in official_homepages for homepage in homepages):
                    score += 10
                    strong_signal = True
                score += min(overlap, 3) * 5
                strong_signal = strong_signal or overlap >= 2
                if conflict:
                    score -= 100
                scored.append((score, overlap, strong_signal, conflict, candidate, works, orcid))
            scored.sort(key=lambda item: (item[0], item[1], len(item[5])), reverse=True)
            score, overlap, strong_signal, conflict, candidate, works, orcid = scored[0]
            ambiguous = len(scored) > 1 and score - scored[1][0] < 3 and not strong_signal
            confidence = (
                "high"
                if strong_signal or score >= 12
                else "medium"
                if score >= 8 and overlap >= 1 and not ambiguous
                else "low"
            )
            code = norm_text(candidate.get("code"))
            fields = tuple(norm_text(item.get("field")) for item in candidate.get("main_fields") or [] if item.get("field"))
            if conflict:
                status = "identity_rejected"
            elif discovery_only:
                status = "identity_confirmed" if confidence == "high" else "identity_uncertain"
            elif confidence in {"high", "medium"}:
                status = "success" if works else "no_recent_record"
            else:
                status = "identity_uncertain"
            reason = f"姓名/外部标识/官网论文交叉得分 {score}，官网题名重合 {overlap}"
            if discovery_only:
                reason += "；当前仅执行有界作者候选发现，未拉取论文"
            if conflict:
                reason += "；ORCID 与官方身份种子冲突，候选已拒绝"
            elif ambiguous:
                reason += "；前两名候选证据接近，保留人工复核"
            if status == "no_recent_record":
                reason += "；作者身份已达到门槛，但当前年份窗口内没有论文记录"
            candidate_rows: list[PublicationAuthorCandidate] = []
            for candidate_score, candidate_overlap, candidate_strong, candidate_conflict, raw_candidate, _, candidate_orcid in scored:
                candidate_code = norm_text(raw_candidate.get("code"))
                signals = []
                if requested_names & self._candidate_names(raw_candidate):
                    signals.append("name")
                if official_orcid and candidate_orcid == official_orcid:
                    signals.append("orcid")
                if candidate_overlap:
                    signals.append(f"official_title_overlap:{candidate_overlap}")
                conflicts = ("orcid_mismatch",) if candidate_conflict else ()
                candidate_decision = (
                    "rejected"
                    if candidate_conflict
                    else "confirmed"
                    if candidate_strong
                    else "probable"
                    if candidate_score >= 8 and candidate_overlap >= 1
                    else "review"
                )
                candidate_rows.append(
                    PublicationAuthorCandidate(
                        source=self.source,
                        author_id=candidate_code,
                        display_name=norm_text(raw_candidate.get("name")),
                        author_url=f"https://zbmath.org/authors/?q=ai:{quote(candidate_code)}",
                        orcid=candidate_orcid,
                        aliases=tuple(
                            norm_text(item.get("name"))
                            for item in raw_candidate.get("further_spellings") or []
                            if item.get("name")
                        ),
                        score=candidate_score,
                        signals=tuple(signals),
                        conflicts=conflicts,
                        decision=candidate_decision,
                        reason=f"score={candidate_score}; title_overlap={candidate_overlap}",
                    )
                )
            candidate_rows.extend(
                PublicationAuthorCandidate(
                    source=self.source,
                    author_id=norm_text(item.get("code")),
                    display_name=norm_text(item.get("name")),
                    decision="rejected",
                    conflicts=("private_override_rejected_source_id",),
                    reason="教师级私有 override 已拒绝该 zbMATH author ID",
                )
                for item in rejected_candidates
            )
            return PublicationEvidenceResult(
                self.source,
                status,
                confidence,
                code,
                f"https://zbmath.org/authors/?q=ai:{quote(code)}",
                orcid,
                fields,
                works,
                reason,
                {
                    "discovery_only": discovery_only,
                    "candidate_count": len(candidates),
                    **({} if discovery_only else self.last_work_metadata),
                },
                identity_status=(
                    "rejected"
                    if status == "identity_rejected"
                    else "confirmed"
                    if confidence == "high"
                    else "probable"
                    if confidence == "medium"
                    else "review"
                ),
                author_candidates=tuple(candidate_rows),
            )
        except PublicationTermsRequired as exc:
            return PublicationEvidenceResult(self.source, "terms_required", reason=str(exc))
        except PublicationSchemaChanged as exc:
            return PublicationEvidenceResult(self.source, "schema_changed", reason=str(exc))
        except PublicationRequestFailed as exc:
            return PublicationEvidenceResult(self.source, "request_failed", reason=str(exc))
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            return PublicationEvidenceResult(self.source, "request_failed", reason=f"{type(exc).__name__}: {exc}")


class OpenAlexAdapter:
    source = "openalex"
    base_url = "https://api.openalex.org"
    cache_version = "openalex-v3-candidate-vector"

    def __init__(self, session: requests.Session | None = None, api_key: str | None = None) -> None:
        self.session = session or requests.Session()
        self.api_key = api_key if api_key is not None else os.environ.get("OPENALEX_API_KEY", "").strip()
        self.http = PublicationHttpClient(self.session, source=self.source)
        self.max_work_pages = max(1, int(os.environ.get("OPENALEX_MAX_WORK_PAGES", "3")))
        self.last_work_metadata: dict[str, Any] = {}

    def _params(self, **values: Any) -> dict[str, Any]:
        return {**values, "api_key": self.api_key}

    def _authors(self, name: str) -> list[dict[str, Any]]:
        data = self.http.get_json(
            f"{self.base_url}/authors",
            params=self._params(search=name, per_page=10),
            timeout=(10.0, 35.0),
            expected_keys=("results",),
        )
        return list(data.get("results") or [])

    def _works(self, author_id: str, start_year: int, end_year: int) -> tuple[PublicationRecord, ...]:
        short_id = author_id.rsplit("/", 1)[-1]
        records: list[PublicationRecord] = []
        cursor = "*"
        pages = 0
        raw_count = 0
        truncated = False
        for _ in range(self.max_work_pages):
            data = self.http.get_json(
                f"{self.base_url}/works",
                params=self._params(
                    filter=f"authorships.author.id:{short_id},publication_year:{start_year}-{end_year}",
                    sort="publication_date:desc",
                    per_page=100,
                    cursor=cursor,
                    select=(
                        "id,doi,display_name,publication_year,publication_date,type,authorships,"
                        "topics,primary_topic,primary_location,ids"
                    ),
                ),
                timeout=(10.0, 45.0),
                expected_keys=("results",),
            )
            items = list(data.get("results") or [])
            pages += 1
            raw_count += len(items)
            for item in items:
                title = norm_text(item.get("display_name") or item.get("title"))
                if not title:
                    continue
                authorship_entries = item.get("authorships") or []
                authors = tuple(
                    norm_text((authorship.get("author") or {}).get("display_name"))
                    for authorship in authorship_entries
                    if (authorship.get("author") or {}).get("display_name")
                )
                author_ids = tuple(
                    norm_text((authorship.get("author") or {}).get("id")).rsplit("/", 1)[-1]
                    for authorship in authorship_entries
                    if (authorship.get("author") or {}).get("id")
                )
                affiliations = tuple(
                    norm_text(institution.get("display_name"))
                    for authorship in authorship_entries
                    for institution in authorship.get("institutions") or []
                    if institution.get("display_name")
                )
                topics = tuple(
                    norm_text(topic.get("display_name"))
                    for topic in item.get("topics") or []
                    if topic.get("display_name")
                )
                primary = item.get("primary_topic") or {}
                if primary.get("display_name") and norm_text(primary.get("display_name")) not in topics:
                    topics = (norm_text(primary.get("display_name")), *topics)
                openalex_id = norm_text(item.get("id")).rsplit("/", 1)[-1]
                ids = item.get("ids") or {}
                venue = norm_text(((item.get("primary_location") or {}).get("source") or {}).get("display_name"))
                records.append(
                    PublicationRecord(
                        self.source,
                        title,
                        int(item["publication_year"]) if item.get("publication_year") else None,
                        norm_text(item.get("doi")),
                        norm_text(item.get("id")),
                        authors,
                        (),
                        topics[:8],
                        source_id=openalex_id,
                        author_ids=author_ids,
                        affiliations=affiliations,
                        arxiv_id=norm_text(ids.get("arxiv")),
                        openalex_id=openalex_id,
                        venue=venue,
                        publication_date=norm_text(item.get("publication_date")),
                        is_preprint=norm_text(item.get("type")).casefold() == "preprint",
                        raw_ref=f"openalex:{openalex_id}" if openalex_id else "",
                    )
                )
            next_cursor = norm_text((data.get("meta") or {}).get("next_cursor"))
            if not next_cursor or not items:
                break
            cursor = next_cursor
        else:
            truncated = bool(cursor and items)
        dedup = {record.source_id or norm_text(record.title).casefold(): record for record in records}
        records = list(dedup.values())
        self.last_work_metadata = {
            "pages": pages,
            "raw_count": raw_count,
            "accepted_count": len(records),
            "truncated": truncated,
        }
        return tuple(records)

    def collect(
        self,
        row: dict[str, Any],
        *,
        start_year: int,
        end_year: int,
        discovery_only: bool = False,
    ) -> PublicationEvidenceResult:
        if norm_text(row.get("论文身份审核状态")).casefold() == "rejected":
            return PublicationEvidenceResult(
                self.source,
                "identity_rejected",
                reason="教师级私有 override 已明确拒绝该外部身份候选",
            )
        if not self.api_key:
            return PublicationEvidenceResult(self.source, "not_configured", reason="OPENALEX_API_KEY 未配置")
        names = list(identity_query_names(row))
        if not names:
            return PublicationEvidenceResult(self.source, "missing_identity_seed", reason="教师姓名为空")
        try:
            confirmed_id = norm_text(row.get("OpenAlex作者ID"))
            if confirmed_id:
                author_url = confirmed_id if confirmed_id.startswith("http") else f"https://openalex.org/{confirmed_id}"
                short_id = author_url.rsplit("/", 1)[-1]
                if discovery_only:
                    return PublicationEvidenceResult(
                        self.source,
                        "identity_confirmed",
                        "high",
                        short_id,
                        author_url,
                        norm_text(row.get("ORCID")).replace("https://orcid.org/", ""),
                        reason="使用教师级私有覆盖或既有证据中的 OpenAlex author ID",
                        metadata={"discovery_only": True, "candidate_count": 1},
                    )
                works = self._works(short_id, start_year, end_year)
                topics = tuple(dict.fromkeys(topic for work in works for topic in work.topics))[:12]
                return PublicationEvidenceResult(
                    self.source,
                    "success" if works else "no_recent_record",
                    "high",
                    short_id,
                    author_url,
                    norm_text(row.get("ORCID")).replace("https://orcid.org/", ""),
                    topics,
                    works,
                    (
                        "使用已确认 OpenAlex author ID 拉取当前窗口论文"
                        if works
                        else "已确认 OpenAlex author ID，但当前年份窗口内没有论文记录"
                    ),
                    {"confirmed_source_id": True, **self.last_work_metadata},
                )
            candidates: list[dict[str, Any]] = []
            for name in names:
                candidates.extend(self._authors(name))
            unique = {norm_text(item.get("id")): item for item in candidates if item.get("id")}
            candidates = list(unique.values())
            rejected_ids = _rejected_ids(row, "拒绝OpenAlex作者ID")
            rejected_candidates = [
                item
                for item in candidates
                if norm_text(item.get("id")).casefold().rsplit("/", 1)[-1] in rejected_ids
            ]
            candidates = [
                item
                for item in candidates
                if norm_text(item.get("id")).casefold().rsplit("/", 1)[-1] not in rejected_ids
            ]
            if not candidates:
                if rejected_candidates:
                    rejected_rows = tuple(
                        PublicationAuthorCandidate(
                            source=self.source,
                            author_id=norm_text(item.get("id")).rsplit("/", 1)[-1],
                            display_name=norm_text(item.get("display_name")),
                            author_url=norm_text(item.get("id")),
                            decision="rejected",
                            conflicts=("private_override_rejected_source_id",),
                            reason="教师级私有 override 已拒绝该 OpenAlex author ID",
                        )
                        for item in rejected_candidates
                    )
                    return PublicationEvidenceResult(
                        self.source,
                        "identity_rejected",
                        reason="所有召回的 OpenAlex 作者候选均已被教师级私有 override 拒绝",
                        identity_status="rejected",
                        author_candidates=rejected_rows,
                    )
                return PublicationEvidenceResult(
                    self.source,
                    "no_candidate",
                    reason="OpenAlex 未找到作者候选；该状态不代表作者没有论文",
                )
            requested = {normalized_name(name) for name in names}
            official = official_publications(row)
            official_orcid = norm_text(row.get("ORCID")).replace("https://orcid.org/", "")
            affiliation_terms = _affiliation_terms(row)
            scored: list[tuple[int, int, bool, bool, dict[str, Any], tuple[PublicationRecord, ...]]] = []
            for candidate in candidates[:5]:
                works = () if discovery_only else self._works(norm_text(candidate.get("id")), start_year, end_year)
                overlap = title_overlap(official, works)
                score = 4 if normalized_name(candidate.get("display_name")) in requested else 0
                orcid = norm_text(candidate.get("orcid")).replace("https://orcid.org/", "")
                strong_signal = False
                conflict = bool(official_orcid and orcid and orcid != official_orcid)
                if official_orcid and orcid == official_orcid:
                    score += 12
                    strong_signal = True
                affiliation_text = " ".join(
                    norm_text((entry.get("institution") or {}).get("display_name"))
                    for entry in candidate.get("affiliations") or candidate.get("last_known_institutions") or []
                ).lower()
                if any(
                    term in affiliation_text or affiliation_text in term
                    for term in affiliation_terms
                    if len(term) >= 3 and affiliation_text
                ):
                    score += 5
                score += min(overlap, 3) * 5
                strong_signal = strong_signal or overlap >= 2
                if conflict:
                    score -= 100
                scored.append((score, overlap, strong_signal, conflict, candidate, works))
            scored.sort(key=lambda item: (item[0], item[1], len(item[5])), reverse=True)
            score, overlap, strong_signal, conflict, candidate, works = scored[0]
            ambiguous = len(scored) > 1 and score - scored[1][0] < 3 and not strong_signal
            confidence = (
                "high"
                if strong_signal or score >= 12
                else "medium"
                if score >= 9 and not ambiguous
                else "low"
            )
            if conflict:
                status = "identity_rejected"
            elif discovery_only:
                status = "identity_probable" if confidence == "medium" else "identity_confirmed" if confidence == "high" else "identity_uncertain"
            elif confidence in {"high", "medium"}:
                status = "success" if works else "no_recent_record"
            else:
                status = "identity_uncertain"
            topics = tuple(dict.fromkeys(topic for work in works for topic in work.topics))[:12]
            reason = f"姓名/机构/官网论文交叉得分 {score}，官网题名重合 {overlap}"
            if discovery_only:
                reason += "；当前仅执行有界作者候选发现，未拉取论文"
            if conflict:
                reason += "；ORCID 与官方身份种子冲突，候选已拒绝"
            elif ambiguous:
                reason += "；前两名候选证据接近，保留人工复核"
            if status == "no_recent_record":
                reason += "；作者身份已达到门槛，但当前年份窗口内没有论文记录"
            candidate_rows: list[PublicationAuthorCandidate] = []
            for candidate_score, candidate_overlap, candidate_strong, candidate_conflict, raw_candidate, _ in scored:
                raw_orcid = norm_text(raw_candidate.get("orcid")).replace("https://orcid.org/", "")
                raw_affiliations = tuple(
                    norm_text((entry.get("institution") or {}).get("display_name"))
                    for entry in raw_candidate.get("affiliations") or raw_candidate.get("last_known_institutions") or []
                    if (entry.get("institution") or {}).get("display_name")
                )
                signals = []
                if normalized_name(raw_candidate.get("display_name")) in requested:
                    signals.append("name")
                if official_orcid and raw_orcid == official_orcid:
                    signals.append("orcid")
                if any(
                    term in " ".join(raw_affiliations).casefold()
                    for term in affiliation_terms
                    if len(term) >= 3
                ):
                    signals.append("affiliation")
                if candidate_overlap:
                    signals.append(f"official_title_overlap:{candidate_overlap}")
                conflicts = ("orcid_mismatch",) if candidate_conflict else ()
                candidate_decision = (
                    "rejected"
                    if candidate_conflict
                    else "confirmed"
                    if candidate_strong
                    else "probable"
                    if candidate_score >= 9 and len(signals) >= 2
                    else "review"
                )
                raw_id = norm_text(raw_candidate.get("id"))
                candidate_rows.append(
                    PublicationAuthorCandidate(
                        source=self.source,
                        author_id=raw_id.rsplit("/", 1)[-1],
                        display_name=norm_text(raw_candidate.get("display_name")),
                        author_url=raw_id,
                        orcid=raw_orcid,
                        affiliations=raw_affiliations,
                        score=candidate_score,
                        signals=tuple(signals),
                        conflicts=conflicts,
                        decision=candidate_decision,
                        reason=f"score={candidate_score}; title_overlap={candidate_overlap}",
                    )
                )
            candidate_rows.extend(
                PublicationAuthorCandidate(
                    source=self.source,
                    author_id=norm_text(item.get("id")).rsplit("/", 1)[-1],
                    display_name=norm_text(item.get("display_name")),
                    author_url=norm_text(item.get("id")),
                    decision="rejected",
                    conflicts=("private_override_rejected_source_id",),
                    reason="教师级私有 override 已拒绝该 OpenAlex author ID",
                )
                for item in rejected_candidates
            )
            return PublicationEvidenceResult(
                self.source,
                status,
                confidence,
                norm_text(candidate.get("id")).rsplit("/", 1)[-1],
                norm_text(candidate.get("id")),
                norm_text(candidate.get("orcid")).replace("https://orcid.org/", ""),
                topics,
                works,
                reason,
                {
                    "discovery_only": discovery_only,
                    "candidate_count": len(candidates),
                    **({} if discovery_only else self.last_work_metadata),
                },
                identity_status=(
                    "rejected"
                    if status == "identity_rejected"
                    else "confirmed"
                    if confidence == "high"
                    else "probable"
                    if confidence == "medium"
                    else "review"
                ),
                author_candidates=tuple(candidate_rows),
            )
        except PublicationTermsRequired as exc:
            return PublicationEvidenceResult(self.source, "terms_required", reason=str(exc))
        except PublicationSchemaChanged as exc:
            return PublicationEvidenceResult(self.source, "schema_changed", reason=str(exc))
        except PublicationRequestFailed as exc:
            return PublicationEvidenceResult(self.source, "request_failed", reason=str(exc))
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            return PublicationEvidenceResult(self.source, "request_failed", reason=f"{type(exc).__name__}: {exc}")
