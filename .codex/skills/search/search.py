#!/usr/bin/env python3
"""Search Codex Obsidian notes with better ranking and summaries."""

import argparse
import json
import re
import sys
from pathlib import Path


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


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("keywords", nargs="+")
    parser.add_argument("--vault-root", default=str(Path("~/obsidian/知识库").expanduser()))
    parser.add_argument("--limit", type=int, default=8)
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
    m = re.search(rf"^{re.escape(key)}:\s*(\[.*\])", text, re.MULTILINE)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


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
    if record["tags"] or record["category"] or record["keywords"]:
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


def score_text(record: dict, keywords: list[str]) -> int:
    score = 0
    title = record["title"].lower()
    corpus = record["corpus"].lower()
    tags_joined = " ".join(record["tags"]).lower()
    path_text = str(record["rel"]).lower()

    for kw in keywords:
        key = kw.lower()
        score += corpus.count(key)
        score += title.count(key) * 8
        score += tags_joined.count(key) * 5
        score += path_text.count(key) * 4

    if record["kind"] == "归档文档":
        score += 20
    if len(record["rel"].parts) >= 3 and record["kind"] == "归档文档":
        score += 12
    if "更新日志" in record["title"]:
        score += 18
    if "项目总结" in record["title"]:
        score += 16
    if any(label in record["title"] for label in ("AI开发参考", "长期经验总结", "可复用经验")):
        score += 14
    if "知识合成" in record["tags"]:
        score += 10
    if record["status"] == "completed":
        score += 4
    if is_low_signal_title(record["title"]):
        score -= 10
    if is_sparse_doc(record):
        score -= 25
    return score


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
        if is_sparse_doc(record):
            continue
        score = score_text(record, args.keywords)
        if score <= 0:
            continue
        record["score"] = score
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
            tag_text = f" · tags: {', '.join(item['tags'][:4])}" if item["tags"] else ""
            link = f"[[{item['rel'].with_suffix('')}|{item['title']}]]"
            print(f"- {link} — {item['summary']}{tag_text}")
        print()
    if notes:
        print("**断点笔记**")
        for item in notes:
            extra = " · ".join(part for part in (item["date"], item["status"]) if part)
            summary = f" — {item['summary']}" if item["summary"] else ""
            link = f"[[{item['rel'].with_suffix('')}|{item['title']}]]"
            if extra:
                print(f"- {link} — {extra}{summary}")
            else:
                print(f"- {link}{summary}")


if __name__ == "__main__":
    main()
