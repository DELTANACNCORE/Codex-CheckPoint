---
name: checkpoint
description: >-
  Save the current Codex session as an Obsidian recovery brief.
  将当前 Codex 会话保存为 Obsidian 恢复断点。
---

# Checkpoint Skill
*会话断点 Skill*

将当前 Codex rollout 写入 Obsidian 恢复断点，保留整段会话中的主要结论、已完成工作、当前状态、续接入口、目标演进和真实知识产出，便于后续任务不读取完整 transcript 即可继续。默认调用会优先保留可用的 Codex 会话标题和用户在 Obsidian 中改过的标题，只修复自动生成的机械标题，再读取全部已保存断点并统一归类。

Write the current Codex rollout as an Obsidian recovery brief. The note retains cross-stage conclusions, completed work, current state, continuation entry points, goal evolution, and real knowledge outputs so a later task can continue without loading the full transcript. A usable Codex thread title and titles changed in Obsidian are preserved; only mechanical automatic titles are repaired.

## 建议请求
*Suggested Prompts*

- `请执行 checkpoint，把当前 Codex 会话写入 Obsidian`\
  `Run checkpoint and save the current Codex session to Obsidian`
- `把这次对话保存成 Obsidian 断点`\
  `Save this conversation as an Obsidian checkpoint`
- `/checkpoint`

## 执行
*Run*

优先直接运行本地脚本。\
Run the local script directly.

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT"
```

指定会话：\
Specify a session:

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --session-id <thread-id>
```

保留已有标题，不进行标题检查：\
Keep the existing title without checking it:

```bash
python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root "$OBSIDIAN_VAULT" --keep-title
```

## 输出
*Output*

- 自动定位最新 rollout 或指定 session 的 rollout。\
  Automatically locates the latest rollout or a rollout for the specified session.
- 调用 `~/.codex/hooks/checkpoint.py`。\
  Calls `~/.codex/hooks/checkpoint.py`.
- 自动 hook 首次创建断点时写入 `Codex工作记录/会话断点/未分类对话/`；已有断点保持原位置更新，不会自动分类或移动历史文件。\
  Automatic hooks create new checkpoints in `Codex工作记录/会话断点/未分类对话/`, preserve an existing note location on updates, and never classify or move history automatically.
- 自动 Stop hook 成功写入会话断点后，会向用户提示最终 vault 相对文件路径和所在目录；未分类对话文件夹中的断点会额外提示调用 `$checkpoint` 进行归类。仅写入每日索引或跳过写入时不会提示。\
  After an automatic Stop hook successfully writes a session checkpoint, the user receives its final vault-relative file path and parent directory. A note in the unclassified directory also directs the user to `$checkpoint` for classification. Index-only and skipped writes produce no notice.
- 默认调用会检查当前断点标题，优先使用可用的 Codex 会话标题；只有自动生成的回执、长问句或其他机械标题才会改名。`title_baseline` 用于识别用户在 Obsidian 中做过的改名，用户标题不会被自动覆盖。随后只扫描 `未分类对话` 与当前手动调用的会话；已分类历史不会被重扫，当前会话再次 `$checkpoint` 时才允许重新归类。\
  Default calls inspect the current title and prefer a usable Codex thread title; only automatic receipts, long question titles, and other mechanical titles are renamed. It then scans only `未分类对话` and the current manually invoked session; categorized history is not rescanned, while a current session can be reclassified when `$checkpoint` runs again.
- `--keep-title` 完全保留当前断点标题，仍会执行全量分类。\
  `--keep-title` preserves the current title completely and still runs the full classification pass.
- 只通过本 skill 的包装脚本执行手动 checkpoint，不直接调用 hook。包装脚本会验证 `--vault-root` 是包含 `.obsidian` 的真实 vault；hook 事件缺少匹配 rollout 时会跳过，绝不回退读取其他会话。\
  Run manual checkpoint only through this skill wrapper, not the hook directly. The wrapper verifies that `--vault-root` is a real vault containing `.obsidian`; hook events without a matching rollout are skipped and never fall back to another session.
- 完成回复必须逐行给出最终断点文件与所在目录，使用分类后的 vault 相对路径，例如 `Codex工作记录/会话断点/系统与运维/检查 Docker 服务.md` 和 `Codex工作记录/会话断点/系统与运维/`。不得只写文件名、链接别名或分类前路径。脚本输出同时保留绝对路径，供后续归档识别。\
  The completion reply must state the final checkpoint file and its parent directory on separate lines using the classified vault-relative paths, for example `Codex工作记录/会话断点/系统与运维/检查 Docker 服务.md` and `Codex工作记录/会话断点/系统与运维/`. Never report only a filename, link alias, or the pre-classification path. Script output also retains the absolute path for downstream archive detection.

## 已验证范围
*Verified Scope*

已验证 `checkpoint.py`、Stop hook 和手动脚本链路。Codex 桌面端对 `/checkpoint` 的原生命令识别尚未稳定验证，可靠方式是按 skill 调用本地脚本。

`checkpoint.py`, the Stop hook, and the manual script path are verified. Stable native `/checkpoint` recognition in Codex Desktop is not yet verified; invoking the local script through this skill remains the reliable path.
