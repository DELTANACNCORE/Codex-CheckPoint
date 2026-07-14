#!/usr/bin/env python3
"""Coverage for Stop-hook background maintenance in Codex CheckPoint."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".codex" / "hooks" / "checkpoint.py"
SESSION_ID = "12121212-3434-5656-7878-909090909090"
PROJECT = "后台维护验证"


def message(role: str, text: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
        },
    }


class BackgroundMaintenanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.hooks = self.home / ".codex" / "hooks"
        self.hooks.mkdir(parents=True)
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.sessions = self.home / ".codex" / "sessions" / "2026" / "07" / "14"
        self.rollout = self.sessions / f"rollout-2026-07-14T10-00-00-{SESSION_ID}.jsonl"
        shutil.copy2(REPO_ROOT / ".codex" / "redaction.py", self.home / ".codex" / "redaction.py")
        shutil.copy2(REPO_ROOT / ".codex" / "metadata.py", self.home / ".codex" / "metadata.py")
        shutil.copy2(HOOK, self.hooks / "checkpoint.py")
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }
        self.summary = self.vault / "项目总结" / f"{PROJECT}.md"
        self.summary.parent.mkdir(parents=True)
        self.summary.write_text(
            f'''---
project: "{PROJECT}"
session_ids: ["{SESSION_ID}"]
tags: []
keywords: []
aliases: []
---

# {PROJECT} 项目总结

## 项目定位

- 初始项目摘要。
''',
            encoding="utf-8",
        )
        self._write_rollout()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_rollout(self) -> None:
        entries = []
        for number in range(5):
            entries.append(message("user", f"维护 {PROJECT} 的第 {number + 1} 项验证。"))
            entries.append(message("assistant", f"第 {number + 1} 项验证已完成。"))
        entries.append(
            {
                "type": "custom_tool_call",
                "payload": {
                    "name": "apply_patch",
                    "input": f"*** Begin Patch\n*** Update File: {self.summary}\n*** End Patch",
                },
            }
        )
        self.rollout.parent.mkdir(parents=True)
        self.rollout.write_text(
            "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
            encoding="utf-8",
        )

    def _run(self, manual: bool = False) -> subprocess.CompletedProcess:
        if manual:
            command = [
                sys.executable,
                str(HOOK),
                "--vault-root",
                str(self.vault),
                "--transcript",
                str(self.rollout),
                "--session-id",
                SESSION_ID,
                "--manual-checkpoint",
            ]
            return subprocess.run(command, env=self.env, text=True, capture_output=True, check=False)
        return subprocess.run(
            [sys.executable, str(HOOK), "--vault-root", str(self.vault)],
            input=json.dumps(
                {
                    "hook_event_name": "Stop",
                    "session_id": SESSION_ID,
                    "transcript_path": str(self.rollout),
                },
                ensure_ascii=False,
            ),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _note_for_session(self) -> Path:
        for path in (self.vault / "Codex工作记录" / "会话断点").rglob("*.md"):
            if f'session_id: "{SESSION_ID}"' in path.read_text(encoding="utf-8"):
                return path
        self.fail("checkpoint note was not written")

    def _wait_for_background_stage(self, stage: str) -> dict:
        log_path = self.home / ".codex" / "logs" / "checkpoint-hook-debug.jsonl"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if log_path.is_file():
                entries = [
                    json.loads(line)
                    for line in log_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                for entry in reversed(entries):
                    if entry.get("stage") == stage:
                        return entry
            time.sleep(0.05)
        self.fail(f"background stage was not recorded: {stage}")

    def test_stop_writes_checkpoint_and_index_before_background_maintenance(self) -> None:
        result = self._run()

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Session checkpoint written:", result.stdout)
        self.assertIn("Background maintenance scheduled", result.stdout)
        self.assertIn("Daily index updated", result.stdout)
        self.assertNotIn("Project knowledge updated:", result.stdout)

        note = self._note_for_session()
        daily_indexes = list((self.vault / "Codex工作记录" / "会话索引").glob("*.md"))
        self.assertTrue(daily_indexes)
        self.assertTrue(any(f"<!-- session:{SESSION_ID} -->" in path.read_text(encoding="utf-8") for path in daily_indexes))

        scheduled = self._wait_for_background_stage("background_maintenance_scheduled")
        completed = self._wait_for_background_stage("background_maintenance_completed")
        self.assertEqual(Path(scheduled["note_path"]).resolve(), note.resolve())
        self.assertEqual(Path(completed["note_path"]).resolve(), note.resolve())
        self.assertTrue((self.vault / "知识库首页.md").is_file())
        self.assertIn(note.stem, self.summary.read_text(encoding="utf-8"))
        self.assertEqual(list((self.vault / "AI开发参考").glob("*.md")), [])
        self.assertEqual(
            list((self.home / ".codex" / "logs").glob("checkpoint-maintenance-*.json")),
            [],
        )

    def test_manual_checkpoint_keeps_derived_maintenance_synchronous(self) -> None:
        result = self._run(manual=True)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Project knowledge updated:", result.stdout)
        self.assertNotIn("Background maintenance scheduled", result.stdout)
        self.assertTrue((self.vault / "知识库首页.md").is_file())
        self.assertIn(self._note_for_session().stem, self.summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
