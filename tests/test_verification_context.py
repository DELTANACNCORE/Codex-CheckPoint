#!/usr/bin/env python3
"""Coverage for freshness guidance when historical knowledge is used in verification work."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIEVE = REPO_ROOT / ".codex" / "hooks" / "retrieve.py"
SESSION = "12345678-1234-1234-1234-123456789012"


class VerificationContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        self.note = self.vault / "Codex工作记录" / "会话断点" / "未分类对话" / "Netplan.md"
        self.note.parent.mkdir(parents=True)
        (self.vault / ".obsidian").mkdir()
        self.note.write_text(
            f'''---
session_id: "{SESSION}"
status: "completed"
projects: []
---

# Netplan 迁移

## 已验证结果

- 历史 Netplan 配置检查通过。

## 可直接续接的结论

- 可以继续核对当前网卡状态。
''',
            encoding="utf-8",
        )
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.home / ".codex")}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_retrieve(self, prompt: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RETRIEVE), "--vault-root", str(self.vault)],
            input=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "prompt": prompt}, ensure_ascii=False),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_verification_request_requires_current_execution(self) -> None:
        result = self.run_retrieve("检查 Netplan 当前状态")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("验证时效要求", result.stdout)
        self.assertIn("必须重新运行相关命令", result.stdout)
        self.assertIn("Netplan 迁移", result.stdout)

    def test_non_verification_recovery_keeps_existing_context_shape(self) -> None:
        result = self.run_retrieve("继续 Netplan 迁移")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn("验证时效要求", result.stdout)
        self.assertIn("Netplan 迁移", result.stdout)


if __name__ == "__main__":
    unittest.main()
