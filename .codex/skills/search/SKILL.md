---
name: search
description: 搜索知识库，按关键词查找整个 vault 中的项目文档和 Codex 会话断点。
---

# Search Skill

按关键词快速检索整个 Obsidian vault。`Codex工作记录/` 保存 Codex 会话断点和索引，`项目总结/` 保存项目材料，`长期经验总结/` 保存可复用结论。

## Suggested prompts

- `搜索知识库里的参考文献`
- `在 Codex工作记录里查找 checkpoint`
- `查找校园旧物出售系统的部署记录`
- `/search checkpoint hook`

## Run

优先直接运行仓库自带脚本：

```bash
python3 ~/.codex/skills/search/search.py --vault-root "$OBSIDIAN_VAULT" <关键词1> [关键词2] [关键词3]
```

如果环境里没有 `OBSIDIAN_VAULT`，默认会使用 `~/obsidian/知识库`。

## Output

脚本会输出：

- 归档文档命中
- 断点笔记命中
- 每条结果的简短摘要或状态

## Reality check

当前可验证的是“按技能调用脚本”这条路径可实现真实搜索。

当前没有证据表明 Codex 桌面端会把 `/search` 稳定识别成原生命令。
