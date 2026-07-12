---
name: synthesize
description: Combine related checkpoints into a knowledge document. 跨会话聚合相关断点并生成知识文档。
---

# Synthesize Skill / 知识合成 Skill

从多条相关断点笔记中提炼知识文档。

Synthesize a knowledge document from multiple related checkpoint notes.

## 建议请求 / Suggested Prompts

- `把这些断点合成为一篇知识文档` / `Synthesize these checkpoints into one knowledge document`
- `按标签整理最近的 Codex 断点` / `Organize recent Codex checkpoints by tag`
- `按项目 synthesize checkpoint迁到Codex` / `Synthesize checkpoint迁到Codex by project`

## 执行 / Run

优先直接运行仓库自带脚本。 Run the bundled script directly.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名>
```

也支持按标签或聚类执行。 Tag and cluster modes are also available.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --tag <标签>
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cluster
```

## 输出 / Output

- 读取相关断点。 Reads related checkpoints.
- 更新 `项目总结/<项目名>.md`。只有用户已确认父子归属时才写入父项目目录。 Updates `项目总结/<项目名>.md`. A parent-project directory is used only after the user confirms the relationship.
- 返回文档路径、覆盖会话数和主要结论。 Returns the document path, covered-session count, and main conclusions.

## 已验证范围 / Verified Scope

按 skill 调用脚本可以真实合成文档。Codex 桌面端对 `/synthesize` 的原生命令识别尚未稳定验证。

Invoking the script through this skill performs real knowledge synthesis. Stable native `/synthesize` recognition in Codex Desktop is not yet verified.
