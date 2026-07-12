---
name: checkpoint
description: Save current Codex session checkpoint to Obsidian in Lite mode.
---

# Checkpoint Skill Lite

由调用时提供主题、标签和关键词，再将当前对话写入断点。

## Suggested prompts

- `用 Lite checkpoint 保存当前对话`
- `把这次对话按 Lite 模式写入 Obsidian`
- `/checkpoint`

## Run

先基于当前对话综合出这些元数据：

- 主题：不超过 20 个汉字
- 大类：1-2 个
- 标签：2-4 个
- 关键词：1-3 个

然后执行：

```bash
python3 ~/.codex/skills/checkpoint/checkpoint_lite.py \
  --vault-root "$OBSIDIAN_VAULT" \
  --topic "主题" \
  --category "大类1,大类2" \
  --tags "标签1,标签2" \
  --keywords "关键词1,关键词2"
```

## Output

脚本会：

- 自动定位最新 rollout 或指定 session 的 rollout
- 用传入元数据调用 `~/.codex/hooks/checkpoint.py`
- 输出写入状态、目标笔记路径和告警信息

## Reality check

Lite 适合希望手动控制标题和标签、且不启用自动 hook 的场景。

当前没有证据表明 Codex 桌面端会把 `/checkpoint` 稳定识别成原生命令。可靠方式仍然是按 skill 调脚本。
