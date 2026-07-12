#!/usr/bin/env python3
"""Codex PreToolUse hook: 写入项目总结/ 时提醒已有文档，避免重复。"""
import json
import os
import sys
from pathlib import Path

if "--vault-root" in sys.argv:
    idx = sys.argv.index("--vault-root")
    if idx + 1 < len(sys.argv):
        os.environ["OBSIDIAN_VAULT"] = sys.argv[idx + 1]

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "~/obsidian/知识库")).expanduser().resolve()
PROJECTS_DIR = VAULT_ROOT / "项目总结"


def extract_paths_from_apply_patch(patch_text: str) -> list:
    paths = []
    for line in (patch_text or "").splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: "):
            if line.startswith(prefix):
                paths.append(line[len(prefix):].strip())
                break
    return paths


def normalize_event(raw: str) -> dict:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
    if isinstance(payload, dict) and payload.get("hook_event_name"):
        return payload
    return event if isinstance(event, dict) else {}


def extract_target_files(tool_name: str, tool_input) -> list:
    name = (tool_name or "").strip()
    if name in ("Write", "Edit") and isinstance(tool_input, dict):
        fp = tool_input.get("file_path", "")
        return [fp] if fp else []
    if name == "apply_patch":
        if isinstance(tool_input, str):
            return extract_paths_from_apply_patch(tool_input)
        if isinstance(tool_input, dict):
            for key in ("patch", "content", "input"):
                value = tool_input.get(key)
                if isinstance(value, str):
                    return extract_paths_from_apply_patch(value)
    return []


def resolve_plan_path(file_path: str):
    if not file_path:
        return None
    try:
        p = Path(str(file_path)).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
    except Exception:
        return None
    try:
        p.relative_to(PROJECTS_DIR)
        return p
    except Exception:
        return None


def main():
    try:
        raw = sys.stdin.read().strip()
    except Exception:
        sys.exit(0)
    if not raw:
        sys.exit(0)

    event = normalize_event(raw)
    if not event:
        sys.exit(0)

    tool_name = event.get("tool_name", "") or event.get("tool", "") or event.get("toolName", "")
    tool_input = event.get("tool_input")
    if tool_input is None:
        tool_input = event.get("toolInput", {})

    target_paths = []
    for fp in extract_target_files(tool_name, tool_input):
        resolved = resolve_plan_path(fp)
        if resolved is not None:
            target_paths.append(resolved)
    if not target_paths:
        sys.exit(0)

    target_dirs = {}
    for path in target_paths:
        target_dirs.setdefault(path.parent, set()).add(path.name)

    reminders = []
    for parent, current_names in target_dirs.items():
        try:
            existing = [
                f for f in os.listdir(parent)
                if f.endswith(".md") and f not in current_names
            ]
        except Exception:
            continue
        if not existing:
            continue
        shown = ", ".join(f"[[{os.path.splitext(f)[0]}]]" for f in existing[:5])
        suffix = " …" if len(existing) > 5 else ""
        reminders.append(
            f"注意：'{parent.name}' 目录已有 {len(existing)} 份文档（{shown}{suffix}），请先确认是否已有相关结论可引用，避免重新推导。"
        )

    if not reminders:
        sys.exit(0)

    out = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "\n".join(reminders),
        }
    }, ensure_ascii=False)
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
