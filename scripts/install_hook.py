#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import WORKSPACE_ROOT

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOOK_DIR = WORKSPACE_ROOT / "hooks" / "hui-yi-signal-hook"
DEFAULT_TEMPLATE_DIR = SKILL_ROOT / "hooks" / "hui-yi-signal-hook"
DEFAULT_CONFIG_PATH = WORKSPACE_ROOT.parent / "openclaw.json"
HOOK_NAME = "hui-yi-signal-hook"


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


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_hook_enabled(config: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    hooks = config.setdefault("hooks", {})
    internal = hooks.setdefault("internal", {})
    if internal.get("enabled") is not True:
        internal["enabled"] = True
        notes.append("SET hooks.internal.enabled = true")
    entries = internal.setdefault("entries", {})
    entry = entries.setdefault(HOOK_NAME, {})
    if entry.get("enabled") is not True:
        entry["enabled"] = True
        notes.append(f"SET hooks.internal.entries.{HOOK_NAME}.enabled = true")
    return config, notes


def write_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Hui-Yi hook files into workspace hooks/ from skill-bundled templates")
    parser.add_argument("--force", action="store_true", help="overwrite existing hook files")
    parser.add_argument("--dry-run", action="store_true", help="show planned writes without changing files")
    parser.add_argument("--enable", action="store_true", help="also enable the hook in openclaw.json")
    parser.add_argument("--target-dir", default=str(DEFAULT_HOOK_DIR), help="target hook directory")
    parser.add_argument("--template-dir", default=str(DEFAULT_TEMPLATE_DIR), help="template source directory")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH), help="path to openclaw.json")
    args = parser.parse_args()

    target_dir = Path(args.target_dir)
    template_dir = Path(args.template_dir)
    config_path = Path(args.config_path)

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
        if args.enable:
            config = load_config(config_path)
            _, notes = ensure_hook_enabled(config)
            if notes:
                for note in notes:
                    print(f"WOULD {note}")
            else:
                print(f"HOOK ALREADY ENABLED in {config_path}")
        return 0

    for destination, template_path in planned:
        content = load_template(template_path)
        print(write_file(destination, content, force=args.force))

    if args.enable:
        config = load_config(config_path)
        config, notes = ensure_hook_enabled(config)
        write_config(config_path, config)
        if notes:
            for note in notes:
                print(note)
        else:
            print(f"HOOK ALREADY ENABLED in {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
