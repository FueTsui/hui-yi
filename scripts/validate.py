#!/usr/bin/env python3
"""Validate Hui-Yi cold memory notes and index consistency.

Checks each note file against the expected schema and cross-validates
tags.json references. Exits with code 1 if any errors are found.

Usage:
  python3 scripts/validate.py [--memory-root PATH] [--strict]

Options:
  --strict    Treat warnings as errors (exit 1 on any issue)
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import DEFAULT_MEMORY_ROOT, parse_heading_value, resolve_memory_root
import json
import re

SKIP = {"index.md", "retrieval-log.md", "_template.md"}

REQUIRED_SECTIONS = [
    "TL;DR",
    "Memory type",
    "Importance",
    "Memory state",
    "Confidence",
    "Last verified",
    "Related tags",
]
RECOMMENDED_SECTIONS = [
    "Semantic context",
    "Triggers",
    "Use this when",
    "Review cadence",
    "Last seen",
    "Next review",
]
VALID_MEMORY_TYPES = {"fact", "experience", "background"}
VALID_IMPORTANCE = {"high", "medium", "low"}
VALID_STATES = {"hot", "warm", "cold", "dormant"}
VALID_CONFIDENCE = {"high", "medium", "low"}
OVERDUE_WARN_DAYS = 90  # warn if next_review is more than this many days in the past


def parse_review_metric(text: str, key: str) -> int | None:
    match = re.search(r"^## Review cadence\s*$(.*?)^(?:## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        return None
    block = match.group(1)
    metric = re.search(rf"^-\s*{re.escape(key)}\s*:\s*(\d+)\s*$", block, re.MULTILINE)
    return int(metric.group(1)) if metric else None


def section_exists(text: str, heading: str) -> bool:
    return bool(re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE))


def validate_note(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a single note file."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append("Cannot read file as UTF-8 — check encoding")
        return errors, warnings

    # --- Required sections ---
    for section in REQUIRED_SECTIONS:
        if not section_exists(text, section):
            errors.append(f"Missing required section: ## {section}")

    # --- Recommended sections ---
    for section in RECOMMENDED_SECTIONS:
        if not section_exists(text, section):
            warnings.append(f"Missing recommended section: ## {section}")

    # --- Enum validation ---
    memory_type = parse_heading_value(text, "Memory type")
    if memory_type and memory_type not in VALID_MEMORY_TYPES:
        errors.append(f"Invalid Memory type {memory_type!r}, must be one of {sorted(VALID_MEMORY_TYPES)}")

    importance = parse_heading_value(text, "Importance")
    if importance and importance not in VALID_IMPORTANCE:
        errors.append(f"Invalid Importance {importance!r}, must be one of {sorted(VALID_IMPORTANCE)}")

    state = parse_heading_value(text, "Memory state")
    if state and state not in VALID_STATES:
        errors.append(f"Invalid Memory state {state!r}, must be one of {sorted(VALID_STATES)}")

    confidence = parse_heading_value(text, "Confidence")
    if confidence and confidence not in VALID_CONFIDENCE:
        errors.append(f"Invalid Confidence {confidence!r}, must be one of {sorted(VALID_CONFIDENCE)}")

    # --- Date field validation ---
    for field in ("Last seen", "Last reviewed", "Next review", "Last verified"):
        raw = parse_heading_value(text, field)
        if raw in (None, "-"):
            continue
        try:
            date.fromisoformat(raw)
        except ValueError:
            errors.append(f"## {field} has invalid date: {raw!r} (expected YYYY-MM-DD)")

    # --- next_review staleness ---
    next_review_raw = parse_heading_value(text, "Next review")
    if next_review_raw:
        try:
            nr = date.fromisoformat(next_review_raw)
            overdue = (date.today() - nr).days
            if overdue > OVERDUE_WARN_DAYS:
                warnings.append(f"next_review {next_review_raw} is {overdue} days overdue (>{OVERDUE_WARN_DAYS}d)")
        except ValueError:
            pass  # already reported above

    # --- Review cadence consistency ---
    r_count = parse_review_metric(text, "review_count")
    r_success = parse_review_metric(text, "review_success")
    r_fail = parse_review_metric(text, "review_fail")
    if r_count is not None and r_success is not None and r_fail is not None:
        if r_success + r_fail > r_count:
            errors.append(
                f"Review cadence inconsistency: review_success({r_success}) + "
                f"review_fail({r_fail}) > review_count({r_count})"
            )
        if r_success < 0 or r_fail < 0 or r_count < 0:
            errors.append("Review cadence contains negative values")

    return errors, warnings


def validate_tags_json(memory_root: Path, note_paths: set[Path]) -> tuple[list[str], list[str]]:
    """Cross-validate tags.json against actual note files."""
    errors: list[str] = []
    warnings: list[str] = []
    tags_path = memory_root / "tags.json"

    if not tags_path.exists():
        warnings.append("tags.json not found — run rebuild.py")
        return errors, warnings

    try:
        data = json.loads(tags_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"tags.json is malformed: {exc}")
        return errors, warnings

    if isinstance(data, dict):
        notes = data.get("notes", []) if isinstance(data.get("notes"), list) else []
    elif isinstance(data, list):
        notes = data
    else:
        errors.append("tags.json has unexpected top-level type (expected dict or list)")
        return errors, warnings

    for entry in notes:
        if not isinstance(entry, dict):
            warnings.append(f"tags.json contains a non-object entry: {entry!r}")
            continue
        raw_path = entry.get("path", "")
        candidate = Path(raw_path)
        if candidate.parts[:2] == ("memory", "cold"):
            candidate = Path(*candidate.parts[2:])
        full_path = memory_root / candidate
        if full_path not in note_paths:
            errors.append(f"tags.json references missing file: {raw_path!r}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Hui-Yi cold memory notes against the schema."
    )
    parser.add_argument("--memory-root", default=None)
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors"
    )
    args = parser.parse_args()

    memory_root = resolve_memory_root(args.memory_root)
    if not memory_root.exists():
        print(f"Error: memory root not found: {memory_root}")
        return 1

    note_files = sorted(
        p for p in memory_root.rglob("*.md") if p.name not in SKIP
    )

    if not note_files:
        print(f"No notes found in {memory_root}")
        return 0

    total_errors = 0
    total_warnings = 0
    note_set: set[Path] = set()

    for path in note_files:
        note_set.add(path)
        errors, warnings = validate_note(path)
        if errors or warnings:
            rel = path.relative_to(memory_root)
            print(f"\n{rel}")
            for msg in errors:
                print(f"  ERROR   {msg}")
                total_errors += 1
            for msg in warnings:
                print(f"  WARN    {msg}")
                total_warnings += 1

    # Cross-validate tags.json
    tag_errors, tag_warnings = validate_tags_json(memory_root, note_set)
    if tag_errors or tag_warnings:
        print("\ntags.json")
        for msg in tag_errors:
            print(f"  ERROR   {msg}")
            total_errors += 1
        for msg in tag_warnings:
            print(f"  WARN    {msg}")
            total_warnings += 1

    print(
        f"\n{'─' * 50}\n"
        f"Validated {len(note_files)} note(s). "
        f"Errors: {total_errors}  Warnings: {total_warnings}"
    )

    if total_errors > 0:
        print("Fix errors and run rebuild.py to sync index.")
        return 1
    if args.strict and total_warnings > 0:
        print("Strict mode: warnings treated as errors.")
        return 1
    if total_errors == 0 and total_warnings == 0:
        print("All notes OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
