#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import WORKSPACE_ROOT

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOOK_DIR = WORKSPACE_ROOT / "hooks" / "hui-yi-signal-hook"
DEFAULT_TEMPLATE_DIR = DEFAULT_HOOK_DIR


def load_template(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Template file not found: {path}")
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return f"SKIP {path} (already exists, use --force to overwrite)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"WROTE {path}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Hui-Yi hook files into workspace hooks/")
    parser.add_argument("--force", action="store_true", help="overwrite existing hook files")
    parser.add_argument("--dry-run", action="store_true", help="show planned writes without changing files")
    parser.add_argument("--target-dir", default=str(DEFAULT_HOOK_DIR), help="target hook directory")
    parser.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR), help="template source directory")
    args = parser.parse_args()

    target_dir = Path(args.target_dir)
    template_dir = Path(args.template_dir)

    hook_md_template_path = template_dir / "HOOK.md"
    handler_ts_template_path = template_dir / "handler.ts"

    planned = [
        (target_dir / "HOOK.md", hook_md_template_path),
        (target_dir / "handler.ts", handler_ts_template_path),
    ]

    if args.dry_run:
        for destination, template_path in planned:
            if not template_path.exists():
                print(f"MISSING TEMPLATE {template_path}")
                continue
            if destination.exists() and not args.force:
                print(f"SKIP {destination} (already exists, use --force to overwrite)")
            else:
                print(f"WOULD WRITE {destination} <- {template_path}")
        return 0

    for destination, template_path in planned:
        content = load_template(template_path)
        print(write_file(destination, content, force=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
