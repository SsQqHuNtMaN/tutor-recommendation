from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from pypinyin import lazy_pinyin

from .private_paths import private_file
from .publication_evidence import norm_text, normalized_name, official_publications, split_publication_entries
from .teacher_identity import TEACHER_ID_COLUMN, teacher_id_for_row


PUBLICATION_IDENTITY_OVERRIDES_PATH = private_file(
    "publication_identity_overrides.json",
    env_name="PUBLICATION_IDENTITY_OVERRIDES_PATH",
)


def _unique(values: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = norm_text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return tuple(output)


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RuntimeError(f"publication identity override field {field!r} must be a list of strings")
    return _unique(value)


def generated_name_aliases(name: Any, teacher_url: Any = "") -> tuple[str, ...]:
    chinese_name = norm_text(name)
    if not chinese_name or not re.search(r"[\u4e00-\u9fff]", chinese_name):
        return ()
    pinyin = lazy_pinyin(chinese_name)
    if len(pinyin) < 2:
        return ()
    surname = pinyin[0]
    given_joined = "".join(pinyin[1:])
    given_spaced = " ".join(pinyin[1:])
    candidates = [
        f"{given_joined} {surname}",
        f"{given_spaced} {surname}",
        f"{surname} {given_joined}",
        f"{surname} {given_spaced}",
    ]
    slug = Path(urlparse(norm_text(teacher_url)).path).stem
    slug = re.sub(r"\d+$", "", slug.lower())
    if slug and re.fullmatch(r"[a-z]+", slug):
        if slug.startswith(surname) and len(slug) > len(surname):
            given = slug[len(surname) :]
            candidates.extend([f"{given} {surname}", f"{surname} {given}"])
        elif slug.endswith(surname) and len(slug) > len(surname):
            given = slug[: -len(surname)]
            candidates.extend([f"{given} {surname}", f"{surname} {given}"])
    return _unique(candidates)


def official_publication_name_candidates(name: Any, publication_text: Any) -> tuple[str, ...]:
    """Extract only author strings that agree with recall-only Chinese-name transliterations."""
    generated = {
        normalized_name(alias)
        for alias in generated_name_aliases(name)
        if normalized_name(alias)
    }
    if not generated:
        return ()
    candidates: list[str] = []
    pattern = re.compile(
        r"(?<![A-Za-z])((?:[A-Z]\.|[A-Z][A-Za-z'-]+)(?:\s+|,\s*)"
        r"(?:[A-Z]\.|[A-Z][A-Za-z'-]+))(?![A-Za-z])"
    )
    for entry in split_publication_entries(publication_text):
        # Author lists conventionally precede the title; restricting the scan reduces venue false positives.
        prefix = entry[: min(len(entry), 220)]
        for match in pattern.finditer(prefix):
            candidate = norm_text(match.group(1).replace(",", " "))
            if normalized_name(candidate) in generated:
                candidates.append(candidate)
    return _unique(candidates)


@dataclass(frozen=True)
class PublicationIdentitySeed:
    teacher_id: str
    name: str
    canonical_english_name: str = ""
    aliases: tuple[str, ...] = ()
    affiliations: tuple[str, ...] = ()
    homepages: tuple[str, ...] = ()
    orcid: str = ""
    openalex_id: str = ""
    zbmath_author_id: str = ""
    dblp_pid: str = ""
    rejected_openalex_ids: tuple[str, ...] = ()
    rejected_zbmath_author_ids: tuple[str, ...] = ()
    known_titles: tuple[str, ...] = ()
    known_coauthors: tuple[str, ...] = ()
    review_status: str = "automatic"
    evidence: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def query_names(self) -> tuple[str, ...]:
        return _unique([self.canonical_english_name, *self.aliases, self.name])[:2]

    def query_fields(self) -> dict[str, str]:
        return {
            "英文姓名": self.canonical_english_name,
            "英文姓名别名": "; ".join(self.aliases),
            "ORCID": self.orcid,
            "OpenAlex作者ID": self.openalex_id,
            "zbMATH作者ID": self.zbmath_author_id,
            "DBLP PID": self.dblp_pid,
            "拒绝OpenAlex作者ID": "; ".join(self.rejected_openalex_ids),
            "拒绝zbMATH作者ID": "; ".join(self.rejected_zbmath_author_ids),
            "已知论文题名": "；".join(self.known_titles),
            "已知合作者": "; ".join(self.known_coauthors),
            "论文身份机构": "; ".join(self.affiliations),
            "论文身份审核状态": self.review_status,
            "论文身份种子哈希": self.fingerprint,
        }


def load_publication_identity_overrides(
    path: Path = PUBLICATION_IDENTITY_OVERRIDES_PATH,
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"publication identity overrides are unreadable: {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("targets", []), list):
        raise RuntimeError("publication identity overrides must contain a targets list")
    overrides: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(payload.get("targets", [])):
        if not isinstance(raw, dict):
            raise RuntimeError(f"publication identity override targets[{index}] must be an object")
        teacher_id = norm_text(raw.get("teacher_id"))
        if not teacher_id:
            raise RuntimeError(f"publication identity override targets[{index}] requires teacher_id")
        if teacher_id in overrides:
            raise RuntimeError(f"duplicate publication identity override for {teacher_id}")
        source_ids = raw.get("source_ids") or {}
        if not isinstance(source_ids, dict):
            raise RuntimeError(f"publication identity override {teacher_id} source_ids must be an object")
        rejected_source_ids = raw.get("rejected_source_ids") or {}
        if not isinstance(rejected_source_ids, dict):
            raise RuntimeError(f"publication identity override {teacher_id} rejected_source_ids must be an object")
        review_status = norm_text(raw.get("review_status") or "confirmed").lower()
        if review_status not in {"confirmed", "review", "rejected"}:
            raise RuntimeError(f"publication identity override {teacher_id} has invalid review_status")
        evidence = _string_list(raw.get("evidence"), "evidence")
        if review_status in {"confirmed", "rejected"} and not evidence:
            raise RuntimeError(
                f"publication identity override {teacher_id} with {review_status} status requires evidence"
            )
        overrides[teacher_id] = {
            "canonical_english_name": norm_text(raw.get("canonical_english_name")),
            "aliases": _string_list(raw.get("aliases"), "aliases"),
            "affiliations": _string_list(raw.get("affiliations"), "affiliations"),
            "orcid": norm_text(raw.get("orcid")).replace("https://orcid.org/", ""),
            "openalex_id": norm_text(source_ids.get("openalex")),
            "zbmath_author_id": norm_text(source_ids.get("zbmath")),
            "dblp_pid": norm_text(source_ids.get("dblp")),
            "rejected_openalex_ids": _string_list(
                rejected_source_ids.get("openalex"), "rejected_source_ids.openalex"
            ),
            "rejected_zbmath_author_ids": _string_list(
                rejected_source_ids.get("zbmath"), "rejected_source_ids.zbmath"
            ),
            "known_titles": _string_list(raw.get("known_titles"), "known_titles"),
            "known_coauthors": _string_list(raw.get("known_coauthors"), "known_coauthors"),
            "review_status": review_status,
            "evidence": evidence,
        }
    return overrides


def build_publication_identity_seed(
    row: Any,
    *,
    school_slug: str,
    college_slug: str,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> PublicationIdentitySeed:
    teacher_id = teacher_id_for_row(school_slug, college_slug, row)
    override = (overrides or {}).get(teacher_id, {})
    name = norm_text(row.get("姓名"))
    canonical = norm_text(override.get("canonical_english_name") or row.get("英文姓名"))
    generated = generated_name_aliases(name, row.get("教师主页链接"))
    official_name_candidates = official_publication_name_candidates(name, row.get("官方论文列表"))
    aliases = _unique(
        [
            canonical,
            *override.get("aliases", ()),
            *norm_text(row.get("英文姓名别名")).split(";"),
            *official_name_candidates,
            *generated,
        ]
    )
    affiliations = _unique(
        [
            *override.get("affiliations", ()),
            row.get("学院归属"),
            row.get("名录研究所"),
            row.get("主页研究所"),
            row.get("官方系别"),
        ]
    )
    homepages = _unique([row.get("个人主页"), row.get("教师主页链接")])
    official_titles = [record.title for record in official_publications(row) if record.title]
    known_titles = _unique([*override.get("known_titles", ()), *official_titles[:5]])
    return PublicationIdentitySeed(
        teacher_id=teacher_id,
        name=name,
        canonical_english_name=canonical,
        aliases=aliases,
        affiliations=affiliations,
        homepages=homepages,
        orcid=norm_text(override.get("orcid") or row.get("ORCID")).replace("https://orcid.org/", ""),
        openalex_id=norm_text(override.get("openalex_id") or row.get("OpenAlex作者ID")),
        zbmath_author_id=norm_text(override.get("zbmath_author_id") or row.get("zbMATH作者ID")),
        dblp_pid=norm_text(override.get("dblp_pid") or row.get("DBLP PID")),
        rejected_openalex_ids=_unique(override.get("rejected_openalex_ids", ())),
        rejected_zbmath_author_ids=_unique(override.get("rejected_zbmath_author_ids", ())),
        known_titles=known_titles,
        known_coauthors=_unique(override.get("known_coauthors", ())),
        review_status=norm_text(override.get("review_status") or "automatic"),
        evidence=_unique(
            [
                *override.get("evidence", ()),
                *(["official_page:english_name"] if canonical and row.get("英文姓名") else []),
                *(["official_publication:author_name"] if official_name_candidates else []),
            ]
        ),
    )


def identity_query_names(row: Any) -> tuple[str, ...]:
    aliases = [part.strip() for part in norm_text(row.get("英文姓名别名")).split(";") if part.strip()]
    return _unique([row.get("英文姓名"), *aliases, row.get("姓名")])[:2]
