#!/usr/bin/env python3
"""Codex Full checkpoint hook: write one recoverable Obsidian session note."""

import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if "--vault-root" in sys.argv:
    position = sys.argv.index("--vault-root")
    if position + 1 < len(sys.argv):
        os.environ["OBSIDIAN_VAULT"] = sys.argv[position + 1]

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "~/obsidian/知识库")).expanduser().resolve()
CODEX_HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
SESSIONS_DIR = CODEX_HOME / "sessions"
SESSION_INDEX = CODEX_HOME / "session_index.jsonl"
WORK_DIR = VAULT_ROOT / "Codex工作记录"
NOTES_DIR = WORK_DIR / "会话断点"
INDEX_DIR = WORK_DIR / "会话索引"
PROJECTS_DIR = VAULT_ROOT / "项目总结"
HOMEPAGE = VAULT_ROOT / "知识库首页.md"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(TIMEZONE)


def session_id_from_path(path: str) -> str:
    matched = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", Path(path).stem)
    return matched.group(1) if matched else Path(path).stem


def latest_rollout(session_id: str = "") -> str:
    if not SESSIONS_DIR.is_dir():
        return ""
    pattern = str(SESSIONS_DIR / "**" / (f"rollout-*{session_id}.jsonl" if session_id else "rollout-*.jsonl"))
    files = [Path(item) for item in glob.glob(pattern, recursive=True)]
    return str(max(files, key=lambda item: item.stat().st_mtime)) if files else ""


def thread_title(session_id: str) -> str:
    if not session_id or not SESSION_INDEX.is_file():
        return ""
    title = ""
    try:
        for line in SESSION_INDEX.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("id") == session_id:
                candidate = str(item.get("thread_name", "")).strip()
                if candidate and "\n" not in candidate:
                    title = candidate
    except (OSError, json.JSONDecodeError):
        return ""
    return title[:80]


def clean_text(text: str, limit: int = 1400) -> str:
    text = re.sub(r"<appshot\b[\s\S]*?</appshot>", "", str(text or ""), flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit].rstrip()


def patch_paths(text: str) -> list[str]:
    paths = []
    for line in str(text or "").splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: "):
            if line.startswith(prefix):
                paths.append(line[len(prefix):].strip())
    return paths


def add_message(messages: list[str], value: str) -> None:
    text = clean_text(value, 600)
    if text and text not in messages:
        messages.append(text)


def parse_rollout(path: str) -> dict:
    context = {"users": [], "assistants": [], "writes": set(), "projects": set()}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return context
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_type = entry.get("type", "")
        payload = entry.get("payload", {}) if isinstance(entry.get("payload"), dict) else {}
        if entry_type == "response_item" and payload.get("type") == "message":
            content = payload.get("content", [])
            if not isinstance(content, list):
                continue
            target = context["users"] if payload.get("role") == "user" else context["assistants"]
            for block in content:
                if isinstance(block, dict):
                    add_message(target, block.get("text") or block.get("input_text") or block.get("output_text") or "")
        elif entry_type == "event_msg":
            if payload.get("type") == "user_message":
                add_message(context["users"], payload.get("message", ""))
            elif payload.get("type") == "agent_message":
                add_message(context["assistants"], payload.get("message", ""))
            elif payload.get("type") == "patch_apply_end":
                for name in (payload.get("changes") or {}):
                    context["writes"].add(str(name))
        elif entry_type == "custom_tool_call":
            tool_name = payload.get("name", "")
            tool_input = payload.get("input", "")
            if tool_name == "apply_patch":
                context["writes"].update(patch_paths(tool_input))
        elif entry_type == "function_call":
            arguments = payload.get("arguments", "")
            try:
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            except json.JSONDecodeError:
                pass
            if isinstance(arguments, dict) and arguments.get("file_path"):
                context["writes"].add(str(arguments["file_path"]))
    for path in context["writes"]:
        try:
            relative = Path(path).expanduser().resolve().relative_to(PROJECTS_DIR)
        except (OSError, ValueError):
            continue
        if len(relative.parts) >= 2 and Path(path).suffix.lower() == ".md":
            context["projects"].add(relative.parts[0])
    return context


def infer_topic(title: str, prompts: list[str]) -> str:
    if title:
        return title
    candidates = [item for item in prompts if len(item) >= 4 and not item.startswith(("/", "# AGENTS", "<"))]
    return (candidates[-1] if candidates else "未命名 Codex 会话")[:80]


def session_status(context: dict) -> tuple[str, str]:
    text = "\n".join(context["assistants"][-3:]).lower()
    if re.search(r"已完成|完成了|验证通过|修复完成|done|completed|verified", text):
        return "completed", "✅ 已完成 / Completed"
    if context["assistants"] or context["writes"]:
        return "interrupted", "⚠️ 待续接 / Needs continuation"
    return "completed", "✅ 已完成 / Completed"


def note_path_for(session_id: str, date: datetime) -> Path:
    for path in NOTES_DIR.rglob("*.md") if NOTES_DIR.is_dir() else []:
        if f'session_id: "{session_id}"' in path.read_text(encoding="utf-8", errors="ignore"):
            return path
    return NOTES_DIR / date.strftime("%Y/%m/%d") / f"{sanitize(session_id)}.md"


def sanitize(value: str) -> str:
    value = re.sub(r'[/\\:*?"<>|\r\n\t]', "_", value).strip().strip(".")
    return value[:80] or "未命名"


def wikilink(path: Path) -> str:
    try:
        return f"[[{path.relative_to(VAULT_ROOT).with_suffix('').as_posix()}|{path.stem}]]"
    except ValueError:
        return f"[[{path.stem}]]"


def write_note(session_id: str, topic: str, context: dict, status: str, label: str, date: datetime) -> Path:
    path = note_path_for(session_id, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    conclusions = context["assistants"][-2:]
    conclusion_text = "\n\n".join(conclusions) if conclusions else "（未提取到可续接的助手结论 / No assistant conclusion was extracted.）"
    outputs = []
    for item in sorted(context["writes"]):
        candidate = Path(item).expanduser()
        if candidate.is_file():
            outputs.append(f"- {wikilink(candidate.resolve())}")
    project_lines = "、".join(sorted(context["projects"])) or "无 / None"
    content = f'''---
date: "{date:%Y-%m-%d}"
session_id: "{session_id}"
status: "{status}"
platform: "codex"
projects: {json.dumps(sorted(context["projects"]), ensure_ascii=False)}
---

# {topic}

> {label} · {date:%Y-%m-%d %H:%M UTC+8}

**会话 ID / Session ID**: `{session_id}`

**涉及项目 / Projects**: {project_lines}

## 可直接续接的结论 / Continuation Brief

{conclusion_text}

## 最近目标 / Recent Goals

{chr(10).join(f'- {item}' for item in context["users"][-3:]) or '（无 / None）'}

## 实际产出 / Outputs

{chr(10).join(outputs) or '（无 / None）'}

## 恢复 / Resume

回到 Codex 线程列表并打开 thread ID `{session_id}`。

Return to the Codex thread list and open thread ID `{session_id}`.
'''
    path.write_text(content, encoding="utf-8")
    return path


def update_index(path: Path, note: Path, topic: str, label: str, date: datetime) -> None:
    path.mkdir(parents=True, exist_ok=True)
    index = path / f"{date:%Y-%m-%d}.md"
    row = f"| {date:%H:%M} | {label} | {wikilink(note)} | {topic} |"
    header = f"# 会话记录 / Session Index - {date:%Y-%m-%d}\n\n| 时间 / Time | 状态 / Status | 断点 / Checkpoint | 主题 / Topic |\n|---|---|---|---|\n"
    lines = index.read_text(encoding="utf-8").splitlines() if index.is_file() else header.splitlines()
    lines = [line for line in lines if f'session_id: "{note.stem}"' not in line and wikilink(note) not in line]
    lines.append(row)
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_project_summaries(projects: set[str], note: Path, topic: str, date: datetime) -> None:
    for project in projects:
        directory = PROJECTS_DIR / project
        if not directory.is_dir():
            continue
        summary = directory / "项目总结.md"
        summary.write_text(
            f"# {project} 项目总结 / Project Summary\n\n"
            f"**最近更新 / Last updated**: {date:%Y-%m-%d %H:%M UTC+8}\n\n"
            f"**最近会话 / Latest session**: {wikilink(note)}\n\n"
            f"**当前主题 / Current topic**: {topic}\n",
            encoding="utf-8",
        )


def update_homepage() -> None:
    notes = sorted(NOTES_DIR.rglob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True) if NOTES_DIR.is_dir() else []
    entries = [f"- {wikilink(path)}" for path in notes[:10]]
    HOMEPAGE.write_text(
        "# 知识库首页 / Knowledge Base Home\n\n"
        "> Codex 会话断点、项目总结与恢复入口。 / Codex checkpoints, project summaries, and recovery entry points.\n\n"
        "## 最近断点 / Recent Checkpoints\n\n"
        + ("\n".join(entries) if entries else "暂无断点 / No checkpoints yet.")
        + "\n",
        encoding="utf-8",
    )


def parse_input() -> tuple[str, str]:
    transcript = ""
    session_id = ""
    if "--transcript" in sys.argv:
        position = sys.argv.index("--transcript")
        transcript = sys.argv[position + 1] if position + 1 < len(sys.argv) else ""
    if "--session-id" in sys.argv:
        position = sys.argv.index("--session-id")
        session_id = sys.argv[position + 1] if position + 1 < len(sys.argv) else ""
    if transcript:
        return transcript, session_id or session_id_from_path(transcript)
    raw = sys.stdin.read().strip()
    if raw:
        try:
            event = json.loads(raw)
            payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
            transcript = event.get("rollout_path") or event.get("transcript_path") or payload.get("rollout_path") or payload.get("transcript_path") or ""
            session_id = event.get("thread_id") or event.get("session_id") or payload.get("thread_id") or payload.get("session_id") or ""
        except json.JSONDecodeError:
            pass
    if not transcript:
        transcript = latest_rollout(session_id)
    return transcript, session_id or session_id_from_path(transcript)


def main() -> None:
    transcript, session_id = parse_input()
    if not transcript or not Path(transcript).is_file():
        print("[checkpoint] No Codex rollout found; skipped.")
        return
    if not VAULT_ROOT.is_dir():
        print(f"[checkpoint] Vault not accessible: {VAULT_ROOT}; skipped.")
        return
    date = now()
    context = parse_rollout(transcript)
    topic = infer_topic(thread_title(session_id), context["users"])
    status, label = session_status(context)
    note = write_note(session_id, topic, context, status, label, date)
    update_index(INDEX_DIR, note, topic, label, date)
    update_project_summaries(context["projects"], note, topic, date)
    update_homepage()
    print(f"[checkpoint] Written: {note}")


if __name__ == "__main__":
    main()
