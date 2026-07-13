#!/usr/bin/env python3
"""Integration coverage for automatic checkpoint write notifications."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / ".codex" / "hooks" / "stop-wrapper.py"
CHECKPOINT_HOOK = REPO_ROOT / ".codex" / "hooks" / "checkpoint.py"
REAL_SESSION = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class StopWrapperNotificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.hooks = self.home / ".codex" / "hooks"
        self.hooks.mkdir(parents=True)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / ".obsidian").mkdir()
        shutil.copy2(WRAPPER, self.hooks / "stop-wrapper.py")
        (self.hooks / "retrieve.py").write_text(
            "import sys\n"
            "sys.stdin.read()\n",
            encoding="utf-8",
        )
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_checkpoint_hook(self, output: str) -> None:
        (self.hooks / "checkpoint.py").write_text(
            "import sys\n"
            "sys.stdin.read()\n"
            f"print({output!r})\n",
            encoding="utf-8",
        )

    def run_wrapper(
        self,
        output: str | None,
        event_name: str = "Stop",
        payload: dict | None = None,
    ) -> subprocess.CompletedProcess:
        if output is not None:
            self.write_checkpoint_hook(output)
        return subprocess.run(
            [
                sys.executable,
                str(self.hooks / "stop-wrapper.py"),
                "--vault-root",
                str(self.vault),
            ],
            input=json.dumps(payload or {"hook_event_name": event_name}),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_stop_write_notifies_user_with_final_vault_location(self) -> None:
        relative_note = "Codex工作记录/会话断点/系统与运维/检查 Docker 服务.md"
        relative_directory = "Codex工作记录/会话断点/系统与运维/"
        absolute_note = self.vault / relative_note
        result = self.run_wrapper(
            "\n".join((
                f"[obsidian-hook] Session checkpoint written: {absolute_note}",
                "[obsidian-hook] Session checkpoint location: "
                f"vault-relative={relative_note}; folder={relative_directory}",
                "[obsidian-hook] Daily index updated",
            ))
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "Stop")
        self.assertEqual(
            payload["systemMessage"],
            "\n".join((
                "本次对话已写入会话断点。",
                f"断点文件：{relative_note}",
                f"所在目录：{relative_directory}",
            )),
        )
        self.assertNotIn("尚未归类", payload["systemMessage"])

    def test_stop_falls_back_to_absolute_output_when_location_line_is_missing(self) -> None:
        relative_note = "Codex工作记录/会话断点/未分类对话/网络连接.md"
        absolute_note = self.vault / relative_note
        result = self.run_wrapper(f"[obsidian-hook] Session checkpoint written: {absolute_note}")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn(f"断点文件：{relative_note}", payload["systemMessage"])
        self.assertIn("所在目录：Codex工作记录/会话断点/未分类对话/", payload["systemMessage"])
        self.assertIn("当前断点尚未归类。调用 `$checkpoint` 进行归类。", payload["systemMessage"])

    def test_index_only_or_prompt_submit_write_does_not_emit_stop_notice(self) -> None:
        indexed = self.run_wrapper("[obsidian-hook] Session indexed without checkpoint: 2/5 rounds")
        prompt_submit = self.run_wrapper(
            "\n".join((
                "[obsidian-hook] Session checkpoint written: /tmp/ignored.md",
                "[obsidian-hook] Session checkpoint location: "
                "vault-relative=Codex工作记录/会话断点/未分类对话/ignored.md; "
                "folder=Codex工作记录/会话断点/未分类对话/",
            )),
            event_name="UserPromptSubmit",
        )

        self.assertEqual(indexed.returncode, 0, indexed.stderr + indexed.stdout)
        self.assertEqual(indexed.stdout, "")
        self.assertEqual(prompt_submit.returncode, 0, prompt_submit.stderr + prompt_submit.stdout)
        self.assertEqual(prompt_submit.stdout, "")

    def test_real_automatic_checkpoint_write_notifies_with_existing_file(self) -> None:
        rollout = self.home / ".codex" / "sessions" / "2026" / "07" / "13" / f"rollout-2026-07-13T10-00-00-{REAL_SESSION}.jsonl"
        entries = []
        for round_number in range(5):
            entries.extend((
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": f"请检查自动断点提示，第 {round_number + 1} 轮。"}],
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": f"第 {round_number + 1} 轮检查完成。"}],
                    },
                },
            ))
        rollout.parent.mkdir(parents=True)
        rollout.write_text(
            "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(CHECKPOINT_HOOK, self.hooks / "checkpoint.py")
        result = self.run_wrapper(
            None,
            payload={
                "hook_event_name": "Stop",
                "session_id": REAL_SESSION,
                "transcript_path": str(rollout),
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        lines = payload["systemMessage"].splitlines()
        self.assertEqual(lines[0], "本次对话已写入会话断点。")
        note_path = lines[1].removeprefix("断点文件：")
        directory = lines[2].removeprefix("所在目录：")
        self.assertTrue((self.vault / note_path).is_file())
        self.assertEqual(Path(note_path).parent.as_posix() + "/", directory)
        self.assertEqual(Path(note_path).parent.as_posix(), "Codex工作记录/会话断点/未分类对话")
        self.assertEqual(lines[3], "当前断点尚未归类。调用 `$checkpoint` 进行归类。")


if __name__ == "__main__":
    unittest.main()
