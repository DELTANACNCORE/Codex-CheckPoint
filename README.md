# Checkpoint

为 Codex 保存可恢复的 Obsidian 会话断点。项目会维护会话索引、项目总结、长期经验和新任务恢复包，减少重新读取完整 rollout 的需求。

## 功能

- Codex Full 模式通过 Stop 与 UserPromptSubmit hook 自动维护知识库，本地解析 rollout。
- Codex Lite 模式保留手动 checkpoint，由调用时提供标题和标签，不启用自动写入。
- 五次有效来回对话后生成恢复断点；短会话只写入每日索引。
- 项目材料写入 `项目总结/`，跨项目经验写入 `长期经验总结/`。
- 新任务优先读取相关长期经验、项目总结和恢复断点。

## Codex 安装

前提：Codex 已初始化，Python 3 可用，`~/.codex/config.toml` 已启用 `hooks = true`。

```bash
git clone https://github.com/hjm4839-coder/checkpoint.git
cd checkpoint
bash ./install.sh
```

Lite 模式：

```bash
bash ./install.sh --lite
```

安装时输入 Obsidian vault 路径。默认路径为 `~/obsidian/知识库`。Full 模式会安装 checkpoint、检索、PreToolUse 与 Stop wrapper；Lite 模式只保留手动 checkpoint 与 PreToolUse。

断点、索引与摘要均在本地从 Codex rollout 和已有知识文档提取，不调用第三方模型服务。

## Codex 知识库结构

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

`按重启事项继续` 会从知识库首页的重启区读取默认恢复断点。手动 checkpoint、搜索和合成通过已安装 skill 调用本地脚本；Codex 桌面端的 slash 命令识别尚无稳定验证。

## 安全与数据边界

不要提交 Obsidian vault、会话 rollout、hook 日志、迁移归档、API 密钥、访问令牌或个人项目文件。`.gitignore` 已覆盖常见运行数据，提交前仍应检查 `git status` 和暂存区。

漏洞披露见 [SECURITY.md](./SECURITY.md)，贡献约定见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## License

[MIT](./LICENSE)
