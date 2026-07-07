#!/usr/bin/env bash
# checkpoint 卸载脚本
# 清理 Stop/PreToolUse hook、skill、env 配置
set -euo pipefail

SETTINGS="$HOME/.claude/settings.json"
SKILLS_DIR="$HOME/.claude/skills"

echo "[checkpoint] 正在卸载..."

if [ ! -f "$SETTINGS" ]; then
    echo "[checkpoint] $SETTINGS 不存在，无需卸载"
else
    python3 - "$SETTINGS" <<'PY'
import json, sys, os
sp = os.path.expanduser(sys.argv[1])
try:
    with open(sp, "r") as f: data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print("[checkpoint] 配置文件不存在或无效，跳过")
    sys.exit(0)

cleaned = False
for hook_type in ("Stop", "PreToolUse"):
    hooks = data.get("hooks", {}).get(hook_type, [])
    if not hooks: continue
    before = len(hooks)
    hooks[:] = [e for e in hooks if not any(
        "checkpoint.py" in h.get("command", "") or "pretool.py" in h.get("command", "")
        for h in e.get("hooks", [])
    )]
    after = len(hooks)
    if after < before:
        cleaned = True
        print(f"[checkpoint] 已清理 hooks.{hook_type}: {before}→{after}")
    if not hooks:
        data["hooks"].pop(hook_type, None)

# 可选移除 OBSIDIAN_VAULT（如果同 checkpoint 同批安装的）
env = data.get("env", {})
vault = env.pop("OBSIDIAN_VAULT", None)
if vault:
    cleaned = True
    print(f"[checkpoint] 已移除 env.OBSIDIAN_VAULT ({vault})")
if not env:
    data.pop("env", None)
if not data.get("hooks"):
    data.pop("hooks", None)

if cleaned:
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[checkpoint] 配置已更新: {sp}")
else:
    print("[checkpoint] 未找到 checkpoint 相关配置")
PY
fi

# 清理 skills
for skill in checkpoint synthesize; do
    D="$SKILLS_DIR/$skill"
    if [ -d "$D" ]; then
        rm -rf "$D"
        echo "[checkpoint] 已删除 skill: $D"
    fi
done

# 清理 bak（如果存在）
BAK="$SETTINGS.bak"
if [ -f "$BAK" ]; then
    rm -f "$BAK"
    echo "[checkpoint] 已删除备份: $BAK"
fi

cat <<EOF

[checkpoint] 卸载完成。

  - 断点笔记和每日索引仍保留在 vault 里（如需删除，手动删除 Claude方案/会话断点/ 和 Claude方案/会话索引/）。
EOF
