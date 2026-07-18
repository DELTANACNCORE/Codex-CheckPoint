#!/usr/bin/env python3
"""Coverage for CxCP's read-only audit and confirmed maintenance actions."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_ROOT = REPO_ROOT / ".codex"
if str(CODEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CODEX_ROOT))

from maintenance import (
    apply_metadata_candidates,
    audit_vault,
    broken_link_repair_candidates,
    link_candidates,
    scan_vault,
)


SYNTHESIZE = REPO_ROOT / ".codex" / "skills" / "synthesize" / "synthesize.py"
SESSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
DUPLICATE_SESSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ARCHIVED_SESSION = "11111111-2222-3333-4444-555555555555"
UNIQUE_SESSION = "99999999-8888-7777-6666-555555555555"


class KnowledgeMaintenanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        self.notes = self.vault / "Codex工作记录" / "会话断点" / "未分类对话"
        self.notes.mkdir(parents=True)
        (self.vault / ".obsidian").mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.home / ".codex")}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_checkpoint(self, name: str, session_id: str, *, status: str = "completed", archive_document: str = "") -> Path:
        path = self.notes / f"{name}.md"
        archive = f'archive_document: "{archive_document}"\n' if archive_document else ""
        path.write_text(
            f'''---
date: "2025-01-01"
session_id: "{session_id}"
status: "{status}"
projects: ["项目甲"]
category: ["开发与工程"]
tags: ["codex/方案", "Netplan"]
keywords: []
aliases: []
{archive}---

# Netplan Ubuntu 网卡迁移

## 已验证结果

- Netplan 配置已经验证。

## 可直接续接的结论

- Ubuntu 网卡迁移可以继续执行。
''',
            encoding="utf-8",
        )
        return path

    def write_document(self, relative: str, title: str, body: str) -> Path:
        path = self.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.replace("<TITLE>", title), encoding="utf-8")
        return path

    def create_fixture(self) -> tuple[Path, Path, Path]:
        first = self.write_checkpoint("Netplan 迁移", SESSION)
        self.write_checkpoint("Netplan 迁移副本", DUPLICATE_SESSION)
        self.write_checkpoint("失效归档", ARCHIVED_SESSION, status="archived", archive_document="项目总结/不存在.md")
        self.write_document(
            "项目总结/项目甲.md",
            "项目甲 项目总结",
            '''---
project: "项目甲"
keywords: ["项目甲"]
aliases: ["项目甲"]
---

# <TITLE>
''',
        )
        self.write_document(
            "Codex工作记录/会话索引/2025-01-01.md",
            "会话索引",
            '''# <TITLE>

| 时间 | 话题 |
|---|---|
| 01:00 | [[项目总结/项目甲\\|项目甲 项目总结]] |
''',
        )
        left = self.write_document(
            "项目总结/Netplan迁移.md",
            "Netplan 迁移项目总结",
            '''---
project: "Netplan迁移"
keywords: ["Netplan", "Ubuntu"]
aliases: ["Netplan 迁移"]
---

# <TITLE>

## 已验证能力

- Netplan 和 Ubuntu 网卡迁移已经验证。
''',
        )
        right = self.write_document(
            "AI开发参考/Netplan部署.md",
            "Netplan Ubuntu 部署参考",
            '''---
project: "Netplan迁移"
keywords: ["Netplan", "Ubuntu"]
aliases: ["Netplan 部署"]
---

# <TITLE>

## 操作方法

- 按 Netplan 配置执行 Ubuntu 网卡部署。

[[不存在的文档]]
''',
        )
        return first, left, right

    def run_synthesize(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SYNTHESIZE), "--vault-root", str(self.vault), *arguments],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_read_only_audit_reports_structure_and_metadata_candidates(self) -> None:
        first, _left, _right = self.create_fixture()
        (self.vault / "空文件.md").touch()
        sessions_root = self.home / ".codex" / "sessions"
        sessions_root.mkdir(parents=True)

        report = audit_vault(self.vault, stale_days=30, sessions_root=sessions_root)

        self.assertTrue(any("空 Markdown" in issue for issue in report["empty_files"]))
        self.assertTrue(any("重复 session_id" in issue for issue in report["duplicates"]))
        self.assertTrue(any("没有匹配 rollout" in issue for issue in report["missing_rollouts"]))
        self.assertTrue(any("归档目标不存在" in issue for issue in report["archives"]))
        self.assertTrue(any("不存在的文档" in issue for issue in report["links"]))
        self.assertFalse(any("项目总结/项目甲\\|" in issue for issue in report["links"]))
        self.assertTrue(any("验证记录已过" in issue for issue in report["stale_verification"]))
        self.assertTrue(any(item["session_id"] == SESSION for item in report["metadata_candidates"]))
        self.assertTrue(any(item["project"] == "项目甲" for item in report["knowledge_candidates"]))
        self.assertNotIn("aliases: [\"Netplan Ubuntu 网卡迁移\"]", first.read_text(encoding="utf-8"))

        cli = self.run_synthesize("--audit", "--stale-days", "30")
        self.assertEqual(cli.returncode, 0, cli.stderr + cli.stdout)
        self.assertIn("知识库审计", cli.stdout)
        self.assertIn("Metadata 回填候选", cli.stdout)
        self.assertNotIn("aliases: [\"Netplan Ubuntu 网卡迁移\"]", first.read_text(encoding="utf-8"))

    def test_metadata_backfill_requires_confirmation_and_preserves_existing_values(self) -> None:
        first, _left, _right = self.create_fixture()
        unique = self.write_checkpoint("Netplan 唯一 metadata", UNIQUE_SESSION)

        rejected = self.run_synthesize(
            "--audit", "--apply-metadata", "--metadata-sessions", UNIQUE_SESSION,
        )
        self.assertEqual(rejected.returncode, 2, rejected.stderr + rejected.stdout)
        self.assertIn("--confirm-metadata", rejected.stderr)

        applied = self.run_synthesize(
            "--audit", "--apply-metadata", "--metadata-sessions", UNIQUE_SESSION, "--confirm-metadata",
        )
        self.assertEqual(applied.returncode, 0, applied.stderr + applied.stdout)
        text = unique.read_text(encoding="utf-8")
        self.assertIn('aliases: ["Netplan Ubuntu 网卡迁移"]', text)
        self.assertIn("Netplan", text)

        records = scan_vault(self.vault)
        with self.assertRaisesRegex(ValueError, "没有可安全回填"):
            apply_metadata_candidates(records, [UNIQUE_SESSION])
        with self.assertRaisesRegex(ValueError, "多个 metadata 候选"):
            apply_metadata_candidates(records, [SESSION])
        self.assertIn("aliases: []", first.read_text(encoding="utf-8"))

    def test_link_candidates_are_read_only_until_confirmed(self) -> None:
        _first, left, right = self.create_fixture()
        records = scan_vault(self.vault)
        candidates = link_candidates(records)
        candidate = next(
            item for item in candidates
            if {item["left"]["path"], item["right"]["path"]} == {left, right}
        )
        self.assertNotIn("## 相关资料", left.read_text(encoding="utf-8"))
        self.assertNotIn("## 相关资料", right.read_text(encoding="utf-8"))

        listed = self.run_synthesize("--link-candidates")
        self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
        self.assertIn(candidate["id"], listed.stdout)

        rejected = self.run_synthesize("--link-candidate", candidate["id"])
        self.assertEqual(rejected.returncode, 2, rejected.stderr + rejected.stdout)
        self.assertIn("--confirm-link", rejected.stderr)

        confirmed = self.run_synthesize("--link-candidate", candidate["id"], "--confirm-link")
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr + confirmed.stdout)
        self.assertIn("双向 wikilink 写入完成", confirmed.stdout)
        self.assertIn("[[AI开发参考/Netplan部署|Netplan Ubuntu 部署参考]]", left.read_text(encoding="utf-8"))
        self.assertIn("[[项目总结/Netplan迁移|Netplan 迁移项目总结]]", right.read_text(encoding="utf-8"))

    def test_link_candidates_ignore_shared_path_and_generated_body_words(self) -> None:
        self.write_document(
            "项目总结/路径噪声甲.md",
            "路径噪声甲",
            "# <TITLE>\n\n/Users/deltanacncore/Documents/Codex text skills synthesize\n",
        )
        self.write_document(
            "项目总结/路径噪声乙.md",
            "路径噪声乙",
            "# <TITLE>\n\n/Users/deltanacncore/Documents/Codex text skills synthesize\n",
        )

        candidates = link_candidates(scan_vault(self.vault))

        pair = {"项目总结/路径噪声甲.md", "项目总结/路径噪声乙.md"}
        self.assertFalse(any({item["left"]["rel"].as_posix(), item["right"]["rel"].as_posix()} == pair for item in candidates))

    def test_broken_link_repair_requires_unique_target_and_confirmation(self) -> None:
        _first, _left, right = self.create_fixture()
        right.write_text(
            right.read_text(encoding="utf-8").replace(
                "[[不存在的文档]]",
                "[[旧 Netplan 文档#验证步骤|保留的显示名称]]",
            ),
            encoding="utf-8",
        )
        replacement = self.write_document(
            "项目总结/Netplan正式文档.md",
            "Netplan 正式项目总结",
            '''---
project: "Netplan迁移"
aliases: ["旧 Netplan 文档"]
keywords: ["Netplan"]
---

# <TITLE>
''',
        )
        records = scan_vault(self.vault)
        candidates = broken_link_repair_candidates(records)
        candidate = next(
            item for item in candidates
            if item["source"]["path"] == right and item["replacement"]["path"] == replacement
        )
        before = right.read_text(encoding="utf-8")

        listed = self.run_synthesize("--repair-link-candidates")
        self.assertEqual(listed.returncode, 0, listed.stderr + listed.stdout)
        self.assertIn(candidate["id"], listed.stdout)
        self.assertEqual(before, right.read_text(encoding="utf-8"))

        rejected = self.run_synthesize("--repair-link-candidate", candidate["id"])
        self.assertEqual(rejected.returncode, 2, rejected.stderr + rejected.stdout)
        self.assertIn("--confirm-link-repair", rejected.stderr)
        self.assertEqual(before, right.read_text(encoding="utf-8"))

        confirmed = self.run_synthesize(
            "--repair-link-candidate", candidate["id"], "--confirm-link-repair",
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr + confirmed.stdout)
        self.assertIn("断裂 wikilink 修复完成", confirmed.stdout)
        self.assertIn("[[项目总结/Netplan正式文档#验证步骤|保留的显示名称]]", right.read_text(encoding="utf-8"))

    def test_broken_link_repair_rejects_ambiguous_aliases(self) -> None:
        source = self.write_document(
            "项目总结/待修复链接.md",
            "待修复链接",
            "# <TITLE>\n\n[[旧部署记录]]\n",
        )
        self.write_document(
            "项目总结/部署记录甲.md",
            "部署记录甲",
            '''---
aliases: ["旧部署记录"]
---

# <TITLE>
''',
        )
        self.write_document(
            "项目总结/部署记录乙.md",
            "部署记录乙",
            '''---
aliases: ["旧部署记录"]
---

# <TITLE>
''',
        )

        candidates = broken_link_repair_candidates(scan_vault(self.vault))

        self.assertFalse(any(item["source"]["path"] == source for item in candidates))


if __name__ == "__main__":
    unittest.main()
