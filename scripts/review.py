#!/usr/bin/env python3
"""Review and resurface Hui-Yi cold memories.

Commands:
- due:      list notes whose next_review is due or overdue
- resurface: rank resurfacing candidates using forgetting risk + current relevance
- feedback: log retrieval feedback and update note review metadata
- session:  interactive batch review of all due notes (Ebbinghaus closed loop)
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    DEFAULT_MEMORY_ROOT,
    load_tags_payload,
    note_file_path,
    parse_date,
    parse_heading_value,
    parse_review_metric,
    read_text_fallback,
    resolve_memory_root,
    save_json,
)

# Ebbinghaus: first review should happen while the memory is still fresh (+1 day).
# Using 7 as the default skips the steepest part of the forgetting curve entirely.
DEFAULT_INTERVAL_DAYS = 1

# Fixed review ladder (Ebbinghaus initial phase, indexed by review_count after increment).
# review_count=0 → note just created, next_review set to today+1 by create.py / rebuild.py
# review_count=1 → first review completed  → next interval = REVIEW_LADDER[1] = 3 days
# review_count=2 → second review completed → next interval = REVIEW_LADDER[2] = 7 days
# ...
# review_count>=5 → graduated to adaptive (multiplicative) phase
REVIEW_LADDER = [1, 3, 7, 14, 30]

# Graduation: a note that has been reviewed ≥5 times with ≥80% success AND its
# adaptive interval has grown to ≥90 days is considered well-consolidated.
# It transitions to Memory state=dormant and interval=365 days.
GRADUATION_MIN_REVIEWS = 5
GRADUATION_MIN_SUCCESS_RATE = 0.8
GRADUATION_MIN_INTERVAL = 90

IMPORTANCE_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}
STATE_WEIGHT = {"hot": 1.0, "warm": 1.5, "cold": 2.0, "dormant": 1.2}
FIELD_WEIGHTS = {
    "title": 2.2,
    "summary": 1.5,
    "semantic_context": 1.8,
    "tags": 1.0,
    "triggers": 1.2,
    "scenarios": 1.1,
}
# StateBias: hot and warm are in active use and should resurface readily;
# cold is preserved but lower urgency; dormant surfaces only on strong triggers.
_STATE_BIAS = {"hot": 1.0, "warm": 1.0, "cold": 0.7, "dormant": 0.3}


def load_tags(memory_root: Path) -> dict:
    return load_tags_payload(memory_root)


def save_tags(memory_root: Path, payload: dict) -> None:
    payload.setdefault("_meta", {})["updated"] = date.today().isoformat()
    save_json(memory_root / "tags.json", payload)


def replace_heading_bullet(text: str, heading: str, new_value: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(heading)}\s*\n)(?:-\s*)?([^\n]+)(\s*$)", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(rf"\1- {new_value}\3", text, count=1)
    return text + f"\n## {heading}\n- {new_value}\n"


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


def append_retrieval_log(log_path: Path, row: str) -> None:
    header = "# Retrieval Log\n\n| Date | Query | Matched | Useful | Action |\n|---|---|---|---|---|\n"
    if not log_path.exists():
        log_path.write_text(header, encoding="utf-8")
    # Use the multi-encoding fallback so an existing log with GB18030 or cp936
    # encoding (common on Windows) does not silently drop the new entry.
    current = read_text_fallback(log_path)
    if not current.endswith("\n"):
        current += "\n"
    current += row + "\n"
    log_path.write_text(current, encoding="utf-8")


def tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    return [part for part in re.split(r"[^\w\-\u4e00-\u9fff]+", text.lower()) if part]


def field_text(note: dict, field: str) -> str:
    value = note.get(field, "")
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    if value is None:
        return ""
    return str(value)


def load_context_text(query: str | None, context_file: str | None, stdin_flag: bool) -> str | None:
    parts: list[str] = []
    if query:
        parts.append(query.strip())
    if context_file:
        path = Path(context_file)
        parts.append(read_text_fallback(path).strip())
    if stdin_flag:
        stdin_text = sys.stdin.read().strip()
        if stdin_text:
            parts.append(stdin_text)
    combined = "\n".join(part for part in parts if part)
    return combined or None


def relevance_score(note: dict, query: str | None) -> tuple[float, dict]:
    if not query:
        return 0.0, {"matched_fields": [], "overlap_terms": []}

    query_terms = tokenize(query)
    if not query_terms:
        return 0.0, {"matched_fields": [], "overlap_terms": []}

    matched_fields: list[str] = []
    overlap_terms: set[str] = set()
    score = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        text = field_text(note, field)
        field_lower = text.lower()
        field_terms = set(tokenize(text))
        field_hits = 0
        for term in query_terms:
            if term in field_lower:
                score += weight
                field_hits += 1
                overlap_terms.add(term)
            elif term in field_terms:
                score += weight * 0.8
                field_hits += 1
                overlap_terms.add(term)
        if field_hits:
            matched_fields.append(field)
            score += min(field_hits, 3) * 0.15

    semantic_context = field_text(note, "semantic_context")
    summary = field_text(note, "summary")
    combined_terms = set(tokenize(semantic_context + " " + summary))
    if combined_terms and query_terms:
        overlap_ratio = len(set(query_terms) & combined_terms) / max(len(set(query_terms)), 1)
        score += overlap_ratio * 2.0

    return score, {
        "matched_fields": sorted(set(matched_fields)),
        "overlap_terms": sorted(overlap_terms),
    }


def forgetting_risk(note: dict, today: date) -> tuple[float, int]:
    next_review = parse_date(note.get("next_review"))
    if not next_review:
        return 0.0, 0
    overdue = (today - next_review).days
    if overdue <= 0:
        return 0.2, overdue
    capped = min(overdue, 30)
    risk = 0.2 + (capped / 30.0) * 0.8
    return min(risk, 1.0), overdue


def current_relevance_value(raw_score: float) -> float:
    if raw_score <= 0:
        return 0.0
    return min(1.0, math.log1p(raw_score) / math.log(10))


def resurfacing_priority(note: dict, today: date, query: str | None) -> tuple[float, dict]:
    importance_value = IMPORTANCE_WEIGHT.get(note.get("importance", "medium"), 2.0) / 3.0
    risk_value, overdue = forgetting_risk(note, today)
    raw_relevance, meta = relevance_score(note, query)
    relevance_value = current_relevance_value(raw_relevance)
    cross_session = min(1.0, int((note.get("review") or {}).get("review_success", 0) or 0) / 3.0)

    score = (
        0.35 * relevance_value
        + 0.25 * risk_value
        + 0.20 * importance_value
        + 0.10 * cross_session
        + 0.10 * _STATE_BIAS.get(note.get("state", "cold"), 0.6)
    )
    meta.update(
        {
            "overdue_days": overdue,
            "raw_relevance": raw_relevance,
            "relevance_value": relevance_value,
            "forgetting_risk": risk_value,
            "importance_value": importance_value,
            "cross_session": cross_session,
        }
    )
    return score, meta


def _compute_next_state(
    text: str,
    note: dict,
    useful: str,
    today: date,
) -> tuple[str, int, int, int, int, str]:
    """Compute new review state after a recall feedback event.

    Returns (state, interval_days, review_count, review_success, review_fail, next_review_iso).

    Algorithm:
    - For early reviews (review_count <= len(REVIEW_LADDER)-1 after increment):
        use the fixed Ebbinghaus ladder to advance the interval on success.
    - For later reviews (adaptive phase): multiply/shrink interval by performance factors.
    - On meeting graduation criteria: lock state=dormant, interval=365.
    """
    interval_days = parse_review_metric(text, "interval_days", DEFAULT_INTERVAL_DAYS)
    review_count = parse_review_metric(text, "review_count", 0) + 1
    review_success = parse_review_metric(text, "review_success", 0)
    review_fail = parse_review_metric(text, "review_fail", 0)
    state = parse_heading_value(text, "Memory state") or note.get("state", "cold")
    importance = note.get("importance", "medium")

    if useful == "yes":
        review_success += 1
        if review_count <= len(REVIEW_LADDER) - 1:
            # Still in the initial ladder phase — use the pre-defined next step
            interval_days = REVIEW_LADDER[review_count]
        else:
            # Adaptive phase: grow interval based on importance
            growth = 2.0 if importance == "high" else 1.6
            interval_days = max(REVIEW_LADDER[-1], int(math.ceil(interval_days * growth)))
        # State promotion
        if state == "cold":
            state = "warm"
        elif state == "warm" and importance == "high":
            state = "hot"
    else:
        review_fail += 1
        shrink = 0.5 if review_fail >= 2 else 0.7
        interval_days = max(1, int(math.ceil(interval_days * shrink)))
        if state == "hot":
            state = "warm"
        elif state == "warm":
            state = "cold"
        elif state == "cold" and importance != "high" and review_fail >= 2:
            state = "dormant"

    # Graduation check: well-consolidated notes transition to dormant / 1-year intervals
    success_rate = review_success / max(review_count, 1)
    if (
        state != "dormant"
        and review_count >= GRADUATION_MIN_REVIEWS
        and success_rate >= GRADUATION_MIN_SUCCESS_RATE
        and interval_days >= GRADUATION_MIN_INTERVAL
    ):
        state = "dormant"
        interval_days = 365

    next_review = (today + timedelta(days=interval_days)).isoformat()
    return state, interval_days, review_count, review_success, review_fail, next_review


def _write_note_feedback(
    note_path: Path,
    note: dict,
    text: str,
    useful: str,
    today: date,
    log_path: Path | None = None,
    query: str | None = None,
    action: str | None = None,
) -> tuple[str, int, str]:
    """Apply feedback, write note file and update the in-memory note dict.

    Returns (state, interval_days, next_review).
    Note: the caller is responsible for saving tags.json after this call.
    """
    state, interval_days, review_count, review_success, review_fail, next_review = (
        _compute_next_state(text, note, useful, today)
    )
    today_str = today.isoformat()

    new_text = replace_review_metric(text, "interval_days", interval_days)
    new_text = replace_review_metric(new_text, "review_count", review_count)
    new_text = replace_review_metric(new_text, "review_success", review_success)
    new_text = replace_review_metric(new_text, "review_fail", review_fail)
    new_text = replace_heading_bullet(new_text, "Last reviewed", today_str)
    new_text = replace_heading_bullet(new_text, "Last seen", today_str)
    new_text = replace_heading_bullet(new_text, "Next review", next_review)
    new_text = replace_heading_bullet(new_text, "Memory state", state)
    note_path.write_text(new_text, encoding="utf-8")

    note["state"] = state
    note["last_reviewed"] = today_str
    note["last_seen"] = today_str
    note["next_review"] = next_review
    if not isinstance(note.get("review"), dict):
        note["review"] = {}
    note["review"]["interval_days"] = interval_days
    note["review"]["review_count"] = review_count
    note["review"]["review_success"] = review_success
    note["review"]["review_fail"] = review_fail

    if log_path is not None:
        _q = query or note.get("title") or "session review"
        _a = action or ("reinforced note" if useful == "yes" else "weakened note")
        append_retrieval_log(
            log_path,
            f"| {today_str} | {_q} | {Path(note.get('path', '')).name} | {useful} | {_a} |",
        )

    return state, interval_days, next_review


def cmd_due(args: argparse.Namespace) -> int:
    memory_root = resolve_memory_root(args.memory_root)
    payload = load_tags(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    today = date.today()
    due = []
    for note in notes:
        next_review = parse_date(note.get("next_review"))
        if next_review and next_review <= today:
            score, meta = resurfacing_priority(note, today, None)
            due.append((score, meta, note))

    due.sort(key=lambda item: item[0], reverse=True)
    if not due:
        print("No notes due for review.")
        return 0

    print("Due notes:")
    for score, meta, note in due[: args.limit]:
        print(
            f"- priority={score:.3f} overdue={meta['overdue_days']}d | {note.get('title')} | "
            f"importance={note.get('importance')} state={note.get('state')} next_review={note.get('next_review')}"
        )
    return 0


def cmd_resurface(args: argparse.Namespace) -> int:
    memory_root = resolve_memory_root(args.memory_root)
    payload = load_tags(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    today = date.today()
    query_text = load_context_text(args.query, args.context_file, args.stdin)
    candidates = []

    for note in notes:
        score, meta = resurfacing_priority(note, today, query_text)
        if query_text:
            if meta["relevance_value"] < args.min_relevance:
                continue
            strong_fields = {"title", "summary", "tags", "triggers"}
            matched_fields = set(meta.get("matched_fields", []))
            if not (strong_fields & matched_fields):
                continue
            overlap_terms = meta.get("overlap_terms", [])
            if len(matched_fields) < 2 and len(overlap_terms) < 2 and meta["relevance_value"] < 0.75:
                continue
        else:
            next_review = parse_date(note.get("next_review"))
            if not next_review or next_review > today:
                continue
        if score >= args.min_priority:
            candidates.append((score, meta, note))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        print("No resurfacing candidates right now.")
        return 0

    print("Resurfacing candidates:")
    for score, meta, note in candidates[: args.limit]:
        prompt = f"You previously touched on '{note.get('title')}'. Want me to pull that thread back in?"
        print(f"- priority={score:.3f} | {note.get('title')}")
        print(
            f"  relevance={meta['relevance_value']:.3f} forgetting_risk={meta['forgetting_risk']:.3f} "
            f"overdue={meta['overdue_days']}d importance={note.get('importance')} state={note.get('state')}"
        )
        if query_text:
            overlap = ", ".join(meta.get("overlap_terms", [])) or "n/a"
            fields = ", ".join(meta.get("matched_fields", [])) or "n/a"
            print(f"  context_query={query_text[:200].replace(chr(10), ' ')}")
            print(f"  overlap_terms={overlap}")
            print(f"  matched_fields={fields}")
        print(f"  prompt: {prompt}")
        print(f"  path: {note.get('path')}")
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    memory_root = resolve_memory_root(args.memory_root)
    payload = load_tags(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    today = date.today()

    target = args.note.strip().lower()
    target_words = set(target.split())

    matched = None
    for note in notes:
        title_lower = (note.get("title") or "").strip().lower()
        path_lower = (note.get("path") or "").strip().lower()
        note_slug = Path(path_lower).stem
        # Match priority: exact title → exact path suffix → slug → all-words in title
        if (
            title_lower == target
            or path_lower.endswith(target)
            or note_slug == target
            or (target_words and all(w in title_lower for w in target_words))
        ):
            matched = note
            break

    if not matched:
        print(f"Note not found: {args.note!r}")
        print("Tip: pass a slug (filename without .md), exact title, or keywords that all appear in the title.")
        return 1

    note_path = note_file_path(memory_root, matched)
    if not note_path.exists():
        print(f"Backing note file missing: {note_path}")
        return 1

    text = note_path.read_text(encoding="utf-8")
    state, interval_days, next_review = _write_note_feedback(
        note_path,
        matched,
        text,
        args.useful,
        today,
        log_path=memory_root / "retrieval-log.md",
        query=args.query,
        action=args.action,
    )
    save_tags(memory_root, payload)

    graduated = state == "dormant" and interval_days == 365
    if graduated:
        print(
            f"🎓 Graduated: {matched.get('title')} — well-consolidated after "
            f"{matched.get('review', {}).get('review_count', '?')} reviews. "
            f"State → dormant, next review in 1 year."
        )
    else:
        print(
            f"Updated {matched.get('title')}: useful={args.useful}, "
            f"state={state}, interval_days={interval_days}, next_review={next_review}"
        )
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    """Interactive batch review session: work through all due notes one by one."""
    memory_root = resolve_memory_root(args.memory_root)
    payload = load_tags(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    today = date.today()
    log_path = memory_root / "retrieval-log.md"

    # Collect due notes sorted by priority (most urgent first)
    due: list[tuple[float, dict, dict]] = []
    for note in notes:
        next_review = parse_date(note.get("next_review"))
        if next_review and next_review <= today:
            score, meta = resurfacing_priority(note, today, None)
            due.append((score, meta, note))
    due.sort(key=lambda item: item[0], reverse=True)

    if not due:
        print("✓ Nothing due for review today.")
        return 0

    total = len(due)
    print(f"\n{'─' * 60}")
    print(f"  Review session — {total} note(s) due today")
    print(f"  Commands:  y = useful   n = not useful   s = skip   q = quit")
    print(f"{'─' * 60}\n")

    reviewed = 0
    skipped = 0
    graduated_titles: list[str] = []

    for idx, (score, meta, note) in enumerate(due, 1):
        note_path = note_file_path(memory_root, note)
        if not note_path.exists():
            print(f"[{idx}/{total}] SKIP — file missing: {note.get('title')}\n")
            skipped += 1
            continue

        text = note_path.read_text(encoding="utf-8")

        # Extract TL;DR lines for the prompt
        tldr: list[str] = []
        in_section = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "## TL;DR":
                in_section = True
                continue
            if in_section:
                if stripped.startswith("## "):
                    break
                if stripped.startswith("- ") and stripped[2:].strip():
                    tldr.append(stripped[2:].strip())
                elif stripped and not stripped.startswith("-"):
                    tldr.append(stripped)

        overdue = meta.get("overdue_days", 0)
        print(f"[{idx}/{total}]  {note.get('title', 'untitled')}")
        print(f"         importance={note.get('importance','?')}  "
              f"state={note.get('state','?')}  overdue={overdue}d  "
              f"priority={score:.3f}")
        for line in tldr[:4]:
            print(f"         → {line}")
        print()

        while True:
            try:
                raw = input("  Recall? [y/n/s/q] > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n\nSession interrupted (Ctrl+C).")
                _save_and_report(payload, memory_root, reviewed, skipped, total, graduated_titles)
                return 0

            if raw == "q":
                print()
                _save_and_report(payload, memory_root, reviewed, skipped, total, graduated_titles)
                return 0
            if raw == "s":
                skipped += 1
                print("  → Skipped.\n")
                break
            if raw in ("y", "n"):
                useful = "yes" if raw == "y" else "no"
                state, interval_days, next_review = _write_note_feedback(
                    note_path, note, text, useful, today, log_path=log_path
                )
                # Save tags.json after each note so an interrupt doesn't lose progress
                save_tags(memory_root, payload)

                graduated = state == "dormant" and interval_days == 365
                if graduated:
                    graduated_titles.append(note.get("title", "?"))
                    print(f"  🎓 Graduated! → dormant, next review +1 year\n")
                else:
                    arrow = "↑" if useful == "yes" else "↓"
                    print(f"  {arrow} {state} | +{interval_days}d → next: {next_review}\n")
                reviewed += 1
                break
            else:
                print("  Enter y, n, s, or q.")

    _save_and_report(payload, memory_root, reviewed, skipped, total, graduated_titles)
    return 0


def _save_and_report(
    payload: dict,
    memory_root: Path,
    reviewed: int,
    skipped: int,
    total: int,
    graduated_titles: list[str],
) -> None:
    save_tags(memory_root, payload)
    # Find earliest next_review among all notes
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    upcoming = [n.get("next_review") for n in notes if n.get("next_review")]
    today_str = date.today().isoformat()
    future = [d for d in upcoming if d > today_str]
    next_session = min(future) if future else "n/a"

    print(f"{'─' * 60}")
    print(f"  Done. Reviewed {reviewed} / {total}  (skipped {skipped})")
    if graduated_titles:
        print(f"  🎓 Graduated: {', '.join(graduated_titles)}")
    print(f"  Next earliest review: {next_session}")
    print(f"{'─' * 60}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    due = sub.add_parser("due")
    due.add_argument("--memory-root", default=None)
    due.add_argument("--limit", type=int, default=10)

    resurface = sub.add_parser("resurface")
    resurface.add_argument("--memory-root", default=None)
    resurface.add_argument("--limit", type=int, default=5)
    resurface.add_argument("--query", default=None, help="short query or topic summary")
    resurface.add_argument("--context-file", default=None, help="path to a text file containing richer context")
    resurface.add_argument("--stdin", action="store_true", help="read additional context from stdin")
    resurface.add_argument("--min-relevance", type=float, default=0.15)
    resurface.add_argument("--min-priority", type=float, default=0.20)

    feedback = sub.add_parser("feedback")
    feedback.add_argument("note")
    feedback.add_argument("--useful", choices=["yes", "no"], required=True)
    feedback.add_argument("--query", default=None)
    feedback.add_argument("--action", default=None)
    feedback.add_argument("--memory-root", default=None)

    session = sub.add_parser(
        "session",
        help="Interactive batch review of all due notes (Ebbinghaus closed loop)",
    )
    session.add_argument("--memory-root", default=None)

    args = parser.parse_args()
    if args.command == "due":
        return cmd_due(args)
    if args.command == "resurface":
        return cmd_resurface(args)
    if args.command == "session":
        return cmd_session(args)
    return cmd_feedback(args)


if __name__ == "__main__":
    raise SystemExit(main())