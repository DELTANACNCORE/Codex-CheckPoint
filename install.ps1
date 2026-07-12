$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Lite = $args[0] -eq "--lite"
$ModeText = if ($Lite) { "Lite（仅手动 /checkpoint）" } else { "Full（自动 hook + 手动 /checkpoint）" }
Write-Host "[checkpoint-codex] 安装模式: $ModeText"
$HookSrc = Join-Path $ScriptDir ".codex/hooks/checkpoint.py"
$PretoolSrc = Join-Path $ScriptDir ".codex/hooks/pretool.py"
$StopWrapperSrc = Join-Path $ScriptDir ".codex/hooks/stop-wrapper.py"
$RetrieveSrc = Join-Path $ScriptDir ".codex/hooks/retrieve.py"
$PretoolWrapperSrc = Join-Path $ScriptDir ".codex/hooks/pretool-wrapper.py"
$SkillSrc = if ($Lite) { Join-Path $ScriptDir ".codex/skills/checkpoint-lite" } else { Join-Path $ScriptDir ".codex/skills/checkpoint" }
$SearchSrc = Join-Path $ScriptDir ".codex/skills/search"
$SynthSrc = Join-Path $ScriptDir ".codex/skills/synthesize"
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$HookDstDir = Join-Path $CodexHome "hooks"
$HookDst = Join-Path $HookDstDir "checkpoint.py"
$PretoolDst = Join-Path $HookDstDir "pretool.py"
$StopWrapperDst = Join-Path $HookDstDir "stop-wrapper.py"
$RetrieveDst = Join-Path $HookDstDir "retrieve.py"
$PretoolWrapperDst = Join-Path $HookDstDir "pretool-wrapper.py"
$SkillDstDir = Join-Path $CodexHome "skills"
$SkillDst = Join-Path $SkillDstDir "checkpoint"
$SearchDst = Join-Path $SkillDstDir "search"
$SynthDst = Join-Path $SkillDstDir "synthesize"
$AgentsDst = Join-Path $CodexHome "AGENTS.md"
$HooksJson = Join-Path $CodexHome "hooks.json"
$ConfigToml = Join-Path $CodexHome "config.toml"
$DefaultVault = Join-Path $HOME "obsidian/知识库"

if (-not (Test-Path $HookSrc)) {
  Write-Error "[checkpoint-codex] 找不到 hook 脚本: $HookSrc"
  exit 1
}
if (-not (Test-Path $PretoolSrc)) {
  Write-Error "[checkpoint-codex] 找不到 PreToolUse 脚本: $PretoolSrc"
  exit 1
}
if (-not (Test-Path $StopWrapperSrc)) {
  Write-Error "[checkpoint-codex] 找不到 Stop wrapper: $StopWrapperSrc"
  exit 1
}
if (-not (Test-Path $RetrieveSrc)) {
  Write-Error "[checkpoint-codex] 找不到检索 hook: $RetrieveSrc"
  exit 1
}
if (-not (Test-Path $PretoolWrapperSrc)) {
  Write-Error "[checkpoint-codex] 找不到 PreTool wrapper: $PretoolWrapperSrc"
  exit 1
}

Write-Host ""
$Vault = Read-Host "你的 Obsidian vault 路径 [默认: $DefaultVault]"
if ([string]::IsNullOrWhiteSpace($Vault)) {
  $Vault = $DefaultVault
}

New-Item -ItemType Directory -Force -Path $HookDstDir | Out-Null
New-Item -ItemType Directory -Force -Path $SkillDstDir | Out-Null
Copy-Item $HookSrc $HookDst -Force
Copy-Item $PretoolSrc $PretoolDst -Force
Copy-Item $StopWrapperSrc $StopWrapperDst -Force
Copy-Item $RetrieveSrc $RetrieveDst -Force
Copy-Item $PretoolWrapperSrc $PretoolWrapperDst -Force
if (Test-Path $SkillDst) {
  Remove-Item $SkillDst -Recurse -Force
}
Copy-Item $SkillSrc $SkillDst -Recurse -Force
if (Test-Path $SearchSrc) {
  if (Test-Path $SearchDst) {
    Remove-Item $SearchDst -Recurse -Force
  }
  Copy-Item $SearchSrc $SearchDst -Recurse -Force
}
if (Test-Path $SynthSrc) {
  if (Test-Path $SynthDst) {
    Remove-Item $SynthDst -Recurse -Force
  }
  Copy-Item $SynthSrc $SynthDst -Recurse -Force
}

if (-not (Test-Path $AgentsDst)) {
  @"
# Codex Checkpoint Guide

## 回答前优先检索知识库

在回答技术、方案、配置、运维、开发类问题之前，优先检索：

1. 从用户问题提取 1-3 个关键词
2. 先读取 `$Vault/长期经验总结/` 中与当前任务相关的经验，再搜索项目总结和会话断点
3. 优先读取最相关的 1-2 篇已有文档
4. 已有结论直接复用，只补充新的差异

## 方案归档

方案敲定后，优先把文档写到：

`$Vault/项目总结/<项目名>/<方案标题>.md`

建议 frontmatter：

```yaml
---
date: YYYY-MM-DD
project: 项目名
tags: [codex/方案, ...]
---
```

## 会话断点

- Full 模式：Stop hook 自动写断点
- Lite 模式：手动运行 checkpoint skill
- 项目目录有真实产出时，会同步刷新项目总结和长期经验总结
"@ | Set-Content $AgentsDst -Encoding UTF8
  Write-Host "[checkpoint-codex] 已创建全局 AGENTS 模板: $AgentsDst"
} else {
  Write-Host "[checkpoint-codex] 检测到已有 AGENTS.md，跳过创建"
}

$data = @{}
if (Test-Path $HooksJson) {
  try {
    $data = Get-Content $HooksJson -Raw | ConvertFrom-Json -AsHashtable
  } catch {
    $data = @{}
  }
}
if (-not $data.ContainsKey("hooks")) {
  $data["hooks"] = @{}
}
$data["hooks"]["Stop"] = if ($data["hooks"].ContainsKey("Stop")) { $data["hooks"]["Stop"] } else { @() }
$data["hooks"]["PreToolUse"] = if ($data["hooks"].ContainsKey("PreToolUse")) { $data["hooks"]["PreToolUse"] } else { @() }
$data["hooks"]["UserPromptSubmit"] = if ($data["hooks"].ContainsKey("UserPromptSubmit")) { $data["hooks"]["UserPromptSubmit"] } else { @() }
$filtered = @()
foreach ($entry in $data["hooks"]["Stop"]) {
  $keep = $true
  foreach ($hook in $entry.hooks) {
    if ($hook.command -like "*checkpoint.py*" -or $hook.command -like "*codex-hook.js*" -or $hook.command -like "*stop-wrapper.py*" -or $hook.command -like "*probe-hook.py*") {
      $keep = $false
    }
  }
  if ($keep) {
    $filtered += $entry
  }
}
if (-not $Lite) {
  $filtered += @{
    hooks = @(
      @{
        type = "command"
        command = "python3 $StopWrapperDst --vault-root $Vault"
        timeout = 30
      }
    )
  }
}
$data["hooks"]["Stop"] = $filtered
$preFiltered = @()
foreach ($entry in $data["hooks"]["PreToolUse"]) {
  $keep = $true
  foreach ($hook in $entry.hooks) {
    if ($hook.command -like "*pretool.py*" -or $hook.command -like "*codex-hook.js*" -or $hook.command -like "*pretool-wrapper.py*" -or $hook.command -like "*probe-hook.py*") {
      $keep = $false
    }
  }
  if ($keep) {
    $preFiltered += $entry
  }
}
$preFiltered += @{
  hooks = @(
    @{
      type = "command"
      command = "python3 $PretoolWrapperDst --vault-root $Vault"
      timeout = 30
    }
  )
}
$data["hooks"]["PreToolUse"] = $preFiltered
$upsFiltered = @()
foreach ($entry in $data["hooks"]["UserPromptSubmit"]) {
  $keep = $true
  foreach ($hook in $entry.hooks) {
    if ($hook.command -like "*checkpoint.py*" -or $hook.command -like "*codex-hook.js*" -or $hook.command -like "*stop-wrapper.py*" -or $hook.command -like "*probe-hook.py*") {
      $keep = $false
    }
  }
  if ($keep) {
    $upsFiltered += $entry
  }
}
$upsFiltered = if ($Lite) {
  $upsFiltered
} else {
  @(
    @{
      hooks = @(
        @{
          type = "command"
          command = "python3 $StopWrapperDst --vault-root $Vault"
          timeout = 30
        }
      )
    }
  ) + $upsFiltered
}
$data["hooks"]["UserPromptSubmit"] = $upsFiltered
$data | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $HooksJson

Write-Host "[checkpoint-codex] 安装完成"
if ($Lite) {
  Write-Host "[checkpoint-codex] Lite 模式已清理 Stop / UserPromptSubmit 自动写入"
} else {
  Write-Host "[checkpoint-codex] Stop hook 已写入 $HooksJson"
}
Write-Host "[checkpoint-codex] PreToolUse hook 已写入 $HooksJson"
Write-Host "[checkpoint-codex] /checkpoint skill 已装到 $SkillDst"
if (Test-Path $SearchSrc) {
  Write-Host "[checkpoint-codex] search 可执行 skill 已装到 $SearchDst"
}
if (Test-Path $SynthSrc) {
  Write-Host "[checkpoint-codex] synthesize 可执行 skill 已装到 $SynthDst"
}
Write-Host "[checkpoint-codex] checkpoint.py 手动执行链路已经验证"
Write-Host "[checkpoint-codex] checkpoint skill 已切到 $(if ($Lite) { 'Lite' } else { 'Full' }) 版本"
Write-Host "[checkpoint-codex] 全局 AGENTS 模板: $AgentsDst"
Write-Host "[checkpoint-codex] slash 直调当前没有完成验证，稳定方式仍然是按 skill 调脚本"
Write-Host "[checkpoint-codex] 当前版本仅支持 Codex，本地解析 rollout，不调用第三方模型服务"
