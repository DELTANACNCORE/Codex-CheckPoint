$ErrorActionPreference = "Stop"

param(
  [string]$Archive = ""
)

if (-not $Archive -or -not (Test-Path $Archive)) {
  Write-Host "用法 / Usage: .\unpack.ps1 <checkpoint-codex-migrate-xxx.tar.gz>"
  exit 1
}

$Vault = $env:OBSIDIAN_VAULT
if (-not $Vault) {
  $Default = Join-Path $HOME "obsidian\知识库"
  $Vault = Read-Host "Obsidian vault 路径 / path [默认 / default: $Default]"
  if (-not $Vault) { $Vault = $Default }
}

Write-Host "[unpack-codex] 知识库 / vault -> $Vault"
New-Item -ItemType Directory -Force -Path $Vault | Out-Null
tar -xzf $Archive -C $Vault --exclude=.codex/* 2>$null
Write-Host "[unpack-codex]   工作记录、项目总结与首页已恢复 / records, summaries, and homepage restored"

Write-Host "[unpack-codex] 会话记录 / sessions -> $HOME\.codex\"
New-Item -ItemType Directory -Force -Path (Join-Path $HOME ".codex") | Out-Null
tar -xzf $Archive -C $HOME .codex/sessions/ 2>$null
Write-Host "[unpack-codex]   sessions 已恢复 / restored"

Write-Host ""
Write-Host "[unpack-codex] 完成。接下来 / Complete. Next:"
Write-Host "  git clone https://github.com/DELTANACNCORE/Codex-CheckPoint.git"
Write-Host "  cd Codex-CheckPoint"
Write-Host "  bash .\install.sh"
