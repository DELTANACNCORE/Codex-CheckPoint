#!/usr/bin/env python3
"""Search Codex Obsidian notes with better ranking and summaries."""

import argparse
import re
import sys
from pathlib import Path

CODEX_ROOT = Path(__file__).resolve().parents[2]
if str(CODEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEX_ROOT))

from metadata import metadata_values, parse_frontmatter_list


SUMMARY_SECTIONS = [
    "关键结论",
    "已验证能力",
    "当前缺口",
    "实施路径",
    "背景概览",
    "背景",
    "项目定位",
    "可复用经验",
    "AI开发参考",
    "避坑清单",
    "可直接续接的结论",
    "已完成事项",
    "当前状态与续接",
    "会话目标演进",
    "最近会话脉络",
    "实际产出",
    "产出",
]

LOW_SIGNAL_TITLE_PATTERNS = (
    r"^请只回复一句",
    r"\bverify\b",
    r"\btrust\b",
    r"\bbypass\b",
)

GENERIC_SEARCH_METADATA = {
    "项目总结",
    "ai开发参考",
    "长期经验总结",
    "经验摘要",
    "核心知识",
    "codex方案",
    "知识库/自动总结",
    "codex/方案",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("keywords", nargs="+")
    parser.add_argument("--vault-root", default=str(Path("~/obsidian/知识库").expanduser()))
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def extract_h1(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def extract_frontmatter_value(text: str, key: str) -> str:
    m = re.search(rf'^{re.escape(key)}:\s*"([^"]+)"', text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(rf"^{re.escape(key)}:\s*([^\n]+)", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_list(text: str, key: str) -> list[str]:
    return parse_frontmatter_list(text, key)


def extract_block(text: str, heading: str) -> str:
    m = re.search(rf"##\s+{re.escape(heading)}\n+([\s\S]*?)(?=\n##\s+|\Z)", text)
    return m.group(1).strip() if m else ""


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            return parts[1]
    return text


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
    return [normalize_space(part) for part in parts if normalize_space(part)]


def is_low_signal_title(title: str) -> bool:
    return any(re.search(pattern, title, re.IGNORECASE) for pattern in LOW_SIGNAL_TITLE_PATTERNS)


def is_sparse_doc(record: dict) -> bool:
    if record["kind"] != "归档文档":
        return False
    if record["tags"] or record["category"] or record["keywords"] or record["aliases"]:
        return False
    body = strip_frontmatter(record["text"])
    return len(normalize_space(body)) < 80


def clamp_text(text: str, limit: int = 140) -> str:
    normalized = normalize_space(text)
    return normalized[: limit - 1].rstrip() + "…" if len(normalized) > limit else normalized


def build_search_corpus(text: str) -> str:
    body = strip_frontmatter(text)
    parts = [extract_h1(text, "")]
    for heading in SUMMARY_SECTIONS:
        block = extract_block(body, heading)
        if block:
            parts.append(block)
    parts.append(body)
    return "\n".join(part for part in parts if part)


def _searchable_metadata(values: list[str]) -> list[str]:
    return [
        value for value in metadata_values(values)
        if normalize_space(value).casefold() not in GENERIC_SEARCH_METADATA
    ]


def _matching_terms(values: list[str], keywords: list[str]) -> list[str]:
    hits = []
    normalized_values = [normalize_space(value).casefold() for value in values if normalize_space(value)]
    for keyword in metadata_values(keywords):
        key = normalize_space(keyword).casefold()
        if key and any(key in value for value in normalized_values):
            hits.append(keyword)
    return metadata_values(hits)


def score_text(record: dict, keywords: list[str]) -> dict | None:
    aliases = _matching_terms(_searchable_metadata(record["aliases"]), keywords)
    metadata_keywords = _matching_terms(_searchable_metadata(record["keywords"]), keywords)
    tags = _matching_terms(_searchable_metadata(record["tags"]), keywords)
    title = _matching_terms([record["title"]], keywords)
    body = _matching_terms([strip_frontmatter(record["text"])], keywords)

    if aliases:
        rank, label, matched = 4, "aliases", aliases
    elif metadata_keywords:
        rank, label, matched = 3, "keywords", metadata_keywords
    elif tags:
        rank, label, matched = 2, "tags", tags
    elif title or body:
        rank, label, matched = 1, "标题" if title else "正文", title or body
    else:
        return None

    score = rank * 10000
    score += len(matched) * 400
    score += len(aliases) * 40 + len(metadata_keywords) * 30 + len(tags) * 20
    if record["kind"] == "归档文档":
        score += 10
    if record["status"] == "completed":
        score += 2
    if is_low_signal_title(record["title"]):
        score -= 10
    return {
        "score": score,
        "match_label": label,
        "matched_terms": matched,
    }


def summarize_hit(record: dict, keywords: list[str]) -> str:
    for heading in SUMMARY_SECTIONS:
        block = record["sections"].get(heading, "")
        for item in parse_items(block):
            lower_item = item.lower()
            if any(kw.lower() in lower_item for kw in keywords):
                return clamp_text(item)

    body = strip_frontmatter(record["text"])
    flat = normalize_space(body)
    lower = flat.lower()
    for kw in keywords:
        idx = lower.find(kw.lower())
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(flat), idx + len(kw) + 80)
            snippet = flat[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(flat):
                snippet = snippet + "..."
            return snippet

    for heading in SUMMARY_SECTIONS:
        block = record["sections"].get(heading, "")
        items = parse_items(block)
        if items:
            return clamp_text(items[0])
    return clamp_text(flat)


def build_record(path: Path, rel: Path, text: str) -> dict:
    sections = {heading: extract_block(text, heading) for heading in SUMMARY_SECTIONS}
    kind = (
        "断点笔记"
        if len(rel.parts) >= 2 and rel.parts[0] == "Codex工作记录" and rel.parts[1] == "会话断点"
        else "归档文档"
    )
    return {
        "path": path,
        "rel": rel,
        "text": text,
        "sections": sections,
        "kind": kind,
        "title": extract_h1(text, path.stem),
        "date": extract_frontmatter_value(text, "date"),
        "status": extract_frontmatter_value(text, "status"),
        "tags": extract_list(text, "tags"),
        "category": extract_list(text, "category"),
        "keywords": extract_list(text, "keywords"),
        "aliases": extract_list(text, "aliases"),
        "corpus": build_search_corpus(text),
    }


def main():
    args = parse_args()
    vault_root = Path(args.vault_root).expanduser().resolve()
    if not vault_root.is_dir():
        print(f"未找到知识库：{vault_root}")
        sys.exit(1)

    matches = []
    for path in sorted(vault_root.rglob("*.md")):
        if path.name == "知识库首页.md":
            continue
        rel = path.relative_to(vault_root)
        if len(rel.parts) >= 2 and rel.parts[0] == "Codex工作记录" and rel.parts[1] == "会话索引":
            continue
        text = read_text(path)
        if not text:
            continue
        record = build_record(path, rel, text)
        body_fallback = _matching_terms(
            [record["title"], strip_frontmatter(record["text"])],
            args.keywords,
        )
        if is_sparse_doc(record) and not body_fallback:
            continue
        match = score_text(record, args.keywords)
        if not match:
            continue
        record.update(match)
        record["summary"] = summarize_hit(record, args.keywords)
        matches.append(record)

    if not matches:
        print("没有找到相关内容。")
        return

    matches.sort(key=lambda item: (-item["score"], item["kind"] != "归档文档", str(item["rel"])))
    selected = matches[: args.limit]
    archive = [m for m in selected if m["kind"] == "归档文档"]
    notes = [m for m in selected if m["kind"] == "断点笔记"]

    print(f"## 搜索结果：{' '.join(args.keywords)}\n")
    if archive:
        print("**归档文档**")
        for item in archive:
            match_text = f" · {item['match_label']} 命中: {', '.join(item['matched_terms'])}"
            link = f"[[{item['rel'].with_suffix('')}|{item['title']}]]"
            print(f"- {link}{match_text} — {item['summary']}")
        print()
    if notes:
        print("**断点笔记**")
        for item in notes:
            extra = " · ".join(part for part in (item["date"], item["status"]) if part)
            summary = f" — {item['summary']}" if item["summary"] else ""
            match_text = f" · {item['match_label']} 命中: {', '.join(item['matched_terms'])}"
            link = f"[[{item['rel'].with_suffix('')}|{item['title']}]]"
            if extra:
                print(f"- {link} — {extra}{match_text}{summary}")
            else:
                print(f"- {link}{match_text}{summary}")


if __name__ == "__main__":
    main()
