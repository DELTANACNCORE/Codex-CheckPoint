#!/usr/bin/env python3
"""
Checkpoint hook: 会话断点写入 Obsidian。
"""

import json
import sys
import os
import re
import glob
import shlex
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# 允许在 import 阶段前通过 CLI 覆盖 vault 路径，方便 Codex hook 直接传参。
if "--vault-root" in sys.argv:
    idx = sys.argv.index("--vault-root")
    if idx + 1 < len(sys.argv):
        os.environ["OBSIDIAN_VAULT"] = sys.argv[idx + 1]

# Windows 默认 stdout/stderr 是 GBK(cp936)，输出 ✓/⚠️/📋/中文会 UnicodeEncodeError。强制 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "~/obsidian/知识库")).expanduser().resolve()
CODEX_HOME = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve()
CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"
CODEX_SESSION_INDEX = CODEX_HOME / "session_index.jsonl"
SPACE_NAME = "Codex工作记录"
HOMEPAGE_NAME = "知识库首页.md"
INDEX_TAG = "codex/会话索引"
PLAN_TAG = "codex/方案"
PRODUCT_LABEL = "Codex"
PLANS_DIR = VAULT_ROOT / SPACE_NAME
PLANS_DIR_STR = str(PLANS_DIR)
INDEX_DIR = PLANS_DIR / "会话索引"       # 每日索引 YYYY-MM-DD.md
NOTE_DIR = PLANS_DIR / "会话断点"         # 单条会话断点 <主题>.md（与会话索引分开）
EXPERIENCE_DIR = PLANS_DIR / "可复用经验"  # 跨项目复用的经验摘要
PROJECTS_DIR = PLANS_DIR
PROJECT_SUMMARY_NAME = "项目总结.md"      # 每个项目目录内的滚动项目摘要
PROJECT_EXPERIENCE_SUFFIX = "长期经验总结.md"
PROJECT_SUMMARY_MAX_CHARS = 18000
AUTO_CHECKPOINT_MIN_ROUNDS = 5
VAULT_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEBUG_LOG_PATH = Path(
    os.environ.get(
        "CHECKPOINT_DEBUG_LOG",
        str(CODEX_HOME / "logs" / "checkpoint-hook-debug.jsonl"),
    )
).expanduser()

# 强信号：明确指向“已形成方案/决策”的短语，命中 1 个即足以判定。
STRONG_PLAN_PATTERNS = [
    "方案如下", "方案是", "设计方案", "方案设计",
    "推荐方案", "最优方案", "备选方案", "技术方案",
    "架构设计", "架构如下", "系统架构",
    "实现计划", "实施步骤", "实现思路",
    "关键决策", "技术选型", "技术决策",
    "here is the plan", "here's the plan",
    "architecture design", "design decision",
    "implementation plan", "proposed solution",
    "这个方案", "按这个方案", "方案确认", "方案定了",
    "就这么设计", "最终方案", "敲定",
]
# 弱信号：日常讨论也常出现的词，需 ≥2 个不同词同时命中才算。
WEAK_PLAN_PATTERNS = [
    "背景", "核心思路", "取舍",
    "按这个来", "确定用", "定了",
]

CONCLUSION_MARKERS = [
    "全部完成", "以上就是", "总结一下", "没有问题的话",
    "有什么问题随时", "随时问我", "任务完成", "已全部",
    "没有其他问题", "overview",
]

STATUS_MAP = {
    "completed":          {"label": "正常结束", "emoji": "✅"},
    "interrupted":        {"label": "会话中断", "emoji": "⚠️"},
    "incomplete_archive": {"label": "方案未归档", "emoji": "📋"},
    "archived":           {"label": "已知识归档", "emoji": "📚"},
    "indexed_only":       {"label": "仅记录会话", "emoji": "📝"},
}


def _debug_value(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _debug_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_debug_value(v) for v in value]
    return value


def _debug_log(stage: str, **fields):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        "stage": stage,
    }
    for key, value in fields.items():
        entry[key] = _debug_value(value)
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def vault_now() -> datetime:
    """返回知识库展示和归档使用的中国标准时间。"""
    return datetime.now(VAULT_TIMEZONE)


PLANS_DIR = VAULT_ROOT / SPACE_NAME
PLANS_DIR_STR = str(PLANS_DIR)
INDEX_DIR = PLANS_DIR / "会话索引"
NOTE_DIR = PLANS_DIR / "会话断点"
EXPERIENCE_DIR = VAULT_ROOT / "长期经验总结"
PROJECTS_DIR = VAULT_ROOT / "项目总结"


def _session_id_from_transcript_path(transcript_path: str) -> str:
    stem = Path(transcript_path).stem
    m = re.search(r"(?:rollout-[^-]+(?:-[^-]+)*-|)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", stem)
    if m:
        return m.group(1)
    return stem


def _find_codex_rollout_by_session(session_id: str) -> str:
    if not session_id or not CODEX_SESSIONS_DIR.is_dir():
        return ""
    pattern = str(CODEX_SESSIONS_DIR / "**" / f"rollout-*{session_id}.jsonl")
    candidates = [Path(p) for p in glob.glob(pattern, recursive=True)]
    if not candidates:
        return ""
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return str(latest)


def _find_latest_codex_rollout() -> str:
    if not CODEX_SESSIONS_DIR.is_dir():
        return ""
    candidates = list(CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"))
    if not candidates:
        return ""
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return str(latest)


def _codex_thread_title(session_id: str) -> str:
    """读取 Codex 桌面端维护的线程标题。"""
    if not session_id or not CODEX_SESSION_INDEX.is_file():
        return ""
    latest_title = ""
    try:
        with open(CODEX_SESSION_INDEX, "r", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("id") != session_id:
                    continue
                title = str(entry.get("thread_name", "")).strip()
                if title and "\n" not in title and "\r" not in title:
                    latest_title = title[:80]
    except (OSError, json.JSONDecodeError):
        pass
    return latest_title


def _add_written_file(result: dict, file_path: str, plans_dir: Path = None, plans_dir_str: str = "", project_root: Path = None):
    if not file_path:
        return
    plans_dir = plans_dir or PLANS_DIR
    plans_dir_str = plans_dir_str or str(plans_dir)
    project_root = project_root or PROJECTS_DIR
    try:
        abs_path = str(Path(file_path).expanduser().resolve())
    except Exception:
        abs_path = file_path
    result["all_writes"].add(abs_path)
    if plans_dir_str in abs_path:
        try:
            rel = Path(abs_path).relative_to(plans_dir)
            if len(rel.parts) > 1 and rel.parts[0] not in ("会话索引", "会话断点", "可复用经验", "长期经验总结"):
                result["written_files"].add(abs_path)
        except Exception:
            result["written_files"].add(abs_path)
        return

    try:
        path = Path(abs_path)
        rel = path.relative_to(project_root)
        if len(rel.parts) >= 2 and path.suffix.lower() == ".md":
            result["written_files"].add(abs_path)
            result["projects"].add(rel.parent.as_posix())
            return
    except Exception:
        pass

    # Vault 根目录下按“分类/项目/文档”组织的项目由用户或其他会话维护。
    # 它们应进入索引和检索，但不能由 Codex方案 的自动摘要逻辑覆盖。
    try:
        path = Path(abs_path)
        rel = path.relative_to(VAULT_ROOT)
        if (
            len(rel.parts) >= 3
            # Codex 自动生成的目录不应视为用户维护的外部项目。
            and "Codex方案" not in rel.parts
            and "Codex工作记录" not in rel.parts
            and "项目总结" not in rel.parts
            and "长期经验总结" not in rel.parts
            and rel.parts[0] != ".obsidian"
            and path.suffix.lower() == ".md"
        ):
            result["external_written_files"].add(abs_path)
            result["external_projects"].add("/".join(rel.parts[:2]))
    except Exception:
        pass


def _extract_paths_from_apply_patch(patch_text: str) -> list:
    paths = []
    for line in (patch_text or "").splitlines():
        for prefix in ("*** Add File: ", "*** Update File: ", "*** Delete File: "):
            if line.startswith(prefix):
                paths.append(line[len(prefix):].strip())
                break
    return paths


def _extract_paths_from_exec_command(cmd_text: str) -> list:
    if not isinstance(cmd_text, str) or not cmd_text.strip():
        return []
    # Codex Desktop 的 custom_tool_call 会把 shell 命令包在 JavaScript 中。
    # 先取出 JSON 里的 cmd 字符串，再按正常 shell 命令解析。
    embedded = re.search(r'"cmd"\s*:\s*"((?:\\.|[^"\\])*)"', cmd_text)
    if embedded:
        try:
            cmd_text = json.loads(f'"{embedded.group(1)}"')
        except json.JSONDecodeError:
            pass
    try:
        tokens = shlex.split(cmd_text)
    except ValueError:
        return []
    if not tokens:
        return []
    write_cmds = {"cp", "mv", "install", "tee", "touch"}
    paths = []
    for idx, token in enumerate(tokens):
        base = os.path.basename(token)
        if base not in write_cmds:
            continue
        tail = tokens[idx + 1 :]
        if base in {"cp", "mv", "install"}:
            candidates = [t for t in tail if not t.startswith("-") and not re.match(r"^(?:&&|\|\||;|\|)$", t)]
            if len(candidates) >= 2:
                paths.append(candidates[-1])
        elif base == "tee":
            candidates = [t for t in tail if not t.startswith("-") and not re.match(r"^(?:&&|\|\||;|\|)$", t)]
            if candidates:
                paths.extend(candidates)
        elif base == "touch":
            candidates = [t for t in tail if not t.startswith("-") and not re.match(r"^(?:&&|\|\||;|\|)$", t)]
            paths.extend(candidates)
    return paths


def _extract_written_paths_from_output(output_text: str) -> list:
    if not isinstance(output_text, str) or not output_text.strip():
        return []
    paths = []
    patterns = (
        r"(?m)^\[obsidian-hook\]\s+Session checkpoint written:\s+([^\r\n]+)$",
        r"(?m)^\[obsidian-hook\]\s+Project knowledge updated:\s+([^\r\n]+)$",
        r"(?m)^文档路径:\s+([^\r\n]+)$",
    )
    for pattern in patterns:
        for m in re.finditer(pattern, output_text):
            matched = m.group(1).strip()
            for part in re.split(r"\s*,\s*", matched):
                cleaned = part.strip().strip('"').strip("'")
                if cleaned:
                    paths.append(cleaned)
    return paths


def _normalize_user_message(text: str) -> str:
    if not isinstance(text, str):
        return ""
    msg = text.strip()
    if not msg:
        return ""
    if "<codex_delegation>" in msg and "</codex_delegation>" in msg:
        m = re.search(r"<input>([\s\S]*?)</input>", msg)
        if m:
            inner = m.group(1).strip()
            if inner:
                return inner
    return msg


LOW_SIGNAL_TOPIC_PATTERNS = (
    r"^(?:重新开始|继续|好的|可以|行|开始|完成)[。！!？? ]*$",
    r"^(?:我(?:已经)?(?:信任|给你权限)|需要别的权限|现在可用了吗|这个对话能用吗)[。！!？? ]*$",
    r"^(?:为什么只有一条|为啥没有|如何验证|怎么验证|那就先做第一步)[。！!？? ]*$",
    r"^(?:请执行|请只回复|你先(?:尝试|模拟)|我手动删除了).{0,48}$",
)


def _format_project_topic(project: str) -> str:
    """把项目目录名转换为可读的会话主题。"""
    topic = re.sub(r"[_-]+", " ", (project or "").strip())
    topic = re.sub(r"(?i)checkpoint", "checkpoint", topic)
    topic = re.sub(r"(?i)codex", "Codex", topic)
    topic = re.sub(r"(?<=[A-Za-z])(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])(?=[A-Za-z])", " ", topic)
    topic = re.sub(r"\s+", " ", topic).strip()
    return topic[:60]


def _is_low_signal_topic(topic: str) -> bool:
    normalized = re.sub(r"\s+", "", (topic or "").strip().lower())
    if not normalized:
        return True
    return any(re.match(pattern, normalized, re.IGNORECASE) for pattern in LOW_SIGNAL_TOPIC_PATTERNS)


def infer_session_topic(user_prompts, projects=None) -> str:
    """在额外 LLM 不可用时，从项目主线和连续提问推断会话标题。"""
    project_names = sorted({str(p).strip() for p in (projects or []) if str(p).strip()})
    if len(project_names) == 1:
        return _format_project_topic(project_names[0])

    prompts = [re.sub(r"\s+", " ", str(p)).strip() for p in (user_prompts or []) if str(p).strip()]
    corpus = "\n".join(prompts).lower()
    if "checkpoint" in corpus and any(token in corpus for token in ("迁到codex", "迁移到codex", "移植到codex", "迁到 codex", "迁移到 codex", "移植到 codex")):
        return "checkpoint 迁到 Codex"
    if "checkpoint" in corpus and "obsidian" in corpus:
        return "checkpoint 接入 Obsidian"

    candidates = [p for p in prompts if not _is_low_signal_topic(p) and len(p) <= 120]
    if candidates:
        # 选择在全程对话中关键词重合最多的提问，避免机械采用最后一句确认语。
        token_counts = {}
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", corpus):
            token_counts[token] = token_counts.get(token, 0) + 1
        scored = []
        for index, candidate in enumerate(candidates):
            tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", candidate.lower())
            score = sum(min(token_counts.get(token, 0), 4) for token in set(tokens))
            score += index * 0.2
            scored.append((score, candidate))
        topic = max(scored, key=lambda item: item[0])[1]
        # 对话轮次不是主题本身，避免标题退化为“第 X 轮讨论”。
        topic = re.sub(r"第[一二三四五六七八九十0-9]+(?:次|轮)(?:讨论|提问)?", "", topic)
        topic = re.sub(r"\s+", " ", topic).strip(" ，。；;：:")
        return topic[:60]
    return ""


def _strip_noise_blocks(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = text.strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"<appshot\b[\s\S]*?</appshot>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^# Applications mentioned by the user:\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^## My request for Codex:\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^Window:.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_session_context(transcript_path: str) -> dict:
    transcript_path = str(transcript_path) if transcript_path is not None else ""
    plans_dir = PLANS_DIR
    plans_dir_str = PLANS_DIR_STR
    project_root = PROJECTS_DIR
    result = {
        "topic": "", "category": [], "tags": [], "keywords": [],
        "user_prompts": [], "written_files": set(), "external_written_files": set(), "all_writes": set(),
        "projects": set(), "external_projects": set(), "last_was_conclusion": False,
        "has_substantive_work": False, "verbal_plan_detected": False,
        "verbal_plan_snippets": [], "used_plan_mode": False,
        "assistant_count": 0, "latest_assistant_update": "", "assistant_updates": [],
        "platform": "codex",
        "thread_title": _codex_thread_title(_session_id_from_transcript_path(transcript_path)),
    }
    if not transcript_path or not os.path.exists(transcript_path):
        return result

    user_messages = []
    assistant_count = 0
    all_assistant_parts = []

    def add_user_message(text: str):
        msg = _strip_noise_blocks(_normalize_user_message(text))
        if msg:
            user_messages.append(msg)

    def add_assistant_text(text: str):
        if not isinstance(text, str) or not text.strip():
            return
        assistant_count_local = len(all_assistant_parts)
        _ = assistant_count_local
        all_assistant_parts.append(text)
        if len(text) > 50:
            result["has_substantive_work"] = True

    def add_tool_use(tool_name: str, tool_input=None):
        if not tool_name:
            return
        result["has_substantive_work"] = True
        if tool_name in ("EnterPlanMode", "ExitPlanMode", "request_user_input"):
            result["used_plan_mode"] = True
        if tool_name in ("Write", "Edit"):
            tool_input = tool_input or {}
            _add_written_file(result, tool_input.get("file_path", ""), plans_dir, plans_dir_str, project_root)
        if tool_name == "apply_patch":
            if isinstance(tool_input, str):
                for path in _extract_paths_from_apply_patch(tool_input):
                    _add_written_file(result, path, plans_dir, plans_dir_str, project_root)

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_type = entry.get("type", "")
                if entry_type == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    add_user_message(content)
                if entry_type == "assistant":
                    assistant_count += 1
                    msg = entry.get("message", {})
                    content = msg.get("content", [])
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if block.get("type") == "text":
                            add_assistant_text(block.get("text", ""))
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            add_tool_use(tool_name, block.get("input", {}))
                if entry_type == "response_item":
                    payload = entry.get("payload", {})
                    payload_type = payload.get("type", "")
                    if payload_type == "message":
                        role = payload.get("role", "")
                        content = payload.get("content", [])
                        if not isinstance(content, list):
                            continue
                        if role == "user":
                            for block in content:
                                add_user_message(block.get("text") or block.get("input_text") or block.get("output_text") or "")
                        elif role == "assistant":
                            assistant_count += 1
                            for block in content:
                                add_assistant_text(block.get("text") or block.get("output_text") or block.get("input_text") or "")
                    elif payload_type == "function_call":
                        tool_name = payload.get("name", "")
                        raw_args = payload.get("arguments", "")
                        tool_input = raw_args
                        if isinstance(raw_args, str):
                            try:
                                tool_input = json.loads(raw_args)
                            except json.JSONDecodeError:
                                tool_input = raw_args
                        add_tool_use(tool_name, tool_input)
                        if isinstance(tool_input, dict):
                            _add_written_file(result, tool_input.get("file_path", ""), plans_dir, plans_dir_str, project_root)
                            if tool_name == "exec_command":
                                for path in _extract_paths_from_exec_command(tool_input.get("cmd", "")):
                                    _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                    elif payload_type == "function_call_output":
                        output = payload.get("output", "")
                        if isinstance(output, (dict, list)):
                            try:
                                output = json.dumps(output, ensure_ascii=False)
                            except Exception:
                                output = str(output)
                        if isinstance(output, str) and "Updated the following files:" in output:
                            for out_line in output.splitlines():
                                m = re.match(r"^[AMDR]\s+(.+)$", out_line.strip())
                                if m:
                                    _add_written_file(result, m.group(1).strip(), plans_dir, plans_dir_str, project_root)
                        if isinstance(output, str):
                            for path in _extract_written_paths_from_output(output):
                                _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                    elif payload_type == "custom_tool_call":
                        tool_name = payload.get("name", "")
                        tool_input = payload.get("input", "")
                        add_tool_use(tool_name, tool_input)
                        if tool_name == "apply_patch" and isinstance(tool_input, str):
                            for path in _extract_paths_from_apply_patch(tool_input):
                                _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                        elif tool_name == "exec" and isinstance(tool_input, str):
                            for path in _extract_paths_from_apply_patch(tool_input):
                                _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                            for path in _extract_paths_from_exec_command(tool_input):
                                _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                    elif payload_type == "custom_tool_call_output":
                        output = payload.get("output", "")
                        if isinstance(output, str):
                            for path in _extract_written_paths_from_output(output):
                                _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                if entry_type == "custom_tool_call":
                    payload = entry.get("payload", {})
                    tool_name = payload.get("name", "")
                    tool_input = payload.get("input", "")
                    add_tool_use(tool_name, tool_input)
                    if tool_name == "apply_patch" and isinstance(tool_input, str):
                        for path in _extract_paths_from_apply_patch(tool_input):
                            _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                    elif tool_name == "exec" and isinstance(tool_input, str):
                        for path in _extract_paths_from_apply_patch(tool_input):
                            _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                        for path in _extract_paths_from_exec_command(tool_input):
                            _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                if entry_type == "custom_tool_call_output":
                    payload = entry.get("payload", {})
                    output = payload.get("output", "")
                    if isinstance(output, str):
                        for path in _extract_written_paths_from_output(output):
                            _add_written_file(result, path, plans_dir, plans_dir_str, project_root)
                if entry_type == "event_msg":
                    payload = entry.get("payload", {})
                    event_name = payload.get("type", "")
                    if event_name == "user_message":
                        add_user_message(payload.get("message", ""))
                    elif event_name == "agent_message":
                        add_assistant_text(payload.get("message", ""))
                    elif event_name == "turn_context":
                        if payload.get("collaboration_mode", {}).get("mode") == "plan":
                            result["used_plan_mode"] = True
                    elif event_name == "patch_apply_end":
                        changes = payload.get("changes", {})
                        if isinstance(changes, dict):
                            for path in changes:
                                _add_written_file(result, path, plans_dir, plans_dir_str, project_root)

        def is_real_prompt(msg: str) -> bool:
            # 跳过 slash 命令、skill 注入内容和过短的指令式消息。
            msg = (msg or "").strip()
            if not msg:
                return False
            if msg.startswith("/"):
                return False
            if msg.startswith("<codex_internal_context"):
                return False
            if msg.startswith("# AGENTS.md instructions"):
                return False
            if msg.startswith("# Files mentioned by the user:"):
                return False
            if msg.startswith("<environment_context>"):
                return False
            if msg.startswith("<permissions instructions>"):
                return False
            if msg.startswith("<codex_delegation>"):
                return False
            if msg.startswith("# Applications mentioned by the user:"):
                return False
            if msg.startswith("## My request for Codex:"):
                return False
            if "<appshot" in msg:
                return False
            if msg.startswith("Window:"):
                return False
            if re.match(r"^<[^>]+>\s*[\s\S]*</[^>]+>$", msg):
                return False
            # transcript 注入的系统消息（含各类 XML 标签）
            for tag in (
                "<command-name>", "<command-message>", "<command-args>",
                "<local-command-stdout>", "<local-command-caveat>",
                "<task-notification>", "<task-id>", "<system-reminder>",
                "<tool-use-id>", "<output-file>",
            ):
                if tag in msg:
                    return False
            if "Base directory for this skill" in msg:
                return False
            return len(msg) >= 4

        def is_good_topic_candidate(msg: str) -> bool:
            """排除含表格/代码/管道符的提问，选适合做主题的自然语言。"""
            if "─" in msg or "│" in msg or "└" in msg or "┌" in msg or "├" in msg:
                return False
            if "```" in msg or "|" in msg:
                return False
            return len(msg) <= 300

        real_prompts = []
        for m in user_messages:
            if not is_real_prompt(m):
                continue
            norm = m.strip()
            # Codex 同一条消息会同时出现在 response_item 和 event_msg；只去掉相邻副本。
            if real_prompts and norm == real_prompts[-1]:
                continue
            real_prompts.append(norm)
        # 话题从自然语言提问中取（排除表格/代码块）
        topic_candidates = [m for m in real_prompts if is_good_topic_candidate(m)]
        if topic_candidates:
            result["topic"] = topic_candidates[-1][:200].replace("\n", " ").replace("\r", " ").strip()
        elif real_prompts:
            result["topic"] = real_prompts[-1][:200].replace("\n", " ").replace("\r", " ").strip()
        elif user_messages:
            result["topic"] = user_messages[0][:200].replace("\n", " ").replace("\r", " ").strip()
        result["user_prompts"] = [m[:200] for m in real_prompts]
        for text in reversed(all_assistant_parts):
            update = _strip_noise_blocks(text)
            if len(update) >= 40:
                result["latest_assistant_update"] = update[:1600].rstrip()
                break
        result["assistant_updates"] = [
            _strip_noise_blocks(text).strip()
            for text in all_assistant_parts
            if len(_strip_noise_blocks(text).strip()) >= 40
        ][-8:]

        all_assistant_text = "".join(all_assistant_parts)
        all_text_lower = all_assistant_text.lower()
        covered_ranges = []

        def collect_hits(patterns):
            hits = []
            for pattern in patterns:
                idx = all_text_lower.find(pattern)
                if idx < 0:
                    continue
                if any(s <= idx <= e for s, e in covered_ranges):
                    continue
                covered_ranges.append((idx, idx + len(pattern)))
                start = max(0, idx - 40)
                end = min(len(all_assistant_text), idx + len(pattern) + 40)
                snippet = all_assistant_text[start:end].replace("\n", " ").strip()
                hits.append(f"...{snippet}...")
            return hits

        strong_hits = collect_hits(STRONG_PLAN_PATTERNS)
        weak_hits = collect_hits(WEAK_PLAN_PATTERNS)
        # 强信号命中 1 个即判定；弱信号需 ≥2 个不同词同时命中。
        if strong_hits or len(weak_hits) >= 2:
            result["verbal_plan_detected"] = True
            result["verbal_plan_snippets"] = (strong_hits + weak_hits)[:3]

        for f in result["written_files"]:
            try:
                rel = Path(f).relative_to(project_root)
                if len(rel.parts) > 1:
                    result["projects"].add(rel.parent.as_posix())
            except Exception:
                pass

        inferred_topic = infer_session_topic(real_prompts, result["projects"])
        if inferred_topic:
            result["topic"] = inferred_topic

        tail_text = all_assistant_text[-2000:].lower()
        result["last_was_conclusion"] = any(m in tail_text for m in CONCLUSION_MARKERS)
        result["assistant_count"] = assistant_count

    except (json.JSONDecodeError, OSError) as e:
        print(f"[obsidian-hook] Warning: transcript parsing error: {e}", file=sys.stderr)

    return result


def determine_session_status(ctx: dict) -> str:
    knowledge_writes = set(ctx.get("written_files", [])) | set(ctx.get("external_written_files", []))
    has_writes = len(knowledge_writes) > 0
    has_substance = ctx["has_substantive_work"]
    has_conclusion = ctx["last_was_conclusion"]
    plan_discussed = ctx["verbal_plan_detected"] or ctx["used_plan_mode"]
    # 改了代码（非方案目录的 Write/Edit）但没归档：可能没干完
    has_code_edits = len(ctx["all_writes"] - knowledge_writes) > 0
    # 讨论了方案但没归档 → 提醒补写
    if plan_discussed and not has_writes:
        return "incomplete_archive"
    # 有归档 / 有收尾语 / 纯问答(无方案讨论且无代码改动) / 无实质工作 → 正常结束
    if has_writes or has_conclusion or not has_substance or (not plan_discussed and not has_code_edits):
        return "completed"
    return "interrupted"


def synthesize_topic_and_tags(user_prompts, written_files=None, projects=None):
    """一次 LLM 调用，返回 {'topic': str|None, 'category': list, 'tags': list, 'keywords': list}。

    category = 1-2 个大类（宽泛领域），tags = 2-4 个小类（具体技术/场景）。
    """
    written_files = written_files or []
    projects = projects or []
    if not user_prompts and not written_files:
        return {"topic": None, "category": [], "tags": [], "keywords": []}
    project_topic = infer_session_topic(user_prompts, projects)
    tags, keywords = _fallback_tags_from_files(written_files or [])
    return {"topic": project_topic or None, "category": [], "tags": tags, "keywords": keywords}



def _fallback_tags_from_files(files):
    """LLM 失败时，从写/改的文件路径中提取标签和关键词。"""
    SKIP = {"", "~", "home", "user", "users", "projects", "src", "code", "dev",
            "desktop", "documents", "downloads", "tmp", "var", "opt", "etc", "usr",
            "library", "applications", "hooks", "skills", "memory",
            "checkpoint-convention", "readme-update-rule", "settings"}
    tags, keywords = [], []
    seen = set()
    for f in sorted(files):
        for p in Path(f).parts:
            p_clean = p.strip().lower()
            base = p_clean.split(".")[0]  # 去扩展名
            if not base or base in SKIP or base.startswith(".") or base.startswith("-"):
                continue
            if base not in seen:
                seen.add(base)
                if len(tags) < 5:
                    tags.append(base)
                elif len(keywords) < 3:
                    keywords.append(base)
    # 文件名作关键词（取最后有意义的）
    for f in sorted(files):
        stem = Path(f).stem.strip()
        if stem and stem not in seen and stem not in SKIP:
            seen.add(stem)
            if len(keywords) < 3:
                keywords.append(stem)
    return tags[:5], keywords[:3]



_FORBIDDEN_FILENAME_RE = re.compile(r'[/\\:*?"<>|\r\n\t]')
# Unicode Box Drawing 块 (U+2500–U+257F) + Block Elements (U+2580–U+259F)
_BOXDRAW_RE = re.compile("[─-▟]")


def sanitize_filename(name: str) -> str:
    """把主题转成合法文件名：去禁止字符/制表符、折叠空白、截断 80 字符。"""
    name = _BOXDRAW_RE.sub("", name or "")
    name = _FORBIDDEN_FILENAME_RE.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if len(name) > 80:
        name = name[:80].rstrip()
    return name or "未命名"


def find_note_by_session(index_dir: Path, session_id: str):
    """在 NOTE_DIR 中按 frontmatter 的 session_id 查找已存在的断点笔记。"""
    for p in sorted(index_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        m = re.search(r'^session_id:\s*"([^"]+)"', text, re.MULTILINE)
        if m and m.group(1) == session_id:
            return p
    return None


def read_frontmatter_list(path: Path, key: str):
    """读取笔记 frontmatter 里某个 JSON 数组字段（如 tags/keywords）。无则返回 []。"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    m = re.search(rf'^{key}:\s*(\[.*\])', text, re.MULTILINE)
    if not m:
        return []
    try:
        v = json.loads(m.group(1))
        return [str(t) for t in v] if isinstance(v, list) else []
    except Exception:
        return []



def _short_resume_text(text: str, limit: int = 1500) -> str:
    """保留用户可读的助手结论，移除代码和无关的运行噪声。"""
    lines = []
    in_code_block = False
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if line.strip().startswith(("[obsidian-hook]", "Script completed", "Wall time")):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _assistant_resume_block(updates) -> str:
    """从助手回复中选择最适合下一轮接手的结论，而非回放聊天记录。"""
    candidates = []
    for index, raw_text in enumerate(updates or []):
        text = _short_resume_text(raw_text)
        if len(text) < 40:
            continue
        score = index * 2
        if re.search(r"(?:根因|结论|已(?:完成|修复|验证|同步|写入)|当前|后续|限制|问题)", text):
            score += 14
        # 中间进度播报在 transcript 末尾最常见，却无法帮助新会话恢复事实。
        if re.search(r"(?:^|。|\n)(?:我会|现在会|接下来会|正在|随后会|I will)", text[:400]):
            score -= 24
        candidates.append((score, index, text))
    if not candidates:
        return "（尚未提取到可用于续接的助手结论）"
    # 优先保留一条收束性回复；如果它过短，再补一条较早的有效结论。
    candidates.sort(reverse=True)
    primary = candidates[0][2]
    if len(primary) >= 420:
        return primary
    for _, _, extra in candidates[1:]:
        if extra != primary:
            combined = primary + "\n\n" + extra
            return _short_resume_text(combined, 1500)
    return primary


def _session_goal_block(prompts) -> str:
    """保留少量目标变化，避免把每条用户消息完整粘进断点。"""
    normalized = []
    seen = set()
    for prompt in prompts or []:
        text = re.sub(r"\s+", " ", str(prompt or "")).strip()
        key = text.lower()
        if (
            not text
            or text.startswith("<image ")
            or text == "</image>"
            or text.startswith("# Files mentioned by the user:")
            or key in seen
        ):
            continue
        seen.add(key)
        normalized.append(text)
    if not normalized:
        return "（未提取到会话目标）"
    # 只保留最近目标，避免断点退化成完整对话的替代副本。
    selected = _dedupe_items(normalized[-3:], 3)
    return "\n".join(f"- {_short_resume_text(item, 180)}" for item in selected)


def _knowledge_write_paths(ctx: dict) -> list:
    return sorted(set(ctx.get("written_files", [])) | set(ctx.get("external_written_files", [])))


def _knowledge_link(file_path: str) -> str:
    path = Path(file_path)
    try:
        rel = path.relative_to(VAULT_ROOT).with_suffix("")
        return f"[[{rel}|{path.stem}]]"
    except Exception:
        return f"[[{path.stem}]]"


def _daily_index_link(file_path: str) -> str:
    """Markdown 表格内禁用 wikilink 别名，避免内部竖线被表格解析器拆列。"""
    path = Path(file_path)
    try:
        rel = path.relative_to(VAULT_ROOT).with_suffix("")
        return f"[[{rel}]]"
    except Exception:
        return f"[[{path.stem}]]"


def _archive_metadata(path: Path) -> dict:
    """读取 synthesize 写入的归档快照；新消息出现后该快照自动失效。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    if not re.search(r"^knowledge_archived:\s*true$", text, re.MULTILINE):
        return {}
    count_match = re.search(r"^archived_prompt_count:\s*(\d+)$", text, re.MULTILINE)
    document_match = re.search(r'^archive_document:\s*"([^"]+)"', text, re.MULTILINE)
    if not count_match or not document_match:
        return {}
    return {
        "prompt_count": int(count_match.group(1)),
        "document": document_match.group(1),
    }


def generate_session_note(session_id: str, ctx: dict, status: str, related: list = None) -> str:
    now = vault_now()
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC+8")
    short_id = session_id[:12] if len(session_id) > 12 else session_id
    label = STATUS_MAP.get(status, {}).get("label", status)
    topic = ctx["topic"] or "(未提取到话题)"
    platform = "codex"
    archive_frontmatter = ""
    if ctx.get("knowledge_archived"):
        archive_frontmatter = (
            "knowledge_archived: true\n"
            f"archived_prompt_count: {ctx.get('archived_prompt_count', 0)}\n"
            f"archive_document: \"{ctx.get('archive_document', '')}\"\n"
        )
    meta_lines = [
        f"**状态**: {label}",
        f"**最近归档**: {timestamp}",
        f"**平台**: {platform}",
        f"**会话 ID**: `{session_id}`",
    ]
    project_refs = sorted(set(ctx.get("projects", [])) | set(ctx.get("external_projects", [])))
    if project_refs:
        meta_lines.append(f"**涉及项目**: {', '.join(project_refs)}")
    meta_lines.append(f"**已记录用户消息**: {len(ctx.get('user_prompts', []))}")
    meta_block = "\n".join(meta_lines)
    goals_block = _session_goal_block(ctx.get("user_prompts", []))
    assistant_block = _assistant_resume_block(
        ctx.get("assistant_updates") or [ctx.get("latest_assistant_update", "")]
    )
    knowledge_writes = _knowledge_write_paths(ctx)
    if knowledge_writes:
        links = [_knowledge_link(path) for path in knowledge_writes]
        yield_block = "\n".join(f"- {l}" for l in links)
        completed_block = "\n".join([
            "- 已将本次识别到的知识产出写入 vault。",
            *[f"- 已归档：{link}" for link in links],
        ])
    else:
        yield_block = "（本次未写入方案文件）"
        completed_block = "- 本次没有新增可链接的知识文档，断点已更新为最新会话状态。"
    continuation_lines = [
        f"- 当前归档状态：{label}。",
        f"- 最近用户目标：{_short_resume_text((ctx.get('user_prompts') or ['（未提取到）'])[-1], 220)}",
    ]
    if project_refs:
        continuation_lines.append(
            "- 优先读取涉及项目的 `项目总结.md`，再根据实际产出和下方结论继续。"
        )
    else:
        continuation_lines.append("- 先依据本断点的主要结论和实际产出继续，避免重新加载完整 transcript。")
    continuation_block = "\n".join(continuation_lines)
    evidence_block = ""
    if status == "incomplete_archive":
        lines = []
        if ctx["used_plan_mode"]:
            lines.append("- **Plan Mode**: 使用了 EnterPlanMode / ExitPlanMode")
        if ctx["verbal_plan_snippets"]:
            lines.append("- **对话中检测到方案讨论**:")
            for snippet in ctx["verbal_plan_snippets"][:3]:
                lines.append(f"  > {snippet}")
        if lines:
            evidence_block = (
                "\n## 方案讨论证据\n\n"
                + "\n".join(lines)
                + f"\n\n> 💡 **建议**：恢复此会话，要求 {PRODUCT_LABEL} 将方案写入 Obsidian。\n"
            )
    return f"""---
date: "{now.strftime('%Y-%m-%d')}"
session_id: "{session_id}"
status: "{status}"
platform: "{platform}"
projects: {json.dumps(sorted(ctx['projects']), ensure_ascii=False)}
external_projects: {json.dumps(sorted(ctx.get('external_projects', [])), ensure_ascii=False)}
category: {json.dumps(ctx.get('category', []), ensure_ascii=False)}
tags: {json.dumps(ctx.get('tags', []), ensure_ascii=False)}
keywords: {json.dumps(ctx.get('keywords', []), ensure_ascii=False)}
aliases: {json.dumps(ctx.get('keywords', []) + ctx.get('tags', []), ensure_ascii=False)}
{archive_frontmatter}---

# {topic}

> {label} · {short_id}

{meta_block}

---

## 可直接续接的结论

{assistant_block}

---

## 已完成事项

{completed_block}

---

## 当前状态与续接

{continuation_block}

---

## 会话目标演进

{goals_block}

---

## 实际产出

{yield_block}
{evidence_block}
---

{"## 相关会话\n\n" + "\n".join(f"- [[{r}]]" for r in related) + "\n\n---\n" if related else ""}
## 恢复

回到 Codex 线程列表，打开 thread_id `{session_id}` 继续。
"""


def remove_index_rows(index_dir: Path, old_stem: str):
    """--force 重命名笔记后，删掉每日索引里指向旧文件名的行。"""
    if not old_stem:
        return
    match_keys = (f"[[{old_stem}]]", f"[[{old_stem}|")
    for idx in index_dir.glob("*.md"):
        try:
            lines = idx.read_text(encoding="utf-8").splitlines(keepends=True)
        except (FileNotFoundError, OSError):
            continue
        new_lines = [
            ln for ln in lines
            if not (any(match_key in ln for match_key in match_keys) and ln.lstrip().startswith("|"))
        ]
        if len(new_lines) != len(lines):
            idx.write_text("".join(new_lines), encoding="utf-8")


def update_daily_index(index_dir: Path, session_note_path: Path | None, session_id: str, ctx: dict, status: str):
    now = vault_now()
    today = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%H:%M")
    index_path = index_dir / f"{today}.md"
    emoji = STATUS_MAP.get(status, {}).get("emoji", "❓")
    topic = ctx["topic"][:60] if ctx["topic"] else "未记录话题"
    knowledge_writes = _knowledge_write_paths(ctx) if session_note_path else []
    if knowledge_writes:
        note_names = [_daily_index_link(path) for path in knowledge_writes]
        yield_str = " · ".join(note_names)
    else:
        yield_str = "—"
    if session_note_path:
        link_target = session_note_path.stem
        topic_cell = f"[[{link_target}]]"
    else:
        link_target = session_id
        topic = re.sub(r"[|\r\n]", " ", topic).strip()
        round_count = int(ctx.get("round_count", 0))
        topic_cell = f"{topic}（未生成断点 {round_count}/{AUTO_CHECKPOINT_MIN_ROUNDS}）"
    entry = f"| {timestamp} | {emoji} | {topic_cell} | {yield_str} | <!-- session:{session_id} -->\n"
    if not index_path.exists():
        header = f"""---
date: "{today}"
tags:
  - {INDEX_TAG}
---

# 会话记录 - {today}

> 每日自动生成 · `{SPACE_NAME}/会话索引/`

| 时间 | 状态 | 话题 | 产出 |
|---|---|---|---|
"""
        index_path.write_text(header, encoding="utf-8")
    # 同一 session 已有行则原地更新，兼容旧版带别名的链接。
    match_keys = (f"<!-- session:{session_id} -->", f"[[{link_target}]]", f"[[{link_target}|")
    lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if any(match_key in line for match_key in match_keys) and line.lstrip().startswith("|"):
            lines[i] = entry
            index_path.write_text("".join(lines), encoding="utf-8")
            return
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(entry)


def collect_restart_candidates() -> list:
    """为首页生成默认恢复项，不单独维护重启事项文件。"""
    candidates = []
    for path in NOTE_DIR.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        session_match = re.search(r'^session_id:\s*"([^"]+)"', text, re.MULTILINE)
        status_match = re.search(r'^status:\s*"([^"]+)"', text, re.MULTILINE)
        title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if not session_match or not status_match:
            continue
        projects = read_frontmatter_list(path, "projects") + read_frontmatter_list(path, "external_projects")
        projects = _dedupe_items(projects, 3)
        status = status_match.group(1)
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0
        priority = 4 if status in ("interrupted", "incomplete_archive") else 2 if projects else 1
        candidates.append({
            "path": path,
            "session_id": session_match.group(1),
            "status": status,
            "title": title_match.group(1).strip() if title_match else path.stem,
            "projects": projects,
            "priority": priority,
            "modified": modified,
        })
    candidates.sort(key=lambda item: (item["priority"], item["modified"]), reverse=True)
    return candidates


def find_related_notes(tags: list, current_stem: str) -> list:
    """找 tag 重叠 ≥2 的已有笔记，返回 stem 列表（最多 5 个）。"""
    related = []
    for n in sorted(NOTE_DIR.glob("*.md")):
        if n.stem == current_stem:
            continue
        existing = read_frontmatter_list(n, "tags")
        overlap = sum(1 for t in tags if t in existing)
        if overlap >= 2:
            related.append(n.stem)
    return related[:5]


def _read_text_limited(path: Path, max_chars: int = 6000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return head + "\n\n...（中间内容已截断）...\n\n" + tail


def _extract_h1(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text or "", re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fallback


def _extract_section(text: str, heading: str) -> str:
    m = re.search(rf"##\s+{re.escape(heading)}\n+([\s\S]*?)(?=\n##\s+|\Z)", text or "")
    return m.group(1).strip() if m else ""


def _parse_items(block: str) -> list:
    if not block:
        return []
    items = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^[-*]\s+", stripped):
            items.append(re.sub(r"^[-*]\s+", "", stripped))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            items.append(re.sub(r"^\d+\.\s+", "", stripped))
    if items:
        return [re.sub(r"\s+", " ", item).strip() for item in items if item.strip()]
    parts = re.split(r"\n\s*\n", block)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def _dedupe_items(items: list, limit: int = None) -> list:
    seen = set()
    unique = []
    for item in items:
        key = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", item)
        key = re.sub(r"\s+", " ", key).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if limit and len(unique) >= limit:
            break
    return unique


def _shorten_line(text: str, limit: int = 150) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _clean_summary_item(text: str) -> str:
    cleaned = re.sub(r"^\[\[[^\]]+\]\]：", "", (text or "")).strip()
    cleaned = re.sub(r"^\[\[[^\]]+\]\]\s*", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _read_project_docs(project: str) -> list:
    docs = []
    for p in _project_doc_paths(project):
        if "自动合成" in p.stem:
            continue
        text = _read_text_limited(p, 12000)
        if not text:
            continue
        docs.append({
            "path": p,
            "title": _extract_h1(text, p.stem),
            "text": text,
            "sections": {
                heading: _extract_section(text, heading)
                for heading in (
                    "关键结论", "当前缺口", "实施路径", "已验证能力", "背景概览",
                    "最佳实践", "踩坑记录", "本轮完成", "已验证结果", "仍未完成",
                    "可复用经验", "避坑清单", "下次同类项目流程", "当前能力",
                    "项目材料", "已验证闭环", "使用方式", "当前边界", "恢复入口"
                )
            },
        })
    return docs


def _project_doc_paths(project: str) -> list:
    """返回某个项目目录下可作为总结材料的归档文档。"""
    project_dir = PROJECTS_DIR / project
    if not project_dir.is_dir():
        return []
    docs = []
    for p in sorted(project_dir.glob("*.md")):
        if p.name == PROJECT_SUMMARY_NAME:
            continue
        if p.name.endswith(PROJECT_EXPERIENCE_SUFFIX):
            continue
        docs.append(p)
    return docs


def _collect_project_material(project: str, ctx: dict, session_note_path: Path) -> str:
    """收集项目归档、旧总结、当前断点，限制体积后交给 LLM。"""
    project_dir = PROJECTS_DIR / project
    parts = [f"项目名：{project}"]
    summary_path = project_dir / PROJECT_SUMMARY_NAME
    if summary_path.exists():
        parts.append("\n## 旧项目总结（用于增量更新）\n" + _read_text_limited(summary_path, 5000))

    if session_note_path and session_note_path.exists():
        parts.append("\n## 本次会话断点\n" + _read_text_limited(session_note_path, 4000))

    written_in_project = []
    for f in sorted(ctx.get("written_files", [])):
        try:
            p = Path(f)
            rel = p.relative_to(project_dir)
            if len(rel.parts) >= 1:
                written_in_project.append(p)
        except Exception:
            pass
    if written_in_project:
        parts.append("\n## 本次直接产出文件\n" + "\n".join(f"- {p.name}" for p in written_in_project))

    docs = _project_doc_paths(project)
    if docs:
        doc_parts = []
        for p in docs[:12]:
            text = _read_text_limited(p, 3500)
            title = _extract_h1(text, p.stem)
            doc_parts.append(f"\n### {title}（{p.name}）\n{text}")
        parts.append("\n## 项目归档文档\n" + "\n".join(doc_parts))

    material = "\n".join(parts)
    if len(material) > PROJECT_SUMMARY_MAX_CHARS:
        material = material[:PROJECT_SUMMARY_MAX_CHARS] + "\n\n...（项目材料超出长度，已截断）..."
    return material


def _frontmatter(title_tags: list, project: str, kind: str) -> str:
    today = vault_now().strftime("%Y-%m-%d")
    tags = [PLAN_TAG, "知识库/自动总结", kind] + [t for t in title_tags if t]
    # 去重但保持顺序
    unique_tags = []
    for t in tags:
        if t not in unique_tags:
            unique_tags.append(t)
    return f"""---
date: {today}
project: {project}
tags: {json.dumps(unique_tags, ensure_ascii=False)}
aliases: {json.dumps([project, "项目总结", "可复用经验", "经验摘要"], ensure_ascii=False)}
---
"""


def _fallback_project_summary(project: str, ctx: dict, session_note_path: Path) -> str:
    docs = _read_project_docs(project)
    prompts = _dedupe_items([f"- {_shorten_line(p, 120)}" for p in ctx.get("user_prompts", [])[:5]], 5) or ["- （未提取到用户提问）"]
    outputs = []
    for doc in docs:
        outputs.append(f"- [[{doc['path'].stem}]]")
    outputs = _dedupe_items(outputs, 8) or ["- （本次未新增项目归档）"]
    session_link = f"[[{session_note_path.stem}]]" if session_note_path else "（无）"
    positioning = []
    status_items = []
    decisions = []
    verified = []
    runtime_notes = []
    experience = []

    for doc in docs:
        for section_name, target in (
            ("背景概览", positioning),
            ("关键结论", decisions),
            ("当前能力", decisions),
            ("已验证能力", verified),
            ("已验证闭环", verified),
            ("当前缺口", status_items),
            ("当前边界", status_items),
            ("实施路径", runtime_notes),
            ("使用方式", runtime_notes),
            ("项目材料", runtime_notes),
            ("最佳实践", experience),
            ("踩坑记录", experience),
            ("已验证结果", verified),
            ("仍未完成", status_items),
        ):
            section = doc["sections"].get(section_name, "")
            for item in _parse_items(section)[:4]:
                cleaned = _clean_summary_item(item)
                if "不再是缺口" in cleaned:
                    continue
                if cleaned:
                    target.append(f"- [[{doc['path'].stem}]]：{_shorten_line(cleaned)}")

    positioning = _dedupe_items(positioning, 4) or [f"- 项目目标是把原仓库的 checkpoint 机制迁到 {PRODUCT_LABEL}，并保持 Obsidian 断点、项目总结和经验沉淀链路可用。"]
    status_items = _dedupe_items(status_items, 5)
    if not status_items:
        status_items = [
            f"- 最近断点：{session_link}",
            f"- 会话状态：{ctx.get('status', 'unknown')}",
        ]
    else:
        status_items.insert(0, f"- 最近断点：{session_link}")
        status_items = _dedupe_items(status_items, 6)

    decisions = _dedupe_items(decisions, 5) or [
        f"- 断点写入目录、标签和首页文件名已经切到 {PRODUCT_LABEL} 口径。",
        f"- 核心链路继续复用 `checkpoint.py`，并补齐 {PRODUCT_LABEL} transcript 解析与 hook 适配。",
    ]
    verified = _dedupe_items(verified, 6) or [
        f"- 当前会话已经能触发断点写入，并能刷新项目级文档。",
    ]
    runtime_notes = _dedupe_items(runtime_notes, 5) or [
        f"- 优先复用已有项目文档、更新日志和断点，避免重新恢复完整 transcript。",
    ]
    experience = _dedupe_items(experience, 5) or [
        f"- 验证时先拆分 hook、wrapper、trust、手动 checkpoint 几层，再看整条链路。",
    ]
    return f"""# {project} 项目总结

## 项目定位

{chr(10).join(positioning)}

## 最近会话脉络

{chr(10).join(prompts)}

## 当前状态

{chr(10).join(status_items)}

## 关键架构与决策

{chr(10).join(decisions)}

## 已验证闭环

{chr(10).join(verified)}

## 部署与运行要点

{chr(10).join(runtime_notes)}

## 重要经验

{chr(10).join(experience)}

## 后续恢复入口

- 先读 [[项目总结]]，快速恢复项目状态和当前缺口。
- 再读 [[Codex hook 与 skill 更新日志]] 和 [[checkpoint 迁到 Codex]]，掌握最近一次规则变动和验证证据。
- 如需理解迁移主线，再读 [[checkpoint 迁到 Codex]] 和最近断点 {session_link}。

## 相关笔记

{chr(10).join(outputs)}
"""


def _fallback_experience(project: str, ctx: dict, session_note_path: Path) -> str:
    session_link = f"[[{session_note_path.stem}]]" if session_note_path else "（无）"
    docs = _read_project_docs(project)
    reusable = []
    pitfalls = []
    workflow = []
    acceptance = []
    keywords = []

    for doc in docs:
        for section_name, target in (
            ("最佳实践", reusable),
            ("可复用经验", reusable),
            ("踩坑记录", pitfalls),
            ("当前缺口", pitfalls),
            ("当前边界", pitfalls),
            ("实施路径", workflow),
            ("使用方式", workflow),
            ("下次同类项目流程", workflow),
            ("已验证能力", acceptance),
            ("已验证闭环", acceptance),
            ("已验证结果", acceptance),
        ):
            section = doc["sections"].get(section_name, "")
            for item in _parse_items(section)[:4]:
                cleaned = _clean_summary_item(item)
                if "不再是缺口" in cleaned:
                    continue
                if cleaned:
                    target.append(f"- {_shorten_line(cleaned)}")
        keywords.extend(re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", doc["title"]))

    reusable = _dedupe_items(reusable, 5) or [
        "- 阶段结束就把方案、验证记录和更新日志写进项目目录，让后续总结不必重新扫完整 transcript。",
        f"- 迁移到 {PRODUCT_LABEL} 时，优先复用现有断点逻辑，再补 transcript 解析、hook 适配和知识库口径切换。",
    ]
    pitfalls = _dedupe_items(pitfalls, 5) or [
        "- 不要把 trust、hook、wrapper、脚本逻辑混在一起排查，否则很容易误判故障层级。",
        "- 不要让 UI 注入块、调试输出和测试残留直接进入断点和知识合成结果。",
    ]
    workflow = _dedupe_items(workflow, 5) or [
        "- 先验证脚本能否独立运行，再验证 hook 输入格式，最后验证真实信任模式和项目级自动沉淀。",
        "- 关键修补完成后，立即回写真实知识库，检查断点、项目总结、经验摘要和搜索结果是否同步变好。",
    ]
    acceptance = _dedupe_items(acceptance, 5) or [
        "- 自动断点、手动 checkpoint、项目总结、可复用经验、搜索和知识合成都需要至少一次真实回写或真实查询验证。",
        "- 打包解包必须验证 `Codex工作记录/`、`项目总结/`、`长期经验总结/`、`知识库首页.md` 和 `~/.codex/sessions/` 是否完整恢复。",
    ]
    keyword_list = _dedupe_items([f"`{k}`" for k in keywords if len(k) >= 2], 12) or [
        "`checkpoint`", "`Codex`", "`Obsidian`", "`hook`", "`synthesize`", "`search`"
    ]

    return f"""# {project} 长期经验总结

## 长期经验总结

{chr(10).join(reusable)}

## 避坑清单

{chr(10).join(pitfalls)}

## 下次同类项目流程

1. 先看 `项目总结.md` 和最近更新日志，确认当前链路和剩余缺口。
2. 先拆脚本、hook、trust、项目沉淀四层做验证，再回到整体验证。
3. 每修一层就回写真实知识库，检查断点、搜索、合成结果是否同步改善。
4. 阶段结束后刷新项目总结和长期经验总结，避免下一轮继续吃长上下文成本。

## 验收检查清单

{chr(10).join(acceptance)}

## 可检索关键词

- {", ".join(keyword_list)}

## 来源

- 最近断点：{session_link}
- 项目文档：{", ".join(f'[[{doc["path"].stem}]]' for doc in docs[:6]) if docs else '（无）'}
"""


def synthesize_project_summary(project: str, ctx: dict, session_note_path: Path) -> str:
    return _fallback_project_summary(project, ctx, session_note_path)


def synthesize_reusable_experience(project: str, ctx: dict, session_note_path: Path) -> str:
    return _fallback_experience(project, ctx, session_note_path)


def update_project_knowledge(ctx: dict, session_note_path: Path):
    """为本次涉及的项目刷新滚动总结，并沉淀长期可复用经验。"""
    projects = sorted(ctx.get("projects", []))
    if not projects:
        return []
    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    written = []
    for project in projects:
        project_dir = PROJECTS_DIR / project
        if not project_dir.is_dir():
            continue
        ctx_with_status = dict(ctx)
        ctx_with_status["status"] = ctx.get("status", "completed")

        summary_body = synthesize_project_summary(project, ctx_with_status, session_note_path)
        summary_path = project_dir / PROJECT_SUMMARY_NAME
        summary_path.write_text(
            _frontmatter(["项目总结"], project, "项目总结") + "\n" + summary_body.strip() + "\n",
            encoding="utf-8",
        )
        written.append(summary_path)

        experience_body = synthesize_reusable_experience(project, ctx_with_status, session_note_path)
        exp_name = f"{sanitize_filename(project)}-{PROJECT_EXPERIENCE_SUFFIX}"
        exp_path = EXPERIENCE_DIR / exp_name
        exp_path.write_text(
            _frontmatter(["长期经验总结"], project, "长期经验总结") + "\n" + experience_body.strip() + "\n",
            encoding="utf-8",
        )
        written.append(exp_path)
    return written


def _vault_link(path: Path, label: str) -> str:
    try:
        rel = path.relative_to(VAULT_ROOT).with_suffix("")
        return f"[[{rel}|{label}]]"
    except ValueError:
        return f"[[{path.stem}|{label}]]"


def update_navigation_notes():
    """为首页入口提供真实可打开的 Markdown 导航页。"""
    experience_index = EXPERIENCE_DIR / "首页.md"
    experience_links = []
    if EXPERIENCE_DIR.is_dir():
        for path in sorted(EXPERIENCE_DIR.glob("*.md")):
            if path == experience_index:
                continue
            title = _extract_h1(_read_text_limited(path, 1200), path.stem)
            experience_links.append(f"- {_vault_link(path, title)}")
    experience_index.write_text(
        "# 长期经验总结\n\n"
        "> 跨项目可复用的流程、边界和验收经验。\n\n"
        "## 可用总结\n\n"
        + ("\n".join(experience_links) if experience_links else "暂无长期经验总结")
        + "\n",
        encoding="utf-8",
    )

    project_index = PROJECTS_DIR / "首页.md"
    project_links = []
    if PROJECTS_DIR.is_dir():
        for summary in sorted(PROJECTS_DIR.rglob(PROJECT_SUMMARY_NAME)):
            title = _extract_h1(_read_text_limited(summary, 1200), summary.parent.name)
            project_links.append(f"- {_vault_link(summary, title)}")
    project_index.write_text(
        "# 项目总结\n\n"
        "> 各项目的当前状态、已验证结论与恢复入口。\n\n"
        "## 项目列表\n\n"
        + ("\n".join(project_links) if project_links else "暂无项目总结")
        + "\n",
        encoding="utf-8",
    )


def update_dashboard():
    """更新知识库首页：概览/状态/大类/小类/待恢复列表。"""
    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    update_navigation_notes()
    notes = list(NOTE_DIR.glob("*.md"))
    total = len(notes)
    status_counts = {"completed": 0, "interrupted": 0, "incomplete_archive": 0, "archived": 0}
    tag_counts = {}
    cat_counts = {}
    pending_entries = []
    unarchived_entries = []
    project_entries = []

    for n in notes:
        try:
            text = n.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        st = re.search(r'^status:\s*"([^"]+)"', text, re.MULTILINE)
        status = st.group(1) if st else ""
        if status in status_counts:
            status_counts[status] += 1
        # 分类 / 标签（从已读 text 解析，不重复读文件）
        cm = re.search(r'^category:\s*(\[.*\])', text, re.MULTILINE)
        if cm:
            try:
                for c in json.loads(cm.group(1)):
                    cat_counts[c] = cat_counts.get(c, 0) + 1
            except Exception:
                pass
        tm = re.search(r'^tags:\s*(\[.*\])', text, re.MULTILINE)
        if tm:
            try:
                for t in json.loads(tm.group(1)):
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            except Exception:
                pass
        note_rel = n.relative_to(VAULT_ROOT).with_suffix("")
        if status == "interrupted":
            d = re.search(r'^date:\s*"([^"]+)"', text, re.MULTILINE)
            h1 = re.search(r'^# (.+)', text, re.MULTILINE)
            pending_entries.append(f"- [[{note_rel}|{h1.group(1) if h1 else n.stem}]] · {d.group(1) if d else '?'}")
        elif status == "incomplete_archive":
            d = re.search(r'^date:\s*"([^"]+)"', text, re.MULTILINE)
            h1 = re.search(r'^# (.+)', text, re.MULTILINE)
            unarchived_entries.append(f"- [[{note_rel}|{h1.group(1) if h1 else n.stem}]] · {d.group(1) if d else '?'}")

    # 项目材料统一位于“项目总结/”，项目入口由各目录中的项目总结确定。
    doc_count = 0
    if PROJECTS_DIR.is_dir():
        for summary in sorted(PROJECTS_DIR.rglob(PROJECT_SUMMARY_NAME)):
            project_dir = summary.parent
            project_docs = sorted(project_dir.glob("*.md"))
            if not project_docs:
                continue
            project_rel = project_dir.relative_to(PROJECTS_DIR).as_posix()
            summary_rel = summary.relative_to(VAULT_ROOT).with_suffix("")
            overview = next((doc for doc in project_docs if doc.name != PROJECT_SUMMARY_NAME), None)
            overview_link = (
                f" · [[{overview.relative_to(VAULT_ROOT).with_suffix('')}|项目材料]]"
                if overview else ""
            )
            project_entries.append(
                f"- [[{summary_rel}|{project_rel}]]{overview_link} · {len(project_docs)} 篇项目文档"
            )
            for md in project_docs:
                doc_count += 1
                try:
                    text = md.read_text(encoding="utf-8")
                except Exception:
                    continue
                tm = re.search(r'^tags:\s*(\[.*\])', text, re.MULTILINE)
                if tm:
                    try:
                        for t in json.loads(tm.group(1)):
                            tag_counts[t] = tag_counts.get(t, 0) + 1
                    except Exception:
                        pass

    completed = status_counts["completed"]
    interrupted = status_counts["interrupted"]
    incomplete = status_counts["incomplete_archive"]
    archived = status_counts["archived"]
    settled = completed + archived
    rate = round(settled / total * 100) if total else 0
    hot_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:10]
    top_cats = sorted(cat_counts.items(), key=lambda x: -x[1])[:6]
    restart_candidates = collect_restart_candidates()
    restart_section = "暂无可恢复会话"
    restart_metadata = ""
    if restart_candidates:
        default = restart_candidates[0]
        default_rel = default["path"].relative_to(VAULT_ROOT)
        default_link = default_rel.with_suffix("")
        default_projects = ", ".join(default["projects"]) if default["projects"] else "未关联项目"
        status_label = STATUS_MAP.get(default["status"], {}).get("label", default["status"])
        restart_metadata = "<!-- codex-restart: " + json.dumps({
            "default_note": default_rel.as_posix(),
            "default_session_id": default["session_id"],
            "default_projects": default["projects"],
        }, ensure_ascii=False) + " -->"
        optional_entries = []
        for item in restart_candidates[:5]:
            item_label = STATUS_MAP.get(item["status"], {}).get("label", item["status"])
            projects = ", ".join(item["projects"]) if item["projects"] else "未关联项目"
            note_rel = item["path"].relative_to(VAULT_ROOT).with_suffix("")
            optional_entries.append(f"- [[{note_rel}|{item['title']}]] · {item_label} · {projects}")
        restart_section = f"""{restart_metadata}

### 默认恢复

- 断点：[[{default_link}|{default['title']}]]
- 状态：{status_label}
- 项目：{default_projects}

### 可选恢复任务

{chr(10).join(optional_entries)}

恢复时只读取所选断点、关联项目总结与相关长期经验，不读取完整 rollout transcript。"""

    latest_index = max(INDEX_DIR.glob("*.md"), default=None, key=lambda path: path.name)
    work_entry = _vault_link(latest_index, "Codex工作记录") if latest_index else "Codex工作记录暂无会话索引"
    dash = f"""# 知识库首页

> 更新于 `{vault_now().strftime('%Y-%m-%d %H:%M UTC+8')}`

## 概览

- 会话总数：{total}
- 已完成：{completed}
- 已知识归档：{archived}
- 待恢复：{interrupted}
- 未归档方案：{incomplete}
- 项目文档：{doc_count}
- 已结束或已归档占比：{rate}%

## 入口

- [[长期经验总结/首页|长期经验总结]]
- [[项目总结/首页|项目总结]]
- {work_entry}
- [[Codex协同Obsidian工作流skill更新日志]]

## 重启事项

{restart_section}

## 项目

{chr(10).join(project_entries) if project_entries else '暂无项目文档'}

## 待恢复会话

{chr(10).join(pending_entries) if pending_entries else '暂无待恢复会话'}

## 未归档方案

{chr(10).join(unarchived_entries) if unarchived_entries else '暂无未归档方案'}

## 标签

{" ".join(f'`{t}` ({c})' for t, c in hot_tags) if hot_tags else '暂无标签'}
"""
    (VAULT_ROOT / HOMEPAGE_NAME).write_text(dash, encoding="utf-8")
    _set_codex_root_order()


def _set_codex_root_order():
    """文件浏览器按修改时间排序时，保持 Codex 知识库入口的固定顺序。"""
    if PRODUCT_LABEL != "Codex":
        return
    paths = (
        VAULT_ROOT / HOMEPAGE_NAME,
        VAULT_ROOT / "长期经验总结",
        VAULT_ROOT / "项目总结",
        VAULT_ROOT / "Codex工作记录",
        VAULT_ROOT / "Codex协同Obsidian工作流skill更新日志.md",
    )
    base = datetime.now().timestamp()
    for offset, path in enumerate(paths):
        if not path.exists():
            continue
        try:
            os.utime(path, (base - offset, base - offset))
        except OSError:
            continue



def _parse_cli():
    """解析命令行/stdin 输入，返回统一 dict。"""
    result = {"transcript": "", "session": "unknown", "cwd": os.getcwd(), "force": False,
              "lite": False, "lite_topic": None, "lite_category": [], "lite_tags": [], "lite_keywords": [],
              "platform": "codex", "hook_event_name": ""}
    result["force"] = "--force" in sys.argv
    for flag, key, is_list in (("--topic", "lite_topic", False), ("--category", "lite_category", True),
                                ("--tags", "lite_tags", True), ("--keywords", "lite_keywords", True)):
        if flag in sys.argv:
            idx = sys.argv.index(flag)
            if idx + 1 < len(sys.argv):
                val = sys.argv[idx + 1]
                result[key] = [t.strip() for t in val.split(",") if t.strip()] if is_list else val
    result["lite"] = result["lite_topic"] is not None
    if "--transcript" in sys.argv:
        idx = sys.argv.index("--transcript")
        if idx + 1 < len(sys.argv):
            result["transcript"] = sys.argv[idx + 1]
        if "--session-id" in sys.argv:
            sid_idx = sys.argv.index("--session-id")
            if sid_idx + 1 < len(sys.argv):
                result["session"] = sys.argv[sid_idx + 1]
        if result["transcript"] and result["session"] == "unknown":
            result["session"] = _session_id_from_transcript_path(result["transcript"])
        _debug_log(
            "manual_mode",
            argv=sys.argv,
            transcript=result["transcript"],
            session=result["session"],
            platform=result["platform"],
            force=result["force"],
            lite=result["lite"],
        )
        print(f"[obsidian-hook] Manual mode: transcript={result['transcript']}, session={result['session']}")
    else:
        raw_input = sys.stdin.read()
        raw = raw_input.strip()
        if not raw:
            result["transcript"] = _find_latest_codex_rollout()
            if result["transcript"]:
                result["session"] = _session_id_from_transcript_path(result["transcript"])
                _debug_log(
                    "empty_stdin_fallback_latest_rollout",
                    argv=sys.argv,
                    transcript=result["transcript"],
                    session=result["session"],
                    platform=result["platform"],
                    raw_stdin_len=len(raw_input),
                )
                return result
            _debug_log(
                "empty_stdin_skip",
                argv=sys.argv,
                raw_stdin_len=len(raw_input),
            )
            print("[obsidian-hook] No stdin input, skipping")
            sys.exit(0)
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            _debug_log(
                "invalid_json_skip",
                argv=sys.argv,
                raw_stdin_len=len(raw_input),
                raw_stdin_preview=raw_input[:2000],
            )
            print("[obsidian-hook] Invalid JSON, skipping")
            sys.exit(0)
        payload = event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
        result["hook_event_name"] = (
            event.get("hook_event_name", "")
            or payload.get("hook_event_name", "")
            or ""
        )
        result["transcript"] = (
            event.get("transcript_path", "")
            or event.get("rollout_path", "")
            or event.get("session_path", "")
            or payload.get("transcript_path", "")
            or payload.get("rollout_path", "")
            or payload.get("session_path", "")
        )
        result["session"] = (
            event.get("session_id", "")
            or event.get("thread_id", "")
            or event.get("id", "")
            or payload.get("session_id", "")
            or payload.get("thread_id", "")
            or payload.get("id", "")
            or "unknown"
        )
        result["cwd"] = event.get("cwd", "") or payload.get("cwd", "") or result["cwd"]
        if not result["transcript"] and result["session"] != "unknown":
            result["transcript"] = _find_codex_rollout_by_session(result["session"])
        if not result["transcript"]:
            result["transcript"] = _find_latest_codex_rollout()
        if result["transcript"] and result["session"] == "unknown":
            result["session"] = _session_id_from_transcript_path(result["transcript"])
        _debug_log(
            "stdin_event_parsed",
            argv=sys.argv,
            hook_event_name=result["hook_event_name"],
            session=result["session"],
            transcript=result["transcript"],
            cwd=result["cwd"],
            platform=result["platform"],
            stop_hook_active=event.get("stop_hook_active"),
            raw_stdin_len=len(raw_input),
            raw_stdin_preview=raw_input[:2000],
        )
    return result


def _read_frontmatter_all(path):
    """一趟读取笔记的 category/tags/keywords frontmatter 字段。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return [], [], []
    def _parse(key):
        m = re.search(rf'^{key}:\s*(\[.*\])', text, re.MULTILINE)
        if not m: return []
        try:
            v = json.loads(m.group(1))
            return [str(t) for t in v] if isinstance(v, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return _parse("category"), _parse("tags"), _parse("keywords")


def main():
    cli = _parse_cli()
    transcript_path, session_id, cwd = cli["transcript"], cli["session"], cli["cwd"]
    force, lite_mode = cli["force"], cli["lite"]
    lite_topic, lite_category, lite_tags, lite_keywords = cli["lite_topic"], cli["lite_category"], cli["lite_tags"], cli["lite_keywords"]
    platform = "codex"
    hook_event_name = cli.get("hook_event_name", "")
    _debug_log(
        "main_start",
        transcript=transcript_path,
        session=session_id,
        cwd=cwd,
        force=force,
        lite=lite_mode,
        platform=platform,
        hook_event_name=hook_event_name,
    )

    if not transcript_path:
        _debug_log("skip_no_transcript", session=session_id, platform=platform)
        print("[obsidian-hook] No transcript path available, skipping")
        sys.exit(0)
    if not VAULT_ROOT.is_dir():
        _debug_log("skip_vault_missing", vault_root=VAULT_ROOT, session=session_id, platform=platform)
        print(f"[obsidian-hook] Vault not accessible: {VAULT_ROOT}, skipping")
        sys.exit(0)
    ctx = extract_session_context(transcript_path)
    ctx["platform"] = platform
    # 历史 transcript 会保留早已删除的写入记录，归档时只链接当前仍存在的项目文件。
    ctx["written_files"] = {path for path in ctx["written_files"] if Path(path).is_file()}
    ctx["external_written_files"] = {path for path in ctx.get("external_written_files", set()) if Path(path).is_file()}
    if hook_event_name == "UserPromptSubmit" and ctx.get("assistant_count", 0) == 0:
        _debug_log(
            "skip_user_prompt_submit_without_assistant",
            session=session_id,
            transcript=transcript_path,
            hook_event_name=hook_event_name,
        )
        print("[obsidian-hook] UserPromptSubmit before first assistant reply, skipping")
        sys.exit(0)
    ctx["round_count"] = min(len(ctx.get("user_prompts", [])), ctx.get("assistant_count", 0))
    status = determine_session_status(ctx)
    ctx["status"] = status
    os.makedirs(INDEX_DIR, exist_ok=True)
    os.makedirs(NOTE_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    existing_note = find_note_by_session(NOTE_DIR, session_id)
    if (
        not force
        and not lite_mode
        and ctx["round_count"] < AUTO_CHECKPOINT_MIN_ROUNDS
        and existing_note is None
    ):
        # 短会话只进入每日索引，避免把权限确认和单次问答堆成难以检索的断点文件。
        if ctx.get("thread_title"):
            ctx["topic"] = ctx["thread_title"]
        update_daily_index(INDEX_DIR, None, session_id, ctx, "indexed_only")
        update_dashboard()
        print(
            "[obsidian-hook] Session indexed without checkpoint: "
            f"{ctx['round_count']}/{AUTO_CHECKPOINT_MIN_ROUNDS} rounds"
        )
        print("[obsidian-hook] Daily index updated")
        sys.exit(0)

    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    archive = _archive_metadata(existing_note) if existing_note else {}
    if archive and len(ctx.get("user_prompts", [])) <= archive["prompt_count"]:
        status = "archived"
        ctx["status"] = status
        ctx["knowledge_archived"] = True
        ctx["archived_prompt_count"] = archive["prompt_count"]
        ctx["archive_document"] = archive["document"]
    old_stem = None
    if lite_mode:
        # Lite 模式：元数据由对话模型生成，直接覆盖，不调 LLM。
        ctx["topic"] = lite_topic or "未命名会话"
        ctx["category"] = lite_category or []
        ctx["tags"] = [t for t in (lite_tags or []) if t]
        ctx["keywords"] = lite_keywords or []
        if existing_note:
            old_stem = existing_note.stem
            existing_note.unlink()
        fname = sanitize_filename(ctx["topic"])
        candidate = NOTE_DIR / f"{fname}.md"
        if candidate.exists():
            candidate = NOTE_DIR / f"{fname}-{session_id[:8]}.md"
        session_note_path = candidate
    elif existing_note and not force:
        # 已有笔记：沿用其文件名与 H1 标题（可能已被手动编辑成更贴切的主题）。
        session_note_path = existing_note
        try:
            for line in session_note_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    existing_title = stripped[2:].strip()
                    if existing_title:
                        ctx["topic"] = existing_title
                    break
        except Exception:
            pass
        # tags/keywords：已有则保留，没有则补一次综合（回填）。
        existing_category, existing_tags, existing_keywords = _read_frontmatter_all(session_note_path)
        if existing_category and existing_tags and existing_keywords:
            ctx["category"] = existing_category
            ctx["tags"] = existing_tags
            ctx["keywords"] = existing_keywords
        else:
            synth = synthesize_topic_and_tags(ctx["user_prompts"], ctx["written_files"], ctx["projects"])
            ctx["category"] = existing_category or synth["category"]
            ctx["tags"] = existing_tags or synth["tags"]
            ctx["keywords"] = existing_keywords or synth["keywords"]
    else:
        # 新笔记，或 --force 强制重新综合（删旧笔记、重新命名）。
        if existing_note and force:
            old_stem = existing_note.stem
            existing_note.unlink()
        synth = synthesize_topic_and_tags(ctx["user_prompts"], ctx["written_files"], ctx["projects"])
        if synth["topic"]:
            ctx["topic"] = synth["topic"]
        elif ctx.get("thread_title"):
            ctx["topic"] = ctx["thread_title"]
        ctx["category"] = synth["category"]
        ctx["tags"] = synth["tags"]
        ctx["keywords"] = synth["keywords"]
        fname = sanitize_filename(ctx["topic"])
        candidate = NOTE_DIR / f"{fname}.md"
        if candidate.exists():
            candidate = NOTE_DIR / f"{fname}-{session_id[:8]}.md"
        session_note_path = candidate
    related = find_related_notes(ctx["tags"], session_note_path.stem)
    note_content = generate_session_note(session_id, ctx, status, related)
    session_note_path.write_text(note_content, encoding="utf-8")
    _debug_log(
        "write_success",
        session=session_id,
        platform=platform,
        status=status,
        note_path=session_note_path,
        transcript=transcript_path,
    )
    print(f"[obsidian-hook] Session checkpoint written: {session_note_path}")
    update_daily_index(INDEX_DIR, session_note_path, session_id, ctx, status)
    project_notes = update_project_knowledge(ctx, session_note_path)
    if project_notes:
        print("[obsidian-hook] Project knowledge updated: " + ", ".join(str(p) for p in project_notes))
    if ctx.get("external_written_files"):
        print("[obsidian-hook] External knowledge project written: " + ", ".join(sorted(ctx["external_written_files"])))
    update_dashboard()
    # --force / lite 重命名后，清掉旧文件名对应的每日索引行
    # 但旧名与新名相同时不能清（会删掉刚加的新行）
    if old_stem and old_stem != session_note_path.stem:
        remove_index_rows(INDEX_DIR, old_stem)
    print(f"[obsidian-hook] Daily index updated")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        _debug_log("uncaught_exception", error=repr(exc), argv=sys.argv)
        raise
