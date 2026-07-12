---
name: checkpoint
description: Save current Codex session checkpoint to Obsidian when Codex chooses this skill.
---

# Checkpoint Skill

Write the current Codex rollout as an Obsidian recovery brief. The note retains the main assistant conclusions, completed work, current status, continuation entry point, compressed goals, and actual knowledge outputs so a later task can resume without loading the full transcript.

## Suggested prompts

- `请执行 checkpoint，把当前 Codex 会话写入 Obsidian`
- `把这次对话保存成 Obsidian 断点`
- `/checkpoint`

## Run

优先直接运行本地脚本：

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT"
```

如果要指定会话：

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --session-id <thread-id>
```

如果要保留现有标题，不强制重新综合：

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --keep-title
```

## Output

脚本会：

- 自动定位最新 rollout 或指定 session 的 rollout
- 调用 `~/.codex/hooks/checkpoint.py`
- 输出写入状态、目标笔记路径和告警信息

## Reality check

当前仓库已经验证 `checkpoint.py`、`Stop` hook 和这个手动脚本链路可用。

当前没有证据表明 Codex 桌面端会把 `/checkpoint` 稳定识别成原生命令。可靠方式仍然是按 skill 调脚本。
