#!/usr/bin/env python3
"""Search Codex Obsidian notes with better ranking and summaries."""

import argparse
import hashlib
import math
import os
import re
import sqlite3
import struct
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
SEMANTIC_MODEL_DEFAULT = "intfloat/multilingual-e5-small"
SEMANTIC_MIN_SCORE = 0.52
SEMANTIC_CHUNK_SIZE = 480
SEMANTIC_CHUNK_OVERLAP = 80
INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    relative_path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_vectors (
    relative_path TEXT NOT NULL,
    model_name TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (relative_path, model_name)
);

CREATE INDEX IF NOT EXISTS idx_semantic_vectors_model ON semantic_vectors(model_name);

CREATE TABLE IF NOT EXISTS semantic_chunks (
    relative_path TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    heading TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL,
    PRIMARY KEY (relative_path, ordinal, model_name)
);

CREATE INDEX IF NOT EXISTS idx_semantic_chunks_model ON semantic_chunks(model_name);
"""


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("keywords", nargs="*")
    parser.add_argument("--vault-root", default=str(Path("~/obsidian/知识库").expanduser()))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--rebuild-index", action="store_true", help="重建当前 vault 的本地搜索索引")
    parser.add_argument("--index-status", action="store_true", help="显示当前 vault 的本地搜索索引状态")
    parser.add_argument("--semantic-status", action="store_true", help="检查本地语义模型与向量缓存状态，不下载模型")
    parser.add_argument("--no-index", action="store_true", help="跳过本地索引，直接扫描 Markdown")
    parser.add_argument("--semantic", action="store_true", help="使用本地已缓存模型进行语义召回，不可用时保持词法检索")
    parser.add_argument("--semantic-model", default=SEMANTIC_MODEL_DEFAULT, help="本地语义模型名称，默认 intfloat/multilingual-e5-small")
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


def is_searchable_path(rel: Path) -> bool:
    if rel.name == "知识库首页.md":
        return False
    return not (len(rel.parts) >= 2 and rel.parts[0] == "Codex工作记录" and rel.parts[1] == "会话索引")


def search_index_path(vault_root: Path) -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    digest = hashlib.sha256(str(vault_root).encode("utf-8")).hexdigest()[:16]
    return codex_home / "cache" / f"cxcp-search-{digest}.sqlite3"


def semantic_chunks_for(record: dict) -> list[dict]:
    """Split a note into compact title-aware passages for semantic recall."""
    body = strip_frontmatter(record["text"])
    body = re.sub(r"^#\s+.*(?:\n|$)", "", body, count=1).strip()
    sections = re.split(r"\n(?=##\s+)", body) if body else []
    chunks = []
    for section in sections:
        heading = ""
        content = section.strip()
        matched = re.match(r"^##\s+(.+?)\s*\n([\s\S]*)$", content)
        if matched:
            heading = matched.group(1).strip()
            content = matched.group(2).strip()
        if not content:
            continue
        prefix = f"# {record['title']}"
        if heading:
            prefix += f"\n## {heading}"
        max_body_length = max(SEMANTIC_CHUNK_SIZE - len(prefix) - 2, 120)
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
        buffer = ""

        def append_chunk(value: str) -> None:
            normalized = value.strip()
            if normalized:
                chunks.append({"heading": heading, "content": f"{prefix}\n\n{normalized}"})

        for paragraph in paragraphs:
            if len(paragraph) > max_body_length:
                if buffer:
                    append_chunk(buffer)
                    buffer = ""
                start = 0
                while start < len(paragraph):
                    append_chunk(paragraph[start : start + max_body_length])
                    start += max_body_length - SEMANTIC_CHUNK_OVERLAP
                continue
            separator = "\n\n" if buffer else ""
            if buffer and len(buffer) + len(separator) + len(paragraph) > max_body_length:
                append_chunk(buffer)
                overlap = buffer[-SEMANTIC_CHUNK_OVERLAP:].strip()
                buffer = overlap + ("\n\n" if overlap else "") + paragraph
            else:
                buffer += separator + paragraph
        if buffer:
            append_chunk(buffer)
    return chunks


def semantic_fingerprint(record: dict) -> str:
    return hashlib.sha256(record["text"].encode("utf-8")).hexdigest()


def vector_to_blob(values: list[float]) -> bytes:
    if not values:
        return b""
    return struct.pack(f"<{len(values)}f", *(float(value) for value in values))


def blob_to_vector(value: bytes) -> list[float]:
    if not value or len(value) % 4:
        return []
    return list(struct.unpack(f"<{len(value) // 4}f", value))


def vector_values(value) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def load_local_semantic_model(model_name: str):
    """Load an already-cached model without allowing a network download."""
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, local_files_only=True), ""
    except Exception as error:
        return None, f"本地语义模型不可用，已保持词法检索：{error}"


def print_semantic_status(vault_root: Path, model_name: str) -> bool:
    """Report local semantic readiness without downloading models or indexing notes."""
    index_path = search_index_path(vault_root)
    model, notice = load_local_semantic_model(model_name)
    print("## 语义检索状态")
    print(f"模型：`{model_name}`")
    print(f"向量缓存：`{index_path}`{'，已存在。' if index_path.exists() else '，尚未建立。'}")
    if model is None:
        print("本地模型：未就绪。")
        print(notice)
        print("准备模型后可再次运行本命令；默认搜索始终可用。")
        return False
    print("本地模型：可用，后续 --semantic 会保持离线加载。")
    return True


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def semantic_scores(
    records: list[dict],
    vault_root: Path,
    query: str,
    model_name: str,
    *,
    use_cache: bool,
) -> tuple[dict[str, dict], str]:
    """Return the highest-scoring local semantic passage for each document."""
    model, notice = load_local_semantic_model(model_name)
    if model is None:
        return {}, notice
    if not records:
        return {}, ""
    fingerprints = {record["rel"].as_posix(): semantic_fingerprint(record) for record in records}
    chunks_by_path = {
        record["rel"].as_posix(): semantic_chunks_for(record)
        for record in records
    }
    vectors: dict[str, list[dict]] = {}
    connection = None
    try:
        if use_cache:
            index_path = search_index_path(vault_root)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(index_path)
            connection.executescript(INDEX_SCHEMA)
            for relative, fingerprint in fingerprints.items():
                rows = list(connection.execute(
                    "SELECT ordinal, heading, content, embedding FROM semantic_chunks "
                    "WHERE relative_path = ? AND model_name = ? AND fingerprint = ? ORDER BY ordinal",
                    (relative, model_name, fingerprint),
                ))
                expected = chunks_by_path[relative]
                if len(rows) != len(expected) or [row[0] for row in rows] != list(range(len(expected))):
                    continue
                cached = []
                for ordinal, heading, content, blob in rows:
                    vector = blob_to_vector(blob)
                    if not vector:
                        cached = []
                        break
                    cached.append({"ordinal": ordinal, "heading": heading, "content": content, "vector": vector})
                if cached:
                    vectors[relative] = cached

        missing = []
        for relative, chunks in chunks_by_path.items():
            if relative in vectors:
                continue
            if connection is not None:
                connection.execute(
                    "DELETE FROM semantic_chunks WHERE relative_path = ? AND model_name = ?",
                    (relative, model_name),
                )
            for ordinal, chunk in enumerate(chunks):
                missing.append({"relative": relative, "ordinal": ordinal, **chunk})
        if missing:
            passages = [f"passage: {item['content']}" for item in missing]
            encoded = model.encode(passages, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
            for item, value in zip(missing, encoded):
                relative = item["relative"]
                vector = vector_values(value)
                if not vector:
                    continue
                vectors.setdefault(relative, []).append({
                    "ordinal": item["ordinal"],
                    "heading": item["heading"],
                    "content": item["content"],
                    "vector": vector,
                })
                if connection is not None:
                    connection.execute(
                        "INSERT OR REPLACE INTO semantic_chunks "
                        "(relative_path, ordinal, model_name, fingerprint, heading, content, embedding) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            relative,
                            item["ordinal"],
                            model_name,
                            fingerprints[relative],
                            item["heading"],
                            item["content"],
                            vector_to_blob(vector),
                        ),
                    )
        query_value = model.encode([f"query: {normalize_space(query)}"], normalize_embeddings=True, show_progress_bar=False)[0]
        query_vector = vector_values(query_value)
        if connection is not None:
            connection.commit()
        matches = {}
        for relative, items in vectors.items():
            ranked = [
                {**item, "score": cosine_similarity(query_vector, item["vector"])}
                for item in items
            ]
            if ranked:
                matches[relative] = max(ranked, key=lambda item: item["score"])
        return matches, ""
    except Exception as error:
        return {}, f"本地语义检索失败，已保持词法检索：{error}"
    finally:
        if connection is not None:
            connection.close()


def semantic_summary(match: dict) -> str:
    content = match.get("content", "")
    parts = content.split("\n\n", 1)
    return clamp_text(parts[-1] if len(parts) == 2 else content, limit=180)


def scan_records(vault_root: Path) -> list[dict]:
    records = []
    for path in sorted(vault_root.rglob("*.md")):
        rel = path.relative_to(vault_root)
        if not is_searchable_path(rel):
            continue
        text = read_text(path)
        if text:
            records.append(build_record(path, rel, text))
    return records


def indexed_records(vault_root: Path, rebuild: bool = False) -> tuple[list[dict], dict]:
    """Refresh a per-vault SQLite cache without touching the user's Markdown files."""
    index_path = search_index_path(vault_root)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(index_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(INDEX_SCHEMA)
        if rebuild:
            connection.execute("DELETE FROM documents")
            connection.execute("DELETE FROM semantic_vectors")
            connection.execute("DELETE FROM semantic_chunks")
        existing = {
            row[0]: (row[1], row[2])
            for row in connection.execute("SELECT relative_path, mtime_ns, size FROM documents")
        }
        discovered = set()
        indexed = 0
        skipped = 0
        for path in sorted(vault_root.rglob("*.md")):
            rel = path.relative_to(vault_root)
            if not is_searchable_path(rel):
                continue
            relative = rel.as_posix()
            discovered.add(relative)
            try:
                stat = path.stat()
            except OSError:
                continue
            fingerprint = (stat.st_mtime_ns, stat.st_size)
            if existing.get(relative) == fingerprint:
                skipped += 1
                continue
            text = read_text(path)
            if not text:
                continue
            connection.execute("DELETE FROM semantic_vectors WHERE relative_path = ?", (relative,))
            connection.execute("DELETE FROM semantic_chunks WHERE relative_path = ?", (relative,))
            connection.execute(
                "INSERT OR REPLACE INTO documents (relative_path, mtime_ns, size, text) VALUES (?, ?, ?, ?)",
                (relative, fingerprint[0], fingerprint[1], text),
            )
            indexed += 1
        stale = set(existing).difference(discovered)
        if stale:
            connection.executemany("DELETE FROM documents WHERE relative_path = ?", ((value,) for value in stale))
            connection.executemany("DELETE FROM semantic_vectors WHERE relative_path = ?", ((value,) for value in stale))
            connection.executemany("DELETE FROM semantic_chunks WHERE relative_path = ?", ((value,) for value in stale))
        connection.commit()
        rows = list(connection.execute("SELECT relative_path, text FROM documents ORDER BY relative_path"))
    finally:
        connection.close()
    records = [build_record(vault_root / relative, Path(relative), text) for relative, text in rows]
    return records, {
        "path": index_path,
        "indexed": indexed,
        "skipped": skipped,
        "removed": len(stale),
        "documents": len(records),
    }


def main():
    args = parse_args()
    vault_root = Path(args.vault_root).expanduser().resolve()
    if not vault_root.is_dir():
        print(f"未找到知识库：{vault_root}")
        sys.exit(1)

    if args.limit < 1:
        print("--limit 必须是正整数。", file=sys.stderr)
        sys.exit(2)
    maintenance_modes = sum((args.rebuild_index, args.index_status, args.semantic_status))
    if maintenance_modes > 1:
        print("一次只能选择一种索引或语义状态检查模式。", file=sys.stderr)
        sys.exit(2)
    if maintenance_modes and args.keywords:
        print("索引或语义状态检查模式不能同时提供搜索关键词。", file=sys.stderr)
        sys.exit(2)
    if args.semantic_status and args.semantic:
        print("--semantic-status 不能与 --semantic 同时使用。", file=sys.stderr)
        sys.exit(2)
    if not args.keywords and not maintenance_modes:
        print("请提供至少一个搜索关键词。", file=sys.stderr)
        sys.exit(2)

    if args.semantic_status:
        print_semantic_status(vault_root, args.semantic_model)
        return

    index_stats = None
    if args.no_index:
        records = scan_records(vault_root)
    else:
        try:
            records, index_stats = indexed_records(vault_root, rebuild=args.rebuild_index)
        except (OSError, sqlite3.Error) as error:
            print(f"本地搜索索引不可用，已回退 Markdown 扫描：{error}", file=sys.stderr)
            records = scan_records(vault_root)

    if args.rebuild_index:
        if index_stats:
            print(
                f"搜索索引已重建：{index_stats['documents']} 篇文档，"
                f"更新 {index_stats['indexed']} 篇，缓存：{index_stats['path']}"
            )
        return
    if args.index_status:
        if index_stats:
            print(
                f"搜索索引状态：{index_stats['documents']} 篇文档，"
                f"本次更新 {index_stats['indexed']} 篇，跳过 {index_stats['skipped']} 篇，"
                f"移除 {index_stats['removed']} 篇，缓存：{index_stats['path']}"
            )
        else:
            print("当前使用直接 Markdown 扫描，未创建本地搜索索引。")
        return

    semantic_matches = {}
    if args.semantic:
        semantic_matches, semantic_notice = semantic_scores(
            records,
            vault_root,
            " ".join(args.keywords),
            args.semantic_model,
            use_cache=not args.no_index,
        )
        if semantic_notice:
            print(semantic_notice, file=sys.stderr)

    matches = []
    for record in records:
        body_fallback = _matching_terms(
            [record["title"], strip_frontmatter(record["text"])],
            args.keywords,
        )
        semantic_match = semantic_matches.get(record["rel"].as_posix(), {})
        semantic_score = semantic_match.get("score", 0.0)
        match = score_text(record, args.keywords)
        if is_sparse_doc(record) and not body_fallback and not match and semantic_score < SEMANTIC_MIN_SCORE:
            continue
        if not match and semantic_score < SEMANTIC_MIN_SCORE:
            continue
        if match is None:
            match = {
                # Lexical results begin at 10,000 and always retain their existing
                # priority over a semantic-only recall result.
                "score": int(semantic_score * 1000),
                "match_label": "语义",
                "matched_terms": [f"{semantic_score:.2f}"],
            }
        record.update(match)
        record["semantic_score"] = semantic_score
        record["summary"] = (
            semantic_summary(semantic_match)
            if match["match_label"] == "语义" and semantic_match
            else summarize_hit(record, args.keywords)
        )
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
            if item["match_label"] == "语义":
                match_text = f" · 语义相似: {item['semantic_score']:.2f}"
            else:
                match_text = f" · {item['match_label']} 命中: {', '.join(item['matched_terms'])}"
            link = f"[[{item['rel'].with_suffix('')}|{item['title']}]]"
            print(f"- {link}{match_text} — {item['summary']}")
        print()
    if notes:
        print("**断点笔记**")
        for item in notes:
            extra = " · ".join(part for part in (item["date"], item["status"]) if part)
            summary = f" — {item['summary']}" if item["summary"] else ""
            if item["match_label"] == "语义":
                match_text = f" · 语义相似: {item['semantic_score']:.2f}"
            else:
                match_text = f" · {item['match_label']} 命中: {', '.join(item['matched_terms'])}"
            link = f"[[{item['rel'].with_suffix('')}|{item['title']}]]"
            if extra:
                print(f"- {link} — {extra}{match_text}{summary}")
            else:
                print(f"- {link}{match_text}{summary}")


if __name__ == "__main__":
    main()
