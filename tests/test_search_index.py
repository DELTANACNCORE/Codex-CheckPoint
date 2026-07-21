#!/usr/bin/env python3
"""Coverage for the dependency-free incremental CxCP search index."""

import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SEARCH = REPO_ROOT / ".codex" / "skills" / "search" / "search.py"


class SearchIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.vault = self.root / "vault"
        self.home = self.root / "home"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.note = self.vault / "项目总结" / "网络项目.md"
        self.note.parent.mkdir(parents=True)
        self.env = {**os.environ, "HOME": str(self.home), "CODEX_HOME": str(self.home / ".codex")}

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_note(self, body: str) -> None:
        self.note.write_text(
            f'''---
aliases: ["网络入口"]
keywords: ["Netplan"]
tags: ["运维/网络"]
---

# 网络项目总结

{body}
''',
            encoding="utf-8",
        )

    def run_search(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SEARCH), "--vault-root", str(self.vault), *arguments],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_incremental_index_tracks_create_update_and_delete(self) -> None:
        self.write_note("Netplan 配置已经验证。")

        first = self.run_search("Netplan")
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        self.assertIn("网络项目总结", first.stdout)
        cache_files = list((self.home / ".codex" / "cache").glob("cxcp-search-*.sqlite3"))
        self.assertEqual(len(cache_files), 1)

        self.write_note("WireGuard 隧道已经验证。")
        updated = self.run_search("WireGuard")
        self.assertEqual(updated.returncode, 0, updated.stderr + updated.stdout)
        self.assertIn("WireGuard", updated.stdout)

        self.note.unlink()
        deleted = self.run_search("WireGuard")
        self.assertEqual(deleted.returncode, 0, deleted.stderr + deleted.stdout)
        self.assertIn("没有找到相关内容", deleted.stdout)

    def test_index_maintenance_commands_do_not_require_keywords(self) -> None:
        self.write_note("Netplan 配置已经验证。")

        rebuilt = self.run_search("--rebuild-index")
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr + rebuilt.stdout)
        self.assertIn("搜索索引已重建", rebuilt.stdout)

        status = self.run_search("--index-status")
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        self.assertIn("搜索索引状态", status.stdout)

        invalid = self.run_search("--rebuild-index", "Netplan")
        self.assertEqual(invalid.returncode, 2, invalid.stderr + invalid.stdout)
        self.assertIn("不能同时提供搜索关键词", invalid.stderr)

    def test_semantic_mode_keeps_lexical_results_when_no_local_model_exists(self) -> None:
        self.write_note("Netplan 配置已经验证。")

        result = self.run_search("--semantic", "Netplan")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("网络项目总结", result.stdout)

    def test_semantic_status_is_read_only_and_does_not_require_keywords(self) -> None:
        self.write_note("Netplan 配置已经验证。")
        before = self.note.read_text(encoding="utf-8")

        result = self.run_search("--semantic-status")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("语义检索状态", result.stdout)
        self.assertIn("向量缓存", result.stdout)
        self.assertEqual(self.note.read_text(encoding="utf-8"), before)
        self.assertFalse((self.home / ".codex" / "cache").exists())

    def test_semantic_cache_reuses_local_vectors(self) -> None:
        self.write_note("Netplan 配置已经验证。")
        spec = spec_from_file_location("cxcp_search_test_module", SEARCH)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)

        class FakeModel:
            def __init__(self) -> None:
                self.passage_batches = 0

            def encode(self, values, **_kwargs):
                if values and values[0].startswith("passage:"):
                    self.passage_batches += 1
                    return [[1.0, 0.0] if "Netplan" in value else [0.0, 1.0] for value in values]
                return [[1.0, 0.0] for _value in values]

        model = FakeModel()
        records = module.scan_records(self.vault)
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home / ".codex")}, clear=False), patch.object(
            module,
            "load_local_semantic_model",
            return_value=(model, ""),
        ):
            first_scores, first_notice = module.semantic_scores(
                records, self.vault, "Netplan 网卡", "fake-local-model", use_cache=True,
            )
            second_scores, second_notice = module.semantic_scores(
                records, self.vault, "Netplan 网卡", "fake-local-model", use_cache=True,
            )

        relative = "项目总结/网络项目.md"
        self.assertEqual(first_notice, "")
        self.assertEqual(second_notice, "")
        self.assertGreater(first_scores[relative]["score"], 0.99)
        self.assertEqual(first_scores, second_scores)
        self.assertEqual(model.passage_batches, 1)

    def test_semantic_chunks_include_a_late_heading_section(self) -> None:
        self.write_note(
            "## 背景\n\n" + "无关说明。" * 160
            + "\n\n## 可直接续接的结论\n\n- 晚段中的 SSH 续接命令已经验证。"
        )
        spec = spec_from_file_location("cxcp_search_chunk_test_module", SEARCH)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)

        record = module.scan_records(self.vault)[0]
        chunks = module.semantic_chunks_for(record)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(any("SSH 续接命令" in chunk["content"] for chunk in chunks))
        self.assertTrue(any(chunk["heading"] == "可直接续接的结论" for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
