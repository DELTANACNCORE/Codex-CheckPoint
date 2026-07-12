#!/usr/bin/env bash
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
HOOKS_JSON="$CODEX_HOME/hooks.json"
SKILLS_DIR="$CODEX_HOME/skills"
AGENTS_DST="$CODEX_HOME/AGENTS.md"

echo "[checkpoint-codex] 正在卸载..."

if [ -f "$HOOKS_JSON" ]; then
  python3 - "$HOOKS_JSON" <<'PY'
import json, sys
hooks_path = sys.argv[1]
try:
    with open(hooks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print("[checkpoint-codex] hooks.json 不存在或无效，跳过")
    sys.exit(0)

hooks = data.get("hooks", {})
targets = {
    "Stop": ("checkpoint.py", "stop-wrapper.py", "probe-hook.py"),
    "UserPromptSubmit": ("checkpoint.py", "stop-wrapper.py", "probe-hook.py"),
    "PreToolUse": ("pretool.py", "pretool-wrapper.py", "probe-hook.py"),
}
changed = False
for hook_name, tokens in targets.items():
    entries = hooks.get(hook_name, [])
    if not entries:
        continue
    before = len(entries)
    entries[:] = [
        entry for entry in entries
        if not any(any(token in h.get("command", "") for token in tokens) for h in entry.get("hooks", []))
    ]
    after = len(entries)
    if after != before:
        changed = True
        print(f"[checkpoint-codex] 已清理 hooks.{hook_name}: {before}->{after}")
    if not entries:
        hooks.pop(hook_name, None)

if changed:
    with open(hooks_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[checkpoint-codex] hooks.json 已更新: {hooks_path}")
else:
    print("[checkpoint-codex] 未找到需要清理的 hook")
PY
fi

for skill in checkpoint search synthesize; do
  if [ -d "$SKILLS_DIR/$skill" ]; then
    rm -rf "$SKILLS_DIR/$skill"
    echo "[checkpoint-codex] 已删除 skill: $SKILLS_DIR/$skill"
  fi
done

for hook in checkpoint.py pretool.py stop-wrapper.py pretool-wrapper.py retrieve.py; do
  if [ -f "$CODEX_HOME/hooks/$hook" ]; then
    rm -f "$CODEX_HOME/hooks/$hook"
    echo "[checkpoint-codex] 已删除 hook: $CODEX_HOME/hooks/$hook"
  fi
done

if [ -f "$AGENTS_DST" ] && rg -n "^# Codex Checkpoint Guide$" "$AGENTS_DST" >/dev/null 2>&1; then
  rm -f "$AGENTS_DST"
  echo "[checkpoint-codex] 已删除自动生成的 AGENTS 模板: $AGENTS_DST"
fi

cat <<EOF

[checkpoint-codex] 卸载完成。
- 你的 Obsidian 笔记仍然保留在 vault 里
- 如需继续使用，重新运行 install.sh 即可
EOF
