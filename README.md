# 会话断点 (checkpoint)

把 Claude Code 每次会话自动沉淀成「断点笔记」——主题命名、状态 triage、标签分类、可恢复。写入磁盘 markdown，配 Obsidian 可变成可交互知识库（不装也能用，最好还是安装）。

会话结束 → Stop hook 自动生成断点 + 更新每日索引。`claude --resume <id>` 恢复接着干。

## 功能

- **自动**：会话结束自动生成断点笔记（任意目录启动 claude 都生效）
- **主题命名**：LLM 综合整次会话提问 → ≤20 字主题，作文件名
- **状态 triage**：✅ completed / ⚠️ interrupted / 📋 incomplete_archive（讨论了方案但没归档）
- **标签分类**：`tags` 固定三分类（产品 / 功能开发 / 日常问答）+ `keywords` 内容关键词
- **方案归档闭环**：方案写入 `Claude方案/<项目名>/` 后断点自动变 ✅，产出列链接方案
- **Bases 视图**：按标签/状态/项目/关键词筛选分组
- **恢复提醒**：⚠️/📋 会话带 `claude --resume <id>` 命令

## 安装

**macOS / Linux**
```bash
git clone <仓库地址> ~/obsidian   # 或任意位置
cd ~/obsidian
./install.sh
```

**Windows（PowerShell）**
```powershell
git clone <仓库地址> $env:USERPROFILE\obsidian
cd $env:USERPROFILE\obsidian
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

`install.sh` / `install.ps1` 会：
- 把 Stop hook 注册到你的 `~/.claude/settings.json`（用户级，任意目录生效）
- 备份原配置到 `.bak`
- 幂等：重复运行不重复注册
- **不动**你已有的 env / API 凭证 / 其他 hook

## 前置条件

- **Claude Code** 已装好（你的 API 凭证会被自动复用，无需额外配）
- **python3**（仅标准库，无需 pip install）
- **Obsidian**（可选，见下）

## 不装 Obsidian 也能用

核心机制只是往磁盘写 markdown 文件，**不依赖 Obsidian 这个 app**。把 `OBSIDIAN_VAULT` 指向任意文件夹即可：

```json
// ~/.claude/settings.json 的 env
"OBSIDIAN_VAULT": "/Users/你/任意文件夹"
```

不装 Obsidian 照样有：断点笔记、每日索引、状态 triage、标签/关键词（frontmatter）、`claude --resume` 恢复。

只是会丢：`.base` 视图（打不开）、wikilink 跳转（`[[...]]` 变纯文本）、标签面板/图谱。即从"可交互知识库"降级成"带索引的会话日志文件夹"，仍然完全可用。

装了 Obsidian 才有 Bases 视图按标签分组、点链接跳转、图谱看关联——体验更好，但非必需。

## API / 模型

脚本读 Claude Code 已有的 env 变量调 LLM 生成主题/标签，自动适配：

| 你的环境 | env 变量 | 鉴权 |
|---|---|---|
| 真 Anthropic Claude | `ANTHROPIC_API_KEY` | x-api-key → api.anthropic.com |
| 网关代理（Bearer 式） | `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` | Bearer → 你的网关 |
| 网关代理（x-api-key 式） | `ANTHROPIC_API_KEY` + `ANTHROPIC_BASE_URL` | x-api-key → 你的网关 |

**没有 API 凭证也能用**：机制本身（断点/索引/状态/恢复）纯本地逻辑，照常跑。只是主题用最长提问代替、无标签。

## 目录结构（安装后）

```
你的 Obsidian vault/Claude方案/
├── 会话索引/            # 每日索引 YYYY-MM-DD.md
├── 会话断点/            # 单条断点笔记 <主题>.md
└── <项目名>/            # 归档方案
```

`会话断点.base` 是 Bases 视图，放 `Claude方案/` 根目录。

## 自定义

- **标签**：改 `.claude/hooks/checkpoint.py` 里的 `ALLOWED_TAGS`（默认 `产品 / 功能开发 / 日常问答`）
- **vault 路径**：设 `OBSIDIAN_VAULT` env
- **手动触发**：会话里输入 `/checkpoint`（skill）

## 卸载

删 `~/.claude/settings.json` 里 `hooks.Stop` 中指向 `checkpoint.py` 的条目，或恢复 `.bak`。
