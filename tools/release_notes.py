#!/usr/bin/env python3
"""Build a validated bilingual GitHub Release body from the Obsidian changelog."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_CHANGELOG = Path("~/obsidian/知识库/Codex协同Obsidian工作流skill更新日志.md").expanduser()


def normalized_version(value: str) -> str:
    version = str(value or "").strip().lstrip("Vv")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?", version):
        raise ValueError("版本号必须采用 x.y.z 格式。")
    return version


def version_section(text: str, version: str) -> str:
    heading = re.compile(rf"^##\s+V?{re.escape(version)}\s*$", re.MULTILINE | re.IGNORECASE)
    matched = heading.search(text)
    if matched is None:
        raise ValueError(f"更新日志缺少 V{version} 章节。")
    next_heading = re.search(r"^##\s+", text[matched.end() :], re.MULTILINE)
    end = matched.end() + next_heading.start() if next_heading else len(text)
    return text[matched.end() : end]


def release_section(text: str, version: str) -> str:
    section = version_section(text, version)
    heading = re.compile(r"^###\s+(?:GitHub\s+Release|GitHub\s+发布)\s*$", re.MULTILINE | re.IGNORECASE)
    matched = heading.search(section)
    if matched is None:
        raise ValueError(f"V{version} 缺少 GitHub Release 双语发布段。")
    next_heading = re.search(r"^###\s+", section[matched.end() :], re.MULTILINE)
    end = matched.end() + next_heading.start() if next_heading else len(section)
    return section[matched.end() : end].strip()


def release_entries(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    entries = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        bullet = re.match(r"^-\s+(.+?)\s*$", line)
        if bullet is None:
            raise ValueError(f"发布段第 {index + 1} 行必须以 '- ' 开始。")
        chinese = bullet.group(1).strip()
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines) or not re.match(r"^\s{2,}\S", lines[index]):
            raise ValueError(f"发布项“{chinese}”缺少缩进的英文描述。")
        english = lines[index].strip()
        if not re.search(r"[\u4e00-\u9fff]", chinese):
            raise ValueError(f"发布项“{chinese}”缺少中文描述。")
        if not re.search(r"[A-Za-z]", english):
            raise ValueError(f"发布项“{chinese}”缺少英文描述。")
        entries.append((chinese, english))
        index += 1
    if not entries:
        raise ValueError("GitHub Release 发布段没有可发布的条目。")
    return entries


def build_release_body(changelog: Path, version: str) -> str:
    try:
        text = changelog.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"无法读取更新日志：{changelog}") from error
    normalized = normalized_version(version)
    entries = release_entries(release_section(text, normalized))
    lines = [f"V{normalized}", ""]
    for chinese, english in entries:
        lines.extend((f"- {chinese}", f"  {english}"))
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从 Obsidian 更新日志生成双语 GitHub Release 正文")
    parser.add_argument("--version", required=True, help="发布版本，例如 1.0.0")
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    parser.add_argument("--output", type=Path, help="可选的正文输出文件；缺省时写到标准输出")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        body = build_release_body(args.changelog.expanduser(), args.version)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.output:
        args.output.expanduser().write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
