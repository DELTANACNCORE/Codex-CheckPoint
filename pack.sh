#!/usr/bin/env bash
set -euo pipefail

CONFIG="$HOME/.codex/config.toml"
VAULT="${OBSIDIAN_VAULT:-}"

if [ -z "$VAULT" ] && [ -f "$CONFIG" ] && command -v python3 >/dev/null 2>&1; then
  VAULT=$(python3 - <<'PY'
from pathlib import Path
import re
cfg = Path.home() / ".codex" / "hooks.json"
try:
    text = cfg.read_text(encoding="utf-8")
except Exception:
    text = ""
m = re.search(r'--vault-root\s+([^\"]\S*|\"[^\"]+\")', text)
if m:
    v = m.group(1).strip('"')
    print(v)
PY
)
fi

if [ -z "${VAULT:-}" ]; then
  read -r -p "Obsidian vault 路径 [默认: $HOME/obsidian/知识库]: " VAULT
  VAULT="${VAULT:-$HOME/obsidian/知识库}"
fi
VAULT="${VAULT/#~/$HOME}"

SESSIONS="$HOME/.codex/sessions"
OUT="checkpoint-codex-migrate-$(date +%Y%m%d-%H%M%S).tar.gz"

echo "[pack-codex] vault: $VAULT"

if [ ! -d "$VAULT/Codex工作记录" ]; then
  echo "[pack-codex] Codex工作记录/ 不存在，目录不对？"
  exit 1
fi

items=(Codex工作记录)
for item in 项目总结 长期经验总结 知识库首页.md Codex协同Obsidian工作流skill更新日志.md; do
  [ -e "$VAULT/$item" ] && items+=("$item")
done

tar -czf "$OUT" -C "$VAULT" "${items[@]}" -C "$HOME" .codex/sessions

SIZE=$(du -h "$OUT" | cut -f1)
echo "[pack-codex] -> $OUT ($SIZE)"
echo "[pack-codex] 传到新电脑后运行 unpack.sh"
