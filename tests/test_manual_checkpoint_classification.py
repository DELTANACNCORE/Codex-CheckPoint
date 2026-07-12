#!/usr/bin/env python3
"""Integration coverage for manual checkpoint classification behavior."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".codex" / "hooks" / "checkpoint.py"
RETRIEVE_HOOK = REPO_ROOT / ".codex" / "hooks" / "retrieve.py"
CHECKPOINT_SKILL = REPO_ROOT / ".codex" / "skills" / "checkpoint" / "checkpoint.py"
SYNTHESIZE_SKILL = REPO_ROOT / ".codex" / "skills" / "synthesize" / "synthesize.py"
DOCKER_SESSION = "11111111-1111-1111-1111-111111111111"
KNOWLEDGE_SESSION = "22222222-2222-2222-2222-222222222222"
MISSING_SESSION = "33333333-3333-3333-3333-333333333333"
INTERVIEW_SESSION = "44444444-4444-4444-4444-444444444444"
RECOVERY_SESSION = "55555555-5555-5555-5555-555555555555"


def response(role: str, text: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": text}],
        },
    }


def write_rollout(path: Path, prompt: str, conclusion: str) -> None:
    entries = []
    for round_number in range(5):
        entries.append(response("user", f"{prompt}，第 {round_number + 1} 轮确认。"))
        entries.append(response("assistant", f"正在处理第 {round_number + 1} 轮。"))
    entries.append(response("assistant", conclusion))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")


def append_assistant_response(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(response("assistant", text), ensure_ascii=False) + "\n")


def append_user_response(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(response("user", text), ensure_ascii=False) + "\n")


class ManualCheckpointClassificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / ".obsidian").mkdir()
        self.sessions = self.home / ".codex" / "sessions" / "2026" / "07" / "13"
        self.hooks = self.home / ".codex" / "hooks"
        self.hooks.mkdir(parents=True)
        shutil.copy2(HOOK, self.hooks / "checkpoint.py")
        self.docker_rollout = self.sessions / f"rollout-2026-07-13T08-00-00-{DOCKER_SESSION}.jsonl"
        self.knowledge_rollout = self.sessions / f"rollout-2026-07-13T08-10-00-{KNOWLEDGE_SESSION}.jsonl"
        write_rollout(self.docker_rollout, "请升级 Docker 服务并检查健康状态", "服务初始验证已完成。")
        write_rollout(
            self.knowledge_rollout,
            "请整理 Obsidian 知识库 checkpoint 工作流",
            "知识库断点配置已完成并通过检索验证。",
        )
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_hook(self, rollout: Path, session_id: str, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "--vault-root",
                str(self.vault),
                "--transcript",
                str(rollout),
                "--session-id",
                session_id,
                *extra,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def run_checkpoint_skill(self, session_id: str, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(CHECKPOINT_SKILL),
                "--vault-root",
                str(self.vault),
                "--session-id",
                session_id,
                *extra,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def note_for_session(self, session_id: str) -> Path:
        for path in (self.vault / "Codex工作记录" / "会话断点").rglob("*.md"):
            if f'session_id: "{session_id}"' in path.read_text(encoding="utf-8"):
                return path
        self.fail(f"missing checkpoint for {session_id}")

    def test_manual_checkpoint_classifies_all_saved_sessions(self) -> None:
        docker_result = self.run_hook(self.docker_rollout, DOCKER_SESSION)
        knowledge_result = self.run_hook(self.knowledge_rollout, KNOWLEDGE_SESSION)
        self.assertEqual(docker_result.returncode, 0, docker_result.stderr + docker_result.stdout)
        self.assertEqual(knowledge_result.returncode, 0, knowledge_result.stderr + knowledge_result.stdout)

        note_dir = self.vault / "Codex工作记录" / "会话断点"
        self.assertEqual(len(list(note_dir.glob("*.md"))), 2)
        self.assertEqual(self.note_for_session(DOCKER_SESSION).parent, note_dir)
        self.assertEqual(self.note_for_session(KNOWLEDGE_SESSION).parent, note_dir)

        append_assistant_response(self.docker_rollout, "Docker 服务升级流程已完成并通过健康检查。")
        append_user_response(self.docker_rollout, "[$checkpoint](/Users/example/.codex/skills/checkpoint/SKILL.md)")
        manual_result = self.run_checkpoint_skill(DOCKER_SESSION)
        self.assertEqual(manual_result.returncode, 0, manual_result.stderr + manual_result.stdout)
        self.assertIn("Manual classification complete: scanned=2", manual_result.stdout)

        docker_note = self.note_for_session(DOCKER_SESSION)
        knowledge_note = self.note_for_session(KNOWLEDGE_SESSION)
        self.assertEqual(docker_note.parent.name, "系统与运维")
        self.assertEqual(knowledge_note.parent.name, "知识库与工作流")
        self.assertIn("# Docker 服务升级流程已完成并通过健康检查", docker_note.read_text(encoding="utf-8"))
        self.assertIn('checkpoint_category: "系统与运维"', docker_note.read_text(encoding="utf-8"))
        self.assertEqual(list(note_dir.glob("*.md")), [])

        index_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.vault / "Codex工作记录" / "会话索引").glob("*.md")
        )
        self.assertEqual(index_text.count(f"<!-- session:{DOCKER_SESSION} -->"), 1)
        self.assertIn("Codex工作记录/会话断点/系统与运维/", index_text)

        append_assistant_response(self.docker_rollout, "Docker 服务已经再次启动。")
        keep_title_result = self.run_checkpoint_skill(DOCKER_SESSION, "--keep-title")
        self.assertEqual(keep_title_result.returncode, 0, keep_title_result.stderr + keep_title_result.stdout)
        self.assertIn("# Docker 服务升级流程已完成并通过健康检查", self.note_for_session(DOCKER_SESSION).read_text(encoding="utf-8"))

        retrieve_result = subprocess.run(
            [sys.executable, str(RETRIEVE_HOOK), "--vault-root", str(self.vault)],
            input=json.dumps({
                "hook_event_name": "UserPromptSubmit",
                "session_id": DOCKER_SESSION,
                "prompt": "继续 Docker 服务升级并检查状态",
            }, ensure_ascii=False),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(retrieve_result.returncode, 0, retrieve_result.stderr + retrieve_result.stdout)
        self.assertIn("Docker 服务升级流程已完成并通过健康检查", retrieve_result.stdout)

        synthesize_result = subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE_SKILL),
                "--vault-root",
                str(self.vault),
                "--project",
                "Docker",
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(synthesize_result.returncode, 0, synthesize_result.stderr + synthesize_result.stdout)
        summary_path = self.vault / "项目总结" / "Docker.md"
        self.assertTrue(summary_path.is_file())
        self.assertIn(
            "[[Codex工作记录/会话断点/系统与运维/",
            summary_path.read_text(encoding="utf-8"),
        )

    def test_hook_event_without_matching_rollout_is_skipped(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOK), "--vault-root", str(self.vault)],
            input=json.dumps({
                "hook_event_name": "Stop",
                "session_id": MISSING_SESSION,
                "transcript_path": None,
            }),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("No transcript path available, skipping", result.stdout)
        self.assertFalse((self.vault / "Codex工作记录" / "会话断点").exists())

    def test_checkpoint_command_notice_does_not_become_the_title(self) -> None:
        interview_rollout = self.sessions / f"rollout-2026-07-13T09-00-00-{INTERVIEW_SESSION}.jsonl"
        write_rollout(
            interview_rollout,
            "现在你协助我做面经吧",
            "我会使用 checkpoint 将本次围绕交付实习面试准备的对话写入 Obsidian 断点。",
        )
        append_assistant_response(interview_rollout, "本次对话已写入 [Obsidian 会话断点](/tmp/incorrect-path.md)。")
        result = self.run_checkpoint_skill(INTERVIEW_SESSION)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note = self.note_for_session(INTERVIEW_SESSION)
        self.assertEqual(note.parent.name, "学习与写作")
        self.assertIn("# 面经准备", note.read_text(encoding="utf-8"))
        self.assertNotIn("本次对话已写入.md", str(note))

    def test_recovery_disclosure_and_response_annotation_do_not_pollute_checkpoint(self) -> None:
        rollout = self.sessions / f"rollout-2026-07-13T09-10-00-{RECOVERY_SESSION}.jsonl"
        write_rollout(
            rollout,
            "配置图片搜索 MCP 并验证工具可用性",
            "已发现并复用长期经验：sub2api Docker 更新 长期经验总结。图片搜索 MCP 已配置完成并通过验证。",
        )
        append_user_response(
            rollout,
            """# Response annotations:
<response-annotations>
[{"text":"已发现并复用长期经验：sub2api Docker 更新 长期经验总结"}]
</response-annotations>
## My request for Codex:
继续验证图片搜索工具
""",
        )
        result = self.run_hook(rollout, RECOVERY_SESSION)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note_text = self.note_for_session(RECOVERY_SESSION).read_text(encoding="utf-8")
        self.assertIn("图片搜索 MCP 已配置完成并通过验证", note_text)
        self.assertNotIn("已发现并复用长期经验", note_text)
        self.assertNotIn("Response annotations", note_text)

    def test_internal_handoff_summary_does_not_pollute_checkpoint(self) -> None:
        session_id = "88888888-8888-8888-8888-888888888888"
        rollout = self.sessions / f"rollout-2026-07-13T09-20-00-{session_id}.jsonl"
        write_rollout(
            rollout,
            "修复 Codex 知识库错误归档",
            "错误项目总结已定位，等待补充聚类安全限制。",
        )
        append_assistant_response(
            rollout,
            """**Handoff Summary**

**Current State**

- This is Codex internal compaction context and must not become a checkpoint conclusion.
""",
        )
        result = self.run_hook(rollout, session_id)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note_text = self.note_for_session(session_id).read_text(encoding="utf-8")
        self.assertIn("错误项目总结已定位，等待补充聚类安全限制", note_text)
        self.assertNotIn("Handoff Summary", note_text)
        self.assertNotIn("Codex internal compaction context", note_text)

    def test_checkpoint_does_not_append_an_unrelated_older_conclusion(self) -> None:
        session_id = "99999999-9999-9999-9999-999999999999"
        rollout = self.sessions / f"rollout-2026-07-13T09-30-00-{session_id}.jsonl"
        write_rollout(
            rollout,
            "配置新闻搜索 MCP 并检查额度",
            "新闻搜索 MCP 调用已到达服务端，但账户额度不足。",
        )
        append_assistant_response(
            rollout,
            "错误知识合成曾混入无关 checkpoint，历史项目总结需要清理。",
        )
        append_assistant_response(
            rollout,
            "新闻搜索 MCP 已注册，当前 API Key 的额度不足，需要补充额度后重新验证。",
        )
        result = self.run_hook(rollout, session_id)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note_text = self.note_for_session(session_id).read_text(encoding="utf-8")
        self.assertIn("新闻搜索 MCP 已注册", note_text)
        self.assertNotIn("错误知识合成曾混入无关 checkpoint", note_text)

    def test_invalid_archive_document_does_not_preserve_archived_state(self) -> None:
        session_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        rollout = self.sessions / f"rollout-2026-07-13T09-40-00-{session_id}.jsonl"
        write_rollout(rollout, "验证失效归档恢复", "当前会话已经完成基础验证。")
        initial = self.run_hook(rollout, session_id)
        self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)
        note = self.note_for_session(session_id)
        note.write_text(
            note.read_text(encoding="utf-8").replace(
                "---\n\n#",
                'knowledge_archived: true\narchived_prompt_count: 5\narchive_document: "项目总结/不存在.md"\n---\n\n#',
                1,
            ),
            encoding="utf-8",
        )

        refreshed = self.run_hook(rollout, session_id)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr + refreshed.stdout)
        note_text = self.note_for_session(session_id).read_text(encoding="utf-8")
        self.assertIn('status: "completed"', note_text)
        self.assertNotIn("knowledge_archived: true", note_text)

    def test_mismatched_hook_session_and_invalid_vault_are_skipped(self) -> None:
        mismatched_result = subprocess.run(
            [sys.executable, str(HOOK), "--vault-root", str(self.vault)],
            input=json.dumps({
                "hook_event_name": "Stop",
                "session_id": MISSING_SESSION,
                "transcript_path": str(self.docker_rollout),
            }),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(mismatched_result.returncode, 0, mismatched_result.stderr + mismatched_result.stdout)
        self.assertIn("Hook session does not match rollout, skipping", mismatched_result.stdout)
        self.assertFalse((self.vault / "Codex工作记录" / "会话断点").exists())

        invalid_vault = self.root / "not-a-vault"
        invalid_vault.mkdir()
        invalid_result = subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "--vault-root",
                str(invalid_vault),
                "--transcript",
                str(self.docker_rollout),
                "--session-id",
                DOCKER_SESSION,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(invalid_result.returncode, 0, invalid_result.stderr + invalid_result.stdout)
        self.assertIn("Not an Obsidian vault", invalid_result.stdout)
        self.assertFalse((invalid_vault / "Codex工作记录").exists())


if __name__ == "__main__":
    unittest.main()
