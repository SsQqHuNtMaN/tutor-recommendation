from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..publication_evidence import looks_like_publication_record, split_publication_entries
from ..teacher_match_targets import TargetConfig


PAGE_PATTERN = re.compile(r"^index\d*\.htm$", re.I)
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ENGLISH_NAME_LABEL_PATTERN = re.compile(
    r"(?:英文姓名|英文名|english\s+name)\s*[：:]\s*([A-Za-z][A-Za-z .,'-]{2,60})",
    re.I,
)
ENGLISH_NAME_BLOCK_WORDS = {
    "university",
    "institute",
    "school",
    "college",
    "faculty",
    "department",
    "renmin",
    "china",
    "homepage",
    "profile",
}
PUBLICATION_SECTION_MARKERS = (
    "selected publications",
    "representative publications",
    "publications",
    "论文发表",
    "发表论文",
    "主要论文",
    "代表性论文",
    "代表论文",
    "近年来主要论著",
    "主要论著",
    "近期主要学术成果",
    "主要学术成果",
)
PUBLICATION_STOP_MARKERS = (
    "工作经历",
    "教育经历",
    "任职经历",
    "学习经历",
    "个人经历",
    "奖励",
    "荣誉",
    "获奖",
    "科研项目",
    "研究项目",
    "基金项目",
    "教学项目",
    "社会兼职",
    "主讲课程",
    "讲授课程",
    "招生信息",
)


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ").replace("\xa0", " ")).strip()


def fetch_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 tutor-recommendation/1.0"})
    response.raise_for_status()
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def discover_directory_pages(soup: BeautifulSoup, directory_url: str) -> list[str]:
    parsed_base = urlparse(directory_url)
    pages = {directory_url}
    for anchor in soup.select("a[href]"):
        href = urljoin(directory_url, norm_text(anchor.get("href")))
        parsed = urlparse(href)
        if parsed.netloc != parsed_base.netloc:
            continue
        if parsed.path.rsplit("/", 1)[0] != parsed_base.path.rsplit("/", 1)[0]:
            continue
        if PAGE_PATTERN.fullmatch(parsed.path.rsplit("/", 1)[-1]):
            pages.add(href)

    def page_number(url: str) -> int:
        name = urlparse(url).path.rsplit("/", 1)[-1].lower()
        match = re.fullmatch(r"index(\d*)\.htm", name)
        return int(match.group(1) or 0) if match else 9999

    return sorted(pages, key=lambda item: (page_number(item), item))


def _labeled_value(card: Tag, label: str) -> str:
    for paragraph in card.select("p"):
        text = norm_text(paragraph.get_text(" ", strip=True))
        if text.startswith(label):
            return norm_text(text[len(label) :].lstrip("：:"))
    return ""


def parse_directory_cards(soup: BeautifulSoup, page_url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in soup.select(".sztuanduia"):
        heading = card.select_one("h1")
        link = heading.select_one("a[href]") if heading else None
        name = norm_text((link or heading).get_text(" ", strip=True) if (link or heading) else "")
        name = re.sub(r"^姓名\s*[：:]\s*", "", name)
        if not name:
            continue
        detail_url = urljoin(page_url, norm_text(link.get("href"))) if link else page_url
        title = _labeled_value(card, "职称")
        direction = _labeled_value(card, "研究方向")
        contact = _labeled_value(card, "联系方式")
        email_match = EMAIL_PATTERN.search(contact)
        affiliation_match = re.search(r"[（(]([^（）()]*学院|[^（）()]*研究院)[）)]", title)
        rows.append(
            {
                "姓名": name,
                "英文姓名": "",
                "英文姓名来源": "",
                "职称": title,
                "研究方向": direction,
                "邮箱": email_match.group(0) if email_match else "",
                "教师主页链接": detail_url,
                "个人主页": "",
                "名录研究所": affiliation_match.group(1) if affiliation_match else "",
                "主页研究所": "",
                "所内职务": "",
                "电话": "",
                "地址": "",
                "个人简介摘要": "",
                "官方论文列表": "",
                "官方论文来源": "",
                "抓取状态": "目录已解析",
            }
        )
    return rows


def _personal_homepage(body: Tag | None, detail_url: str) -> str:
    if body is None:
        return ""
    detail_host = urlparse(detail_url).netloc.lower()
    preferred: list[str] = []
    fallback: list[str] = []
    for anchor in body.select("a[href]"):
        href = urljoin(detail_url, norm_text(anchor.get("href")))
        parsed = urlparse(href)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() == detail_host:
            continue
        text = norm_text(anchor.get_text(" ", strip=True)).lower()
        if "个人主页" in text or "homepage" in text:
            preferred.append(href)
        else:
            fallback.append(href)
    return (preferred or fallback or [""])[0]


def _section_prefix(text: str) -> tuple[str, str]:
    lowered = text.lower().strip()
    lowered = re.sub(r"^[一二三四五六七八九十\d]+[、.)）]\s*", "", lowered)
    for kind, markers in (("publication", PUBLICATION_SECTION_MARKERS), ("stop", PUBLICATION_STOP_MARKERS)):
        for marker in markers:
            index = lowered.find(marker)
            if index < 0 or index > 2:
                continue
            end = index + len(marker)
            suffix = lowered[end:]
            if not suffix or suffix[0] in "：:-—" or len(lowered) <= len(marker) + 8:
                return kind, text[end:].lstrip(" ：:-—")
    return "", ""


def _node_chunks(node: Tag) -> list[str]:
    if node.name == "tr":
        cells = [norm_text(cell.get_text(" ", strip=True)) for cell in node.find_all(["th", "td"], recursive=False)]
        joined = " | ".join(cell for cell in cells if cell)
        return [joined] if joined else []
    return [norm_text(part) for part in node.get_text("\n", strip=True).splitlines() if norm_text(part)]


def _node_publication_entries(node: Tag, chunks: list[str]) -> list[str]:
    if not chunks:
        return []
    candidate_chunks = chunks
    if len(chunks) > 1:
        joined = " ".join(chunks)
        individually_valid = [chunk for chunk in chunks if looks_like_publication_record(chunk)]
        # A paragraph broken by <br> commonly separates authors, title and venue.
        # Preserve independently valid numbered rows, otherwise reconstruct the full citation.
        if looks_like_publication_record(joined) and len(individually_valid) <= 1:
            candidate_chunks = [joined]
    entries: list[str] = []
    for chunk in candidate_chunks:
        entries.extend(split_publication_entries(chunk))
    return entries


def _clean_english_person_name(value: Any) -> str:
    text = norm_text(value).strip("-–—|,;：:()[]{}")
    text = re.sub(r"\s+", " ", text)
    tokens = re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?|[A-Z]\.", text)
    if not 2 <= len(tokens) <= 4:
        return ""
    if any(token.casefold().rstrip(".") in ENGLISH_NAME_BLOCK_WORDS for token in tokens):
        return ""
    candidate = " ".join(tokens)
    return candidate if re.fullmatch(r"[A-Za-z][A-Za-z .'-]+", candidate) else ""


def _official_english_name(soup: BeautifulSoup, header: Tag | None, body: Tag | None) -> tuple[str, str]:
    for container, source in ((header, "official_label"), (body, "official_label")):
        if container is None:
            continue
        for node in container.select("p, li"):
            match = ENGLISH_NAME_LABEL_PATTERN.search(norm_text(node.get_text(" ", strip=True)))
            if match:
                candidate = _clean_english_person_name(match.group(1))
                if candidate:
                    return candidate, source
    for selector in ("meta[name='author']", "meta[name='citation_author']"):
        node = soup.select_one(selector)
        candidate = _clean_english_person_name(node.get("content") if node else "")
        if candidate:
            return candidate, "official_meta"
    heading = header.select_one("h1, h2") if header else None
    if heading is not None:
        heading_text = norm_text(heading.get_text(" ", strip=True))
        latin_text = norm_text(re.sub(r"[^A-Za-z .'-]", " ", heading_text))
        candidate = _clean_english_person_name(latin_text)
        if candidate:
            return candidate, "official_heading"
    return "", ""


def _publication_lines(body: Tag | None) -> list[str]:
    if body is None:
        return []
    lines: list[str] = []
    active = False
    nodes = body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr"])
    for node in nodes:
        if node.name in {"p", "li", "tr"} and node.find_parent(["p", "li", "tr"]) is not None:
            continue
        chunks = _node_chunks(node)
        if not chunks:
            continue

        heading_kind = ""
        remainder = ""
        emphasis = node.find(["strong", "b"])
        if emphasis is not None:
            heading_kind, _ = _section_prefix(norm_text(emphasis.get_text(" ", strip=True)))
            if heading_kind:
                emphasized = norm_text(emphasis.get_text(" ", strip=True))
                chunks = [chunk for chunk in chunks if chunk != emphasized]
        if not heading_kind:
            heading_kind, remainder = _section_prefix(chunks[0])
            if heading_kind:
                chunks = chunks[1:]
                if remainder:
                    chunks.insert(0, remainder)

        if heading_kind == "stop":
            active = False
            continue
        if heading_kind == "publication":
            active = True
        if not active:
            continue

        for entry in _node_publication_entries(node, chunks):
            if 12 <= len(entry) <= 1600 and looks_like_publication_record(entry) and entry not in lines:
                lines.append(entry)
        if len(lines) >= 40:
            break
    return lines


def _biography_text(body: Tag | None) -> str:
    if body is None:
        return ""
    stop_markers = (
        "selected publications",
        "representative publications",
        "publications",
        "论文发表",
        "发表论文",
        "主要学术成果",
        "代表性论文",
        "代表论文",
        "近年来主要论著",
        "近期主要学术成果",
    )
    lines: list[str] = []
    for raw_line in body.get_text("\n", strip=True).splitlines():
        text = norm_text(raw_line)
        if not text:
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in stop_markers):
            break
        if YEAR_PATTERN.search(text) and len(text) > 80:
            continue
        lines.append(text)
        if sum(len(item) for item in lines) >= 3000:
            break
    return " ".join(lines)[:3000]


def parse_teacher_detail(soup: BeautifulSoup, row: dict[str, Any]) -> dict[str, Any]:
    detail = dict(row)
    header = soup.select_one(".muyslia")
    body = soup.select_one(".wuyshux")
    if header:
        detail["职称"] = _labeled_value(header, "职称") or detail.get("职称", "")
        detail["研究方向"] = _labeled_value(header, "研究方向") or detail.get("研究方向", "")
        contact = _labeled_value(header, "联系方式")
        email_match = EMAIL_PATTERN.search(contact)
        if email_match:
            detail["邮箱"] = email_match.group(0)
    detail["个人主页"] = _personal_homepage(body, detail["教师主页链接"])
    english_name, english_name_source = _official_english_name(soup, header, body)
    if english_name:
        detail["英文姓名"] = english_name
        detail["英文姓名来源"] = english_name_source
    detail["个人简介摘要"] = _biography_text(body)
    publications = _publication_lines(body)
    detail["官方论文列表"] = "\n".join(publications)
    detail["官方论文来源"] = detail["教师主页链接"] if publications else ""
    detail["主页研究所"] = detail.get("名录研究所", "")
    detail["抓取状态"] = "成功" if header or body else "详情页主内容缺失"
    return detail


def fetch_ruc_isbd_directory(session: requests.Session, config: TargetConfig) -> list[dict[str, Any]]:
    first_soup = fetch_soup(session, config.directory_url)
    page_urls = discover_directory_pages(first_soup, config.directory_url)
    merged: dict[str, dict[str, Any]] = {}
    for page_url in page_urls:
        soup = first_soup if page_url == config.directory_url else fetch_soup(session, page_url)
        for row in parse_directory_cards(soup, page_url):
            merged.setdefault(row["教师主页链接"], row)

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(merged.values(), start=1):
        row["名录序号"] = index
        try:
            detail_soup = fetch_soup(session, row["教师主页链接"])
            row = parse_teacher_detail(detail_soup, row)
        except Exception as exc:  # network failures must remain visible in the workbook
            row["抓取状态"] = f"详情页失败：{type(exc).__name__}: {exc}"
        rows.append(row)
        time.sleep(0.05)
    return rows
