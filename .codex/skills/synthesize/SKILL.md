---
name: synthesize
description: |
  跨会话聚合相关断点、生成知识文档并清理伪对话或重复断点。
  Combine related checkpoints into a knowledge document and review pseudo or duplicate checkpoints.
---

# Synthesize Skill
*知识合成 Skill*

从多条相关断点笔记中提炼知识文档。

Synthesize a knowledge document from multiple related checkpoint notes.

单独调用 `$synthesize` 不会自行挑选断点，也不会写入项目总结。用户必须明确给出项目名、标签，或明确要求聚类并确认目标范围。选定材料后，脚本才会写入项目总结，并将参与会话和项目总结标记为已知识归档；随后按已记录用户消息数和材料长度判断是否值得提炼 AI开发参考。长会话只提示 Codex 询问用户是否提炼 AI开发参考；短会话明确说明未写入 AI开发参考。无论长度如何，用户可以明确要求强制提炼。

Calling `$synthesize` alone does not select checkpoints or write a project summary. The user must explicitly provide a project, tag, or a confirmed clustering target. Only then does the script write the project summary and mark participating sessions and the summary as knowledge-archived. It then uses recorded user-message count and material length to classify the selection: long sessions only prompt Codex to ask whether an AI development reference should be extracted; short sessions explicitly state that no AI development reference was written. The user can explicitly force extraction regardless of length.

用户要求查找可合并会话时，先运行候选扫描并展示候选编号、涉及会话、共同依据和建议项目。候选扫描只读取未归档会话，不会修改 vault。收到明确同意与目标项目名后，才可执行归档。

When the user asks to find mergeable sessions, run the candidate scan first and present the candidate ID, source sessions, shared evidence, and suggested project. Candidate scanning reads only unarchived sessions and never changes the vault. Archive only after explicit approval and a target project name.

AI开发参考属于用户控制的核心知识，只能在用户明确要求时创建或覆盖。它应服务于资料量大、需要跨新任务复用的公司项目、学习项目或长期研究，而非普通会话摘要。

AI development reference is user-controlled core knowledge. Create or replace it only when the user explicitly requests it. It serves material-rich company, learning, or research work that benefits from reuse across new tasks, not ordinary session summaries.

项目总结和经授权写入的 AI开发参考会补全 `aliases` 与 `keywords`，用于后续精确检索。既有人工 metadata 保持原值；自动 hook 不会借此创建或覆盖 AI开发参考。

Project summaries and user-authorized AI development references enrich `aliases` and `keywords` for later precise retrieval. Existing manual metadata remains unchanged; automatic hooks never use this enrichment to create or replace an AI development reference.

## 建议请求
*Suggested Prompts*

- `把这些断点合成为一篇知识文档`\
  `Synthesize these checkpoints into one knowledge document`
- `按标签整理最近的 Codex 断点`\
  `Organize recent Codex checkpoints by tag`
- `按项目 synthesize checkpoint迁到Codex`\
  `Synthesize checkpoint迁到Codex by project`
- `检查哪些会话可以合并归档`\
  `Review sessions that can be merged after confirmation`
- `审计知识库结构和失效链接`\
  `Audit vault structure and broken links`
- `查找可以添加的跨文档链接`\
  `Review cross-document link proposals`
- `检查哪些项目总结需要人工整理或刷新`\
  `Review project summaries that may need manual synthesis or refresh`
- `查找可以安全修复的断裂链接`\
  `Review safe broken-link repair proposals`
- `清理伪对话和重复断点`\
  `Review pseudo and duplicate checkpoints`

## 执行
*Run*

优先直接运行仓库自带脚本。\
Run the bundled script directly.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名>
```

标签模式只整理用户明确指定的标签。聚类模式只用于用户明确要求跨会话聚合，并确认这批材料应归入指定项目；缺少确认或项目名时脚本拒绝写入。\
Tag mode only processes the tag explicitly named by the user. Cluster mode is reserved for an explicitly requested cross-session aggregation whose target project has been confirmed; the script refuses to write without both confirmation and project name.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --tag <标签>
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cluster --cluster-project <项目名> --confirm-cluster
```

## 知识库审计
*Vault Audit*

`--audit` 只读检查空 Markdown、断点 frontmatter、重复 session、缺少 rollout、归档目标、项目总结、wikilink、验证时效、metadata 回填候选、知识整理建议和高区分度材料簇。审计不会写入报告、项目总结、断点或索引。

`--audit` read-checks empty Markdown, checkpoint frontmatter, duplicate sessions, missing rollouts, archive targets, project summaries, wikilinks, verification freshness, metadata-backfill proposals, knowledge-organization suggestions, and high-distinction material clusters. It never writes a report, project summary, checkpoint, or index.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --audit --stale-days 30
```

审计列出的 metadata 候选只能由用户逐条或按明确 session 范围确认。先展示候选、session ID 和拟写入字段，再获得明确同意；已有人工 `aliases` 或 `keywords` 保持原值。重复 session ID 必须先用断点清理处理。

Metadata proposals from an audit require item-level or explicitly scoped session confirmation. Show the proposal, session ID, and fields first, then obtain explicit approval; existing manual `aliases` or `keywords` remain unchanged. Duplicate session IDs must be handled through checkpoint cleanup first.

候选证据优先采用 frontmatter 的 `tags` 与 `keywords`，再采用 aliases、完整标题和英文技术词。代码块、URL、路径、session 标识和宽泛工作流词不会作为候选依据。高区分度材料簇需要至少三条未归档断点共有同一 metadata 信号，只提示人工审阅，不会选择会话、添加链接、合并文档或授权归档。

Candidate evidence prioritizes frontmatter `tags` and `keywords`, then aliases, full titles, and English technical terms. Code blocks, URLs, paths, session identifiers, and broad workflow words do not support candidates. A high-distinction material cluster requires one shared metadata signal across at least three unarchived checkpoints; it only prompts review and never selects sessions, adds links, merges documents, or authorizes archival.

知识整理建议只依据断点中已写入的明确项目字段，提示尚未归档会话或可能需要刷新项目总结的材料。建议不会推断父项目，不会选择会话，也不会构成归档授权；实际归档仍需用户明确指定项目或确认合并候选。

Knowledge-organization suggestions use only explicit project fields already stored in checkpoints. They surface unarchived material or project summaries that may need refresh. A suggestion never infers a parent project, selects sessions, or authorizes archival; actual archival still needs a user-specified project or a confirmed merge proposal.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --audit --apply-metadata --metadata-sessions <session-id> --confirm-metadata
```

## 跨文档链接
*Cross-document Links*

`--link-candidates` 只根据项目、aliases、keywords、tags 与可用标题生成高置信候选。共同项目仍需至少一个具体特征；没有共同项目时需要至少三个具体特征。正文路径、写入回执和宽泛工作流词不会参与关联。

`--link-candidates` generates high-confidence proposals from projects, aliases, keywords, tags, and usable titles only. A shared project still needs one concrete feature; without one, three concrete features are required. Body paths, write receipts, and broad workflow terms do not participate.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --link-candidates
```

扫描后先展示候选编号、两篇文档和共同依据。用户明确确认后，才在两篇文档各自的 `## 相关资料` 区加入一个 root-relative wikilink；现有正文和人工链接保持不变。

After scanning, show the candidate ID, both documents, and the shared evidence. Only explicit user approval adds one root-relative wikilink to each document's `## 相关资料` section; existing body text and manual links remain unchanged.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --link-candidate <候选编号> --confirm-link
```

## 断裂链接修复
*Broken-link Repair*

`--repair-link-candidates` 只处理当前无法解析的 wikilink。替代目标必须在 aliases、标题或文件名上唯一匹配；相近的多个候选会被拒绝，正文词重叠不会参与替换判断。

`--repair-link-candidates` considers only currently unresolved wikilinks. A replacement must uniquely match an alias, title, or filename; close competing candidates are rejected, and body-word overlap does not influence replacement selection.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --repair-link-candidates
```

扫描输出来源文档、原始链接、替代目标和匹配依据。用户明确确认后，脚本仅在来源文档中替换该断裂链接，保留原有显示别名和章节锚点。

The scan prints the source document, original link, replacement target, and matching evidence. After explicit approval, the script replaces only that broken link in the source document while preserving its display alias and heading anchor.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --repair-link-candidate <候选编号> --confirm-link-repair
```

## 合并候选
*Merge Proposals*

`--merge-candidates` 只扫描未知识归档、标题可用的会话断点。候选需要共同项目加一个具体特征，或至少三个非泛化特征；`checkpoint`、`Codex`、`hook`、`知识库`、`Docker`、`运维` 等宽泛词不能单独形成候选。扫描结果不能作为归档授权。

`--merge-candidates` scans only unarchived checkpoint notes with usable titles. A proposal requires a shared project plus one concrete signal, or at least three non-generic signals; broad terms such as `checkpoint`, `Codex`, `hook`, `知识库`, `Docker`, and `运维` cannot create a proposal alone. Scan output is never archive authorization.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --merge-candidates
```

扫描结束后，Codex 必须向用户展示候选，并询问：`是否将候选 <候选编号> 归档到 项目总结/<项目名>.md？` 只有用户明确同意后，才使用候选编号和目标项目执行归档。

After scanning, Codex must show the proposal and ask: `是否将候选 <候选编号> 归档到 项目总结/<项目名>.md？` Only an explicit user approval permits archival with the candidate ID and target project.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --merge-candidate <候选编号> --merge-project <项目名> --confirm-merge
```

用户明确指定 session ID 与项目名时，可跳过候选扫描。该路径仍要求 `--confirm-merge`，并且仅归档指定的 session；重复 session ID、已归档 session 或父项目路径会被拒绝。

When the user explicitly supplies session IDs and a project name, candidate scanning can be skipped. This path still requires `--confirm-merge` and archives only the specified sessions; duplicate session IDs, archived sessions, and parent-project paths are rejected.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --merge-sessions <session-id-1> <session-id-2> --merge-project <项目名> --confirm-merge
```

合并归档默认只写入独立项目文件 `项目总结/<项目名>.md`。用户要求归入父项目时，必须先询问：`该项目是否归属于‘<父项目>’？` 得到明确确认后才可使用已有的父项目归档规则。

Merge archival writes only the independent project file `项目总结/<项目名>.md` by default. When the user requests a parent project, first ask: `该项目是否归属于‘<父项目>’？` Use the existing parent-project archiving rules only after explicit confirmation.

## 断点清理
*Checkpoint Cleanup*

`--cleanup-checkpoints` 以断点标题为主，结合 session ID、rollout 是否存在和摘要正文相似度筛选伪对话与重复记录。默认仅输出候选，不会写入项目总结，也不会修改 vault。

`--cleanup-checkpoints` uses checkpoint titles as the primary signal, then checks session IDs, rollout presence, and summary-body similarity for pseudo or duplicate records. It only reports candidates by default: it does not write a project summary or change the vault.

- 标题低信号且没有匹配 rollout 的伪对话会列为删除候选。\
  Low-signal titles without a matching rollout become deletion candidates.
- 有匹配 rollout 但标题像写入回执、技能调用或原始进度消息的断点会列为重命名候选。\
  The script suggests a new title for rollout-backed notes whose title looks like a write receipt, skill call, or raw progress message.
- 两条都存在真实 rollout 的相似会话只会报告，不会自动删除。\
  Similar sessions backed by two real rollouts are reported only and are never automatically deleted.

先运行扫描并审阅结果。\
Run the scan and review its output first.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cleanup-checkpoints
```

用户明确确认候选后，才运行执行模式。执行模式会删除高置信候选，重命名可修复标题，并同步每日索引链接。\
Run apply mode only after the user explicitly confirms the candidates. It deletes high-confidence candidates, renames repairable titles, and updates daily-index links.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --cleanup-checkpoints --apply-cleanup
```

## 验证时效
*Verification Freshness*

用户提出测试、验证、检查、诊断、排查或复测时，历史断点和项目总结只能提供线索。Codex 必须在当前环境重新执行对应命令或检查；当前结果与历史结论冲突时，以当前结果为准。

When the user asks to test, verify, check, diagnose, troubleshoot, or retest, historical checkpoints and project summaries provide leads only. Codex must re-run the relevant command or inspection in the current environment; current results prevail over conflicting historical conclusions.

可调用 `$verify` 查看这一执行边界。\
Use `$verify` to apply this execution boundary.

## AI开发参考
*AI Development Reference*

用户对长会话明确表示需要提炼，或对短会话明确表示强制提炼时，才使用 AI开发参考模式。此模式仍会先写项目总结和归档；随后评估 verified conclusions、code or configuration、commands、operating methods、validation evidence、pitfalls 六类材料。有效类别少于三类时，必须再次确认用户仍要提炼。

Use AI development reference mode only after the user asks for extraction from a long session or explicitly forces it for a short one. This mode still writes and archives the project summary first, then assesses verified conclusions, code or configuration, commands, operating methods, validation evidence, and pitfalls. When fewer than three categories are present, ask again whether the user still requires the summary.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term
```

获得用户明确授权后才可写入。已有 AI开发参考不会被覆盖；用户明确要求更新现有文件时，额外传入 `--replace-approved`。\
Write only after explicit user authorization. Existing AI development references are protected from replacement; add `--replace-approved` only when the user explicitly requests an update.

```bash
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term --user-approved
python3 ~/.codex/skills/synthesize/synthesize.py --vault-root "$OBSIDIAN_VAULT" --project <项目名> --long-term --user-approved --replace-approved
```

## 输出
*Output*

- 读取相关断点。\
  Reads related checkpoints.
- 更新 `项目总结/<项目名>.md`。只有用户已确认父子归属时才写入父项目目录。\
  Updates `项目总结/<项目名>.md`. A parent-project directory is used only after the user confirms the relationship.
- AI开发参考写入 `AI开发参考/<项目名>.md`，每个项目仅一篇；项目总结和参与会话均已知识归档。\
  AI development reference is written to `AI开发参考/<项目名>.md`, one file per project; the project summary and participating sessions are knowledge-archived.
- 返回文档路径、覆盖会话数和主要结论。\
  Returns the document path, covered-session count, and main conclusions.

## 已验证范围
*Verified Scope*

按 skill 调用脚本可以真实合成文档。Codex 桌面端对 `/synthesize` 的原生命令识别尚未稳定验证。

Invoking the script through this skill performs real knowledge synthesis. Stable native `/synthesize` recognition in Codex Desktop is not yet verified.
