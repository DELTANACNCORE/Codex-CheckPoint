#!/usr/bin/env python3
"""Load a compact Obsidian recovery brief before Codex answers a new prompt."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

CODEX_ROOT = Path(__file__).resolve().parents[1]
if str(CODEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEX_ROOT))

from metadata import parse_frontmatter_list

if "--vault-root" in sys.argv:
    idx = sys.argv.index("--vault-root")
    if idx + 1 < len(sys.argv):
        os.environ["OBSIDIAN_VAULT"] = sys.argv[idx + 1]

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT", "~/obsidian/知识库")).expanduser().resolve()
WORK_DIR = VAULT_ROOT / "Codex工作记录"
NOTES_DIR = WORK_DIR / "会话断点"
PROJECTS_DIR = VAULT_ROOT / "项目总结"
REFERENCE_DIR = VAULT_ROOT / "AI开发参考"
LEGACY_REFERENCE_DIR = VAULT_ROOT / "长期经验总结"
HOMEPAGE = VAULT_ROOT / "知识库首页.md"
SEARCH_SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "search" / "search.py"
MAX_CONTEXT_CHARS = 2200
RECOVERY_SECTIONS = (
    "可直接续接的结论",
    "已完成事项",
    "当前状态与续接",
    "实际产出",
)
PROJECT_SECTIONS = ("项目定位", "当前状态", "后续恢复入口")
REFERENCE_SECTIONS = ("核心结论", "经典代码与配置", "常用指令", "操作方法", "完成路径", "避坑清单", "验收检查清单")
GENERIC_KEYWORDS = {
    "checkpoint", "codex", "hook", "obsidian", "知识库", "会话", "项目", "总结", "搜索", "检索",
}
REFERENCE_GENERIC_TERMS = GENERIC_KEYWORDS | {
    "长期经验", "经验", "ai开发参考", "开发参考", "参考", "更新", "配置", "操作", "服务", "系统", "工具", "工作流", "验证", "检查",
    "docker", "compose", "容器", "运维",
}
RECOVERY_INTENT = ("恢复", "继续", "接手", "上次", "重启", "断点", "checkpoint", "知识库", "项目总结")
DEFAULT_RESTART_INTENT = ("重启事项", "按重启", "继续上一个", "恢复上一个", "上次任务")
SEARCH_INTENT = RECOVERY_INTENT + ("查找", "搜索", "检索", "资料", "文档")
VERIFICATION_INTENT = ("测试", "验证", "检查", "诊断", "排查", "复测")
VERIFICATION_NOTICE = (
    "验证时效要求：当前任务包含检查、测试、验证或诊断。知识库中的历史结果只能作为待核对线索；"
    "执行前必须重新运行相关命令、检查当前环境，并在结果与历史结论不一致时以当前结果为准。"
)


def normalize_event(raw: str) -> dict:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(event, dict):
        return {}
    payload = event.get("payload")
    if isinstance(payload, dict) and payload.get("hook_event_name"):
        return payload
    return event


def is_meaningful_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if len(text) < 4 or text.startswith("/"):
        return False
    if text.startswith("[") and "](" in text:
        return False
    if "<system" in text.lower() or "<developer" in text.lower():
        return False
    return True


def user_request_text(prompt: str) -> str:
    """移除桌面端附带的引用标注，避免旧回复文本反向触发知识检索。"""
    text = str(prompt or "")
    request_marker = "## My request for Codex:"
    if request_marker in text:
        text = text.split(request_marker, 1)[1]
    text = re.sub(r"(?ms)^# Response annotations:.*?</response-annotations>\s*", "", text)
    text = re.sub(r"(?ms)<response-annotations>.*?</response-annotations>\s*", "", text)
    return text.strip()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def extract_list(text: str, key: str) -> list[str]:
    return parse_frontmatter_list(text, key)


def extract_frontmatter_string(text: str, key: str) -> str:
    matched = re.search(rf"^{re.escape(key)}:\s*\"?([^\n\"]+)\"?$", text, re.MULTILINE)
    return matched.group(1).strip() if matched else ""


def extract_value(text: str, key: str) -> str:
    matched = re.search(rf'^\*\*{re.escape(key)}\*\*:\s*(.+)$', text, re.MULTILINE)
    return matched.group(1).strip() if matched else ""


def extract_h1(text: str, fallback: str) -> str:
    matched = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return matched.group(1).strip() if matched else fallback


def extract_section(text: str, heading: str) -> str:
    matched = re.search(rf"^##\s+{re.escape(heading)}\n+([\s\S]*?)(?=\n##\s+|\Z)", text, re.MULTILINE)
    return matched.group(1).strip() if matched else ""


def clamp(text: str, limit: int) -> str:
    normalized = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def find_session_note(session_id: str) -> Path | None:
    if not session_id or not NOTES_DIR.is_dir():
        return None
    for path in NOTES_DIR.rglob("*.md"):
        text = read_text(path)
        matched = re.search(r'^session_id:\s*"([^"]+)"', text, re.MULTILINE)
        if matched and matched.group(1) == session_id:
            return path
    return None


def projects_for_note(text: str) -> list[str]:
    projects = []
    for key in ("projects", "external_projects"):
        for project in extract_list(text, key):
            if project not in projects:
                projects.append(project)
    return projects


def keywords_for(prompt: str, projects: list[str]) -> list[str]:
    keywords = list(projects)
    lowered = prompt.lower()
    for keyword in GENERIC_KEYWORDS:
        if keyword in lowered:
            keywords.append(keyword)
    for fragment in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_.-]{2,}", prompt):
        if fragment not in keywords:
            keywords.append(fragment)
    unique = []
    seen = set()
    for keyword in keywords:
        normalized = keyword.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique[:10]


def score_note(path: Path, text: str, keywords: list[str]) -> int:
    if not keywords:
        return 0
    title = extract_h1(text, path.stem).lower()
    aliases = " ".join(extract_list(text, "aliases")).lower()
    tags = " ".join(extract_list(text, "tags")).lower()
    projects = " ".join(projects_for_note(text)).lower()
    recovery = " ".join(extract_section(text, heading) for heading in RECOVERY_SECTIONS).lower()
    full_text = text.lower()
    score = 0
    for keyword in keywords:
        term = keyword.lower()
        score += title.count(term) * 14
        score += aliases.count(term) * 16
        score += projects.count(term) * 12
        score += tags.count(term) * 8
        score += recovery.count(term) * 4
        score += full_text.count(term)
    if re.search(r'^status:\s*"completed"', text, re.MULTILINE):
        score += 2
    return score


def best_matching_note(keywords: list[str]) -> Path | None:
    if not NOTES_DIR.is_dir():
        return None
    candidates = []
    for path in NOTES_DIR.rglob("*.md"):
        text = read_text(path)
        score = score_note(path, text, keywords)
        if score:
            try:
                modified = path.stat().st_mtime
            except OSError:
                modified = 0
            candidates.append((score, modified, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def default_restart_note() -> Path | None:
    """从知识库首页的重启事项区读取默认断点，不猜测项目名。"""
    text = read_text(HOMEPAGE)
    matched = re.search(r"<!--\s*codex-restart:\s*(\{.*?\})\s*-->", text)
    if not matched:
        return None
    try:
        metadata = json.loads(matched.group(1))
        path = (VAULT_ROOT / str(metadata.get("default_note", ""))).resolve()
        path.relative_to(VAULT_ROOT)
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    return path if path.is_file() else None


def render_note_brief(path: Path) -> tuple[str, list[str]]:
    text = read_text(path)
    if not text:
        return "", []
    title = extract_h1(text, path.stem)
    status = extract_value(text, "状态")
    blocks = [f"### 会话断点：{title}"]
    if status:
        blocks.append(f"状态：{status}")
    for heading in RECOVERY_SECTIONS:
        section = extract_section(text, heading)
        if section:
            limits = {
                "可直接续接的结论": 650,
                "已完成事项": 280,
                "当前状态与续接": 280,
                "实际产出": 260,
            }
            blocks.append(f"#### {heading}\n{clamp(section, limits[heading])}")
    return clamp("\n\n".join(blocks), 1500), projects_for_note(text)


def project_summary_path(project: str) -> Path:
    direct = PROJECTS_DIR / f"{project}.md"
    if direct.is_file():
        return direct
    grouped = PROJECTS_DIR / project / "项目总结.md"
    if grouped.is_file() and re.search(r"^group_confirmed:\s*true$", read_text(grouped), re.MULTILINE):
        return grouped
    return direct


def render_project_brief(projects: list[str]) -> str:
    for project in projects:
        path = project_summary_path(project)
        text = read_text(path)
        if not text:
            continue
        blocks = [f"### 项目总结：{extract_h1(text, project)}"]
        for heading in PROJECT_SECTIONS:
            section = extract_section(text, heading)
            if section:
                limits = {"项目定位": 220, "当前状态": 430, "后续恢复入口": 220}
                blocks.append(f"#### {heading}\n{clamp(section, limits[heading])}")
        return clamp("\n\n".join(blocks), 850)
    return ""


def match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").lower())


def is_specific_reference_term(value: str) -> bool:
    key = match_key(value)
    if key in REFERENCE_GENERIC_TERMS:
        return False
    return len(key) >= 3


def reference_match_score(path: Path, text: str, prompt: str) -> int:
    """AI开发参考只接受稳定身份词或多个特征词，避免通用运维词把无关项目带入。"""
    prompt_key = match_key(prompt)
    if not prompt_key:
        return 0

    project = extract_frontmatter_string(text, "project")
    aliases = extract_list(text, "aliases")
    strong_terms = [project, path.stem, *aliases]
    for term in strong_terms:
        key = match_key(term)
        if is_specific_reference_term(term) and key in prompt_key:
            return 100 + len(key)

    title = extract_h1(text, path.stem)
    tags = extract_list(text, "tags")
    weak_terms = []
    for term in [title, *tags]:
        key = match_key(term)
        if is_specific_reference_term(term) and key in prompt_key and key not in weak_terms:
            weak_terms.append(key)
    if len(weak_terms) < 2:
        return 0
    return sum(len(term) for term in weak_terms) + 20


def reference_note_paths() -> list[Path]:
    """优先读取 AI开发参考，并为未迁移的旧目录保留只读兼容。"""
    paths = []
    canonical_stems = set()
    if REFERENCE_DIR.is_dir():
        for path in sorted(REFERENCE_DIR.glob("*.md")):
            paths.append(path)
            canonical_stems.add(path.stem)
    if LEGACY_REFERENCE_DIR.is_dir():
        for path in sorted(LEGACY_REFERENCE_DIR.glob("*.md")):
            if path.stem not in canonical_stems:
                paths.append(path)
    return paths


def render_ai_development_references(prompt: str) -> str:
    """匹配 AI开发参考，并要求 Codex 在复用前向用户说明来源。"""
    if not prompt:
        return ""
    candidates = []
    for path in reference_note_paths():
        text = read_text(path)
        if not text:
            continue
        score = reference_match_score(path, text, prompt)
        if score:
            candidates.append((score, path, text))
    if not candidates:
        return ""
    blocks = []
    titles = []
    for _, path, text in sorted(candidates, key=lambda item: (-item[0], item[1].name))[:2]:
        title = extract_h1(text, path.stem)
        titles.append(title)
        parts = [f"### AI开发参考：{title}"]
        for heading in REFERENCE_SECTIONS:
            section = extract_section(text, heading)
            if section:
                parts.append(f"#### {heading}\n{clamp(section, 420)}")
        blocks.append("\n\n".join(parts))
    notice = (
        "AI开发参考复用要求：本轮回复开头先向用户说明“已发现并复用 AI开发参考："
        + "、".join(titles)
        + "”。随后才可使用下列内容；不得把它当作无提示的隐含上下文。"
    )
    return clamp(notice + "\n\n" + "\n\n".join(blocks), 900)


def recovery_brief(session_id: str, prompt: str) -> str:
    current_note = find_session_note(session_id)
    source = "当前会话断点"
    if current_note is None:
        if not any(marker in prompt.lower() for marker in RECOVERY_INTENT):
            return ""
        use_default = any(marker in prompt.lower() for marker in DEFAULT_RESTART_INTENT)
        current_note = default_restart_note() if use_default else best_matching_note(keywords_for(prompt, []))
        source = "知识库首页指定的默认断点" if use_default else "匹配到的历史会话断点"
    if current_note is None:
        return ""
    note_block, projects = render_note_brief(current_note)
    if not note_block:
        return ""
    project_block = render_project_brief(projects)
    body = f"来源：{source}\n\n{note_block}"
    if project_block:
        body += "\n\n" + project_block
    return clamp(body, MAX_CONTEXT_CHARS)


def search_knowledge(keywords: list[str]) -> str:
    """没有可读断点时保留旧的全库搜索作为兜底。"""
    if not keywords or not SEARCH_SCRIPT.is_file():
        return ""
    try:
        proc = subprocess.run(
            [sys.executable, str(SEARCH_SCRIPT), "--vault-root", str(VAULT_ROOT), "--limit", "2", *keywords],
            text=True,
            capture_output=True,
            check=False,
            timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    result = proc.stdout.strip()
    if not result or result == "没有找到相关内容。":
        return ""
    return clamp(result, MAX_CONTEXT_CHARS)


def should_search_knowledge(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    return any(marker in lowered for marker in SEARCH_INTENT)


def requires_live_verification(prompt: str) -> bool:
    lowered = (prompt or "").lower()
    if any(marker in lowered for marker in VERIFICATION_INTENT):
        return True
    return bool(re.search(r"\b(?:test|verify|check|diagnose|debug)\b", lowered))


def main() -> None:
    raw = sys.stdin.read()
    event = normalize_event(raw)
    if event.get("hook_event_name") != "UserPromptSubmit":
        return
    prompt = user_request_text(str(event.get("prompt", "") or ""))
    if not is_meaningful_prompt(prompt):
        return

    session_id = str(event.get("session_id", "") or "")
    keywords = keywords_for(prompt, [])
    reference = render_ai_development_references(prompt)
    result = recovery_brief(session_id, prompt)
    if result:
        if reference:
            result = clamp(f"{reference}\n\n{result}", MAX_CONTEXT_CHARS)
        context = (
            "以下是已从 Obsidian 读取的任务恢复包。若其中包含 AI开发参考，严格遵循其复用提示，"
            "先向用户说明再使用；只有恢复包缺少必要细节时才读取完整 rollout transcript：\n\n"
            f"{result}"
        )
    else:
        result = reference
        if not result and should_search_knowledge(prompt):
            result = search_knowledge(keywords)
        if not result:
            return
        context = (
            "以下是本轮任务先行读取的知识库结论。若包含 AI开发参考，严格遵循其复用提示，"
            "先向用户说明再使用；与当前问题无关时忽略：\n\n"
            f"{result}"
        )
    if requires_live_verification(prompt):
        context = VERIFICATION_NOTICE + "\n\n" + context
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
