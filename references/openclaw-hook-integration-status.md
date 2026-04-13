# Hui-Yi OpenClaw Hook Integration Status

> 文档类型：阶段性状态记录，不是长期规范文档。
> 当前有效规范请优先看 `SKILL.md`、`README.md` 和相关 references 中的规范类文档。

## 当前结论

已经找到 OpenClaw 的稳定扩展点：

- **workspace hooks**
- 事件类型优先选择：`message:preprocessed`

这意味着 Hui-Yi 的最小上层接入原型，不需要 patch OpenClaw runtime，也不需要改 hash 命名的 `dist/*.js`。

---

## 已落地内容

### Workspace hook
路径：
- `hooks/hui-yi-signal-hook/HOOK.md`
- `hooks/hui-yi-signal-hook/handler.ts`

### Hook 行为
- 监听 `message:preprocessed`
- 对 message body 做保守 Hui-Yi 意图判断
- 命中时调用 `skills/hui-yi/scripts/openclaw_signal_hook.py`
- 当前默认 `--dry-run`
- 不向用户主动发消息，只写日志

---

## 为什么选 `message:preprocessed`

比 `message:received` 更好，因为它已经经过：
- 媒体理解
- 链接理解
- 文本预处理

也就是说，传给 Hui-Yi 的 query 更接近 agent 真正看到的文本。

---

## 当前配置状态

已在 `C:\Users\fuetsui\.openclaw\openclaw.json` 中加入：

```json
{
  "hooks": {
    "internal": {
      "enabled": true,
      "entries": {
        "hui-yi-signal-hook": {
          "enabled": true
        }
      }
    }
  }
}
```

---

## 仍需注意

OpenClaw hooks 在文档中要求：
- 启用后需要 **重启 gateway** 才会重新加载

所以当前状态是：
- hook 文件已存在
- config 已启用
- **是否真正开始执行，取决于 gateway 是否已重启/重载 hooks**

---

## 当前阶段性质

这是一个真正的上层最小接入原型，但仍然是保守模式：
- dry-run
- 不改用户可见行为
- 不自动写 strong activation
- 不碰主回答链

---

## 下一步

1. 重启 gateway 让 hook 生效
2. 用一条明显 Hui-Yi 意图的消息验证日志
3. 如果稳定，再把 hook 从 `--dry-run` 升级到真实 weak activation
