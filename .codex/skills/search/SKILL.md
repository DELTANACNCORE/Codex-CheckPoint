---
name: search
description: Search the vault for project documents and Codex session checkpoints. 按关键词搜索 vault 中的项目文档和 Codex 会话断点。
---

# Search Skill / 知识库搜索 Skill

按关键词快速检索整个 Obsidian vault。`Codex工作记录/` 保存 Codex 会话断点和索引，`项目总结/` 保存项目材料，`长期经验总结/` 保存可复用结论。

Search the complete Obsidian vault by keyword. `Codex工作记录/` stores Codex checkpoints and indexes, `项目总结/` stores project material, and `长期经验总结/` stores reusable conclusions.

## 建议请求 / Suggested Prompts

- `搜索知识库里的参考文献` / `Search the knowledge base for references`
- `在 Codex工作记录里查找 checkpoint` / `Find checkpoint in Codex工作记录`
- `查找校园旧物出售系统的部署记录` / `Find deployment records for the campus marketplace`
- `/search checkpoint hook`

## 执行 / Run

优先直接运行仓库自带脚本。 Run the bundled script directly.

```bash
python3 ~/.codex/skills/search/search.py --vault-root "$OBSIDIAN_VAULT" <关键词1> [关键词2] [关键词3]
```

没有设置 `OBSIDIAN_VAULT` 时，默认使用 `~/obsidian/知识库`。

When `OBSIDIAN_VAULT` is unset, the default vault is `~/obsidian/知识库`.

## 输出 / Output

- 归档文档命中。 Archived-document matches.
- 断点笔记命中。 Checkpoint-note matches.
- 每条结果的简短摘要或状态。 A short summary or status for each result.

## 已验证范围 / Verified Scope

按 skill 调用脚本的路径可完成真实搜索。Codex 桌面端对 `/search` 的原生命令识别尚未稳定验证。

Invoking the script through this skill performs real searches. Stable native `/search` recognition in Codex Desktop is not yet verified.
