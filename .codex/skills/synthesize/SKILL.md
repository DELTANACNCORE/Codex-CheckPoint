---
name: synthesize
description: Combine related checkpoints into a knowledge document and review pseudo or duplicate checkpoints. 跨会话聚合相关断点、生成知识文档并清理伪对话或重复断点。
---

# Synthesize Skill / 知识合成 Skill

从多条相关断点笔记中提炼知识文档。

Synthesize a knowledge document from multiple related checkpoint notes.

单独调用 `$synthesize` 不会自行挑选断点，也不会写入项目总结。用户必须明确给出项目名、标签，或明确要求聚类并确认目标范围。选定材料后，脚本才会写入项目总结，并将参与会话和项目总结标记为已知识归档；随后按已记录用户消息数和材料长度判断是否值得提炼 AI开发参考。长会话只提示 Codex 询问用户是否提炼 AI开发参考；短会话明确说明未写入 AI开发参考。无论长度如何，用户可以明确要求强制提炼。

Calling `$synthesize` alone does not select checkpoints or write a project summary. The user must explicitly provide a project, tag, or a confirmed clustering target. Only then does the script write the project summary and mark participating sessions and the summary as knowledge-archived. It then uses recorded user-message count and material length to classify the selection: long sessions only prompt Codex to ask whether an AI development reference should be extracted; short sessions explicitly state that no AI development reference was written. The user can explicitly force extraction regardless of length.

AI开发参考属于用户控制的核心知识，只能在用户明确要求时创建或覆盖。它应服务于资料量大、需要跨新任务复用的公司项目、学习项目或长期研究，而非普通会话摘要。

AI development reference is user-controlled core knowledge. Create or replace it only when the user explicitly requests it. It serves material-rich company, learning, or research work that benefits from reuse across new tasks, not ordinary session summaries.

## 建议请求 / Suggested Prompts

- `把这些断点合成为一篇知识文档` / `Synthesize these checkpoints into one knowledge document`
- `按标签整理最近的 Codex 断点` / `Organize recent Codex checkpoints by tag`
- `按项目 synthesize checkpoint迁到Codex` / `Synthesize checkpoint迁到Codex by project`
- `清理伪对话和重复断点` / `Review pseudo and duplicate checkpoints`

## 执行 / Run

优先直接运行仓库自带脚本。 Run the bundled script directly.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名>
```

标签模式只整理用户明确指定的标签。聚类模式只用于用户明确要求跨会话聚合，并确认这批材料应归入指定项目；缺少确认或项目名时脚本拒绝写入。 Tag mode only processes the tag explicitly named by the user. Cluster mode is reserved for an explicitly requested cross-session aggregation whose target project has been confirmed; the script refuses to write without both confirmation and project name.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --tag <标签>
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cluster --cluster-project <项目名> --confirm-cluster
```

## 断点清理 / Checkpoint Cleanup

`--cleanup-checkpoints` 以断点标题为主，结合 session ID、rollout 是否存在和摘要正文相似度筛选伪对话与重复记录。默认仅输出候选，不会写入项目总结，也不会修改 vault。

`--cleanup-checkpoints` uses checkpoint titles as the primary signal, then checks session IDs, rollout presence, and summary-body similarity for pseudo or duplicate records. It only reports candidates by default: it does not write a project summary or change the vault.

- 标题低信号且没有匹配 rollout 的伪对话会列为删除候选。 Low-signal titles without a matching rollout become deletion candidates.
- 有匹配 rollout 但标题像写入回执、技能调用或原始进度消息的断点会列为重命名候选。 The script suggests a new title for rollout-backed notes whose title looks like a write receipt, skill call, or raw progress message.
- 两条都存在真实 rollout 的相似会话只会报告，不会自动删除。 Similar sessions backed by two real rollouts are reported only and are never automatically deleted.

先运行扫描并审阅结果。 Run the scan and review its output first.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cleanup-checkpoints
```

用户明确确认候选后，才运行执行模式。执行模式会删除高置信候选，重命名可修复标题，并同步每日索引链接。

Run apply mode only after the user explicitly confirms the candidates. It deletes high-confidence candidates, renames repairable titles, and updates daily-index links.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cleanup-checkpoints --apply-cleanup
```

## AI开发参考 / AI Development Reference

用户对长会话明确表示需要提炼，或对短会话明确表示强制提炼时，才使用 AI开发参考模式。此模式仍会先写项目总结和归档；随后评估 verified conclusions、code or configuration、commands、operating methods、validation evidence、pitfalls 六类材料。有效类别少于三类时，必须再次确认用户仍要提炼。

Use AI development reference mode only after the user asks for extraction from a long session or explicitly forces it for a short one. This mode still writes and archives the project summary first, then assesses verified conclusions, code or configuration, commands, operating methods, validation evidence, and pitfalls. When fewer than three categories are present, ask again whether the user still requires the summary.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term
```

获得用户明确授权后才可写入。已有 AI开发参考不会被覆盖；用户明确要求更新现有文件时，额外传入 `--replace-approved`。

Write only after explicit user authorization. Existing AI development references are protected from replacement; add `--replace-approved` only when the user explicitly requests an update.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term --user-approved
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term --user-approved --replace-approved
```

## 输出 / Output

- 读取相关断点。 Reads related checkpoints.
- 更新 `项目总结/<项目名>.md`。只有用户已确认父子归属时才写入父项目目录。 Updates `项目总结/<项目名>.md`. A parent-project directory is used only after the user confirms the relationship.
- AI开发参考写入 `AI开发参考/<项目名>.md`，每个项目仅一篇；项目总结和参与会话均已知识归档。 AI development reference is written to `AI开发参考/<项目名>.md`, one file per project; the project summary and participating sessions are knowledge-archived.
- 返回文档路径、覆盖会话数和主要结论。 Returns the document path, covered-session count, and main conclusions.

## 已验证范围 / Verified Scope

按 skill 调用脚本可以真实合成文档。Codex 桌面端对 `/synthesize` 的原生命令识别尚未稳定验证。

Invoking the script through this skill performs real knowledge synthesis. Stable native `/synthesize` recognition in Codex Desktop is not yet verified.
