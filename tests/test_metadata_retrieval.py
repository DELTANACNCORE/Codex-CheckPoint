#!/usr/bin/env python3
"""Regression coverage for CxCP metadata generation and retrieval."""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_ROOT = REPO_ROOT / ".codex"
HOOK = CODEX_ROOT / "hooks" / "checkpoint.py"
RETRIEVE = CODEX_ROOT / "hooks" / "retrieve.py"
SEARCH = CODEX_ROOT / "skills" / "search" / "search.py"
SYNTHESIZE = CODEX_ROOT / "skills" / "synthesize" / "synthesize.py"

if str(CODEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEX_ROOT))

from metadata import parse_frontmatter_list


def load_checkpoint(vault: Path):
    previous_vault = os.environ.get("OBSIDIAN_VAULT")
    os.environ["OBSIDIAN_VAULT"] = str(vault)
    try:
        spec = importlib.util.spec_from_file_location(f"metadata_checkpoint_{id(vault)}", HOOK)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_vault is None:
            os.environ.pop("OBSIDIAN_VAULT", None)
        else:
            os.environ["OBSIDIAN_VAULT"] = previous_vault


class MetadataParsingTest(unittest.TestCase):
    def test_parser_supports_json_delimited_and_yaml_block_lists(self) -> None:
        text = """---
aliases: ["Netplan", "网卡切换"]
keywords: Docker，Nginx, MySQL
tags:
  - 运维/网络
  - shell/Netplan
---

# 测试
"""
        self.assertEqual(parse_frontmatter_list(text, "aliases"), ["Netplan", "网卡切换"])
        self.assertEqual(parse_frontmatter_list(text, "keywords"), ["Docker", "Nginx", "MySQL"])
        self.assertEqual(parse_frontmatter_list(text, "tags"), ["运维/网络", "shell/Netplan"])

    def test_checkpoint_filters_path_noise_and_preserves_manual_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            checkpoint = load_checkpoint(vault)
            noisy_path = (
                Path.home()
                / "obsidian"
                / ".codex"
                / "worktrees"
                / "temporary-worktree"
                / "项目甲"
                / "src"
                / "netplan-switch.py"
            )
            tags, keywords = checkpoint._fallback_tags_from_files([str(noisy_path)])
            combined = {value.casefold() for value in tags + keywords}
            self.assertIn("项目甲", tags)
            self.assertIn("netplan-switch", combined)
            self.assertFalse(
                {"users", Path.home().name.casefold(), "obsidian", "worktrees", "temporary-worktree", "src"}
                & combined
            )

            ctx = {
                "topic": "Ubuntu 网卡切换",
                "title_baseline": "Ubuntu 网卡切换",
                "title_source": "assistant",
                "checkpoint_category": "",
                "knowledge_archived": False,
                "projects": set(),
                "external_projects": set(),
                "category": [],
                "tags": ["运维/网络"],
                "keywords": [],
                "aliases": [],
                "user_prompts": ["配置 Ubuntu 网卡切换"],
                "assistant_updates": ["已完成 Netplan 网卡切换验证。"],
                "latest_assistant_update": "已完成 Netplan 网卡切换验证。",
                "written_files": set(),
                "external_written_files": set(),
                "used_plan_mode": False,
                "verbal_plan_snippets": [],
            }
            generated = checkpoint.generate_session_note("metadata-session", ctx, "completed")
            self.assertEqual(parse_frontmatter_list(generated, "keywords"), ["网络"])
            self.assertEqual(
                parse_frontmatter_list(generated, "aliases"),
                ["Ubuntu 网卡切换", "网络", "运维/网络"],
            )

            ctx["keywords"] = ["手工关键词"]
            ctx["aliases"] = ["手工入口"]
            preserved = checkpoint.generate_session_note("metadata-session", ctx, "completed")
            self.assertEqual(parse_frontmatter_list(preserved, "keywords"), ["手工关键词"])
            self.assertEqual(parse_frontmatter_list(preserved, "aliases"), ["手工入口"])

    def test_automatic_project_summary_enriches_metadata_without_creating_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            checkpoint = load_checkpoint(vault)
            note = vault / "Codex工作记录" / "会话断点" / "未分类对话" / "自动项目.md"
            note.parent.mkdir(parents=True)
            note.write_text(
                """---
session_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
keywords: ["Netplan"]
aliases: ["自动网卡入口"]
---

# 自动项目
""",
                encoding="utf-8",
            )
            written = checkpoint.update_project_knowledge(
                {
                    "projects": {"自动元数据项目"},
                    "tags": ["运维/网络"],
                    "keywords": ["Netplan"],
                    "status": "completed",
                    "user_prompts": ["整理自动项目的 Netplan 网卡配置。"],
                    "written_files": set(),
                    "external_written_files": set(),
                    "latest_assistant_update": "Netplan 配置已经验证。",
                },
                note,
            )
            self.assertEqual(len(written), 1)
            summary_text = written[0].read_text(encoding="utf-8")
            self.assertIn("Netplan", parse_frontmatter_list(summary_text, "keywords"))
            self.assertIn("自动元数据项目", parse_frontmatter_list(summary_text, "aliases"))
            self.assertFalse((vault / "AI开发参考" / "自动元数据项目.md").exists())

    def test_regular_refresh_preserves_existing_aliases_and_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            home = root / "home"
            (vault / ".obsidian").mkdir(parents=True)
            session_id = "cccccccc-dddd-eeee-ffff-000000000000"
            rollout = home / ".codex" / "sessions" / "2026" / "07" / "14" / f"rollout-2026-07-14T10-00-00-{session_id}.jsonl"
            entries = []
            for round_number in range(5):
                entries.extend((
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": f"配置 Netplan 网卡切换，第 {round_number + 1} 轮。"}],
                        },
                    },
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": f"第 {round_number + 1} 轮 Netplan 验证完成。"}],
                        },
                    },
                ))
            rollout.parent.mkdir(parents=True)
            rollout.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")
            env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(home / ".codex")}
            command = [
                sys.executable,
                str(HOOK),
                "--vault-root",
                str(vault),
                "--transcript",
                str(rollout),
                "--session-id",
                session_id,
            ]
            first = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            note = next((vault / "Codex工作记录" / "会话断点").rglob("*.md"))
            original = note.read_text(encoding="utf-8")
            updated = re.sub(r"^keywords:.*$", 'keywords: ["手工关键词"]', original, flags=re.MULTILINE)
            updated = re.sub(r"^aliases:.*$", 'aliases: ["手工入口"]', updated, flags=re.MULTILINE)
            note.write_text(updated, encoding="utf-8")

            second = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            refreshed = note.read_text(encoding="utf-8")
            self.assertEqual(parse_frontmatter_list(refreshed, "keywords"), ["手工关键词"])
            self.assertEqual(parse_frontmatter_list(refreshed, "aliases"), ["手工入口"])

            legacy = re.sub(r"^tags:.*$", 'tags: ["/", "obsidian", "知识库", "项目总结"]', refreshed, flags=re.MULTILINE)
            legacy = re.sub(r"^keywords:.*$", 'keywords: ["Netplan"]', legacy, flags=re.MULTILINE)
            legacy = re.sub(
                r"^aliases:.*$",
                'aliases: ["Netplan", "/", "obsidian", "知识库", "项目总结"]',
                legacy,
                flags=re.MULTILINE,
            )
            note.write_text(legacy, encoding="utf-8")

            repaired = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
            self.assertEqual(repaired.returncode, 0, repaired.stderr + repaired.stdout)
            repaired_text = note.read_text(encoding="utf-8")
            self.assertEqual(parse_frontmatter_list(repaired_text, "tags"), [])
            self.assertEqual(parse_frontmatter_list(repaired_text, "keywords"), ["Netplan"])
            aliases = parse_frontmatter_list(repaired_text, "aliases")
            self.assertIn("Netplan", aliases)
            self.assertFalse({"/", "obsidian", "知识库", "项目总结"} & set(aliases))


class SearchRankingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_note(self, name: str, frontmatter: str, title: str, body: str) -> None:
        path = self.vault / "项目总结" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\n{frontmatter}---\n\n# {title}\n\n{body}\n", encoding="utf-8")

    def test_alias_match_ranks_before_keyword_and_body_matches(self) -> None:
        self.write_note(
            "别名优先",
            "aliases:\n  - 专属入口\nkeywords: [\"普通词\"]\ntags: [\"运维/网络\"]\n",
            "别名命中文档",
            "这份内容不依赖正文命中。",
        )
        self.write_note(
            "关键词次级",
            "aliases: []\nkeywords: [\"专属入口\"]\ntags: [\"运维/网络\"]\n",
            "关键词命中文档",
            "关键词用于次级排序。",
        )
        self.write_note(
            "正文兜底",
            "aliases: []\nkeywords: []\ntags: []\n",
            "正文命中文档",
            "专属入口 只出现在正文。",
        )

        result = subprocess.run(
            [sys.executable, str(SEARCH), "--vault-root", str(self.vault), "专属入口"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("aliases 命中: 专属入口", result.stdout)
        self.assertLess(result.stdout.index("别名命中文档"), result.stdout.index("关键词命中文档"))
        self.assertLess(result.stdout.index("关键词命中文档"), result.stdout.index("正文命中文档"))


class RetrieveAliasRankingTest(unittest.TestCase):
    def test_recovery_prefers_alias_over_a_newer_title_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            home = root / "home"
            note_dir = vault / "Codex工作记录" / "会话断点" / "未分类对话"
            note_dir.mkdir(parents=True)
            (vault / ".obsidian").mkdir()
            alias_note = note_dir / "别名断点.md"
            alias_note.write_text(
                """---
session_id: "dddddddd-eeee-ffff-0000-111111111111"
status: "completed"
aliases:
  - 优先别名
---

# 别名断点

## 可直接续接的结论

- 别名断点的恢复结论已验证。
""",
                encoding="utf-8",
            )
            title_note = note_dir / "标题断点.md"
            title_note.write_text(
                """---
session_id: "eeeeeeee-ffff-0000-1111-222222222222"
status: "completed"
aliases: []
---

# 优先别名标题断点

## 可直接续接的结论

- 标题匹配的恢复结论已验证。
""",
                encoding="utf-8",
            )
            os.utime(title_note, None)
            env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(home / ".codex")}
            event = {"hook_event_name": "UserPromptSubmit", "prompt": "优先别名 恢复"}
            result = subprocess.run(
                [sys.executable, str(RETRIEVE), "--vault-root", str(vault)],
                input=json.dumps(event, ensure_ascii=False),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("别名断点", result.stdout)
            self.assertNotIn("优先别名标题断点", result.stdout)


class SynthesizeProjectSelectionTest(unittest.TestCase):
    def test_project_selection_rejects_generic_checkpoint_and_codex_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            home = root / "home"
            note_dir = vault / "Codex工作记录" / "会话断点" / "未分类对话"
            note_dir.mkdir(parents=True)
            (vault / ".obsidian").mkdir()

            target = note_dir / "迁移会话.md"
            target.write_text(
                """---
session_id: "12121212-1212-1212-1212-121212121212"
status: "completed"
projects: ["checkpoint迁到Codex"]
tags: ["codex/方案"]
keywords: ["metadata"]
aliases: ["checkpoint迁到Codex"]
---

# checkpoint 迁到 Codex

**已记录用户消息**: 8

## 可直接续接的结论

- metadata 检索迁移已完成。

## 已验证结果

- 迁移测试已通过。
""",
                encoding="utf-8",
            )
            unrelated = note_dir / "无关会话.md"
            unrelated.write_text(
                """---
session_id: "34343434-3434-3434-3434-343434343434"
status: "completed"
projects: []
tags: []
keywords: []
aliases: []
---

# 普通 Codex checkpoint 设置

**已记录用户消息**: 8

## 可直接续接的结论

- 这是无关会话，只包含常见的 Codex checkpoint 回执词。
""",
                encoding="utf-8",
            )
            env = {**os.environ, "HOME": str(home), "CODEX_HOME": str(home / ".codex")}
            result = subprocess.run(
                [
                    sys.executable,
                    str(SYNTHESIZE),
                    "--vault-root",
                    str(vault),
                    "--project",
                    "checkpoint迁到Codex",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("已归档断点数: 1", result.stdout)
            summary = (vault / "项目总结" / "checkpoint迁到Codex.md").read_text(encoding="utf-8")
            self.assertIn("12121212-1212-1212-1212-121212121212", summary)
            self.assertNotIn("34343434-3434-3434-3434-343434343434", summary)
            self.assertIn('status: "completed"', unrelated.read_text(encoding="utf-8"))
            self.assertNotIn("archive_document:", unrelated.read_text(encoding="utf-8"))


class SynthesizeMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.vault = self.root / "vault"
        self.home = self.root / "home"
        self.note_dir = self.vault / "Codex工作记录" / "会话断点" / "未分类对话"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.note_dir.mkdir(parents=True)
        (self.note_dir / "元数据会话.md").write_text(
            """---
session_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
status: "completed"
projects:
  - 元数据项目
tags:
  - 运维/网络
keywords: Netplan, Ubuntu
aliases:
  - 人工入口
---

# Ubuntu 网卡迁移

**已记录用户消息**: 24

## 可直接续接的结论

- Netplan 配置已经验证。

## 已验证结果

- Ubuntu 网卡切换成功。

## 会话目标演进

- 校验 Netplan 与 Ubuntu 的迁移配置。
- 整理网卡切换后的恢复方案和验证证据。

## 实际产出

- 已生成配置说明，并完成网卡状态、地址和路由的多轮验证记录。
""",
            encoding="utf-8",
        )
        summary = self.vault / "项目总结" / "元数据项目.md"
        summary.parent.mkdir(parents=True)
        summary.write_text(
            """---
project: 元数据项目
keywords:
  - 手工关键词
aliases:
  - 手工入口
---

# 旧总结
""",
            encoding="utf-8",
        )
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_synthesize_preserves_summary_metadata_and_writes_authorized_reference_metadata(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE),
                "--vault-root",
                str(self.vault),
                "--project",
                "元数据项目",
                "--long-term",
                "--user-approved",
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        summary_text = (self.vault / "项目总结" / "元数据项目.md").read_text(encoding="utf-8")
        self.assertEqual(parse_frontmatter_list(summary_text, "keywords"), ["手工关键词"])
        self.assertEqual(parse_frontmatter_list(summary_text, "aliases"), ["手工入口"])

        reference_text = (self.vault / "AI开发参考" / "元数据项目.md").read_text(encoding="utf-8")
        self.assertIn("user_authorized: true", reference_text)
        self.assertIn("Netplan", parse_frontmatter_list(reference_text, "keywords"))
        self.assertIn("人工入口", parse_frontmatter_list(reference_text, "aliases"))


if __name__ == "__main__":
    unittest.main()
