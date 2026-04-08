# Hui-Yi README / 使用速查

> **Python 3.10+** required — scripts use `X | Y` union-type syntax.

Hui-Yi 是一个**冷记忆管理 skill**。
它的任务很简单：

**把低频但高价值的信息整理进 `memory/cold/`，并在“当前相关 + 快被遗忘”时再唤起。**

---

## 什么时候用

适合：
- 长期保留经验、决策、背景知识
- 问“之前这个问题怎么处理的”
- 定期冷却 daily notes
- 维护冷记忆质量和 review 节奏

不适合：
- 当天临时事项 → `memory/YYYY-MM-DD.md`
- 高频个人/项目背景 → `MEMORY.md`
- 工具路径、环境坑点 → `TOOLS.md`
- 新错误、新纠正、未验证 lesson → `.learnings/`

一句话：

**近期放 warm，长期低频放 cold。不要把高频词误当高价值记忆。**

---

## 核心思路

Hui-Yi 不按“词”记忆，而按**记忆单元**记忆。

一个记忆单元可以是：
- lesson
- decision
- stable fact
- troubleshooting result
- background context

推荐的回忆逻辑：

```text
Priority ≈
  0.35 * CurrentRelevance
+ 0.25 * ForgettingRisk
+ 0.20 * Importance
+ 0.10 * CrossSessionReuse
+ 0.10 * StateBias
```

也就是优先找这种内容：
- 曾经重要
- 最近变冷
- 当前又重新相关

---

## 关键字段

*已更新：* 近期加入 **Bridge** 模块，提供从 scheduler 到实际投递的桥接层。以下章节包含其使用说明。

一条冷记忆 note 建议至少有：

- `Importance`
- `Memory state`
- `Last seen`
- `Last reviewed`
- `Next review`
- `Review cadence`
- `Confidence`
- `Related tags`

状态含义：
- `hot`：最近强化过，可直接用
- `warm`：适合轻提醒
- `cold`：保留但低优先级
- `dormant`：仅在强触发下唤醒

---

## 最常用命令

### 搜索

```bash
python3 skills/hui-yi/scripts/search.py <keyword>
```

### 重建索引

```bash
python3 skills/hui-yi/scripts/rebuild.py
```

### 看冷却状态

```bash
python3 skills/hui-yi/scripts/cool.py status
python3 skills/hui-yi/scripts/cool.py scan
python3 skills/hui-yi/scripts/cool.py done <reviewed> <archived> <merged>
```

### 看衰减 / review

```bash
python3 skills/hui-yi/scripts/decay.py --dry-run
python3 skills/hui-yi/scripts/review.py due
python3 skills/hui-yi/scripts/review.py resurface --query "当前话题"
python3 skills/hui-yi/scripts/review.py resurface --context-file context.txt
Get-Content context.txt | python3 skills/hui-yi/scripts/review.py resurface --stdin
python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review
```

### 写回反馈

```bash
python3 skills/hui-yi/scripts/review.py feedback <note> --useful yes|no --query "触发它的当前话题"
```

`<note>` 支持精确标题、文件 slug（无扩展名）、或所有词都出现在标题中的关键词组合。

### 批量复习（今日到期，Ebbinghaus 闭环）

```bash
python3 skills/hui-yi/scripts/review.py session
```

逐条展示 TL;DR，输入 `y / n / s / q` 完成反馈，自动更新间隔和状态。

### 新建笔记

```bash
python3 skills/hui-yi/scripts/create.py --title "主题" --type experience --importance high --tags "tag1,tag2"
```

自动设置 `interval_days: 1`、`next_review: tomorrow`，并在创建后运行 `rebuild.py`。

### Schema 校验

```bash
python3 skills/hui-yi/scripts/validate.py            # 检查所有 note
python3 skills/hui-yi/scripts/validate.py --strict   # 警告也报错
```

### 启用定时回忆 scheduler

```bash
cp skills/hui-yi/references/schedule.example.json memory/cold/schedule.json
# 编辑 schedule.json：时区、时间、importance 门槛等
python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review
python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review --preview --query "当前话题"
```

注意：
- `--schedule-id` 的含义是“只运行这条 schedule 的筛选规则”，**不是**“忽略门槛强制预览一个结果”
- `--preview` 才是调试 / 预览模式，会绕过 due、importance、allowed_states、cooldown、require_relevance 等筛选门槛，方便看候选排序

---

## 常见工作流

### 1. 找以前的经验

1. 先看当前对话 / recent memory / `MEMORY.md`
2. 不够再搜 cold memory
3. 如果当前上下文比较长，用：
   - `--query` 传短主题
   - `--context-file` 传文本文件
   - `--stdin` 直接喂上下文
4. 只读最相关的 1-3 条
5. 总结输出，不要整块倒 raw note

### 2. 新增一条冷记忆

1. 判断它 30 天后是否还值钱
2. 查 `index.md` 是否已有同主题 note
3. 没有就用 `_template.md` 建新 note
4. 补齐核心字段
5. 跑 `rebuild.py`

### 3. 定期 cooling

1. `cool.py scan`
2. 从 daily notes 中挑真正值得长期保存的内容
3. 路由到正确位置
4. 更新或新建 cold note
5. 跑 `rebuild.py`
6. `cool.py done ...`

---

## 设计原则

- archive less, but archive better
- recall less, but recall at the right time
- 主动回忆优先用轻提醒，不要直接 dump 老笔记
- `resurface` 现在支持 `query / context-file / stdin` 三种输入
- `scheduler.py` 是自定义定时回忆的最小原型，目前负责“筛选候选”，不是自动发消息守护进程
- scheduler 现在支持低打扰策略：单次上限、全局 cooldown、去重、quiet hours、gentle mode
- 当前仍是轻量 relevance 排序，不是 embedding 级语义召回

---

## 文件说明

- `SKILL.md`：完整规则
- `scripts/common.py`：脚本共享 helper（路径解析、heading/date 解析、tags 读取等）
- `scripts/smoke_test.py`：最小可执行冒烟测试，临时创建隔离的 cold memory 环境后依次跑 create / validate / search / review / decay / cool / scheduler
- `references/cold-memory-schema.md`：schema
- `references/examples.md`：示例
- `references/heartbeat-cooling-playbook.md`：cooling 流程
- `references/integration-patterns.md`：Trigger Modes、heartbeat / cron 对接、scheduler 边界与 preview 用法

### 开发时建议先跑一次

```bash
python3 skills/hui-yi/scripts/smoke_test.py
```

如果你只记 7 条命令，就记这 7 条：

```bash
python3 skills/hui-yi/scripts/create.py --title "主题"          # 新建笔记
python3 skills/hui-yi/scripts/review.py session                   # 今日复习
python3 skills/hui-yi/scripts/search.py <keyword>                 # 搜索
python3 skills/hui-yi/scripts/rebuild.py                          # 重建索引
python3 skills/hui-yi/scripts/cool.py status                      # 查冷却状态
python3 skills/hui-yi/scripts/decay.py --dry-run --rebuild        # 预览衰减
python3 skills/hui-yi/scripts/validate.py                         # 校验 schema
```

## 桥接层 (Bridge)

`skills/hui-yi/bridge/bridge.py` 提供一个轻量的桥接层，将 `scheduler.py` 的候选结果进一步过滤、去重、限流并（可选）投递。

### 主要特性
- **配置路径统一**：默认读取 `skills/hui-yi/bridge/config.example.json`，其中 `statePath`、`outputPath` 已指向 bridge 目录。
- **投递模式**：`logOnly`（默认，仅在返回 JSON 中记录），`stdout`（打印消息），`file`（写入 `deliveries.log`），`message`（占位，后续可接 OpenClaw `message` 工具）。
- **策略**：支持 `maxCandidates`、`minScore`、`preferScheduleIds`、`globalCooldownHours`、`perScheduleCooldownHours`、`maxDeliveriesPerDay`、`quietHours`，并返回 `rejectedCandidates` 与原因。
- **dry‑run / preview**：`--dry-run` 或配置 `dryRun:true` 仅输出结果，不写状态，也不投递。

### 快速运行示例
```bash
# 预览一次调度并查看候选
python3 skills/hui-yi/bridge/bridge.py --dry-run

# 正式投递（假设已配置 delivery mode 为 file）
python3 skills/hui-yi/bridge/bridge.py
```

### 配置示例（已在 `config.example.json` 中）
```json
{
  "enabled": true,
  "memoryRoot": "memory/cold",
  "scheduleConfig": "memory/cold/schedule.json",
  "schedulerScript": "skills/hui-yi/scripts/scheduler.py",
  "statePath": "skills/hui-yi/bridge/bridge-state.json",
  "delivery": {
    "mode": "logOnly",
    "outputPath": "skills/hui-yi/bridge/deliveries.log"
  },
  "deliveryPolicy": {
    "maxCandidates": 3,
    "minScore": 0.45,
    "preferScheduleIds": [],
    "globalCooldownHours": 0,
    "perScheduleCooldownHours": 0,
    "maxDeliveriesPerDay": 0,
    "quietHours": { "enabled": false, "start": "23:00", "end": "08:00" }
  }
}
```

如需在实际投递时使用 OpenClaw 消息工具，请将 `delivery.mode` 改为 `message` 并在后续集成中调用 `message` API。