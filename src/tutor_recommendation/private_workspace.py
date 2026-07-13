from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ROOT = PROJECT_ROOT / "user_private"
SOURCE_DIR = PRIVATE_ROOT / "source"
PROFILE_DIR = PRIVATE_ROOT / "profile"
OVERRIDES_DIR = PRIVATE_ROOT / "overrides"
PROFILE_PATH = PROFILE_DIR / "student_profile.json"
LEGACY_PROFILE_PATH = PROJECT_ROOT / "data/private/student_profile.json"
DRAFT_PROFILE_PATH = PROFILE_DIR / "student_profile.draft.json"
REQUEST_PATH = PRIVATE_ROOT / "request.md"
REQUEST_EXAMPLE_PATH = PRIVATE_ROOT / "request.example.md"
PROFILE_TEMPLATE_PATH = PROJECT_ROOT / "data/templates/student_profile.example.json"
SUPPORTED_SOURCE_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".json"}


def ensure_private_workspace() -> list[Path]:
    created: list[Path] = []
    for directory in (PRIVATE_ROOT, SOURCE_DIR, PROFILE_DIR, OVERRIDES_DIR):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created.append(directory)
    if not REQUEST_PATH.exists() and REQUEST_EXAMPLE_PATH.is_file():
        shutil.copyfile(REQUEST_EXAMPLE_PATH, REQUEST_PATH)
        created.append(REQUEST_PATH)
    return created


def initialize_profile_draft(force: bool = False) -> Path:
    ensure_private_workspace()
    if DRAFT_PROFILE_PATH.exists() and not force:
        return DRAFT_PROFILE_PATH
    template = json.loads(PROFILE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    template["_draft_requires_confirmation"] = True
    template["_note"] = "Coding Agent 画像草稿：确认方向、权重和强信号词后，移除草稿标记并保存为 student_profile.json。"
    DRAFT_PROFILE_PATH.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return DRAFT_PROFILE_PATH


def _extract_pdf(path: Path) -> str:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires PyMuPDF; install requirements.txt first") from exc
    with fitz.open(path) as document:
        return "\n".join(page.get_text("text") for page in document)


def _extract_docx(path: Path) -> str:
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(
            node.text or ""
            for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        ).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_source_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix == ".docx":
        text = _extract_docx(path)
    elif suffix in {".txt", ".md", ".json"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"unsupported private source type: {path.name}")
    return re.sub(r"[ \t]+", " ", text).strip()


def extract_profile_draft(force: bool = False) -> tuple[Path, list[Path]]:
    ensure_private_workspace()
    sources = sorted(
        path for path in SOURCE_DIR.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES
    )
    if not sources:
        raise FileNotFoundError(f"no supported materials found in {SOURCE_DIR}")
    if DRAFT_PROFILE_PATH.exists() and not force:
        raise FileExistsError(f"draft already exists: {DRAFT_PROFILE_PATH}; use --force to replace it")

    extracted: list[str] = []
    for source in sources:
        text = extract_source_text(source)
        if text:
            extracted.append(f"[{source.name}]\n{text}")
    if not extracted:
        raise RuntimeError("private materials were found but no readable text could be extracted")

    template = json.loads(PROFILE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    template.update(
        {
            "_draft_requires_confirmation": True,
            "_draft_source_files": [str(path.relative_to(PRIVATE_ROOT)) for path in sources],
            "_note": "草稿不能用于正式匹配。Coding Agent 必须提炼背景、调整关键词权重并让用户确认。",
            "resume_match_context": "\n\n".join(extracted)[:50000],
        }
    )
    DRAFT_PROFILE_PATH.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return DRAFT_PROFILE_PATH, sources
