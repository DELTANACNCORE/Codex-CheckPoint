#!/usr/bin/env python3
"""Regression coverage for relevant long-term experience retrieval."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIEVE = REPO_ROOT / ".codex" / "hooks" / "retrieve.py"
CURRENT_SESSION = "11111111-1111-1111-1111-111111111111"


class RetrieveLongTermRelevanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        experience_dir = self.vault / "长期经验总结"
        experience_dir.mkdir()
        (experience_dir / "sub2api.md").write_text(
            """---
project: sub2api
tags: ["长期经验总结", "核心知识", "Docker", "sub2api", "运维"]
aliases: ["sub2api 更新", "sub2api Docker 升级"]
---

# sub2api Docker 更新 长期经验总结

## 核心结论

sub2api 使用明确镜像版本执行 Docker 更新。
""",
            encoding="utf-8",
        )
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_retrieve(self, prompt: str, session_id: str = "") -> str:
        event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": session_id,
            "prompt": prompt,
        }
        result = subprocess.run(
            [sys.executable, str(RETRIEVE), "--vault-root", str(self.vault)],
            input=json.dumps(event, ensure_ascii=False),
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def write_current_checkpoint(self) -> None:
        note_path = self.vault / "Codex工作记录" / "会话断点" / "当前会话.md"
        note_path.parent.mkdir(parents=True)
        note_path.write_text(
            f"""---
date: "2026-07-13"
session_id: "{CURRENT_SESSION}"
status: "completed"
projects: ["checkpoint迁到Codex"]
external_projects: []
---

# 当前知识库清理会话

**状态**: 正常结束

## 可直接续接的结论

继续处理知识库检索规则。
""",
            encoding="utf-8",
        )

    def test_response_annotation_does_not_reintroduce_quoted_experience(self) -> None:
        self.write_current_checkpoint()
        output = self.run_retrieve(
            """# Response annotations:
<response-annotations>
[{"text":"已发现并复用长期经验：sub2api Docker 更新 长期经验总结"}]
</response-annotations>
## My request for Codex:
为什么这个无关经验一直出现？
""",
            CURRENT_SESSION,
        )
        self.assertIn("当前知识库清理会话", output)
        self.assertNotIn("sub2api Docker 更新 长期经验总结", output)

    def test_direct_project_reference_reuses_experience(self) -> None:
        output = self.run_retrieve("请检查 sub2api Docker 更新")
        self.assertIn("sub2api Docker 更新 长期经验总结", output)

    def test_generic_docker_reference_does_not_reuse_experience(self) -> None:
        output = self.run_retrieve("Docker 服务怎么更新")
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
