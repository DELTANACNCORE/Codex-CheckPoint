---
name: checkpoint
description: Save current session checkpoint to Obsidian. Triggered by /checkpoint. (Lite: uses conversation model, no extra API call)
---

# /checkpoint — Save session checkpoint (Lite)

用**当前对话模型**生成主题/标签/关键词，不额外调 API。

## Triggers

- `/checkpoint`

## Steps

### 1. 综合元数据

基于当前对话内容，生成：

- **主题**：≤20 汉字，概括本次会话做了什么
- **分类标签**：从「产品」「功能开发」「日常问答」挑 **1-2 个**最贴合的
- **内容关键词**：1-3 个，描述具体涉及的技术/模块/场景（逗号分隔）

输出为：`主题: xxx` / `标签: a,b` / `关键词: x,y`

### 2. 找当前会话 transcript

```bash
ls -t ~/.claude/projects/*/*.jsonl | head -1
```
session_id 取文件名去 `.jsonl`。

### 3. 跑脚本（传入元数据，不调 LLM）

```bash
python3 ~/obsidian/.claude/hooks/checkpoint.py \
  --transcript <path> \
  --session-id <id> \
  --topic "主题" \
  --tags "标签1,标签2" \
  --keywords "关键词1,关键词2,关键词3"
```

### 4. 报告

展示：状态、话题、标签、关键词、产出。有 ⚠️/📋 提醒恢复。
