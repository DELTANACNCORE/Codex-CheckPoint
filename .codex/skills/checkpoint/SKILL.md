---
name: checkpoint
description: Refresh the current Codex session checkpoint in Obsidian. 刷新当前 Codex 会话的 Obsidian 断点。
---

# Checkpoint / 会话断点

手动刷新当前 Codex 会话断点。自动模式由 Stop hook 在会话结束时执行；此 skill 用于立即更新或修正断点。

Refresh the current Codex session checkpoint manually. The Stop hook runs automatically at the end of a session; use this skill to update a checkpoint immediately.

## 执行 / Run

```bash
python3 ~/.codex/hooks/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --force
```

`--force` 会重新写入当前会话断点。脚本自动定位最新 Codex rollout，并从线程标题和会话内容提取恢复信息。

`--force` rewrites the current session checkpoint. The script locates the latest Codex rollout and extracts recovery information from the thread title and session content.
