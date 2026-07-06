---
name: checkpoint
description: Save current session checkpoint to Obsidian. Triggered by /checkpoint.
---

# /checkpoint — Save session checkpoint

Write current Claude Code session checkpoint to Obsidian vault.

## Triggers

- `/checkpoint`

## Steps

### 1. Find transcript

```bash
ls -t ~/.claude/projects/-Users-ouyangkai-obsidian/*.jsonl | head -1
```

### 2. Get session ID

Check `~/.claude/sessions/` for the most recently modified JSON, or extract from transcript filename. Falls back to `manual-<timestamp>`.

### 3. Run

```bash
python3 ~/obsidian/.claude/hooks/checkpoint.py --transcript <path> --session-id <id>
```

### 4. Report

Show session status, outputs, and any warnings (interrupted / incomplete_archive).
