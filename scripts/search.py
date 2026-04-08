#!/usr/bin/env python3
"""Search Hui-Yi cold memory metadata by keyword or short query."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[2]
DEFAULT_MEMORY_ROOT = WORKSPACE_ROOT / "memory" / "cold"
STATE_BOOST = {"hot": 0.2, "warm": 0.35, "cold": 0.25, "dormant": 0.05}
IMPORTANCE_BOOST = {"high": 0.35, "medium": 0.2, "low": 0.05}


def resolve_memory_root(arg: str | None) -> Path:
    if arg:
        candidate = Path(arg)
        return candidate if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
    return DEFAULT_MEMORY_ROOT


def load_tags(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        notes = data.get("notes", [])
        return notes if isinstance(notes, list) else []
    if isinstance(data, list):
        return data
    return []


def score_note(note: dict, query_terms: list[str]) -> tuple[float, dict]:
    fields = {
        "title": note.get("title", ""),
        "summary": note.get("summary", ""),
        "semantic_context": note.get("semantic_context", ""),
        "tags": " ".join(note.get("tags", []) if isinstance(note.get("tags"), list) else []),
        "triggers": " ".join(note.get("triggers", []) if isinstance(note.get("triggers"), list) else []),
        "scenarios": " ".join(note.get("scenarios", []) if isinstance(note.get("scenarios"), list) else []),
    }

    score = 0.0
    matched_fields = []
    for term in query_terms:
        term = term.lower().strip()
        if not term:
            continue
        if term in fields["title"].lower():
            score += 1.8
            matched_fields.append("title")
        if term in fields["summary"].lower():
            score += 1.2
            matched_fields.append("summary")
        if term in fields["semantic_context"].lower():
            score += 1.1
            matched_fields.append("semantic_context")
        if term in fields["tags"].lower():
            score += 0.8
            matched_fields.append("tags")
        if term in fields["triggers"].lower():
            score += 0.9
            matched_fields.append("triggers")
        if term in fields["scenarios"].lower():
            score += 0.7
            matched_fields.append("scenarios")

    score += IMPORTANCE_BOOST.get(note.get("importance", "medium"), 0.0)
    score += STATE_BOOST.get(note.get("state", "cold"), 0.0)
    return score, {"matched_fields": sorted(set(matched_fields))}


def search_full_text(memory_root: Path, query_terms: list[str]) -> list[tuple[str, int, str]]:
    """Search note file bodies for query terms. Returns (filename, line_no, line) hits."""
    skip = {"index.md", "retrieval-log.md", "_template.md"}
    hits: list[tuple[str, int, str]] = []
    for path in sorted(memory_root.rglob("*.md")):
        if path.name in skip:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            line_lower = line.lower()
            if any(term in line_lower for term in query_terms):
                hits.append((path.name, lineno, line.rstrip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Hui-Yi cold memory metadata by keyword or short query")
    parser.add_argument("query", help="keyword or short query")
    parser.add_argument("memory_root", nargs="?", default=None, help="optional cold memory root")
    parser.add_argument(
        "--full-text",
        action="store_true",
        help="Also search inside note file bodies, not just metadata",
    )
    args = parser.parse_args()

    query_raw = args.query
    query_terms = [part for part in query_raw.lower().split() if part.strip()]
    memory_root = resolve_memory_root(args.memory_root)
    index_path = memory_root / "index.md"
    tags_path = memory_root / "tags.json"

    print(f"=== Searching cold memory for: {query_raw} ===\n")

    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").splitlines()
        hits = [(i + 1, line) for i, line in enumerate(lines) if any(term in line.lower() for term in query_terms)]
        if hits:
            print("## index.md matches:")
            for line_no, line in hits:
                print(f"{line_no}: {line}")
            print()
        else:
            print("## No matches in index.md\n")
    else:
        print(f"## index.md not found at {index_path}\n")

    notes = load_tags(tags_path)
    if not notes:
        print(f"## tags.json not found or empty at {tags_path}")
    else:
        ranked = []
        for note in notes:
            score, meta = score_note(note, query_terms)
            if score >= 1.0:
                ranked.append((score, note, meta))

        if not ranked:
            print("## No matches in tags.json")
        else:
            ranked.sort(key=lambda item: item[0], reverse=True)
            print("## ranked tags.json matches:")
            for score, note, meta in ranked[:10]:
                print(f"- score={score:.2f} | {note.get('title', 'untitled')} -> {note.get('path', '(missing path)')}")
                print(
                    f"  importance={note.get('importance', 'medium')} state={note.get('state', 'cold')} "
                    f"confidence={note.get('confidence', 'unknown')} next_review={note.get('next_review', 'n/a')}"
                )
                matched_fields = ", ".join(meta.get("matched_fields", [])) or "n/a"
                print(f"  matched_fields={matched_fields}")
            print()

    if args.full_text:
        ft_hits = search_full_text(memory_root, query_terms)
        if ft_hits:
            print("## full-text matches in note files:")
            last_file = ""
            for filename, lineno, line in ft_hits[:40]:
                if filename != last_file:
                    print(f"\n  {filename}")
                    last_file = filename
                print(f"  {lineno:4d}: {line}")
            if len(ft_hits) > 40:
                print(f"\n  ... {len(ft_hits) - 40} more lines omitted (narrow your query)")
            print()
        else:
            print("## No full-text matches in note files\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())