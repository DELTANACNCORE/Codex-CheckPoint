---
name: verify
description: |
  在当前环境重新执行测试、检查与诊断，再判断历史知识结论是否仍然有效。
  Re-run tests, checks, and diagnostics against the current environment before accepting historical knowledge conclusions.
---

# Verify Skill
*验证与诊断 Skill*

历史断点、项目总结和 AI开发参考只能提供检查线索，不能作为当前状态的证据。用户要求测试、验证、检查、诊断、排查或复测时，先读取必要的历史结论，再在当前环境执行对应命令或检查。

Historical checkpoints, project summaries, and AI development references provide investigation leads only. When the user asks to test, verify, check, diagnose, troubleshoot, or retest, read the necessary historical conclusion and then run the relevant command or inspection in the current environment.

## 执行规则
*Execution Rules*

确认当前工作目录、服务状态、配置版本和依赖条件。历史命令需要按当前路径、容器名称、版本和权限重新核对后才能执行。

Confirm the current working directory, service state, configuration version, and prerequisites. Re-check historical commands against current paths, container names, versions, and permissions before running them.

实际执行测试、健康检查、构建、状态查询或诊断命令。结果与历史结论不一致时，以当前命令输出为准，并说明差异。

Run the actual test, health check, build, status query, or diagnostic command. When results differ from the historical conclusion, use the current command output as the source of truth and state the difference.

## 命令入口
*Command Runner*

需要统一记录当前验证证据时，可使用 `verify.py` 执行用户明确指定的命令。脚本只运行传入的 `--command`，输出会脱敏；`--dry-run` 仅展示将执行的命令。它不会根据历史断点自行选择命令，也不会写入 Vault。

Use `verify.py` to record current verification evidence for commands explicitly supplied by the user. It runs only the provided `--command` values and redacts output; `--dry-run` shows commands without running them. It does not select commands from history or write to the vault.

```bash
python3 ~/.codex/skills/verify/verify.py \
  --cwd <项目目录> \
  --command "python3 -m unittest discover -s tests -v"
```

缺少可执行条件、访问权限或安全确认时，明确说明验证未完成的原因，不把历史“已验证”标记视为当前通过。

When executable prerequisites, access, or safety approval are absent, state why verification remains incomplete. A historical “verified” label does not establish a current pass.

## 输出
*Output*

- 已执行的命令或检查项目。\
  Commands or checks actually executed.
- 当前结果与历史结论的比较。\
  Comparison between current results and historical conclusions.
- 未完成验证的具体阻塞条件。\
  Concrete blocking condition for any incomplete verification.

## 已验证范围
*Verified Scope*

该 skill 提供验证行为边界；实际命令由当前任务、运行环境和用户授权决定。

This skill defines verification behavior boundaries. Actual commands depend on the current task, environment, and user authorization.
