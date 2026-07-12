# Codex CheckPoint / Codex 会话断点

为 Codex 与 Obsidian 提供会话断点、持续恢复、项目总结和知识检索。仓库只包含运行时 hook、skills、README、许可证和忽略规则，不包含安装、迁移、打包或解包脚本。

Session checkpoints, continuous recovery, project summaries, and knowledge retrieval for Codex and Obsidian. This repository contains only runtime hooks, skills, the README, license, and ignore rules. It does not include installation, migration, packing, or unpacking scripts.

## 上游与署名 / Upstream and Attribution

本项目基于 [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint)，原始作者为 [hjm4839-coder](https://github.com/hjm4839-coder)。本仓库保留原始 MIT 许可证和 Git 历史，并改造成仅支持 Codex 的实现。

This project is based on [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint) by [hjm4839-coder](https://github.com/hjm4839-coder). It retains the original MIT license and Git history while adapting the workflow exclusively for Codex.

## 功能 / Features

- 自动断点：会话结束时按日期写入 `Codex工作记录/会话断点/YYYY/MM/DD/`。 Automatic checkpoints: sessions are written by date under `Codex工作记录/会话断点/YYYY/MM/DD/`.
- 持续更新：有效对话达到阈值后，在新用户消息时刷新断点。 Continuous updates: a checkpoint is refreshed when a new user message arrives after the meaningful-round threshold.
- 恢复注入：新任务可读取相关断点、项目总结和长期经验的短摘要。 Recovery injection: new tasks can receive compact context from relevant checkpoints, project summaries, and reusable experience.
- 项目总结与长期经验：写入 `项目总结/<项目名>/` 时自动刷新滚动总结和跨项目经验。 Project summaries and reusable experience: writing under `项目总结/<项目名>/` refreshes rolling summaries and cross-project experience.
- 搜索与合成：保留本地 `search` 与 `synthesize` skills。 Search and synthesis: local `search` and `synthesize` skills remain available.
- PreTool 提醒：写入项目文档前提示已有相关材料。 PreTool reminder: project-document writes are checked against existing material.

## 配置 / Setup

前提：已安装 Codex、Python 3 和 Obsidian vault，并在 `~/.codex/config.toml` 的 `[features]` 下启用 `hooks = true`。

Prerequisites: Codex, Python 3, and an Obsidian vault. Enable `hooks = true` under `[features]` in `~/.codex/config.toml`.

```bash
git clone https://github.com/DELTANACNCORE/Codex-CheckPoint.git
cd Codex-CheckPoint
mkdir -p ~/.codex/hooks ~/.codex/skills
cp .codex/hooks/*.py ~/.codex/hooks/
cp -R .codex/skills/checkpoint ~/.codex/skills/checkpoint
cp -R .codex/skills/search ~/.codex/skills/search
cp -R .codex/skills/synthesize ~/.codex/skills/synthesize
chmod +x ~/.codex/hooks/*.py
```

将下列 hook 注册到 `~/.codex/hooks.json`，并将 vault 路径替换为实际路径。

Register the following hooks in `~/.codex/hooks.json`, replacing the vault path with the actual path.

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.codex/hooks/stop-wrapper.py --vault-root ~/obsidian/知识库",
        "timeout": 30
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.codex/hooks/stop-wrapper.py --vault-root ~/obsidian/知识库",
        "timeout": 30
      }]
    }],
    "PreToolUse": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.codex/hooks/pretool-wrapper.py --vault-root ~/obsidian/知识库",
        "timeout": 30
      }]
    }]
  }
}
```

## 日常使用 / Daily Use

1. 正常使用 Codex，hook 会持续维护断点。 Use Codex normally; hooks maintain checkpoints continuously.
2. 打开 `知识库首页.md` 或 `Codex工作记录/会话索引/` 回顾最近会话。 Open `知识库首页.md` or `Codex工作记录/会话索引/` to review recent sessions.
3. 需要立即刷新当前断点时调用 checkpoint skill。 Invoke the checkpoint skill to refresh the current checkpoint immediately.
4. 需要查找知识时调用 search skill；需要跨会话整理时调用 synthesize skill。 Invoke search to find knowledge and synthesize to consolidate related sessions.
5. 接手项目时优先读取 `项目总结/<项目名>/项目总结.md`。 When resuming a project, read `项目总结/<项目名>/项目总结.md` first.

## 目录结构 / Repository Layout

```text
.codex/
├── hooks/
│   ├── checkpoint.py
│   ├── pretool.py
│   ├── pretool-wrapper.py
│   ├── retrieve.py
│   └── stop-wrapper.py
└── skills/
    ├── checkpoint/
    ├── search/
    └── synthesize/
```

```text
vault/
├── 知识库首页.md
├── 长期经验总结/
├── 项目总结/<项目名>/
└── Codex工作记录/
    ├── 会话索引/YYYY-MM-DD.md
    └── 会话断点/YYYY/MM/DD/<主题>.md
```

## 许可证 / License

[MIT](./LICENSE)
