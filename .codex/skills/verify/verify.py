#!/usr/bin/env python3
"""Run explicitly selected verification commands with redacted evidence."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


CODEX_ROOT = Path(__file__).resolve().parents[2]
if str(CODEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEX_ROOT))

from redaction import redact_sensitive_text


DEFAULT_TIMEOUT = 120
DEFAULT_MAX_OUTPUT = 8000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行用户明确指定的当前环境验证命令")
    parser.add_argument("--command", action="append", dest="commands", help="需要执行的命令，可重复提供")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="命令执行目录，默认当前目录")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="每条命令的超时秒数")
    parser.add_argument("--max-output", type=int, default=DEFAULT_MAX_OUTPUT, help="每条命令保留的最大输出字符数")
    parser.add_argument("--dry-run", action="store_true", help="只显示将执行的命令，不实际运行")
    return parser.parse_args()


def _captured_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _safe_output(value: str, limit: int) -> str:
    text = redact_sensitive_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def run_command(command: str, cwd: Path, timeout: int) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    try:
        arguments = shlex.split(command)
    except ValueError as error:
        return None, f"命令解析失败：{error}"
    if not arguments:
        return None, "命令不能为空。"
    try:
        return subprocess.run(
            arguments,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        ), ""
    except subprocess.TimeoutExpired as error:
        output = _captured_text(error.stdout) + _captured_text(error.stderr)
        return None, f"命令在 {timeout} 秒后超时。\n{output}"
    except OSError as error:
        return None, f"命令无法启动：{error}"


def main() -> int:
    args = parse_args()
    commands = [str(command).strip() for command in args.commands or [] if str(command).strip()]
    if not commands:
        print("至少需要提供一条 --command。", file=sys.stderr)
        return 2
    if args.timeout < 1:
        print("--timeout 必须是正整数。", file=sys.stderr)
        return 2
    if args.max_output < 200:
        print("--max-output 至少为 200。", file=sys.stderr)
        return 2
    cwd = args.cwd.expanduser().resolve()
    if not cwd.is_dir():
        print(f"验证目录不存在：{cwd}", file=sys.stderr)
        return 2

    print("## 当前环境验证")
    print(f"工作目录：`{cwd}`")
    print(f"验证命令数：{len(commands)}")
    failed = False
    for index, command in enumerate(commands, start=1):
        safe_command = redact_sensitive_text(command)
        print(f"\n### 验证 {index}\n")
        print(f"命令：`{safe_command}`")
        if args.dry_run:
            print("结果：仅预演，未执行。")
            continue
        result, error = run_command(command, cwd, args.timeout)
        if result is None:
            failed = True
            print("结果：未完成。")
            print(_safe_output(error, args.max_output))
            continue
        if result.returncode == 0:
            print("结果：通过。")
        else:
            failed = True
            print(f"结果：失败，退出码 {result.returncode}。")
        output = _safe_output((result.stdout or "") + (result.stderr or ""), args.max_output)
        if output.strip():
            print("输出：")
            print(output.rstrip())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
