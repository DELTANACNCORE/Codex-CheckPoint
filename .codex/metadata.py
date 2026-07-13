"""Shared frontmatter metadata utilities for CxCP."""

from __future__ import annotations

import json
import re
from pathlib import Path


_BASE_NOISE_VALUES = {
    "",
    "/",
    "\\",
    ".",
    "..",
    "~",
    "home",
    "user",
    "users",
    "projects",
    "src",
    "code",
    "dev",
    "desktop",
    "documents",
    "downloads",
    "tmp",
    "var",
    "private",
    "opt",
    "etc",
    "usr",
    "library",
    "applications",
    "obsidian",
    "知识库",
    "codex",
    "codex方案",
    "codex工作记录",
    "claude",
    "claude方案",
    "hooks",
    "skills",
    "memory",
    "worktrees",
    "项目总结",
    "ai开发参考",
    "长期经验总结",
    "经验摘要",
    "checkpoint-convention",
    "readme-update-rule",
    "settings",
}


def clean_metadata_value(value: object) -> str:
    """Return a compact frontmatter value without surrounding quotes."""
    text = str(value or "").strip().strip("\"'")
    return re.sub(r"\s+", " ", text)


def _noise_values() -> set[str]:
    values = set(_BASE_NOISE_VALUES)
    values.update(part.casefold() for part in Path.home().parts if part not in {"/", "\\"})
    return values


METADATA_NOISE_VALUES = _noise_values()


def is_valid_generated_metadata(value: object) -> bool:
    """Reject filesystem and runtime path fragments from generated metadata."""
    text = clean_metadata_value(value)
    if not text or text.casefold() in METADATA_NOISE_VALUES:
        return False
    if text.startswith(".") or text.startswith("-"):
        return False
    return True


def metadata_values(*values: object, limit: int | None = None, filter_noise: bool = False) -> list[str]:
    """Flatten, deduplicate, and optionally filter metadata values.

    Existing user-authored values remain untouched. Generated values use noise
    filtering so path fragments never enter frontmatter.
    """
    result = []
    seen = set()

    def add(value: object) -> bool:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if add(item):
                    return True
            return False
        text = clean_metadata_value(value)
        if not text or (filter_noise and not is_valid_generated_metadata(text)):
            return False
        key = text.casefold()
        if key in seen:
            return False
        seen.add(key)
        result.append(text)
        return bool(limit and len(result) >= limit)

    for value in values:
        if add(value):
            break
    return result


def metadata_leaf_values(values: object, limit: int | None = None) -> list[str]:
    """Return generated leaf terms from hierarchical tags."""
    leaves = []
    for value in metadata_values(values):
        leaves.append(value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])
    return metadata_values(leaves, limit=limit, filter_noise=True)


def frontmatter_block(text: str) -> str:
    """Return the YAML frontmatter block, or an empty string when absent."""
    source = str(text or "").lstrip("\ufeff")
    if not source.startswith("---\n"):
        return ""
    end = re.search(r"\n---[ \t]*(?:\n|$)", source[4:])
    if not end:
        return ""
    return source[4 : 4 + end.start()]


def _scalar_values(value: str) -> list[str]:
    text = clean_metadata_value(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            text = text[1:-1]
        else:
            if isinstance(parsed, list):
                return metadata_values(parsed)
            return []
    if any(separator in text for separator in (",", "，", "、")):
        return metadata_values(re.split(r"[,，、]", text))
    return metadata_values([text])


def parse_frontmatter_list(text: str, key: str) -> list[str]:
    """Read JSON, delimiter-separated, or YAML-block list fields."""
    frontmatter = frontmatter_block(text)
    if not frontmatter:
        return []
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*)$", frontmatter, re.MULTILINE)
    if not match:
        return []
    inline = match.group(1).strip()
    if inline:
        return _scalar_values(inline)

    values = []
    for line in frontmatter[match.end() :].splitlines():
        if not line.strip():
            continue
        item = re.match(r"^[ \t]*-[ \t]+(.+?)\s*$", line)
        if item:
            values.append(item.group(1))
            continue
        break
    return metadata_values(values)
