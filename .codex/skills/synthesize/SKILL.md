---
name: synthesize
description: Combine related checkpoints into a knowledge document. 跨会话聚合相关断点并生成知识文档。
---

# Synthesize Skill / 知识合成 Skill

从多条相关断点笔记中提炼知识文档。

Synthesize a knowledge document from multiple related checkpoint notes.

长期经验总结属于用户控制的核心知识，只能在用户明确要求时创建或覆盖。它应服务于资料量大、需要跨新任务复用的公司项目、学习项目或长期研究，而非普通会话摘要。

Long-term experience is user-controlled core knowledge. Create or replace it only when the user explicitly requests it. It serves material-rich company, learning, or research work that benefits from reuse across new tasks, not ordinary session summaries.

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

## 长期经验总结 / Long-term Experience

用户明确要求“提炼长期经验”时，先运行质量评估，不会写入文件。先评估 verified conclusions、code or configuration、commands、operating methods、validation evidence、pitfalls 六类材料；有效类别少于三类时，必须询问用户是否仍要求提炼。

When the user explicitly requests a long-term experience summary, run the quality assessment first. It does not write a file. Assess verified conclusions, code or configuration, commands, operating methods, validation evidence, and pitfalls. When fewer than three categories are present, ask whether the user still requires the summary.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term
```

获得用户明确授权后才可写入。已有长期经验不会被覆盖；用户明确要求更新现有文件时，额外传入 `--replace-approved`。

Write only after explicit user authorization. Existing long-term experience is protected from replacement; add `--replace-approved` only when the user explicitly requests an update.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term --user-approved
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term --user-approved --replace-approved
```

## 输出 / Output

- 读取相关断点。 Reads related checkpoints.
- 更新 `项目总结/<项目名>.md`。只有用户已确认父子归属时才写入父项目目录。 Updates `项目总结/<项目名>.md`. A parent-project directory is used only after the user confirms the relationship.
- 长期经验写入 `长期经验总结/<项目名>.md`，每个项目仅一篇，不改写会话归档状态。 Long-term experience is written to `长期经验总结/<项目名>.md`, one file per project, without changing session archive status.
- 返回文档路径、覆盖会话数和主要结论。 Returns the document path, covered-session count, and main conclusions.

## 已验证范围 / Verified Scope

按 skill 调用脚本可以真实合成文档。Codex 桌面端对 `/synthesize` 的原生命令识别尚未稳定验证。

Invoking the script through this skill performs real knowledge synthesis. Stable native `/synthesize` recognition in Codex Desktop is not yet verified.
