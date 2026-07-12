## 摘要 / Summary

说明用户可见行为和受影响的 Codex 工作流。

Describe the user-visible behavior and the affected Codex workflow.

## 验证 / Verification

- [ ] `python3 -m py_compile .codex/hooks/*.py .codex/skills/*/*.py`
- [ ] `bash -n install.sh uninstall.sh pack.sh unpack.sh`
- [ ] 已验证相关 hook、skill 或隔离 vault 行为 / Relevant hook, skill, or isolated vault behavior was verified

## 数据边界 / Data Boundary

- [ ] 不包含 vault 内容、rollout 文件、日志、令牌或机器特定路径 / No vault content, rollout files, logs, tokens, or machine-specific paths are included
