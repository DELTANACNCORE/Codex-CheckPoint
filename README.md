# Codex CheckPoint V0.9.0
*Codex 会话断点 V0.9.0*

为 Codex 与 Obsidian 提供会话断点、持续恢复、项目总结和知识检索。仓库只包含运行时 hook、skills、README、许可证和忽略规则，不包含安装、迁移、打包或解包脚本。

Session checkpoints, continuous recovery, project summaries, and knowledge retrieval for Codex and Obsidian. This repository contains only runtime hooks, skills, the README, license, and ignore rules. It does not include installation, migration, packing, or unpacking scripts.

## 上游与署名
*Upstream and Attribution*

本项目基于 [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint)，原始作者为 [hjm4839-coder](https://github.com/hjm4839-coder)。本仓库保留原始 MIT 许可证和 Git 历史，并改造成仅支持 Codex 的实现。

This project is based on [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint) by [hjm4839-coder](https://github.com/hjm4839-coder). It retains the original MIT license and Git history while adapting the workflow exclusively for Codex.

## 功能
*Features*

- 自动断点：新会话写入 `Codex工作记录/会话断点/未分类对话/`，已有断点后续保持原位置更新。标题优先采用可用的 Codex 会话标题，再回退到跨阶段的助手结论；`title_baseline` 会保护用户在 Obsidian 中改过的标题。自动 hook 不会触发分类或移动历史文件；手动 checkpoint 只修复自动生成的回执、长问句和依赖上下文的机械标题，只整理未分类对话和当前重新检查的会话。Stop hook 成功写入后会提示最终断点文件和目录；未分类断点会提示调用 `$checkpoint` 归类，索引记录或跳过写入时保持静默。\
  Automatic checkpoints create new notes in `Codex工作记录/会话断点/未分类对话/` and preserve existing note locations on later updates. Titles prefer a usable Codex thread title, then fall back to cross-stage assistant conclusions; `title_baseline` protects titles changed in Obsidian. Automatic hooks never classify or move history. Manual checkpoint repairs only automatic receipts, long questions, and context-dependent mechanical titles, then organizes only unclassified notes and the current rechecked session. After a successful Stop-hook write, the user receives the final checkpoint file and directory; an unclassified note directs the user to `$checkpoint` for classification, while index-only and skipped writes stay silent.
- Stop Hook 提速：自动 Stop 在断点和每日索引写入后立即返回，项目总结和知识库首页由受锁保护的后台子进程刷新。手动 checkpoint 保持同步，以保证分类和最终位置回执。\
  Stop-hook acceleration: automatic Stop returns after the checkpoint and daily index are written, then refreshes project summaries and the vault homepage in a lock-protected background process. Manual checkpoint remains synchronous so classification and final-location receipts stay reliable.
- 会话隔离：hook 事件只有在 session 与 rollout 一一匹配且 vault 根目录包含 `.obsidian` 时才允许写入；缺少匹配 rollout 的内部或环境会话会直接跳过，绝不借用最近的其他会话。\
  Session isolation: hook events write only when their session matches a rollout and the vault root contains `.obsidian`; internal or ambient events without a matching rollout are skipped and never borrow another session.
- 断点清理：`synthesize --cleanup-checkpoints` 会先以标题为主扫描伪对话、重复副本和机械标题。默认只报告；`--apply-cleanup` 仅在用户确认后删除无 rollout 的高置信候选、修复可推导的标题，并同步每日索引。两条真实会话即使相似也只报告。\
  Checkpoint cleanup: `synthesize --cleanup-checkpoints` first scans for pseudo conversations, duplicate copies, and mechanical titles with title-first matching. It only reports by default; after user confirmation, `--apply-cleanup` removes high-confidence candidates without rollouts, repairs derivable titles, and synchronizes daily indexes. Similar rollout-backed sessions are reported only.
- 跨日索引：同日会话首行使用真实对话开始时间，第二行显示 session 更新；跨日会话在首日和更新日均以 session 更新时间为首行，第二行标注原始对话时间。\
  Cross-day indexes show the real conversation start time and session update on the same day. For cross-day sessions, both the first and update day use the session update time first and label the original conversation time below.
- 持续更新：有效对话达到阈值后，在新用户消息时刷新断点。\
  Continuous updates: a checkpoint is refreshed when a new user message arrives after the meaningful-round threshold.
- 恢复注入：新任务可读取相关断点、项目总结和 AI开发参考的短摘要。AI开发参考要求直接项目名或别名命中，或至少两个独立特征词命中；Docker、运维等宽泛主题词不会单独触发，界面引用标注也不会参与匹配。复用时，Codex 会先向用户说明文档来源。\
  Recovery injection: new tasks can receive compact context from relevant checkpoints, project summaries, and AI development references. References require a direct project or alias match, or at least two independent identity terms; broad Docker or operations terms alone do not trigger reuse, and UI response annotations do not participate in matching. Codex announces the source before reuse.
- 项目总结：独立项目固定写入 `项目总结/<项目名>.md`，同一会话涉及多个独立项目时合并为一篇并记录 `session_ids`。自动归属只接受仍存在、项目名一致且已记录当前 session 的单项目总结；历史写入、已删除文件和旧合并总结不会产生新项目关系。父项目目录需要用户明确确认归属关系。\
  Project summaries: independent projects use `项目总结/<项目名>.md`; multiple independent projects in one session are merged into one note with `session_ids`. Automatic ownership accepts only an existing single-project summary whose name and current session match; historical writes, deleted files, and older merged summaries cannot create project relationships. Parent-project directories require explicit user confirmation.
- AI开发参考：每次 `synthesize` 都会归档项目总结，并按会话长度提示是否值得提炼 AI开发参考。只有用户明确授权或强制要求时才写入 `AI开发参考/<项目名>.md`；有效材料类别不足三类时必须再次询问。自动 hook 不会创建、覆盖或删除 AI开发参考。旧 `长期经验总结/` 目录只提供读取兼容。\
  AI development reference: every `synthesize` run archives the project summary and uses session length to recommend extraction. `AI开发参考/<项目名>.md` is written only with explicit user authorization or a forced request; fewer than three useful material categories requires another user decision. Automatic hooks never create, replace, or delete AI development references. The former `长期经验总结/` directory remains read-compatible only.
- 敏感信息脱敏：自动生成的断点、每日索引、项目总结、首页与 AI开发参考会替换常见 Bearer Token、API Key、访问令牌、密码、JWT、`sk-` 密钥、Cookie 和私钥内容。普通项目 Markdown 不会被扫描或改写。\
  Sensitive-information redaction: generated checkpoints, daily indexes, project summaries, the homepage, and AI development references replace common Bearer tokens, API keys, access tokens, passwords, JWTs, `sk-` keys, cookies, and private keys. Ordinary project Markdown files are neither scanned nor rewritten.
- 搜索与合成：保留本地 `search` 与 `synthesize` skills；合成必须指定项目或标签。聚类合成额外要求用户确认范围和目标项目名，未确认的聚类不能写入知识库。\
  Search and synthesis: local `search` and `synthesize` skills remain available. Synthesis requires an explicit project or tag. Cluster synthesis also requires a user-confirmed scope and target project name; an unconfirmed cluster cannot write to the vault.
- 用户确认合并：`synthesize --merge-candidates` 只读取未归档断点并报告高置信候选。候选需要共同项目加具体特征，或至少三个非泛化特征；用户确认候选编号和目标项目后，才可归档到一个独立项目总结。用户也可直接指定 session ID 与目标项目。\
  User-confirmed merge: `synthesize --merge-candidates` reads only unarchived checkpoints and reports high-confidence proposals. A proposal needs a shared project plus a concrete signal, or at least three non-generic signals; archival to one independent project summary requires a user-approved proposal ID and target project. Users can also directly specify session IDs and a target project.
- 知识库维护：`synthesize --audit` 只读检查空 Markdown、frontmatter、重复 session、缺少 rollout、归档目标、wikilink、项目总结、验证时效、metadata 候选与知识整理建议。metadata 回填、双向链接和断裂链接修复都要求指定候选并获得用户确认；自动 hook 不运行这些维护操作。\
  Vault maintenance: `synthesize --audit` read-checks empty Markdown, frontmatter, duplicate sessions, missing rollouts, archive targets, wikilinks, project summaries, verification freshness, metadata proposals, and knowledge-organization suggestions. Metadata backfill, reciprocal links, and broken-link repair all require a specified proposal and user confirmation; automatic hooks never run these maintenance actions.
- 增量搜索索引：`search` 使用 vault 专属的 SQLite 缓存增量索引 Markdown，保持 aliases、keywords、tags、标题和正文的原有排序，并在索引不可用时回退直接扫描。显式 `--semantic` 使用固定版本的本地 `multilingual-e5-small`，按标题和段落分块召回；默认检索不会下载模型或改变现有排序。\
  Incremental search index: `search` uses a vault-specific SQLite cache to incrementally index Markdown while preserving aliases, keywords, tags, title, and body ranking; it falls back to direct scanning when the index is unavailable. Explicit `--semantic` uses a pinned local `multilingual-e5-small` model with title-aware paragraph chunks; default retrieval never downloads a model or changes the existing ordering.
- 验证时效：用户提出测试、验证、检查、诊断、排查或复测时，恢复注入会要求重新执行当前环境中的相关命令，历史“已验证”内容仅作为线索。\
  Verification freshness: when users ask to test, verify, check, diagnose, troubleshoot, or retest, recovery injection requires relevant commands to be re-run in the current environment; historical “verified” content is only a lead.
- PreTool 提醒：写入项目文档前提示已有相关材料。\
  PreTool reminder: project-document writes are checked against existing material.

## V0.9.0
*Version 0.9.0*

- 确认式会话合并：`synthesize --merge-candidates` 仅报告未归档断点的高置信关联。写入同一份平面项目总结前，用户必须确认候选编号和目标项目；直接指定 session 也需要确认参数。\
  Confirmed session merging: `synthesize --merge-candidates` only reports high-confidence relationships among unarchived checkpoints. Writing one flat project summary requires the user to confirm the proposal ID and target project; direct session selection also requires confirmation.
- 知识库维护：新增只读 `--audit`、metadata 回填候选、跨文档链接候选和断裂链接修复候选。每一类写入都需要展示证据并取得用户对指定候选的确认，自动 hook 不执行维护操作。\
  Vault maintenance: added read-only `--audit`, metadata-backfill proposals, cross-document link proposals, and broken-link repair proposals. Every write presents evidence and requires approval for the specified proposal; automatic hooks never perform maintenance.
- 本地检索：新增 vault 专属 SQLite 增量索引，以及显式、离线的 `--semantic` 段落级语义召回。默认词法检索的排序和网络边界保持不变，模型不可用时回退词法检索。\
  Local retrieval: added a vault-specific incremental SQLite index and explicit offline, paragraph-level `--semantic` recall. Default lexical ranking and network boundaries remain unchanged, and unavailable models fall back to lexical retrieval.
- 验证时效：新增 `$verify`，测试、检查、诊断和复测任务会将历史知识作为线索，并以当前环境重新执行的结果为准。\
  Verification freshness: added `$verify`; testing, checking, diagnosis, and retesting use historical knowledge as leads and rely on commands re-run in the current environment.

## V0.8.1
*Version 0.8.1*

- 后台维护：仅迁入 Stop Hook 的核心提速能力。后台任务会串行刷新项目总结和知识库首页，并记录启动、完成或失败；启动失败时自动回退到同步维护。\
  Background maintenance: only the core Stop-hook acceleration is included. Background work serially refreshes project summaries and the vault homepage and records scheduling, completion, or failure; a spawn failure falls back to synchronous maintenance.
- 写入边界：没有引入上游的自动健康检查、60 分钟节流或自动 AI开发参考写入。`--audit` 仅由用户手动调用且默认只读；AI开发参考仍仅由获得用户明确授权的 `$synthesize` 写入。\
  Write boundaries: this release does not add the upstream automatic health check, 60-minute throttle, or automatic AI development reference writes. `--audit` is manual and read-only by default; AI development references remain writable only through explicitly authorized `$synthesize`.

## V0.8.0
*Version 0.8.0*

- metadata 兼容与补全：新断点、项目总结和经用户授权写入的 AI开发参考现支持 JSON 数组、逗号分隔值与 YAML 列表形式的 `aliases` 和 `keywords`。人工 metadata 会被保留，生成值会过滤用户目录、临时目录与 `worktrees` 等路径噪声。\
  Metadata compatibility and enrichment: new checkpoints, project summaries, and user-authorized AI development references support JSON arrays, comma-separated values, and YAML lists for `aliases` and `keywords`. Manual metadata is preserved, while generated values filter user directories, temporary directories, `worktrees`, and other path noise.
- 精确检索：`search` 依次按 `aliases`、`keywords`、`tags`、标题或正文排序，并保留旧 Markdown 的正文兼容检索。新任务的恢复匹配也会使用 aliases。\
  Precise retrieval: `search` ranks `aliases`, `keywords`, `tags`, then title or body matches and retains body fallback for older Markdown. New-task recovery matching also uses aliases.
- 授权边界保持不变：metadata 补全不会触发 AI开发参考的创建、替换、删除或授权。该文件仍只由用户明确授权的 `$synthesize` 写入。\
  Authorization boundary unchanged: metadata enrichment never creates, replaces, deletes, or authorizes an AI development reference. Such files remain writable only through explicitly authorized `$synthesize`.

## V0.7.0
*Version 0.7.0*

- AI开发参考：将面向跨任务复用的用户控制知识统一命名为 `AI开发参考/<项目名>.md`。每次 `synthesize` 都会归档项目总结，只有用户明确授权后才创建或替换 AI开发参考；旧 `长期经验总结/` 保持只读兼容。\
  AI development references: user-controlled knowledge for cross-task reuse is now named `AI开发参考/<项目名>.md`. Every `synthesize` run archives the project summary, while creating or replacing an AI development reference requires explicit user authorization. The former `长期经验总结/` directory remains read-compatible.
- 精确复用：AI开发参考仅在项目名或别名直接匹配，或至少两个独立特征词同时匹配时注入恢复上下文。Docker、运维等宽泛主题词不再单独触发，也不会被界面引用标注意外带入。\
  Precise reuse: an AI development reference is injected only for a direct project or alias match, or at least two independent identity terms. Broad topics such as Docker or operations no longer trigger reuse alone, and UI response annotations cannot accidentally reintroduce one.
- 凭据保护：断点、每日索引、项目总结、首页和 AI开发参考在写入前会脱敏常见令牌、密钥、密码、Cookie、JWT 与私钥；用户自行维护的普通项目 Markdown 保持原样。\
  Credential protection: checkpoints, daily indexes, project summaries, the homepage, and AI development references redact common tokens, keys, passwords, cookies, JWTs, and private keys before writing. Ordinary user-maintained project Markdown remains unchanged.

## V0.6.2
*Version 0.6.2*

- 自动写入提醒：Stop hook 在真实写入会话断点后向用户显示 vault 相对文件路径和目录。短会话仅写入每日索引、无匹配 rollout 或其他跳过情形不会产生误报。\
  Automatic write notification: after a real session-checkpoint write, the Stop hook shows the user the vault-relative file path and directory. Short index-only sessions, missing rollouts, and other skipped writes do not produce a false notice.
- 未分类暂存与受限归类：新自动断点写入 `Codex工作记录/会话断点/未分类对话/`。手动 `$checkpoint` 只整理未分类、遗留顶层断点和当前重新检查的会话，已分类历史保持原样；同标题冲突仍留在未分类目录。\
  Unclassified staging and limited classification: new automatic checkpoints are written to `Codex工作记录/会话断点/未分类对话/`. Manual `$checkpoint` organizes only unclassified notes, legacy top-level notes, and the current rechecked session; categorized history remains unchanged, and title collisions remain in the unclassified directory.

## V0.6.1
*Version 0.6.1*

- 最终断点位置：手动 checkpoint 完成分类后才输出写入回执。回执同时给出绝对路径、分类后的 vault 相对文件路径和所在目录，避免仅显示文件名或分类前位置。\
  Final checkpoint location: manual checkpoint reports the write only after classification. The receipt includes the absolute path, classified vault-relative file path, and parent directory so it never shows only a filename or the pre-classification location.

## V0.6.0
*Version 0.6.0*

- 标题保护与恢复摘要：手动 checkpoint 不再默认删除并重建既有笔记。可用的 Codex 会话标题与用户在 Obsidian 中改过的标题会保留；回执、长问句和依赖上下文的答案句会被修复。恢复摘要从完整会话的早、中、晚阶段提取结论，并排除 checkpoint 与分类回执。\
  Title protection and recovery briefs: manual checkpoint no longer deletes and rebuilds existing notes by default. Usable Codex thread titles and titles changed in Obsidian are preserved; receipts, long questions, and context-dependent answer sentences are repaired. Recovery briefs select conclusions from early, middle, and late conversation stages while excluding checkpoint and classification receipts.
- 索引与链接：每日索引改为稳定的四列表格，支持跨日会话的对话时间与更新时间，并在断点改名、分类移动和知识归档后修复路径链接及归档状态。\
  Indexes and links: daily indexes use a stable four-column table, show conversation and update time for cross-day sessions, and repair path links and archive status after checkpoint renames, classification moves, and knowledge archival.
- 清理与验证：清理流程兼容转义的 Obsidian 别名链接，能够更新当前索引结构。新增跨日索引、标题保护、回执过滤、用户改名保护和链接修复测试。\
  Cleanup and verification: cleanup supports escaped Obsidian alias links and the current index layout. New coverage verifies cross-day indexes, title protection, receipt filtering, user-renamed titles, and link repair.

## 配置
*Setup*

前提：已安装 Codex、Python 3 和 Obsidian vault，并在 `~/.codex/config.toml` 的 `[features]` 下启用 `hooks = true`。

Prerequisites: Codex, Python 3, and an Obsidian vault. Enable `hooks = true` under `[features]` in `~/.codex/config.toml`.

```bash
git clone https://github.com/DELTANACNCORE/Codex-CheckPoint.git
cd Codex-CheckPoint
mkdir -p ~/.codex/hooks ~/.codex/skills
cp .codex/redaction.py ~/.codex/redaction.py
cp .codex/metadata.py ~/.codex/metadata.py
cp .codex/maintenance.py ~/.codex/maintenance.py
cp .codex/hooks/*.py ~/.codex/hooks/
cp -R .codex/skills/checkpoint ~/.codex/skills/checkpoint
cp -R .codex/skills/search ~/.codex/skills/search
cp -R .codex/skills/synthesize ~/.codex/skills/synthesize
cp -R .codex/skills/verify ~/.codex/skills/verify
# 将 .codex/AGENTS.md 的规则合并到 ~/.codex/AGENTS.md，保留已有本地规则。
chmod +x ~/.codex/hooks/*.py
```

语义检索为可选能力。首次准备本地模型时安装固定依赖并联网缓存模型一次；后续 `search --semantic` 固定离线。

Semantic retrieval is optional. Install the pinned dependencies and cache the model online once during initial preparation; later `search --semantic` calls remain offline.

```bash
python3 -m pip install --user --only-binary=:all: -r ~/.codex/skills/search/requirements-semantic.txt
HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
```

将下列 hook 注册到 `~/.codex/hooks.json`，并将 vault 路径替换为实际路径。

Register the following hooks in `~/.codex/hooks.json`, replacing the vault path with the actual path.

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.codex/hooks/stop-wrapper.py --vault-root ~/obsidian/知识库",
        "timeout": 30
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.codex/hooks/stop-wrapper.py --vault-root ~/obsidian/知识库",
        "timeout": 30
      }]
    }],
    "PreToolUse": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.codex/hooks/pretool-wrapper.py --vault-root ~/obsidian/知识库",
        "timeout": 30
      }]
    }]
  }
}
```

## 交给 Codex 安装
*Ask Codex to Install*

可以把下面整段提示词发送给另一端 Codex。它需要终端写入权限，因为会修改该机器的 `~/.codex/`；没有明确 vault 路径时，它应先询问路径，不能猜测或覆盖已有配置。

Send the complete prompt below to another Codex instance. It needs terminal write permission because it modifies that machine's `~/.codex/`. When the vault path is unknown, it must ask first and must not guess or overwrite existing configuration.

```text
请安装 Codex CheckPoint：
https://github.com/DELTANACNCORE/Codex-CheckPoint.git

目标是为当前机器启用完整的 Codex + Obsidian 知识库工作流。

1. 询问 Obsidian vault 路径；如果没有明确路径，不要继续。
2. 克隆仓库到临时工作目录或用户指定目录。
3. 将仓库 .codex/redaction.py 复制到 ~/.codex/redaction.py。
4. 将仓库 .codex/metadata.py 复制到 ~/.codex/metadata.py。
5. 将仓库 .codex/maintenance.py 复制到 ~/.codex/maintenance.py。
6. 将仓库 .codex/hooks/*.py 复制到 ~/.codex/hooks/。
7. 将 checkpoint、search、synthesize、verify 复制到 ~/.codex/skills/。
8. 确保 ~/.codex/config.toml 的 [features] 包含 hooks = true。
9. 读取并保留 ~/.codex/hooks.json 中已有的非本项目 hook；注册以下三个 hook：
   - Stop: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - UserPromptSubmit: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - PreToolUse: python3 ~/.codex/hooks/pretool-wrapper.py --vault-root <vault-path>
10. 将仓库 .codex/AGENTS.md 的项目归档规则合并到 ~/.codex/AGENTS.md，保留已有本地规则。
11. 为复制后的 hook 添加可执行权限。
12. 运行 python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root <vault-path> 进行验证。
13. 报告 hooks.json 的实际修改、写入的断点路径和验证结果。不要输出令牌、rollout 内容或私有 vault 内容。
```

```text
Install Codex CheckPoint:
https://github.com/DELTANACNCORE/Codex-CheckPoint.git

Enable the complete Codex and Obsidian knowledge workflow on this machine.

1. Ask for the Obsidian vault path. Do not continue without an explicit path.
2. Clone the repository into a temporary directory or a user-selected directory.
3. Copy .codex/redaction.py into ~/.codex/redaction.py.
4. Copy .codex/metadata.py into ~/.codex/metadata.py.
5. Copy .codex/maintenance.py into ~/.codex/maintenance.py.
6. Copy .codex/hooks/*.py into ~/.codex/hooks/.
7. Copy checkpoint, search, synthesize, and verify into ~/.codex/skills/.
8. Ensure [features] in ~/.codex/config.toml contains hooks = true.
9. Read and preserve unrelated hooks in ~/.codex/hooks.json, then register these hooks:
   - Stop: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - UserPromptSubmit: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - PreToolUse: python3 ~/.codex/hooks/pretool-wrapper.py --vault-root <vault-path>
10. Merge the project-archiving rules from .codex/AGENTS.md into ~/.codex/AGENTS.md while preserving existing local rules.
11. Add executable permission to copied hook files.
12. Verify with python3 ~/.codex/skills/checkpoint/checkpoint.py --vault-root <vault-path>.
13. Report the actual hooks.json changes, checkpoint path, and verification result. Do not expose tokens, rollout content, or private vault content.
```

## 日常使用
*Daily Use*

1. 正常使用 Codex，hook 会持续维护断点。\
   Use Codex normally; hooks maintain checkpoints continuously.
2. 打开 `知识库首页.md` 或 `Codex工作记录/会话索引/` 回顾最近会话。\
   Open `知识库首页.md` or `Codex工作记录/会话索引/` to review recent sessions.
3. 需要立即刷新当前断点并统一整理全部断点时调用 checkpoint skill。\
   Invoke the checkpoint skill to refresh the current checkpoint and organize all saved checkpoints together.
4. 需要查找知识时调用 search skill；需要跨会话整理时明确指定项目或标签。聚类整理只有在用户确认范围和目标项目后才可调用。\
   Invoke search to find knowledge and specify a project or tag when using synthesize. Cluster synthesis is available only after the user confirms the scope and target project.
5. 需要清理伪对话或重复断点时，先运行 `synthesize --cleanup-checkpoints` 审阅候选；用户确认后再使用 `--apply-cleanup`。\
   To clean pseudo or duplicate checkpoints, first review candidates with `synthesize --cleanup-checkpoints`, then use `--apply-cleanup` after user confirmation.
6. 需要合并相关会话时，先运行 `synthesize --merge-candidates`；展示候选后，只有用户确认候选编号和独立项目名才可归档。用户直接指定 session ID 时仍须提供目标项目和确认参数。\
   To merge related sessions, first run `synthesize --merge-candidates`; after showing a proposal, archive only when the user confirms its ID and an independent project name. Direct session-ID selection still requires a target project and confirmation flag.
7. 需要检查结构、旧 metadata、知识整理建议或验证时效时运行 `synthesize --audit`。需要回填 metadata、添加跨文档链接或修复断裂链接时，先展示候选，再由用户确认指定候选。\
   Run `synthesize --audit` to inspect structure, legacy metadata, knowledge-organization suggestions, or verification freshness. For metadata backfill, cross-document links, or broken-link repair, show proposals first and obtain confirmation for the specified proposal.
8. 接手项目时优先读取 `项目总结/<项目名>.md`；已确认的父项目才读取 `项目总结/<父项目>/项目总结.md`。\
   When resuming a project, read `项目总结/<项目名>.md` first; read `项目总结/<父项目>/项目总结.md` only for confirmed parent projects.
9. 需要 AI开发参考时明确调用 `synthesize` 并授权写入；普通 checkpoint 不会生成该文件。\
   Explicitly invoke `synthesize` and authorize the write for an AI development reference; ordinary checkpoints never generate it.

## 目录结构
*Repository Layout*

```text
.codex/
├── metadata.py
├── maintenance.py
├── redaction.py
├── hooks/
│   ├── checkpoint.py
│   ├── pretool.py
│   ├── pretool-wrapper.py
│   ├── retrieve.py
│   └── stop-wrapper.py
└── skills/
    ├── checkpoint/
    ├── search/
    ├── synthesize/
    └── verify/
```

```text
vault/
├── 知识库首页.md
├── AI开发参考/<项目名>.md
├── 项目总结/<项目名>.md
└── Codex工作记录/
    ├── 会话索引/YYYY-MM-DD.md
    └── 会话断点/
        ├── 未分类对话/<自动断点主题>.md
        └── <分类>/<手动整理后的断点主题>.md
```

## 项目归档规则
*Project Archiving Rules*

独立项目只保留一份 `项目总结/<项目名>.md`。用户提到“归档到同一项目”或“放到父项目”时，Codex 必须询问该项目是否归属于该父项目；得到明确确认后，才可创建 `项目总结/<父项目>/`，并在其 `项目总结.md` 标记 `group_confirmed: true`。没有归属关系的多个项目在同一次会话中合并为一篇项目总结，并将所有会话标识写入 `session_ids`。

相关会话的自动识别只生成候选，不会自动创建项目总结、移动断点或变更索引。用户确认候选编号和独立项目名后，才会将该候选涉及的 session 归档到一篇平面项目总结；用户直接指定的 session 也遵循同一确认边界。

An independent project keeps one `项目总结/<项目名>.md`. When a user asks to archive work under the same or a parent project, Codex must ask whether the project belongs to that parent. Only an explicit confirmation permits `项目总结/<父项目>/`, whose `项目总结.md` must contain `group_confirmed: true`. Unrelated projects from one session are merged into one project summary with all session identifiers in `session_ids`.

Automatic related-session detection produces proposals only; it never creates a project summary, moves a checkpoint, or changes an index. A proposal's sessions are archived into one flat project summary only after the user confirms the proposal ID and independent project name; directly specified sessions follow the same confirmation boundary.

## 许可证
*License*

[MIT](./LICENSE)
