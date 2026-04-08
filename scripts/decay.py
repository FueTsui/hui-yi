#!/usr/bin/env python3
"""Decay Hui-Yi note confidence and state using verification / review freshness.

This is a lightweight forgetting-aware maintenance helper, not a full SRS engine.

IMPORTANT: decay.py modifies note .md files directly. It does NOT update tags.json
or index.md. After running this script, run rebuild.py to re-sync the index:

  python3 scripts/decay.py [--dry-run]
  python3 scripts/rebuild.py          # required to sync tags.json / index.md

Or use --rebuild to do both in one step:

  python3 scripts/decay.py --rebuild
"""
from __future__ import annotations

import argparse
import math
import re
# subprocess removed – using direct function call for rebuild
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import DEFAULT_MEMORY_ROOT, SKIP_MARKDOWN, parse_date, parse_heading_value, parse_review_metric, resolve_memory_root

SKIP = SKIP_MARKDOWN
STATE_ORDER = ["hot", "warm", "cold", "dormant"]
CONFIDENCE_ORDER = ["high", "medium", "low"]
DEFAULT_INTERVAL_DAYS = 1  # Ebbinghaus: first review at +1 day while memory is still fresh


def replace_heading_bullet(text: str, heading: str, new_value: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(heading)}\s*\n)(?:-\s*)?([^\n]+)(\s*$)", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(rf"\1- {new_value}\3", text, count=1)
    return text


def replace_review_metric(text: str, key: str, new_value: int) -> str:
    block_pattern = re.compile(r"(^## Review cadence\s*$)(.*?)(^(?:## |\Z))", re.MULTILINE | re.DOTALL)
    match = block_pattern.search(text)
    if not match:
        insertion = f"\n## Review cadence\n- interval_days: {DEFAULT_INTERVAL_DAYS}\n- review_count: 0\n- review_success: 0\n- review_fail: 0\n"
        text += insertion
        match = block_pattern.search(text)
        if not match:
            return text
    block = match.group(2)
    metric_pattern = re.compile(rf"(^-\s*{re.escape(key)}\s*:\s*)(\d+)(\s*$)", re.MULTILINE)
    if metric_pattern.search(block):
        block = metric_pattern.sub(rf"\g<1>{new_value}\g<3>", block, count=1)
    else:
        if not block.endswith("\n"):
            block += "\n"
        block += f"- {key}: {new_value}\n"
    return text[: match.start(2)] + block + text[match.end(2) :]


def iter_notes(root: Path):
    for path in root.rglob("*.md"):
        if path.name in SKIP:
            continue
        yield path


def demote_state(state: str | None) -> str | None:
    if state not in STATE_ORDER:
        return state
    idx = STATE_ORDER.index(state)
    return STATE_ORDER[min(idx + 1, len(STATE_ORDER) - 1)]


def demote_confidence(confidence: str | None) -> str | None:
    if confidence not in CONFIDENCE_ORDER:
        return confidence
    idx = CONFIDENCE_ORDER.index(confidence)
    return CONFIDENCE_ORDER[min(idx + 1, len(CONFIDENCE_ORDER) - 1)]


def next_interval(interval_days: int, review_success: int, review_fail: int) -> int:
    success_factor = 1 + min(review_success, 4) * 0.35
    fail_penalty = 1 + min(review_fail, 3) * 0.2
    raw = interval_days * success_factor / fail_penalty
    return max(1, int(math.ceil(raw)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decay Hui-Yi note confidence and state. Run rebuild.py afterward to sync tags.json."
    )
    parser.add_argument("--memory-root", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Run rebuild.py automatically after decay to sync index.md and tags.json",
    )
    args = parser.parse_args()

    root = resolve_memory_root(args.memory_root)
    today = date.today()
    changes = []
    dormant_candidates = []

    for path in iter_notes(root):
        text = path.read_text(encoding="utf-8")
        confidence = parse_heading_value(text, "Confidence")
        state = parse_heading_value(text, "Memory state")
        importance = parse_heading_value(text, "Importance") or "medium"
        last_verified = parse_date(parse_heading_value(text, "Last verified") or "")
        last_reviewed = parse_date(parse_heading_value(text, "Last reviewed") or "")
        last_seen = parse_date(parse_heading_value(text, "Last seen") or "")
        next_review = parse_date(parse_heading_value(text, "Next review") or "")
        interval_days = parse_review_metric(text, "interval_days", DEFAULT_INTERVAL_DAYS)
        review_count = parse_review_metric(text, "review_count", 0)
        review_success = parse_review_metric(text, "review_success", 0)
        review_fail = parse_review_metric(text, "review_fail", 0)

        review_anchor = last_reviewed or last_seen or last_verified
        review_age = (today - review_anchor).days if review_anchor else None
        verify_age = (today - last_verified).days if last_verified else None
        overdue_days = (today - next_review).days if next_review else None

        target_confidence = confidence
        target_state = state
        target_interval = interval_days
        target_next_review = next_review.isoformat() if next_review else None
        reasons = []

        if verify_age is not None:
            if verify_age > 180 and confidence == "medium":
                target_confidence = "low"
                reasons.append(f"verification stale {verify_age}d")
            elif verify_age > 120 and confidence == "high":
                target_confidence = "medium"
                reasons.append(f"verification old {verify_age}d")

        if overdue_days is not None and overdue_days > max(interval_days, 7):
            target_state = demote_state(state)
            reasons.append(f"review overdue {overdue_days}d")

        if review_age is not None and review_age > 120 and importance != "high":
            target_state = demote_state(target_state)
            reasons.append(f"not revisited for {review_age}d")

        if review_age is not None and review_age > 180 and (target_state == "cold" or target_state == "dormant"):
            dormant_candidates.append((path, review_age))

        if target_state == state and overdue_days is not None and overdue_days > 0:
            target_interval = max(1, next_interval(interval_days, review_success, review_fail))
            target_next_review = (today + timedelta(days=target_interval)).isoformat()
            reasons.append("rescheduled overdue review")

        if not reasons:
            continue

        changes.append((path, confidence, target_confidence, state, target_state, target_interval, target_next_review, reasons))

        if not args.dry_run:
            new_text = text
            if target_confidence and target_confidence != confidence:
                new_text = replace_heading_bullet(new_text, "Confidence", target_confidence)
            if target_state and target_state != state:
                new_text = replace_heading_bullet(new_text, "Memory state", target_state)
            if target_next_review:
                new_text = replace_heading_bullet(new_text, "Next review", target_next_review)
            if target_interval != interval_days:
                new_text = replace_review_metric(new_text, "interval_days", target_interval)
            path.write_text(new_text, encoding="utf-8")

    if not changes and not dormant_candidates:
        print(f"No decay needed. memory root: {root}")
        return 0

    for path, old_conf, new_conf, old_state, new_state, interval_days, next_review, reasons in changes:
        print(
            f"UPDATE: {path} | confidence {old_conf} -> {new_conf} | state {old_state} -> {new_state} | "
            f"interval {interval_days}d | next review {next_review or 'n/a'} | reasons: {', '.join(reasons)}"
        )
    for path, age in dormant_candidates:
        print(f"DORMANT-CANDIDATE: {path} — no meaningful revisit for {age} days")

    if args.dry_run:
        print("Dry run only; no files modified.")
        return 0

    if args.rebuild:
        # Directly invoke rebuild logic without spawning a subprocess
        import importlib.util, sys, pathlib
        rebuild_path = pathlib.Path(__file__).with_name('rebuild.py')
        spec = importlib.util.spec_from_file_location('rebuild', rebuild_path)
        rebuild_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rebuild_mod)
        rebuild_main = rebuild_mod.main
        original_argv = sys.argv
        try:
            sys.argv = ["rebuild.py", "--memory-root", str(root)]
            exit_code = rebuild_main()
        finally:
            sys.argv = original_argv
        if exit_code == 0:
            print("\nRebuild completed successfully via direct function call.")
        else:
            print(f"\nWarning: rebuild reported error (exit code {exit_code}).")
    else:
        print("\nNote: tags.json and index.md are NOT yet updated.")
        print("Run 'python3 scripts/rebuild.py' to sync them, or rerun with --rebuild.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())