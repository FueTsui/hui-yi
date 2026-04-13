# OpenClaw Runtime Prototype for Hui-Yi

## 结论先说

这一步已经查到了 OpenClaw 的技能装载/系统 prompt 注入相关入口，确认了两件事：

1. **技能列表与 SKILL.md 注入发生在 OpenClaw 上层 prompt 构建链中**
2. **当前不建议直接修改 `node_modules/openclaw/dist/*.js` 来硬接 Hui-Yi hook**

原因很简单：
- 编译产物文件名带 hash，升级即变
- 改动不可维护
- 很难做可回退、可验证的最小原型

所以当前阶段最合理的最小接入原型是：

> **先做 workspace-side prototype runner，模拟上层在 Hui-Yi skill-hit 后调用 `openclaw_signal_hook.py`。**

---

## 已确认的信息

### 技能 prompt 注入相关文件
- `dist/system-prompt-D1HfWIw9.js`
- `dist/skills-B5qdBn1G.js`
- `dist/skill-scanner-Fgz4c6ro.js`

### 观察到的关键事实
- `system-prompt-*.js` 中包含 `<available_skills>` 注入逻辑
- `skills-*.js` 中包含本地 / bundled / plugin skill 装载与 prompt 格式化逻辑
- 说明 Hui-Yi 的“被命中”发生在上层 agent 的 prompt 决策链中，而不是 skill 自己能直接拦到

---

## 为什么现在不直接 patch OpenClaw runtime

### 不建议直接改 `dist/*.js`
因为这样会带来：
- 版本漂移
- hash 文件名变化
- 难以 merge
- 难以确认 hook 时机是否稳定

### 更合理的做法
先把最小原型收敛成一个独立 runner：
- 不破坏 OpenClaw 主程序
- 可独立验证输入/输出契约
- 未来真正接 runtime 时，只需把同一调用契约接到 skill-hit hook 点

---

## 当前最小原型

新增脚本：
- `scripts/openclaw_runtime_probe.py`

它的职责不是修改 runtime，而是：
- 模拟上层 skill-hit 后的调用
- 调 `openclaw_signal_hook.py`
- 输出 machine-readable 结果
- 明确标记当前仍是 `workspace-prototype`

---

## 原型调用示例

```bash
python skills/hui-yi/scripts/openclaw_runtime_probe.py \
  --query "之前 hui yi 和 openclaw 记忆边界怎么定的" \
  --channel feishu \
  --scope-type user \
  --scope-id ou_cc473c77898e667c521d29abe7bd197a \
  --dry-run
```

---

## 推荐的真实 runtime hook 点

如果后续真的接进 OpenClaw runtime，最推荐的位置是：

> **after Hui-Yi skill selection, before recall/resurface execution**

也就是：
1. 上层 agent 判定当前请求命中 Hui-Yi
2. 构造 channel/chat/thread 对应的稳定 session key
3. 调 `openclaw_signal_hook.py`
4. 再继续正常 recall / answer 流程

---

## 下一步的真正工程任务

如果要从 prototype 进到 runtime integration，建议拆成单独任务：

1. 找到 prompt/skill selection 后的稳定扩展点
2. 评估是否已有 hook / middleware 机制可复用
3. 避免直接改 hash dist 文件，优先找源码层或插件层入口
4. 将 `openclaw_signal_hook.py` 的调用契约接进去

---

## 当前阶段结论

这一步已经完成：
- 上层入口查探
- runtime 风险判断
- 最小接入原型 runner

但**还没有对 OpenClaw runtime 本体做侵入式修改**，这是刻意的，不是没做完。

因为现在最重要的是先把集成契约做稳，而不是把系统主程序改脏。
