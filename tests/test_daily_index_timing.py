#!/usr/bin/env python3
"""Coverage for conversation-time daily index rows and legacy table migration."""

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".codex" / "hooks" / "checkpoint.py"
SESSION_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def load_hook(vault: Path):
    previous_vault = os.environ.get("OBSIDIAN_VAULT")
    os.environ["OBSIDIAN_VAULT"] = str(vault)
    try:
        spec = importlib.util.spec_from_file_location(f"daily_index_hook_{id(vault)}", HOOK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_vault is None:
            os.environ.pop("OBSIDIAN_VAULT", None)
        else:
            os.environ["OBSIDIAN_VAULT"] = previous_vault


class DailyIndexTimingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.index_dir = self.vault / "Codex工作记录" / "会话索引"
        self.note = self.vault / "Codex工作记录" / "会话断点" / "跨日会话.md"
        self.note.parent.mkdir(parents=True)
        self.note.write_text("# 跨日会话\n", encoding="utf-8")
        self.hook = load_hook(self.vault)
        self.context = {
            "topic": "跨日会话时间验证",
            "round_count": 5,
            "conversation_started_at": "2026-07-12T23:22:00+08:00",
            "written_files": set(),
            "external_written_files": set(),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def update(self, value: datetime) -> None:
        self.hook.update_daily_index(
            self.index_dir,
            self.note,
            SESSION_ID,
            self.context,
            "completed",
            now=value,
        )

    def test_cross_day_entries_show_conversation_and_update_times(self) -> None:
        self.update(datetime(2026, 7, 12, 23, 55, tzinfo=TIMEZONE))
        self.update(datetime(2026, 7, 13, 3, 16, tzinfo=TIMEZONE))

        first_day = (self.index_dir / "2026-07-12.md").read_text(encoding="utf-8")
        second_day = (self.index_dir / "2026-07-13.md").read_text(encoding="utf-8")
        self.assertIn("| 时间 | 状态 | 话题 | 产出 |", first_day)
        self.assertIn("| :--- | :---: | :--- | :--- |", first_day)
        self.assertIn(
            "03:16<br><small>对话时间 07-12 23:22</small>",
            first_day,
        )
        self.assertIn(
            "03:16<br><small>对话时间 07-12 23:22</small>",
            second_day,
        )
        self.assertNotIn("session 更新为", first_day)
        self.assertEqual(first_day.count(f"<!-- session:{SESSION_ID} -->"), 1)
        self.assertEqual(second_day.count(f"<!-- session:{SESSION_ID} -->"), 1)
        self.assertIn("<!-- session-date:2026-07-12 -->", first_day)
        self.assertIn("<!-- session-date:2026-07-13 -->", second_day)

    def test_legacy_five_column_row_is_replaced_without_blank_column(self) -> None:
        self.index_dir.mkdir(parents=True)
        legacy = self.index_dir / "2026-07-12.md"
        legacy.write_text(
            """---
date: "2026-07-12"
---

# 会话记录 - 2026-07-12

| 时间 | 状态 | 话题 | 产出 | |
| --- | --- | --- | --- | --- |
| 23:55 | ✅ | [[Codex工作记录/会话断点/跨日会话|跨日会话]] | — | <!-- session:cccccccc-cccc-cccc-cccc-cccccccccccc --> |
""",
            encoding="utf-8",
        )
        self.update(datetime(2026, 7, 12, 23, 55, tzinfo=TIMEZONE))

        text = legacy.read_text(encoding="utf-8")
        self.assertIn("| 时间 | 状态 | 话题 | 产出 |", text)
        self.assertNotIn("| 时间 | 状态 | 话题 | 产出 | |", text)
        self.assertIn("session 更新为 23:55", text)
        self.assertIn("[[Codex工作记录/会话断点/跨日会话\\|跨日会话]]", text)
        self.assertNotIn("[[Codex工作记录/会话断点/跨日会话|跨日会话]]", text)

    def test_legacy_row_without_closing_pipe_is_migrated(self) -> None:
        self.index_dir.mkdir(parents=True)
        legacy = self.index_dir / "2026-07-12.md"
        legacy.write_text(
            """---
date: "2026-07-12"
---

# 会话记录 - 2026-07-12

| 时间 | 状态 | 话题 | 产出 | |
| --- | --- | --- | --- | --- |
| 23:55 | ✅ | [[Codex工作记录/会话断点/跨日会话|跨日会话]] | — | <!-- session:cccccccc-cccc-cccc-cccc-cccccccccccc -->
""",
            encoding="utf-8",
        )
        self.update(datetime(2026, 7, 12, 23, 55, tzinfo=TIMEZONE))

        text = legacy.read_text(encoding="utf-8")
        self.assertNotIn("| 产出 | |", text)
        self.assertNotIn("| — | <!-- session:", text)
        self.assertIn("<!-- session-date:2026-07-12 -->", text)


if __name__ == "__main__":
    unittest.main()
