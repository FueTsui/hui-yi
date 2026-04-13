# OpenClaw Integration Design for Hui-Yi Session Signals

> 文档类型：架构设计稿，用于说明推荐接法与边界，不是唯一实现真相。
> 如实现与本文不一致，以当前 `SKILL.md`、`README.md` 和实际代码行为为准。

这份设计稿定义：

> **Hui-Yi 的 `signal_pipeline.py` 应该如何接入 OpenClaw 上层 agent / skill 命中路径，才能把真实聊天流转成 repetition-first 的冷记忆强化信号。**

---

## 1. 目标

前面已经完成的能力：
- `signal_detect.py`：detect real-session candidates
- `signal_apply.py`：write weak / strong activation back
- `signal_pipeline.py`：detect + threshold + optional apply
- `review.py feedback --session-key`：useful recall → strong activation
- `review.py resurface --write-signals`：high-confidence recall → weak activation

现在缺的不是底层能力，而是：

> **上层 OpenClaw agent 在什么时机、用什么字段、按什么边界调用 `signal_pipeline.py`。**

---

## 2. 核心原则

### 2.1 不全量吞所有聊天
Hui-Yi 不是全局聊天日志分析器。

不要做：
- 每条消息都跑 `signal_pipeline.py`
- 所有频道都无差别打 repetition
- 对普通闲聊做冷记忆强化

### 2.2 只在“命中 Hui-Yi 语义”的时候接入
最稳的接法是：

1. 上层 agent 先判断本轮是否命中 Hui-Yi
2. 只有命中时，才调用 `signal_pipeline.py`

也就是：

**skill 命中 → 才累积弱激活**

而不是：

**任意聊天 → 都去扫冷记忆**

### 2.3 弱激活与强激活分层
- 命中 Hui-Yi / recall 候选出现 → `weak activation`
- recall 被证明 useful → `strong activation`

这样不会因为系统自己捞了一次 note，就把它吹成强记忆。

### 2.4 避让 OpenClaw 主记忆
如果当前内容明显属于：
- 高频稳定事实
- 当前对话上下文
- 当天流水
- 工具/环境信息

应优先留在 OpenClaw 系统记忆，不要进 Hui-Yi 强化链。

---

## 3. 最推荐的接入点

### 推荐接法：Skill-hit Hook

也就是在上层 agent **已经判断当前请求命中 Hui-Yi skill 之后**，追加一次轻量调用：

```text
User message
  → skill selection
    → Hui-Yi matched
      → call signal_pipeline.py (weak activation)
      → continue normal recall / resurface / answer flow
```

这是当前最合适的接法，因为：
- 噪音最低
- 边界最清楚
- 最符合 Hui-Yi 的“低频高价值”定位

---

## 4. 不推荐的接入点

### 4.1 全局消息入口
不要在所有入站消息一进来就调用 `signal_pipeline.py`。

问题：
- 成本高
- 噪音多
- 会把普通聊天也刷进 repetition
- 会和 OpenClaw 主记忆职责打架

### 4.2 Heartbeat 批量回扫所有对话
不建议把 heartbeat 当主入口。

heartbeat 更适合：
- maintenance
- cooling
- rebuild / validate

不适合做高频真实会话强化主入口。

### 4.3 scheduler / decay 内偷偷调用
不推荐。

原因：
- scheduler 是 selector
- decay 是 maintenance helper
- 都不该偷偷篡改 session signals 主轨迹

---

## 5. session_key 规范

上层接入必须生成稳定的 `session_key`。

推荐格式：

```text
<channel>:<scope>:<id>:<thread-or-main>
```

### Feishu 私聊
```text
feishu:user:ou_xxx:main
```

### Feishu 群主流
```text
feishu:chat:oc_xxx:main
```

### Feishu 话题线程
```text
feishu:chat:oc_xxx:thread:omt_xxx
```

### 一般规则
- 能区分频道 / 平台
- 能区分 chat_id
- 能区分 thread 与 main stream
- 保持稳定，不要每条消息都变

### 不建议
不要把 message_id 当 session_key。

那会把每条消息都变成新 session，直接毁掉 cross-session 语义。

---

## 6. 上层调用条件

建议只有满足以下条件之一时才触发 `signal_pipeline.py`：

### 条件 A. Hui-Yi skill 被显式命中
例如用户说：
- 之前怎么处理来着
- 有记录吗
- 你记得吗
- 帮我回忆一下
- archive this / cool this down

### 条件 B. 当前回答明确依赖旧上下文
即使用户没说“记得吗”，但 agent 已判断：
- 需要旧经验、旧决策、旧排障结果
- 需要 historical continuity

### 条件 C. recall 之后用户继续沿旧主题追问
这说明旧 note 真的被再次激活了，不只是一次偶然命中。

---

## 7. 上层不应调用的条件

### 不调用场景
- 纯寒暄
- 普通事实问答
- 单次工具命令执行
- 高频主记忆类话题
- 当前消息与冷记忆几乎无关

一句话：

**只有“旧记忆确实可能参与了当前对话”时，才值得调用 pipeline。**

---

## 8. 最小调用协议

推荐上层传入：

### 必需参数
- `--query` 或 `--context-file`
- `--session-key`
- `--apply`

### 推荐参数
- `--min-relevance 0.30`
- `--min-confidence medium`
- `--limit 3`
- `--json`

示例：

```bash
python skills/hui-yi/scripts/signal_pipeline.py \
  --query "hui yi 的 decay 和 openclaw 记忆边界" \
  --session-key "feishu:user:ou_cc473c77898e667c521d29abe7bd197a:main" \
  --apply \
  --limit 3 \
  --min-relevance 0.30 \
  --min-confidence medium \
  --json
```

---

## 9. 上层接入后的标准流程

### 流程 1. 用户消息命中 Hui-Yi
1. 用户发来消息
2. 上层 agent 命中 Hui-Yi
3. 构造 `session_key`
4. 调 `signal_pipeline.py --apply`
5. 得到候选 / applied 结果
6. 继续正常 recall / resurface / answer

### 流程 2. recall 后确认 useful
1. `review.py feedback --useful yes --session-key ...`
2. 调 `signal_apply.py`
3. 将弱激活升级为强激活轨迹的一部分

这会形成：
- skill hit → weak activation
- useful recall → strong activation

---

## 10. 与 OpenClaw 系统记忆的避让策略

上层在调用前应先做一次轻量判断：

### 如果内容明显属于以下之一，则不要触发 Hui-Yi pipeline
- `MEMORY.md` 高频稳定事实
- `memory/YYYY-MM-DD.md` 当天流水
- `TOOLS.md` 工具/环境信息
- `.learnings/` 尚未验证的新教训

### 只有以下内容值得进入 Hui-Yi pipeline
- 低频但高价值
- 需要历史连续性
- 被再次提及的旧经验 / 旧决策 / 排障结果 / 背景知识

---

## 11. 去重与节流建议

### 11.1 单轮消息不要重复调多次
同一用户消息命中 Hui-Yi 后，只调用一次 pipeline 即可。

### 11.2 同一 session 内保守写弱激活
即使多轮都命中，也应依赖 `signal_apply.py` 的 dedup 机制，不要额外手动叠加多次。

### 11.3 bridge / automation 层不要重复补写
如果将来 bridge 也会做 pipeline 调用，要避免：
- 主对话层已经写一次
- bridge 又写一次

否则 repetition 会被刷高。

---

## 12. 最推荐的第一版上层实现

如果是在 OpenClaw agent 层接入，我建议第一版只做：

### Hook 时机
- **选中 Hui-Yi skill 后**
- **真正开始执行 cold-memory recall 之前**

### Hook 动作
调用：
- `signal_pipeline.py --apply --json`

### Hook 用途
- 只是累积 weak activation
- 不改变主回答逻辑
- 不自动追加别的用户可见输出

也就是：

> 它是记忆强化副作用，不是主流程替代者。

---

## 13. 后续演进方向

### Phase A
先接 Hui-Yi skill hit hook

### Phase B
再接 recall 后 useful feedback 自动强化

### Phase C
如果确认稳定，再考虑：
- 将更丰富的上下文摘要传入 `--context-file`
- 在 bridge / automation 场景中复用 pipeline

### 不建议太早做
- 全局所有消息自动跑 pipeline
- transcript 全量回扫
- 用 heartbeat 当主强化入口

---

## 14. 最终建议

最稳的接法只有一句话：

> **让 OpenClaw 在“命中 Hui-Yi skill”的真实对话场景里，轻量调用 `signal_pipeline.py`，写入 weak activation；而 strong activation 只来自 useful recall。**

这样可以同时满足：
- repetition-first
- 低噪音
- 不和系统主记忆打架
- 易于逐步上线

---

## 15. 推荐下一步

如果继续落地，最值得做的是：

1. 把这份设计的摘要写进 `README.md` / `SKILL.md`
2. 如果 OpenClaw 上层允许，增加一个最小 hook：
   - Hui-Yi skill hit → `signal_pipeline.py --apply`
3. 先在 dry-run 或 log-only 模式观察一段时间
4. 再决定是否扩大接入范围
