#!/usr/bin/env python3
"""Synthesize Codex checkpoints into a higher-signal knowledge note."""

import argparse
from difflib import SequenceMatcher
import importlib.util
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


VAULT_TIMEZONE = ZoneInfo("Asia/Shanghai")
LINK_VAULT_ROOT: Path | None = None


SECTION_HEADINGS = [
    "背景",
    "项目定位",
    "可直接续接的结论",
    "已完成事项",
    "当前状态与续接",
    "会话目标演进",
    "最近会话脉络",
    "关键结论",
    "当前状态",
    "本轮完成",
    "新一轮进展",
    "最佳实践",
    "踩坑记录",
    "已验证结果",
    "仍未完成",
    "可复用经验",
    "避坑清单",
    "下次同类项目流程",
    "实际产出",
    "产出",
]

LOW_SIGNAL_TITLE_PATTERNS = (
    r"^请只回复一句",
    r"\bverify\b",
    r"\btrust\b",
    r"\bbypass\b",
)
CLEANUP_LOW_SIGNAL_TITLE_PATTERNS = (
    r"^__image_",
    r"^\[\$(?:checkpoint|synthesize|search)\]",
    r"^/(?:checkpoint|synthesize|search)(?:\s|$)",
    r"^(?:checkpoint|synthesize|search)\s*$",
    r"^(?:本次对话(?:项目)?已(?:写入|加入)|正在(?:写入|生成)).*",
    r"^(?:你这个感觉对|好的|可以|行|继续|重新开始|开始|完成|现在可用了吗|这个对话能用吗|那就先做第一步|请只回复(?:一句)?|第[一二三四五六七八九十0-9]+题|问题[一二三四五六七八九十0-9]*|verify|trust|bypass).*$",
)
LONG_SESSION_MIN_PROMPTS = 20
LONG_SESSION_MIN_CHARS = 12000


def parse_args():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project")
    group.add_argument("--tag")
    group.add_argument("--cluster", action="store_true")
    group.add_argument("--cleanup-checkpoints", action="store_true", help="扫描伪对话和重复断点，默认只输出候选")
    parser.add_argument("--cluster-project", help="确认聚类后写入的目标项目名")
    parser.add_argument("--confirm-cluster", action="store_true", help="确认用户明确要求按聚类范围写入")
    parser.add_argument("--title")
    parser.add_argument("--vault-root", default=str(Path("~/obsidian/知识库").expanduser()))
    parser.add_argument("--sessions-root", help="Codex rollout 根目录，默认使用 $CODEX_HOME/sessions")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--apply-cleanup", action="store_true", help="执行 --cleanup-checkpoints 的高置信清理")
    parser.add_argument("--long-term", action="store_true", help="评估或写入用户授权的长期经验总结")
    parser.add_argument("--user-approved", action="store_true", help="确认用户明确授权写入长期经验")
    parser.add_argument("--replace-approved", action="store_true", help="确认用户明确授权覆盖已有长期经验")
    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def source_link(path: Path) -> str:
    """为分类后的断点生成唯一的 vault 相对链接。"""
    if LINK_VAULT_ROOT is not None:
        try:
            relative = path.relative_to(LINK_VAULT_ROOT).with_suffix("").as_posix()
            return f"[[{relative}|{path.stem}]]"
        except ValueError:
            pass
    return f"[[{path.stem}]]"


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def cleanup_title_key(title: str) -> str:
    """将标题转换为适合严格比对的键，同时移除常见的副本后缀。"""
    normalized = normalize_space(title).lower()
    normalized = re.sub(r"^#\s*", "", normalized)
    normalized = re.sub(r"\.(?:md|markdown)$", "", normalized)
    normalized = re.sub(r"(?:\s*[-_]?)?(?:副本|复制|copy)(?:\s*\d+)?\s*$", "", normalized, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalized)


def cleanup_title_reason(title: str) -> str:
    """只依据标题识别明显不适合作为会话名的写入回执与交互碎片。"""
    cleaned = normalize_space(title)
    if not cleaned:
        return "标题为空"
    compact = re.sub(r"\s+", "", cleaned).lower()
    if any(re.match(pattern, cleaned, re.IGNORECASE) for pattern in CLEANUP_LOW_SIGNAL_TITLE_PATTERNS):
        return "标题属于技能调用、写入回执或确认语"
    if any(re.match(pattern, compact, re.IGNORECASE) for pattern in LOW_SIGNAL_TITLE_PATTERNS):
        return "标题属于低信息确认语"
    if len(cleaned) > 56 and re.search(r"(?:当前会话|本次对话|该条|说明|仍未|为什么|之后|因为)", cleaned):
        return "标题像原始进度消息，无法概括会话"
    return ""


def clamp_text(text: str, limit: int = 180) -> str:
    text = normalize_space(text)
    return text[: limit - 1].rstrip() + "…" if len(text) > limit else text


def is_placeholder_text(text: str) -> bool:
    normalized = normalize_space(text)
    if not normalized:
        return True
    placeholders = (
        "待补充",
        "当前材料不足",
        "当前材料已经聚合",
        "当前没有提取到新的明显缺口",
        "当前没有提取到独立的验证会话说明",
        "当前材料以断点为主",
        "（LLM 不可用",
    )
    return any(marker in normalized for marker in placeholders)


def extract_h1(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def extract_frontmatter_list(text: str, key: str) -> list[str]:
    m = re.search(rf"^{re.escape(key)}:\s*(\[.*\])", text, re.MULTILINE)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def extract_frontmatter_value(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*\"?([^\n\"]+)\"?$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_block(text: str, heading: str) -> str:
    m = re.search(rf"##\s+{re.escape(heading)}\n+([\s\S]*?)(?=\n##\s+|\Z)", text)
    return m.group(1).strip() if m else ""


def extract_terms(text: str) -> list[str]:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", text or "")
    unique = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique


def parse_items(block: str) -> list[str]:
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
        return [normalize_space(item) for item in items if normalize_space(item)]

    parts = re.split(r"\n\s*\n", block)
    parsed = [normalize_space(part) for part in parts if normalize_space(part)]
    return parsed


def dedupe_texts(items: list[str], limit: int | None = None) -> list[str]:
    seen = set()
    unique = []
    for item in items:
        key = normalize_space(re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", item))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if limit and len(unique) >= limit:
            break
    return unique


def build_record(path: Path, text: str) -> dict:
    sections = {heading: extract_block(text, heading) for heading in SECTION_HEADINGS}
    status_match = re.search(r'^status:\s*"([^"]+)"', text, re.MULTILINE)
    date_text = extract_frontmatter_value(text, "date")
    kind = "session" if "会话断点" in path.parts else "doc"
    return {
        "path": path,
        "text": text,
        "title": extract_h1(text, path.stem),
        "tags": extract_frontmatter_list(text, "tags"),
        "category": extract_frontmatter_list(text, "category"),
        "keywords": extract_frontmatter_list(text, "keywords"),
        "projects": extract_frontmatter_list(text, "projects"),
        "session_ids": extract_frontmatter_list(text, "session_ids"),
        "session_id": extract_frontmatter_value(text, "session_id"),
        "status": status_match.group(1) if status_match else "",
        "date": date_text,
        "kind": kind,
        "sections": sections,
        "context": sections.get("可直接续接的结论", "") or sections.get("会话目标演进", "") or sections.get("最近会话脉络", "") or sections.get("背景", "") or sections.get("项目定位", ""),
        "outputs": sections.get("实际产出", "") or sections.get("产出", "") or sections.get("已完成事项", "") or sections.get("关键结论", ""),
    }


def note_records(note_dir: Path) -> list[dict]:
    records = []
    for path in sorted(note_dir.rglob("*.md")):
        text = read_text(path)
        if not text:
            continue
        records.append(build_record(path, text))
    return records


def project_records(projects_dir: Path, project: str, target_title: str) -> list[dict]:
    records = []
    direct = projects_dir / f"{safe_filename(project)}.md"
    if direct.is_file():
        text = read_text(direct)
        if text:
            records.append(build_record(direct, text))
        return records
    project_dir = projects_dir / project
    group_summary = project_dir / "项目总结.md"
    if not (project_dir.is_dir() and re.search(r"^group_confirmed:\s*true$", read_text(group_summary), re.MULTILINE)):
        return records
    for path in sorted(project_dir.glob("*.md")):
        # 项目总结与自动合成都是派生结果，继续作为输入会形成递归引用。
        if path.stem == target_title or path.stem == "项目总结" or "自动合成" in path.stem:
            continue
        text = read_text(path)
        if not text:
            continue
        records.append(build_record(path, text))
    return records


def dedupe_records(records: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for record in records:
        key = str(record["path"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def default_sessions_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "sessions"
    return Path.home() / ".codex" / "sessions"


def rollout_session_ids(sessions_root: Path) -> set[str]:
    """只以 rollout 文件名确认会话存在，不读取完整私有会话内容。"""
    if not sessions_root.is_dir():
        return set()
    session_ids = set()
    pattern = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.IGNORECASE)
    for path in sessions_root.rglob("rollout-*.jsonl"):
        matched = pattern.search(path.stem)
        if matched:
            session_ids.add(matched.group(1))
    return session_ids


def checkpoint_substance(record: dict) -> str:
    """排除 frontmatter、时间和恢复提示，只比较真正的会话摘要内容。"""
    sections = record["sections"]
    blocks = [
        sections.get("可直接续接的结论", ""),
        sections.get("会话目标演进", ""),
        sections.get("实际产出", "") or sections.get("产出", ""),
    ]
    text = "\n".join(block for block in blocks if block)
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "", text).lower()
    return text[:12000]


def checkpoint_content_similarity(left: dict, right: dict) -> float:
    left_text = checkpoint_substance(left)
    right_text = checkpoint_substance(right)
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0
    if min(len(left_text), len(right_text)) < 80:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def checkpoint_titles_match(left: dict, right: dict) -> bool:
    left_key = cleanup_title_key(left["title"])
    right_key = cleanup_title_key(right["title"])
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if min(len(left_key), len(right_key)) < 8:
        return False
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.92


def has_matching_rollout(record: dict, known_session_ids: set[str]) -> bool:
    session_id = record.get("session_id", "")
    return bool(session_id and session_id in known_session_ids)


def checkpoint_quality(record: dict, known_session_ids: set[str]) -> tuple:
    substance = checkpoint_substance(record)
    return (
        int(has_matching_rollout(record, known_session_ids)),
        int(len(substance) >= 120),
        prompt_count(record["text"]),
        len(substance),
        len(record["text"]),
        str(record["path"]),
    )


def clean_title_candidate(value: str) -> str:
    candidate = normalize_space(value)
    candidate = re.sub(r"^[-*]\s+", "", candidate)
    candidate = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", candidate)
    candidate = re.sub(r"`([^`]+)`", r"\1", candidate)
    candidate = re.sub(r"^\*\*[^*]+\*\*[:：]\s*", "", candidate)
    candidate = re.split(r"(?<=[。！？!?])\s*", candidate)[0]
    candidate = candidate.strip(" 。；;：:")
    return candidate[:60]


def project_title(project: str) -> str:
    title = re.sub(r"[_-]+", " ", normalize_space(project))
    title = re.sub(r"(?i)checkpoint", "checkpoint", title)
    title = re.sub(r"(?i)codex", "Codex", title)
    title = re.sub(r"(?<=[A-Za-z])(?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])(?=[A-Za-z])", " ", title)
    return normalize_space(title)[:60]


def is_usable_title_candidate(candidate: str) -> bool:
    if not candidate or len(candidate) < 5 or len(candidate) > 60:
        return False
    if cleanup_title_reason(candidate):
        return False
    if candidate.startswith(("我会", "现在会", "接下来会", "正在", "随后会")):
        return False
    return "[$" not in candidate and "会话 ID" not in candidate


def suggest_checkpoint_title(record: dict) -> str:
    """真实会话的失真标题优先退回已记录项目，再从目标演进中选择可读标题。"""
    projects = dedupe_texts(record.get("projects", []))
    if len(projects) == 1:
        candidate = project_title(projects[0])
        if is_usable_title_candidate(candidate):
            return candidate

    goal_block = record["sections"].get("会话目标演进", "") or record["sections"].get("最近会话脉络", "")
    candidates = [clean_title_candidate(item) for item in parse_items(goal_block)]
    candidates = [candidate for candidate in candidates if is_usable_title_candidate(candidate)]
    if candidates:
        return max(enumerate(candidates), key=lambda item: (len(extract_terms(item[1])), len(item[1]), item[0]))[1]

    conclusion = record["sections"].get("可直接续接的结论", "")
    for sentence in re.split(r"(?<=[。！？!?])\s*", conclusion):
        candidate = clean_title_candidate(sentence)
        if is_usable_title_candidate(candidate) and not re.match(r"^(?:已发现并复用长期经验|本次对话已写入)", candidate):
            return candidate
    return ""


def cleanup_candidate_priority(action: str) -> int:
    return {"delete": 3, "rename": 2, "report": 1}.get(action, 0)


def add_cleanup_candidate(candidates: dict[str, dict], candidate: dict) -> None:
    key = str(candidate["record"]["path"])
    existing = candidates.get(key)
    if existing is None or cleanup_candidate_priority(candidate["action"]) > cleanup_candidate_priority(existing["action"]):
        candidates[key] = candidate


def cleanup_candidate(action: str, record: dict, reason: str, other: dict | None = None, new_title: str = "") -> dict:
    return {
        "action": action,
        "record": record,
        "reason": reason,
        "other": other,
        "new_title": new_title,
    }


def build_checkpoint_cleanup_candidates(records: list[dict], known_session_ids: set[str]) -> list[dict]:
    """产生可审阅候选。两条都能回查 rollout 的相似会话只做报告。"""
    candidates: dict[str, dict] = {}

    by_session_id: dict[str, list[dict]] = {}
    for record in records:
        session_id = record.get("session_id", "")
        if session_id:
            by_session_id.setdefault(session_id, []).append(record)
    for session_id, grouped in by_session_id.items():
        if len(grouped) < 2:
            continue
        canonical = max(grouped, key=lambda record: checkpoint_quality(record, known_session_ids))
        for record in grouped:
            if record is canonical:
                continue
            similarity = checkpoint_content_similarity(canonical, record)
            if similarity >= 0.92:
                add_cleanup_candidate(
                    candidates,
                    cleanup_candidate("delete", record, f"同一 session_id {session_id[:12]} 的重复副本，正文相似度 {similarity:.0%}", canonical),
                )
            else:
                add_cleanup_candidate(
                    candidates,
                    cleanup_candidate("report", record, f"同一 session_id {session_id[:12]} 出现内容不同的多份记录", canonical),
                )

    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            if left.get("session_id") and left.get("session_id") == right.get("session_id"):
                continue
            if not checkpoint_titles_match(left, right):
                continue
            similarity = checkpoint_content_similarity(left, right)
            if similarity < 0.92:
                add_cleanup_candidate(
                    candidates,
                    cleanup_candidate("report", right, f"标题与“{left['title']}”重复，但正文相似度仅 {similarity:.0%}", left),
                )
                continue
            canonical = max((left, right), key=lambda record: checkpoint_quality(record, known_session_ids))
            duplicate = right if canonical is left else left
            if not has_matching_rollout(duplicate, known_session_ids):
                add_cleanup_candidate(
                    candidates,
                    cleanup_candidate("delete", duplicate, f"标题和正文均重复，且没有匹配 rollout，正文相似度 {similarity:.0%}", canonical),
                )
            elif has_matching_rollout(canonical, known_session_ids):
                add_cleanup_candidate(
                    candidates,
                    cleanup_candidate("report", duplicate, f"两个真实会话标题和正文高度相似，正文相似度 {similarity:.0%}", canonical),
                )

    for record in records:
        existing = candidates.get(str(record["path"]))
        if existing and existing["action"] == "delete":
            continue
        reason = cleanup_title_reason(record["title"])
        if not reason:
            continue
        if not has_matching_rollout(record, known_session_ids):
            add_cleanup_candidate(candidates, cleanup_candidate("delete", record, f"{reason}，且没有匹配 rollout"))
            continue
        new_title = suggest_checkpoint_title(record)
        if new_title and cleanup_title_key(new_title) != cleanup_title_key(record["title"]):
            add_cleanup_candidate(candidates, cleanup_candidate("rename", record, reason, new_title=new_title))
        else:
            add_cleanup_candidate(candidates, cleanup_candidate("report", record, f"{reason}，但无法从现有摘要安全推导新标题"))

    action_order = {"delete": 0, "rename": 1, "report": 2}
    return sorted(candidates.values(), key=lambda item: (action_order[item["action"]], str(item["record"]["path"])))


def is_low_signal_session(record: dict) -> bool:
    if record["kind"] != "session":
        return False
    title = record["title"]
    if any(re.search(pattern, title, re.IGNORECASE) for pattern in LOW_SIGNAL_TITLE_PATTERNS):
        return True
    prompts = parse_items(record["sections"].get("会话目标演进", "") or record["sections"].get("最近会话脉络", "") or record["context"])
    if len(prompts) <= 1 and len(record["text"]) < 400:
        return True
    return False


def is_verification_session(record: dict) -> bool:
    title = record["title"].lower()
    return any(keyword in title for keyword in ("verify", "trust", "checkpoint", "正常信任", "最终验证"))


def score_record(record: dict, project: str, target_tokens: list[str]) -> int:
    score = 0
    joined = " ".join(
        [
            record["title"],
            record["text"],
            " ".join(record["tags"]),
            " ".join(record["keywords"]),
            " ".join(record["category"]),
        ]
    ).lower()
    if record["kind"] == "doc":
        score += 120
    if project and project.lower() in joined:
        score += 80
    if any(token and token.lower() in joined for token in target_tokens):
        score += 30
    if record["status"] == "completed":
        score += 15
    if "已验证结果" in record["sections"] and record["sections"]["已验证结果"]:
        score += 20
    if "仍未完成" in record["sections"] and record["sections"]["仍未完成"]:
        score += 20
    if is_low_signal_session(record):
        score -= 70
    if is_verification_session(record):
        score += 10
    return score


def project_identity_tokens(project: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]{2,}", project or "")
    expanded = []
    for token in tokens:
        expanded.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[\u4e00-\u9fff]{2,}", token))
    return [token.lower() for token in expanded if len(token) >= 2]


def record_matches_project(record: dict, project: str) -> bool:
    if project in record.get("projects", []):
        return True
    joined = " ".join(
        [record["title"], record["text"], " ".join(record["tags"]), " ".join(record["keywords"])]
    ).lower()
    if project.lower() in joined:
        return True
    identity_tokens = project_identity_tokens(project)
    return len({token for token in identity_tokens if token in joined}) >= 2


def select_records(records: list[dict], args, plans_dir: Path) -> tuple[str, list[dict], list[str]]:
    if args.project:
        project = args.project.strip()
        title = args.title or f"{project} 知识整理"
        project_docs = project_records(plans_dir, project, title)
        target_tokens = extract_terms(project)
        for doc in project_docs:
            target_tokens.extend(extract_terms(doc["title"]))
            target_tokens.extend(doc["tags"])
        target_tokens = [token for token in target_tokens if token]

        scored_notes = []
        for record in records:
            if not record_matches_project(record, project):
                continue
            score = score_record(record, project, target_tokens)
            if score <= 0:
                continue
            scored_notes.append((score, record))
        scored_notes.sort(key=lambda item: (-item[0], item[1]["title"]))

        selected = project_docs[:]
        selected.extend(record for _, record in scored_notes[: args.limit + 4])
        selected = dedupe_records(selected)

        strong_docs = [record for record in selected if record["kind"] == "doc"]
        strong_notes = [record for record in selected if record["kind"] == "session" and not is_low_signal_session(record)]
        evidence_notes = [record for record in selected if record["kind"] == "session" and is_verification_session(record)]
        # 单条短会话仍需要生成项目总结；只是在后续长度判断中不会建议长期经验。
        if not strong_docs and not strong_notes:
            strong_notes = [record for record in selected if record["kind"] == "session"][: args.limit]

        ordered = dedupe_records(strong_docs + strong_notes[: args.limit] + evidence_notes[:3])
        tags = dedupe_texts(["codex/方案", project, "知识合成"])
        return project, ordered, tags

    if args.tag:
        tag = args.tag.strip()
        selected = [r for r in records if tag in r["tags"] or tag in r["keywords"] or tag in r["category"]]
        selected = sorted(selected, key=lambda r: (r["kind"] != "doc", r["title"]))
        title = args.title or f"{tag} 知识整理"
        tags = ["codex/方案", tag, "知识合成"]
        return "知识合成", selected[: args.limit], tags

    best = []
    best_tags = []
    for idx, record in enumerate(records):
        current_tags = set(record["tags"])
        if not current_tags:
            continue
        cluster = [record]
        overlap_tags = set(current_tags)
        for other in records[idx + 1 :]:
            shared = current_tags.intersection(other["tags"])
            if len(shared) >= 2:
                cluster.append(other)
                overlap_tags.update(shared)
        if len(cluster) > len(best):
            best = cluster
            best_tags = sorted(overlap_tags)
    project = args.cluster_project.strip()
    tags = dedupe_texts(["codex/方案", project, "知识合成"] + best_tags[:4])
    return project, best[: args.limit], tags


def format_record_item(record: dict, text: str) -> str:
    return f"- {source_link(record['path'])}：{clamp_text(text)}"


def collect_section_from_records(records: list[dict], headings: list[str], limit: int, predicate=None) -> list[str]:
    items = []
    ordered = sorted(records, key=lambda r: (r["kind"] != "doc", r["title"]))
    for record in ordered:
        if predicate and not predicate(record):
            continue
        for heading in headings:
            block = record["sections"].get(heading, "")
            for item in parse_items(block):
                if is_placeholder_text(item):
                    continue
                items.append(format_record_item(record, item))
    return dedupe_texts(items, limit)


def collect_background(records: list[dict]) -> list[str]:
    items = []
    for record in sorted(records, key=lambda r: (r["kind"] != "doc", r["title"])):
        block = record["sections"].get("背景") or record["sections"].get("项目定位")
        parsed = parse_items(block)
        if block and parsed:
            candidate = parsed[0]
            if not is_placeholder_text(candidate):
                items.append(format_record_item(record, candidate))
            continue
        if record["kind"] == "session" and not is_low_signal_session(record):
            prompt_items = parse_items(record["sections"].get("会话目标演进", "") or record["sections"].get("最近会话脉络", "") or record["context"])
            if prompt_items:
                items.append(format_record_item(record, prompt_items[0]))
    return dedupe_texts(items, 5)


def collect_verified(records: list[dict]) -> list[str]:
    items = collect_section_from_records(records, ["已验证结果"], 8)
    if items:
        return items
    items = collect_section_from_records(records, ["关键结论", "本轮完成"], 8)
    return [item for item in items if re.search(r"验证|可用|支持|能|可以|真实", item)]


def collect_gaps(records: list[dict]) -> list[str]:
    items = collect_section_from_records(records, ["仍未完成", "踩坑记录", "避坑清单"], 8)
    if items:
        return items
    items = collect_section_from_records(records, ["关键结论", "当前状态"], 8)
    return [item for item in items if re.search(r"未|缺|问题|风险|污染|误判|差距", item)]


def collect_actions(records: list[dict]) -> list[str]:
    items = collect_section_from_records(records, ["最佳实践", "本轮完成", "新一轮进展", "下次同类项目流程"], 8)
    if items:
        return items
    return collect_section_from_records(records, ["可复用经验"], 6)


def collect_evidence(records: list[dict]) -> list[str]:
    items = []
    for record in records:
        if record["kind"] != "session":
            continue
        title = record["title"]
        if "bypass hook trust" in title.lower():
            items.append(f"- {source_link(record['path'])}：trust 放行前链路验证。")
        elif "normal trust verify" in title.lower() or "正常信任" in title:
            items.append(f"- {source_link(record['path'])}：正常信任模式写回验证。")
        elif "final cli verify" in title.lower():
            items.append(f"- {source_link(record['path'])}：CLI 最终写回验证。")
        elif "checkpoint" in title.lower():
            items.append(f"- {source_link(record['path'])}：手动 checkpoint 或断点写回验证。")
    return dedupe_texts(items, 5)


def synthesize_body(project: str, title: str, records: list[dict]) -> str:
    backgrounds = collect_background(records)
    verified = collect_verified(records)
    gaps = collect_gaps(records)
    actions = collect_actions(records)
    evidence = collect_evidence(records)
    related = dedupe_texts([f"- {source_link(record['path'])}" for record in records], 12)

    if not backgrounds:
        backgrounds = ["- 当前材料不足，缺少可直接复用的背景说明。"]
    if not verified:
        verified = ["- 当前材料已经聚合，但明确的验证结论仍需补写。"]
    if not gaps:
        gaps = ["- 当前没有提取到新的明显缺口，但仍需人工复核。"]
    if not actions:
        actions = ["- 当前材料以断点为主，后续应继续补项目文档和操作记录。"]
    if not evidence:
        evidence = ["- 当前没有提取到独立的验证会话说明。"]

    return (
        f"# {title}\n\n"
        f"## 背景概览\n\n" + "\n".join(backgrounds) + "\n\n"
        f"## 已验证能力\n\n" + "\n".join(verified) + "\n\n"
        f"## 当前缺口\n\n" + "\n".join(gaps) + "\n\n"
        f"## 实施路径\n\n" + "\n".join(actions) + "\n\n"
        f"## 验证证据\n\n" + "\n".join(evidence) + "\n\n"
        f"## 相关材料\n\n" + "\n".join(related) + "\n"
    )


def long_term_quality(records: list[dict]) -> tuple[list[str], dict]:
    """长期经验必须包含可验证的多类核心材料，不能由空泛总结构成。"""
    joined = "\n".join(record["text"] for record in records)
    signals = []
    if re.search(r"```[^\n]*\n[\s\S]+?```", joined):
        signals.append("经典代码或配置")
    if re.search(r"(?:^|\n)\s*(?:python3?|git|docker|curl|npm|pip|ssh|cd|rg|sed)\b", joined, re.IGNORECASE):
        signals.append("可执行指令")
    if collect_actions(records):
        signals.append("操作方法")
    if collect_verified(records):
        signals.append("验证证据")
    if collect_gaps(records):
        signals.append("风险或避坑")
    return dedupe_texts(signals), {"records": len(records), "signals": len(dedupe_texts(signals))}


def collect_code_blocks(records: list[dict]) -> list[str]:
    blocks = []
    for record in records:
        for block in re.findall(r"```[^\n]*\n([\s\S]*?)```", record["text"]):
            cleaned = block.strip()
            if cleaned:
                blocks.append(cleaned[:900])
    return dedupe_texts(blocks, 4)


def collect_commands(records: list[dict]) -> list[str]:
    commands = []
    for block in collect_code_blocks(records):
        for line in block.splitlines():
            command = line.strip()
            if re.match(r"(?:python3?|git|docker|curl|npm|pip|ssh|cd|rg|sed)\b", command):
                commands.append(command)
    return dedupe_texts(commands, 12)


def synthesize_long_term_body(project: str, title: str, records: list[dict]) -> str:
    code_blocks = collect_code_blocks(records)
    commands = collect_commands(records)
    conclusions = collect_verified(records) or collect_background(records)
    operations = collect_actions(records)
    pitfalls = collect_gaps(records)
    sources = dedupe_texts([f"- {source_link(record['path'])}" for record in records], 12)
    return (
        f"# {title}\n\n"
        "## 核心结论\n\n" + "\n".join(conclusions or ["- 待补充：来源材料未提供可验证的核心结论。"]) + "\n\n"
        "## 经典代码与配置\n\n" + ("\n\n".join(f"```text\n{block}\n```" for block in code_blocks) if code_blocks else "待补充：没有可复用的代码或配置。") + "\n\n"
        "## 常用指令\n\n" + ("\n".join(f"- `{command}`" for command in commands) if commands else "待补充：没有可复用的指令。") + "\n\n"
        "## 操作方法\n\n" + "\n".join(operations or ["- 待补充：没有可复用的操作方法。"]) + "\n\n"
        "## 完成路径\n\n" + "\n".join(f"{index}. {item.lstrip('- ').strip()}" for index, item in enumerate(operations, 1)) + "\n\n"
        "## 避坑清单\n\n" + "\n".join(pitfalls or ["- 待补充：没有已验证的风险或避坑记录。"]) + "\n\n"
        "## 来源\n\n" + "\n".join(sources) + "\n"
    )


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()[:120] or "知识整理"


def set_frontmatter_value(text: str, key: str, value: str) -> str:
    line = f"{key}: {value}"
    pattern = rf"^{re.escape(key)}:\s*.*$"
    if re.search(pattern, text, re.MULTILINE):
        return re.sub(pattern, line, text, count=1, flags=re.MULTILINE)
    return re.sub(r"^---\n", f"---\n{line}\n", text, count=1)


def vault_note_target(path: Path, vault_root: Path) -> str:
    try:
        return path.relative_to(vault_root).with_suffix("").as_posix()
    except ValueError:
        return ""


def replace_wikilink_targets(text: str, replacements: dict[str, str]) -> str:
    """只替换完整的 Obsidian 链接目标，保留别名和标题锚点。"""
    result = text
    for old_target, new_target in sorted(replacements.items(), key=lambda item: -len(item[0])):
        if not old_target or old_target == new_target:
            continue
        pattern = re.compile(r"\[\[" + re.escape(old_target) + r"(?P<anchor>#[^|\]]*)?(?P<alias>\|[^\]]+)?\]\]")
        result = pattern.sub(
            lambda match: f"[[{new_target}{match.group('anchor') or ''}{match.group('alias') or ''}]]",
            result,
        )
    return result


def checkpoint_link_targets(record: dict, vault_root: Path, records: list[dict]) -> set[str]:
    targets = {vault_note_target(record["path"], vault_root)}
    stem = record["path"].stem
    title = record["title"]
    if sum(other["path"].stem == stem for other in records) == 1:
        targets.add(stem)
    if title and sum(other["title"] == title for other in records) == 1:
        targets.add(title)
    return {target for target in targets if target}


def line_references_target(line: str, target: str) -> bool:
    pattern = r"\[\[" + re.escape(target) + r"(?:#[^|\]]*)?(?:\|[^\]]+)?\]\]"
    return bool(re.search(pattern, line))


def daily_index_topic_cell(line: str) -> str:
    cells = line.rstrip("\n").split("|")
    return cells[3] if len(cells) > 3 else ""


def remove_daily_index_entries(vault_root: Path, record: dict, records: list[dict]) -> int:
    index_dir = vault_root / "Codex工作记录" / "会话索引"
    if not index_dir.is_dir():
        return 0
    session_id = record.get("session_id", "")
    marker = f"<!-- session:{session_id} -->" if session_id else ""
    targets = checkpoint_link_targets(record, vault_root, records)
    removed = 0
    for index_path in index_dir.glob("*.md"):
        text = read_text(index_path)
        if not text:
            continue
        lines = text.splitlines(keepends=True)
        kept = []
        for line in lines:
            is_row = line.lstrip().startswith("|")
            is_marked = bool(marker and marker in line)
            is_linked = is_row and any(line_references_target(daily_index_topic_cell(line), target) for target in targets)
            if is_row and (is_marked or is_linked):
                removed += 1
                continue
            kept.append(line)
        rewritten = "".join(kept)
        if rewritten != text:
            index_path.write_text(rewritten, encoding="utf-8")
    return removed


def available_renamed_checkpoint_path(record: dict, new_title: str) -> Path:
    current_path = record["path"]
    candidate = current_path.with_name(f"{safe_filename(new_title)}.md")
    if candidate == current_path or not candidate.exists():
        return candidate
    suffix = safe_filename(record.get("session_id", "")[:8] or "session")
    numbered = current_path.with_name(f"{safe_filename(new_title)}-{suffix}.md")
    sequence = 2
    while numbered.exists() and numbered != current_path:
        numbered = current_path.with_name(f"{safe_filename(new_title)}-{suffix}-{sequence}.md")
        sequence += 1
    return numbered


def rewrite_vault_links_for_rename(vault_root: Path, replacements: dict[str, str]) -> None:
    for path in vault_root.rglob("*.md"):
        text = read_text(path)
        if not text:
            continue
        rewritten = replace_wikilink_targets(text, replacements)
        if rewritten != text:
            path.write_text(rewritten, encoding="utf-8")


def rewrite_renamed_checkpoint_aliases(vault_root: Path, target: str, old_title: str, new_title: str) -> None:
    """重命名断点后同步显示名，避免项目总结继续展示被清理的旧标题。"""
    if not target or not old_title or old_title == new_title:
        return
    pattern = re.compile(
        r"\[\[" + re.escape(target) + r"(?P<anchor>#[^|\]]*)?\|" + re.escape(old_title) + r"\]\]"
    )
    for path in vault_root.rglob("*.md"):
        text = read_text(path)
        if not text:
            continue
        rewritten = pattern.sub(
            lambda match: f"[[{target}{match.group('anchor') or ''}|{new_title}]]",
            text,
        )
        if rewritten != text:
            path.write_text(rewritten, encoding="utf-8")


def split_markdown_table_row(line: str) -> list[str]:
    """按表格分隔符拆行，保留 wikilink 别名内部的竖线。"""
    cells = []
    current = []
    inside_wikilink = False
    index = 0
    raw = line.rstrip("\n")
    while index < len(raw):
        if raw.startswith("[[", index):
            inside_wikilink = True
            current.append("[[")
            index += 2
            continue
        if raw.startswith("]]", index):
            inside_wikilink = False
            current.append("]]")
            index += 2
            continue
        char = raw[index]
        if char == "|" and not inside_wikilink:
            cells.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    cells.append("".join(current))
    return cells


def refresh_daily_index_link(vault_root: Path, session_id: str, new_path: Path) -> None:
    if not session_id:
        return
    index_dir = vault_root / "Codex工作记录" / "会话索引"
    if not index_dir.is_dir():
        return
    marker = f"<!-- session:{session_id} -->"
    new_target = vault_note_target(new_path, vault_root)
    if not new_target:
        return
    for index_path in index_dir.glob("*.md"):
        text = read_text(index_path)
        if not text or marker not in text:
            continue
        lines = text.splitlines(keepends=True)
        changed = False
        for index, line in enumerate(lines):
            if marker not in line or not line.lstrip().startswith("|"):
                continue
            cells = split_markdown_table_row(line)
            marker_index = next((position for position, cell in enumerate(cells) if marker in cell), -1)
            if marker_index < 5:
                continue
            output_cell = cells[marker_index - 1]
            rebuilt = cells[:3] + [f" [[{new_target}|{new_path.stem}]] ", output_cell, cells[marker_index]]
            lines[index] = "|".join(rebuilt) + "\n"
            changed = True
        if changed:
            index_path.write_text("".join(lines), encoding="utf-8")


def rename_checkpoint_note(vault_root: Path, record: dict, new_title: str, records: list[dict]) -> Path | None:
    current_path = record["path"]
    text = read_text(current_path)
    if not text:
        return None
    old_title = record["title"]
    updated = re.sub(r"^#\s+.+$", f"# {new_title}", text, count=1, flags=re.MULTILINE)
    aliases = dedupe_texts(extract_frontmatter_list(updated, "aliases") + ([old_title] if old_title else []))
    if aliases:
        updated = set_frontmatter_value(updated, "aliases", json.dumps(aliases, ensure_ascii=False))
    new_path = available_renamed_checkpoint_path(record, new_title)
    current_path.write_text(updated, encoding="utf-8")
    if new_path != current_path:
        current_path.rename(new_path)

    replacements = {vault_note_target(current_path, vault_root): vault_note_target(new_path, vault_root)}
    if sum(other["path"].stem == current_path.stem for other in records) == 1:
        replacements[current_path.stem] = vault_note_target(new_path, vault_root)
    if old_title and sum(other["title"] == old_title for other in records) == 1:
        replacements[old_title] = vault_note_target(new_path, vault_root)
    rewrite_vault_links_for_rename(vault_root, replacements)
    rewrite_renamed_checkpoint_aliases(vault_root, vault_note_target(new_path, vault_root), old_title, new_title)
    refresh_daily_index_link(vault_root, record.get("session_id", ""), new_path)
    return new_path


def cleanup_relative_path(record: dict, vault_root: Path) -> str:
    target = vault_note_target(record["path"], vault_root)
    return target or str(record["path"])


def print_checkpoint_cleanup_candidates(candidates: list[dict], vault_root: Path) -> None:
    if not candidates:
        print("未发现伪对话、重复断点或需要修正的标题。")
        return
    labels = {"delete": "删除候选", "rename": "重命名候选", "report": "人工复核"}
    for candidate in candidates:
        record = candidate["record"]
        line = f"{labels[candidate['action']]}: {cleanup_relative_path(record, vault_root)}"
        if candidate["action"] == "rename":
            line += f" -> {candidate['new_title']}"
        if candidate.get("other"):
            line += f"；对照：{candidate['other']['title']}"
        print(f"{line}；原因：{candidate['reason']}")


def run_checkpoint_cleanup(args, vault_root: Path, note_dir: Path) -> None:
    sessions_root = Path(args.sessions_root).expanduser().resolve() if args.sessions_root else default_sessions_root()
    records = note_records(note_dir)
    known_session_ids = rollout_session_ids(sessions_root)
    candidates = build_checkpoint_cleanup_candidates(records, known_session_ids)
    counts = {action: sum(candidate["action"] == action for candidate in candidates) for action in ("delete", "rename", "report")}
    matched = sum(has_matching_rollout(record, known_session_ids) for record in records)
    print(f"断点清理检查：扫描 {len(records)} 条断点，匹配 rollout {matched} 条，rollout 根目录：{sessions_root}")
    print(f"删除候选：{counts['delete']}；重命名候选：{counts['rename']}；人工复核：{counts['report']}。")
    print_checkpoint_cleanup_candidates(candidates, vault_root)
    if not args.apply_cleanup:
        print("本次仅生成候选，未修改任何断点或索引。确认后使用 --cleanup-checkpoints --apply-cleanup 执行。")
        return

    deleted = 0
    index_rows_removed = 0
    delete_paths = {
        str(candidate["record"]["path"])
        for candidate in candidates
        if candidate["action"] == "delete"
    }
    retained_session_records = {}
    for record in records:
        session_id = record.get("session_id", "")
        if session_id and str(record["path"]) not in delete_paths:
            retained_session_records.setdefault(session_id, record)
    for candidate in candidates:
        if candidate["action"] != "delete":
            continue
        record = candidate["record"]
        path = record["path"]
        if not path.exists():
            continue
        if record.get("session_id") not in retained_session_records:
            index_rows_removed += remove_daily_index_entries(vault_root, record, records)
        path.unlink()
        deleted += 1

    for session_id, record in retained_session_records.items():
        if any(candidate["record"].get("session_id") == session_id for candidate in candidates if candidate["action"] == "delete"):
            refresh_daily_index_link(vault_root, session_id, record["path"])

    renamed = 0
    for candidate in candidates:
        if candidate["action"] != "rename":
            continue
        if rename_checkpoint_note(vault_root, candidate["record"], candidate["new_title"], records):
            renamed += 1
    if deleted or renamed:
        refresh_dashboard(vault_root)
    print(f"清理完成：删除 {deleted} 条断点，重命名 {renamed} 条断点，移除 {index_rows_removed} 条索引记录。")


def prompt_count(text: str) -> int:
    matched = re.search(r"^\*\*已记录用户消息\*\*:\s*(\d+)", text, re.MULTILINE)
    return int(matched.group(1)) if matched else 0


def session_length_metrics(records: list[dict]) -> dict:
    sessions = [record for record in records if record["kind"] == "session"]
    prompts = sum(prompt_count(record["text"]) for record in sessions)
    chars = sum(len(record["text"]) for record in sessions)
    is_long = prompts >= LONG_SESSION_MIN_PROMPTS or chars >= LONG_SESSION_MIN_CHARS
    return {"sessions": len(sessions), "prompts": prompts, "chars": chars, "is_long": is_long}


def write_long_term_experience(args, vault_root: Path, project: str, selected: list[dict]) -> bool:
    """只有用户显式授权时才写入长期经验；项目总结已在调用前完成。"""
    signals, quality = long_term_quality(selected)
    print("长期经验质量评估：" + ("、".join(signals) if signals else "未发现有效核心材料"))
    print(f"材料数：{quality['records']}；有效类别：{quality['signals']}。")
    if not args.user_approved:
        print("项目总结已归档。长期经验仍需用户明确授权，当前未写入。")
        return False
    if quality["signals"] < 3:
        print("材料类别不足三类，依据用户强制授权继续写入长期经验。")
    experience_dir = vault_root / "长期经验总结"
    target_path = experience_dir / f"{safe_filename(project)}.md"
    if target_path.exists() and not args.replace_approved:
        print(f"已有长期经验：{target_path}。覆盖前需要用户明确授权，并加入 --replace-approved。")
        return False
    experience_dir.mkdir(parents=True, exist_ok=True)
    selected_session_ids = []
    for record in selected:
        if record["kind"] == "session" and record.get("session_id"):
            selected_session_ids.append(record["session_id"])
        selected_session_ids.extend(record.get("session_ids", []))
    frontmatter = (
        "---\n"
        f"date: {datetime.now(VAULT_TIMEZONE).strftime('%Y-%m-%d')}\n"
        f"project: {project}\n"
        "long_term_experience: true\n"
        "user_authorized: true\n"
        f"session_ids: {json.dumps(dedupe_texts(selected_session_ids), ensure_ascii=False)}\n"
        f"tags: {json.dumps(dedupe_texts(['长期经验总结', '核心知识', project]), ensure_ascii=False)}\n"
        "---\n\n"
    )
    title = args.title or f"{project} 长期经验总结"
    target_path.write_text(frontmatter + synthesize_long_term_body(project, title, selected), encoding="utf-8")
    print(f"长期经验路径: {target_path}")
    return True


def mark_source_sessions_archived(records: list[dict], target_path: Path, vault_root: Path) -> list[Path]:
    """把本次真实参与知识合成的断点改为已归档，并保留归档快照。"""
    try:
        archive_document = target_path.relative_to(vault_root).as_posix()
    except ValueError:
        archive_document = str(target_path)
    archived = []
    for record in records:
        if record["kind"] != "session":
            continue
        path = record["path"]
        text = read_text(path)
        if not text.startswith("---\n"):
            continue
        updated = set_frontmatter_value(text, "status", '"archived"')
        updated = set_frontmatter_value(updated, "knowledge_archived", "true")
        updated = set_frontmatter_value(updated, "archived_prompt_count", str(prompt_count(text)))
        updated = set_frontmatter_value(updated, "archive_document", json.dumps(archive_document, ensure_ascii=False))
        updated = re.sub(r"^\*\*状态\*\*:\s*.+$", "**状态**: 已知识归档", updated, count=1, flags=re.MULTILINE)
        updated = re.sub(r"^>\s*.+?\s*·\s*([0-9a-f-]{6,})$", r"> 已知识归档 · \1", updated, count=1, flags=re.MULTILINE)
        path.write_text(updated, encoding="utf-8")
        archived.append(path)
    return archived


def refresh_daily_index_status(vault_root: Path, archived_paths: list[Path]) -> None:
    for note_path in archived_paths:
        text = read_text(note_path)
        date_text = extract_frontmatter_value(text, "date")
        if not date_text:
            continue
        index_path = vault_root / "Codex工作记录" / "会话索引" / f"{date_text}.md"
        if not index_path.is_file():
            continue
        lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
        session_id = extract_frontmatter_value(text, "session_id")
        marker = f"<!-- session:{session_id} -->" if session_id else ""
        for index, line in enumerate(lines):
            if not marker or marker not in line or not line.lstrip().startswith("|"):
                continue
            lines[index] = re.sub(r"^(\|\s*[^|]+\|\s*)[^|]+", r"\1📚 ", line)
        index_path.write_text("".join(lines), encoding="utf-8")


def refresh_dashboard(vault_root: Path) -> None:
    skill_path = Path(__file__).resolve()
    candidates = (
        skill_path.parents[2] / "hooks" / "checkpoint.py",
    )
    hook_path = next((path for path in candidates if path.is_file()), None)
    if hook_path is None:
        return
    try:
        os.environ["OBSIDIAN_VAULT"] = str(vault_root)
        spec = importlib.util.spec_from_file_location("codex_checkpoint", hook_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.update_dashboard()
    except Exception:
        return


def main():
    args = parse_args()
    if args.confirm_cluster and not args.cluster:
        print("--confirm-cluster 只能与 --cluster 一起使用。", file=sys.stderr)
        sys.exit(2)
    if args.cluster_project and not args.cluster:
        print("--cluster-project 只能与 --cluster 一起使用。", file=sys.stderr)
        sys.exit(2)
    if args.cluster and not args.confirm_cluster:
        print("聚类模式可能跨项目选择材料；请在用户明确确认范围后添加 --confirm-cluster。", file=sys.stderr)
        sys.exit(2)
    if args.cluster and not (args.cluster_project or "").strip():
        print("聚类模式必须提供 --cluster-project <项目名>，避免生成无归属的“知识合成”项目总结。", file=sys.stderr)
        sys.exit(2)
    if args.apply_cleanup and not args.cleanup_checkpoints:
        print("--apply-cleanup 只能与 --cleanup-checkpoints 一起使用。", file=sys.stderr)
        sys.exit(2)
    if args.cleanup_checkpoints and args.long_term:
        print("断点清理不能同时写入长期经验。", file=sys.stderr)
        sys.exit(2)
    vault_root = Path(args.vault_root).expanduser().resolve()
    global LINK_VAULT_ROOT
    LINK_VAULT_ROOT = vault_root
    work_dir = vault_root / "Codex工作记录"
    projects_dir = vault_root / "项目总结"
    note_dir = work_dir / "会话断点"
    if not note_dir.is_dir():
        print(f"未找到目录：{note_dir}")
        sys.exit(1)

    if args.cleanup_checkpoints:
        run_checkpoint_cleanup(args, vault_root, note_dir)
        return

    records = note_records(note_dir)
    project, selected, tags = select_records(records, args, projects_dir)
    if len(selected) < 1:
        print("没有找到可合成的断点。")
        sys.exit(1)

    title = args.title or (f"{project} 知识整理" if project else "Codex 知识整理")
    # 默认只更新一个独立项目摘要；目录仅服务于已确认的父项目。
    target_path = projects_dir / f"{safe_filename(project)}.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing_session_ids = extract_frontmatter_list(read_text(target_path), "session_ids")
    selected_session_ids = []
    for record in selected:
        if record["kind"] == "session" and record.get("session_id"):
            selected_session_ids.append(record["session_id"])
        selected_session_ids.extend(record.get("session_ids", []))
    session_ids = dedupe_texts(existing_session_ids + selected_session_ids)
    frontmatter = (
        "---\n"
        f"date: {datetime.now(VAULT_TIMEZONE).strftime('%Y-%m-%d')}\n"
        f"project: {project}\n"
        "knowledge_archived: true\n"
        "archive_status: \"archived\"\n"
        f"session_ids: {json.dumps(session_ids, ensure_ascii=False)}\n"
        f"tags: {json.dumps(tags, ensure_ascii=False)}\n"
        "---\n\n"
    )
    body = synthesize_body(project, title, selected)
    target_path.write_text(frontmatter + body, encoding="utf-8")
    archived_paths = mark_source_sessions_archived(selected, target_path, vault_root)
    refresh_daily_index_status(vault_root, archived_paths)
    refresh_dashboard(vault_root)
    print(f"文档路径: {target_path}")
    print(f"覆盖会话数: {len(selected)}")
    print(f"已归档断点数: {len(archived_paths)}")
    print(f"主要结论: 已从 {len(selected)} 条材料中整理出更高信噪比的知识文档。")
    metrics = session_length_metrics(selected)
    print(f"会话长度：{metrics['sessions']} 个会话，{metrics['prompts']} 条用户消息，{metrics['chars']} 个字符。")
    if args.long_term:
        write_long_term_experience(args, vault_root, project, selected)
        refresh_dashboard(vault_root)
    elif metrics["is_long"]:
        print("检测到长会话。项目总结已归档；请先询问用户是否需要提炼长期经验，未获得明确授权不得写入。")
    else:
        print("会话长度不足以建议长期经验。项目总结已归档，未写入长期经验；用户仍可明确要求强制提炼。")


if __name__ == "__main__":
    main()
