---
name: synthesize
description: 跨会话知识合成，将同类断点聚合成知识文档。
---

# Synthesize Skill

从多条相关断点笔记中提炼知识文档。

## Suggested prompts

- `把这些断点合成为一篇知识文档`
- `按标签整理最近的 Codex 断点`
- `按项目 synthesize checkpoint迁到Codex`

## Run

优先直接运行仓库自带脚本：

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名>
```

也支持：

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --tag <标签>
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cluster
```

## Output

脚本会：

- 读取相关断点
- 在 `项目总结/<项目>/` 下生成知识文档
- 返回文档路径、覆盖会话数和主要结论

## Reality check

当前可验证的是“按技能调用脚本”这条路径可以真实合成文档。

当前没有证据表明 Codex 桌面端会把 `/synthesize` 稳定识别成原生命令。
