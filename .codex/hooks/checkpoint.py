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

CODEX_ROOT = Path(__file__).resolve().parents[1]
if str(CODEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEX_ROOT))

from metadata import (
    is_valid_generated_metadata,
    metadata_leaf_values,
    metadata_values,
    parse_frontmatter_list,
)
from redaction import redact_sensitive_text

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
EXPERIENCE_DIR = PLANS_DIR / "AI开发参考"  # 跨项目复用的参考摘要
PROJECTS_DIR = PLANS_DIR
PROJECT_SUMMARY_NAME = "项目总结.md"      # 仅已确认父项目目录使用的汇总文件
PROJECT_EXPERIENCE_SUFFIX = "AI开发参考.md"
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
    if isinstance(value, str):
        return redact_sensitive_text(value)
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


def _parse_rollout_time(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(VAULT_TIMEZONE)


def rollout_conversation_started_at(transcript_path: str) -> datetime | None:
    """优先使用 session_meta 时间，回退到 rollout 中首个带时间戳的事件。"""
    earliest = None
    try:
        with open(transcript_path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                timestamp = _parse_rollout_time(entry.get("timestamp"))
                if timestamp is None:
                    continue
                if earliest is None:
                    earliest = timestamp
                if entry.get("type") == "session_meta":
                    return timestamp
    except OSError:
        return None
    return earliest


PLANS_DIR = VAULT_ROOT / SPACE_NAME
PLANS_DIR_STR = str(PLANS_DIR)
INDEX_DIR = PLANS_DIR / "会话索引"
NOTE_DIR = PLANS_DIR / "会话断点"
EXPERIENCE_DIR = VAULT_ROOT / "AI开发参考"
LEGACY_EXPERIENCE_DIR = VAULT_ROOT / "长期经验总结"
PROJECTS_DIR = VAULT_ROOT / "项目总结"
UNCLASSIFIED_CHECKPOINT_DIR = NOTE_DIR / "未分类对话"

CHECKPOINT_CATEGORY_RULES = (
    ("知识库与工作流", ("checkpoint", "obsidian", "知识库", "synthesize", "hook", "会话断点", "vault")),
    ("系统与运维", ("docker", "部署", "服务器", "cpu", "服务", "sub2api", "tomcat", "mysql", "linux")),
    ("工具与配置", ("mcp", "搜索", "tavily", "web", "插件", "配置", "安装", "api")),
    ("学习与写作", ("课程", "报告", "面试", "面经", "学习", "文档", "论文", "校园")),
    ("开发与工程", ("开发", "代码", "项目", "node", "typescript", "java", "fastify", "测试")),
)


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
                    latest_title = redact_sensitive_text(title)[:80]
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
            if len(rel.parts) > 1 and rel.parts[0] not in ("会话索引", "会话断点", "可复用经验", "长期经验总结", "AI开发参考"):
                result["written_files"].add(abs_path)
        except Exception:
            result["written_files"].add(abs_path)
        return

    try:
        path = Path(abs_path)
        rel = path.relative_to(project_root)
        if len(rel.parts) == 1 and path.suffix.lower() == ".md" and path.stem != "首页":
            result["written_files"].add(abs_path)
            result["projects"].add(path.stem)
            return
        if len(rel.parts) >= 2 and path.suffix.lower() == ".md":
            parent = rel.parts[0]
            parent_summary = project_root / parent / PROJECT_SUMMARY_NAME
            if _is_confirmed_project_group(parent_summary):
                result["written_files"].add(abs_path)
                result["projects"].add(parent)
            return
    except Exception:
        pass

    # Vault 根目录下按“分类/项目/文档”组织的项目由用户或其他会话维护。
    # 它们应进入索引和检索，但不能由自动摘要逻辑覆盖。
    try:
        path = Path(abs_path)
        rel = path.relative_to(VAULT_ROOT)
        if (
            len(rel.parts) >= 3
            and "Codex方案" not in rel.parts
            and "Codex工作记录" not in rel.parts
            and "项目总结" not in rel.parts
            and "长期经验总结" not in rel.parts
            and "AI开发参考" not in rel.parts
            and rel.parts[0] != ".obsidian"
            and path.suffix.lower() == ".md"
        ):
            result["external_written_files"].add(abs_path)
            result["external_projects"].add("/".join(rel.parts[:2]))
    except Exception:
        pass


def _is_confirmed_project_group(summary_path: Path) -> bool:
    """项目目录只有在用户确认归属后才可作为父级项目。"""
    try:
        text = summary_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False
    return bool(re.search(r"^group_confirmed:\s*true$", text, re.MULTILINE))


def _project_summary_path(project: str) -> Path:
    return PROJECTS_DIR / f"{sanitize_filename(project)}.md"


def _trusted_session_projects(projects, session_id: str, project_root: Path) -> set[str]:
    """仅保留仍存在且已绑定当前 session 的单项目总结，避免历史写入反向制造项目归属。"""
    if not session_id:
        return set()
    trusted = set()
    for raw_project in projects or []:
        project = str(raw_project or "").strip()
        if not project:
            continue
        safe_project = sanitize_filename(project)
        candidates = (
            project_root / f"{safe_project}.md",
            project_root / safe_project / PROJECT_SUMMARY_NAME,
        )
        for summary_path in candidates:
            try:
                text = summary_path.read_text(encoding="utf-8")
            except (FileNotFoundError, OSError):
                continue
            if re.search(r"^merged_projects:\s*", text, re.MULTILINE):
                continue
            declared = re.search(r'^project:\s*"?([^"\n]+)"?$', text, re.MULTILINE)
            if not declared or declared.group(1).strip() != project:
                continue
            if session_id in read_frontmatter_list(summary_path, "session_ids"):
                trusted.add(project)
                break
    return trusted


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


def _is_internal_handoff_summary(text: str) -> bool:
    """忽略 Codex 为上下文压缩注入的交接摘要，避免其成为用户知识。"""
    if not isinstance(text, str):
        return False
    lines = [line.strip().strip("#*` ").lower() for line in text.strip().splitlines() if line.strip()]
    return len(lines) >= 2 and lines[0] == "handoff summary" and lines[1] == "current state"


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
                msg = inner
    request_marker = "## My request for Codex:"
    if request_marker in msg:
        msg = msg.split(request_marker, 1)[1]
    msg = re.sub(r"(?ms)^# Response annotations:.*?</response-annotations>\s*", "", msg)
    msg = re.sub(r"(?ms)<response-annotations>.*?</response-annotations>\s*", "", msg)
    return msg.strip()


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
    if "面经" in corpus or "模拟面试" in corpus:
        return "面经准备"

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
    cleaned = re.sub(r"(?is)<codex_internal_context\\b[^>]*>.*?</codex_internal_context>\\s*", "", cleaned)
    if _is_internal_handoff_summary(cleaned):
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
        "conversation_started_at": "",
        "thread_title": _codex_thread_title(_session_id_from_transcript_path(transcript_path)),
    }
    if not transcript_path or not os.path.exists(transcript_path):
        return result
    conversation_started_at = rollout_conversation_started_at(transcript_path)
    if conversation_started_at is not None:
        result["conversation_started_at"] = conversation_started_at.isoformat()

    user_messages = []
    assistant_count = 0
    all_assistant_parts = []

    def content_text(block) -> str:
        if isinstance(block, str):
            return block
        if not isinstance(block, dict):
            return ""
        for key in ("text", "output_text", "input_text", "content", "value"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                nested = "\n".join(content_text(item) for item in value)
                if nested.strip():
                    return nested
        return ""

    def add_user_message(text: str):
        msg = redact_sensitive_text(_strip_noise_blocks(_normalize_user_message(text)))
        if msg:
            user_messages.append(msg)

    def add_assistant_text(text: str):
        cleaned = redact_sensitive_text(_strip_noise_blocks(text))
        if not cleaned:
            return
        assistant_count_local = len(all_assistant_parts)
        _ = assistant_count_local
        all_assistant_parts.append(cleaned)
        if len(cleaned) > 50:
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
                                add_user_message(content_text(block))
                        elif role == "assistant":
                            assistant_count += 1
                            for block in content:
                                add_assistant_text(content_text(block))
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
            if re.match(r"^\[\$(?:checkpoint|synthesize|search)\]\(", msg, re.IGNORECASE):
                return False
            if _is_internal_handoff_summary(msg):
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
            if msg.startswith("<image ") or msg == "</image>":
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
        # 回执和相邻副本不属于会话事实。保留整段会话中的有效助手结论，
        # 由后续摘要函数挑选代表性内容，避免只把末尾一段写进断点。
        assistant_updates = []
        seen_updates = set()
        for text in all_assistant_parts:
            update = _strip_noise_blocks(text)
            if len(update) < 6 or _is_checkpoint_receipt(update):
                continue
            fingerprint = re.sub(r"\s+", " ", update).strip().lower()
            if fingerprint in seen_updates:
                continue
            seen_updates.add(fingerprint)
            assistant_updates.append(update)
        result["assistant_updates"] = assistant_updates
        if assistant_updates:
            result["latest_assistant_update"] = assistant_updates[-1][:1600].rstrip()

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

        # rollout 会永久保留曾经写入或删除过的项目总结路径。只有现存的单项目
        # 总结明确记录当前 session 时，该路径才能代表项目归属。
        result["projects"] = _trusted_session_projects(
            result["projects"],
            _session_id_from_transcript_path(transcript_path),
            project_root,
        )

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
    tags, keywords = [], []
    seen = set()
    for f in sorted(files):
        parts = Path(f).parts
        for index, p in enumerate(parts):
            p_clean = p.strip().lower()
            previous = parts[index - 1].strip().lower() if index else ""
            if previous == "worktrees":
                continue
            base = p_clean.split(".")[0]  # 去扩展名
            if not is_valid_generated_metadata(base):
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
        key = stem.casefold()
        if is_valid_generated_metadata(stem) and key not in seen:
            seen.add(key)
            if len(keywords) < 3:
                keywords.append(stem)
    return tags[:5], keywords[:3]


def build_checkpoint_keywords(keywords=None, tags=None) -> list[str]:
    """Prefer supplied keywords and fall back to specific tag leaf terms."""
    values = metadata_values(keywords or [], limit=3, filter_noise=True)
    return values or metadata_leaf_values(tags or [], limit=3)


def build_aliases(topic=None, project=None, tags=None, keywords=None, existing=None) -> list[str]:
    """Preserve existing aliases and supplement new notes with stable terms."""
    existing_values = metadata_values(existing or [])
    generated = metadata_values(
        topic,
        project,
        keywords or [],
        tags or [],
        metadata_leaf_values(tags or []),
        limit=12,
        filter_noise=True,
    )
    return metadata_values(existing_values, generated, limit=12)


def is_legacy_generated_path_metadata(aliases, keywords, tags) -> bool:
    """Recognize old aliases copied mechanically from generated path metadata."""
    expected = metadata_values(keywords or [], tags or [])
    actual = metadata_values(aliases or [])
    if not expected or actual != expected:
        return False
    return any(
        not is_valid_generated_metadata(value)
        for value in [*(keywords or []), *(tags or []), *(aliases or [])]
    )



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


def _note_relative_target(path: Path) -> str:
    """返回分类断点可稳定跳转的 vault 相对目标。"""
    try:
        return path.resolve().relative_to(VAULT_ROOT).with_suffix("").as_posix()
    except ValueError:
        return path.stem


def _frontmatter_string(text: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}:\s*"([^"]*)"', text or "", re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(rf"^{re.escape(key)}:\s*([^\n]+)", text or "", re.MULTILINE)
    return match.group(1).strip().strip('"') if match else ""


def _upsert_frontmatter_string(text: str, key: str, value: str) -> str:
    """更新断点 frontmatter 中的单值字段，保留其余正文。"""
    line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    if text.startswith("---\n"):
        return text.replace("\n---\n", f"\n{line}\n---\n", 1)
    return f"---\n{line}\n---\n\n{text.lstrip()}"


def _checkpoint_category(ctx: dict) -> str:
    """以会话标题为主、完整对话为辅地分配稳定分类。"""
    title = str(ctx.get("topic", "")).lower()
    details = " ".join([
        " ".join(str(item) for item in ctx.get("user_prompts", [])),
        " ".join(str(item) for item in ctx.get("projects", [])),
        " ".join(str(item) for item in ctx.get("external_projects", [])),
    ]).lower()
    winner = "其他会话"
    winner_score = 0
    for category, keywords in CHECKPOINT_CATEGORY_RULES:
        title_hits = sum(1 for keyword in keywords if keyword.lower() in title)
        detail_hits = sum(min(details.count(keyword.lower()), 2) for keyword in keywords)
        # 标题代表用户可见的会话主线，正文中的 checkpoint 等通用词只作为辅助证据。
        score = title_hits * 20 + detail_hits
        if score > winner_score:
            winner = category
            winner_score = score
        elif score == winner_score and score and winner == "其他会话":
            winner = category
    return winner


def _rollouts_by_session() -> dict:
    """建立 session ID 到最新 rollout 的索引，供手动全量分类复用。"""
    if not CODEX_SESSIONS_DIR.is_dir():
        return {}
    rollouts = {}
    for path in CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"):
        session_id = _session_id_from_transcript_path(str(path))
        if not session_id:
            continue
        previous = rollouts.get(session_id)
        try:
            if previous is None or path.stat().st_mtime > previous.stat().st_mtime:
                rollouts[session_id] = path
        except OSError:
            continue
    return rollouts


def _checkpoint_note_category_context(note_path: Path, text: str, rollouts: dict) -> tuple[dict, bool]:
    """手动分类优先解析原始 rollout，缺失时回退到断点的有效内容。"""
    session_id = _frontmatter_string(text, "session_id")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    note_title = title_match.group(1).strip() if title_match else note_path.stem
    rollout = rollouts.get(session_id)
    if rollout:
        ctx = extract_session_context(str(rollout))
        if ctx.get("user_prompts") or ctx.get("assistant_updates") or ctx.get("topic"):
            # 手动 checkpoint 会将 H1 更新为对用户可读的会话总结；它比末尾的 /checkpoint
            # 调用或确认语更能代表分类主线，完整 rollout 仍用于补足关键词。
            if note_title:
                ctx["topic"] = note_title
            ctx["projects"] = set(ctx.get("projects", set())) | set(read_frontmatter_list(note_path, "projects"))
            ctx["external_projects"] = set(ctx.get("external_projects", set())) | set(
                read_frontmatter_list(note_path, "external_projects")
            )
            return ctx, True

    sections = []
    for heading in ("会话目标演进", "可直接续接的结论", "已完成事项", "实际产出"):
        match = re.search(
            rf"^##\s+{re.escape(heading)}\n+([\s\S]*?)(?=\n##\s+|\Z)",
            text,
            re.MULTILINE,
        )
        if match:
            sections.append(match.group(1).strip())
    return {
        "topic": note_title,
        "user_prompts": sections,
        "projects": set(read_frontmatter_list(note_path, "projects")),
        "external_projects": set(read_frontmatter_list(note_path, "external_projects")),
    }, False


def _available_category_path(note_path: Path, category: str, session_id: str) -> Path:
    """为移动后的断点保留原文件名；冲突时追加 session ID，不覆盖已有笔记。"""
    category_dir = NOTE_DIR / sanitize_filename(category)
    category_dir.mkdir(parents=True, exist_ok=True)
    candidate = category_dir / note_path.name
    if candidate.resolve() == note_path.resolve() or not candidate.exists():
        return candidate
    suffix = sanitize_filename(session_id[:8] or "session")
    candidate = category_dir / f"{note_path.stem}-{suffix}.md"
    sequence = 2
    while candidate.exists() and candidate.resolve() != note_path.resolve():
        candidate = category_dir / f"{note_path.stem}-{suffix}-{sequence}.md"
        sequence += 1
    return candidate


def _replace_wikilink_targets(text: str, replacements: dict) -> str:
    """仅替换确切的 Obsidian 链接目标，保留别名和标题锚点。"""
    result = text
    for old_target, new_target in sorted(replacements.items(), key=lambda item: -len(item[0])):
        if not old_target or old_target == new_target:
            continue
        pattern = re.compile(
            r"\[\[" + re.escape(old_target)
            + r"(?P<anchor>#[^|\\\]]*)?(?P<alias>(?:\\)?\|[^\]]+)?\]\]"
        )
        result = pattern.sub(
            lambda match: f"[[{new_target}{match.group('anchor') or ''}{match.group('alias') or ''}]]",
            result,
        )
    return result


def _checkpoint_title_key(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    text = re.sub(r"^[#>*-]+\s*", "", text)
    return text.strip(" ，。；;：:!?！？")


def _checkpoint_titles_match(left: str, right: str) -> bool:
    left_key = _checkpoint_title_key(left)
    right_key = _checkpoint_title_key(right)
    return bool(left_key and right_key and left_key == right_key)


def _is_checkpoint_receipt(text: str) -> bool:
    """排除 checkpoint、分类和索引写入完成后的执行回执。"""
    cleaned = re.sub(r"\[[^\]]+\]\([^)]*\)", "", str(text or "").strip())
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return bool(re.match(
        r"^(?:\[obsidian-hook\]|"
        r"(?:本次对话|当前会话)?已写入恢复断点|"
        r"本次对话已写入|"
        r"正在生成当前会话断点|"
        r"全量分类完成|"
        r"(?:Manual classification complete|Session checkpoint written|Daily index updated))",
        cleaned,
        re.IGNORECASE,
    ))


def _is_usable_checkpoint_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(title or "").strip())
    if not 4 <= len(normalized) <= 80:
        return False
    if _is_low_signal_topic(normalized) or _is_checkpoint_receipt(normalized):
        return False
    if re.match(r"^(?:新标签页|New chat|Untitled|未命名|第[一二三四五六七八九十0-9]+轮)", normalized, re.IGNORECASE):
        return False
    return True


def _title_matches_user_prompt(title: str, prompts) -> bool:
    return any(_checkpoint_titles_match(title, prompt) for prompt in prompts or [])


def _is_raw_prompt_title(title: str, prompts) -> bool:
    """长问句和上下文指代语属于机械标题；简洁任务名仍可保留。"""
    if not _title_matches_user_prompt(title, prompts):
        return False
    normalized = re.sub(r"\s+", " ", str(title or "").strip())
    if len(normalized) <= 24 and not re.search(r"(?:为什么|怎么|如何|是否|能不能|可以吗|吗|？|\?)", normalized):
        return False
    return True


def _is_context_dependent_title(title: str) -> bool:
    """筛出依赖上文才能理解的答案句，避免它们替代整个会话标题。"""
    normalized = re.sub(r"\s+", " ", str(title or "").strip())
    if re.match(r"^(?:之前|当前|这次|那(?:个|为什么|怎么)|为什么|怎么|如何|服务端返回|原来)", normalized):
        return True
    return bool(re.search(r"(?:user quota is not enough|已写入恢复断点|全量分类完成)", normalized, re.IGNORECASE))


def _has_descriptive_thread_title(ctx: dict) -> bool:
    title = str(ctx.get("thread_title", "")).strip()
    prompts = ctx.get("user_prompts", [])
    first_prompt = prompts[0] if prompts else ""
    return _is_usable_checkpoint_title(title) and not _checkpoint_titles_match(title, first_prompt)


def _recovery_terms(text: str) -> set[str]:
    words = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", str(text or "").lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        words.update(segment[index:index + 2] for index in range(max(len(segment) - 1, 0)))
    return words


def _assistant_recovery_candidates(updates, user_prompts=None) -> list[tuple[int, int, str]]:
    """从完整会话中选出可验证的助手结论，排除进度播报和运行回执。"""
    candidates = []
    total = max(len(updates or []), 1)
    context_terms = _recovery_terms(" ".join(user_prompts or []))
    for index, raw_text in enumerate(updates or []):
        text = _short_resume_text(raw_text, 900)
        if len(text) < 6 or _is_checkpoint_receipt(text):
            continue
        lead = re.sub(r"^[\s>*#-]+", "", text).strip()
        if re.match(r"^(?:我会|现在会|接下来会|正在|随后会|I will(?:\b|$))", lead, re.IGNORECASE):
            continue
        score = int(index * 6 / total)
        if re.search(r"(?:根因|结论|原因|说明|因此|已(?:完成|配置|注册|验证|修复|同步|写入)|已经|当前|成功|失败|无法|限制|问题)", text):
            score += 18
        if context_terms:
            shared_terms = len(_recovery_terms(text) & context_terms)
            if shared_terms:
                score += min(shared_terms, 5) * 3
            else:
                # 跨项目的历史说明会被错误拼入当前会话时，不能抢占恢复摘要。
                score -= 18
        if re.search(r"(?:已发现并复用(?:长期经验|\s*AI开发参考)|Script completed|Wall time)", text):
            score -= 30
        candidates.append((score, index, text))
    return candidates


def _summary_title(summary: str, limit: int = 60) -> str:
    """从可直接续接的助手结论提取一行会话标题。"""
    if not summary:
        return ""
    cleaned = _short_resume_text(summary, 900)
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("```", "#", "- [[", "[obsidian-hook]", "（尚未提取")):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\*\*[^*]+\*\*[:：]\s*", "", line)
        line = re.sub(r"^是[，,]\s*", "", line)
        line = re.sub(r"\[[^\]]+\]\([^)]*\)", "", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.split(r"(?<=[。！？!?])\s*", line)[0].strip(" 。；;：:")
        if _is_checkpoint_receipt(line) or re.match(r"^Obsidian 仓库路径已确认", line):
            continue
        if re.match(r"^(?:第[一二三四五六七八九十0-9]+题|问题[一二三四五六七八九十0-9]*)[：:]", line):
            continue
        if 6 <= len(line) <= limit * 2 and not re.match(r"^(?:我会|现在会|接下来会|正在|随后会)", line):
            return line[:limit].rstrip(" ，。；;：:")
    return ""


def _checkpoint_summary_title(ctx: dict) -> str:
    """没有可用会话标题时，以最强的助手结论生成标题。"""
    candidates = _assistant_recovery_candidates(
        ctx.get("assistant_updates") or [ctx.get("latest_assistant_update", "")],
        ctx.get("user_prompts", []),
    )
    for _score, _index, text in sorted(candidates, reverse=True):
        title = _summary_title(text)
        if _is_usable_checkpoint_title(title):
            return title
    return ""


def _preferred_checkpoint_title(ctx: dict, synthesized_topic: str = "") -> tuple[str, str]:
    """标题优先级：用户可见会话标题、助手结论、全局主题推断。"""
    if _has_descriptive_thread_title(ctx):
        return str(ctx["thread_title"]).strip(), "thread"
    summary_title = _checkpoint_summary_title(ctx)
    if _is_usable_checkpoint_title(summary_title):
        return summary_title, "assistant"
    if _is_usable_checkpoint_title(synthesized_topic):
        return synthesized_topic.strip(), "inferred"
    fallback = str(ctx.get("topic", "")).strip()
    return (fallback or "未命名"), "inferred"


def _should_refresh_checkpoint_title(
    existing_title: str,
    existing_text: str,
    ctx: dict,
    refresh_title: bool,
    keep_title: bool,
) -> bool:
    if keep_title or not refresh_title:
        return False
    baseline = _frontmatter_string(existing_text, "title_baseline")
    source = _frontmatter_string(existing_text, "title_source")
    # H1 与记录的自动标题不同，说明用户在 Obsidian 中改过标题。
    if baseline and not _checkpoint_titles_match(existing_title, baseline):
        return False
    # 自动标题同样保持稳定；手动 checkpoint 只处理明显错误的标题。
    requires_repair = (
        not _is_usable_checkpoint_title(existing_title)
        or _is_checkpoint_receipt(existing_title)
        or _is_raw_prompt_title(existing_title, ctx.get("user_prompts", []))
        or _is_context_dependent_title(existing_title)
    )
    if source in {"thread", "assistant", "inferred", "preserved", "manual"}:
        return requires_repair
    # 旧版没有来源字段时，也只修复回执、问句和依赖上下文的答案句。
    return requires_repair


def _renamed_checkpoint_path(note_path: Path, title: str, session_id: str) -> Path:
    filename = sanitize_filename(title)
    candidate = note_path.parent / f"{filename}.md"
    if candidate.resolve() == note_path.resolve() or not candidate.exists():
        return candidate
    suffix = sanitize_filename(session_id[:8] or "session")
    candidate = note_path.parent / f"{filename}-{suffix}.md"
    sequence = 2
    while candidate.exists() and candidate.resolve() != note_path.resolve():
        candidate = note_path.parent / f"{filename}-{suffix}-{sequence}.md"
        sequence += 1
    return candidate


def _repair_checkpoint_links(replacements: dict) -> None:
    """断点改名或分类移动后同步 vault 内的路径型链接和默认恢复入口。"""
    if not replacements:
        return
    for markdown_path in VAULT_ROOT.rglob("*.md"):
        try:
            text = markdown_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        rewritten = _replace_wikilink_targets(text, replacements)
        for old_target, new_target in replacements.items():
            old_note = f'"default_note": "{old_target}.md"'
            new_note = f'"default_note": "{new_target}.md"'
            rewritten = rewritten.replace(old_note, new_note)
        if rewritten != text:
            markdown_path.write_text(rewritten, encoding="utf-8")


def _rename_checkpoint_note(note_path: Path, title: str, session_id: str) -> Path:
    target_path = _renamed_checkpoint_path(note_path, title, session_id)
    if target_path.resolve() == note_path.resolve():
        return note_path
    old_target = _note_relative_target(note_path)
    note_path.rename(target_path)
    _repair_checkpoint_links({old_target: _note_relative_target(target_path)})
    return target_path


def find_note_by_session(index_dir: Path, session_id: str):
    """在 NOTE_DIR 中按 frontmatter 的 session_id 查找已存在的断点笔记。"""
    for p in sorted(index_dir.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        m = re.search(r'^session_id:\s*"([^"]+)"', text, re.MULTILINE)
        if m and m.group(1) == session_id:
            return p
    return None


def read_frontmatter_list(path: Path, key: str):
    """读取笔记 frontmatter 里的 JSON、分隔文本或 YAML 列表字段。"""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    return parse_frontmatter_list(text, key)



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
        # 这是 retrieve 注入时的透明度提示，不属于会话结论；保留同一行其后的实际回答。
        line = re.sub(r"^\s*已发现并复用(?:长期经验|\s*AI开发参考)：[^。！？!?]*(?:[。！？!?]\s*)?", "", line)
        if not line.strip() or line.strip().startswith(("长期经验复用要求：", "AI开发参考复用要求：")):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    # 代码块被移除后，不能留下“命令如下：”这类没有后文的半句。
    cleaned = re.sub(
        r"(?:；|。)\s*(?:命令行(?:对应)?操作是|具体命令如下|执行命令如下)[：:]\s*(?=(?:当前|由于|因此|但|$))",
        "。",
        cleaned,
    )
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _assistant_resume_block(updates, user_prompts=None) -> str:
    """保留跨阶段的关键结论，让新会话可凭断点继续而非重读完整 transcript。"""
    candidates = _assistant_recovery_candidates(updates, user_prompts)
    if not candidates:
        return "（尚未提取到可用于续接的助手结论）"

    def terms(text: str) -> set[str]:
        return set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", text.lower()))

    ranked = sorted(candidates, reverse=True)
    score_floor = ranked[0][0] - 22
    eligible = [candidate for candidate in candidates if candidate[0] >= score_floor]
    selected = []
    selected_terms = []

    def add_candidate(candidate) -> None:
        candidate_terms = terms(candidate[2])
        if any(
            candidate_terms
            and selected_term
            and len(candidate_terms & selected_term) / max(len(candidate_terms | selected_term), 1) >= 0.72
            for selected_term in selected_terms
        ):
            return
        selected.append(candidate)
        selected_terms.append(candidate_terms)

    # 先从早、中、晚三个阶段各取一条强结论，避免末尾追问淹没已完成的主线。
    last_index = max(candidate[1] for candidate in candidates)
    phase_limits = (
        (0, max(0, round(last_index * 0.34))),
        (max(0, round(last_index * 0.34)) + 1, max(0, round(last_index * 0.68))),
        (max(0, round(last_index * 0.68)) + 1, last_index),
    )
    for start, end in phase_limits:
        scoped = [candidate for candidate in eligible if start <= candidate[1] <= end]
        if scoped:
            add_candidate(max(scoped, key=lambda item: (item[0], item[1])))
        if len(selected) == 3:
            break

    # 会话很短、某一阶段没有有效结论时，以全局得分补齐。
    for candidate in ranked:
        if candidate[0] < score_floor:
            continue
        add_candidate(candidate)
        if len(selected) == 3:
            break
    selected.sort(key=lambda item: item[1])
    return "\n\n".join(_short_resume_text(item[2], 650) for item in selected)


def _session_goal_block(prompts) -> str:
    """记录初始目标、关键推进与最新目标，保留会话方向而非末尾三句。"""
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
    concise = [
        item for item in normalized
        if len(item) <= 220
        and "```" not in item
        and not item.lstrip().startswith(("---", "# "))
    ] or normalized
    selected = [("初始目标", concise[0])]
    if len(concise) >= 4:
        for fraction in (0.34, 0.67):
            index = min(len(concise) - 2, max(1, round((len(concise) - 1) * fraction)))
            candidate = concise[index]
            if not any(_checkpoint_titles_match(candidate, existing) for _, existing in selected):
                selected.append(("关键推进", candidate))
    latest = concise[-1]
    if not any(_checkpoint_titles_match(latest, existing) for _, existing in selected):
        selected.append(("最新目标", latest))
    elif len(selected) == 1:
        selected[0] = ("当前目标", latest)
    return "\n\n".join(
        f"- **{label}**：{_short_resume_text(item, 180)}"
        for label, item in selected[:4]
    )


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
    """为 Markdown 表格生成显示紧凑且可点击的 Obsidian 链接。"""
    path = Path(file_path)
    try:
        rel = path.resolve().relative_to(VAULT_ROOT).with_suffix("")
        return f"[[{rel.as_posix()}\\|{path.stem}]]"
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
    document = document_match.group(1)
    if not (VAULT_ROOT / document).is_file():
        return {}
    return {
        "prompt_count": int(count_match.group(1)),
        "document": document,
    }


def generate_session_note(session_id: str, ctx: dict, status: str, related: list = None) -> str:
    now = vault_now()
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC+8")
    short_id = session_id[:12] if len(session_id) > 12 else session_id
    label = STATUS_MAP.get(status, {}).get("label", status)
    topic = ctx["topic"] or "(未提取到话题)"
    title_baseline = str(ctx.get("title_baseline") or topic).strip()
    title_source = str(ctx.get("title_source") or "inferred").strip()
    checkpoint_category = str(ctx.get("checkpoint_category", "")).strip()
    checkpoint_category_line = f'checkpoint_category: "{checkpoint_category}"\n' if checkpoint_category else ""
    keywords = ctx.get("keywords") or build_checkpoint_keywords(ctx.get("keywords"), ctx.get("tags"))
    aliases = ctx.get("aliases") or build_aliases(
        topic,
        None,
        ctx.get("tags"),
        keywords,
        ctx.get("aliases"),
    )
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
        ctx.get("assistant_updates") or [ctx.get("latest_assistant_update", "")],
        ctx.get("user_prompts", []),
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
            "- 优先读取涉及项目的单文件项目总结，再根据实际产出和下方结论继续。"
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
    return redact_sensitive_text(f"""---
date: "{now.strftime('%Y-%m-%d')}"
session_id: "{session_id}"
status: "{status}"
platform: "{platform}"
projects: {json.dumps(sorted(ctx['projects']), ensure_ascii=False)}
external_projects: {json.dumps(sorted(ctx.get('external_projects', [])), ensure_ascii=False)}
category: {json.dumps(ctx.get('category', []), ensure_ascii=False)}
{checkpoint_category_line}tags: {json.dumps(ctx.get('tags', []), ensure_ascii=False)}
keywords: {json.dumps(keywords, ensure_ascii=False)}
aliases: {json.dumps(aliases, ensure_ascii=False)}
title_baseline: {json.dumps(title_baseline, ensure_ascii=False)}
title_source: {json.dumps(title_source, ensure_ascii=False)}
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
""")


def _compact_index_text(text: str, limit: int = 42) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    compact = re.sub(r"[|\r\n]", " ", compact).strip()
    return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."


def _daily_index_header(index_date: str) -> str:
    return f"""---
date: "{index_date}"
tags:
  - {INDEX_TAG}
---

# 会话记录 - {index_date}

> 每日自动生成 · `{SPACE_NAME}/会话索引/`

| 时间 | 状态 | 话题 | 产出 |
| :--- | :---: | :--- | :--- |
"""


def _daily_index_marker(session_id: str, index_date: str) -> str:
    # 注释留在第四列，避免被 Markdown 当成第五个空白列。
    return f"<!-- session:{session_id} --> <!-- session-date:{index_date} -->"


def _daily_index_row_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    cells = []
    current = []
    wiki_depth = 0
    # 旧版曾生成没有结尾竖线的行；Markdown 仍会把它当成表格行。
    body = stripped[1:-1] if stripped.endswith("|") else stripped[1:]
    index = 0
    while index < len(body):
        char = body[index]
        pair = body[index:index + 2]
        if pair == "[[":
            wiki_depth += 1
            current.append(pair)
            index += 2
            continue
        if pair == "]]" and wiki_depth:
            wiki_depth -= 1
            current.append(pair)
            index += 2
            continue
        if char == "|" and wiki_depth == 0:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def _daily_index_link_label(target: str) -> str:
    """为表格内链接生成简短、稳定的显示标题。"""
    base_target = (target or "").split("#", 1)[0].strip()
    label = base_target.rsplit("/", 1)[-1].strip()
    return label or "笔记"


def _daily_index_safe_wikilinks(text: str) -> str:
    """表格别名使用转义竖线，保持可点击且不会被 Markdown 拆列。"""
    safe_text = text or ""
    # 将旧版未转义别名迁移为 Obsidian 可识别的安全别名。
    safe_text = re.sub(
        r"\[\[([^|\]]+)(?<!\\)\|([^\]]+)\]\]",
        lambda match: f"[[{match.group(1)}\\|{match.group(2)}]]",
        safe_text,
    )

    # 裸链接会展示完整 vault 路径，路径型链接改为紧凑标题。
    def compact_bare_link(match):
        target = match.group(1)
        if "/" not in target:
            return match.group(0)
        return f"[[{target}\\|{_daily_index_link_label(target)}]]"

    return re.sub(r"\[\[([^|\\\]]+)\]\]", compact_bare_link, safe_text)


def _normalize_daily_index_layout(index_path: Path) -> None:
    """将旧五列表格和超长未生成断点行压缩为统一四列。"""
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (FileNotFoundError, OSError):
        return
    rewritten = []
    for line in lines:
        cells = _daily_index_row_cells(line)
        if cells is None:
            rewritten.append(line)
            continue
        if cells and cells[0] == "时间":
            rewritten.append("| 时间 | 状态 | 话题 | 产出 |\n")
            continue
        if cells and all(re.fullmatch(r"[-: ]+", cell or "") for cell in cells):
            rewritten.append("| :--- | :---: | :--- | :--- |\n")
            continue
        if len(cells) < 4:
            rewritten.append(line)
            continue
        marker_comments = []
        for cell in cells[4:]:
            marker_comments.extend(re.findall(r"<!--\s*[^>]+-->", cell))
        cells = cells[:4]
        cells[2] = _daily_index_safe_wikilinks(cells[2])
        cells[3] = _daily_index_safe_wikilinks(cells[3])
        if marker_comments:
            cells[3] = (cells[3] + " " + " ".join(marker_comments)).strip()
        if "[[" not in cells[2]:
            cells[2] = _compact_index_text(cells[2])
        rewritten.append("| " + " | ".join(cells) + " |\n")
    index_path.write_text(redact_sensitive_text("".join(rewritten)), encoding="utf-8")


def _ensure_daily_index(index_path: Path) -> None:
    if not index_path.exists():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(redact_sensitive_text(_daily_index_header(index_path.stem)), encoding="utf-8")
        return
    _normalize_daily_index_layout(index_path)


def _index_row_date(line: str, fallback_date: str) -> str:
    matched = re.search(r"<!--\s*session-date:(\d{4}-\d{2}-\d{2})\s*-->", line)
    return matched.group(1) if matched else fallback_date


def _upsert_daily_index_entry(index_path: Path, session_id: str, index_date: str, entry: str) -> None:
    marker = f"<!-- session:{session_id} -->"
    lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
    matching_rows = [
        row_index
        for row_index, line in enumerate(lines)
        if marker in line
        and line.lstrip().startswith("|")
        and _index_row_date(line, index_path.stem) == index_date
    ]
    if not matching_rows:
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(redact_sensitive_text(entry))
        return
    selected_row = matching_rows[0]
    rewritten = []
    for row_index, line in enumerate(lines):
        if row_index == selected_row:
            rewritten.append(entry)
        elif row_index in matching_rows:
            continue
        else:
            rewritten.append(line)
    index_path.write_text(redact_sensitive_text("".join(rewritten)), encoding="utf-8")


def _remove_legacy_index_entries(index_dir: Path, session_id: str, keep_dates: set[str]) -> None:
    marker = f"<!-- session:{session_id} -->"
    for index_path in index_dir.glob("*.md"):
        try:
            lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (FileNotFoundError, OSError):
            continue
        rewritten = []
        changed = False
        for line in lines:
            legacy = (
                marker in line
                and line.lstrip().startswith("|")
                and "<!-- session-date:" not in line
            )
            if legacy and index_path.stem not in keep_dates:
                changed = True
                continue
            rewritten.append(line)
        if changed:
            index_path.write_text(redact_sensitive_text("".join(rewritten)), encoding="utf-8")


def _conversation_time_from_context(ctx: dict, fallback: datetime) -> datetime:
    conversation_time = _parse_rollout_time(ctx.get("conversation_started_at"))
    return conversation_time or fallback


def _daily_index_time_cell(conversation_time: datetime, update_time: datetime, index_date: str) -> str:
    if index_date == conversation_time.strftime("%Y-%m-%d") == update_time.strftime("%Y-%m-%d"):
        return (
            f"{conversation_time.strftime('%H:%M')}"
            f"<br><small>session 更新为 {update_time.strftime('%H:%M')}</small>"
        )
    # 跨日会话在首日和更新日采用同一种时间语义：第一行是 session
    # 更新时间，第二行保留原始对话起点，避免将跨日更新时间误读为首日时间。
    return (
        f"{update_time.strftime('%H:%M')}"
        f"<br><small>对话时间 {conversation_time.strftime('%m-%d %H:%M')}</small>"
    )


def update_daily_index(
    index_dir: Path,
    session_note_path: Path | None,
    session_id: str,
    ctx: dict,
    status: str,
    now: datetime | None = None,
):
    update_time = now.astimezone(VAULT_TIMEZONE) if now else vault_now()
    conversation_time = _conversation_time_from_context(ctx, update_time)
    conversation_date = conversation_time.strftime("%Y-%m-%d")
    update_date = update_time.strftime("%Y-%m-%d")
    emoji = STATUS_MAP.get(status, {}).get("emoji", "❓")
    knowledge_writes = _knowledge_write_paths(ctx) if session_note_path else []
    note_names = [_daily_index_link(path) for path in knowledge_writes if Path(path).is_file()]
    if len(note_names) > 2:
        note_names = note_names[:2] + [f"+{len(note_names) - 2}"]
    yield_str = " · ".join(note_names) if note_names else "—"
    if session_note_path:
        link_target = _note_relative_target(session_note_path)
        topic_cell = f"[[{link_target}\\|{session_note_path.stem}]]"
    else:
        topic = _compact_index_text(ctx.get("topic") or "未记录话题")
        round_count = int(ctx.get("round_count", 0))
        topic_cell = f"{topic}<br><small>未生成断点 {round_count}/{AUTO_CHECKPOINT_MIN_ROUNDS}</small>"

    target_dates = [conversation_date]
    if update_date != conversation_date:
        target_dates.append(update_date)

    # 旧版本把 session 标记放在第五列。每次写入前统一收敛为四列，
    # 这样跨日迁移和后续的状态、链接刷新都面对同一种表格结构。
    index_dir.mkdir(parents=True, exist_ok=True)
    for existing_index in index_dir.glob("*.md"):
        _normalize_daily_index_layout(existing_index)
    _remove_legacy_index_entries(index_dir, session_id, set(target_dates))
    for index_date in target_dates:
        index_path = index_dir / f"{index_date}.md"
        _ensure_daily_index(index_path)
        time_cell = _daily_index_time_cell(conversation_time, update_time, index_date)
        marker = _daily_index_marker(session_id, index_date)
        entry = f"| {time_cell} | {emoji} | {topic_cell} | {yield_str} {marker} |\n"
        _upsert_daily_index_entry(index_path, session_id, index_date, entry)


def collect_restart_candidates() -> list:
    """为首页生成默认恢复项，不单独维护重启事项文件。"""
    candidates = []
    for path in NOTE_DIR.rglob("*.md"):
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


def find_related_notes(tags: list, current_path: Path) -> list:
    """找 tag 重叠 ≥2 的已有笔记，返回 vault 相对链接目标。"""
    related = []
    for n in sorted(NOTE_DIR.rglob("*.md")):
        if n.resolve() == current_path.resolve():
            continue
        existing = read_frontmatter_list(n, "tags")
        overlap = sum(1 for t in tags if t in existing)
        if overlap >= 2:
            related.append(_note_relative_target(n))
    return related[:5]


def _repair_daily_index_links(index_dir: Path, replacements: dict):
    """分类移动后修复索引中指向旧断点路径的链接。"""
    if not replacements:
        return
    for index_path in index_dir.glob("*.md"):
        try:
            text = index_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        rewritten = _replace_wikilink_targets(text, replacements)
        if rewritten != text:
            index_path.write_text(redact_sensitive_text(rewritten), encoding="utf-8")


def organize_checkpoint_notes(current_note_path: Path | None = None) -> tuple[dict, dict]:
    """仅归类未分类断点、遗留顶层断点和当前被手动重新检查的会话。"""
    candidates = [
        *sorted(UNCLASSIFIED_CHECKPOINT_DIR.rglob("*.md")),
        *sorted(NOTE_DIR.glob("*.md")),
    ]
    if current_note_path is not None and current_note_path.is_file():
        candidates.append(current_note_path)
    note_paths = []
    seen_paths = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        note_paths.append(path)
    rollouts = _rollouts_by_session()
    final_paths = {}
    moved_pairs = []
    category_counts = {}
    transcript_backed = 0
    skipped = 0

    for note_path in note_paths:
        try:
            text = note_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        session_id = _frontmatter_string(text, "session_id")
        if not session_id:
            skipped += 1
            continue
        ctx, used_rollout = _checkpoint_note_category_context(note_path, text, rollouts)
        if used_rollout:
            transcript_backed += 1
        category = _checkpoint_category(ctx)
        category_counts[category] = category_counts.get(category, 0) + 1
        updated_text = _upsert_frontmatter_string(text, "checkpoint_category", category)
        if updated_text != text:
            note_path.write_text(redact_sensitive_text(updated_text), encoding="utf-8")
        target_path = _available_category_path(note_path, category, session_id)
        if target_path.resolve() != note_path.resolve():
            note_path.rename(target_path)
        moved_pairs.append((note_path, target_path))
        final_paths[session_id] = target_path

    replacements = {}
    target_by_stem = {}
    for old_path, new_path in moved_pairs:
        old_target = _note_relative_target(old_path)
        new_target = _note_relative_target(new_path)
        replacements[old_target] = new_target
        target_by_stem.setdefault(old_path.stem, set()).add(new_target)
    # 旧版本的关联会话和每日索引使用过纯文件名链接；仅在标题唯一时修复它们。
    for stem, targets in target_by_stem.items():
        if len(targets) == 1:
            replacements[stem] = next(iter(targets))

    _repair_checkpoint_links(replacements)

    return final_paths, {
        "scanned": len(moved_pairs),
        "moved": sum(1 for old_path, new_path in moved_pairs if old_path != new_path),
        "transcript_backed": transcript_backed,
        "skipped": skipped,
        "categories": category_counts,
    }


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
                    "可复用经验", "AI开发参考", "避坑清单", "下次同类项目流程", "当前能力",
                    "项目材料", "已验证闭环", "使用方式", "当前边界", "恢复入口"
                )
            },
        })
    return docs


def _project_doc_paths(project: str) -> list:
    """独立项目使用单个摘要文件；确认的父项目才使用目录摘要。"""
    group_summary = PROJECTS_DIR / project / PROJECT_SUMMARY_NAME
    if _is_confirmed_project_group(group_summary):
        return [group_summary]
    summary = _project_summary_path(project)
    return [summary] if summary.is_file() else []


def _collect_project_material(project: str, ctx: dict, session_note_path: Path) -> str:
    """收集项目归档、旧总结、当前断点，限制体积后交给 LLM。"""
    project_dir = PROJECTS_DIR / project
    parts = [f"项目名：{project}"]
    summary_path = (
        project_dir / PROJECT_SUMMARY_NAME
        if _is_confirmed_project_group(project_dir / PROJECT_SUMMARY_NAME)
        else _project_summary_path(project)
    )
    if summary_path.exists():
        parts.append("\n## 旧项目总结（用于增量更新）\n" + _read_text_limited(summary_path, 5000))

    if session_note_path and session_note_path.exists():
        parts.append("\n## 本次会话断点\n" + _read_text_limited(session_note_path, 4000))

    written_in_project = []
    for f in sorted(ctx.get("written_files", [])):
        try:
            p = Path(f)
            if p == _project_summary_path(project) or p.parent == project_dir:
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


def _frontmatter(
    title_tags: list,
    project: str,
    kind: str,
    session_ids: list[str] = None,
    keywords: list[str] = None,
    aliases: list[str] = None,
    **extra,
) -> str:
    today = vault_now().strftime("%Y-%m-%d")
    tags = [PLAN_TAG, "知识库/自动总结", kind] + [t for t in title_tags if t]
    unique_tags = metadata_values(tags)
    unique_keywords = metadata_values(keywords or [], limit=8)
    if not unique_keywords:
        unique_keywords = metadata_values(
            project,
            metadata_leaf_values(unique_tags),
            limit=8,
            filter_noise=True,
        )
    unique_aliases = metadata_values(aliases or [], limit=12)
    if not unique_aliases:
        unique_aliases = build_aliases(
            project,
            project,
            unique_tags,
            unique_keywords,
            ["项目总结", "AI开发参考", "经验摘要"],
        )
    extra_lines = "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in extra.items())
    return f"""---
date: {today}
project: {project}
session_ids: {json.dumps(sorted(set(session_ids or [])), ensure_ascii=False)}
tags: {json.dumps(unique_tags, ensure_ascii=False)}
keywords: {json.dumps(unique_keywords, ensure_ascii=False)}
aliases: {json.dumps(unique_aliases, ensure_ascii=False)}
{extra_lines}---
"""


def _fallback_project_summary(project: str, ctx: dict, session_note_path: Path) -> str:
    docs = _read_project_docs(project)
    prompts = _dedupe_items([f"- {_shorten_line(p, 120)}" for p in ctx.get("user_prompts", [])[:5]], 5) or ["- （未提取到用户提问）"]
    outputs = []
    for doc in docs:
        outputs.append(f"- {_knowledge_link(doc['path'])}")
    outputs = _dedupe_items(outputs, 8) or ["- （本次未新增项目归档）"]
    session_link = _knowledge_link(session_note_path) if session_note_path else "（无）"
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
                    target.append(f"- {_knowledge_link(doc['path'])}：{_shorten_line(cleaned)}")

    positioning = _dedupe_items(positioning, 4) or [
        f"- 本次项目目标：{_shorten_line((ctx.get('user_prompts') or ['未提取到'])[0], 180)}"
    ]
    status_items = _dedupe_items(status_items, 5)
    if not status_items:
        status_items = [
            f"- 最近断点：{session_link}",
            f"- 会话状态：{ctx.get('status', 'unknown')}",
        ]
    else:
        status_items.insert(0, f"- 最近断点：{session_link}")
        status_items = _dedupe_items(status_items, 6)

    assistant_conclusion = _short_resume_text(ctx.get("latest_assistant_update", ""), 500)
    decisions = _dedupe_items(decisions, 5) or [
        f"- 本轮结论：{assistant_conclusion}" if assistant_conclusion else "- 待补充：当前断点未提取到可复核的关键结论。"
    ]
    verified = _dedupe_items(verified, 6) or ["- 待补充：当前材料没有独立的验证证据。"]
    runtime_notes = _dedupe_items(runtime_notes, 5) or ["- 待补充：当前材料没有明确的部署或运行要点。"]
    experience = _dedupe_items(experience, 5) or ["- 待补充：当前材料尚不足以提炼项目经验。"]
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

- 先读本项目总结，快速恢复项目状态和当前缺口。
- 再读最近断点 {session_link} 和上方“相关笔记”，核对当前结论与实际产出。
- 继续实施时优先遵循“部署与运行要点”和“关键架构与决策”；没有项目文档时从断点的实际产出继续。

## 相关笔记

{chr(10).join(outputs)}
"""


def synthesize_project_summary(project: str, ctx: dict, session_note_path: Path) -> str:
    return _fallback_project_summary(project, ctx, session_note_path)


def update_project_knowledge(ctx: dict, session_note_path: Path):
    """自动链路只维护项目总结；AI开发参考由 synthesize 的显式授权流程写入。"""
    projects = sorted(ctx.get("projects", []))
    if not projects:
        return []
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    current_session_ids = read_frontmatter_list(session_note_path, "session_ids")
    if not current_session_ids:
        text = _read_text_limited(session_note_path, 1000)
        match = re.search(r'^session_id:\s*"([^"]+)"', text, re.MULTILINE)
        current_session_ids = [match.group(1)] if match else []

    # 同一会话命中多个独立项目时使用同一摘要，避免再次制造目录和重复文档。
    if len(projects) > 1:
        project = "、".join(projects)
        summary_path = next(
            (path for path in PROJECTS_DIR.glob("*.md")
             if set(read_frontmatter_list(path, "merged_projects")) == set(projects)),
            PROJECTS_DIR / f"{sanitize_filename(project)}.md",
        )
    else:
        project = projects[0]
        group_summary = PROJECTS_DIR / project / PROJECT_SUMMARY_NAME
        summary_path = group_summary if _is_confirmed_project_group(group_summary) else _project_summary_path(project)

    existing_sessions = read_frontmatter_list(summary_path, "session_ids")
    session_ids = sorted(set(existing_sessions + current_session_ids))
    summary_keywords = read_frontmatter_list(summary_path, "keywords")
    summary_aliases = read_frontmatter_list(summary_path, "aliases")
    if not summary_keywords:
        summary_keywords = metadata_values(
            ctx.get("keywords", []),
            project,
            metadata_leaf_values(ctx.get("tags", [])),
            limit=8,
            filter_noise=True,
        )
    if not summary_aliases:
        summary_aliases = build_aliases(
            project,
            project,
            ctx.get("tags", []),
            summary_keywords,
            None,
        )
    ctx_with_status = dict(ctx)
    ctx_with_status["status"] = ctx.get("status", "completed")
    summary_body = synthesize_project_summary(project, ctx_with_status, session_note_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    extra = {"merged_projects": projects} if len(projects) > 1 else {}
    if summary_path.name == PROJECT_SUMMARY_NAME and _is_confirmed_project_group(summary_path):
        extra["group_confirmed"] = True
        extra["children"] = read_frontmatter_list(summary_path, "children")
    summary_path.write_text(
        redact_sensitive_text(
            _frontmatter(
                ["项目总结"],
                project,
                "项目总结",
                session_ids,
                keywords=summary_keywords,
                aliases=summary_aliases,
                **extra,
            )
            + "\n" + summary_body.strip() + "\n"
        ),
        encoding="utf-8",
    )
    written = [summary_path]

    return written


def _vault_link(path: Path, label: str) -> str:
    try:
        rel = path.relative_to(VAULT_ROOT).with_suffix("")
        return f"[[{rel}|{label}]]"
    except ValueError:
        return f"[[{path.stem}|{label}]]"


def update_navigation_notes():
    """首页直接列出项目与经验，不再生成额外导航笔记。"""
    return


def _reference_document_paths() -> list[Path]:
    """首页优先列出 AI开发参考，并兼容尚未迁移的旧目录。"""
    paths = []
    canonical_stems = set()
    if EXPERIENCE_DIR.is_dir():
        for path in sorted(EXPERIENCE_DIR.glob("*.md")):
            paths.append(path)
            canonical_stems.add(path.stem)
    if LEGACY_EXPERIENCE_DIR.is_dir():
        for path in sorted(LEGACY_EXPERIENCE_DIR.glob("*.md")):
            if path.stem not in canonical_stems:
                paths.append(path)
    return paths


def update_dashboard():
    """更新知识库首页：概览/状态/大类/小类/待恢复列表。"""
    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    notes = list(NOTE_DIR.rglob("*.md"))
    total = len(notes)
    status_counts = {"completed": 0, "interrupted": 0, "incomplete_archive": 0, "archived": 0}
    tag_counts = {}
    cat_counts = {}
    pending_entries = []
    unarchived_entries = []
    project_entries = []
    experience_docs = []

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

    # 独立项目使用顶层单文件；目录只代表经用户确认的父项目拓扑。
    doc_count = 0
    if PROJECTS_DIR.is_dir():
        summaries = sorted(path for path in PROJECTS_DIR.glob("*.md") if path.name != "首页.md")
        for summary in summaries:
            title = _extract_h1(_read_text_limited(summary, 1200), summary.stem)
            project_entries.append(f"- {_vault_link(summary, title)}")
            doc_count += 1
        for group_summary in sorted(PROJECTS_DIR.glob(f"*/{PROJECT_SUMMARY_NAME}")):
            if not _is_confirmed_project_group(group_summary):
                continue
            title = _extract_h1(_read_text_limited(group_summary, 1200), group_summary.parent.name)
            project_entries.append(f"- {_vault_link(group_summary, title)}")
            children = [path for path in sorted(group_summary.parent.glob("*.md")) if path != group_summary]
            for child in children:
                project_entries.append(f"  - {_vault_link(child, _extract_h1(_read_text_limited(child, 800), child.stem))}")
                doc_count += 1
            doc_count += 1

    for experience in _reference_document_paths():
        title = _extract_h1(_read_text_limited(experience, 1200), experience.stem)
        experience_docs.append((experience, title))
    experience_entries = [f"- {_vault_link(path, title)}" for path, title in experience_docs]

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

恢复时读取所选断点和关联项目总结。AI开发参考存在匹配项时，回复会先向用户说明复用内容。"""

    latest_index = max(INDEX_DIR.glob("*.md"), default=None, key=lambda path: path.name)
    work_entry = _vault_link(latest_index, "Codex工作记录") if latest_index else "Codex工作记录暂无会话索引"
    if len(experience_docs) == 1:
        experience_entry = _vault_link(experience_docs[0][0], "AI开发参考")
    elif experience_entries:
        experience_entry = f"AI开发参考共 {len(experience_entries)} 篇，见下方列表"
    else:
        experience_entry = "暂无 AI开发参考"
    project_entry = project_entries[0][2:] if project_entries else "暂无项目总结"
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

- {experience_entry}
- {project_entry}
- {work_entry}
- [[Codex协同Obsidian工作流skill更新日志]]

## 重启事项

{restart_section}

## 项目

{chr(10).join(project_entries) if project_entries else '暂无项目文档'}

## AI开发参考

{chr(10).join(experience_entries) if experience_entries else '暂无 AI开发参考'}

## 待恢复会话

{chr(10).join(pending_entries) if pending_entries else '暂无待恢复会话'}

## 未归档方案

{chr(10).join(unarchived_entries) if unarchived_entries else '暂无未归档方案'}

## 标签

{" ".join(f'`{t}` ({c})' for t, c in hot_tags) if hot_tags else '暂无标签'}
"""
    (VAULT_ROOT / HOMEPAGE_NAME).write_text(redact_sensitive_text(dash), encoding="utf-8")
    _set_codex_root_order()


def _set_codex_root_order():
    """文件浏览器按修改时间排序时，保持 Codex 知识库入口的固定顺序。"""
    if PRODUCT_LABEL != "Codex":
        return
    paths = (
        VAULT_ROOT / HOMEPAGE_NAME,
        VAULT_ROOT / "AI开发参考",
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
              "manual_checkpoint": "--manual-checkpoint" in sys.argv,
              "refresh_title": "--refresh-title" in sys.argv,
              "keep_title": "--keep-title" in sys.argv,
              "platform": "codex", "hook_event_name": "", "hook_event_received": False}
    result["force"] = "--force" in sys.argv
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
            manual_checkpoint=result["manual_checkpoint"],
            refresh_title=result["refresh_title"],
            keep_title=result["keep_title"],
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
        result["hook_event_received"] = True
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
            _debug_log(
                "hook_event_rollout_missing_skip",
                hook_event_name=result["hook_event_name"],
                session=result["session"],
                cwd=result["cwd"],
            )
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
    """一趟读取断点的分类、检索 metadata 字段。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return [], [], [], []
    return (
        parse_frontmatter_list(text, "category"),
        parse_frontmatter_list(text, "tags"),
        parse_frontmatter_list(text, "keywords"),
        parse_frontmatter_list(text, "aliases"),
    )


def main():
    cli = _parse_cli()
    transcript_path, session_id, cwd = cli["transcript"], cli["session"], cli["cwd"]
    force = cli["force"]
    manual_checkpoint = cli.get("manual_checkpoint", False)
    refresh_title = cli.get("refresh_title", False)
    keep_title = cli.get("keep_title", False)
    platform = "codex"
    hook_event_name = cli.get("hook_event_name", "")
    _debug_log(
        "main_start",
        transcript=transcript_path,
        session=session_id,
        cwd=cwd,
        force=force,
        refresh_title=refresh_title,
        keep_title=keep_title,
        platform=platform,
        hook_event_name=hook_event_name,
    )

    if not transcript_path or not os.path.isfile(transcript_path):
        _debug_log(
            "skip_no_transcript",
            session=session_id,
            transcript=transcript_path,
            platform=platform,
            hook_event_name=hook_event_name,
        )
        print("[obsidian-hook] No transcript path available, skipping")
        sys.exit(0)
    if not VAULT_ROOT.is_dir() or not (VAULT_ROOT / ".obsidian").is_dir():
        _debug_log("skip_invalid_vault", vault_root=VAULT_ROOT, session=session_id, platform=platform)
        print(f"[obsidian-hook] Not an Obsidian vault: {VAULT_ROOT}, skipping")
        sys.exit(0)
    transcript_session_id = _session_id_from_transcript_path(transcript_path)
    if hook_event_name and session_id != "unknown" and transcript_session_id != session_id:
        _debug_log(
            "skip_session_transcript_mismatch",
            session=session_id,
            transcript_session=transcript_session_id,
            transcript=transcript_path,
            hook_event_name=hook_event_name,
        )
        print("[obsidian-hook] Hook session does not match rollout, skipping")
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
    os.makedirs(UNCLASSIFIED_CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    existing_note = find_note_by_session(NOTE_DIR, session_id)
    if (
        not force
        and not manual_checkpoint
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

    archive = _archive_metadata(existing_note) if existing_note else {}
    if archive and len(ctx.get("user_prompts", [])) <= archive["prompt_count"]:
        status = "archived"
        ctx["status"] = status
        ctx["knowledge_archived"] = True
        ctx["archived_prompt_count"] = archive["prompt_count"]
        ctx["archive_document"] = archive["document"]
    if existing_note:
        # 已有断点始终原地更新。标题只有在自动生成且明显需要修复时才变更，
        # H1 与 title_baseline 不同即视为用户在 Obsidian 中手动改名。
        session_note_path = existing_note
        try:
            existing_note_text = session_note_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            existing_note_text = ""
        existing_title = _extract_h1(existing_note_text, session_note_path.stem)
        synth = synthesize_topic_and_tags(ctx["user_prompts"], ctx["written_files"], ctx["projects"])
        preferred_title, preferred_source = _preferred_checkpoint_title(ctx, synth["topic"])
        if (
            _should_refresh_checkpoint_title(
                existing_title,
                existing_note_text,
                ctx,
                refresh_title,
                keep_title,
            )
            and _is_usable_checkpoint_title(preferred_title)
            and not _checkpoint_titles_match(existing_title, preferred_title)
        ):
            session_note_path = _rename_checkpoint_note(session_note_path, preferred_title, session_id)
            ctx["topic"] = preferred_title
            ctx["title_baseline"] = preferred_title
            ctx["title_source"] = preferred_source
        else:
            ctx["topic"] = existing_title or session_note_path.stem
            ctx["title_baseline"] = _frontmatter_string(existing_note_text, "title_baseline") or ctx["topic"]
            ctx["title_source"] = _frontmatter_string(existing_note_text, "title_source") or "preserved"
        existing_checkpoint_category = _frontmatter_string(existing_note_text, "checkpoint_category")
        if existing_checkpoint_category:
            ctx["checkpoint_category"] = existing_checkpoint_category
        # 常规刷新逐字段保留手工 metadata，只补齐尚未记录的字段。
        existing_category, existing_tags, existing_keywords, existing_aliases = _read_frontmatter_all(session_note_path)
        if not force and is_legacy_generated_path_metadata(
            existing_aliases,
            existing_keywords,
            existing_tags,
        ):
            existing_tags = metadata_values(existing_tags, filter_noise=True)
            existing_keywords = metadata_values(existing_keywords, filter_noise=True)
            existing_aliases = []
        if force:
            ctx["category"] = synth["category"]
            ctx["tags"] = synth["tags"]
            ctx["keywords"] = build_checkpoint_keywords(synth["keywords"], synth["tags"])
        else:
            ctx["category"] = existing_category or synth["category"]
            ctx["tags"] = existing_tags or synth["tags"]
            ctx["keywords"] = existing_keywords or build_checkpoint_keywords(synth["keywords"], ctx["tags"])
        ctx["aliases"] = existing_aliases
    else:
        # 新笔记优先采用 Codex 会话标题，再回退到完整对话中的助手结论。
        synth = synthesize_topic_and_tags(ctx["user_prompts"], ctx["written_files"], ctx["projects"])
        ctx["topic"], ctx["title_source"] = _preferred_checkpoint_title(ctx, synth["topic"])
        ctx["title_baseline"] = ctx["topic"]
        ctx["category"] = synth["category"]
        ctx["tags"] = synth["tags"]
        ctx["keywords"] = build_checkpoint_keywords(synth["keywords"], synth["tags"])
        ctx["aliases"] = []
        fname = sanitize_filename(ctx["topic"])
        candidate = UNCLASSIFIED_CHECKPOINT_DIR / f"{fname}.md"
        if candidate.exists():
            candidate = UNCLASSIFIED_CHECKPOINT_DIR / f"{fname}-{session_id[:8]}.md"
        session_note_path = candidate
    if not ctx.get("keywords"):
        ctx["keywords"] = build_checkpoint_keywords(ctx.get("keywords"), ctx.get("tags"))
    if not ctx.get("aliases"):
        ctx["aliases"] = build_aliases(
            ctx.get("topic"),
            None,
            ctx.get("tags"),
            ctx.get("keywords"),
            ctx.get("aliases"),
        )
    related = find_related_notes(ctx["tags"], session_note_path)
    note_content = generate_session_note(session_id, ctx, status, related)
    session_note_path.write_text(redact_sensitive_text(note_content), encoding="utf-8")
    _debug_log(
        "write_success",
        session=session_id,
        platform=platform,
        status=status,
        note_path=session_note_path,
        transcript=transcript_path,
    )
    if manual_checkpoint:
        categorized_paths, category_report = organize_checkpoint_notes(session_note_path)
        session_note_path = categorized_paths.get(session_id, session_note_path)
        category_details = ", ".join(
            f"{category}={count}" for category, count in sorted(category_report["categories"].items())
        ) or "无可分类会话"
        print(
            "[obsidian-hook] Manual classification complete: "
            f"scanned={category_report['scanned']}, moved={category_report['moved']}, "
            f"rollout_backed={category_report['transcript_backed']}, skipped={category_report['skipped']}; "
            f"{category_details}"
        )
    final_note_path = session_note_path.resolve()
    try:
        vault_relative_path = final_note_path.relative_to(VAULT_ROOT).as_posix()
        vault_relative_directory = final_note_path.parent.relative_to(VAULT_ROOT).as_posix() + "/"
    except ValueError:
        vault_relative_path = str(final_note_path)
        vault_relative_directory = str(final_note_path.parent) + os.sep
    print(f"[obsidian-hook] Session checkpoint written: {final_note_path}")
    print(
        "[obsidian-hook] Session checkpoint location: "
        f"vault-relative={vault_relative_path}; folder={vault_relative_directory}"
    )
    update_daily_index(INDEX_DIR, session_note_path, session_id, ctx, status)
    project_notes = update_project_knowledge(ctx, session_note_path)
    if project_notes:
        print("[obsidian-hook] Project knowledge updated: " + ", ".join(str(p) for p in project_notes))
    if ctx.get("external_written_files"):
        print("[obsidian-hook] External knowledge project written: " + ", ".join(sorted(ctx["external_written_files"])))
    update_dashboard()
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
