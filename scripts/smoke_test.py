#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = SKILL_ROOT.parents[1]


def run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    print(f"$ {' '.join(cmd)}")
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="huiyi-smoke-") as tmp:
        root = Path(tmp)
        memory_root = root / "memory"
        cold_root = memory_root / "cold"
        cold_root.mkdir(parents=True, exist_ok=True)
        (cold_root / "index.md").write_text("# Cold Memory Index\n", encoding="utf-8")
        (cold_root / "tags.json").write_text('{"_meta":{"version":4},"notes":[]}\n', encoding="utf-8")
        (cold_root / "retrieval-log.md").write_text("# Retrieval Log\n", encoding="utf-8")
        template_src = SKILL_ROOT / "references" / "note-template.md"
        if template_src.exists():
            shutil.copy2(template_src, cold_root / "_template.md")
        (memory_root / "heartbeat-state.json").write_text("{}\n", encoding="utf-8")

        py = sys.executable
        scripts = SCRIPT_DIR
        run([py, str(scripts / "create.py"), "--title", "Smoke Test Auto", "--tags", "smoke,test", "--memory-root", str(cold_root)], WORKSPACE_ROOT)
        run([py, str(scripts / "validate.py"), "--memory-root", str(cold_root), "--strict"], WORKSPACE_ROOT)
        run([py, str(scripts / "search.py"), "smoke", str(cold_root)], WORKSPACE_ROOT)
        run([py, str(scripts / "review.py"), "resurface", "--query", "smoke test auto", "--memory-root", str(cold_root)], WORKSPACE_ROOT)
        run([py, str(scripts / "review.py"), "feedback", "smoke-test-auto", "--useful", "yes", "--query", "smoke test auto", "--memory-root", str(cold_root)], WORKSPACE_ROOT)
        run([py, str(scripts / "decay.py"), "--dry-run", "--memory-root", str(cold_root)], WORKSPACE_ROOT)
        run([py, str(scripts / "cool.py"), "status", "--memory-root", str(memory_root)], WORKSPACE_ROOT)

        schedule_path = cold_root / "schedule.json"
        schedule_path.write_text(
            '{\n'
            '  "enabled": true,\n'
            '  "prompt_templates": {"prompt": "建议回忆：{title}"},\n'
            '  "schedules": [\n'
            '    {\n'
            '      "id": "smoke",\n'
            '      "enabled": true,\n'
            '      "allowed_states": ["warm", "cold", "hot", "dormant"],\n'
            '      "require_due": false,\n'
            '      "min_priority": 0.0,\n'
            '      "min_relevance": 0.0,\n'
            '      "delivery_mode": "prompt",\n'
            '      "max_items": 1\n'
            '    }\n'
            '  ]\n'
            '}\n',
            encoding="utf-8",
        )
        run([py, str(scripts / "scheduler.py"), "--schedule-id", "smoke", "--memory-root", str(cold_root), "--config", str(schedule_path), "--query", "smoke test auto"], WORKSPACE_ROOT)

    print("Hui-Yi smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
