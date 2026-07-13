#!/usr/bin/env python3
"""Coverage for credential redaction in Codex knowledge outputs."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".codex" / "hooks" / "checkpoint.py"
SYNTHESIZE = REPO_ROOT / ".codex" / "skills" / "synthesize" / "synthesize.py"
REDACTION = REPO_ROOT / ".codex" / "redaction.py"
SESSION_ID = "99999999-aaaa-bbbb-cccc-dddddddddddd"
SYNTHESIS_SESSION_ID = "88888888-aaaa-bbbb-cccc-eeeeeeeeeeee"

SECRETS = (
    "fake-bearer-token-1234567890",
    "ab84335a-1248-4a9c-bbd2-a8a3048664e5",
    "api-key-value-123456",
    "token-value-123456789",
    "password-value-123456",
    "secret-value-123456",
    "sk-testc6a2afdab413df77dfd20dc2f3970527",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb2RleCJ9.signaturevalue123456",
    "sessionid-abcdef123456",
    "private-material-123456",
)


def response(role: str, text: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": text}],
        },
    }


def load_redaction_module():
    spec = importlib.util.spec_from_file_location("cxcp_redaction_test", REDACTION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CheckpointRedactionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.sessions = self.home / ".codex" / "sessions" / "2026" / "07" / "14"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.home / ".codex"),
        }

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def assert_no_secret(self, text: str) -> None:
        for secret in SECRETS:
            self.assertNotIn(secret, text, secret)

    def assert_redacted(self, text: str) -> None:
        self.assert_no_secret(text)
        self.assertIn("[REDACTED]", text)

    def run_hook(self, rollout: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(HOOK),
                "--vault-root",
                str(self.vault),
                "--transcript",
                str(rollout),
                "--session-id",
                SESSION_ID,
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_rollout(self, user_source: Path, project_summary: Path) -> Path:
        entries = []
        for round_number in range(5):
            entries.append(response(
                "user",
                "第 {} 轮检查凭据保护。Authorization: Bearer fake-bearer-token-1234567890；"
                "X-Namespace: ab84335a-1248-4a9c-bbd2-a8a3048664e5；"
                "api_key=api-key-value-123456。".format(round_number + 1),
            ))
            entries.append(response(
                "assistant",
                "第 {} 轮验证。token=token-value-123456789，password=password-value-123456，"
                "secret: 'secret-value-123456'，使用 sk-testc6a2afdab413df77dfd20dc2f3970527。".format(round_number + 1),
            ))
        entries.append(response(
            "assistant",
            "验证完成。JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb2RleCJ9.signaturevalue123456，"
            "Cookie: sessionid-abcdef123456，\n-----BEGIN PRIVATE KEY-----\n"
            "private-material-123456\n-----END PRIVATE KEY-----",
        ))
        for target in (user_source, project_summary):
            entries.append({
                "type": "custom_tool_call",
                "payload": {
                    "name": "apply_patch",
                    "input": f"*** Begin Patch\n*** Update File: {target}\n*** End Patch",
                },
            })
        rollout = self.sessions / f"rollout-2026-07-14T09-00-00-{SESSION_ID}.jsonl"
        rollout.parent.mkdir(parents=True, exist_ok=True)
        rollout.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")
        return rollout

    def test_common_credential_shapes_are_redacted(self) -> None:
        redaction = load_redaction_module()
        raw = "\n".join((
            "Authorization: Bearer fake-bearer-token-1234567890",
            '"Authorization": "Bearer fake-bearer-token-1234567890"',
            "X-Namespace: ab84335a-1248-4a9c-bbd2-a8a3048664e5",
            "api_key=api-key-value-123456",
            '"token": "token-value-123456789"',
            "password=password-value-123456",
            "secret: 'secret-value-123456'",
            "OPENAI_API_KEY=sk-testc6a2afdab413df77dfd20dc2f3970527",
            "python3 deploy.py --api-key api-key-value-123456",
            "Cookie: sessionid-abcdef123456",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb2RleCJ9.signaturevalue123456",
            "-----BEGIN PRIVATE KEY-----\nprivate-material-123456\n-----END PRIVATE KEY-----",
        ))

        redacted = redaction.redact_sensitive_text(raw)

        self.assert_redacted(redacted)
        self.assertEqual(
            redaction.redact_sensitive_text("token=short password=1234 secret: tiny"),
            "token=short password=1234 secret: tiny",
        )

    def test_hook_redacts_generated_documents_without_mutating_source_markdown(self) -> None:
        user_source = self.vault / "项目资料" / "凭据测试" / "原始方案.md"
        user_source.parent.mkdir(parents=True)
        original_source = "api_key=api-key-value-123456\nAuthorization: Bearer fake-bearer-token-1234567890\n"
        user_source.write_text(original_source, encoding="utf-8")

        project_summary = self.vault / "项目总结" / "凭据测试.md"
        project_summary.parent.mkdir(parents=True)
        project_summary.write_text(
            f"---\nproject: 凭据测试\nsession_ids: [\"{SESSION_ID}\"]\n---\n\n# 凭据测试 项目总结\n",
            encoding="utf-8",
        )
        session_index = self.home / ".codex" / "session_index.jsonl"
        session_index.parent.mkdir(parents=True)
        session_index.write_text(
            json.dumps({"id": SESSION_ID, "thread_name": "部署 API token=token-value-123456789"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        result = self.run_hook(self.write_rollout(user_source, project_summary))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assert_no_secret(result.stdout)

        note = next((self.vault / "Codex工作记录" / "会话断点").rglob("*.md"))
        index = next((self.vault / "Codex工作记录" / "会话索引").glob("*.md"))
        homepage = self.vault / "知识库首页.md"
        generated = "\n".join(path.read_text(encoding="utf-8") for path in (note, index, project_summary, homepage))
        self.assert_redacted(generated)
        self.assertEqual(user_source.read_text(encoding="utf-8"), original_source)

    def test_synthesize_redacts_project_and_long_term_outputs(self) -> None:
        note_dir = self.vault / "Codex工作记录" / "会话断点" / "未分类对话"
        note_dir.mkdir(parents=True)
        note = note_dir / "安全归档断点.md"
        note.write_text(
            f'''---
date: "2026-07-14"
session_id: "{SYNTHESIS_SESSION_ID}"
status: "completed"
projects: ["安全归档"]
tags: ["security"]
keywords: []
aliases: []
---

# 安全归档断点

**已记录用户消息**: 24

## 可直接续接的结论

- Authorization: Bearer fake-bearer-token-1234567890 已在配置中验证。

## 会话目标演进

- 为安全归档处理 api_key=api-key-value-123456。

## 已验证结果

- token=token-value-123456789 已通过真实环境验证。

## 最佳实践

- password=password-value-123456 仅通过受控配置传递。

## 踩坑记录

- secret: 'secret-value-123456' 曾被写入临时输出。

## 实际产出

```bash
python3 deploy.py --api-key api-key-value-123456
```
''',
            encoding="utf-8",
        )
        user_source = self.vault / "项目资料" / "安全归档" / "原始部署说明.md"
        user_source.parent.mkdir(parents=True)
        original_source = "Authorization: Bearer fake-bearer-token-1234567890\n"
        user_source.write_text(original_source, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE),
                "--vault-root",
                str(self.vault),
                "--project",
                "安全归档",
                "--long-term",
                "--user-approved",
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assert_no_secret(result.stdout)

        summary = self.vault / "项目总结" / "安全归档.md"
        reference = self.vault / "AI开发参考" / "安全归档.md"
        homepage = self.vault / "知识库首页.md"
        self.assertTrue(summary.is_file())
        self.assertTrue(reference.is_file())
        self.assertIn("ai_development_reference: true", reference.read_text(encoding="utf-8"))
        generated = "\n".join(path.read_text(encoding="utf-8") for path in (note, summary, reference, homepage))
        self.assert_redacted(generated)
        self.assertEqual(user_source.read_text(encoding="utf-8"), original_source)

    def test_ai_reference_still_requires_explicit_authorization(self) -> None:
        note_dir = self.vault / "Codex工作记录" / "会话断点" / "未分类对话"
        note_dir.mkdir(parents=True)
        (note_dir / "授权测试.md").write_text(
            """---
session_id: "77777777-aaaa-bbbb-cccc-eeeeeeeeeeee"
status: "completed"
projects: ["授权测试"]
tags: []
keywords: []
aliases: []
---

# 授权测试

**已记录用户消息**: 24

## 会话目标演进

- 整理授权测试项目的已验证操作。

## 已验证结果

- 已完成真实验证。
""",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(SYNTHESIZE),
                "--vault-root",
                str(self.vault),
                "--project",
                "授权测试",
                "--long-term",
            ],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue((self.vault / "项目总结" / "授权测试.md").is_file())
        self.assertFalse((self.vault / "AI开发参考" / "授权测试.md").exists())
        self.assertIn("AI开发参考仍需用户明确授权", result.stdout)


if __name__ == "__main__":
    unittest.main()
