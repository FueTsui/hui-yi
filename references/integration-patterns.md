# Trigger Modes + Integration Patterns

这份文档专门解释 Hui-Yi **怎么被触发**、**谁来调用脚本**、以及它如何和 heartbeat / cron / 上层 agent 对接。

---

## 1. Trigger Modes

Hui-Yi 不是常驻守护进程，也不是安装后自动执行的后台服务。

它有三种触发模式：

### A. Semantic Trigger（语义触发）

当当前请求明显涉及以下意图时，优先考虑 Hui-Yi：

- 回忆旧上下文
- 询问“之前怎么处理的”
- 要求 archive / cool / 冷却 / 归档
- 需要低频但高价值的历史背景来补强当前回答

典型触发语句：
- do you remember
- how did we handle that
- archive this
- cool this down
- 回忆一下 / 之前 / 以前 / 你记得吗 / 有记录吗

**责任边界：**
- 上层 agent 决定是否命中 skill
- Hui-Yi 负责说明应该查哪里、怎么查、怎么写回
- 真正执行时，由 agent 显式运行脚本或读写文件

### B. Maintenance Trigger（维护触发）

当目标是定期维护 cold memory，而不是回答一个具体问题时，触发 Hui-Yi 的维护流程。

适合：
- cooling recent daily notes
- rebuild / validate / decay
- heartbeat 例行维护
- 发布前巡检

常见入口：
- `cool.py scan`
- `decay.py --dry-run`
- `rebuild.py`
- `validate.py --strict`
- `smoke_test.py`

**责任边界：**
- 外部 heartbeat / cron / 人工维护流程 触发
- Hui-Yi 只提供维护规则和脚本接口，不自己调度自己

### C. Debug Trigger（调试触发）

当你要检查 skill 是否健康、某个筛选是否正确、或者发布前回归时，进入调试模式。

适合：
- 冒烟测试
- schema 校验
- scheduler 预览
- 文档与实现对齐检查

常见入口：
- `python3 skills/hui-yi/scripts/smoke_test.py`
- `python3 skills/hui-yi/scripts/validate.py --strict`
- `python3 skills/hui-yi/scripts/scheduler.py --schedule-id <id> --preview --query "..."`

**责任边界：**
- 由开发者 / 维护者显式触发
- 不应被误当成正常用户工作流的一部分

---

## 2. Who actually starts the skill?

Hui-Yi 的启动链条通常是：

1. 上层 agent 发现当前意图和 Hui-Yi 匹配
2. agent 读取 `SKILL.md`
3. agent 决定是否读取 cold-memory 文件，或运行某个 helper script
4. helper script 执行具体动作

所以 Hui-Yi 的真正入口不是某个 daemon，而是：

- `SKILL.md` 的触发描述
- 上层 agent 的技能选择逻辑
- 外部维护流程（heartbeat / cron / manual run）

---

## 3. Integration Patterns

### Pattern 1: In-chat recall（对话内回忆）

适用：
- 用户问“之前有记录吗”
- 当前回答明显需要历史上下文补强

建议流程：
1. 先看当前对话和 warm memory
2. 再决定是否进入 cold memory
3. 如需查询，优先用 `search.py` / `review.py resurface`
4. 总结结果，不直接 dump 原始 note

建议脚本：
- `search.py <query>`
- `review.py resurface --query "..."`
- `review.py resurface --context-file <file>`

### Pattern 2: Heartbeat maintenance（心跳维护）

适用：
- 周期性扫描最近 daily notes
- 低打扰地做 cooling 维护

建议流程：
1. `cool.py scan`
2. 判断哪些 daily notes 值得进入 cold memory
3. 需要时更新 / 新建 cold note
4. `rebuild.py`
5. `cool.py done <reviewed> <archived> <merged>`

说明：
- heartbeat 负责“什么时候检查”
- Hui-Yi 负责“检查时怎么处理”
- 不建议 heartbeat 每次都大扫除

### Pattern 3: Cron-driven scheduled recall（外部定时回忆）

适用：
- 你已经有 cron / scheduler 桥接
- 想定时挑选一个值得提醒的旧 note

建议流程：
1. 外部 cron 定时运行 `scheduler.py`
2. `scheduler.py` 输出候选 note
3. 上层 agent / workflow 决定是否真的发给用户

重要：
- `scheduler.py` 是 **selector**，不是发消息守护进程
- 它负责选候选，不负责投递

常见命令：
- 正常模式：
  - `python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review`
- 调试预览：
  - `python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review --preview --query "..."`

### Pattern 4: Release / audit workflow（发布前巡检）

适用：
- 发 ClawHub / GitHub 之前
- 审计或大改之后

建议流程：
1. `smoke_test.py`
2. `validate.py --strict`
3. scheduler 正常 / preview 各跑一次
4. 对照 `references/publish-checklist.md`
5. 确认 manifest / docs / version 同步

---

## 4. Normal mode vs Preview mode

### `--schedule-id`
表示：
- 只运行某条 schedule 的筛选规则

不表示：
- 强制返回一个候选

所以如果该 schedule 本身要求：
- due
- high importance
- allowed_states
- cooldown

那它依然可能返回：
- `No scheduled recall candidates right now.`

### `--preview`
表示：
- 调试 / 预览模式
- 用于看候选排序
- 会绕过 due、importance、allowed_states、cooldown、require_relevance 等正式门槛

适合：
- 开发时检查配置
- 发布前验证 scheduler 没死
- 排查“为什么现在没候选”

---

## 5. Recommended boundaries

### Hui-Yi 应该负责
- 冷记忆的结构规则
- recall / archive / maintenance 的方法论
- helper scripts
- 候选选择与元数据维护

### Hui-Yi 不应该负责
- 自动发消息
- 自己注册 cron
- 自己决定何时打扰用户
- 代替上层 agent 做最终沟通判断

一句话：

**Hui-Yi 负责记忆策略和候选选择，上层系统负责调度与沟通。**

---

## 6. Bridge MVP 设计稿

如果你想增加“自动常驻插件”，推荐做一个**薄桥接层**，不要把 Hui-Yi 本体改成守护进程。

### 6.1 目标

Bridge MVP 只负责：
- 定时唤起
- 调用 `scheduler.py`
- 解析候选结果
- 做最小去重 / 限流 / quiet-hours 控制
- 把候选交给上层消息或 agent 层投递

Hui-Yi 本体继续负责：
- 冷记忆方法论
- note 结构与元数据
- recall / archive / cooling / rebuild / decay / scheduler 逻辑

一句话：

**Hui-Yi 负责选候选，Bridge 负责定时、去重、投递。**

### 6.2 最小分层

#### A. Hui-Yi skill 层
保留现状，不改职责：
- `scheduler.py` 负责候选筛选
- `review.py` / `search.py` 负责 recall
- `cool.py` / `rebuild.py` / `decay.py` 负责维护

#### B. Bridge 常驻层
新增一个很薄的桥接器，例如：
- `huiyi-bridge`
- `cold-memory-bridge`

负责：
- 轮询 schedule
- 调 Hui-Yi scheduler
- 保存 bridge 自己的状态
- 决定是否投递

#### C. Messaging / Agent 层
负责真正发消息：
- 发给用户
- 发到主会话
- 或交给上层 workflow 继续处理

### 6.3 MVP 组件

#### 1) Scheduler Runner
作用：
- 周期性运行 `scheduler.py`

输入：
- `memory/cold/schedule.json`

输出：
- 候选 note
- 或无候选

#### 2) Bridge State Store
建议单独维护：
- `memory/cold/bridge-state.json`

最小记录：
- 上次运行时间
- 每条 schedule 最近触发时间
- 最近一次投递的 note
- 去重信息
- 最近错误

示例：

```json
{
  "lastRun": "2026-04-08T21:00:00+08:00",
  "schedules": {
    "daily-evening-review": {
      "lastTriggered": "2026-04-08T21:00:00+08:00",
      "lastDeliveredNote": "memory/cold/foo.md"
    }
  }
}
```

#### 3) Candidate Normalizer
Bridge 需要把 `scheduler.py` 输出转成统一结构，例如：

```json
{
  "scheduleId": "daily-evening-review",
  "title": "Foo memory",
  "path": "memory/cold/foo.md",
  "score": 0.73,
  "deliveryMode": "prompt",
  "message": "你之前提过「Foo memory」..."
}
```

第一版如果 `scheduler.py` 还没有 `--json`，Bridge 就只能做文本解析。
所以长期建议：
- 后续给 `scheduler.py` 增加 `--json`

#### 4) Delivery Policy
Bridge 只做最小决策：

允许投递：
- 有候选
- 不在桥接层静默期
- 没重复投过
- 当前 schedule 没超限

拒绝投递：
- quiet hours
- cooldown 未过
- 候选重复
- 配置要求 dry-run / log-only

#### 5) Delivery Adapter
Bridge 不自己做外部 HTTP 发消息，而是调用上层系统已有消息能力。

也就是说：
- Hui-Yi 不负责发消息
- Bridge 也不直接绑定外部平台 SDK
- 最终投递仍走 OpenClaw 现有消息层

### 6.4 最小执行流

正常模式：
1. bridge 定时醒来
2. 读取 `schedule.json`
3. 遍历启用的 schedule
4. 调 `scheduler.py`
5. 如果有候选，标准化输出
6. 读取 `bridge-state.json` 做去重与限流判断
7. 满足条件则交给上层投递
8. 更新 `bridge-state.json`

### 6.5 推荐目录

如果单独做桥接插件，建议：

```text
skills/
└── huiyi-bridge/
    ├── SKILL.md
    ├── manifest.yaml
    └── scripts/
        ├── daemon.py
        ├── state.py
        ├── runner.py
        └── parse_scheduler_output.py
```

如果先做轻量原型，也可以先放 workspace automation 目录：

```text
automation/
└── huiyi_bridge/
    ├── daemon.py
    ├── bridge-state.json
    └── README.md
```

### 6.6 MVP 范围建议

第一版建议只做：
- 轮询 schedule
- 调 `scheduler.py`
- 解析结果
- 去重
- 投递一条消息
- 写 state

第一版不要做：
- 自动改 note
- 自动 feedback
- 自动 decay / rebuild
- 复杂多目标路由
- 自己接管消息平台 SDK

### 6.7 风险点

#### 重复提醒
需要 bridge 自己做去重，不要只靠 Hui-Yi 的 cooldown。

#### 输出解析脆弱
如果靠人类可读文本做解析，后期容易碎。最好给 `scheduler.py` 增加 `--json`。

#### 责任污染
记忆策略留在 Hui-Yi，调度和投递放在 Bridge，别混。

#### 静默与打扰控制
最好双层控制：
- schedule 一层
- bridge 一层

### 6.8 最推荐的演进顺序

1. 先给 `scheduler.py` 增加 `--json`
2. 再做 bridge MVP
3. 跑 dry-run 一段时间
4. 最后再接真实投递

---

## 7. Practical recommendation

如果你想让这套系统长期稳定，建议默认这么接：

- 对话回忆 → `review.py resurface` / `search.py`
- 周期维护 → heartbeat + `cool.py` / `rebuild.py`
- 定时候选 → cron + `scheduler.py`
- 自动常驻 → bridge + `scheduler.py`
- 发布前检查 → `smoke_test.py` + `publish-checklist.md`

这样职责最清楚，也最不容易互相打架。
