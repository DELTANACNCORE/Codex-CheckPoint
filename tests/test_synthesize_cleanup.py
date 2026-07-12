#!/usr/bin/env python3
"""Coverage for title-first checkpoint cleanup in the synthesize skill."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHESIZE = REPO_ROOT / ".codex" / "skills" / "synthesize" / "synthesize.py"
GOOD_SESSION = "11111111-1111-1111-1111-111111111111"
COPY_SESSION = "22222222-2222-2222-2222-222222222222"
FAKE_SESSION = "33333333-3333-3333-3333-333333333333"
RENAME_SESSION = "44444444-4444-4444-4444-444444444444"
REAL_DUPLICATE_A = "55555555-5555-5555-5555-555555555555"
REAL_DUPLICATE_B = "66666666-6666-6666-6666-666666666666"
SAME_SESSION = "77777777-7777-7777-7777-777777777777"


class SynthesizeCleanupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        self.note_dir = self.vault / "Codex工作记录" / "会话断点"
        self.index_dir = self.vault / "Codex工作记录" / "会话索引"
        self.sessions = self.home / ".codex" / "sessions"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_rollout(self, session_id: str) -> None:
        path = self.sessions / "2026" / "07" / "13" / f"rollout-2026-07-13T08-00-00-{session_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    def write_note(self, name: str, title: str, session_id: str, conclusion: str, goals: str, output: str = "") -> Path:
        path = self.note_dir / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""---
date: "2026-07-13"
session_id: "{session_id}"
status: "completed"
projects: []
tags: []
keywords: []
aliases: []
---

# {title}

**已记录用户消息**: 5

## 可直接续接的结论

{conclusion}

## 会话目标演进

{goals}

## 实际产出

{output}
""",
            encoding="utf-8",
        )
        return path

    def write_index(self, rows: list[tuple[str, str, str]]) -> Path:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        path = self.index_dir / "2026-07-13.md"
        lines = [
            "---\n",
            "date: \"2026-07-13\"\n",
            "---\n\n",
            "# 会话记录 - 2026-07-13\n\n",
            "| 时间 | 状态 | 话题 | 产出 |\n",
            "|---|---|---|---|\n",
        ]
        for session_id, target, label in rows:
            lines.append(
                f"| 08:00 | ✅ | [[{target}\\|{label}]] | — "
                f"<!-- session:{session_id} --> <!-- session-date:2026-07-13 --> |\n"
            )
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def run_cleanup(self, apply: bool = False) -> subprocess.CompletedProcess:
        command = [
            sys.executable,
            str(SYNTHESIZE),
            "--vault-root",
            str(self.vault),
            "--sessions-root",
            str(self.sessions),
            "--cleanup-checkpoints",
        ]
        if apply:
            command.append("--apply-cleanup")
        return subprocess.run(command, env=self.env, text=True, capture_output=True, check=False)

    def run_cluster(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE),
                "--vault-root",
                str(self.vault),
                "--sessions-root",
                str(self.sessions),
                "--cluster",
                *extra,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def create_cleanup_fixture(self) -> dict[str, Path]:
        shared_conclusion = "Docker 服务已部署并通过健康检查，配置和端口状态均已验证。"
        shared_goals = "- 部署 Docker 服务并检查健康状态"
        good = self.write_note("Docker 服务部署", "Docker 服务部署", GOOD_SESSION, shared_conclusion, shared_goals)
        copy = self.write_note("Docker 服务部署 副本", "Docker 服务部署 副本", COPY_SESSION, shared_conclusion, shared_goals)
        fake = self.write_note(
            "本次对话已写入 Obsidian",
            "本次对话已写入 Obsidian",
            FAKE_SESSION,
            "这是一条写入回执，不代表独立会话。",
            "- 本次对话已写入 Obsidian",
        )
        rename = self.write_note(
            "请只回复一句",
            "请只回复一句",
            RENAME_SESSION,
            "Docker 健康检查已经配置完成，容器状态正常。",
            "- 配置 Docker 服务健康检查",
        )
        real_a = self.write_note("真实重复会话 A", "真实重复会话", REAL_DUPLICATE_A, shared_conclusion, shared_goals)
        real_b = self.write_note("真实重复会话 B", "真实重复会话", REAL_DUPLICATE_B, shared_conclusion, shared_goals)
        for session_id in (GOOD_SESSION, RENAME_SESSION, REAL_DUPLICATE_A, REAL_DUPLICATE_B):
            self.write_rollout(session_id)
        self.write_index([
            (COPY_SESSION, "Codex工作记录/会话断点/Docker 服务部署 副本", "Docker 服务部署 副本"),
            (FAKE_SESSION, "Codex工作记录/会话断点/本次对话已写入 Obsidian", "本次对话已写入 Obsidian"),
            (RENAME_SESSION, "Codex工作记录/会话断点/请只回复一句", "请只回复一句"),
            (REAL_DUPLICATE_A, "Codex工作记录/会话断点/真实重复会话 A", "真实重复会话"),
            (REAL_DUPLICATE_B, "Codex工作记录/会话断点/真实重复会话 B", "真实重复会话"),
        ])
        project_summary = self.vault / "项目总结" / "cleanup.md"
        project_summary.parent.mkdir(parents=True, exist_ok=True)
        project_summary.write_text(
            "[[Codex工作记录/会话断点/请只回复一句|请只回复一句]]\n",
            encoding="utf-8",
        )
        return {"good": good, "copy": copy, "fake": fake, "rename": rename, "real_a": real_a, "real_b": real_b}

    def test_dry_run_only_reports_candidates(self) -> None:
        paths = self.create_cleanup_fixture()
        result = self.run_cleanup()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("删除候选：2；重命名候选：1；人工复核：1", result.stdout)
        self.assertIn("本次仅生成候选，未修改任何断点或索引", result.stdout)
        self.assertTrue(paths["copy"].is_file())
        self.assertTrue(paths["fake"].is_file())
        self.assertTrue(paths["rename"].is_file())

    def test_apply_removes_only_safe_candidates_and_repairs_index(self) -> None:
        paths = self.create_cleanup_fixture()
        index_path = self.index_dir / "2026-07-13.md"
        with index_path.open("a", encoding="utf-8") as handle:
            handle.write(
                "| 08:01 | ✅ | [[Codex工作记录/会话断点/保留的会话|保留的会话]] | "
                "[[Codex工作记录/会话断点/Docker 服务部署 副本|引用重复副本]] | "
                "<!-- session:88888888-8888-8888-8888-888888888888 -->\n"
            )
        result = self.run_cleanup(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("清理完成：删除 2 条断点，重命名 1 条断点", result.stdout)
        self.assertFalse(paths["copy"].exists())
        self.assertFalse(paths["fake"].exists())
        self.assertFalse(paths["rename"].exists())
        renamed = self.note_dir / "配置 Docker 服务健康检查.md"
        self.assertTrue(renamed.is_file())
        renamed_text = renamed.read_text(encoding="utf-8")
        self.assertIn("# 配置 Docker 服务健康检查", renamed_text)
        self.assertIn('aliases: ["请只回复一句"]', renamed_text)
        self.assertTrue(paths["real_a"].is_file())
        self.assertTrue(paths["real_b"].is_file())

        index_text = (self.index_dir / "2026-07-13.md").read_text(encoding="utf-8")
        self.assertNotIn(COPY_SESSION, index_text)
        self.assertNotIn(FAKE_SESSION, index_text)
        self.assertIn(RENAME_SESSION, index_text)
        self.assertIn("Codex工作记录/会话断点/配置 Docker 服务健康检查", index_text)
        self.assertIn(
            "[[Codex工作记录/会话断点/配置 Docker 服务健康检查\\|配置 Docker 服务健康检查]]",
            index_text,
        )
        self.assertNotIn("请只回复一句]]", index_text)
        self.assertIn(REAL_DUPLICATE_A, index_text)
        self.assertIn(REAL_DUPLICATE_B, index_text)
        self.assertIn("保留的会话", index_text)
        project_text = (self.vault / "项目总结" / "cleanup.md").read_text(encoding="utf-8")
        self.assertIn("|配置 Docker 服务健康检查]]", project_text)
        self.assertNotIn("|请只回复一句]]", project_text)

    def test_same_session_copy_keeps_its_index_row(self) -> None:
        original = self.write_note(
            "同一会话",
            "同一会话",
            SAME_SESSION,
            "同一份会话内容已经完成，并可用于继续恢复。",
            "- 整理同一会话断点",
        )
        duplicate = self.write_note(
            "同一会话 副本",
            "同一会话 副本",
            SAME_SESSION,
            "同一份会话内容已经完成，并可用于继续恢复。",
            "- 整理同一会话断点",
        )
        self.write_rollout(SAME_SESSION)
        self.write_index([
            (SAME_SESSION, "Codex工作记录/会话断点/同一会话 副本", "同一会话 副本"),
        ])

        result = self.run_cleanup(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        remaining = [path for path in (original, duplicate) if path.exists()]
        self.assertEqual(len(remaining), 1)
        index_text = (self.index_dir / "2026-07-13.md").read_text(encoding="utf-8")
        self.assertIn(SAME_SESSION, index_text)
        self.assertIn(remaining[0].stem, index_text)

    def test_cluster_requires_confirmation_and_target_project(self) -> None:
        note = self.write_note(
            "Docker 服务部署",
            "Docker 服务部署",
            GOOD_SESSION,
            "Docker 服务已部署并通过健康检查。",
            "- 部署 Docker 服务并检查健康状态",
        )
        note.write_text(
            note.read_text(encoding="utf-8").replace("tags: []", 'tags: ["docker", "health"]'),
            encoding="utf-8",
        )

        unconfirmed = self.run_cluster()
        self.assertEqual(unconfirmed.returncode, 2, unconfirmed.stderr + unconfirmed.stdout)
        self.assertIn("--confirm-cluster", unconfirmed.stderr)
        self.assertFalse((self.vault / "项目总结" / "知识合成.md").exists())

        unnamed = self.run_cluster("--confirm-cluster")
        self.assertEqual(unnamed.returncode, 2, unnamed.stderr + unnamed.stdout)
        self.assertIn("--cluster-project", unnamed.stderr)
        self.assertFalse((self.vault / "项目总结" / "知识合成.md").exists())

        confirmed = self.run_cluster("--confirm-cluster", "--cluster-project", "Docker 服务")
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr + confirmed.stdout)
        self.assertTrue((self.vault / "项目总结" / "Docker 服务.md").is_file())
        self.assertFalse((self.vault / "项目总结" / "知识合成.md").exists())


if __name__ == "__main__":
    unittest.main()
