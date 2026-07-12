# Checkpoint

[![CI](https://github.com/DELTANACNCORE/Codex-CheckPoint/actions/workflows/ci.yml/badge.svg)](https://github.com/DELTANACNCORE/Codex-CheckPoint/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

为 Codex 保存可恢复的 Obsidian 会话断点，并维护会话索引、项目总结、长期经验和新任务恢复包，减少重新读取完整 rollout 的需求。

An Obsidian checkpoint workflow for Codex. It maintains session indexes, project summaries, reusable experience, and recovery briefs so later tasks can continue without reloading a full rollout.

## 上游与署名 / Upstream and Attribution

本项目基于 [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint) 的原始实现构建，原始作者为 [hjm4839-coder](https://github.com/hjm4839-coder)。`DELTANACNCORE/Codex-CheckPoint` 在保留原始 MIT 许可证和 Git 提交历史的基础上，完成了仅支持 Codex 的工作流改造。

This project is based on [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint) by [hjm4839-coder](https://github.com/hjm4839-coder). `DELTANACNCORE/Codex-CheckPoint` retains the original MIT license and Git history while adapting the workflow exclusively for Codex.

## 当前状态 / Current Status

适用于已启用 hooks 的 Codex 环境。核心断点、索引、检索与知识合成均在本地从 Codex rollout 和已有 Markdown 文档提取，不依赖第三方模型服务。

Designed for Codex environments with hooks enabled. Checkpoints, indexes, retrieval, and knowledge synthesis are derived locally from Codex rollouts and existing Markdown notes without third-party model services.

## 功能 / Features

- Full 模式通过 Stop、UserPromptSubmit 和 PreToolUse hook 自动维护知识库。Full mode automatically maintains the knowledge base through Stop, UserPromptSubmit, and PreToolUse hooks.
- Lite 模式保留手动 checkpoint，由调用时提供标题和标签，不启用自动写入。Lite mode keeps checkpointing manual, takes caller-provided titles and tags, and does not enable automatic writes.
- 五次有效来回对话后生成恢复断点，短会话只写入每日索引。A recovery brief is generated after five meaningful rounds; short sessions are recorded only in the daily index.
- 项目材料写入 `项目总结/`，跨项目经验写入 `长期经验总结/`。Project material is written to `项目总结/`, while cross-project experience is written to `长期经验总结/`.
- 新任务优先读取相关长期经验、项目总结和恢复断点。New tasks retrieve relevant experience, project summaries, and recovery briefs first.

## 安装 / Installation

前提：Codex 已初始化，Python 3 可用，`~/.codex/config.toml` 已启用 `hooks = true`。

Prerequisites: Codex is initialized, Python 3 is available, and `hooks = true` is enabled in `~/.codex/config.toml`.

```bash
git clone https://github.com/DELTANACNCORE/Codex-CheckPoint.git
cd Codex-CheckPoint
bash ./install.sh
```

Lite 模式 / Lite mode:

```bash
bash ./install.sh --lite
```

安装时输入 Obsidian vault 路径，默认路径为 `~/obsidian/知识库`。Full 模式会安装 checkpoint、检索、PreToolUse 与 Stop wrapper；Lite 模式只保留手动 checkpoint 与 PreToolUse。

Enter the Obsidian vault path during installation. The default is `~/obsidian/知识库`. Full mode installs checkpoint, retrieval, PreToolUse, and Stop wrappers; Lite mode keeps manual checkpointing and PreToolUse only.

## 知识库结构 / Vault Layout

```text
vault/
├── 知识库首页.md
├── 长期经验总结/
├── 项目总结/
├── Codex工作记录/
│   ├── 会话断点/
│   └── 会话索引/
└── Codex协同Obsidian工作流skill更新日志.md
```

`按重启事项继续` 会从知识库首页的重启区读取默认恢复断点。手动 checkpoint、搜索和合成通过已安装 skill 调用本地脚本；Codex 桌面端对 slash 直调的稳定支持仍未完成验证。

`按重启事项继续` reads the default recovery brief from the restart section of the vault homepage. Manual checkpointing, search, and synthesis run through installed local skills; stable native slash-command support in Codex Desktop is not yet verified.

## 安全与数据边界 / Security and Data Boundary

不要提交 Obsidian vault、会话 rollout、hook 日志、迁移归档、API 密钥、访问令牌或个人项目文件。`.gitignore` 已覆盖常见运行数据，提交前仍应检查 `git status` 和暂存区。

Do not commit an Obsidian vault, session rollouts, hook logs, migration archives, API keys, access tokens, or personal project files. `.gitignore` covers common runtime data, but always inspect `git status` and the staging area before committing.

漏洞披露见 [SECURITY.md](./SECURITY.md)，贡献约定见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

See [SECURITY.md](./SECURITY.md) for vulnerability reporting and [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidance.

## 许可证 / License

[MIT English](./LICENSE) · [中文说明 / Chinese reference](./LICENSE.zh-CN.md)
