# Contributing

Keep changes scoped to Codex and the documented checkpoint workflow. Do not commit vault content, rollout files, hook logs, API keys, tokens, or machine-specific configuration.

Before opening a pull request, run:

```bash
python3 -m py_compile .codex/hooks/*.py .codex/skills/*/*.py
bash -n install.sh uninstall.sh pack.sh unpack.sh
```

Describe the affected mode, Full or Lite, and include the verification command or hook event used for the change.
