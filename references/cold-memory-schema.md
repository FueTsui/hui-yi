# Cold Memory Schema Reference

用在：创建或修改 cold note、`index.md`、`tags.json`、`retrieval-log.md`。

目标只有两个：
1. note 对人类可读
2. metadata 对检索和回忆调度有用

不要围着高频词打转，核心单位是 **memory unit**。

---

## Note 最小模板

```markdown
# [Topic title]

## TL;DR
- 这条 note 是什么
- 什么时候有用
- 关键结论

## Memory type
- fact | experience | background

## Importance
- high | medium | low

## Semantic context
1-2 句自然语言说明：这条 note 在什么任务里有帮助，为什么有帮助。

## Triggers
- 触发词或短语

## Use this when
- 具体使用场景

## Memory state
- hot | warm | cold | dormant

## Review cadence
- interval_days: 7
- review_count: 0
- review_success: 0
- review_fail: 0

## Last seen
- YYYY-MM-DD

## Last reviewed
- YYYY-MM-DD

## Next review
- YYYY-MM-DD

## Confidence
- high | medium | low

## Last verified
- YYYY-MM-DD

## Related tags
- tag1
- tag2

## Details
可选，只有真的需要长背景时再写。
```

---

## 字段说明

必需字段：
- Topic title
- TL;DR
- Memory type
- Importance
- Semantic context
- Triggers
- Use this when
- Memory state
- Confidence
- Last verified
- Related tags

推荐字段：
- Review cadence
- Last seen
- Last reviewed
- Next review

简化理解：
- `Importance`：历史价值
- `Memory state`：当前温度
- `Review cadence`：复习节奏
- `Confidence`：可靠程度

---

## 状态建议

```text
hot      最近强化过，能直接用
warm     适合轻提醒
cold     保留但低优先级
dormant  除非强触发，否则别主动拿出来
```

---

## 默认 review ladder

```text
创建
+1d
+3d
+7d
+14d
+30d
```

之后：
- helpful recall → 间隔拉长
- unhelpful recall → 间隔缩短或继续冷却

---

## index.md 格式

```markdown
# Cold Memory Index

- `note-file.md` — 一句话总结
  - type: fact | experience | background
  - importance: high | medium | low
  - state: hot | warm | cold | dormant
  - tags: ...
  - triggers: ...
  - read when: ...
  - confidence: high | medium | low
  - updated: YYYY-MM-DD
  - next review: YYYY-MM-DD | none
```

要求：
- 一条 note 一个 block
- 按最近更新时间排序

---

## tags.json 格式

```json
{
  "_meta": {
    "description": "Structured metadata for cold-memory retrieval",
    "version": 4,
    "updated": "YYYY-MM-DD"
  },
  "notes": [
    {
      "title": "...",
      "path": "memory/cold/xxx.md",
      "type": "fact|experience|background",
      "importance": "high|medium|low",
      "state": "hot|warm|cold|dormant",
      "summary": "...",
      "semantic_context": "...",
      "tags": ["..."],
      "triggers": ["..."],
      "scenarios": ["..."],
      "confidence": "high|medium|low",
      "last_seen": "YYYY-MM-DD or null",
      "last_reviewed": "YYYY-MM-DD or null",
      "next_review": "YYYY-MM-DD or null",
      "review": {
        "interval_days": 7,
        "review_count": 0,
        "review_success": 0,
        "review_fail": 0
      },
      "last_verified": "YYYY-MM-DD",
      "updated": "YYYY-MM-DD"
    }
  ]
}
```

---

## retrieval-log.md 格式

```markdown
# Retrieval Log

| Date | Query | Matched | Useful | Action |
|---|---|---|---|---|
| 2026-04-07 | heartbeat startup | daily-memory-auto-create-hardening.md | yes | reinforced note |
```

只记录 cold memory retrieval，不记录 warm / MEMORY.md 查询。

---

## 维护规则

- note 文件是 source of truth
- `index.md` 和 `tags.json` 要同步
- 漂移了就 rebuild
- 不要手工编造过度精确的 review 数据
- 小而准，比大而乱更重要

一句话：

**schema 是为了更准地回忆，不是为了把系统写得像论文。**