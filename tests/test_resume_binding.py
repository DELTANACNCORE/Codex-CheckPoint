#!/usr/bin/env python3
"""Resume binding keeps continuation sessions on the original checkpoint note."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_ROOT = REPO_ROOT / ".codex"
HOOK = CODEX_ROOT / "hooks" / "checkpoint.py"
RETRIEVE = CODEX_ROOT / "hooks" / "retrieve.py"


def load_module(path: Path, vault: Path, name: str):
    previous_vault = os.environ.get("OBSIDIAN_VAULT")
    previous_home = os.environ.get("CODEX_HOME")
    os.environ["OBSIDIAN_VAULT"] = str(vault)
    os.environ["CODEX_HOME"] = str(vault / ".codex-home")
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_vault is None:
            os.environ.pop("OBSIDIAN_VAULT", None)
        else:
            os.environ["OBSIDIAN_VAULT"] = previous_vault
        if previous_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous_home


class ResumeBindingTest(unittest.TestCase):
    def test_retrieve_writes_binding_for_explicit_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "vault"
            notes = vault / "Codex工作记录" / "会话断点" / "知识库与工作流"
            notes.mkdir(parents=True)
            (vault / ".obsidian").mkdir()
            note = notes / "checkpoint 迁到 Codex.md"
            original = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
            note.write_text(
                f"""---
session_id: "{original}"
session_ids: ["{original}"]
status: "completed"
---

# checkpoint 迁到 Codex

## 可直接续接的结论

继续完善续接绑定。

## 已完成事项

- 已有主断点

## 当前状态与续接

- 等待新对话续接

## 实际产出

（无）
""",
                encoding="utf-8",
            )
            retrieve = load_module(RETRIEVE, vault, f"retrieve_{id(vault)}")
            runtime = "cccccccc-4444-5555-6666-dddddddddddd"
            prompt = f"打开 thread_id {original} 继续 checkpoint 迁移"
            brief = retrieve.recovery_brief(runtime, prompt)
            self.assertIn("用户指定的会话断点", brief)
            bind_path = Path(os.environ.get("CODEX_HOME", vault / ".codex-home")) 
            # module captured RESUME_BIND_DIR at import; re-load with env
            retrieve = load_module(RETRIEVE, vault, f"retrieve2_{id(vault)}")
            brief = retrieve.recovery_brief(runtime, prompt)
            bind_file = retrieve.RESUME_BIND_DIR / f"{runtime}.json"
            self.assertTrue(bind_file.is_file(), brief)
            payload = json.loads(bind_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["target_session_id"], original)
            self.assertEqual(Path(payload["note_path"]).resolve(), note.resolve())

    def test_checkpoint_updates_original_note_and_records_session_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "vault"
            notes = vault / "Codex工作记录" / "会话断点" / "知识库与工作流"
            notes.mkdir(parents=True)
            (vault / ".obsidian").mkdir()
            (vault / "Codex工作记录" / "会话索引").mkdir(parents=True)
            (vault / "项目总结").mkdir(parents=True)
            original = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
            runtime = "cccccccc-4444-5555-6666-dddddddddddd"
            note = notes / "checkpoint 迁到 Codex.md"
            note.write_text(
                f"""---
date: "2026-07-18"
session_id: "{original}"
session_ids: ["{original}"]
status: "completed"
platform: "codex"
projects: ["checkpoint迁到Codex"]
external_projects: []
category: []
tags: ["checkpoint"]
keywords: ["checkpoint"]
aliases: ["checkpoint 迁到 Codex"]
title_baseline: "checkpoint 迁到 Codex"
title_source: "preserved"
---

# checkpoint 迁到 Codex

> 正常结束 · aaaaaaaa-111

**状态**: 正常结束
**会话 ID**: `{original}`

## 可直接续接的结论

旧结论

## 已完成事项

- 旧事项

## 当前状态与续接

- 旧状态

## 实际产出

（本次未写入方案文件）
""",
                encoding="utf-8",
            )

            checkpoint = load_module(HOOK, vault, f"checkpoint_{id(vault)}")
            bind_dir = checkpoint.RESUME_BIND_DIR
            bind_dir.mkdir(parents=True, exist_ok=True)
            (bind_dir / f"{runtime}.json").write_text(
                json.dumps(
                    {
                        "runtime_session_id": runtime,
                        "target_session_id": original,
                        "note_path": str(note),
                        "source": "用户指定的会话断点",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            # Simulate the core resolution + note generation path used by main.
            existing_note = checkpoint.find_note_by_session(checkpoint.NOTE_DIR, runtime)
            self.assertIsNone(existing_note)
            binding = checkpoint.load_resume_binding(runtime)
            resume_note, resume_target = checkpoint.resolve_resume_note(checkpoint.NOTE_DIR, binding)
            self.assertEqual(resume_note.resolve(), note.resolve())
            self.assertEqual(resume_target, original)

            ctx = {
                "topic": "checkpoint 迁到 Codex",
                "title_baseline": "checkpoint 迁到 Codex",
                "title_source": "preserved",
                "checkpoint_category": "知识库与工作流",
                "knowledge_archived": False,
                "projects": {"checkpoint迁到Codex"},
                "external_projects": set(),
                "category": [],
                "tags": ["checkpoint"],
                "keywords": ["checkpoint"],
                "aliases": ["checkpoint 迁到 Codex"],
                "user_prompts": ["打开旧会话继续", "修改 checkpoint 让续接写入原断点"],
                "assistant_updates": ["已改为续接写入原 session 断点，并在 session_ids 记录多个会话。"],
                "latest_assistant_update": "已改为续接写入原 session 断点，并在 session_ids 记录多个会话。",
                "written_files": set(),
                "external_written_files": set(),
                "used_plan_mode": False,
                "verbal_plan_snippets": [],
                "resume_bound": True,
                "runtime_session_id": runtime,
                "continuation_session_ids": [runtime],
            }
            content = checkpoint.generate_session_note(original, ctx, "completed")
            note.write_text(content, encoding="utf-8")

            self.assertIn(f'session_id: "{original}"', content)
            self.assertIn(runtime, content)
            self.assertIn("session_ids:", content)
            self.assertIn("continuation_session_ids:", content)
            # Still one note path.
            self.assertTrue(note.is_file())
            found = checkpoint.find_note_by_session(checkpoint.NOTE_DIR, runtime)
            self.assertEqual(found.resolve(), note.resolve())
            found_original = checkpoint.find_note_by_session(checkpoint.NOTE_DIR, original)
            self.assertEqual(found_original.resolve(), note.resolve())
            siblings = list(notes.glob("*.md"))
            self.assertEqual(len(siblings), 1)


if __name__ == "__main__":
    unittest.main()
