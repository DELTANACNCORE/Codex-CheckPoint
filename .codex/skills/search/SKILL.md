---
name: search
description: |
  Search the vault for project documents and Codex session checkpoints.
  按关键词搜索 vault 中的项目文档和 Codex 会话断点。
---

# Search Skill
*知识库搜索 Skill*

按关键词快速检索整个 Obsidian vault。`Codex工作记录/` 保存 Codex 会话断点和索引，`项目总结/` 保存项目材料，`AI开发参考/` 保存可复用结论。

Search the complete Obsidian vault by keyword. `Codex工作记录/` stores Codex checkpoints and indexes, `项目总结/` stores project material, and `AI开发参考/` stores reusable conclusions.

## 建议请求
*Suggested Prompts*

- `搜索知识库里的参考文献`\
  `Search the knowledge base for references`
- `在 Codex工作记录里查找 checkpoint`\
  `Find checkpoint in Codex工作记录`
- `查找校园旧物出售系统的部署记录`\
  `Find deployment records for the campus marketplace`
- `/search checkpoint hook`

## 执行
*Run*

优先直接运行仓库自带脚本。\
Run the bundled script directly.

```bash
python3 ~/.codex/skills/search/search.py --vault-root "$OBSIDIAN_VAULT" <关键词1> [关键词2] [关键词3]
```

没有设置 `OBSIDIAN_VAULT` 时，默认使用 `~/obsidian/知识库`。

When `OBSIDIAN_VAULT` is unset, the default vault is `~/obsidian/知识库`.

搜索会维护当前 vault 专属的 SQLite 增量索引，缓存位于 `$CODEX_HOME/cache/`，不会写入任何 Obsidian Markdown。索引不可用时自动回退到直接扫描。

Search maintains a SQLite incremental index dedicated to the current vault under `$CODEX_HOME/cache/` and never writes Obsidian Markdown. It automatically falls back to direct scanning when the index is unavailable.

```bash
python3 ~/.codex/skills/search/search.py --vault-root "$OBSIDIAN_VAULT" --index-status
python3 ~/.codex/skills/search/search.py --vault-root "$OBSIDIAN_VAULT" --rebuild-index
```

## 可选语义检索
*Optional Semantic Retrieval*

当用户使用自然语言描述已知方案、标题和关键词都无法定位时，可显式传入 `--semantic`。该模式只加载已经存在于本机缓存中的 `sentence-transformers` 模型，默认模型为 `intfloat/multilingual-e5-small`；加载过程固定离线，脚本不会下载模型或向外发送笔记内容。

When a user describes a known solution in natural language and titles or keywords cannot locate it, explicitly add `--semantic`. This mode loads only an already-cached local `sentence-transformers` model; the default is `intfloat/multilingual-e5-small`. Loading is fixed offline: the script never downloads a model or sends note content externally.

语义依赖固定使用 `requirements-semantic.txt` 中的版本。`sentence-transformers 5.x` 与该模型的旧版 Pooling 配置存在兼容问题，不能替代固定版本。

Semantic dependencies use the versions pinned in `requirements-semantic.txt`. `sentence-transformers 5.x` is incompatible with this model's legacy Pooling configuration and cannot replace the pinned versions.

```bash
python3 -m pip install --user --only-binary=:all: -r ~/.codex/skills/search/requirements-semantic.txt
HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
```

第二条命令只在首次准备模型时联网执行一次。后续 `search --semantic` 固定离线加载本地缓存。

The second command accesses the network once during initial model preparation. Later `search --semantic` calls load the local cache offline.

```bash
python3 ~/.codex/skills/search/search.py --vault-root "$OBSIDIAN_VAULT" --semantic <自然语言查询>
```

语义向量按文档标题和段落分块保存到当前 vault 对应的 `$CODEX_HOME/cache/` SQLite 缓存中。模型不可用、缓存损坏或向量计算失败时，命令会提示原因并继续使用原有的词法检索；默认搜索没有开启语义召回，原有排序保持不变。

Semantic vectors are stored as title-aware document and paragraph chunks in the `$CODEX_HOME/cache/` SQLite cache for the current vault. When the model is unavailable, the cache is damaged, or vector computation fails, the command reports the reason and continues with the existing lexical search. Default searches do not enable semantic recall, so their previous ordering remains unchanged.

## 检索优先级
*Retrieval Priority*

脚本会按 `aliases`、`keywords`、`tags`、标题或正文的顺序排序，并保留无 metadata 旧文档的正文兼容检索。`--semantic` 仅在词法命中之外补充达到阈值的语义结果，词法排序始终优先。每次最多返回 5 条，继续处理时只读取最相关的 1-2 篇。

The script ranks `aliases`, `keywords`, `tags`, then title or body matches, while retaining body fallback for older documents without metadata. `--semantic` adds only threshold-passing semantic results beyond lexical hits, and lexical ordering always takes precedence. It returns at most five results; subsequent work reads only the one or two most relevant notes.

## 输出
*Output*

- 归档文档命中。\
  Archived-document matches.
- 断点笔记命中。\
  Checkpoint-note matches.
- 每条结果的简短摘要或状态。\
  A short summary or status for each result.

## 已验证范围
*Verified Scope*

按 skill 调用脚本的路径可完成真实搜索。Codex 桌面端对 `/search` 的原生命令识别尚未稳定验证。

Invoking the script through this skill performs real searches. Stable native `/search` recognition in Codex Desktop is not yet verified.
