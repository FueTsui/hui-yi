---
name: hui-yi-signal-hook
description: "Trigger Hui-Yi session signal accumulation on likely cold-memory / recall turns"
metadata:
  { "openclaw": { "emoji": "🧠", "events": ["message:preprocessed"], "requires": { "bins": ["python"] } } }
---

# Hui-Yi Signal Hook

Workspace hook prototype for Hui-Yi.

Purpose:
- listen on `message:preprocessed`
- prefer explicit Hui-Yi skill-hit metadata when available
- fall back to conservative Hui-Yi / recall / historical-continuity intent detection only when explicit skill-hit metadata is absent
- call `skills/hui-yi/core/openclaw_signal_hook.py`
- default to conservative dry-run behavior unless explicitly changed

This hook is intended as the minimal stable OpenClaw-side integration prototype.
