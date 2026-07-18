#!/usr/bin/env python3
"""Coverage for user-confirmed merge proposals in the synthesize skill."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHESIZE = REPO_ROOT / ".codex" / "skills" / "synthesize" / "synthesize.py"
FIRST_SESSION = "11111111-2222-3333-4444-555555555555"
SECOND_SESSION = "66666666-7777-8888-9999-aaaaaaaaaaaa"
UNRELATED_SESSION = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
ARCHIVED_SESSION = "12121212-3434-5656-7878-909090909090"
LOW_SIGNAL_SESSION = "abababab-cdcd-efef-1212-343434343434"


class SynthesizeMergeCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        self.note_dir = self.vault / "Codex工作记录" / "会话断点" / "未分类对话"
        self.note_dir.mkdir(parents=True)
        (self.vault / ".obsidian").mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_note(
        self,
        name: str,
        title: str,
        session_id: str,
        *,
        projects: str = '[]',
        aliases: str = '[]',
        keywords: str = '[]',
        status: str = "completed",
    ) -> Path:
        path = self.note_dir / f"{name}.md"
        path.write_text(
            f'''---
date: "2026-07-18"
session_id: "{session_id}"
status: "{status}"
projects: {projects}
tags: ["codex/方案", "系统与运维"]
keywords: {keywords}
aliases: {aliases}
---

# {title}

**已记录用户消息**: 6

## 可直接续接的结论

- 已完成 Netplan 与 Ubuntu 网卡迁移的配置校验。

## 会话目标演进

- 校验 Netplan 配置和 Ubuntu 网卡状态。
- 记录迁移后的连接测试与回滚路径。

## 已验证结果

- 新网卡配置已生效，地址和默认路由均正常。

## 实际产出

- 已写入 Netplan 配置、验证命令和回滚说明。
''',
            encoding="utf-8",
        )
        return path

    def create_fixture(self) -> tuple[Path, Path]:
        first = self.write_note(
            "Netplan 初始迁移",
            "Ubuntu Netplan 初始迁移",
            FIRST_SESSION,
            projects='["Netplan迁移"]',
            aliases='["Netplan", "Ubuntu 网卡"]',
            keywords='["Netplan", "Ubuntu"]',
        )
        second = self.write_note(
            "Netplan 验证",
            "Ubuntu Netplan 验证",
            SECOND_SESSION,
            projects='["Netplan迁移"]',
            aliases='["Netplan", "Ubuntu 网卡"]',
            keywords='["Netplan", "Ubuntu"]',
        )
        self.write_note(
            "无关 Docker 会话",
            "Docker 容器状态检查",
            UNRELATED_SESSION,
            aliases='["Docker", "容器"]',
            keywords='["Docker", "容器"]',
        )
        self.write_note(
            "已归档 Netplan",
            "Ubuntu Netplan 旧记录",
            ARCHIVED_SESSION,
            projects='["Netplan迁移"]',
            aliases='["Netplan", "Ubuntu 网卡"]',
            keywords='["Netplan", "Ubuntu"]',
            status="archived",
        )
        self.write_note(
            "写入回执",
            "本次对话已写入 Obsidian",
            LOW_SIGNAL_SESSION,
            projects='["Netplan迁移"]',
            aliases='["Netplan", "Ubuntu 网卡"]',
            keywords='["Netplan", "Ubuntu"]',
        )
        return first, second

    def run_synthesize(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE),
                "--vault-root",
                str(self.vault),
                *arguments,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def candidate_id(self) -> str:
        result = self.run_synthesize("--merge-candidates")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        matched = re.search(r"候选编号: (merge-[a-f0-9]+)", result.stdout)
        self.assertIsNotNone(matched, result.stdout)
        return matched.group(1)

    def test_candidate_scan_is_read_only_and_excludes_archived_or_low_signal_notes(self) -> None:
        first, second = self.create_fixture()

        result = self.run_synthesize("--merge-candidates")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("生成 1 组高置信候选", result.stdout)
        self.assertIn(FIRST_SESSION, result.stdout)
        self.assertIn(SECOND_SESSION, result.stdout)
        self.assertNotIn(ARCHIVED_SESSION, result.stdout)
        self.assertNotIn(LOW_SIGNAL_SESSION, result.stdout)
        self.assertIn("本次仅生成候选，未修改任何断点、项目总结或索引", result.stdout)
        self.assertFalse((self.vault / "项目总结").exists())
        self.assertNotIn("knowledge_archived: true", first.read_text(encoding="utf-8"))
        self.assertNotIn("knowledge_archived: true", second.read_text(encoding="utf-8"))

    def test_candidate_requires_confirmation_then_archives_exact_source_sessions(self) -> None:
        first, second = self.create_fixture()
        candidate = self.candidate_id()

        unconfirmed = self.run_synthesize("--merge-candidate", candidate, "--merge-project", "Netplan 项目")
        self.assertEqual(unconfirmed.returncode, 2, unconfirmed.stderr + unconfirmed.stdout)
        self.assertIn("--confirm-merge", unconfirmed.stderr)
        self.assertFalse((self.vault / "项目总结" / "Netplan 项目.md").exists())

        confirmed = self.run_synthesize(
            "--merge-candidate",
            candidate,
            "--merge-project",
            "Netplan 项目",
            "--confirm-merge",
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr + confirmed.stdout)
        summary = self.vault / "项目总结" / "Netplan 项目.md"
        self.assertTrue(summary.is_file())
        summary_text = summary.read_text(encoding="utf-8")
        self.assertIn(FIRST_SESSION, summary_text)
        self.assertIn(SECOND_SESSION, summary_text)
        self.assertIn("knowledge_archived: true", first.read_text(encoding="utf-8"))
        self.assertIn("knowledge_archived: true", second.read_text(encoding="utf-8"))

    def test_user_can_directly_specify_sessions_and_parent_paths_are_rejected(self) -> None:
        first, second = self.create_fixture()

        rejected = self.run_synthesize(
            "--merge-sessions",
            FIRST_SESSION,
            SECOND_SESSION,
            "--merge-project",
            "网络项目/网卡迁移",
            "--confirm-merge",
        )
        self.assertEqual(rejected.returncode, 2, rejected.stderr + rejected.stdout)
        self.assertIn("独立项目名", rejected.stderr)
        self.assertFalse((self.vault / "项目总结").exists())

        direct = self.run_synthesize(
            "--merge-sessions",
            FIRST_SESSION,
            SECOND_SESSION,
            "--merge-project",
            "用户指定网卡迁移",
            "--confirm-merge",
        )
        self.assertEqual(direct.returncode, 0, direct.stderr + direct.stdout)
        self.assertTrue((self.vault / "项目总结" / "用户指定网卡迁移.md").is_file())
        self.assertIn("knowledge_archived: true", first.read_text(encoding="utf-8"))
        self.assertIn("knowledge_archived: true", second.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
