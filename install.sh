#!/usr/bin/env bash
set -euo pipefail

LITE=false
if [ "${1:-}" = "--lite" ]; then
  LITE=true
  echo "[checkpoint-codex] 安装模式: Lite（仅手动 /checkpoint） / Installation mode: Lite (manual /checkpoint only)"
else
  echo "[checkpoint-codex] 安装模式: Full（自动 hook + 手动 /checkpoint） / Installation mode: Full (automatic hooks + manual /checkpoint)"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SRC="$SCRIPT_DIR/.codex/hooks/checkpoint.py"
PRETOOL_SRC="$SCRIPT_DIR/.codex/hooks/pretool.py"
STOP_WRAPPER_SRC="$SCRIPT_DIR/.codex/hooks/stop-wrapper.py"
RETRIEVE_SRC="$SCRIPT_DIR/.codex/hooks/retrieve.py"
PRETOOL_WRAPPER_SRC="$SCRIPT_DIR/.codex/hooks/pretool-wrapper.py"
if [ "$LITE" = true ]; then
  SKILL_SRC="$SCRIPT_DIR/.codex/skills/checkpoint-lite"
else
  SKILL_SRC="$SCRIPT_DIR/.codex/skills/checkpoint"
fi
SEARCH_SRC="$SCRIPT_DIR/.codex/skills/search"
SYNTH_SRC="$SCRIPT_DIR/.codex/skills/synthesize"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
HOOK_DST_DIR="$CODEX_HOME/hooks"
HOOK_DST="$HOOK_DST_DIR/checkpoint.py"
PRETOOL_DST="$HOOK_DST_DIR/pretool.py"
STOP_WRAPPER_DST="$HOOK_DST_DIR/stop-wrapper.py"
RETRIEVE_DST="$HOOK_DST_DIR/retrieve.py"
PRETOOL_WRAPPER_DST="$HOOK_DST_DIR/pretool-wrapper.py"
SKILL_DST_DIR="$CODEX_HOME/skills"
SKILL_DST="$SKILL_DST_DIR/checkpoint"
SEARCH_DST="$SKILL_DST_DIR/search"
SYNTH_DST="$SKILL_DST_DIR/synthesize"
AGENTS_DST="$CODEX_HOME/AGENTS.md"
HOOKS_JSON="$CODEX_HOME/hooks.json"
CONFIG_TOML="$CODEX_HOME/config.toml"
DEFAULT_VAULT="$HOME/obsidian/知识库"

echo "[checkpoint-codex] 仓库目录 / Repository: $SCRIPT_DIR"
echo "[checkpoint-codex] Codex 目录 / Codex home: $CODEX_HOME"

if [ ! -f "$HOOK_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 hook 脚本 / Hook script not found: $HOOK_SRC" >&2
  exit 1
fi

if [ ! -f "$PRETOOL_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 PreToolUse 脚本 / PreToolUse script not found: $PRETOOL_SRC" >&2
  exit 1
fi

if [ ! -f "$STOP_WRAPPER_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 Stop wrapper / Stop wrapper not found: $STOP_WRAPPER_SRC" >&2
  exit 1
fi

if [ ! -f "$RETRIEVE_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到检索 hook / Retrieval hook not found: $RETRIEVE_SRC" >&2
  exit 1
fi

if [ ! -f "$PRETOOL_WRAPPER_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 PreTool wrapper / PreTool wrapper not found: $PRETOOL_WRAPPER_SRC" >&2
  exit 1
fi

echo
echo "断点笔记会写到 Obsidian vault 下的 Codex工作记录/ 目录。 / Checkpoints will be written to Codex工作记录/ in your Obsidian vault."
read -r -p "Obsidian vault 路径 / path [默认 / default: $DEFAULT_VAULT]: " VAULT
VAULT="${VAULT:-$DEFAULT_VAULT}"

mkdir -p "$HOOK_DST_DIR" "$SKILL_DST_DIR"
cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"
echo "[checkpoint-codex] ✓ hook 脚本已复制 / Hook script copied: $HOOK_DST"
cp "$PRETOOL_SRC" "$PRETOOL_DST"
chmod +x "$PRETOOL_DST"
echo "[checkpoint-codex] ✓ PreToolUse 脚本已复制 / PreToolUse script copied: $PRETOOL_DST"
cp "$STOP_WRAPPER_SRC" "$STOP_WRAPPER_DST"
chmod +x "$STOP_WRAPPER_DST"
echo "[checkpoint-codex] ✓ Stop wrapper 已复制 / Stop wrapper copied: $STOP_WRAPPER_DST"
cp "$RETRIEVE_SRC" "$RETRIEVE_DST"
chmod +x "$RETRIEVE_DST"
echo "[checkpoint-codex] ✓ 检索 hook 已复制 / Retrieval hook copied: $RETRIEVE_DST"
cp "$PRETOOL_WRAPPER_SRC" "$PRETOOL_WRAPPER_DST"
chmod +x "$PRETOOL_WRAPPER_DST"
echo "[checkpoint-codex] ✓ PreTool wrapper 已复制 / PreTool wrapper copied: $PRETOOL_WRAPPER_DST"

rm -rf "$SKILL_DST"
cp -R "$SKILL_SRC" "$SKILL_DST"
echo "[checkpoint-codex] ✓ /checkpoint skill 已安装 / installed: $SKILL_DST"

if [ -d "$SEARCH_SRC" ]; then
  rm -rf "$SEARCH_DST"
  cp -R "$SEARCH_SRC" "$SEARCH_DST"
  echo "[checkpoint-codex] ✓ /search skill 已安装 / installed: $SEARCH_DST"
fi

if [ -d "$SYNTH_SRC" ]; then
  rm -rf "$SYNTH_DST"
  cp -R "$SYNTH_SRC" "$SYNTH_DST"
  echo "[checkpoint-codex] ✓ /synthesize skill 已安装 / installed: $SYNTH_DST"
fi

if [ ! -f "$AGENTS_DST" ]; then
  cat > "$AGENTS_DST" <<EOF
# Codex Checkpoint Guide

## 回答前优先检索知识库 / Retrieve Knowledge Before Answering

在回答技术、方案、配置、运维、开发类问题之前优先检索。 Before answering technical, design, configuration, operations, or development questions, retrieve relevant knowledge first.

1. 从用户问题提取 1-3 个关键词。 Extract 1-3 keywords from the request.
2. 先读取 \`$VAULT/长期经验总结/\` 中相关经验，再搜索项目总结和会话断点。 Read relevant experience first, then search project summaries and checkpoints.
3. 优先读取最相关的 1-2 篇已有文档。 Read the 1-2 most relevant documents first.
4. 已有结论直接复用，只补充新的差异。 Reuse existing conclusions and add only new differences.

## 方案归档 / Archive Decisions

方案敲定后优先写入以下位置。 When a decision is settled, prefer this document location:

\`$VAULT/项目总结/<项目名>/<方案标题>.md\`

建议 frontmatter。 Suggested frontmatter:

\`\`\`yaml
---
date: YYYY-MM-DD
project: 项目名
tags: [codex/方案, ...]
---
\`\`\`

## 会话断点 / Session Checkpoints

- Full 模式：Stop hook 自动写断点。 Full mode: the Stop hook writes checkpoints automatically.
- Lite 模式：手动运行 checkpoint skill。 Lite mode: run the checkpoint skill manually.
- 项目目录有真实产出时，会同步刷新项目总结和长期经验总结。 Real project output refreshes project and reusable-experience summaries.
EOF
  echo "[checkpoint-codex] ✓ 已创建全局 AGENTS 模板 / Global AGENTS template created: $AGENTS_DST"
else
  echo "[checkpoint-codex] · 检测到已有 AGENTS.md，跳过创建 / Existing AGENTS.md detected, skipped"
fi

python3 - "$HOOKS_JSON" "$STOP_WRAPPER_DST" "$PRETOOL_WRAPPER_DST" "$VAULT" "$LITE" <<'PY'
import json, sys, os

hooks_path, stop_wrapper_dst, pretool_wrapper_dst, vault, lite_flag = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
lite = lite_flag.lower() == "true"
if os.path.exists(hooks_path):
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
else:
    data = {}

hooks = data.setdefault("hooks", {})
stop = hooks.setdefault("Stop", [])
pre = hooks.setdefault("PreToolUse", [])
user_prompt_submit = hooks.setdefault("UserPromptSubmit", [])
stop[:] = [
    entry for entry in stop
    if not any(
        any(token in h.get("command", "") for token in ("checkpoint.py", "codex-hook.js", "stop-wrapper.py", "probe-hook.py"))
        for h in entry.get("hooks", [])
    )
]
pre[:] = [
    entry for entry in pre
    if not any(
        any(token in h.get("command", "") for token in ("pretool.py", "codex-hook.js", "pretool-wrapper.py", "probe-hook.py"))
        for h in entry.get("hooks", [])
    )
]
user_prompt_submit[:] = [
    entry for entry in user_prompt_submit
    if not any(
        any(token in h.get("command", "") for token in ("checkpoint.py", "codex-hook.js", "stop-wrapper.py", "probe-hook.py"))
        for h in entry.get("hooks", [])
    )
]
if not lite:
    stop.insert(0, {
        "hooks": [
            {
                "type": "command",
                "command": f"python3 {stop_wrapper_dst} --vault-root {vault}",
                "timeout": 30,
            }
        ]
    })
pre.insert(0, {
    "hooks": [
        {
            "type": "command",
            "command": f"python3 {pretool_wrapper_dst} --vault-root {vault}",
            "timeout": 30,
        }
    ]
})
if not lite:
    user_prompt_submit.insert(0, {
        "hooks": [
            {
                "type": "command",
                "command": f"python3 {stop_wrapper_dst} --vault-root {vault}",
                "timeout": 30,
            }
        ]
    })

with open(hooks_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
if lite:
    print(f"[checkpoint-codex] ✓ Lite 模式已清理自动写入 / Lite mode cleared Stop and UserPromptSubmit writes")
else:
    print(f"[checkpoint-codex] ✓ Stop hook 已写入 / registered: {hooks_path}")
print(f"[checkpoint-codex] ✓ PreToolUse hook 已写入 / registered: {hooks_path}")
PY

if [ -f "$CONFIG_TOML" ]; then
  if rg -n '^hooks = true$' "$CONFIG_TOML" >/dev/null 2>&1; then
    echo "[checkpoint-codex] ✓ config.toml 已开启 hooks / hooks enabled"
  else
    echo "[checkpoint-codex] ⚠️ 请确认 $CONFIG_TOML 的 [features] 下已启用 hooks = true / confirm hooks = true under [features]"
  fi
else
  echo "[checkpoint-codex] ⚠️ 未找到 $CONFIG_TOML，请确认 Codex 已初始化 / config not found; confirm Codex is initialized"
fi

cat <<EOF

[checkpoint-codex] 安装完成 / Installation complete ($([ "$LITE" = true ] && echo 'Lite' || echo 'Full') mode).

- $([ "$LITE" = true ] && echo 'Lite 模式跳过自动写入 / Lite mode skips automatic writes' || echo "Stop Hook 已注册 / registered: $HOOKS_JSON")
- PreToolUse Hook 已注册 / registered: $HOOKS_JSON
- vault 路径将通过 --vault-root 传给 hook / the vault path is passed through --vault-root
- checkpoint.py 手动执行链路已经验证 / the manual checkpoint.py path is verified
- search 与 synthesize 已作为本地 skill 安装 / search and synthesize skills are installed locally
- $([ "$LITE" = true ] && echo 'checkpoint skill 已切到 Lite 版本 / checkpoint skill uses Lite' || echo 'checkpoint skill 使用 Full 版本 / checkpoint skill uses Full')
- 全局 AGENTS 模板 / global AGENTS template: $([ -f "$AGENTS_DST" ] && echo "$AGENTS_DST" || echo '未创建 / not created')
- slash 直调尚未稳定验证，可靠方式是按 skill 调脚本 / native slash invocation is not yet verified; invoke the script through the skill

当前版本仅支持 Codex / This version supports Codex only:
- 自动断点可用 / automatic checkpoints are available
- Codex rollout 解析可用 / Codex rollout parsing is available
- 输出目录、标签和首页文件名使用 Codex 口径 / output paths, tags, and homepage names follow Codex conventions
- search 与 synthesize 提供本地脚本 / search and synthesize provide local scripts
EOF
