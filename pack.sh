#!/usr/bin/env bash
# checkpoint 知识库打包脚本（旧电脑运行）
set -euo pipefail

echo "知识库在哪个目录？"
read -r -p "Obsidian vault 路径 [默认: $HOME/obsidian/知识库]: " VAULT
VAULT="${VAULT:-$HOME/obsidian/知识库}"
VAULT="${VAULT/#~/$HOME}"

PLANS="$VAULT/Claude方案"
DASH="$VAULT/_知识库首页.md"
PROJECTS="$HOME/.claude/projects"
OUT="checkpoint-migrate-$(date +%Y%m%d-%H%M).tar.gz"

echo "[pack] vault: $VAULT"

if [ ! -d "$PLANS" ]; then
    echo "[pack] Claude方案/ 不存在，目录不对？"
    exit 1
fi

# 首页如果在 vault 根也打进去
[ -f "$DASH" ] && cp "$DASH" "$PLANS/" 2>/dev/null || true

tar -czf "$OUT" -C "$VAULT" Claude方案 -C "$HOME" .claude/projects

[ -f "$PLANS/_知识库首页.md" ] && rm "$PLANS/_知识库首页.md" 2>/dev/null || true

SIZE=$(du -h "$OUT" | cut -f1)
echo "[pack] → $OUT ($SIZE)"
echo "[pack] 传到新电脑后跑 unpack.sh"
