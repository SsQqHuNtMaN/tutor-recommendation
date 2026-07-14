from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..teacher_match_targets import TargetConfig


PAGE_PATTERN = re.compile(r"^index\d*\.htm$", re.I)
EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


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


def _publication_lines(body: Tag | None) -> list[str]:
    if body is None:
        return []
    lines: list[str] = []
    for node in body.select("p, li"):
        text = norm_text(node.get_text(" ", strip=True))
        if 20 <= len(text) <= 1200 and (YEAR_PATTERN.search(text) or DOI_PATTERN.search(text)):
            if text not in lines:
                lines.append(text)
        if len(lines) >= 40:
            break
    return lines


def _biography_text(body: Tag | None) -> str:
    if body is None:
        return ""
    stop_markers = (
        "selected publications",
        "representative publications",
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
