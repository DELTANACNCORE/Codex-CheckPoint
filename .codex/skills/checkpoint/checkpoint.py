#!/usr/bin/env python3
"""Run Codex checkpoint hook manually for the latest or selected rollout."""

import argparse
import glob
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-root", default=str(Path("~/obsidian/知识库").expanduser()))
    parser.add_argument("--rollout")
    parser.add_argument("--session-id")
    parser.add_argument("--keep-title", action="store_true")
    parser.add_argument("--refresh-title", action="store_true")
    return parser.parse_args()


def codex_home() -> Path:
    return Path.home() / ".codex"


def checkpoint_hook_path() -> Path:
    return codex_home() / "hooks" / "checkpoint.py"


def latest_rollout() -> Path | None:
    sessions_dir = codex_home() / "sessions"
    candidates = list(sessions_dir.rglob("rollout-*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def rollout_by_session(session_id: str) -> Path | None:
    sessions_dir = codex_home() / "sessions"
    pattern = str(sessions_dir / "**" / f"rollout-*{session_id}.jsonl")
    candidates = [Path(p) for p in glob.glob(pattern, recursive=True)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def session_id_from_rollout(path: Path) -> str:
    stem = path.stem
    parts = stem.split("-")
    return "-".join(parts[-5:]) if len(parts) >= 5 else stem


def main():
    args = parse_args()
    hook = checkpoint_hook_path()
    if not hook.exists():
        print(f"未找到 hook 脚本：{hook}")
        sys.exit(1)

    vault_root = Path(args.vault_root).expanduser().resolve()
    if not vault_root.is_dir() or not (vault_root / ".obsidian").is_dir():
        print(f"不是有效的 Obsidian vault：{vault_root}")
        sys.exit(1)

    rollout = None
    if args.rollout:
        rollout = Path(args.rollout).expanduser().resolve()
    elif args.session_id:
        rollout = rollout_by_session(args.session_id)
    else:
        rollout = latest_rollout()
    if rollout is None or not rollout.exists():
        print("没有找到可用的 Codex rollout。")
        sys.exit(1)

    session_id = args.session_id or session_id_from_rollout(rollout)
    cmd = [
        sys.executable,
        str(hook),
        "--manual-checkpoint",
        "--vault-root",
        str(vault_root),
        "--transcript",
        str(rollout),
        "--session-id",
        session_id,
    ]
    if args.keep_title:
        cmd.append("--keep-title")
    else:
        # 手动 checkpoint 会检查自动生成的标题是否需要刷新，但不会删除已有笔记。
        cmd.append("--refresh-title")

    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
