#!/usr/bin/env python3
"""Review and resurface Hui-Yi cold memories.

Commands:
- due:      list notes whose next_review is due or overdue
- resurface: rank resurfacing candidates using repetition-first reinforcement
- feedback: log retrieval feedback and update note review metadata
- session:  interactive batch review of due or repeatedly-activated notes
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
    repetition_signal,
    resolve_memory_root,
    save_json,
)
from signal_detect import detect_match, load_context_text
from signal_pipeline import apply_candidates

DEFAULT_INTERVAL_DAYS = 1
REVIEW_LADDER = [1, 2, 4, 7, 15, 30, 60]
GRADUATION_MIN_REVIEWS = 7
GRADUATION_MIN_SUCCESS_RATE = 0.8
GRADUATION_INTERVAL_DAYS = {"high": 180, "medium": 120, "low": 90}
DORMANT_INTERVAL_DAYS = {"high": 180, "medium": 270, "low": 365}
ADAPTIVE_GROWTH = {"high": 1.35, "medium": 1.5, "low": 1.7}
STRENGTH_RISK_FACTOR = {"weak": 1.08, "normal": 1.0, "strong": 0.78}
IMPORTANCE_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}
def load_tags(memory_root: Path) -> dict:
    return load_tags_payload(memory_root)


def save_tags(memory_root: Path, payload: dict) -> None:
    payload.setdefault("_meta", {})["updated"] = date.today().isoformat()
    save_json(memory_root / "tags.json", payload)


def replace_heading_bullet(text: str, heading: str, new_value: str) -> str:
    pattern = re.compile(
        rf"(^## {re.escape(heading)}\s*$\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(rf"\1- {new_value}\n\n", text, count=1)
    return text + f"\n## {heading}\n- {new_value}\n"


def replace_review_metric(text: str, key: str, new_value: int) -> str:
    block_pattern = re.compile(r"(^## Review cadence\s*$)(.*?)(^(?:## |\Z))", re.MULTILINE | re.DOTALL)
    match = block_pattern.search(text)
    if not match:
        insertion = (
            f"\n## Review cadence\n"
            f"- interval_days: {DEFAULT_INTERVAL_DAYS}\n"
            f"- review_count: 0\n"
            f"- review_success: 0\n"
            f"- review_fail: 0\n"
            f"- retrieval_count: 0\n"
            f"- reinforcement_count: 0\n"
        )
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
    current = read_text_fallback(log_path)
    if not current.endswith("\n"):
        current += "\n"
    current += row + "\n"
    log_path.write_text(current, encoding="utf-8")


def forgetting_risk(note: dict, today: date) -> tuple[float, int]:
    next_review = parse_date(note.get("next_review"))
    review = note.get("review") if isinstance(note.get("review"), dict) else {}
    interval_days = max(1, int(review.get("interval_days", DEFAULT_INTERVAL_DAYS) or DEFAULT_INTERVAL_DAYS))
    strength = memory_strength(note)
    anchor = (
        parse_date(note.get("last_reviewed"))
        or parse_date(note.get("last_seen"))
        or parse_date(note.get("last_verified"))
    )
    if next_review and anchor is None:
        anchor = next_review - timedelta(days=interval_days)
    if anchor is None:
        return 0.0, 0

    elapsed_days = max(0, (today - anchor).days)
    progress = elapsed_days / max(interval_days, 1)
    risk = 1.0 - math.exp(-1.2 * progress)

    overdue = 0
    if next_review:
        overdue = (today - next_review).days
        if overdue > 0:
            overdue_ratio = min(2.0, overdue / max(interval_days, 1))
            risk = min(1.0, risk + 0.15 + 0.15 * overdue_ratio)

    risk *= STRENGTH_RISK_FACTOR.get(strength, 1.0)
    return max(0.05, min(risk, 1.0)), overdue


def due_pressure(note: dict, today: date) -> tuple[float, int]:
    risk_value, overdue = forgetting_risk(note, today)
    next_review = parse_date(note.get("next_review"))
    review = note.get("review") if isinstance(note.get("review"), dict) else {}
    interval_days = max(1, int(review.get("interval_days", DEFAULT_INTERVAL_DAYS) or DEFAULT_INTERVAL_DAYS))
    if not next_review:
        return risk_value, overdue
    days_until = (next_review - today).days
    if days_until <= 0:
        overdue_ratio = min(1.0, abs(days_until) / max(interval_days, 1))
        return min(1.0, 0.65 + 0.35 * overdue_ratio), overdue
    pre_due_window = max(1, interval_days // 2)
    if days_until <= pre_due_window:
        edge = 1.0 - (days_until / max(pre_due_window, 1))
        return max(risk_value, 0.25 + 0.45 * edge), overdue
    return min(risk_value, 0.20), overdue


def resurfacing_priority(note: dict, today: date, query: str | None) -> tuple[float, dict]:
    importance_value = IMPORTANCE_WEIGHT.get(note.get("importance", "medium"), 2.0) / 3.0
    due_value, overdue = due_pressure(note, today)
    if query:
        relevance_value, meta = detect_match(note, query)
        raw_relevance = meta.get("raw_score", 0.0)
    else:
        relevance_value, meta = 0.0, {"matched_fields": [], "overlap_terms": [], "raw_score": 0.0, "confidence": "none"}
        raw_relevance = 0.0
    repeat_value = repetition_signal(note, today)
    strength = memory_strength(note)
    strength_value = {"weak": 1.0, "normal": 0.75, "strong": 0.55}.get(strength, 0.75)

    score = (
        0.40 * repeat_value
        + 0.25 * relevance_value
        + 0.15 * due_value
        + 0.10 * importance_value
        + 0.10 * strength_value
    )
    meta.update(
        {
            "overdue_days": overdue,
            "raw_relevance": raw_relevance,
            "relevance_value": relevance_value,
            "due_pressure": due_value,
            "forgetting_risk": due_value,
            "importance_value": importance_value,
            "repetition_signal": repeat_value,
            "memory_strength": strength,
            "strength_value": strength_value,
        }
    )
    return score, meta


def memory_strength(note: dict) -> str:
    review = note.get("review") if isinstance(note.get("review"), dict) else {}
    interval_days = int(review.get("interval_days", DEFAULT_INTERVAL_DAYS) or DEFAULT_INTERVAL_DAYS)
    retrieval_count = int(review.get("retrieval_count", 0) or 0)
    reinforcement_count = int(review.get("reinforcement_count", 0) or 0)
    review_success = int(review.get("review_success", 0) or 0)
    state = str(note.get("state", "cold"))

    if (
        reinforcement_count >= 3
        or retrieval_count >= 5
        or (review_success >= 4 and interval_days >= 15)
        or (state == "hot" and review_success >= 3)
    ):
        return "strong"
    if reinforcement_count >= 1 or retrieval_count >= 2 or review_success >= 2:
        return "normal"
    return "weak"


def next_success_interval(interval_days: int, importance: str) -> int:
    current = max(1, interval_days)
    for step in REVIEW_LADDER:
        if current < step:
            return step
    growth = ADAPTIVE_GROWTH.get(importance, ADAPTIVE_GROWTH["medium"])
    return max(REVIEW_LADDER[-1], int(math.ceil(current * growth)))


def relearning_interval(interval_days: int) -> int:
    return 1 if interval_days <= REVIEW_LADDER[4] else 2


def _compute_next_state(text: str, note: dict, useful: str, today: date) -> tuple[str, int, int, int, int, int, int, str]:
    interval_days = parse_review_metric(text, "interval_days", DEFAULT_INTERVAL_DAYS)
    review_count = parse_review_metric(text, "review_count", 0) + 1
    review_success = parse_review_metric(text, "review_success", 0)
    review_fail = parse_review_metric(text, "review_fail", 0)
    retrieval_count = parse_review_metric(text, "retrieval_count", 0) + 1
    reinforcement_count = parse_review_metric(text, "reinforcement_count", 0)
    state = parse_heading_value(text, "Memory state") or note.get("state", "cold")
    importance = note.get("importance", "medium")

    if useful == "yes":
        review_success += 1
        reinforcement_count += 1
        interval_days = next_success_interval(interval_days, importance)
        if state in {"cold", "dormant"}:
            state = "warm"
        elif state == "warm" and (importance == "high" or reinforcement_count >= 3):
            state = "hot"
    else:
        review_fail += 1
        interval_days = relearning_interval(interval_days)
        if state == "hot":
            state = "warm"
        else:
            state = "cold"

    success_rate = review_success / max(review_count, 1)
    graduation_interval = GRADUATION_INTERVAL_DAYS.get(importance, GRADUATION_INTERVAL_DAYS["medium"])
    dormant_interval = DORMANT_INTERVAL_DAYS.get(importance, DORMANT_INTERVAL_DAYS["medium"])
    if (
        state != "dormant"
        and useful == "yes"
        and reinforcement_count >= 3
        and review_success >= GRADUATION_MIN_REVIEWS
        and success_rate >= GRADUATION_MIN_SUCCESS_RATE
        and interval_days >= graduation_interval
    ):
        state = "dormant"
        interval_days = dormant_interval

    next_review = (today + timedelta(days=interval_days)).isoformat()
    return state, interval_days, review_count, review_success, review_fail, retrieval_count, reinforcement_count, next_review


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
    (
        state,
        interval_days,
        review_count,
        review_success,
        review_fail,
        retrieval_count,
        reinforcement_count,
        next_review,
    ) = _compute_next_state(text, note, useful, today)
    today_str = today.isoformat()

    new_text = replace_review_metric(text, "interval_days", interval_days)
    new_text = replace_review_metric(new_text, "review_count", review_count)
    new_text = replace_review_metric(new_text, "review_success", review_success)
    new_text = replace_review_metric(new_text, "review_fail", review_fail)
    new_text = replace_review_metric(new_text, "retrieval_count", retrieval_count)
    new_text = replace_review_metric(new_text, "reinforcement_count", reinforcement_count)
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
    note["review"]["retrieval_count"] = retrieval_count
    note["review"]["reinforcement_count"] = reinforcement_count
    note["strength"] = memory_strength(note)

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
        repeat_value = repetition_signal(note, today)
        if (next_review and next_review <= today) or repeat_value >= 0.35:
            score, meta = resurfacing_priority(note, today, None)
            due.append((score, meta, note))

    due.sort(key=lambda item: item[0], reverse=True)
    if not due:
        print("No notes due for review.")
        return 0

    print("Due notes:")
    for score, meta, note in due[: args.limit]:
        print(
            f"- priority={score:.3f} overdue={meta['overdue_days']}d repeat={meta.get('repetition_signal', 0.0):.3f} | {note.get('title')} | "
            f"importance={note.get('importance')} state={note.get('state')} "
            f"strength={meta.get('memory_strength')} next_review={note.get('next_review')}"
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
            if meta["relevance_value"] < args.min_relevance and meta.get("repetition_signal", 0.0) < 0.35:
                continue
            strong_fields = {"title", "summary", "tags", "triggers"}
            matched_fields = set(meta.get("matched_fields", []))
            if not (strong_fields & matched_fields) and meta.get("repetition_signal", 0.0) < 0.35:
                continue
        else:
            next_review = parse_date(note.get("next_review"))
            if (not next_review or next_review > today) and meta.get("repetition_signal", 0.0) < 0.35:
                continue
        if score >= args.min_priority:
            candidates.append((score, meta, note))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        print("No resurfacing candidates right now.")
        return 0

    print("Resurfacing candidates:")
    surfaced = candidates[: args.limit]
    if args.write_signals and args.session_key:
        signal_candidates = [
            {
                "title": note.get("title"),
                "path": note.get("path"),
                "relevance": meta.get("relevance_value", 0.0),
                "confidence": "high" if meta.get("relevance_value", 0.0) >= 0.60 else "medium",
                "matched_fields": meta.get("matched_fields", []),
                "overlap_terms": meta.get("overlap_terms", []),
                "raw_score": meta.get("raw_relevance", 0.0),
                "repetition_signal": meta.get("repetition_signal", 0.0),
            }
            for _, meta, note in surfaced
            if meta.get("relevance_value", 0.0) >= max(args.min_relevance, 0.30) or meta.get("repetition_signal", 0.0) >= 0.35
        ]
        apply_candidates(
            memory_root,
            signal_candidates,
            args.session_key,
            strength="weak",
            source="resurface_candidate",
            activated_at=today.isoformat(),
        )
        payload = load_tags(memory_root)
        notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
        by_path = {n.get("path"): n for n in notes}
        surfaced = [(score, meta, by_path.get(note.get("path"), note)) for score, meta, note in surfaced]

    for score, meta, note in surfaced:
        prompt = f"You previously touched on '{note.get('title')}'. Want me to pull that thread back in?"
        print(f"- priority={score:.3f} | {note.get('title')}")
        print(
            f"  repetition={meta.get('repetition_signal', 0.0):.3f} relevance={meta['relevance_value']:.3f} due_pressure={meta['due_pressure']:.3f} "
            f"overdue={meta['overdue_days']}d importance={note.get('importance')} "
            f"state={note.get('state')} strength={meta.get('memory_strength')}"
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


def apply_session_signal(
    memory_root: Path,
    note_name: str,
    session_key: str | None,
    today: date,
    *,
    strength: str,
    source: str,
) -> None:
    if not session_key:
        return

    import importlib.util

    signal_apply_path = Path(__file__).with_name("signal_apply.py")
    spec = importlib.util.spec_from_file_location("signal_apply", signal_apply_path)
    signal_apply_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(signal_apply_mod)

    original_argv = sys.argv
    try:
        sys.argv = [
            "signal_apply.py",
            note_name,
            "--memory-root",
            str(memory_root),
            "--session-key",
            session_key,
            "--strength",
            strength,
            "--source",
            source,
            "--activated-at",
            today.isoformat(),
        ]
        exit_code = signal_apply_mod.main()
        if exit_code != 0:
            print(f"Warning: signal_apply reported error (exit code {exit_code}).")
    finally:
        sys.argv = original_argv


def apply_feedback_signal(memory_root: Path, note_name: str, useful: str, session_key: str | None, today: date) -> None:
    if useful != "yes" or not session_key:
        return
    apply_session_signal(
        memory_root,
        note_name,
        session_key,
        today,
        strength="strong",
        source="feedback_useful",
    )


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
    apply_feedback_signal(memory_root, matched.get("path") or matched.get("title") or args.note, args.useful, args.session_key, today)
    payload = load_tags(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    refreshed = next((n for n in notes if (n.get("path") == matched.get("path"))), matched)

    note_path = note_file_path(memory_root, refreshed)
    if note_path.exists():
        refreshed_text = note_path.read_text(encoding="utf-8")
        refreshed["strength"] = memory_strength(refreshed)
        refreshed["state"] = parse_heading_value(refreshed_text, "Memory state") or refreshed.get("state")
        refreshed["next_review"] = parse_heading_value(refreshed_text, "Next review") or refreshed.get("next_review")
        refreshed["last_reviewed"] = parse_heading_value(refreshed_text, "Last reviewed") or refreshed.get("last_reviewed")

    save_tags(memory_root, payload)

    matched = refreshed
    strength = matched.get("strength", memory_strength(matched))
    graduated = state == "dormant" and interval_days >= min(DORMANT_INTERVAL_DAYS.values())
    if graduated:
        print(
            f"🎓 Graduated: {matched.get('title')} — well-consolidated after "
            f"{matched.get('review', {}).get('review_count', '?')} reviews. "
            f"State → dormant, strength={strength}, next review in {interval_days} days."
        )
    else:
        print(
            f"Updated {matched.get('title')}: useful={args.useful}, "
            f"state={state}, strength={strength}, interval_days={interval_days}, next_review={next_review}"
        )
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    memory_root = resolve_memory_root(args.memory_root)
    payload = load_tags(memory_root)
    notes = payload.get("notes", []) if isinstance(payload.get("notes"), list) else []
    today = date.today()
    log_path = memory_root / "retrieval-log.md"

    due: list[tuple[float, dict, dict]] = []
    for note in notes:
        next_review = parse_date(note.get("next_review"))
        repeat_value = repetition_signal(note, today)
        if (next_review and next_review <= today) or repeat_value >= 0.35:
            score, meta = resurfacing_priority(note, today, None)
            due.append((score, meta, note))
    due.sort(key=lambda item: item[0], reverse=True)

    if not due:
        print("✓ Nothing due for review today.")
        return 0

    total = len(due)
    print(f"\n{'─' * 60}")
    print(f"  Review session — {total} note(s) due or repeatedly activated")
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
              f"state={note.get('state','?')}  strength={memory_strength(note)}  overdue={overdue}d  "
              f"repeat={meta.get('repetition_signal', 0.0):.3f}  priority={score:.3f}")
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
                save_tags(memory_root, payload)

                graduated = state == "dormant" and interval_days >= min(DORMANT_INTERVAL_DAYS.values())
                strength = note.get("strength", memory_strength(note))
                if graduated:
                    graduated_titles.append(note.get("title", "?"))
                    print(f"  🎓 Graduated! → dormant, strength={strength}, next review +{interval_days}d\n")
                else:
                    arrow = "↑" if useful == "yes" else "↓"
                    print(f"  {arrow} {state} / {strength} | +{interval_days}d → next: {next_review}\n")
                reviewed += 1
                break
            else:
                print("  Enter y, n, s, or q.")

    _save_and_report(payload, memory_root, reviewed, skipped, total, graduated_titles)
    return 0


def _save_and_report(payload: dict, memory_root: Path, reviewed: int, skipped: int, total: int, graduated_titles: list[str]) -> None:
    save_tags(memory_root, payload)
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
    resurface.add_argument("--session-key", default=None, help="stable session identifier for optional weak activation writeback")
    resurface.add_argument("--write-signals", action="store_true", help="write weak activation signals for high-confidence resurfacing hits")

    feedback = sub.add_parser("feedback")
    feedback.add_argument("note")
    feedback.add_argument("--useful", choices=["yes", "no"], required=True)
    feedback.add_argument("--query", default=None)
    feedback.add_argument("--action", default=None)
    feedback.add_argument("--session-key", default=None, help="stable session identifier for real-session signal accumulation")
    feedback.add_argument("--memory-root", default=None)

    session = sub.add_parser("session", help="Interactive batch review of all due or repeatedly activated notes")
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
