---
name: checkpoint
description: Save the current Codex session as an Obsidian recovery brief. 将当前 Codex 会话保存为 Obsidian 恢复断点。
---

# Checkpoint Skill / 会话断点 Skill

将当前 Codex rollout 写入 Obsidian 恢复断点，保留主要结论、已完成工作、当前状态、续接入口、压缩目标和真实知识产出，便于后续任务不读取完整 transcript 即可继续。

Write the current Codex rollout as an Obsidian recovery brief. The note retains main conclusions, completed work, status, continuation entry points, compressed goals, and real knowledge outputs so a later task can continue without loading the full transcript.

## 建议请求 / Suggested Prompts

- `请执行 checkpoint，把当前 Codex 会话写入 Obsidian` / `Run checkpoint and save the current Codex session to Obsidian`
- `把这次对话保存成 Obsidian 断点` / `Save this conversation as an Obsidian checkpoint`
- `/checkpoint`

## 执行 / Run

优先直接运行本地脚本。 Run the local script directly.

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT"
```

指定会话 / Specify a session:

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --session-id <thread-id>
```

保留已有标题，不强制重新综合 / Keep the existing title without forced synthesis:

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --keep-title
```

## 输出 / Output

- 自动定位最新 rollout 或指定 session 的 rollout。 Automatically locates the latest rollout or a rollout for the specified session.
- 调用 `~/.codex/hooks/checkpoint.py`。 Calls `~/.codex/hooks/checkpoint.py`.
- 输出写入状态、目标笔记路径和告警信息。 Prints write status, the target note path, and warnings.

## 已验证范围 / Verified Scope

已验证 `checkpoint.py`、Stop hook 和手动脚本链路。Codex 桌面端对 `/checkpoint` 的原生命令识别尚未稳定验证，可靠方式是按 skill 调用本地脚本。

`checkpoint.py`, the Stop hook, and the manual script path are verified. Stable native `/checkpoint` recognition in Codex Desktop is not yet verified; invoking the local script through this skill remains the reliable path.
