# Hui-Yi Publish Checklist

在发布 / 打包 / 提交 ClawHub 前，至少过一遍这张表。

## 1. 脚本可运行

- [ ] `python3 skills/hui-yi/scripts/smoke_test.py`
- [ ] `python3 skills/hui-yi/scripts/validate.py --memory-root memory/cold --strict`
- [ ] 如果改了 scheduler，额外跑：
  - [ ] `python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review --memory-root memory/cold`
  - [ ] `python3 skills/hui-yi/scripts/scheduler.py --schedule-id daily-evening-review --memory-root memory/cold --preview --query "test preview"`

## 2. 文档和实现一致

- [ ] `README.md` 中的命令都存在
- [ ] `SKILL.md` 中列出的脚本与实际文件一致
- [ ] 新增参数（例如 `--preview`）已同步到 README / SKILL
- [ ] `CHANGELOG.md` 已记录本次对外可见变更

## 3. 包内容完整

- [ ] `manifest.yaml` 与实际脚本一致
- [ ] `references/` 中示例和 schema 没过期
- [ ] `_meta.json` / 发布元数据版本号如有需要已更新
- [ ] 发布包中不包含 `__pycache__/`、`.pyc`、临时测试文件

## 4. 回归关注点

重点检查这些最容易回归的地方：

- [ ] 空字段 `-` 不会被误解析成下一个 heading
- [ ] `review.py feedback` 支持 slug / title / 关键词匹配
- [ ] `review.py resurface` 对高相关 query 不会误筛掉结果
- [ ] `scheduler.py --schedule-id` 与 `--preview` 语义清晰，不混淆
- [ ] Windows 下编码 fallback 仍正常

## 5. 发布前最后一眼

- [ ] 没有临时调试输出
- [ ] 没有把本地测试数据误带进 skill 包
- [ ] 文档里没有还在说旧行为
- [ ] 版本说明足够让下一个人看懂这次改了什么
