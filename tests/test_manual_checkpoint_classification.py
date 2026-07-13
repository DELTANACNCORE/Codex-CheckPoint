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
TITLE_SESSION = "66666666-6666-6666-6666-666666666666"
MANUAL_TITLE_SESSION = "77777777-7777-7777-7777-777777777777"
RECHECK_SESSION = "12121212-1212-1212-1212-121212121212"
PENDING_SESSION = "13131313-1313-1313-1313-131313131313"
COLLISION_ONE_SESSION = "14141414-1414-1414-1414-141414141414"
COLLISION_TWO_SESSION = "15151515-1515-1515-1515-151515151515"
LEGACY_SESSION = "16161616-1616-1616-1616-161616161616"


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


def append_project_summary_write(rollout: Path, summary_path: Path) -> None:
    entry = {
        "type": "custom_tool_call",
        "payload": {
            "name": "apply_patch",
            "input": f"*** Begin Patch\n*** Update File: {summary_path}\n*** End Patch",
        },
    }
    with rollout.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


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
        write_rollout(self.docker_rollout, "请升级 Docker 服务并检查健康状态", "Docker 服务初始验证已完成。")
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

    def write_project_summary(self, project: str, session_id: str, merged: bool = False) -> Path:
        path = self.vault / "项目总结" / f"{project}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        merged_line = f'merged_projects: ["{project}"]\n' if merged else ""
        path.write_text(
            f"""---
project: {project}
session_ids: ["{session_id}"]
{merged_line}---

# {project} 项目总结
""",
            encoding="utf-8",
        )
        return path

    def set_thread_title(self, session_id: str, title: str) -> None:
        session_index = self.home / ".codex" / "session_index.jsonl"
        session_index.parent.mkdir(parents=True, exist_ok=True)
        with session_index.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "id": session_id,
                "thread_name": title,
            }, ensure_ascii=False) + "\n")

    def test_manual_checkpoint_classifies_all_saved_sessions(self) -> None:
        docker_result = self.run_hook(self.docker_rollout, DOCKER_SESSION)
        knowledge_result = self.run_hook(self.knowledge_rollout, KNOWLEDGE_SESSION)
        self.assertEqual(docker_result.returncode, 0, docker_result.stderr + docker_result.stdout)
        self.assertEqual(knowledge_result.returncode, 0, knowledge_result.stderr + knowledge_result.stdout)

        note_dir = self.vault / "Codex工作记录" / "会话断点"
        unclassified_dir = note_dir / "未分类对话"
        self.assertEqual(list(note_dir.glob("*.md")), [])
        self.assertEqual(len(list(unclassified_dir.glob("*.md"))), 2)
        self.assertEqual(self.note_for_session(DOCKER_SESSION).parent, unclassified_dir)
        self.assertEqual(self.note_for_session(KNOWLEDGE_SESSION).parent, unclassified_dir)

        append_assistant_response(self.docker_rollout, "Docker 服务升级流程已完成并通过健康检查。")
        append_user_response(self.docker_rollout, "[$checkpoint](/Users/example/.codex/skills/checkpoint/SKILL.md)")
        manual_result = self.run_checkpoint_skill(DOCKER_SESSION)
        self.assertEqual(manual_result.returncode, 0, manual_result.stderr + manual_result.stdout)
        self.assertIn("Manual classification complete: scanned=2", manual_result.stdout)

        docker_note = self.note_for_session(DOCKER_SESSION)
        knowledge_note = self.note_for_session(KNOWLEDGE_SESSION)
        self.assertEqual(docker_note.parent.name, "系统与运维")
        self.assertEqual(knowledge_note.parent.name, "知识库与工作流")
        written_lines = [
            line for line in manual_result.stdout.splitlines()
            if line.startswith("[obsidian-hook] Session checkpoint written: ")
        ]
        self.assertEqual(
            written_lines,
            [f"[obsidian-hook] Session checkpoint written: {docker_note.resolve()}"],
        )
        resolved_vault = self.vault.resolve()
        relative_note = docker_note.resolve().relative_to(resolved_vault).as_posix()
        relative_directory = docker_note.parent.resolve().relative_to(resolved_vault).as_posix() + "/"
        self.assertIn(
            "[obsidian-hook] Session checkpoint location: "
            f"vault-relative={relative_note}; folder={relative_directory}",
            manual_result.stdout,
        )
        self.assertIn("# Docker 服务初始验证已完成", docker_note.read_text(encoding="utf-8"))
        self.assertIn('checkpoint_category: "系统与运维"', docker_note.read_text(encoding="utf-8"))
        self.assertEqual(list(note_dir.glob("*.md")), [])
        self.assertEqual(list(unclassified_dir.glob("*.md")), [])

        index_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.vault / "Codex工作记录" / "会话索引").glob("*.md")
        )
        self.assertEqual(index_text.count(f"<!-- session:{DOCKER_SESSION} -->"), 1)
        self.assertIn("Codex工作记录/会话断点/系统与运维/", index_text)

        append_assistant_response(self.docker_rollout, "Docker 服务已经再次启动。")
        keep_title_result = self.run_checkpoint_skill(DOCKER_SESSION, "--keep-title")
        self.assertEqual(keep_title_result.returncode, 0, keep_title_result.stderr + keep_title_result.stdout)
        self.assertIn("# Docker 服务初始验证已完成", self.note_for_session(DOCKER_SESSION).read_text(encoding="utf-8"))

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

    def test_manual_checkpoint_only_reclassifies_unclassified_or_current_session(self) -> None:
        recheck_rollout = self.sessions / f"rollout-2026-07-13T08-20-00-{RECHECK_SESSION}.jsonl"
        pending_rollout = self.sessions / f"rollout-2026-07-13T08-30-00-{PENDING_SESSION}.jsonl"
        write_rollout(
            recheck_rollout,
            "请升级 Docker 服务并检查健康状态",
            "Docker 服务初始验证已完成。",
        )
        write_rollout(
            pending_rollout,
            "请整理 Obsidian 知识库 checkpoint 工作流",
            "知识库断点配置已完成并通过检索验证。",
        )

        initial = self.run_hook(recheck_rollout, RECHECK_SESSION)
        self.assertEqual(initial.returncode, 0, initial.stderr + initial.stdout)
        first_manual = self.run_checkpoint_skill(RECHECK_SESSION)
        self.assertEqual(first_manual.returncode, 0, first_manual.stderr + first_manual.stdout)
        categorized_note = self.note_for_session(RECHECK_SESSION)
        self.assertEqual(categorized_note.parent.name, "系统与运维")
        categorized_note.write_text(
            categorized_note.read_text(encoding="utf-8").replace(
                'checkpoint_category: "系统与运维"',
                'checkpoint_category: "保留分类"',
                1,
            ),
            encoding="utf-8",
        )

        pending = self.run_hook(pending_rollout, PENDING_SESSION)
        self.assertEqual(pending.returncode, 0, pending.stderr + pending.stdout)
        self.assertEqual(self.note_for_session(PENDING_SESSION).parent.name, "未分类对话")
        pending_manual = self.run_checkpoint_skill(PENDING_SESSION)
        self.assertEqual(pending_manual.returncode, 0, pending_manual.stderr + pending_manual.stdout)
        self.assertIn("Manual classification complete: scanned=1", pending_manual.stdout)
        self.assertEqual(self.note_for_session(RECHECK_SESSION), categorized_note)
        self.assertIn('checkpoint_category: "保留分类"', categorized_note.read_text(encoding="utf-8"))

        recheck_manual = self.run_checkpoint_skill(RECHECK_SESSION, "--keep-title")
        self.assertEqual(recheck_manual.returncode, 0, recheck_manual.stderr + recheck_manual.stdout)
        self.assertIn("Manual classification complete: scanned=1", recheck_manual.stdout)
        self.assertIn(
            'checkpoint_category: "系统与运维"',
            self.note_for_session(RECHECK_SESSION).read_text(encoding="utf-8"),
        )

    def test_automatic_name_collision_stays_in_unclassified_directory(self) -> None:
        first_rollout = self.sessions / f"rollout-2026-07-13T08-40-00-{COLLISION_ONE_SESSION}.jsonl"
        second_rollout = self.sessions / f"rollout-2026-07-13T08-50-00-{COLLISION_TWO_SESSION}.jsonl"
        for rollout in (first_rollout, second_rollout):
            write_rollout(
                rollout,
                "请检查 Docker 服务的健康状态",
                "Docker 服务健康检查已完成。",
            )

        first = self.run_hook(first_rollout, COLLISION_ONE_SESSION)
        second = self.run_hook(second_rollout, COLLISION_TWO_SESSION)
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        first_note = self.note_for_session(COLLISION_ONE_SESSION)
        second_note = self.note_for_session(COLLISION_TWO_SESSION)
        note_dir = self.vault / "Codex工作记录" / "会话断点"
        self.assertEqual(first_note.parent.name, "未分类对话")
        self.assertEqual(second_note.parent.name, "未分类对话")
        self.assertNotEqual(first_note.name, second_note.name)
        self.assertEqual(list(note_dir.glob("*.md")), [])

    def test_manual_checkpoint_migrates_legacy_top_level_note_once(self) -> None:
        legacy_rollout = self.sessions / f"rollout-2026-07-13T08-55-00-{LEGACY_SESSION}.jsonl"
        pending_rollout = self.sessions / f"rollout-2026-07-13T08-56-00-{PENDING_SESSION}.jsonl"
        write_rollout(
            legacy_rollout,
            "请检查 Docker 服务的健康状态",
            "Docker 服务健康检查已完成。",
        )
        write_rollout(
            pending_rollout,
            "请整理 Obsidian 知识库 checkpoint 工作流",
            "知识库断点配置已完成并通过检索验证。",
        )
        note_dir = self.vault / "Codex工作记录" / "会话断点"
        note_dir.mkdir(parents=True)
        legacy_note = note_dir / "旧版 Docker 健康检查.md"
        legacy_note.write_text(
            f'''---
session_id: "{LEGACY_SESSION}"
status: "completed"
projects: []
tags: []
keywords: []
aliases: []
---

# 旧版 Docker 健康检查
''',
            encoding="utf-8",
        )

        pending = self.run_hook(pending_rollout, PENDING_SESSION)
        self.assertEqual(pending.returncode, 0, pending.stderr + pending.stdout)
        result = self.run_checkpoint_skill(PENDING_SESSION)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Manual classification complete: scanned=2", result.stdout)
        self.assertFalse(legacy_note.exists())
        self.assertEqual(self.note_for_session(LEGACY_SESSION).parent.name, "系统与运维")
        self.assertEqual(list(note_dir.glob("*.md")), [])

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

    def test_manual_checkpoint_repairs_mechanical_title_from_full_context(self) -> None:
        rollout = self.sessions / f"rollout-2026-07-13T09-05-00-{TITLE_SESSION}.jsonl"
        write_rollout(
            rollout,
            "请按照安装文档配置多个搜索 MCP",
            "网页搜索 MCP 已配置完成，并已验证认证和基础检索。",
        )
        append_assistant_response(rollout, "图片搜索 MCP 已配置完成，独立密钥与工具发现均已验证。")
        append_assistant_response(rollout, "新闻搜索 MCP 已恢复可用，旧会话的额度错误来自此前认证状态。")
        append_assistant_response(
            rollout,
            "已写入恢复断点：[旧标题.md](/tmp/old.md)。全量分类完成，扫描 9 条断点并归类了 1 条记录。",
        )
        self.set_thread_title(TITLE_SESSION, "安装并配置 Agent")

        note_dir = self.vault / "Codex工作记录" / "会话断点" / "系统与运维"
        old_note = note_dir / "之前失败时，服务端返回的是 user quota is not enough.md"
        note_dir.mkdir(parents=True)
        old_target = "Codex工作记录/会话断点/系统与运维/之前失败时，服务端返回的是 user quota is not enough"
        old_note.write_text(
            f"""---
session_id: "{TITLE_SESSION}"
status: "interrupted"
projects: []
tags: []
keywords: []
aliases: []
---

# 之前失败时，服务端返回的是 user quota is not enough

## 可直接续接的结论

旧回执
""",
            encoding="utf-8",
        )
        index_path = self.vault / "Codex工作记录" / "会话索引" / "2026-07-13.md"
        index_path.parent.mkdir(parents=True)
        index_path.write_text(
            f"| 09:05 | ⚠️ | [[{old_target}\\|旧标题]] | — <!-- session:{TITLE_SESSION} --> |\n",
            encoding="utf-8",
        )
        project_path = self.vault / "项目总结" / "MCP 安装.md"
        project_path.parent.mkdir(parents=True)
        project_path.write_text(f"[[{old_target}\\|旧标题]]\n", encoding="utf-8")

        result = self.run_checkpoint_skill(TITLE_SESSION)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note = self.note_for_session(TITLE_SESSION)
        note_text = note.read_text(encoding="utf-8")
        self.assertEqual(note.stem, "安装并配置 Agent")
        self.assertIn("# 安装并配置 Agent", note_text)
        self.assertIn('title_baseline: "安装并配置 Agent"', note_text)
        self.assertIn('title_source: "thread"', note_text)
        self.assertIn("网页搜索 MCP 已配置完成", note_text)
        self.assertIn("新闻搜索 MCP 已恢复可用", note_text)
        self.assertNotIn("全量分类完成", note_text)
        self.assertIn("**初始目标**", note_text)
        self.assertIn("**最新目标**", note_text)
        self.assertFalse(old_note.exists())
        self.assertNotIn(old_target, index_path.read_text(encoding="utf-8"))
        self.assertNotIn(old_target, project_path.read_text(encoding="utf-8"))

    def test_manual_checkpoint_preserves_a_title_changed_in_obsidian(self) -> None:
        rollout = self.sessions / f"rollout-2026-07-13T09-06-00-{MANUAL_TITLE_SESSION}.jsonl"
        write_rollout(
            rollout,
            "配置搜索 MCP 并验证联网能力",
            "搜索 MCP 的初始配置已经完成。",
        )
        append_assistant_response(rollout, "最新验证表明搜索 MCP 已经可用。")
        self.set_thread_title(MANUAL_TITLE_SESSION, "配置搜索 MCP")

        note_dir = self.vault / "Codex工作记录" / "会话断点" / "工具与配置"
        note_dir.mkdir(parents=True)
        user_named_note = note_dir / "用户确认的 MCP 配置方案.md"
        user_named_note.write_text(
            f"""---
session_id: "{MANUAL_TITLE_SESSION}"
status: "completed"
projects: []
tags: []
keywords: []
aliases: []
title_baseline: "搜索 MCP 的初始配置已经完成"
title_source: "assistant"
---

# 用户确认的 MCP 配置方案
""",
            encoding="utf-8",
        )

        result = self.run_checkpoint_skill(MANUAL_TITLE_SESSION)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note = self.note_for_session(MANUAL_TITLE_SESSION)
        self.assertEqual(note, user_named_note)
        note_text = note.read_text(encoding="utf-8")
        self.assertIn("# 用户确认的 MCP 配置方案", note_text)
        self.assertIn('title_baseline: "搜索 MCP 的初始配置已经完成"', note_text)

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

    def test_historical_project_summary_writes_do_not_create_a_merge(self) -> None:
        session_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        rollout = self.sessions / f"rollout-2026-07-13T09-50-00-{session_id}.jsonl"
        write_rollout(rollout, "修复项目总结归属", "当前项目总结归属已经完成验证。")
        trusted = self.write_project_summary("可信项目", session_id)
        stale_merge = self.write_project_summary("历史合并项目", session_id, merged=True)
        deleted = self.vault / "项目总结" / "已删除项目.md"
        append_project_summary_write(rollout, trusted)
        append_project_summary_write(rollout, stale_merge)
        append_project_summary_write(rollout, deleted)

        result = self.run_hook(rollout, session_id)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        note_text = self.note_for_session(session_id).read_text(encoding="utf-8")
        self.assertIn('projects: ["可信项目"]', note_text)
        self.assertFalse((self.vault / "项目总结" / "可信项目、历史合并项目、已删除项目.md").exists())

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
