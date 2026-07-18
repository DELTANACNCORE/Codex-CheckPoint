"""Read-only and user-confirmed maintenance helpers for the CxCP vault."""

from __future__ import annotations

from datetime import date, datetime
from difflib import SequenceMatcher
import hashlib
import json
import re
from pathlib import Path

from metadata import metadata_values, parse_frontmatter_list


CHECKPOINT_PREFIX = ("Codex工作记录", "会话断点")
INDEX_PREFIX = ("Codex工作记录", "会话索引")
CHECKPOINT_FIELDS = ("date", "session_id", "status", "projects", "category", "tags", "keywords", "aliases")
GENERIC_IDENTITIES = {
    "ai", "checkpoint", "claude", "codex", "hook", "skill", "obsidian",
    "项目", "总结", "方案", "开发", "工作流", "工具", "系统", "配置", "知识库",
    "经验", "参考", "会话", "迁到", "服务", "网络", "运维", "部署", "更新",
    "测试", "验证", "检查", "问题", "修复", "自动", "文档", "代码", "功能",
    "支持", "任务", "使用", "处理", "内容", "整理", "记录", "资料", "链接",
    "docker", "compose", "container", "readme", "markdown", "json", "yaml",
    "ai开发参考", "核心知识", "会话断点", "工作记录", "项目总结", "长期经验总结",
    "users", "home", "documents", "library", "https", "http", "true", "false",
    "image", "latest", "name", "text", "skills", "synthesize", "deltanacncore", "agent",
    "未关联项目", "无关联项目", "未分类对话",
}
LOW_SIGNAL_TITLE_PATTERNS = (
    r"^请只回复一句",
    r"\bverify\b",
    r"\btrust\b",
    r"\bbypass\b",
    r"^(?:本次对话(?:项目)?已(?:写入|加入)|正在(?:写入|生成)).*",
)
VERIFICATION_HEADINGS = ("已验证结果", "已验证能力", "已验证闭环", "验证证据")
SESSION_ID_PATTERN = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.IGNORECASE)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_h1(text: str, fallback: str) -> str:
    matched = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return matched.group(1).strip() if matched else fallback


def frontmatter_block(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = re.search(r"\n---[ \t]*(?:\n|$)", text[4:])
    if not end:
        return ""
    return text[4 : 4 + end.start()]


def has_frontmatter_field(text: str, key: str) -> bool:
    return bool(re.search(rf"^{re.escape(key)}:\s*", frontmatter_block(text), re.MULTILINE))


def extract_frontmatter_scalar(text: str, key: str) -> str:
    matched = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter_block(text), re.MULTILINE)
    if not matched:
        return ""
    value = matched.group(1).strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            decoded = json.loads(value)
            return str(decoded) if not isinstance(decoded, (dict, list)) else ""
        except json.JSONDecodeError:
            return value.strip('"')
    return value.strip("'")


def extract_section(text: str, heading: str) -> str:
    matched = re.search(rf"^##\s+{re.escape(heading)}\n+([\s\S]*?)(?=\n##\s+|\Z)", text, re.MULTILINE)
    return matched.group(1).strip() if matched else ""


def is_checkpoint_record(record: dict) -> bool:
    return tuple(record["rel"].parts[:2]) == CHECKPOINT_PREFIX


def is_index_record(record: dict) -> bool:
    return tuple(record["rel"].parts[:2]) == INDEX_PREFIX


def record_projects(record: dict) -> list[str]:
    values = parse_frontmatter_list(record["text"], "projects")
    scalar = extract_frontmatter_scalar(record["text"], "project")
    if scalar:
        values.append(scalar)
    return metadata_values(values)


def scan_vault(vault_root: Path) -> list[dict]:
    records = []
    for path in sorted(vault_root.rglob("*.md")):
        try:
            rel = path.relative_to(vault_root)
        except ValueError:
            continue
        if ".obsidian" in rel.parts:
            continue
        text = read_text(path)
        if not text:
            continue
        records.append({
            "path": path,
            "rel": rel,
            "text": text,
            "title": extract_h1(text, path.stem),
            "session_id": extract_frontmatter_scalar(text, "session_id"),
            "status": extract_frontmatter_scalar(text, "status"),
            "date": extract_frontmatter_scalar(text, "date"),
            "projects": record_projects({"text": text}),
            "aliases": parse_frontmatter_list(text, "aliases"),
            "keywords": parse_frontmatter_list(text, "keywords"),
            "tags": parse_frontmatter_list(text, "tags"),
            "links": extract_wikilink_targets(text),
        })
    return records


def empty_markdown_files(vault_root: Path) -> list[str]:
    empty = []
    for path in sorted(vault_root.rglob("*.md")):
        try:
            rel = path.relative_to(vault_root)
            if ".obsidian" in rel.parts or path.stat().st_size > 0:
                continue
        except OSError:
            continue
        empty.append(f"空 Markdown：`{rel.as_posix()}`")
    return empty


def rollout_session_ids(sessions_root: Path | None) -> set[str]:
    if sessions_root is None or not sessions_root.is_dir():
        return set()
    session_ids = set()
    for path in sessions_root.rglob("rollout-*.jsonl"):
        matched = SESSION_ID_PATTERN.search(path.stem)
        if matched:
            session_ids.add(matched.group(1))
    return session_ids


def identity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalize_space(value).lower())


def extract_identity_tokens(value: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff]{3,}", value or ""):
        if token not in tokens:
            tokens.append(token)
    return tokens


def is_specific_identity(value: str) -> bool:
    key = identity_key(value)
    if len(key) < 3 or key in GENERIC_IDENTITIES:
        return False
    tokens = extract_identity_tokens(value)
    return bool(tokens) and any(identity_key(token) not in GENERIC_IDENTITIES for token in tokens)


def is_usable_title(title: str) -> bool:
    value = normalize_space(title)
    if len(value) < 5 or len(value) > 80:
        return False
    if value.startswith(("我会", "现在会", "接下来会", "正在", "随后会")):
        return False
    return not any(re.search(pattern, value, re.IGNORECASE) for pattern in LOW_SIGNAL_TITLE_PATTERNS)


def metadata_candidate(record: dict) -> dict | None:
    if not is_checkpoint_record(record) or not record["session_id"]:
        return None
    if not frontmatter_block(record["text"]):
        return None
    aliases = record["aliases"]
    keywords = record["keywords"]
    suggested_aliases = [record["title"]] if not aliases and is_usable_title(record["title"]) else []
    suggested_keywords = []
    if not keywords:
        technical_terms = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", record["title"])
        values = [*record["projects"], record["title"], *technical_terms]
        for value in values:
            if is_specific_identity(value):
                suggested_keywords.append(normalize_space(value))
        suggested_keywords = metadata_values(suggested_keywords, limit=6, filter_noise=True)
    if not suggested_aliases and not suggested_keywords:
        return None
    return {
        "session_id": record["session_id"],
        "record": record,
        "aliases": suggested_aliases,
        "keywords": suggested_keywords,
    }


def metadata_candidates(records: list[dict]) -> list[dict]:
    candidates = [candidate for record in records if (candidate := metadata_candidate(record))]
    return sorted(candidates, key=lambda item: (item["record"]["rel"].as_posix(), item["session_id"]))


def set_frontmatter_value(text: str, key: str, value: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = re.search(r"\n---[ \t]*(?:\n|$)", text[4:])
    if not end:
        return text
    front_end = 4 + end.start()
    frontmatter = text[4:front_end]
    suffix = text[front_end:]
    line = f"{key}: {value}"
    pattern = rf"^{re.escape(key)}:\s*.*$"
    if re.search(pattern, frontmatter, re.MULTILINE):
        frontmatter = re.sub(pattern, line, frontmatter, count=1, flags=re.MULTILINE)
    else:
        frontmatter = line + "\n" + frontmatter
    return "---\n" + frontmatter + suffix


def apply_metadata_candidates(records: list[dict], session_ids: list[str]) -> list[Path]:
    requested = metadata_values(session_ids)
    if not requested:
        raise ValueError("metadata 回填必须指定至少一个 session ID。")
    grouped: dict[str, list[dict]] = {}
    for candidate in metadata_candidates(records):
        grouped.setdefault(candidate["session_id"], []).append(candidate)
    missing = [session_id for session_id in requested if session_id not in grouped]
    if missing:
        raise ValueError("以下 session 没有可安全回填的 metadata 候选：" + "、".join(missing))
    ambiguous = [session_id for session_id in requested if len(grouped[session_id]) != 1]
    if ambiguous:
        raise ValueError("以下 session 存在多个 metadata 候选，请先清理重复断点：" + "、".join(ambiguous))
    updated_paths = []
    for session_id in requested:
        candidate = grouped[session_id][0]
        record = candidate["record"]
        text = read_text(record["path"])
        if not text:
            continue
        updated = text
        if candidate["aliases"] and not parse_frontmatter_list(updated, "aliases"):
            updated = set_frontmatter_value(updated, "aliases", json.dumps(candidate["aliases"], ensure_ascii=False))
        if candidate["keywords"] and not parse_frontmatter_list(updated, "keywords"):
            updated = set_frontmatter_value(updated, "keywords", json.dumps(candidate["keywords"], ensure_ascii=False))
        if updated != text:
            record["path"].write_text(updated, encoding="utf-8")
            updated_paths.append(record["path"])
    return updated_paths


def extract_wikilink_targets(text: str) -> set[str]:
    targets = set()
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        inner = match.group(1)
        target = []
        index = 0
        while index < len(inner):
            char = inner[index]
            if char == "\\" and index + 1 < len(inner):
                if inner[index + 1] in "|#":
                    break
                target.append(inner[index + 1])
                index += 2
                continue
            if char in "|#":
                break
            target.append(char)
            index += 1
        value = "".join(target).strip()
        if value:
            targets.add(value)
    return targets


def document_index(records: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    by_rel = {}
    by_stem: dict[str, list[dict]] = {}
    for record in records:
        target = record["rel"].with_suffix("").as_posix()
        by_rel[target] = record
        by_stem.setdefault(record["path"].stem, []).append(record)
    return by_rel, by_stem


def resolve_wikilink(source: dict, target: str, by_rel: dict[str, dict], by_stem: dict[str, list[dict]]) -> dict | None:
    normalized = target.replace("\\", "/").strip().lstrip("/")
    if not normalized:
        return None
    candidates = [normalized]
    source_parent = source["rel"].parent
    if source_parent != Path("."):
        candidates.append((source_parent / normalized).as_posix())
    for candidate in candidates:
        candidate = candidate.removesuffix(".md")
        if candidate in by_rel:
            return by_rel[candidate]
    stem_matches = by_stem.get(Path(normalized).stem, [])
    return stem_matches[0] if len(stem_matches) == 1 else None


def link_issues(records: list[dict]) -> list[str]:
    by_rel, by_stem = document_index(records)
    issues = []
    for record in records:
        for target in sorted(record["links"]):
            if target.lower() in {"wikilink", "placeholder", "占位符"}:
                continue
            if resolve_wikilink(record, target, by_rel, by_stem) is None:
                issues.append(f"断裂链接 `[[{target}]]`：`{record['rel'].as_posix()}`")
    return issues


def normalized_link_value(value: str) -> str:
    return identity_key(Path(normalize_space(value)).stem)


def wikilink_inner_target(inner: str) -> tuple[str, str]:
    """Return a link target and the alias or heading suffix that should be retained."""
    target = []
    index = 0
    while index < len(inner):
        char = inner[index]
        if char == "\\" and index + 1 < len(inner):
            if inner[index + 1] in "|#":
                target.append(inner[index + 1])
                index += 2
                continue
            target.append(inner[index + 1])
            index += 2
            continue
        if char in "|#":
            return "".join(target).strip(), inner[index:]
        target.append(char)
        index += 1
    return "".join(target).strip(), ""


def link_repair_evidence(source: dict, target: str, candidate: dict) -> tuple[int, str]:
    """Score only a unique replacement for a broken wikilink.

    A repair candidate needs an exact alias or a strong filename/title match. Generic
    topic overlap never authorizes a replacement because it is insufficient to know
    which historical document the user meant to link.
    """
    target_key = normalized_link_value(target)
    if not target_key:
        return 0, ""
    target_path = normalize_space(target).replace("\\", "/").removesuffix(".md")
    candidate_path = candidate["rel"].with_suffix("").as_posix()
    candidate_values = [candidate["path"].stem, candidate["title"], *candidate["aliases"]]
    for value in candidate_values:
        if target_key and target_key == normalized_link_value(value):
            label = "aliases" if value in candidate["aliases"] else "标题或文件名"
            return 100, label

    target_leaf = Path(target_path).stem
    candidate_leaf = candidate["path"].stem
    ratio = SequenceMatcher(None, normalized_link_value(target_leaf), normalized_link_value(candidate_leaf)).ratio()
    same_parent = Path(target_path).parent == candidate["rel"].parent
    if ratio >= 0.88 and (same_parent or ratio >= 0.94):
        return int(ratio * 100), f"文件名相似度 {ratio:.0%}"
    return 0, ""


def link_repair_candidate_id(source: dict, target: str, replacement: dict) -> str:
    raw = "|".join((source["rel"].as_posix(), normalize_space(target), replacement["rel"].as_posix()))
    return "repair-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def broken_link_repair_candidates(records: list[dict]) -> list[dict]:
    """Find unambiguous replacements for existing broken wikilinks without writing."""
    by_rel, by_stem = document_index(records)
    candidates = []
    for source in records:
        for target in sorted(source["links"]):
            if target.lower() in {"wikilink", "placeholder", "占位符"}:
                continue
            if resolve_wikilink(source, target, by_rel, by_stem) is not None:
                continue
            scored = []
            for replacement in records:
                if replacement is source:
                    continue
                score, evidence = link_repair_evidence(source, target, replacement)
                if score:
                    scored.append((score, evidence, replacement))
            scored.sort(key=lambda item: (-item[0], item[2]["rel"].as_posix()))
            if not scored:
                continue
            best_score, evidence, replacement = scored[0]
            second_score = scored[1][0] if len(scored) > 1 else 0
            # A near-tie could point at two documents intentionally sharing an alias.
            if second_score >= best_score - 5:
                continue
            candidates.append({
                "id": link_repair_candidate_id(source, target, replacement),
                "source": source,
                "target": target,
                "replacement": replacement,
                "evidence": evidence,
            })
    return sorted(candidates, key=lambda item: (item["source"]["rel"].as_posix(), item["target"]))


def rewrite_link_target(text: str, broken_target: str, replacement: dict) -> str:
    replacement_target = replacement["rel"].with_suffix("").as_posix()

    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        target, suffix = wikilink_inner_target(inner)
        if target != broken_target:
            return match.group(0)
        return f"[[{replacement_target}{suffix}]]"

    return re.sub(r"\[\[([^\]]+)\]\]", replace, text)


def apply_broken_link_repair_candidate(records: list[dict], candidate_id: str) -> Path:
    candidate = next(
        (item for item in broken_link_repair_candidates(records) if item["id"] == candidate_id),
        None,
    )
    if candidate is None:
        raise ValueError("未找到该链接修复候选。候选可能已修复、已删除或证据已变化，请重新扫描。")
    source = candidate["source"]
    text = read_text(source["path"])
    rewritten = rewrite_link_target(text, candidate["target"], candidate["replacement"])
    if rewritten == text:
        raise ValueError("链接修复候选未找到可替换的原始链接，请重新扫描。")
    source["path"].write_text(rewritten, encoding="utf-8")
    return source["path"]


def archive_issue(record: dict, vault_root: Path) -> str:
    archived = record["status"] == "archived" or bool(re.search(r"^knowledge_archived:\s*true$", record["text"], re.MULTILINE))
    if not archived:
        return ""
    archive_document = extract_frontmatter_scalar(record["text"], "archive_document")
    if not archive_document:
        return f"已归档断点缺少 archive_document：`{record['rel'].as_posix()}`"
    candidate = Path(archive_document)
    if candidate.is_absolute():
        return f"archive_document 不能使用绝对路径：`{record['rel'].as_posix()}`"
    resolved = (vault_root / candidate).resolve()
    try:
        resolved.relative_to(vault_root.resolve())
    except ValueError:
        return f"archive_document 越出知识库目录：`{record['rel'].as_posix()}`"
    if not resolved.is_file():
        return f"归档目标不存在：`{record['rel'].as_posix()}` -> `{archive_document}`"
    return ""


def project_summary_issue(record: dict, vault_root: Path) -> list[str]:
    issues = []
    for project in record["projects"]:
        direct = vault_root / "项目总结" / f"{project}.md"
        grouped = vault_root / "项目总结" / project / "项目总结.md"
        if direct.is_file() or grouped.is_file():
            continue
        issues.append(f"关联项目缺少项目总结：`{record['rel'].as_posix()}` -> `{project}`")
    return issues


def parse_note_date(value: str) -> date | None:
    candidate = normalize_space(value).strip('"\'')
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(candidate[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def stale_verification_issues(records: list[dict], stale_days: int, today: date | None = None) -> list[str]:
    current = today or date.today()
    issues = []
    for record in records:
        if not any(extract_section(record["text"], heading) for heading in VERIFICATION_HEADINGS):
            continue
        note_date = parse_note_date(record["date"])
        if note_date is None:
            continue
        age = (current - note_date).days
        if age > stale_days:
            issues.append(f"验证记录已过 {age} 天，执行前建议复核：`{record['rel'].as_posix()}`")
    return issues


def is_knowledge_archived(record: dict) -> bool:
    return record["status"] == "archived" or bool(
        re.search(r"^knowledge_archived:\s*true$", record["text"], re.MULTILINE)
    )


def project_summary_session_ids(record: dict) -> set[str]:
    return set(parse_frontmatter_list(record["text"], "session_ids"))


def knowledge_organization_candidates(records: list[dict]) -> list[dict]:
    """Report manual synthesis opportunities without inferring project hierarchy.

    The report deliberately uses only the explicit `projects` metadata. A candidate is
    an invitation to review source sessions, never authorization to merge or archive.
    """
    unarchived_by_project: dict[str, list[dict]] = {}
    summaries_by_project: dict[str, list[dict]] = {}
    for record in records:
        for project in record["projects"]:
            if not is_specific_identity(project):
                continue
            if is_checkpoint_record(record) and not is_knowledge_archived(record):
                unarchived_by_project.setdefault(project, []).append(record)
            elif record["rel"].parts and record["rel"].parts[0] == "项目总结":
                summaries_by_project.setdefault(project, []).append(record)

    candidates = []
    for project, source_records in sorted(unarchived_by_project.items()):
        by_session = {
            record["session_id"]: record
            for record in source_records
            if record["session_id"]
        }
        sources = sorted(by_session.values(), key=lambda item: item["rel"].as_posix())
        if not sources:
            continue
        summaries = summaries_by_project.get(project, [])
        covered_session_ids = set().union(*(project_summary_session_ids(summary) for summary in summaries)) if summaries else set()
        pending_sources = [source for source in sources if source["session_id"] not in covered_session_ids]
        if summaries and pending_sources:
            candidates.append({
                "kind": "项目总结刷新",
                "project": project,
                "sources": pending_sources,
                "summaries": summaries,
            })
        elif not summaries and len(sources) >= 2:
            candidates.append({
                "kind": "项目知识整理",
                "project": project,
                "sources": sources,
                "summaries": [],
            })
    return candidates


def audit_vault(vault_root: Path, stale_days: int = 30, sessions_root: Path | None = None) -> dict:
    records = scan_vault(vault_root)
    checkpoints = [record for record in records if is_checkpoint_record(record)]
    frontmatter = []
    archives = []
    projects = []
    by_session: dict[str, list[dict]] = {}
    for record in checkpoints:
        if not frontmatter_block(record["text"]):
            frontmatter.append(f"缺少 frontmatter：`{record['rel'].as_posix()}`")
            continue
        for field in CHECKPOINT_FIELDS:
            if not has_frontmatter_field(record["text"], field):
                frontmatter.append(f"缺少字段 `{field}`：`{record['rel'].as_posix()}`")
        if record["session_id"]:
            by_session.setdefault(record["session_id"], []).append(record)
        issue = archive_issue(record, vault_root)
        if issue:
            archives.append(issue)
        projects.extend(project_summary_issue(record, vault_root))
    duplicates = []
    for session_id, grouped in sorted(by_session.items()):
        if len(grouped) > 1:
            paths = "、".join(f"`{record['rel'].as_posix()}`" for record in grouped)
            duplicates.append(f"重复 session_id `{session_id}`：{paths}")
    known_rollouts = rollout_session_ids(sessions_root)
    missing_rollouts = []
    if sessions_root is not None and sessions_root.is_dir():
        for record in checkpoints:
            if record["session_id"] and record["session_id"] not in known_rollouts:
                missing_rollouts.append(f"没有匹配 rollout：`{record['rel'].as_posix()}`")
    return {
        "records": records,
        "checkpoint_count": len(checkpoints),
        "empty_files": empty_markdown_files(vault_root),
        "frontmatter": frontmatter,
        "duplicates": duplicates,
        "missing_rollouts": missing_rollouts,
        "archives": archives,
        "projects": projects,
        "links": link_issues(records),
        "stale_verification": stale_verification_issues(records, stale_days),
        "metadata_candidates": metadata_candidates(checkpoints),
        "knowledge_candidates": knowledge_organization_candidates(records),
        "stale_days": stale_days,
    }


def document_signals(record: dict) -> dict[str, str]:
    signals: dict[str, str] = {}

    def add(prefix: str, value: str) -> None:
        label = normalize_space(value)
        key = identity_key(label)
        if label and key and is_specific_identity(label):
            signals.setdefault(f"{prefix}:{key}", label)

    for project in record["projects"]:
        add("project", project)
    for value in [*record["aliases"], *record["keywords"], *record["tags"], record["title"]]:
        add("identity", value)
    # Body-wide words frequently include local paths, generated receipts, and shared
    # tooling names. Link candidates use only user-visible metadata and titles.
    for value in [record["title"], *extract_identity_tokens(record["title"])]:
        add("term", value)
    return signals


def link_pair_evidence(left: dict, right: dict) -> dict | None:
    left_signals = document_signals(left)
    right_signals = document_signals(right)
    shared = set(left_signals).intersection(right_signals)
    projects = sorted(key for key in shared if key.startswith("project:"))
    identities = sorted(key for key in shared if not key.startswith("project:"))
    if not ((projects and identities) or len(identities) >= 3):
        return None
    return {
        "projects": [left_signals[key] for key in projects],
        "identities": [left_signals[key] for key in identities],
    }


def documents_linked(left: dict, right: dict, by_rel: dict[str, dict], by_stem: dict[str, list[dict]]) -> bool:
    for source, target in ((left, right), (right, left)):
        for value in source["links"]:
            resolved = resolve_wikilink(source, value, by_rel, by_stem)
            if resolved is target:
                return True
    return False


def link_candidate_id(left: dict, right: dict) -> str:
    values = sorted((left["rel"].as_posix(), right["rel"].as_posix()))
    digest = hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:10]
    return f"link-{digest}"


def link_candidates(records: list[dict]) -> list[dict]:
    eligible = [
        record for record in records
        if not is_index_record(record)
        and record["rel"].name != "知识库首页.md"
        and is_usable_title(record["title"])
    ]
    by_rel, by_stem = document_index(records)
    candidates = []
    for index, left in enumerate(eligible):
        for right in eligible[index + 1 :]:
            if documents_linked(left, right, by_rel, by_stem):
                continue
            evidence = link_pair_evidence(left, right)
            if not evidence:
                continue
            candidates.append({
                "id": link_candidate_id(left, right),
                "left": left,
                "right": right,
                "projects": evidence["projects"],
                "identities": metadata_values(evidence["identities"], limit=6),
            })
    return sorted(candidates, key=lambda item: (item["left"]["rel"].as_posix(), item["right"]["rel"].as_posix()))


def related_wikilink(record: dict) -> str:
    target = record["rel"].with_suffix("").as_posix()
    return f"[[{target}|{record['title']}]]"


def append_related_link(text: str, link: str) -> str:
    if link in text:
        return text
    heading = re.search(r"^##\s+相关资料\s*$", text, re.MULTILINE)
    if not heading:
        return text.rstrip() + f"\n\n## 相关资料\n\n- {link}\n"
    tail = text[heading.end():]
    next_heading = re.search(r"\n##\s+", tail)
    insertion = f"\n- {link}"
    if next_heading:
        point = heading.end() + next_heading.start()
        return text[:point].rstrip() + insertion + "\n" + text[point:]
    return text.rstrip() + insertion + "\n"


def apply_link_candidate(records: list[dict], candidate_id: str) -> list[Path]:
    candidate = next((item for item in link_candidates(records) if item["id"] == candidate_id), None)
    if candidate is None:
        raise ValueError("未找到该链接候选。候选可能已写入、已删除或关联依据发生变化，请重新扫描。")
    updated = []
    for source, target in ((candidate["left"], candidate["right"]), (candidate["right"], candidate["left"])):
        text = read_text(source["path"])
        rewritten = append_related_link(text, related_wikilink(target))
        if rewritten != text:
            source["path"].write_text(rewritten, encoding="utf-8")
            updated.append(source["path"])
    return updated


def format_audit_report(report: dict, item_limit: int = 12) -> str:
    groups = (
        ("空 Markdown", report["empty_files"]),
        ("断点 frontmatter", report["frontmatter"]),
        ("重复 session", report["duplicates"]),
        ("缺少 rollout", report["missing_rollouts"]),
        ("归档状态", report["archives"]),
        ("项目归属", report["projects"]),
        ("Wiki-link", report["links"]),
        (f"验证时效超过 {report['stale_days']} 天", report["stale_verification"]),
    )
    issue_count = sum(len(items) for _, items in groups)
    lines = [f"知识库审计：扫描 {len(report['records'])} 篇 Markdown，断点 {report['checkpoint_count']} 条，发现 {issue_count} 项结构问题。"]
    for title, items in groups:
        if not items:
            continue
        lines.append(f"\n## {title}：{len(items)} 项")
        lines.extend(f"- {item}" for item in items[:item_limit])
        if len(items) > item_limit:
            lines.append(f"- 其余 {len(items) - item_limit} 项未展开。")
    candidates = report["metadata_candidates"]
    lines.append(f"\n## Metadata 回填候选：{len(candidates)} 条")
    for candidate in candidates[:item_limit]:
        record = candidate["record"]
        proposed = []
        if candidate["aliases"]:
            proposed.append("aliases=" + json.dumps(candidate["aliases"], ensure_ascii=False))
        if candidate["keywords"]:
            proposed.append("keywords=" + json.dumps(candidate["keywords"], ensure_ascii=False))
        lines.append(f"- {candidate['session_id']} · `{record['rel'].as_posix()}` · {'；'.join(proposed)}")
    if len(candidates) > item_limit:
        lines.append(f"- 其余 {len(candidates) - item_limit} 条未展开。")
    knowledge_candidates = report["knowledge_candidates"]
    lines.append(f"\n## 知识整理建议：{len(knowledge_candidates)} 项")
    for candidate in knowledge_candidates[:item_limit]:
        sources = "、".join(f"`{source['rel'].as_posix()}`" for source in candidate["sources"])
        summary_text = ""
        if candidate["summaries"]:
            summary_text = "；现有总结：" + "、".join(
                f"`{summary['rel'].as_posix()}`" for summary in candidate["summaries"]
            )
        lines.append(
            f"- {candidate['kind']}：`{candidate['project']}` 有 {len(candidate['sources'])} 条待审阅会话"
            f"（{sources}）{summary_text}。"
        )
    if len(knowledge_candidates) > item_limit:
        lines.append(f"- 其余 {len(knowledge_candidates) - item_limit} 项未展开。")
    lines.append("知识整理建议不推断父项目关系，也不构成归档授权。")
    lines.append("\n本次审计未修改 vault。metadata 回填必须指定 session ID 并附加 --confirm-metadata。")
    return "\n".join(lines)


def format_link_candidates(candidates: list[dict], limit: int = 8) -> str:
    lines = [f"跨文档链接候选：生成 {len(candidates)} 组高置信候选。"]
    for candidate in candidates[: max(limit, 0)]:
        left = candidate["left"]
        right = candidate["right"]
        lines.extend((
            "",
            f"候选编号: {candidate['id']}",
            f"文档 A: `{left['rel'].as_posix()}` · {left['title']}",
            f"文档 B: `{right['rel'].as_posix()}` · {right['title']}",
            "共同项目: " + ("、".join(candidate["projects"]) if candidate["projects"] else "无"),
            "共同特征: " + "、".join(candidate["identities"]),
        ))
    if not candidates:
        lines.append("当前没有达到高置信阈值的候选。")
    lines.append("\n本次仅生成候选，未写入链接。确认后使用 --link-candidate <候选编号> --confirm-link。")
    return "\n".join(lines)


def format_broken_link_repair_candidates(candidates: list[dict], limit: int = 8) -> str:
    lines = [f"断裂链接修复候选：生成 {len(candidates)} 条唯一替代候选。"]
    for candidate in candidates[: max(limit, 0)]:
        source = candidate["source"]
        replacement = candidate["replacement"]
        replacement_link = f"[[{replacement['rel'].with_suffix('').as_posix()}|{replacement['title']}]]"
        lines.extend((
            "",
            f"候选编号: {candidate['id']}",
            f"来源文档: `{source['rel'].as_posix()}` · {source['title']}",
            f"断裂链接: [[{candidate['target']}]]",
            f"建议替换: {replacement_link}",
            f"匹配依据: {candidate['evidence']}",
        ))
    if not candidates:
        lines.append("当前没有证据充分且替代目标唯一的候选。")
    lines.append("\n本次仅生成候选，未修复链接。确认后使用 --repair-link-candidate <候选编号> --confirm-link-repair。")
    return "\n".join(lines)
