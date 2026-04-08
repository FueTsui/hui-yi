# Hui-Yi Bridge MVP

最小原型桥接层，用来把 Hui-Yi 的 `scheduler.py --json` 接到一个可定时运行的轻量桥接器上。

## 目标

Bridge 只负责：
- 调度运行 `scheduler.py --json`
- 解析候选
- 去重 / 限流 / dry-run
- 保存 bridge 自己的状态

Bridge 不负责：
- 修改 cold-memory note
- 直接接管外部平台 SDK
- 替代 Hui-Yi 的 recall / cooling / rebuild 逻辑

## 文件

- `bridge.py`：命令行入口
- `config.example.json`：最小配置示例
- `bridge-state.json`：运行状态文件（首次运行自动创建）

## 快速试跑

```bash
python skills/hui-yi/bridge/bridge.py \
  --config skills/hui-yi/bridge/config.example.json \
  --dry-run
```

## 当前行为

- 调用 `skills/hui-yi/scripts/scheduler.py --json`
- 支持单 schedule 或从 `schedule.json` 自动 sweep 启用的 schedules
- 汇总所有 schedule 的候选
- 默认取第一条 candidate（如果有）
- 基于 `bridge-state.json` 做最小去重
- dry-run 时只打印结果，不发消息

输出里会包含：
- `scheduleRuns`：每条 schedule 的候选数
- `candidateCount`：汇总候选数
- `selectedCandidate`：dry-run 下被选中的候选详情
- `selectionPolicy`：当前排序与投递策略
- `rejectedCandidates`：被 policy 拒绝的候选及原因

## 当前 delivery policy

支持：
- `maxCandidates`
- `minScore`
- `preferScheduleIds`
- `globalCooldownHours`
- `perScheduleCooldownHours`
- `maxDeliveriesPerDay`
- `quietHours`

当前拒绝原因包括：
- `duplicate`
- `below_policy_threshold`
- `schedule_deprioritized`
- `quiet_hours`
- `global_cooldown`
- `schedule_cooldown`
- `daily_limit`

## 当前 delivery adapter

支持：
- `logOnly`：只在结果里记录，不落地外发
- `stdout`：直接打印 message 到 stdout
- `file`：把投递记录追加写入本地日志文件
- `message`：仅保留接口占位，当前原型不直接调用 OpenClaw 消息工具

说明：
- 为了避免本地原型偷偷对外发消息，`message` 模式当前只返回 `not_implemented`
- 真正接 OpenClaw `message` 工具，建议放到正式插件或 agent-integrated 版本里做

## 后续建议

- 把 `message` adapter 接到正式 OpenClaw 消息层
- 补按 channel / user 的 quiet-hours 差异化策略
- 补更完整的 delivery history，而不只是 lastDelivered 映射