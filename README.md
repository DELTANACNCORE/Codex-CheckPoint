# Codex CheckPoint / Codex 会话断点

当前 `main` 分支在 Codex 会话结束时自动生成可恢复的 Obsidian 断点，并同步每日索引、知识库首页与涉及项目的简短状态。

The current `main` branch writes a recoverable Obsidian checkpoint when a Codex session ends and refreshes the daily index, vault homepage, and concise status for affected projects.

## 上游与署名 / Upstream and Attribution

本项目基于 [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder/checkpoint) 的原始实现，原始作者为 [hjm4839-coder](https://github.com/hjm4839-coder)。本仓库保留原始 MIT 许可证和 Git 历史，并改造成仅支持 Codex 的精简运行版本。

This project is based on [hjm4839-coder/checkpoint](https://github.com/hjm4839-coder) by [hjm4839-coder](https://github.com/hjm4839-coder). It retains the original MIT license and Git history while providing a compact Codex-only runtime.

## 日常使用 / Daily Use

1. 正常使用 Codex，Stop hook 会在会话结束时写入断点。 Use Codex normally; the Stop hook writes a checkpoint when the session ends.
2. 打开 `知识库首页.md` 或 `Codex工作记录/会话索引/` 查看最近会话。 Open `知识库首页.md` or `Codex工作记录/会话索引/` to review recent sessions.
3. 需要立即更新时调用 checkpoint skill。 Invoke the checkpoint skill when an immediate refresh is needed.
4. 接手项目时先读取 `项目总结/<项目名>/项目总结.md`，再打开最近断点。 When resuming a project, read `项目总结/<项目名>/项目总结.md` before opening the latest checkpoint.

## 功能 / Features

- 自动断点：Stop hook 按年月日写入 `Codex工作记录/会话断点/YYYY/MM/DD/`。 Automatic checkpoints: the Stop hook writes to `Codex工作记录/会话断点/YYYY/MM/DD/`.
- 线程标题优先：断点优先采用 Codex 线程标题。 Thread-title first: checkpoints prefer the Codex thread title.
- 每日索引与首页：自动维护每日会话索引和知识库首页。 Daily index and homepage: both are refreshed automatically.
- 项目状态：会话写入 `项目总结/<项目名>/` 时刷新该项目的简短状态。 Project status: writes under `项目总结/<项目名>/` refresh that project's concise status.
- 精简运行边界：仓库只包含自动断点、每日索引、首页和项目状态。 Compact runtime boundary: the repository contains only automatic checkpoints, daily indexes, the homepage, and project status.

## 配置 / Setup

前提：已安装 Codex、Python 3 和 Obsidian vault。将 hook 与 skill 复制到 `~/.codex`，并在 `~/.codex/hooks.json` 注册 Stop hook。

Prerequisites: Codex, Python 3, and an Obsidian vault. Copy the hook and skill into `~/.codex`, then register the Stop hook in `~/.codex/hooks.json`.

```bash
git clone https://github.com/DELTANACNCORE/Codex-CheckPoint.git
cd Codex-CheckPoint
mkdir -p ~/.codex/hooks ~/.codex/skills
cp .codex/hooks/checkpoint.py ~/.codex/hooks/checkpoint.py
cp -R .codex/skills/checkpoint ~/.codex/skills/checkpoint
chmod +x ~/.codex/hooks/checkpoint.py
```

在 `~/.codex/hooks.json` 中按以下结构加入 Stop hook，并将 vault 路径替换为你的实际路径。

Add the Stop hook to `~/.codex/hooks.json` with the following structure, replacing the vault path with your actual path.

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.codex/hooks/checkpoint.py --vault-root ~/obsidian/知识库",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Codex 配置还需要在 `~/.codex/config.toml` 的 `[features]` 下启用 `hooks = true`。

Codex also requires `hooks = true` under `[features]` in `~/.codex/config.toml`.

## 目录结构 / Repository Layout

```text
.codex/
├── hooks/
│   └── checkpoint.py
└── skills/
    └── checkpoint/
        └── SKILL.md
```

```text
vault/
├── 知识库首页.md
├── 项目总结/<项目名>/项目总结.md
└── Codex工作记录/
    ├── 会话索引/YYYY-MM-DD.md
    └── 会话断点/YYYY/MM/DD/<session-id>.md
```

## 许可证 / License

[MIT](./LICENSE)
