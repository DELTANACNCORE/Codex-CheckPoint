#!/usr/bin/env bash
set -euo pipefail

LITE=false
if [ "${1:-}" = "--lite" ]; then
  LITE=true
  echo "[checkpoint-codex] 安装模式: Lite（仅手动 /checkpoint）"
else
  echo "[checkpoint-codex] 安装模式: Full（自动 hook + 手动 /checkpoint）"
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

echo "[checkpoint-codex] 仓库目录: $SCRIPT_DIR"
echo "[checkpoint-codex] Codex 目录: $CODEX_HOME"

if [ ! -f "$HOOK_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 hook 脚本: $HOOK_SRC" >&2
  exit 1
fi

if [ ! -f "$PRETOOL_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 PreToolUse 脚本: $PRETOOL_SRC" >&2
  exit 1
fi

if [ ! -f "$STOP_WRAPPER_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 Stop wrapper: $STOP_WRAPPER_SRC" >&2
  exit 1
fi

if [ ! -f "$RETRIEVE_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到检索 hook: $RETRIEVE_SRC" >&2
  exit 1
fi

if [ ! -f "$PRETOOL_WRAPPER_SRC" ]; then
  echo "[checkpoint-codex] ✗ 找不到 PreTool wrapper: $PRETOOL_WRAPPER_SRC" >&2
  exit 1
fi

echo
echo "断点笔记会写到你的 Obsidian vault 下的 Codex工作记录/ 目录。"
read -r -p "你的 Obsidian vault 路径 [默认: $DEFAULT_VAULT]: " VAULT
VAULT="${VAULT:-$DEFAULT_VAULT}"

mkdir -p "$HOOK_DST_DIR" "$SKILL_DST_DIR"
cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"
echo "[checkpoint-codex] ✓ hook 脚本已复制到 $HOOK_DST"
cp "$PRETOOL_SRC" "$PRETOOL_DST"
chmod +x "$PRETOOL_DST"
echo "[checkpoint-codex] ✓ PreToolUse 脚本已复制到 $PRETOOL_DST"
cp "$STOP_WRAPPER_SRC" "$STOP_WRAPPER_DST"
chmod +x "$STOP_WRAPPER_DST"
echo "[checkpoint-codex] ✓ Stop wrapper 已复制到 $STOP_WRAPPER_DST"
cp "$RETRIEVE_SRC" "$RETRIEVE_DST"
chmod +x "$RETRIEVE_DST"
echo "[checkpoint-codex] ✓ 检索 hook 已复制到 $RETRIEVE_DST"
cp "$PRETOOL_WRAPPER_SRC" "$PRETOOL_WRAPPER_DST"
chmod +x "$PRETOOL_WRAPPER_DST"
echo "[checkpoint-codex] ✓ PreTool wrapper 已复制到 $PRETOOL_WRAPPER_DST"

rm -rf "$SKILL_DST"
cp -R "$SKILL_SRC" "$SKILL_DST"
echo "[checkpoint-codex] ✓ /checkpoint skill 已装到 $SKILL_DST"

if [ -d "$SEARCH_SRC" ]; then
  rm -rf "$SEARCH_DST"
  cp -R "$SEARCH_SRC" "$SEARCH_DST"
  echo "[checkpoint-codex] ✓ /search skill 已装到 $SEARCH_DST"
fi

if [ -d "$SYNTH_SRC" ]; then
  rm -rf "$SYNTH_DST"
  cp -R "$SYNTH_SRC" "$SYNTH_DST"
  echo "[checkpoint-codex] ✓ /synthesize skill 已装到 $SYNTH_DST"
fi

if [ ! -f "$AGENTS_DST" ]; then
  cat > "$AGENTS_DST" <<EOF
# Codex Checkpoint Guide

## 回答前优先检索知识库

在回答技术、方案、配置、运维、开发类问题之前，优先检索：

1. 从用户问题提取 1-3 个关键词
2. 先读取 \`$VAULT/长期经验总结/\` 中与当前任务相关的经验，再搜索项目总结和会话断点
3. 优先读取最相关的 1-2 篇已有文档
4. 已有结论直接复用，只补充新的差异

## 方案归档

方案敲定后，优先把文档写到：

\`$VAULT/项目总结/<项目名>/<方案标题>.md\`

建议 frontmatter：

\`\`\`yaml
---
date: YYYY-MM-DD
project: 项目名
tags: [codex/方案, ...]
---
\`\`\`

## 会话断点

- Full 模式：Stop hook 自动写断点
- Lite 模式：手动运行 checkpoint skill
- 项目目录有真实产出时，会同步刷新项目总结和长期经验总结
EOF
  echo "[checkpoint-codex] ✓ 已创建全局 AGENTS 模板: $AGENTS_DST"
else
  echo "[checkpoint-codex] · 检测到已有 AGENTS.md，跳过创建"
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
    print(f"[checkpoint-codex] ✓ Lite 模式已清理 Stop / UserPromptSubmit 自动写入")
else:
    print(f"[checkpoint-codex] ✓ Stop hook 已写入 {hooks_path}")
print(f"[checkpoint-codex] ✓ PreToolUse hook 已写入 {hooks_path}")
PY

if [ -f "$CONFIG_TOML" ]; then
  if rg -n '^hooks = true$' "$CONFIG_TOML" >/dev/null 2>&1; then
    echo "[checkpoint-codex] ✓ config.toml 已开启 hooks"
  else
    echo "[checkpoint-codex] ⚠️ 请确认 $CONFIG_TOML 的 [features] 下已启用 hooks = true"
  fi
else
  echo "[checkpoint-codex] ⚠️ 未找到 $CONFIG_TOML，请确认 Codex 已初始化"
fi

cat <<EOF

[checkpoint-codex] 安装完成（$([ "$LITE" = true ] && echo 'Lite' || echo 'Full') 模式）。

- $([ "$LITE" = true ] && echo 'Lite 模式跳过 Stop / UserPromptSubmit 自动写入' || echo "Stop Hook 已注册到 $HOOKS_JSON")
- PreToolUse Hook 已注册到 $HOOKS_JSON
- vault 路径将通过 --vault-root 传给 hook
- checkpoint.py 手动执行链路已经验证
- search 与 synthesize 已作为本地可执行 skill 安装
- $([ "$LITE" = true ] && echo 'checkpoint skill 已切到 Lite 版本' || echo 'checkpoint skill 使用 Full 版本')
- 全局 AGENTS 模板：$([ -f "$AGENTS_DST" ] && echo "$AGENTS_DST" || echo '未创建')
- slash 直调当前没有完成验证，稳定方式仍然是按 skill 调脚本

当前版本仅支持 Codex：
- 自动断点可用
- Codex rollout 解析可用
- 输出目录、标签和首页文件名都会使用 Codex 口径
- search 与 synthesize 已有本地脚本实现
EOF
