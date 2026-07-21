#!/usr/bin/env python3
"""Keep CxCP Skill descriptions Chinese-first for the Codex Skill picker."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / ".codex" / "skills"
EXPECTED_DESCRIPTIONS = {
    "checkpoint": "将当前 Codex 会话保存为 Obsidian 恢复断点。",
    "search": "按关键词搜索 vault 中的项目文档和 Codex 会话断点。",
    "synthesize": "跨会话聚合相关断点、生成知识文档并清理伪对话或重复断点。",
    "verify": "在当前环境重新执行测试、检查与诊断，再判断历史知识结论是否仍然有效。",
}


def description_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    matched = re.search(r"^description:\s*\|\s*$\n((?:^[ \t]+.*$\n?)*)", text, re.MULTILINE)
    if matched is None:
        return []
    return [line.strip() for line in matched.group(1).splitlines() if line.strip()]


class SkillDescriptionsTest(unittest.TestCase):
    def test_project_skills_have_chinese_first_descriptions(self) -> None:
        skill_files = {path.parent.name: path for path in SKILLS_ROOT.glob("*/SKILL.md")}

        self.assertEqual(set(skill_files), set(EXPECTED_DESCRIPTIONS))
        for name, expected in EXPECTED_DESCRIPTIONS.items():
            lines = description_lines(skill_files[name])
            self.assertGreaterEqual(len(lines), 2, name)
            self.assertEqual(lines[0], expected)
            self.assertRegex(lines[0], r"[\u4e00-\u9fff]")
            self.assertRegex(lines[1], r"[A-Za-z]")


if __name__ == "__main__":
    unittest.main()
