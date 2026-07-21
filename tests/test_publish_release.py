#!/usr/bin/env python3
"""Coverage for explicit GitHub Release preflight and publishing."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "publish_release.py"
COMMIT = "1234567890abcdef1234567890abcdef12345678"


def load_module():
    spec = importlib.util.spec_from_file_location("publish_release_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublishReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.changelog = self.root / "更新日志.md"
        self.changelog.write_text(
            """# 更新日志

## V1.0.1

### GitHub Release

- 修复续接摘要。
  Fix continuation summaries.
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git_runner(self, repo_root: Path, *arguments: str) -> str:
        values = {
            ("status", "--porcelain"): "",
            ("rev-parse", "HEAD"): COMMIT,
            ("rev-parse", "refs/tags/v1.0.1^{}") : COMMIT,
            ("config", "--get", "remote.origin.url"): "git@github.com:DELTANACNCORE/Codex-CheckPoint.git",
            (
                "ls-remote", "--tags", "origin", "refs/tags/v1.0.1", "refs/tags/v1.0.1^{}",
            ): "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/v1.0.1\n"
            + f"{COMMIT}\trefs/tags/v1.0.1^{{}}",
        }
        return values[arguments]

    def preflight(self) -> dict:
        return self.module.preflight(
            self.root,
            "1.0.1",
            self.changelog,
            "origin",
            git_runner=self.git_runner,
        )

    def test_parses_github_remote_variants(self) -> None:
        self.assertEqual(
            self.module.github_repository("https://github.com/DELTANACNCORE/Codex-CheckPoint.git"),
            "DELTANACNCORE/Codex-CheckPoint",
        )
        self.assertEqual(
            self.module.github_repository("ssh://git@github.com/DELTANACNCORE/Codex-CheckPoint.git"),
            "DELTANACNCORE/Codex-CheckPoint",
        )
        with self.assertRaisesRegex(self.module.ReleaseError, "github.com"):
            self.module.github_repository("https://example.com/project.git")

    def test_preflight_requires_clean_matching_local_and_remote_tag(self) -> None:
        check = self.preflight()

        self.assertEqual(check["tag"], "v1.0.1")
        self.assertEqual(check["commit"], COMMIT)
        self.assertEqual(check["repository"], "DELTANACNCORE/Codex-CheckPoint")
        self.assertIn("修复续接摘要", check["body"])

    def test_preflight_rejects_dirty_worktree(self) -> None:
        def dirty_runner(repo_root: Path, *arguments: str) -> str:
            if arguments == ("status", "--porcelain"):
                return " M README.md"
            return self.git_runner(repo_root, *arguments)

        with self.assertRaisesRegex(self.module.ReleaseError, "未提交改动"):
            self.module.preflight(self.root, "1.0.1", self.changelog, "origin", git_runner=dirty_runner)

    def test_publish_is_idempotent_only_when_existing_release_matches(self) -> None:
        check = self.preflight()
        existing = {
            "name": check["title"],
            "tag_name": check["tag"],
            "body": check["body"],
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/DELTANACNCORE/Codex-CheckPoint/releases/tag/v1.0.1",
        }
        calls = []

        def request_runner(method: str, endpoint: str, token: str, payload: dict | None):
            calls.append((method, endpoint, payload))
            return 200, existing

        release, created = self.module.publish_release(check, "token", request_runner=request_runner)

        self.assertFalse(created)
        self.assertEqual(release["html_url"], existing["html_url"])
        self.assertEqual([item[0] for item in calls], ["GET"])


if __name__ == "__main__":
    unittest.main()
