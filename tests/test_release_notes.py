#!/usr/bin/env python3
"""Coverage for release-note generation from the Obsidian changelog."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "release_notes.py"


def load_module():
    spec = importlib.util.spec_from_file_location("release_notes_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.changelog = Path(self.temp_dir.name) / "更新日志.md"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_changelog(self, release_body: str) -> None:
        self.changelog.write_text(
            f"""# 更新日志

## V1.0.0

### Added

- 内部更新条目。

### GitHub Release

{release_body}

## V0.9.1

- 历史版本。
""",
            encoding="utf-8",
        )

    def test_builds_screenshot_style_bilingual_body(self) -> None:
        self.write_changelog(
            """- 续接断点会保留历史结论和执行证据。
  Continuations retain earlier conclusions and execution evidence.
- 审计会展示高区分度的只读材料簇。
  Audits show high-distinction read-only material clusters."""
        )

        body = self.module.build_release_body(self.changelog, "1.0.0")

        self.assertEqual(
            body,
            """V1.0.0

- 续接断点会保留历史结论和执行证据。
  Continuations retain earlier conclusions and execution evidence.
- 审计会展示高区分度的只读材料簇。
  Audits show high-distinction read-only material clusters.
""",
        )

    def test_rejects_release_item_without_english_line(self) -> None:
        self.write_changelog("- 缺少英文描述。")

        with self.assertRaisesRegex(ValueError, "英文描述"):
            self.module.build_release_body(self.changelog, "1.0.0")

    def test_rejects_missing_version_section(self) -> None:
        self.changelog.write_text("# 更新日志\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "缺少 V1.0.0"):
            self.module.build_release_body(self.changelog, "1.0.0")


if __name__ == "__main__":
    unittest.main()
