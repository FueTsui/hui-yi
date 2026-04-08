# Hui Yi Changelog

## 1.0.8 — Bridge relocation and documentation

- Moved the **hui-yi bridge** from `automation/huiyi_bridge/` into the skill package at `skills/hui-yi/bridge/`.
- Updated `README.md` and `SKILL.md` to document the new Bridge (桥接层) module, its configuration, delivery modes, and usage examples.
- Adjusted default configuration paths (`statePath`, `outputPath`) to point to the new bridge directory.
- Added a quick‑run example and clarified how to enable real message delivery via the `message` mode.
- Committed the changes and refreshed the git history.

## 1.0.7 — Helper consolidation and smoke coverage

## 1.0.7 — Helper consolidation and smoke coverage

**Script internals:**
- added `scripts/common.py` to centralize shared helper logic for path resolution, heading parsing, date parsing, tags payload loading, and encoding fallback reads
- refactored `review.py`, `validate.py`, and `decay.py` to use the shared helper layer instead of carrying drift-prone duplicate implementations

**Regression safety:**
- added `scripts/smoke_test.py`, an isolated end-to-end smoke harness that bootstraps a temporary cold-memory tree and runs create / validate / search / resurface / feedback / decay / cool / scheduler in sequence

**Docs:**
- clarified that `scheduler.py --schedule-id ...` runs a specific schedule's filters, not a force-preview mode
- added `scheduler.py --preview` as an explicit debug / preview path for candidate inspection
- documented `common.py`, `smoke_test.py`, and the preview workflow in README / SKILL

---

## 1.0.7 — Earlier completeness pass

**New scripts:**
- `scripts/create.py`: create a note with Ebbinghaus defaults (`interval_days: 1`, `next_review: tomorrow`, auto-rebuild)
- `scripts/validate.py`: schema validation — required sections, enum values, date fields, cross-validates tags.json file references

**review.py additions:**
- `review.py session`: interactive batch review of all due notes; accepts y/n/s/q per note, auto-writes feedback, prints graduation when criteria met
- `REVIEW_LADDER = [1, 3, 7, 14, 30]`: early reviews (review_count ≤ 4) now follow the documented Ebbinghaus ladder exactly instead of the multiplicative formula
- Graduation mechanism: notes with ≥5 reviews, ≥80% success rate, and ≥90d interval transition to `dormant` / 365d
- Fuzzy note matching in `feedback`: accepts slug, exact title, or all-words-in-title keywords
- `StateBias` fix: `hot=1.0, warm=1.0, cold=0.7, dormant=0.3` (previously `hot` and `dormant` shared a 0.6 value)

**search.py addition:**
- `--full-text` flag: searches note file bodies in addition to metadata

**decay.py addition:**
- `--rebuild` flag: automatically runs `rebuild.py` after decay to sync `tags.json`
- Module docstring now clearly documents the required `rebuild.py` post-step

**Documentation:**
- First-time setup section added to `SKILL.md` (steps 1-6 including `retrieval-log.md` and optional scheduler)
- `references/note-template.md` added as standalone blank template (separate from `cold-memory-schema.md`)
- `SKILL.md` and `README.md` updated to `python3`, Python 3.10+ requirement added
- `heartbeat-cooling-playbook.md`: `decay.py` → `rebuild.py` dependency made explicit
- `README.md`: added `session`, `create.py`, `validate.py` commands; scheduler setup instructions

---

## 1.0.6 — Current public release

> Note: entries 1.1.0–1.5.0 below are internal development milestones whose features
> are all included in the 1.0.6 / 1.0.7 published package. They are retained here for
> internal change history only.

Public release version for the current publishable prototype node.

Highlights:
- forgetting-aware cold-memory workflow
- review / resurfacing / feedback loop
- query/context-aware resurfacing
- low-interruption timed-recall scheduler prototype
- compressed docs and improved package consistency

For fuller internal implementation history, see the milestone entries below.

---

## 1.5.0 — Low-interruption recall filtering

**Human-like filtering pass.** Extended `scheduler.py` with low-interruption behavior closer to human recall filtering:
- per-run item caps
- global cooldown windows
- dedupe groups
- quiet-hours delivery mode switching
- optional context gating

**Schedule config expansion.** Added and documented schedule fields such as `max_total_per_day`, `global_cooldown_hours`, `dedupe_by`, `context_required`, and `quiet_hours`.

This keeps timed recall focused on “whether now is a good moment to surface something,” not just “whether something is due.”

---

## 1.4.0 — Timed-recall scheduler prototype

**Scheduled recall prototype.** Added `scripts/scheduler.py` as a low-interruption selector for custom timed recall. It reads schedule config, filters eligible notes, and prints the best recall candidate instead of directly pushing messages.

**Config example.** Added `references/schedule.example.json` as a starter config for custom timed recall design.

**Docs alignment.** Updated manifest, SKILL, and README so the scheduler prototype is part of the documented package surface.

---

## 1.3.0 — Publish polish and context-input resurfacing

**Publish polish.** Cleaned up package consistency issues discovered during release-readiness audit, including proper CLI help behavior for `search.py`.

**Phase-5 context input.** Extended `review.py resurface` to accept:
- `--query`
- `--context-file <file>`
- `--stdin`

This makes resurfacing work with short prompts, saved context snippets, or piped task context instead of only tiny query strings.

**Docs and manifest alignment.** Updated SKILL, README, and manifest text so published docs match actual helper behavior.

---

## 1.2.0 — Query-aware resurfacing audit upgrade

**Phase-4 audit upgrade.** Added a current-context-aware resurfacing path so Hui-Yi no longer ranks candidates only by due status and static metadata.

**New resurfacing logic.** `review.py resurface` now supports:
- `--query "..."`
- relevance scoring across title, summary, semantic_context, tags, triggers, and scenarios
- combined priority using current relevance, forgetting risk, importance, cross-session reuse, and state bias

**Feedback smoothing.** Adjusted `review.py feedback` so state drops are less abrupt for high-importance notes and interval updates are less brittle than a hard yes=×2 / no=÷2 rule.

**Docs alignment.** Updated README and SKILL guidance so documented workflows match the actual review/resurface helper behavior.

This release still uses lightweight lexical-semantic heuristics, not embeddings. It closes the biggest gap from the prior audit by adding a real CurrentRelevance term to resurfacing decisions.

---

## 1.1.0 — Forgetting-aware cold memory upgrade

**Positioning upgrade.** Clarified Hui-Yi as a cold-memory archive plus a forgetting-aware recall layer, instead of a purely passive archive.

**Ebbinghaus / SRS framing.** Added a practical forgetting-curve model:
- review cadence ladder (`+1d`, `+3d`, `+7d`, `+14d`, `+30d`)
- simplified strength / decay guidance
- boundary-of-forgetting resurfacing strategy

**Memory unit model.** Shifted guidance away from raw keyword frequency toward memory units composed of:
- topic or concept bundle
- semantic context
- importance
- state
- review metadata
- recall feedback

**New metadata guidance.** Expanded the documented schema to include:
- `importance`
- `state`
- `last_seen`
- `last_reviewed`
- `next_review`
- `review` subfields

**Recall quality rules.** Added blended recall scoring and stronger guardrails against noisy resurfacing:
- semantic relevance over token overlap
- importance × forgetting risk × current relevance mindset
- active-recall style prompting preferred over note dumping

**Reference docs refreshed.** Updated:
- `SKILL.md`
- `README.md`
- `references/cold-memory-schema.md`
- `references/examples.md`
- `references/heartbeat-cooling-playbook.md`

This release is primarily a skill-design and documentation upgrade. It intentionally stops short of claiming full Anki-style automation in the helper scripts.

---

## 1.0.5 — Remove legacy shell helpers

**Shell helper removal.** Removed legacy `.sh` helper scripts so the skill no longer ships shell wrapper variants alongside the Python helpers.

**Python-only helpers.** Standardized the maintained helper set around the cross-platform Python scripts:
- `search.py`
- `rebuild.py`
- `decay.py`
- `cool.py`

**Release alignment.** Synced the source skill changelog with the published ClawHub/GitHub release so local source history matches the 1.0.5 release contents.

---

## 1.0.2 — Cross-platform update and release alignment

**Cross-platform helpers.** Replaced bash-first operational guidance with Python helper scripts intended to work on Linux, macOS, and Windows using a standard `python` command.

**Helper cleanup.** Renamed Python helpers to remove the `hui_yi_` prefix:
- `hui_yi_search.py` → `search.py`
- `hui_yi_rebuild.py` → `rebuild.py`
- `hui_yi_decay.py` → `decay.py`
- `hui_yi_cool.py` → `cool.py`

**Schema alignment.** Standardized the documented archive shape around the current workspace-friendly formats:
- `index.md` uses one Markdown block per note
- `tags.json` uses `{ _meta, notes[] }`
- note sections use bullet-based values that match existing cold-memory notes

**State handling.** Cooling guidance updates the top-level `coldMemory` object inside `memory/heartbeat-state.json` instead of overwriting the whole file. `rebuild.py` now refreshes `coldMemory.lastIndexRefresh`, and `cool.py scan` uses `lastArchive` for incremental detection.

**Automation is optional.** The skill explicitly works in manual mode when helper scripts are unavailable. Scripts are helpers, not hard dependencies.

**Packaging/docs sync.** Added and aligned:
- `manifest.yaml`
- `README.md`
- manifest notes and reference docs
- legacy shell deprecation messages

**Retrieval quality.** Improved semantic-context extraction during rebuild so prose sections are preserved in `tags.json`.

---

## 1.0.1 — Wording and publishing consistency

Patch release.

Changes:
- replaced Chinese trigger examples with English phrasing in `SKILL.md`
- updated the cold-memory schema reference to use the same English trigger wording
- kept recall semantics unchanged; this release is wording and publishing consistency only

---

## 1.0.0 — Original public release (by Fue Tsui)

Original OpenClaw skill release.

Key characteristics of the early public version:
- instruction-heavy `SKILL.md`
- reference-based cold-memory workflow
- published to ClawHub / GitHub as the initial public baseline
- later identified as needing clearer manifest/path declarations for platform review