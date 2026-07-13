#!/usr/bin/env python3
"""Codex hook wrapper: 归档会话，并在用户提问前检索知识库。"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if "--vault-root" in sys.argv:
    idx = sys.argv.index("--vault-root")
    if idx + 1 < len(sys.argv):
        os.environ["OBSIDIAN_VAULT"] = sys.argv[idx + 1]

CODEX_HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "~/obsidian/知识库")).expanduser().resolve()
LOG_PATH = CODEX_HOME / "logs" / "stop-wrapper-debug.jsonl"
CHECKPOINT_HOOK = Path(__file__).with_name("checkpoint.py")
RETRIEVE_HOOK = Path(__file__).with_name("retrieve.py")
KNOWLEDGE_PROJECT_UPDATED = re.compile(
    r"^\[obsidian-hook\] (?:Project knowledge updated|External knowledge project written):",
    re.MULTILINE,
)
CHECKPOINT_WRITTEN = re.compile(
    r"^\[obsidian-hook\]\s+Session checkpoint written:\s+(?P<path>[^\r\n]+)$",
    re.MULTILINE,
)
CHECKPOINT_LOCATION = re.compile(
    r"^\[obsidian-hook\]\s+Session checkpoint location:\s+"
    r"vault-relative=(?P<path>.+?);\s*folder=(?P<folder>[^\r\n]+)$",
    re.MULTILINE,
)
UNCLASSIFIED_CHECKPOINT_DIRECTORY = "Codex工作记录/会话断点/未分类对话"


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


def _merged_hook_output(outputs: list[str], event_name: str) -> str:
    """合并多个 hook 的 JSON 输出，避免向 Codex 输出多行协议内容。"""
    merged = {}
    contexts = []
    system_messages = []
    for output in outputs:
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            _log("invalid_hook_stdout", event_name=event_name, stdout=output[:2000])
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if key == "systemMessage" and isinstance(value, str) and value.strip():
                system_messages.append(value.strip())
            elif key != "hookSpecificOutput":
                merged[key] = value
        specific = data.get("hookSpecificOutput")
        if not isinstance(specific, dict):
            continue
        for key, value in specific.items():
            if key == "additionalContext" and isinstance(value, str) and value.strip():
                contexts.append(value.strip())
            elif key != "hookEventName":
                merged.setdefault("hookSpecificOutput", {})[key] = value

    if not merged and not contexts and not system_messages:
        return ""
    specific = merged.setdefault("hookSpecificOutput", {})
    specific["hookEventName"] = event_name
    if contexts:
        specific["additionalContext"] = "\n\n".join(contexts)
    if system_messages:
        merged["systemMessage"] = "\n".join(system_messages)
    return json.dumps(merged, ensure_ascii=False)


def _checkpoint_written_notice(output: str) -> str:
    """将 hook 的真实写入结果转换成用户可见的定位提示。"""
    written = CHECKPOINT_WRITTEN.search(output or "")
    if not written:
        return ""
    location = CHECKPOINT_LOCATION.search(output or "")
    if location:
        note_path = location.group("path").strip()
        directory = location.group("folder").strip()
    else:
        absolute_path = Path(written.group("path").strip()).expanduser().resolve()
        try:
            note_path = absolute_path.relative_to(VAULT_ROOT).as_posix()
            directory = absolute_path.parent.relative_to(VAULT_ROOT).as_posix() + "/"
        except ValueError:
            note_path = str(absolute_path)
            directory = str(absolute_path.parent) + os.sep
    lines = [
        "本次对话已写入会话断点。",
        f"断点文件：{note_path}",
        f"所在目录：{directory}",
    ]
    normalized_directory = directory.replace("\\", "/").strip().strip("/")
    if normalized_directory == UNCLASSIFIED_CHECKPOINT_DIRECTORY:
        lines.append("当前断点尚未归类。调用 `$checkpoint` 进行归类。")
    return "\n".join(lines)


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

    checkpoint_proc = _run([sys.executable, str(CHECKPOINT_HOOK), *sys.argv[1:]], raw_input, "checkpoint_hook")

    retrieve_proc = None
    if event_name == "UserPromptSubmit":
        retrieve_proc = _run([sys.executable, str(RETRIEVE_HOOK), *sys.argv[1:]], raw_input, "retrieve_hook")

    outputs = []
    if checkpoint_proc and checkpoint_proc.stdout.strip():
        outputs.append(checkpoint_proc.stdout.strip())
    if event_name == "Stop" and checkpoint_proc:
        checkpoint_notice = _checkpoint_written_notice(checkpoint_proc.stdout or "")
        if checkpoint_notice:
            outputs.append(json.dumps({"systemMessage": checkpoint_notice}, ensure_ascii=False))
    if (
        event_name == "Stop"
        and checkpoint_proc
        and KNOWLEDGE_PROJECT_UPDATED.search(checkpoint_proc.stdout or "")
    ):
        outputs.append(json.dumps({"systemMessage": "本次对话项目已加入知识库"}, ensure_ascii=False))
    if retrieve_proc and retrieve_proc.stdout.strip():
        outputs.append(retrieve_proc.stdout.strip())

    merged_output = _merged_hook_output(outputs, event_name)
    if merged_output:
        sys.stdout.write(merged_output + "\n")
    elif outputs:
        _log("suppressed_plain_stdout", event_name=event_name, outputs=outputs)

    rc_candidates = []
    if checkpoint_proc is not None:
        rc_candidates.append(checkpoint_proc.returncode)
    if retrieve_proc is not None:
        rc_candidates.append(retrieve_proc.returncode)
    sys.exit(max(rc_candidates) if rc_candidates else 0)


if __name__ == "__main__":
    main()
