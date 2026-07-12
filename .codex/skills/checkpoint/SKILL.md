---
name: checkpoint
description: Save the current Codex session as an Obsidian recovery brief. 将当前 Codex 会话保存为 Obsidian 恢复断点。
---

# Checkpoint Skill / 会话断点 Skill

将当前 Codex rollout 写入 Obsidian 恢复断点，保留主要结论、已完成工作、当前状态、续接入口、压缩目标和真实知识产出，便于后续任务不读取完整 transcript 即可继续。默认调用会依据最新助手结论重新生成当前断点标题，然后读取全部已保存断点并统一归类。

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

保留已有标题，不重新生成标题 / Keep the existing title without refreshing it:

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --keep-title
```

## 输出 / Output

- 自动定位最新 rollout 或指定 session 的 rollout。 Automatically locates the latest rollout or a rollout for the specified session.
- 调用 `~/.codex/hooks/checkpoint.py`。 Calls `~/.codex/hooks/checkpoint.py`.
- 自动 hook 首次创建断点时写入 `Codex工作记录/会话断点/` 顶层；已有断点保持原位置更新，不会分类或移动历史文件。 Automatic hooks create new checkpoints at the top level, preserve an existing note's location on updates, and never classify or move history.
- 默认调用会重新生成当前断点标题，并扫描全部断点的 rollout 后统一归类；缺失 rollout 的旧断点依据其已有摘要归类。 Default calls refresh the current title, then scan every saved checkpoint rollout and classify all notes; older notes without a rollout use their existing recovery brief.
- `--keep-title` 仅保留当前断点标题，仍会执行全量分类。 `--keep-title` preserves only the current title and still runs the full classification pass.
- 只通过本 skill 的包装脚本执行手动 checkpoint，不直接调用 hook。包装脚本会验证 `--vault-root` 是包含 `.obsidian` 的真实 vault；hook 事件缺少匹配 rollout 时会跳过，绝不回退读取其他会话。 Run manual checkpoint only through this skill wrapper, not the hook directly. The wrapper verifies that `--vault-root` is a real vault containing `.obsidian`; hook events without a matching rollout are skipped and never fall back to another session.
- 输出写入状态、目标笔记路径和告警信息。 Prints write status, the target note path, and warnings.

## 已验证范围 / Verified Scope

已验证 `checkpoint.py`、Stop hook 和手动脚本链路。Codex 桌面端对 `/checkpoint` 的原生命令识别尚未稳定验证，可靠方式是按 skill 调用本地脚本。

`checkpoint.py`, the Stop hook, and the manual script path are verified. Stable native `/checkpoint` recognition in Codex Desktop is not yet verified; invoking the local script through this skill remains the reliable path.
