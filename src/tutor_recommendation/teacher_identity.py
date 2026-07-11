from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TEACHER_ID_COLUMN = "教师ID"
IDENTITY_CONFIDENCE_COLUMN = "身份置信度"


def norm_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ")
    if text.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(value: Any) -> str:
    text = norm_text(value).split(";")[0].strip()
    if not text.startswith(("http://", "https://")):
        return ""
    parsed = urlparse(text)
    if not parsed.netloc:
        return ""
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        )
    )
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            "",
            query,
            "",
        )
    )


def is_generic_url(value: str) -> bool:
    url = normalize_url(value)
    if not url:
        return True
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")
    if path in {"", "/", "/index.htm", "/index.html", "/system/caslogin.jsp"}:
        return True
    if host == "ai.fudan.edu.cn" and re.fullmatch(r"/[^/]+/list\.htm", path):
        return False
    if path.endswith(("/list.htm", "/list.html", "/index.htm")):
        return True
    return False


def extract_emails(value: Any) -> list[str]:
    return sorted(set(re.findall(r"[\w.\-+]+@[\w.\-]+\.\w+", norm_text(value).lower())))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def identity_basis(school_slug: str, college_slug: str, row: Any) -> tuple[str, str]:
    getter = row.get
    for column in ["教师主页链接", "个人主页"]:
        urls: list[str] = []
        for raw in re.split(r"[;；,，\s]+", norm_text(getter(column, ""))):
            url = normalize_url(raw)
            if url and not is_generic_url(url):
                urls.append(url)
        if urls:
            return "url", f"{school_slug}|{sorted(set(urls))[0]}"

    emails = extract_emails(getter("邮箱", ""))
    if emails:
        return "email", f"{school_slug}|{emails[0]}"

    name = re.sub(r"\s+", "", norm_text(getter("姓名", ""))).lower()
    source_url = normalize_url(getter("教师主页链接", "")) or normalize_url(getter("个人主页", ""))
    title = norm_text(getter("职称", "")).lower()
    institute = norm_text(getter("官方系别", "") or getter("名录研究所", "")).lower()
    ordinal = norm_text(getter("名录序号", ""))
    return "provisional", "|".join([school_slug, college_slug, name, source_url, title, institute, ordinal])


def teacher_id_for_row(school_slug: str, college_slug: str, row: Any) -> str:
    existing = norm_text(row.get(TEACHER_ID_COLUMN, ""))
    if existing:
        return existing
    kind, basis = identity_basis(school_slug, college_slug, row)
    prefix = "teacher" if kind != "provisional" else "provisional"
    return f"{prefix}_{_digest(f'{kind}|{basis}')}"


def identity_confidence_for_row(school_slug: str, college_slug: str, row: Any) -> str:
    existing = norm_text(row.get(IDENTITY_CONFIDENCE_COLUMN, ""))
    if existing:
        return existing
    kind, _ = identity_basis(school_slug, college_slug, row)
    return "高" if kind == "url" else "中" if kind == "email" else "低-待复核"


def ensure_teacher_identity(school_slug: str, college_slug: str, row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    output[TEACHER_ID_COLUMN] = teacher_id_for_row(school_slug, college_slug, output)
    output[IDENTITY_CONFIDENCE_COLUMN] = identity_confidence_for_row(school_slug, college_slug, output)
    return output


def teacher_record_key(school_slug: str, college_slug: str, row: Any) -> str:
    return f"{school_slug}/{college_slug}|{teacher_id_for_row(school_slug, college_slug, row)}"
