#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "用法 / Usage: ./unpack.sh <checkpoint-codex-migrate-xxx.tar.gz>"
  exit 1
fi

VAULT="${OBSIDIAN_VAULT:-}"
if [ -z "${VAULT:-}" ]; then
  read -r -p "Obsidian vault 路径 / path [默认 / default: $HOME/obsidian/知识库]: " VAULT
  VAULT="${VAULT:-$HOME/obsidian/知识库}"
fi
VAULT="${VAULT/#~/$HOME}"

echo "[unpack-codex] 知识库 / vault -> $VAULT"
mkdir -p "$VAULT"
tar -xzf "$ARCHIVE" -C "$VAULT" --exclude='.codex/*'
echo "[unpack-codex]   工作记录、项目总结与首页已恢复 / records, summaries, and homepage restored ✓"

echo "[unpack-codex] rollout 会话记录 / sessions -> $HOME/.codex/"
mkdir -p "$HOME/.codex"
tar -xzf "$ARCHIVE" -C "$HOME" .codex/sessions/ && echo "[unpack-codex]   sessions 已恢复 / restored ✓"

echo
echo "[unpack-codex] 完成。接下来 / Complete. Next:"
echo "  git clone https://github.com/DELTANACNCORE/Codex-CheckPoint.git"
echo "  cd Codex-CheckPoint && ./install.sh"
