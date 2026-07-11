from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .teacher_identity import TEACHER_ID_COLUMN, teacher_record_key


STATUS_COLUMN = "套磁情况"
CONTACT_DATE_COLUMN = "套磁时间"
CONTACT_RESPONSE_COLUMN = "回复情况"
CONTACT_NOTE_COLUMN = "回复情况备注"
LEGACY_CONTACT_NOTE_COLUMNS = ["套磁备注"]
CONTACT_COLUMNS = [STATUS_COLUMN, CONTACT_DATE_COLUMN, CONTACT_RESPONSE_COLUMN, CONTACT_NOTE_COLUMN]
VALID_CONTACT_STATUSES = ["已套磁", "先不考虑", "不可能", "不匹配"]
LEGACY_STATUS_ALIASES = {"不考虑": "先不考虑"}
DEFAULT_CONTACT_RESPONSES = ["已发", "官回", "添加微信", "约面试", "考核", "已满"]
CONTACT_STATUS_PATH = Path("outputs") / "contact_status.json"
TEACHER_SUMMARY_SHEETS = {"优先套磁名单", "全量教师名录"}


def norm_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def target_key(school_slug: str, college_slug: str) -> str:
    return f"{school_slug}/{college_slug}"


def row_key(school_slug: str, college_slug: str, row: Any) -> str:
    if norm_text(row.get(TEACHER_ID_COLUMN, "")):
        return teacher_record_key(school_slug, college_slug, row)
    return legacy_row_key(school_slug, college_slug, row)


def legacy_row_key(school_slug: str, college_slug: str, row: Any) -> str:
    if isinstance(row, pd.Series):
        name = norm_text(row.get("姓名"))
        teacher_url = norm_text(row.get("教师主页链接"))
        personal_url = norm_text(row.get("个人主页"))
    else:
        name = norm_text(row.get("姓名", ""))
        teacher_url = norm_text(row.get("教师主页链接", ""))
        personal_url = norm_text(row.get("个人主页", ""))
    return "|".join([target_key(school_slug, college_slug), name, teacher_url or personal_url])


def empty_store() -> dict[str, Any]:
    return {
        "version": 3,
        "updated_at": "",
        "statuses": {},
    }


def normalize_status_store(data: Any) -> dict[str, Any]:
    store = empty_store()
    if not isinstance(data, dict):
        return store
    try:
        store["version"] = max(int(data.get("version") or 1), 3)
    except (TypeError, ValueError):
        store["version"] = 3
    store["updated_at"] = norm_text(data.get("updated_at") or data.get("updatedAt"))
    statuses = data.get("statuses") or data.get("records") or {}
    if not isinstance(statuses, dict):
        return store
    for key, value in statuses.items():
        entry = normalize_contact_entry(value)
        if entry:
            store["statuses"][norm_text(key)] = entry
    return store


def split_responses(value: Any) -> list[str]:
    if isinstance(value, list):
        candidates = value
    else:
        text = norm_text(value)
        if not text:
            return []
        for sep in ["；", ";", "、", ","]:
            text = text.replace(sep, "|")
        candidates = text.split("|")
    responses: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        response = norm_text(item)
        if not response or response in seen:
            continue
        responses.append(response)
        seen.add(response)
    return responses


def join_responses(value: Any) -> str:
    return "；".join(split_responses(value))


def unique_join_text(values: list[Any], sep: str = "；") -> str:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = norm_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return sep.join(output)


def split_known_and_custom_responses(value: Any) -> tuple[list[str], list[str]]:
    known: list[str] = []
    custom: list[str] = []
    for response in split_responses(value):
        if response in DEFAULT_CONTACT_RESPONSES:
            known.append(response)
        else:
            custom.append(response)
    return known, custom


def normalize_contact_entry(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        status = normalize_status(value)
        return {"status": status} if status else {}
    if not isinstance(value, dict):
        return {}

    status = normalize_status(value.get("status") or value.get("contactStatus") or value.get(STATUS_COLUMN))
    contacted_at = norm_text(
        value.get("contacted_at")
        or value.get("contactedAt")
        or value.get("date")
        or value.get(CONTACT_DATE_COLUMN)
    )
    responses, custom_responses = split_known_and_custom_responses(
        value.get("responses")
        or value.get("reply_statuses")
        or value.get("replyStatuses")
        or value.get(CONTACT_RESPONSE_COLUMN)
    )
    note = unique_join_text(
        [
            value.get("note"),
            value.get("contact_note"),
            value.get(CONTACT_NOTE_COLUMN),
            *(value.get(column) for column in LEGACY_CONTACT_NOTE_COLUMNS),
            join_responses(custom_responses),
        ]
    )

    entry: dict[str, Any] = {}
    if status:
        entry["status"] = status
    if contacted_at:
        entry["contacted_at"] = contacted_at
    if responses:
        entry["responses"] = responses
    if note:
        entry["note"] = note
    for field in ["name", "school", "college", "teacher_url", "updated_at"]:
        text = norm_text(value.get(field))
        if text:
            entry[field] = text
    return entry


def load_status_store(path: Path = CONTACT_STATUS_PATH) -> dict[str, Any]:
    if not path.exists():
        return empty_store()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"contact status store is unreadable: {path}: {exc}") from exc
    return normalize_status_store(data)


def save_status_store(store: dict[str, Any], path: Path = CONTACT_STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    store = normalize_status_store(store)
    store["updated_at"] = datetime.now().isoformat(timespec="seconds")
    tmp_path = path.with_name(f".{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def normalize_status(value: Any) -> str:
    value = norm_text(value)
    value = LEGACY_STATUS_ALIASES.get(value, value)
    return value if value in VALID_CONTACT_STATUSES else ""


def contact_entry_from_store(store: dict[str, Any], key: str) -> dict[str, Any]:
    return normalize_contact_entry(store.get("statuses", {}).get(key, {}))


def status_from_store(store: dict[str, Any], key: str) -> str:
    return normalize_status(contact_entry_from_store(store, key).get("status"))


def has_status_entry(store: dict[str, Any], key: str) -> bool:
    statuses = store.get("statuses", {})
    return isinstance(statuses, dict) and key in statuses


def set_status_in_store(
    store: dict[str, Any],
    key: str,
    status: str,
    *,
    name: str = "",
    school: str = "",
    college: str = "",
    teacher_url: str = "",
) -> None:
    status = normalize_status(status)
    statuses = store.setdefault("statuses", {})
    if not status:
        entry = normalize_contact_entry(statuses.get(key, {}))
        entry.pop("status", None)
        if entry:
            statuses[key] = entry
        else:
            statuses.pop(key, None)
        return
    entry = normalize_contact_entry(statuses.get(key, {}))
    entry.update(
        {
            "status": status,
            "name": name,
            "school": school,
            "college": college,
            "teacher_url": teacher_url,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    statuses[key] = {field: value for field, value in entry.items() if value}


def contact_entry_from_row(row: Any) -> dict[str, Any]:
    getter = row.get if isinstance(row, pd.Series) else lambda key, default="": row.get(key, default)
    entry: dict[str, Any] = {}
    status = normalize_status(getter(STATUS_COLUMN, ""))
    contacted_at = norm_text(getter(CONTACT_DATE_COLUMN, ""))
    responses, custom_responses = split_known_and_custom_responses(getter(CONTACT_RESPONSE_COLUMN, ""))
    note = unique_join_text(
        [
            getter(CONTACT_NOTE_COLUMN, ""),
            *(getter(column, "") for column in LEGACY_CONTACT_NOTE_COLUMNS),
            join_responses(custom_responses),
        ]
    )
    if status:
        entry["status"] = status
    if contacted_at:
        entry["contacted_at"] = contacted_at
    if responses:
        entry["responses"] = responses
    if note:
        entry["note"] = note
    return entry


def insert_contact_columns_after_name(df: pd.DataFrame) -> pd.DataFrame:
    if "姓名" not in df.columns:
        return df
    legacy_notes = [df[column] for column in LEGACY_CONTACT_NOTE_COLUMNS if column in df.columns]
    if legacy_notes:
        current_notes = df[CONTACT_NOTE_COLUMN] if CONTACT_NOTE_COLUMN in df.columns else None
        merged_notes = []
        for row_idx in range(len(df)):
            merged_notes.append(
                unique_join_text(
                    [
                        current_notes.iloc[row_idx] if current_notes is not None else "",
                        *(series.iloc[row_idx] for series in legacy_notes),
                    ]
                )
            )
        df[CONTACT_NOTE_COLUMN] = merged_notes
    columns = list(df.columns)
    for column in CONTACT_COLUMNS:
        if column not in columns:
            df[column] = ""
            columns.append(column)
    for column in LEGACY_CONTACT_NOTE_COLUMNS:
        if column in columns:
            columns.remove(column)
    for column in CONTACT_COLUMNS:
        columns.remove(column)
    insert_at = columns.index("姓名") + 1
    for offset, column in enumerate(CONTACT_COLUMNS):
        columns.insert(insert_at + offset, column)
    return df[columns]


def insert_status_after_name(df: pd.DataFrame) -> pd.DataFrame:
    return insert_contact_columns_after_name(df)


def apply_contact_statuses(
    df: pd.DataFrame,
    school_slug: str,
    college_slug: str,
    store: dict[str, Any] | None = None,
    authoritative: bool | None = None,
) -> pd.DataFrame:
    df = df.copy()
    df = insert_contact_columns_after_name(df)
    if "姓名" not in df.columns or STATUS_COLUMN not in df.columns:
        return df
    loaded_from_default = store is None
    store = store if store is not None else load_status_store()
    if authoritative is None:
        authoritative = loaded_from_default and CONTACT_STATUS_PATH.exists()
    values: dict[str, list[str]] = {column: [] for column in CONTACT_COLUMNS}
    for _, row in df.iterrows():
        key = row_key(school_slug, college_slug, row)
        stored_entry = contact_entry_from_store(store, key)
        stored_key_exists = has_status_entry(store, key)
        if not stored_entry:
            legacy_key = legacy_row_key(school_slug, college_slug, row)
            stored_entry = contact_entry_from_store(store, legacy_key)
            stored_key_exists = has_status_entry(store, legacy_key)
        current_entry = contact_entry_from_row(row)
        if authoritative:
            entry = stored_entry if stored_key_exists else {}
        else:
            entry = {**current_entry, **stored_entry}
        values[STATUS_COLUMN].append(normalize_status(entry.get("status")))
        values[CONTACT_DATE_COLUMN].append(norm_text(entry.get("contacted_at")))
        values[CONTACT_RESPONSE_COLUMN].append(join_responses(entry.get("responses", [])))
        values[CONTACT_NOTE_COLUMN].append(norm_text(entry.get("note")))
    for column, column_values in values.items():
        df[column] = column_values
    return df


def apply_contact_statuses_to_rows(
    rows: list[dict[str, Any]],
    school_slug: str,
    college_slug: str,
    store: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return rows
    df = pd.DataFrame(rows)
    df = apply_contact_statuses(df, school_slug, college_slug, store)
    return df.to_dict("records")
