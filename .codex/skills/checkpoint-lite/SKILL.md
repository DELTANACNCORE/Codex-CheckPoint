---
name: checkpoint
description: Save the current Codex session to Obsidian in Lite mode. 以 Lite 模式将当前 Codex 会话保存到 Obsidian。
---

# Checkpoint Skill Lite / 轻量会话断点 Skill

由调用时提供主题、标签和关键词，再将当前对话写入断点。

Provide the topic, tags, and keywords at invocation time, then write the current conversation as a checkpoint.

## 建议请求 / Suggested Prompts

- `用 Lite checkpoint 保存当前对话` / `Save the current conversation with Lite checkpoint`
- `把这次对话按 Lite 模式写入 Obsidian` / `Write this conversation to Obsidian in Lite mode`
- `/checkpoint`

## 执行 / Run

先从当前对话整理元数据。 First derive metadata from the current conversation.

- 主题：不超过 20 个汉字。 Topic: no more than 20 Chinese characters or an equally concise title.
- 大类：1 到 2 个。 Categories: 1 to 2 broad categories.
- 标签：2 到 4 个。 Tags: 2 to 4 specific tags.
- 关键词：1 到 3 个。 Keywords: 1 to 3 search terms.

```bash
python3 ~/.codex/skills/checkpoint/checkpoint_lite.py \
  --vault-root "$OBSIDIAN_VAULT" \
  --topic "主题 / Topic" \
  --category "大类1,大类2" \
  --tags "标签1,标签2" \
  --keywords "关键词1,关键词2"
```

## 输出 / Output

- 自动定位最新 rollout 或指定 session 的 rollout。 Automatically locates the latest or specified session rollout.
- 用传入元数据调用 `~/.codex/hooks/checkpoint.py`。 Calls `~/.codex/hooks/checkpoint.py` with supplied metadata.
- 输出写入状态、目标笔记路径和告警信息。 Prints write status, the target note path, and warnings.

## 已验证范围 / Verified Scope

Lite 适合手动控制标题和标签且不启用自动 hook 的场景。Codex 桌面端对 `/checkpoint` 的原生命令识别尚未稳定验证，可靠方式是按 skill 调用本地脚本。

Lite suits workflows that require manual title and tag control without automatic hooks. Stable native `/checkpoint` recognition in Codex Desktop is not yet verified; invoking the local script through this skill remains the reliable path.
