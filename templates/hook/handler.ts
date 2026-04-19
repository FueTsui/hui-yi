import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const FALLBACK_WORKSPACE_DIR = process.env.OPENCLAW_WORKSPACE_DIR || process.cwd();
const HOOK_VERSION = "2026-04-13-skill-hit-priority-v4";
const MAX_LOG_BYTES = 256 * 1024;
const KEEP_LOG_BYTES = 128 * 1024;

function looksLikeHuiYiIntent(text: string): boolean {
  const q = (text || "").toLowerCase();
  if (!q.trim()) return false;
  const patterns = [
    /之前/,
    /以前/,
    /有记录吗/,
    /你记得吗/,
    /回忆/,
    /怎么处理/,
    /历史/,
    /延续/,
    /archive this/i,
    /cool this down/i,
    /hui\s*-?yi/i,
    /cold memory/i,
    /remember/i,
    /what did we do before/i
  ];
  return patterns.some((pattern) => pattern.test(text));
}

function extractSkillNames(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[;,|]/)
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
  }
  return [];
}

function hasExplicitHuiYiSkillHit(event: any): boolean {
  const metadata = event?.context?.metadata || {};
  const candidates = [
    metadata.selectedSkill,
    metadata.selected_skill,
    metadata.skill,
    metadata.skill_name,
    metadata.skillName,
    metadata.matchedSkill,
    metadata.matched_skill,
    metadata.skillHits,
    metadata.skill_hits,
    event?.context?.selectedSkill,
    event?.context?.skill,
    event?.context?.skillHits,
  ];

  for (const candidate of candidates) {
    const names = extractSkillNames(candidate);
    if (names.some((name) => name === "hui-yi" || name === "hui yi" || name === "hui_yi")) {
      return true;
    }
  }
  return false;
}

function parseFromAddress(rawFrom: unknown): { channel?: string; id?: string } {
  if (typeof rawFrom !== "string") return {};
  const trimmed = rawFrom.trim();
  if (!trimmed.includes(":")) return { id: trimmed };
  const [channel, ...rest] = trimmed.split(":");
  return { channel: channel || undefined, id: rest.join(":") || undefined };
}

function inferScopeType(event: any): "user" | "chat" {
  const metadata = event?.context?.metadata || {};
  const channelId = String(event?.context?.channelId || "");
  const parsedFrom = parseFromAddress(event?.context?.from);
  if (String(metadata.chat_type || metadata.chatType || "").toLowerCase() === "direct") return "user";
  if (typeof parsedFrom.id === "string" && /^ou_/i.test(parsedFrom.id)) return "user";
  if (channelId.startsWith("user:")) return "user";
  return "chat";
}

function inferScopeId(event: any, scopeType: "user" | "chat"): string | null {
  const metadata = event?.context?.metadata || {};
  const channelId = String(event?.context?.channelId || "");
  const parsedFrom = parseFromAddress(event?.context?.from);
  if (scopeType === "user") {
    const userCandidates = [
      metadata.senderId,
      metadata.sender_id,
      parsedFrom.id
    ];
    for (const candidate of userCandidates) {
      if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
    }
    if (channelId.startsWith("user:")) return channelId.slice("user:".length);
  }
  const chatCandidates = [
    metadata.chatId,
    metadata.chat_id,
    parsedFrom.id
  ];
  for (const candidate of chatCandidates) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  if (channelId.startsWith("chat:")) return channelId.slice("chat:".length);
  if (channelId.startsWith("user:")) return channelId.slice("user:".length);
  return channelId || null;
}

function resolveWorkspaceDir(event: any): string {
  const candidates = [
    event?.context?.workspaceDir,
    event?.context?.sessionEntry?.workspaceDir,
    event?.context?.cfg?.agents?.defaults?.workspace,
    FALLBACK_WORKSPACE_DIR
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim();
    }
  }
  return FALLBACK_WORKSPACE_DIR;
}

function appendHookLog(workspaceDir: string, payload: Record<string, unknown>): void {
  try {
    const logPath = path.join(workspaceDir, "hooks", "hui-yi-signal-hook", "hook.log");
    fs.mkdirSync(path.dirname(logPath), { recursive: true });

    if (fs.existsSync(logPath)) {
      const stats = fs.statSync(logPath);
      if (stats.size > MAX_LOG_BYTES) {
        const buffer = fs.readFileSync(logPath);
        const tail = buffer.subarray(Math.max(0, buffer.length - KEEP_LOG_BYTES));
        fs.writeFileSync(logPath, tail);
      }
    }

    fs.appendFileSync(logPath, `${JSON.stringify(payload)}\n`, "utf8");
  } catch (error) {
    console.warn(`[hui-yi-signal-hook] log write error: ${error instanceof Error ? error.message : String(error)}`);
  }
}

const handler = async (event: any) => {
  const bootstrapWorkspaceDir = resolveWorkspaceDir(event);
  appendHookLog(bootstrapWorkspaceDir, {
    ts: new Date().toISOString(),
    stage: "alive",
    hookVersion: HOOK_VERSION,
    seenType: event?.type || null,
    seenAction: event?.action || null,
    contextDump: {
      channelId: event?.context?.channelId ?? null,
      from: event?.context?.from ?? null,
      parsedFrom: parseFromAddress(event?.context?.from),
      metadata: event?.context?.metadata ?? null,
      hasBodyForAgent: typeof event?.context?.bodyForAgent === "string",
      bodyPreview: typeof event?.context?.bodyForAgent === "string" ? event.context.bodyForAgent.slice(0, 120) : null
    }
  });

  if (event?.type !== "message" || event?.action !== "preprocessed") return;
  const body = String(event?.context?.bodyForAgent || "");
  const workspaceDir = bootstrapWorkspaceDir;
  const explicitSkillHit = hasExplicitHuiYiSkillHit(event);
  const heuristicIntent = looksLikeHuiYiIntent(body);

  if (!explicitSkillHit && !heuristicIntent) {
    appendHookLog(workspaceDir, {
      ts: new Date().toISOString(),
      stage: "skipped",
      hookVersion: HOOK_VERSION,
      reason: "no_skill_hit_or_intent_match",
      action: event?.action,
      type: event?.type,
      bodyPreview: body.slice(0, 200)
    });
    return;
  }

  const scopeType = inferScopeType(event);
  const scopeId = inferScopeId(event, scopeType);
  if (!scopeId) {
    appendHookLog(workspaceDir, {
      ts: new Date().toISOString(),
      stage: "skipped",
      hookVersion: HOOK_VERSION,
      reason: "missing_scope_id",
      bodyPreview: body.slice(0, 200)
    });
    return;
  }

  const parsedFrom = parseFromAddress(event?.context?.from);
  const channel = String(parsedFrom.channel || event?.context?.provider || event?.context?.channelId || "feishu");
  const threadId = typeof event?.context?.metadata?.threadId === "string" ? event.context.metadata.threadId : undefined;

  const scriptPath = path.join(workspaceDir, "skills", "hui-yi", "core", "openclaw_signal_hook.py");
  const args = [
    scriptPath,
    "--query",
    body,
    "--channel",
    channel,
    "--scope-type",
    scopeType,
    "--scope-id",
    scopeId,
    "--trigger-source",
    explicitSkillHit ? "skill_hit" : "heuristic_fallback"
  ];
  if (threadId) args.push("--thread-id", threadId);

  appendHookLog(workspaceDir, {
    ts: new Date().toISOString(),
    stage: "triggered",
    hookVersion: HOOK_VERSION,
    triggerSource: explicitSkillHit ? "skill_hit" : "heuristic_fallback",
    channel,
    scopeType,
    scopeId,
    threadId: threadId || null,
    bodyPreview: body.slice(0, 200)
  });

  void new Promise<void>((resolve) => {
    const child = spawn("python", args, {
      cwd: workspaceDir,
      stdio: ["ignore", "pipe", "pipe"]
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("close", (code) => {
      appendHookLog(workspaceDir, {
        ts: new Date().toISOString(),
        stage: "completed",
        hookVersion: HOOK_VERSION,
        exitCode: code,
        stdout: stdout.trim() || null,
        stderr: stderr.trim() || null
      });
      if (stdout.trim()) console.log(`[hui-yi-signal-hook] ${stdout.trim()}`);
      if (stderr.trim()) console.warn(`[hui-yi-signal-hook] ${stderr.trim()}`);
      resolve();
    });
    child.on("error", (error) => {
      appendHookLog(workspaceDir, {
        ts: new Date().toISOString(),
        stage: "spawn_error",
        hookVersion: HOOK_VERSION,
        error: error instanceof Error ? error.message : String(error)
      });
      console.warn(`[hui-yi-signal-hook] spawn error: ${error instanceof Error ? error.message : String(error)}`);
      resolve();
    });
  });
};

export default handler;
