# 参与贡献 / Contributing

修改应限定在 Codex 和已记录的 checkpoint 工作流范围内。不要提交 vault 内容、rollout 文件、hook 日志、API 密钥、令牌或机器特定配置。

Keep changes scoped to Codex and the documented checkpoint workflow. Do not commit vault content, rollout files, hook logs, API keys, tokens, or machine-specific configuration.

提交 Pull Request 前运行以下检查。

Run these checks before opening a pull request.

```bash
python3 -m py_compile .codex/hooks/*.py .codex/skills/*/*.py
bash -n install.sh uninstall.sh pack.sh unpack.sh
```

说明受影响的模式，Full 或 Lite，并附上用于验证变更的命令或 hook 事件。

Describe the affected mode, Full or Lite, and include the command or hook event used to verify the change.
