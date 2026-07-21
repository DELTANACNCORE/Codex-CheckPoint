#!/usr/bin/env python3
"""Coverage for the explicit current-environment verification runner."""

from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY = REPO_ROOT / ".codex" / "skills" / "verify" / "verify.py"


def python_command(source: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"


class VerifyRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_verify(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY), "--cwd", str(self.cwd), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_runs_explicit_command_and_reports_current_result(self) -> None:
        result = self.run_verify("--command", python_command("print('当前验证通过')"))

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("当前环境验证", result.stdout)
        self.assertIn("结果：通过", result.stdout)
        self.assertIn("当前验证通过", result.stdout)

    def test_failure_keeps_command_exit_status_as_evidence(self) -> None:
        result = self.run_verify("--command", python_command("raise SystemExit(3)"))

        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertIn("结果：失败，退出码 3", result.stdout)

    def test_dry_run_does_not_execute_command(self) -> None:
        marker = self.cwd / "executed.txt"
        command = python_command(f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')")

        result = self.run_verify("--dry-run", "--command", command)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertFalse(marker.exists())
        self.assertIn("仅预演，未执行", result.stdout)

    def test_redacts_sensitive_command_output(self) -> None:
        secret = "token-value-123456789"
        result = self.run_verify("--command", python_command(f"print('token={secret}')"))

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertNotIn(secret, result.stdout)
        self.assertIn("[REDACTED]", result.stdout)


if __name__ == "__main__":
    unittest.main()
