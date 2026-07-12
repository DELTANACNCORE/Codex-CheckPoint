# Codex CheckPoint V0.5.5 / Codex 会话断点 V0.5.5

为 Codex 与 Obsidian 提供会话断点、持续恢复、项目总结和知识检索。仓库只包含运行时 hook、skills、README、许可证和忽略规则，不包含安装、迁移、打包或解包脚本。

Session checkpoints, continuous recovery, project summaries, and knowledge retrieval for Codex and Obsidian. This repository contains only runtime hooks, skills, the README, license, and ignore rules. It does not include installation, migration, packing, or unpacking scripts.

## 上游与署名 / Upstream and Attribution

本项目基于 [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint)，原始作者为 [hjm4839-coder](https://github.com/hjm4839-coder)。本仓库保留原始 MIT 许可证和 Git 历史，并改造成仅支持 Codex 的实现。

This project is based on [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint) by [hjm4839-coder](https://github.com/hjm4839-coder). It retains the original MIT license and Git history while adapting the workflow exclusively for Codex.

## 功能 / Features

- 自动断点：会话结束时按日期写入 `Codex工作记录/会话断点/YYYY/MM/DD/`。 Automatic checkpoints: sessions are written by date under `Codex工作记录/会话断点/YYYY/MM/DD/`.
- 持续更新：有效对话达到阈值后，在新用户消息时刷新断点。 Continuous updates: a checkpoint is refreshed when a new user message arrives after the meaningful-round threshold.
- 恢复注入：新任务可读取相关断点、项目总结和长期经验的短摘要；复用长期经验时，Codex 会先向用户说明文档来源。 Recovery injection: new tasks can receive compact context from relevant checkpoints, project summaries, and reusable experience; Codex announces the document before reusing long-term experience.
- 项目总结：独立项目固定写入 `项目总结/<项目名>.md`，同一会话涉及多个独立项目时合并为一篇并记录 `session_ids`。父项目目录需要用户明确确认归属关系。 Project summaries: independent projects use `项目总结/<项目名>.md`; multiple independent projects in one session are merged into one note with `session_ids`. Parent-project directories require explicit user confirmation.
- 长期经验：每次 `synthesize` 都会归档项目总结，并按会话长度提示是否值得提炼长期经验。只有用户明确授权或强制要求时才写入 `长期经验总结/<项目名>.md`；有效材料类别不足三类时必须再次询问。自动 hook 不会创建、覆盖或删除长期经验。 Long-term experience: every `synthesize` run archives the project summary and uses session length to recommend extraction. `长期经验总结/<项目名>.md` is written only with explicit user authorization or a forced request; fewer than three useful material categories requires another user decision. Automatic hooks never create, replace, or delete long-term experience.
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
# 将 .codex/AGENTS.md 的规则合并到 ~/.codex/AGENTS.md，保留已有本地规则。
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

## 交给 Codex 安装 / Ask Codex to Install

可以把下面整段提示词发送给另一端 Codex。它需要终端写入权限，因为会修改该机器的 `~/.codex/`；没有明确 vault 路径时，它应先询问路径，不能猜测或覆盖已有配置。

Send the complete prompt below to another Codex instance. It needs terminal write permission because it modifies that machine's `~/.codex/`. When the vault path is unknown, it must ask first and must not guess or overwrite existing configuration.

```text
请安装 Codex CheckPoint：
https://github.com/DELTANACNCORE/Codex-CheckPoint.git

目标是为当前机器启用完整的 Codex + Obsidian 知识库工作流。

1. 询问 Obsidian vault 路径；如果没有明确路径，不要继续。
2. 克隆仓库到临时工作目录或用户指定目录。
3. 将仓库 .codex/hooks/*.py 复制到 ~/.codex/hooks/。
4. 将 checkpoint、search、synthesize 复制到 ~/.codex/skills/。
5. 确保 ~/.codex/config.toml 的 [features] 包含 hooks = true。
6. 读取并保留 ~/.codex/hooks.json 中已有的非本项目 hook；注册以下三个 hook：
   - Stop: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - UserPromptSubmit: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - PreToolUse: python3 ~/.codex/hooks/pretool-wrapper.py --vault-root <vault-path>
7. 将仓库 .codex/AGENTS.md 的项目归档规则合并到 ~/.codex/AGENTS.md，保留已有本地规则。
8. 为复制后的 hook 添加可执行权限。
9. 运行 python3 ~/.codex/hooks/checkpoint.py --vault-root <vault-path> --force 进行验证。
10. 报告 hooks.json 的实际修改、写入的断点路径和验证结果。不要输出令牌、rollout 内容或私有 vault 内容。
```

```text
Install Codex CheckPoint:
https://github.com/DELTANACNCORE/Codex-CheckPoint.git

Enable the complete Codex and Obsidian knowledge workflow on this machine.

1. Ask for the Obsidian vault path. Do not continue without an explicit path.
2. Clone the repository into a temporary directory or a user-selected directory.
3. Copy .codex/hooks/*.py into ~/.codex/hooks/.
4. Copy checkpoint, search, and synthesize into ~/.codex/skills/.
5. Ensure [features] in ~/.codex/config.toml contains hooks = true.
6. Read and preserve unrelated hooks in ~/.codex/hooks.json, then register these hooks:
   - Stop: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - UserPromptSubmit: python3 ~/.codex/hooks/stop-wrapper.py --vault-root <vault-path>
   - PreToolUse: python3 ~/.codex/hooks/pretool-wrapper.py --vault-root <vault-path>
7. Merge the project-archiving rules from .codex/AGENTS.md into ~/.codex/AGENTS.md while preserving existing local rules.
8. Add executable permission to copied hook files.
9. Verify with python3 ~/.codex/hooks/checkpoint.py --vault-root <vault-path> --force.
10. Report the actual hooks.json changes, checkpoint path, and verification result. Do not expose tokens, rollout content, or private vault content.
```

## 日常使用 / Daily Use

1. 正常使用 Codex，hook 会持续维护断点。 Use Codex normally; hooks maintain checkpoints continuously.
2. 打开 `知识库首页.md` 或 `Codex工作记录/会话索引/` 回顾最近会话。 Open `知识库首页.md` or `Codex工作记录/会话索引/` to review recent sessions.
3. 需要立即刷新当前断点时调用 checkpoint skill。 Invoke the checkpoint skill to refresh the current checkpoint immediately.
4. 需要查找知识时调用 search skill；需要跨会话整理时调用 synthesize skill。 Invoke search to find knowledge and synthesize to consolidate related sessions.
5. 接手项目时优先读取 `项目总结/<项目名>.md`；已确认的父项目才读取 `项目总结/<父项目>/项目总结.md`。 When resuming a project, read `项目总结/<项目名>.md` first; read `项目总结/<父项目>/项目总结.md` only for confirmed parent projects.
6. 需要长期经验时明确调用 `synthesize` 并授权写入；普通 checkpoint 不会生成该文件。 Explicitly invoke `synthesize` and authorize the write for long-term experience; ordinary checkpoints never generate it.

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
├── 长期经验总结/<项目名>.md
├── 项目总结/<项目名>.md
└── Codex工作记录/
    ├── 会话索引/YYYY-MM-DD.md
    └── 会话断点/YYYY/MM/DD/<主题>.md
```

## 项目归档规则 / Project Archiving Rules

独立项目只保留一份 `项目总结/<项目名>.md`。用户提到“归档到同一项目”或“放到父项目”时，Codex 必须询问该项目是否归属于该父项目；得到明确确认后，才可创建 `项目总结/<父项目>/`，并在其 `项目总结.md` 标记 `group_confirmed: true`。没有归属关系的多个项目在同一次会话中合并为一篇项目总结，并将所有会话标识写入 `session_ids`。

An independent project keeps one `项目总结/<项目名>.md`. When a user asks to archive work under the same or a parent project, Codex must ask whether the project belongs to that parent. Only an explicit confirmation permits `项目总结/<父项目>/`, whose `项目总结.md` must contain `group_confirmed: true`. Unrelated projects from one session are merged into one project summary with all session identifiers in `session_ids`.

## 许可证 / License

[MIT](./LICENSE)
