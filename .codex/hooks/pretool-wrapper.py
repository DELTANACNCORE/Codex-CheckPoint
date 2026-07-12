#!/usr/bin/env python3
"""Codex PreToolUse hook wrapper: 调用 Codex 的项目文档检查。"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if "--vault-root" in sys.argv:
    idx = sys.argv.index("--vault-root")
    if idx + 1 < len(sys.argv):
        os.environ["OBSIDIAN_VAULT"] = sys.argv[idx + 1]

CODEX_HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
LOG_PATH = CODEX_HOME / "logs" / "pretool-wrapper-debug.jsonl"
PRETOOL_HOOK = Path(__file__).with_name("pretool.py")


def _log(stage: str, **fields):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "stage": stage,
    }
    entry.update(fields)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _run(cmd: list[str], raw_input: str, name: str):
    try:
        proc = subprocess.run(
            cmd,
            input=raw_input,
            text=True,
            capture_output=True,
            check=False,
        )
        _log(
            f"{name}_done",
            command=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout[:2000],
            stderr=proc.stderr[:2000],
        )
        return proc
    except Exception as exc:
        _log(f"{name}_error", command=cmd, error=repr(exc))
        return None


def main():
    raw_input = sys.stdin.read()
    _log("wrapper_start", argv=sys.argv, raw_stdin_len=len(raw_input), raw_stdin_preview=raw_input[:2000])
    event_name = ""
    try:
        payload = json.loads(raw_input) if raw_input.strip() else {}
        if isinstance(payload, dict):
            event_name = str(payload.get("hook_event_name", "") or "")
    except Exception:
        event_name = ""

    pretool_proc = _run([sys.executable, str(PRETOOL_HOOK), *sys.argv[1:]], raw_input, "pretool_hook")

    outputs = []
    if pretool_proc and pretool_proc.stdout.strip():
        outputs.append(pretool_proc.stdout.strip())

    passthrough_hook_output = any(s.startswith("{") for s in outputs)
    if passthrough_hook_output:
        sys.stdout.write("\n".join(outputs) + "\n")
    elif outputs:
        _log("suppressed_plain_stdout", event_name=event_name, outputs=outputs)

    rc_candidates = []
    if pretool_proc is not None:
        rc_candidates.append(pretool_proc.returncode)
    sys.exit(max(rc_candidates) if rc_candidates else 0)


if __name__ == "__main__":
    main()
