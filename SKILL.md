---
name: hui-yi
description: >
  Trigger for cold-memory recall and archive work under memory/cold/. Use for older
  low-frequency context, historical continuity, resurfacing, cooling, rebuild, and
  repetition-driven reinforcement. Do not use for fresh daily notes, stable high-frequency
  facts, tooling/setup notes, or unvalidated new learnings.
---

# Hui Yi — Cold memory reinforcement

Hui Yi manages the **cold reinforcement layer** under `memory/cold/`.

Core rule:

**Repeatedly reactivated information deserves reinforcement first. Ebbinghaus sets the pace, not the sole trigger.**

## Use Hui Yi when

- older low-frequency context would materially improve the current answer
- the user asks what was done before, asks to recall/archive something, or wants historical continuity
- a reusable lesson, decision, troubleshooting result, or stable background note should be preserved in `memory/cold/`
- durable content from daily notes should be cooled into cold memory
- cold-memory notes, metadata, or retrieval quality need maintenance

## Do not use Hui Yi when

- the content is today's transient note → `memory/YYYY-MM-DD.md`
- the content is a stable high-frequency fact → `MEMORY.md`
- the content is tooling, machine path, or environment setup → `TOOLS.md`
- the content is a fresh mistake or still-unvalidated lesson → `.learnings/`
- the content contains secrets, tokens, or passwords

## Boundary

OpenClaw primary memory handles:
- current chat continuity
- recent daily notes
- stable high-frequency facts
- tooling and environment notes
- fresh learnings

Hui Yi handles:
- low-frequency, high-value knowledge under `memory/cold/`
- historical context that keeps resurfacing across real conversations
- durable experience, decisions, and troubleshooting notes that should not pollute primary memory

Selection rule:
- high-frequency and stable → primary memory
- low-frequency but high-value → Hui Yi
- fresh daily context → keep warm first, cool later if it proves durable
- tooling/environment notes → `TOOLS.md`
- unvalidated lessons → `.learnings/`

## Operating model

Treat each note as a **memory unit**, not a raw keyword.
A memory unit may be a lesson, fact, decision, troubleshooting result, or durable background note.

Prioritize:
1. repeated activation in real conversations
2. semantic relevance to the current task
3. due pressure relative to current interval
4. importance
5. reinforcement strength

Working rules:
- repeated useful mentions strengthen memory
- successful recall advances the interval
- failed recall resets to a short relearning step (`+1d` or `+2d`)
- `dormant` is for consolidated archive material, not punished failures

## Expected metadata

Cold notes remain Markdown, with metadata such as:
- `Importance`
- `Memory state` (`hot | warm | cold | dormant`)
- `Last seen`, `Last reviewed`, `Next review`
- review cadence / counts / success / fail / retrieval / reinforcement
- session signals (`current_session_hits`, `recent_session_hits`, `cross_session_repeat_count`, `consecutive_session_count`, `last_activated`)
- `Confidence`, `Last verified`, `Related tags`

## Retrieval and review rules

When retrieving:
1. Check current conversation first.
2. Check warm memory / `MEMORY.md` / `TOOLS.md` / `.learnings/` when appropriate.
3. Use cold memory only when archival context would materially help.
4. Open as few notes as possible, ideally 1 and no more than 3.
5. Summarize instead of pasting raw notes unless asked.
6. Log meaningful cold-memory retrievals in `memory/cold/retrieval-log.md`.

When reviewing:
1. Repeated activation is the primary trigger.
2. `Next review` is secondary pressure, not the only gate.
3. Use active recall first, then reveal the note.
4. Success advances one interval step.
5. Failure resets to a short relearning step.
6. Repeatedly useful notes become stronger memory.
7. Move to `dormant` only after repeated successful consolidation or explicit archive intent.

## Archiving and maintenance

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

During maintenance:
- merge overlapping notes
- sharpen summaries, triggers, and semantic context
- demote stale or noisy notes carefully
- review `retrieval-log.md` for never-recalled, unmatched, unhelpful, or repeatedly useful items
- do not let decay logic silently postpone overdue reviews

Favor a smaller, sharper archive over a large fuzzy one.

## Files and scripts

Cold-memory area:
- `memory/cold/index.md`
- `memory/cold/tags.json`
- `memory/cold/retrieval-log.md`
- `memory/cold/_template.md`
- `memory/cold/schedule.json`
- `memory/heartbeat-state.json`

Key scripts:
- `create.py` create note with defaults and initial session signals
- `validate.py` validate notes and metadata references
- `search.py` search metadata or full text
- `rebuild.py` rebuild `index.md` and `tags.json`
- `decay.py` light maintenance without silently postponing due review
- `cool.py` scan daily notes and update heartbeat cold-memory stats
- `review.py` due, session review, resurface, feedback
- `scheduler.py` timed selector with repetition-sensitive gating
- `signal_detect.py` / `signal_pipeline.py` for session activation signals
- `openclaw_signal_hook.py` / `openclaw_runtime_probe.py` for integration validation
- `smoke_test.py` for isolated end-to-end verification

## Error handling

- missing `memory/cold/` → bootstrap it
- missing or malformed `index.md` / `tags.json` → run `rebuild.py`
- missing `retrieval-log.md` → recreate standard header
- missing `heartbeat-state.json` → create with top-level `coldMemory`
- dangling note path in metadata → repair index / tags
- noisy resurfacing → tighten thresholds before adding more notes
- unsure where content belongs → ask the user

## Sanity check

Before shipping script changes, run:

```bash
python3 skills/hui-yi/scripts/smoke_test.py
```

## Read only when needed

- `README.md`
- `references/cold-memory-schema.md`
- `references/examples.md`
- `references/heartbeat-cooling-playbook.md`
- `references/integration-patterns.md`
- `references/real-session-signals-design.md`
- `references/openclaw-integration-design.md`
- `references/openclaw-runtime-prototype.md`
- `bridge/README.md`
