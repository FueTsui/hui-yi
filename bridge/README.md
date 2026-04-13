# Hui-Yi Bridge

Bridge 是 Hui-Yi 的轻量桥接层，用来把 `scheduler.py` 选出的候选进一步做策略筛选、去重、限流和可选投递。

## 它负责什么

Bridge 负责：
- 调用 `scheduler.py --json`
- 汇总候选
- 应用 `deliveryPolicy`
- 记录运行状态
- 按配置决定是仅记录、打印、写文件，还是接消息投递

Bridge 不负责：
- 修改 cold-memory note
- 替代 `rebuild.py`、`review.py`、`cool.py`
- 充当完整的长期守护进程

## 目录与配置

关键文件：
- `bridge.py`：命令行入口
- `config.example.json`：示例配置
- `bridge-state.json`：bridge 自身状态

默认情况下：
- 当前仓库根目录运行时，会优先兼容本仓库路径
- 安装到 `skills/hui-yi/` 后运行时，会优先兼容安装路径

## 快速试跑

当前仓库根目录：

```bash
python bridge/bridge.py --dry-run
```

安装模式，从 workspace 根目录：

```bash
python skills/hui-yi/bridge/bridge.py --dry-run
```

## 当前行为

- 调用 scheduler 获取 machine-readable candidates
- 支持单 schedule 或 sweep 所有启用 schedule
- 对候选按 score / relevance / forgettingRisk / importance / state 排序
- 应用 `maxCandidates`、`minScore`、冷却、quiet hours 等策略
- 输出最终选中项和被拒绝项

输出里常见字段：
- `scheduleRuns`
- `candidateCount`
- `selectedCandidate`
- `topCandidates`
- `rejectedCandidates`
- `deliveryResult`

## 支持的 delivery mode

- `logOnly`：只记录结果，不外发
- `stdout`：打印 message
- `file`：写入本地日志
- `message`：通过 adapter 执行投递，当前默认支持 `command` 适配器

### delivery adapter

当前 bridge 不再内置写死平台/用户的 demo 发送逻辑，而是要求显式配置 adapter。

当前支持：
- `adapter.type = command`
- `adapter.command`：自定义命令模板

可用占位符：
- `{message}`
- `{title}`
- `{path}`
- `{channel}`
- `{target}`
- `{schedule_id}`

这样 bridge 的职责更清楚：
- bridge 负责选候选、做策略和触发 adapter
- adapter 负责真正投递
- 平台绑定不再硬编码在 bridge 里

## 常见策略字段

`deliveryPolicy` 支持：
- `maxCandidates`
- `minScore`
- `preferScheduleIds`
- `globalCooldownHours`
- `perScheduleCooldownHours`
- `maxDeliveriesPerDay`
- `quietHours`

常见拒绝原因：
- `duplicate`
- `below_policy_threshold`
- `schedule_deprioritized`
- `quiet_hours`
- `global_cooldown`
- `schedule_cooldown`
- `daily_limit`

## 建议的调试顺序

1. 先单独跑 `scheduler.py --preview`
2. 再跑 `bridge.py --dry-run`
3. 最后才接真实 delivery mode

如果 `bridge` 没有产出结果，优先检查：
- `schedule.json` 是否存在并启用对应 schedule
- `memory/cold/tags.json` 是否有候选 note
- `deliveryPolicy` 是否过严
- 当前时间是否命中 quiet hours 或 cooldown
