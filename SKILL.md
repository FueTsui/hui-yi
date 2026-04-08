---
name: hui-yi
description: >
  Trigger for cold-memory recall and archive work under memory/cold/. Strong triggers:
  "do you remember", "what did we do before", "archive this", "cool this down",
  "有记录吗", "之前怎么处理", older low-frequency context, historical continuity,
  recall / resurfacing / cooling / rebuild / decay. Strong excludes: fresh daily notes
  (→ memory/YYYY-MM-DD.md), high-frequency facts (→ MEMORY.md), tool/setup notes
  (→ TOOLS.md), and fresh learnings still being validated (→ .learnings/).
---

# Hui Yi — Forgetting-aware Cold Memory

Archive low-frequency, high-value knowledge, then resurface it only when it is both relevant now and at risk of being forgotten.

## What this skill manages

Hui Yi manages the **cold** layer, not the whole memory stack.

Memory layers:
- **Active**: current chat and current task
- **Warm**: recent daily files and near-term context
- **Cold**: durable low-frequency knowledge in `memory/cold/`
- **Dormant**: archived items that should rarely surface unless strongly triggered

Use Hui Yi for:
- archiving reusable lessons, background, and stable historical context
- recalling older context that would materially improve the current answer
- cooling daily notes into cold memory
- maintaining cold-memory quality, review timing, and retrieval metadata

Do **not** use Hui Yi for:
- today's transient notes → `memory/YYYY-MM-DD.md`
- high-frequency project or personal facts → `MEMORY.md`
- tool paths, setup quirks, machine notes → `TOOLS.md`
- fresh mistakes or unvalidated lessons → `.learnings/`

## Core model

The unit is a **memory unit**, not a raw keyword.
A memory unit can be a reusable lesson, decision, fact, troubleshooting result, or durable background note.

Do not rank memories by word frequency alone.
Use a blend of:
- semantic relevance
- forgetting risk
- importance
- cross-session reuse
- recall feedback

Working principle:

```text
Priority ≈
  0.35 * CurrentRelevance
+ 0.25 * ForgettingRisk
+ 0.20 * Importance
+ 0.10 * CrossSessionReuse
+ 0.10 * StateBias
```

## Memory metadata

Cold notes remain Markdown, but Hui Yi expects metadata like:
- `Importance`: high | medium | low
- `Memory state`: hot | warm | cold | dormant
- `Last seen` — last time this note appeared in a conversation or task
- `Last reviewed` — last time the note was explicitly reviewed for recall quality
- `Next review` — scheduled date for the next spaced review
- `Review cadence`
  - `interval_days` — current review interval (starts at 1, grows with each success)
  - `review_count`
  - `review_success`
  - `review_fail`
- `Confidence` — reliability of the note's content (high | medium | low)
- `Last verified` — last time the **content** was confirmed still accurate and current.
  This is NOT updated during recall feedback; only update it when you re-verify the
  underlying information against source of truth.
- `Related tags`

States:
- **hot**: recently reinforced, okay to inject when useful
- **warm**: good prompted-recall candidate
- **cold**: preserved, lower urgency
- **dormant**: keep archived, surface only with a strong trigger

## Recall rules

Prefer **active recall** over passive dumping.
Good pattern:
- “You previously touched on X. Want me to pull that thread back in?”

Avoid:
- long unsolicited note dumps
- surfacing weakly related archive material
- recalling based on one noisy keyword match

When retrieving:
1. Check current conversation first.
2. Check warm memory / `MEMORY.md` / `TOOLS.md` / `.learnings/` when appropriate.
3. Use cold memory only when archival context would materially help.
4. Open the fewest notes possible, ideally 1 and no more than 3.
5. Summarize, do not paste raw notes unless asked.
6. Log meaningful cold-memory retrievals in `memory/cold/retrieval-log.md`.

## Requirements

Python 3.10+ (`X | Y` union-type syntax used throughout the helper scripts).

## First-time setup

If `memory/cold/` does not exist, bootstrap it:

1. Create `memory/cold/` directory.
2. Create `memory/cold/index.md` with header `# Cold Memory Index`.
3. Create `memory/cold/tags.json`:
   ```json
   { "_meta": { "version": 4 }, "notes": [] }
   ```
4. Copy `references/note-template.md` → `memory/cold/_template.md`
   (`cold-memory-schema.md` is the full schema reference; keep it separate from `_template.md`).
5. Create `memory/cold/retrieval-log.md` — just the header line:
   ```
   # Retrieval Log
   ```
   The `review.py feedback` and `review.py session` commands append rows automatically.
6. **Optional — timed recall scheduler:**
   ```bash
   cp references/schedule.example.json memory/cold/schedule.json
   # then edit schedule.json: timezone, cron time, min_importance, etc.
   ```

## Storage layout

```text
memory/
├── cold/
│   ├── index.md
│   ├── tags.json
│   ├── retrieval-log.md
│   ├── _template.md
│   ├── schedule.json        ← optional, copy from references/schedule.example.json
│   └── <topic>.md
├── heartbeat-state.json

skills/hui-yi/scripts/
├── common.py    ← shared path / parse / JSON helpers
├── create.py    ← new note with Ebbinghaus defaults
├── validate.py  ← schema validation
├── search.py
├── rebuild.py
├── decay.py
├── cool.py
├── review.py
├── scheduler.py
└── smoke_test.py
```

## Script roles

- `create.py --title "..."`: create a new note with Ebbinghaus defaults (`interval_days: 1`, `next_review: tomorrow`)
- `validate.py`: check all notes against the schema; cross-validate tags.json file references
- `search.py <query>`: search cold-memory metadata by keyword/query
- `search.py <query> --full-text`: also search note file bodies (not just metadata)
- `rebuild.py`: rebuild `index.md` and `tags.json` from note files
- `decay.py [--rebuild]`: decay stale notes; `--rebuild` syncs tags.json in one step
- `cool.py`: scan daily notes and update heartbeat cold-memory stats
- `review.py due`: list notes due for review
- `review.py session`: **interactive batch review** — presents each due note's TL;DR, collects y/n/s/q, applies Ebbinghaus intervals, handles graduation
- `review.py resurface --query "..."`: rank resurfacing candidates using a short topic query
- `review.py resurface --context-file <file>` / `--stdin`: rank resurfacing candidates using richer context
- `review.py feedback <note>`: single-note feedback; `<note>` accepts slug, title, or keywords
- `scheduler.py`: timed-recall selector driven by schedule config with cooldown, dedupe, and quiet-hours filters
- `smoke_test.py`: isolated end-to-end smoke test that bootstraps a temp cold-memory root and runs the core scripts in sequence

### Scheduler setup

`scheduler.py` reads `memory/cold/schedule.json`. To enable it:

```bash
cp references/schedule.example.json memory/cold/schedule.json
# then edit memory/cold/schedule.json to match your preferred schedule and timezone
```

The example config runs a daily evening review at 21:00, surfaces one high-importance note, and applies quiet hours from 22:30 to 08:00.

Important:
- `--schedule-id` means “run this schedule's filters now”, not “force a candidate for preview”
- `--preview` is the explicit debug mode. It bypasses due, importance, allowed_states, cooldown, and relevance-required gating so you can inspect candidate ranking for that schedule

## Review cadence

Default ladder for notes that merit reinforcement:
- creation
- +1 day
- +3 days
- +7 days
- +14 days
- +30 days

After that:
- helpful recall → extend interval
- unhelpful recall → shorten interval or cool further
- high-importance notes should degrade more slowly than low-importance notes

## Archiving rules

Archive only if at least one is true:
- it will still matter after 30 days
- it captures a reusable lesson or workflow
- it would materially improve a future answer or decision
- the user explicitly wants it preserved

Before archiving, route elsewhere if it belongs in:
- `memory/YYYY-MM-DD.md`
- `MEMORY.md`
- `TOOLS.md`
- `.learnings/`
- `AGENTS.md` / `SOUL.md`

Never store secrets, tokens, or passwords in cold memory.

## Maintenance rules

During maintenance:
- merge overlapping notes
- sharpen summaries, triggers, and semantic context
- demote stale or noisy notes
- review `retrieval-log.md` for:
  - notes never recalled
  - unmatched queries
  - unhelpful recalls
  - repeatedly useful recalls

Favor a smaller, sharper archive over a large fuzzy one.

## Error handling

- missing `memory/cold/` → bootstrap it
- missing or malformed `index.md` / `tags.json` → rebuild with `rebuild.py`
- missing `retrieval-log.md` → recreate standard header
- missing `heartbeat-state.json` → create with top-level `coldMemory`
- dangling note path in metadata → repair index / tags
- noisy resurfacing → tighten thresholds before adding more notes
- unsure where content belongs → ask the user

## Development sanity check

Before shipping script changes, run:

```bash
python3 skills/hui-yi/scripts/smoke_test.py
```

This boots an isolated temporary cold-memory tree and exercises create, validate, search, resurface, feedback, decay, cool, and scheduler.

## References

Read only when needed:
- `references/cold-memory-schema.md` → note/index/tags structure
- `references/examples.md` → concrete note examples
- `references/heartbeat-cooling-playbook.md` → cooling workflow
- `references/integration-patterns.md` → trigger modes, heartbeat/cron integration, scheduler boundary, preview vs normal mode

Core rule:

**archive less, but archive better. recall less, but recall at the right time.**

## Bridge (桥接层)

`skills/hui-yi/bridge/bridge.py` 是一个轻量桥接层，用于在调度 (`scheduler.py`) 与实际投递之间完成筛选、去重、频控等策略。默认配置位于 `skills/hui-yi/bridge/config.example.json`，其中已设置 `statePath`、`outputPath` 指向 bridge 目录。

### 关键功能
- **统一配置**：`config.example.json` 包含 `deliveryPolicy`（`maxCandidates`、`minScore`、`globalCooldownHours`、`perScheduleCooldownHours`、`maxDeliveriesPerDay`、`quietHours` 等）。
- **投递模式**：`logOnly`（默认，仅记录返回 JSON），`stdout`（打印），`file`（写入 `deliveries.log`），`message`（占位，后续可接 OpenClaw 消息工具）。
- **dry‑run / preview**：`--dry-run` 或 `dryRun:true` 只输出结果，不修改状态或投递。
- **状态持久化**：`bridge-state.json` 记录上一次运行时间、已投递记录，以实现去重与频控。

### 使用示例
```bash
# 预览候选（不投递）
python3 skills/hui-yi/bridge/bridge.py --dry-run

# 正式投递（默认 logOnly）
python3 skills/hui-yi/bridge/bridge.py
```

如需实际向用户发送消息，请将 `delivery.mode` 改为 `message` 并在后续集成中使用 OpenClaw `message` API。