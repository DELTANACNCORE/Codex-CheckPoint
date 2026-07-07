# 会话断点 (checkpoint)

把 Claude Code 每次会话自动沉淀成「断点笔记」——主题命名、状态 triage、标签分类、可恢复。写入磁盘 markdown，配 Obsidian 可变成可交互知识库（推荐安装，不装也能用）。

会话结束 → Stop hook 自动生成断点 + 更新每日索引。`claude --resume <id>` 恢复接着干。

> **当前仅支持 Claude Code**。依赖 Claude Code hooks（Stop/PreToolUse）机制，暂不兼容其他 AI 编程工具（Cursor/Windsurf/Codex CLI 等）。欢迎社区的适配 PR。

## 功能

- **自动**：会话结束自动生成断点笔记（任意目录启动 claude 都生效）
- **主题命名**：LLM 综合整次会话提问 → ≤20 字主题，作文件名
- **状态 triage**：✅ completed / ⚠️ interrupted / 📋 incomplete_archive（讨论了方案但没归档）
- **大小类标签**：`category` 1-2 个大类（如 技术开发、运维管理），`tags` 2-4 个小类（如 前端/Vue、shell/Netplan），`keywords` 1-3 个精确搜索词。三字段由 LLM 一次调用产出
- **方案归档闭环**：方案写入 `Claude方案/<项目名>/` 后断点自动变 ✅，产出列链接方案
- **Bases 视图**：按标签/状态/项目/关键词筛选分组
- **恢复提醒**：⚠️/📋 会话带 `claude --resume <id>` 命令
- **知识库首页**：自动刷新仪表盘（断点总数/待恢复/热门标签）
- **会话关联**：同一标签会话自动 wikilink 互连，形成知识链
- **PreToolUse 提醒**：写 `Claude方案/` 文件时自动提醒已有相关文档，避免重复
- **知识合成**：`/synthesize` 将同类断点提炼成知识文档
- **LLM 兜底**：模型异常时从文件路径自动提取标签，不全空

## 安装

**macOS / Linux**
```bash
git clone <仓库地址> ~/obsidian   # 或任意位置
cd ~/obsidian

# Full 模式（自动 Stop hook，推荐）
./install.sh

# 或 Lite 模式（仅手动 /checkpoint，不额外调 API）
./install.sh --lite
```

**Windows（PowerShell）**
```powershell
git clone <仓库地址> $env:USERPROFILE\obsidian
cd $env:USERPROFILE\obsidian

# Full 模式
powershell -ExecutionPolicy Bypass -File .\install.ps1

# 或 Lite 模式
powershell -ExecutionPolicy Bypass -File .\install.ps1 --lite
```

`install.sh` / `install.ps1` 会：
- 把 Stop hook + PreToolUse hook 注册到 `~/.claude/settings.json`（用户级，任意目录生效）
- 装 `/checkpoint` + `/synthesize` skill
- 写 OBSIDIAN_VAULT 到 env
- 创建 `~/.claude/CLAUDE.md`（若不存在，含归档约定+知识检索指令）
- 备份原配置到 `.bak`
- 幂等：重复运行不重复注册
- **不动**你已有的 env / API 凭证 / 其他 hook

### 两种模式

| | Full（默认） | Lite |
|---|---|---|
| **自动 Stop hook** | ✅ 会话结束自动生成断点 | ❌ |
| **手动 /checkpoint** | ✅ 脚本调 LLM 起标题/标签 | ✅ **对话模型**生成标题/标签 |
| **额外 API 调用** | 每次 Stop hook 1 次 | **0** |
| **标签/关键词** | LLM 动态生成（2-5 标签 + 1-3 关键词） | Claude 在对话中生成 |
| **适合** | 有 API 凭证、要自动化 | 不想额外调 API、只要手动管家 |

Lite 版 `/checkpoint` 用**当前对话模型**（你已经在对话中用的那个）分析会话内容，起标题、打标签，传给脚本写笔记——全程不额外调 LLM。

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

**没有 API 凭证也能用**：机制本身（断点/索引/状态/恢复）纯本地逻辑，照常跑。只是主题用最长提问代替、标签为空。

## 目录结构（安装后）

```
你的 Obsidian vault/Claude方案/
├── 会话索引/            # 每日索引 YYYY-MM-DD.md
├── 会话断点/            # 单条断点笔记 <主题>.md
└── <项目名>/            # 归档方案
```

`会话断点.base` 是 Bases 视图，放 `Claude方案/` 根目录。

## 自定义

- **标签**：标签完全动态，无需自定义。如需改标签生成 prompt，改 `.claude/hooks/checkpoint.py` 里的 `synthesize_topic_and_tags` 函数
- **vault 路径**：设 `OBSIDIAN_VAULT` env
- **手动触发**：会话里输入 `/checkpoint`（skill）

## 卸载

```bash
./uninstall.sh            # macOS / Linux
# 或
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1   # Windows
```

会自动清理：
- hooks.Stop 中 checkpoint 条目
- hooks.PreToolUse 中 pretool 条目
- `/checkpoint` + `/synthesize` skill
- env.OBSIDIAN_VAULT（若同批安装）
- 配置备份文件

断点笔记和每日索引**不删除**（留档），如需彻底清空手动删 `Claude方案/会话断点/` 和 `Claude方案/会话索引/`。
