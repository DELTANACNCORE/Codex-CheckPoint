#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
if [ -z "$ARCHIVE" ] || [ ! -f "$ARCHIVE" ]; then
  echo "用法: ./unpack.sh <checkpoint-codex-migrate-xxx.tar.gz>"
  exit 1
fi

VAULT="${OBSIDIAN_VAULT:-}"
if [ -z "${VAULT:-}" ]; then
  read -r -p "Obsidian vault 路径 [默认: $HOME/obsidian/知识库]: " VAULT
  VAULT="${VAULT:-$HOME/obsidian/知识库}"
fi
VAULT="${VAULT/#~/$HOME}"

echo "[unpack-codex] 知识库 -> $VAULT"
mkdir -p "$VAULT"
tar -xzf "$ARCHIVE" -C "$VAULT" --exclude='.codex/*'
echo "[unpack-codex]   工作记录、项目总结与首页 ✓"

echo "[unpack-codex] rollout -> $HOME/.codex/"
mkdir -p "$HOME/.codex"
tar -xzf "$ARCHIVE" -C "$HOME" .codex/sessions/ && echo "[unpack-codex]   sessions ✓"

echo
echo "[unpack-codex] 完成。接下来："
echo "  git clone https://github.com/hjm4839-coder/checkpoint.git"
echo "  cd checkpoint && ./install.sh"
