#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_MEMORY_ROOT = WORKSPACE_ROOT / "memory" / "cold"
DEFAULT_HEARTBEAT_PATH = WORKSPACE_ROOT / "memory" / "heartbeat-state.json"
SKIP_MARKDOWN = {"index.md", "retrieval-log.md", "_template.md"}
TEXT_FALLBACK_ENCODINGS = ["utf-8", "utf-8-sig", "gb18030", "cp936"]


def resolve_memory_root(arg: str | None, default: Path = DEFAULT_MEMORY_ROOT) -> Path:
    if arg:
        candidate = Path(arg)
        return candidate if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
    return default


def load_json(path: Path, default: dict | list | None = None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {} if default is None else default


def save_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text_fallback(path: Path) -> str:
    last_error: Exception | None = None
    for encoding in TEXT_FALLBACK_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return path.read_text(encoding="utf-8", errors="replace")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    if not value or value == "-":
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_heading_value(text: str, heading: str) -> str | None:
    pattern = rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    block = match.group(1)
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            return value or None
        return stripped
    return None


def parse_review_metric(text: str, key: str, default: int = 0) -> int:
    match = re.search(r"^## Review cadence\s*$(.*?)^(?:## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return default
    block = match.group(1)
    metric = re.search(rf"^-\s*{re.escape(key)}\s*:\s*(\d+)\s*$", block, re.MULTILINE)
    return int(metric.group(1)) if metric else default


def note_file_path(memory_root: Path, note: dict) -> Path:
    raw = note.get("path", "")
    candidate = Path(raw)
    if candidate.parts[:2] == ("memory", "cold"):
        candidate = Path(*candidate.parts[2:])
    return memory_root / candidate


def load_tags_payload(memory_root: Path) -> dict:
    tags_path = memory_root / "tags.json"
    if not tags_path.exists():
        return {"_meta": {"version": 4}, "notes": []}
    data = load_json(tags_path, default={"_meta": {"version": 4}, "notes": []})
    return data if isinstance(data, dict) else {"_meta": {"version": 4}, "notes": []}


def extract_notes_list(payload: dict | list | object) -> list[dict]:
    if isinstance(payload, dict):
        notes = payload.get("notes", [])
        return notes if isinstance(notes, list) else []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []
