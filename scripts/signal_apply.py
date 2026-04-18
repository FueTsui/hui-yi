#!/usr/bin/env python3
"""Apply real session activation signals to a Hui-Yi cold note."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    load_tags_payload,
    note_file_path,
    parse_session_signals,
    replace_or_insert_section_metrics,
    resolve_memory_root,
    save_json,
)


def slugify(text: str) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", text.strip().lower())
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "session"


def find_note(notes: list[dict], target: str) -> dict | None:
    lookup = target.strip().lower()
    target_words = set(lookup.split())
    for note in notes:
        title_lower = (note.get("title") or "").strip().lower()
        path_lower = (note.get("path") or "").strip().lower()
        note_slug = Path(path_lower).stem
        if (
            title_lower == lookup
            or path_lower.endswith(lookup)
            or note_slug == lookup
            or (target_words and all(w in title_lower for w in target_words))
        ):
            return note
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a real-session activation event to a Hui-Yi note")
    parser.add_argument("note")
    parser.add_argument("--memory-root", default=None)
    parser.add_argument("--session-key", required=True)
    parser.add_argument("--strength", choices=["weak", "medium", "strong"], default="medium")
    parser.add_argument("--activated-at", default=None, help="ISO date, defaults to today")
    parser.add_argument("--source", default="feedback_useful")
    args = parser.parse_args()

    memory_root = resolve_memory_root(args.memory_root)
    payload = load_tags_payload(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    matched = find_note(notes, args.note)
    if not matched:
        print(f"Note not found: {args.note!r}", file=sys.stderr)
        return 1

    note_path = note_file_path(memory_root, matched)
    if not note_path.exists():
        print(f"Backing note file missing: {note_path}", file=sys.stderr)
        return 1

    activated_day = date.fromisoformat(args.activated_at).isoformat() if args.activated_at else date.today().isoformat()
    text = note_path.read_text(encoding="utf-8")
    signals = parse_session_signals(text)

    dedup_key = f"{args.session_key}|{slugify(Path(note_path).stem)}|{activated_day}|{args.source}"
    history = matched.get("signal_history") if isinstance(matched.get("signal_history"), list) else []
    if dedup_key in history:
        print(f"SKIP duplicate activation: {matched.get('title')} | {dedup_key}", file=sys.stderr)
        return 0

    signals["current_session_hits"] = int(signals.get("current_session_hits", 0) or 0) + 1
    strength_bump = {"weak": 1, "medium": 1, "strong": 2}[args.strength]
    signals["recent_session_hits"] = int(signals.get("recent_session_hits", 0) or 0) + strength_bump

    last_session_key = matched.get("last_session_key")
    if last_session_key != args.session_key:
        signals["cross_session_repeat_count"] = int(signals.get("cross_session_repeat_count", 0) or 0) + 1
        if last_session_key:
            signals["consecutive_session_count"] = int(signals.get("consecutive_session_count", 0) or 0) + 1
        else:
            signals["consecutive_session_count"] = max(1, int(signals.get("consecutive_session_count", 0) or 0))
    else:
        signals["consecutive_session_count"] = max(1, int(signals.get("consecutive_session_count", 0) or 0))

    signals["last_activated"] = activated_day

    new_text = replace_or_insert_section_metrics(
        text,
        "Session signals",
        {
            "current_session_hits": signals["current_session_hits"],
            "recent_session_hits": signals["recent_session_hits"],
            "cross_session_repeat_count": signals["cross_session_repeat_count"],
            "consecutive_session_count": signals["consecutive_session_count"],
            "last_activated": signals["last_activated"],
        },
    )
    note_path.write_text(new_text, encoding="utf-8")

    matched["session_signals"] = signals
    matched["last_seen"] = activated_day
    matched["last_session_key"] = args.session_key
    history = (history + [dedup_key])[-20:]
    matched["signal_history"] = history
    payload.setdefault("_meta", {})["updated"] = activated_day
    save_json(memory_root / "tags.json", payload)

    print(
        f"Applied signal: {matched.get('title')} | session_key={args.session_key} | "
        f"strength={args.strength} | recent_hits={signals['recent_session_hits']} | "
        f"cross_session_repeat_count={signals['cross_session_repeat_count']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
