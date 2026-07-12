from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import secrets
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd

from .contact_status import (
    CONTACT_STATUS_PATH,
    STATUS_COLUMN,
    contact_entry_from_store,
    empty_store,
    has_status_entry,
    load_status_store,
    normalize_contact_entry,
    save_status_store,
    row_key as contact_row_key,
)
from .teacher_match_targets import TARGETS, TargetConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIEWER_DIR = PROJECT_ROOT / "viewer"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
STATUS_STORE_PATH = (PROJECT_ROOT / CONTACT_STATUS_PATH).resolve()
STATUS_LOCK = Lock()
DATA_CACHE_LOCK = Lock()
DATA_CACHE: dict[str, Any] = {"signature": None, "payload": None}
DETAIL_CACHE_LOCK = Lock()
DETAIL_CACHE: dict[str, dict[str, Any]] = {}
CSRF_TOKEN = secrets.token_urlsafe(32)
VIEWER_API_VERSION = 4
MAX_JSON_BYTES = 2 * 1024 * 1024
SUMMARY_CACHE_VERSION = 1
SUMMARY_CACHE_PATH = OUTPUTS_DIR / ".viewer_summary_cache.json"
FINAL_SHEET = "全量教师名录"
DETAIL_SHEETS = {
    "dblp": ["DBLP近三年明细", "DBLP近三年论文明细"],
    "arxiv": ["arXiv近三年明细"],
    "web": ["网页证据明细"],
    "webSearch": ["WebSearch证据明细"],
}


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    return normalized == "localhost" or normalized == "::1" or normalized.startswith("127.")


def request_host_is_allowed(host_header: str) -> bool:
    if not host_header:
        return False
    parsed = urlparse(f"//{host_header}")
    return bool(parsed.hostname and is_loopback_host(parsed.hostname))


def request_origin_is_allowed(origin: str, host_header: str) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not is_loopback_host(parsed.hostname):
        return False
    origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = urlparse(f"//{host_header}")
    host_port = host.port or 80
    return origin_port == host_port


def norm_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def clean_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def clean_record(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): clean_value(value) for key, value in row.items()}


def target_key(target: TargetConfig) -> str:
    return f"{target.school_slug}/{target.college_slug}"


def record_key(target: TargetConfig, raw: dict[str, Any]) -> str:
    return contact_row_key(target.school_slug, target.college_slug, raw)


def same_teacher(item: dict[str, Any], raw: dict[str, Any]) -> bool:
    if norm_text(item.get("姓名")) != norm_text(raw.get("姓名")):
        return False
    item_teacher_url = norm_text(item.get("教师主页链接"))
    teacher_url = norm_text(raw.get("教师主页链接"))
    return not item_teacher_url or not teacher_url or item_teacher_url == teacher_url


def detail_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        indexed.setdefault(norm_text(row.get("姓名")), []).append(row)
    return indexed


def matching_details(indexed: dict[str, list[dict[str, Any]]], raw: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = indexed.get(norm_text(raw.get("姓名")), [])
    return [item for item in candidates if same_teacher(item, raw)]


def read_sheet(path: Path, sheet_name: str) -> list[dict[str, Any]]:
    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except ValueError:
        return []
    return [clean_record(row) for row in df.to_dict("records")]


def read_detail_groups(path: Path) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for key, sheet_names in DETAIL_SHEETS.items():
        rows: list[dict[str, Any]] = []
        for sheet_name in sheet_names:
            rows.extend(read_sheet(path, sheet_name))
        groups[key] = rows
    return groups


def store_contact_entry_for_row(store: dict[str, Any], target: TargetConfig, raw: dict[str, Any], row_key: str) -> dict[str, Any]:
    if has_status_entry(store, row_key):
        return contact_entry_from_store(store, row_key)
    statuses = store.get("statuses", {})
    if not isinstance(statuses, dict):
        return {}
    name = norm_text(raw.get("姓名"))
    prefix = f"{target_key(target)}|{name}|"
    candidates = [
        normalize_contact_entry(value)
        for key, value in statuses.items()
        if norm_text(key).startswith(prefix)
    ]
    candidates = [entry for entry in candidates if entry]
    return candidates[0] if len(candidates) == 1 else {}


def workbook_signature() -> tuple[tuple[str, str, Any, Any], ...]:
    signature: list[tuple[str, str, Any, Any]] = []
    for key in TARGETS:
        target = TARGETS[key]
        path = (PROJECT_ROOT / target.final_path).resolve()
        try:
            stat = path.stat()
        except FileNotFoundError:
            signature.append((key, str(target.final_path), None, None))
            continue
        signature.append((key, str(target.final_path), stat.st_mtime_ns, stat.st_size))
    return tuple(signature)


def build_base_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in TARGETS:
        target = TARGETS[key]
        final_path = PROJECT_ROOT / target.final_path
        if not final_path.exists():
            continue
        rows = read_sheet(final_path, FINAL_SHEET)
        for raw in rows:
            row_key = record_key(target, raw)
            records.append(
                {
                    "_targetKey": key,
                    "schoolSlug": target.school_slug,
                    "collegeSlug": target.college_slug,
                    "schoolName": target.school_name,
                    "collegeName": target.college_name,
                    "sourcePath": str(target.final_path),
                    "raw": raw,
                    "key": row_key,
                }
            )
    return records


def load_summary_cache(signature: tuple[tuple[str, str, Any, Any], ...]) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(SUMMARY_CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if payload.get("version") != SUMMARY_CACHE_VERSION:
        return None
    if payload.get("signature") != [list(item) for item in signature]:
        return None
    records = payload.get("records")
    return records if isinstance(records, list) else None


def save_summary_cache(signature: tuple[tuple[str, str, Any, Any], ...], records: list[dict[str, Any]]) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SUMMARY_CACHE_VERSION,
        "signature": [list(item) for item in signature],
        "records": records,
    }
    temp_path = SUMMARY_CACHE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp_path.replace(SUMMARY_CACHE_PATH)


def base_records() -> list[dict[str, Any]]:
    signature = workbook_signature()
    cached = load_summary_cache(signature)
    if cached is not None:
        return cached
    records = build_base_records()
    try:
        save_summary_cache(signature, records)
    except OSError:
        pass
    return records


def build_records() -> list[dict[str, Any]]:
    store = load_status_store(STATUS_STORE_PATH)
    records: list[dict[str, Any]] = []
    for base in base_records():
        target_name = norm_text(base.get("_targetKey"))
        target = TARGETS.get(target_name)
        if target is None:
            continue
        raw = dict(base.get("raw") or {})
        row_key = norm_text(base.get("key")) or record_key(target, raw)
        contact = normalize_contact_entry(raw)
        stored_contact = store_contact_entry_for_row(store, target, raw, row_key)
        if stored_contact:
            contact = {**contact, **stored_contact}
        status = norm_text(contact.get("status") or raw.get(STATUS_COLUMN))
        raw[STATUS_COLUMN] = status
        records.append(
            {
                "schoolSlug": base.get("schoolSlug", ""),
                "collegeSlug": base.get("collegeSlug", ""),
                "schoolName": base.get("schoolName", ""),
                "collegeName": base.get("collegeName", ""),
                "sourcePath": base.get("sourcePath", ""),
                "raw": raw,
                "contact": contact,
                "status": status,
                "key": row_key,
            }
        )
    return records


def source_signature() -> tuple[tuple[str, str, Any, Any], ...]:
    signature = list(workbook_signature())
    try:
        status_stat = STATUS_STORE_PATH.stat()
    except FileNotFoundError:
        signature.append(("contact_status", str(CONTACT_STATUS_PATH), None, None))
    else:
        signature.append(("contact_status", str(CONTACT_STATUS_PATH), status_stat.st_mtime_ns, status_stat.st_size))
    return tuple(signature)


def detail_indexes_for_path(path: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    stat = path.stat()
    signature = (stat.st_mtime_ns, stat.st_size)
    cache_key = str(path.resolve())
    with DETAIL_CACHE_LOCK:
        cached = DETAIL_CACHE.get(cache_key)
        if cached and cached.get("signature") == signature:
            return cached["indexes"]
        groups = read_detail_groups(path)
        indexes = {name: detail_index(items) for name, items in groups.items()}
        DETAIL_CACHE[cache_key] = {"signature": signature, "indexes": indexes}
        return indexes


def detail_payload(row_key: str) -> dict[str, Any] | None:
    record = next((item for item in data_payload()["records"] if item.get("key") == row_key), None)
    if record is None:
        return None
    source_path = Path(norm_text(record.get("sourcePath")))
    path = source_path if source_path.is_absolute() else PROJECT_ROOT / source_path
    if not path.is_file():
        return None
    indexes = detail_indexes_for_path(path)
    raw = record.get("raw") or {}
    return {
        "key": row_key,
        "dblp": matching_details(indexes["dblp"], raw),
        "arxiv": matching_details(indexes["arxiv"], raw),
        "web": matching_details(indexes["web"], raw),
        "webSearch": matching_details(indexes["webSearch"], raw),
    }


def data_payload() -> dict[str, Any]:
    with DATA_CACHE_LOCK:
        signature = source_signature()
        if DATA_CACHE["signature"] == signature and DATA_CACHE["payload"] is not None:
            return DATA_CACHE["payload"]
        payload = {
            "records": build_records(),
            "statusStore": status_store_for_response(),
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        DATA_CACHE["signature"] = signature
        DATA_CACHE["payload"] = payload
        return payload


def status_store_for_response() -> dict[str, Any]:
    return load_status_store(STATUS_STORE_PATH) if STATUS_STORE_PATH.exists() else empty_store()


def save_contact_entry(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    with STATUS_LOCK:
        store = status_store_for_response()
        statuses = store.setdefault("statuses", {})
        normalized = normalize_contact_entry(entry)
        if normalized:
            normalized["updated_at"] = datetime.now().isoformat(timespec="seconds")
            statuses[key] = normalized
        else:
            statuses.pop(key, None)
        save_status_store(store, STATUS_STORE_PATH)
        return status_store_for_response()


class ViewerHandler(SimpleHTTPRequestHandler):
    server_version = "TeacherViewer/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.write_json({"ok": True, "apiVersion": VIEWER_API_VERSION})
            return
        if parsed.path == "/api/session":
            self.write_json({"token": CSRF_TOKEN, "apiVersion": VIEWER_API_VERSION})
            return
        if parsed.path == "/api/data":
            self.write_json(data_payload())
            return
        if parsed.path == "/api/detail":
            row_key = norm_text(parse_qs(parsed.query).get("key", [""])[0])
            details = detail_payload(row_key) if row_key else None
            if details is None:
                self.write_json({"error": "teacher detail not found"}, HTTPStatus.NOT_FOUND)
            else:
                self.write_json(details)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not request_host_is_allowed(self.headers.get("Host", "")):
            self.write_json({"error": "invalid host"}, HTTPStatus.FORBIDDEN)
            return
        if not request_origin_is_allowed(self.headers.get("Origin", ""), self.headers.get("Host", "")):
            self.write_json({"error": "cross-origin write request rejected"}, HTTPStatus.FORBIDDEN)
            return
        fetch_site = self.headers.get("Sec-Fetch-Site", "")
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            self.write_json({"error": "cross-site write request rejected"}, HTTPStatus.FORBIDDEN)
            return
        token = self.headers.get("X-Tutor-Viewer-Token", "")
        if not token or not hmac.compare_digest(token, CSRF_TOKEN):
            self.write_json({"error": "invalid viewer token"}, HTTPStatus.FORBIDDEN)
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.write_json({"error": "application/json is required"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            payload = self.read_json()
        except OverflowError:
            self.write_json({"error": "request body is too large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        except (json.JSONDecodeError, ValueError):
            self.write_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self.write_json({"error": "json object is required"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/contact":
            key = norm_text(payload.get("key"))
            entry = payload.get("entry") or {}
            if not key or not isinstance(entry, dict):
                self.write_json({"error": "key and entry are required"}, HTTPStatus.BAD_REQUEST)
                return
            store = save_contact_entry(key, entry)
            self.write_json({"ok": True, "statusStore": store})
            return
        self.write_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def serve_static(self, request_path: str) -> None:
        if request_path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        relative = unquote(request_path.lstrip("/")) or "index.html"
        path = (VIEWER_DIR / relative).resolve()
        if not path.is_file() or VIEWER_DIR not in path.parents:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            mime_type = "text/javascript"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.write_response_body(data)

    def read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length < 0:
            raise ValueError("invalid content length")
        if length > MAX_JSON_BYTES:
            raise OverflowError("request body too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def write_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.write_response_body(raw)

    def write_response_body(self, raw: bytes) -> None:
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            self.log_message("client disconnected before response completed")
        except OSError as exc:
            if getattr(exc, "winerror", None) in {10053, 10054}:
                self.log_message("client disconnected before response completed")
                return
            raise

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[viewer] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the teacher contact dashboard with local outputs APIs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not is_loopback_host(args.host):
        parser.error("the viewer may only listen on localhost/loopback addresses")
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"Teacher viewer: http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
