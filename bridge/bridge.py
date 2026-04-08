#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# The workspace root (project root)
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (WORKSPACE_ROOT / path).resolve()


def run_scheduler(config: dict, schedule_id: str | None = None) -> dict:
    python_bin = config.get("pythonBin", "python")
    scheduler_script = resolve_path(config.get("schedulerScript", "skills/hui-yi/scripts/scheduler.py"))
    memory_root = resolve_path(config.get("memoryRoot", "memory/cold"))

    cmd = [
        python_bin,
        str(scheduler_script),
        "--memory-root",
        str(memory_root),
        "--json",
    ]
    chosen_schedule_id = schedule_id or config.get("scheduleId")
    if chosen_schedule_id:
        cmd.extend(["--schedule-id", str(chosen_schedule_id)])
    query = config.get("query")
    if query:
        cmd.extend(["--query", str(query)])
    if config.get("preview", False):
        cmd.append("--preview")

    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"scheduler failed: {proc.returncode}")
    return json.loads(proc.stdout)


def load_schedule_ids(config: dict) -> list[str]:
    if config.get("scheduleId"):
        return [str(config["scheduleId"])]
    memory_root = resolve_path(config.get("memoryRoot", "memory/cold"))
    schedule_path = resolve_path(config.get("scheduleConfig", str(memory_root / "schedule.json")))
    payload = load_json(schedule_path)
    schedules = payload.get("schedules", []) if isinstance(payload.get("schedules"), list) else []
    return [
        str(s.get("id"))
        for s in schedules
        if isinstance(s, dict) and s.get("enabled", True) and s.get("id")
    ]


def parse_time_hhmm(value: str | None) -> tuple[int, int] | None:
    if not value or ":" not in value:
        return None
    try:
        hh, mm = value.split(":", 1)
        return int(hh), int(mm)
    except ValueError:
        return None


def quiet_hours_active(now: datetime, quiet_hours: dict | None) -> bool:
    if not isinstance(quiet_hours, dict) or not quiet_hours.get("enabled", False):
        return False
    start = parse_time_hhmm(quiet_hours.get("start"))
    end = parse_time_hhmm(quiet_hours.get("end"))
    if not start or not end:
        return False
    now_minutes = now.hour * 60 + now.minute
    start_minutes = start[0] * 60 + start[1]
    end_minutes = end[0] * 60 + end[1]
    if start_minutes <= end_minutes:
        return start_minutes <= now_minutes < end_minutes
    return now_minutes >= start_minutes or now_minutes < end_minutes


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def within_hours(now_dt: datetime, previous: str | None, hours: float | int | None) -> bool:
    if not hours or float(hours) <= 0:
        return False
    prev_dt = parse_iso_datetime(previous)
    if prev_dt is None:
        return False
    return now_dt - prev_dt < timedelta(hours=float(hours))


def count_recent_global_deliveries(state: dict, now_dt: datetime, hours: float | int | None) -> int:
    if not hours or float(hours) <= 0:
        return 0
    last_delivered = state.get("lastDelivered", {}) if isinstance(state.get("lastDelivered"), dict) else {}
    return sum(1 for ts in last_delivered.values() if within_hours(now_dt, ts, hours))


def schedule_last_delivery(state: dict, schedule_id: str) -> str | None:
    schedule_state = state.get("scheduleLastDelivered", {}) if isinstance(state.get("scheduleLastDelivered"), dict) else {}
    value = schedule_state.get(schedule_id)
    return str(value) if value else None


def policy_allows_candidate(candidate: dict, state: dict, config: dict, now_dt: datetime) -> tuple[bool, str]:
    last_delivered = state.get("lastDelivered", {})
    key = f"{candidate.get('scheduleId')}::{candidate.get('path')}"
    if key in last_delivered:
        return False, "duplicate"

    policy = config.get("deliveryPolicy", {}) if isinstance(config.get("deliveryPolicy"), dict) else {}
    min_score = float(policy.get("minScore", 0.0) or 0.0)
    score = float(candidate.get("score", 0.0) or 0.0)
    if score < min_score:
        return False, "below_policy_threshold"

    prefer_ids = policy.get("preferScheduleIds", []) if isinstance(policy.get("preferScheduleIds"), list) else []
    if prefer_ids and str(candidate.get("scheduleId")) not in {str(x) for x in prefer_ids}:
        return False, "schedule_deprioritized"

    quiet = policy.get("quietHours")
    if quiet_hours_active(now_dt, quiet):
        return False, "quiet_hours"

    global_cooldown = policy.get("globalCooldownHours")
    if count_recent_global_deliveries(state, now_dt, global_cooldown) > 0:
        return False, "global_cooldown"

    schedule_cooldown = policy.get("perScheduleCooldownHours")
    if within_hours(now_dt, schedule_last_delivery(state, str(candidate.get("scheduleId"))), schedule_cooldown):
        return False, "schedule_cooldown"

    max_per_day = int(policy.get("maxDeliveriesPerDay", 0) or 0)
    if max_per_day > 0:
        delivered_today = 0
        for ts in (state.get("lastDelivered", {}) if isinstance(state.get("lastDelivered"), dict) else {}).values():
            prev_dt = parse_iso_datetime(ts)
            if prev_dt and prev_dt.date() == now_dt.date():
                delivered_today += 1
        if delivered_today >= max_per_day:
            return False, "daily_limit"

    return True, key


def candidate_sort_key(candidate: dict) -> tuple:
    note = candidate.get("note", {}) if isinstance(candidate.get("note"), dict) else {}
    meta = candidate.get("meta", {}) if isinstance(candidate.get("meta"), dict) else {}
    score = float(candidate.get("score", 0.0) or 0.0)
    relevance = float(meta.get("relevance", 0.0) or 0.0)
    forgetting_risk = float(meta.get("forgettingRisk", 0.0) or 0.0)
    importance_rank = {"high": 3, "medium": 2, "low": 1}.get(str(note.get("importance", "low")), 0)
    state_rank = {"hot": 4, "warm": 3, "cold": 2, "dormant": 1}.get(str(note.get("state", "dormant")), 0)
    return (score, relevance, forgetting_risk, importance_rank, state_rank)


def select_best_candidate(candidates: list[dict], state: dict, config: dict, now_dt: datetime) -> tuple[dict | None, str | None, list[dict]]:
    ranked = sorted(candidates, key=candidate_sort_key, reverse=True)
    max_candidates = int((config.get("deliveryPolicy", {}) or {}).get("maxCandidates", len(ranked)) or len(ranked))
    rejected: list[dict] = []
    for candidate in ranked[:max_candidates]:
        ok, decision = policy_allows_candidate(candidate, state, config, now_dt)
        if ok:
            return candidate, decision, rejected
        rejected.append({
            "scheduleId": candidate.get("scheduleId"),
            "path": candidate.get("path"),
            "reason": decision,
        })
    return None, None, rejected


def deliver_candidate(candidate: dict, config: dict, delivered_at: str) -> dict:
    delivery = config.get("delivery", {}) if isinstance(config.get("delivery"), dict) else {}
    mode = str(delivery.get("mode", "logOnly"))
    payload = {
        "deliveredAt": delivered_at,
        "mode": mode,
        "scheduleId": candidate.get("scheduleId"),
        "title": candidate.get("title"),
        "path": candidate.get("path"),
        "message": candidate.get("message"),
    }
    if mode == "logOnly":
        payload["status"] = "logged"
        return payload
    if mode == "stdout":
        print(candidate.get("message", ""))
        payload["status"] = "printed"
        return payload
    if mode == "file":
        output_path = resolve_path(delivery.get("outputPath", "skills/hui-yi/bridge/deliveries.log"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        payload["status"] = "written"
        payload["outputPath"] = str(output_path)
        return payload
    if mode == "message":
        # Build a simple text message payload for the OpenClaw message tool.
        # Use the CLI via a shell so that .cmd/.exe wrappers on Windows are found.
        msg_content = {"text": candidate.get("message", "")}
        try:
            # Escape double quotes for the shell command
            escaped_msg = json.dumps(msg_content, ensure_ascii=False).replace('"', '\\"')
            cmd = f"openclaw message send --channel feishu --target ou_cc473c77898e667c521d29abe7bd197a --message \"{escaped_msg}\""
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(WORKSPACE_ROOT),
                shell=True,
            )
            if proc.returncode == 0:
                payload["status"] = "sent"
                payload["messageToolResult"] = proc.stdout.strip()
            else:
                payload["status"] = "failed"
                payload["error"] = proc.stderr.strip() or proc.stdout.strip()
        except Exception as e:
            payload["status"] = "error"
            payload["exception"] = str(e)
        return payload
    raise ValueError(f"Unsupported delivery mode: {mode}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hui-Yi bridge MVP")
    parser.add_argument("--config", default="skills/hui-yi/bridge/config.example.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config_path = resolve_path(args.config)
    config = load_json(config_path)
    if not config.get("enabled", True):
        print("Bridge disabled.")
        return 0

    state_path = resolve_path(config.get("statePath", "skills/hui-yi/bridge/bridge-state.json"))
    state = load_json(state_path)
    state.setdefault("lastDelivered", {})
    state.setdefault("scheduleLastDelivered", {})

    now_dt = datetime.now().astimezone()
    now = now_dt.isoformat(timespec="seconds")
    schedule_ids = load_schedule_ids(config)
    all_candidates: list[dict] = []
    schedule_runs: list[dict] = []
    mode = "normal"

    for schedule_id in schedule_ids:
        payload = run_scheduler(config, schedule_id=schedule_id)
        mode = payload.get("mode", mode)
        candidates = payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []
        schedule_runs.append({
            "scheduleId": schedule_id,
            "candidateCount": len(candidates),
        })
        for candidate in candidates:
            enriched = dict(candidate)
            enriched.setdefault("scheduleId", schedule_id)
            all_candidates.append(enriched)

    ranked_candidates = sorted(all_candidates, key=candidate_sort_key, reverse=True)
    result = {
        "ranAt": now,
        "mode": mode,
        "scheduleRuns": schedule_runs,
        "candidateCount": len(all_candidates),
        "delivered": None,
        "reason": None,
        "selectionPolicy": {
            "sort": ["score", "relevance", "forgettingRisk", "importance", "state"],
            "dedupe": "scheduleId+path",
            "deliveryPolicy": config.get("deliveryPolicy", {}),
        },
    }

    if not ranked_candidates:
        result["reason"] = "no_candidates"
        state["lastRun"] = now
        save_json(state_path, state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    candidate, decision, rejected = select_best_candidate(ranked_candidates, state, config, now_dt)
    if candidate is None or decision is None:
        result["reason"] = "all_candidates_rejected"
        result["rejectedCandidates"] = rejected
        state["lastRun"] = now
        save_json(state_path, state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    is_dry_run = True if args.dry_run or config.get("dryRun", False) else False
    result["delivered"] = {
        "scheduleId": candidate.get("scheduleId"),
        "title": candidate.get("title"),
        "path": candidate.get("path"),
        "message": candidate.get("message"),
        "dryRun": is_dry_run,
    }
    if rejected:
        result["rejectedCandidates"] = rejected
    if is_dry_run:
        result["selectedCandidate"] = candidate
        result["topCandidates"] = ranked_candidates[:3]
    else:
        result["deliveryResult"] = deliver_candidate(candidate, config, now)
    state["lastRun"] = now
    if not is_dry_run:
        state["lastDelivered"][decision] = now
        state["scheduleLastDelivered"][str(candidate.get("scheduleId"))] = now
    save_json(state_path, state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
