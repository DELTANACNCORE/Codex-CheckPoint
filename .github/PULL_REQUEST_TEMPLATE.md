## Summary

Describe the user-visible behavior and the affected Codex workflow.

## Verification

- [ ] `python3 -m py_compile .codex/hooks/*.py .codex/skills/*/*.py`
- [ ] `bash -n install.sh uninstall.sh pack.sh unpack.sh`
- [ ] Relevant hook, skill, or isolated vault behavior was verified

## Data Boundary

- [ ] No vault content, rollout files, logs, tokens, or machine-specific paths are included
