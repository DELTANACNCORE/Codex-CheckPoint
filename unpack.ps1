$ErrorActionPreference = "Stop"

param(
  [string]$Archive = ""
)

if (-not $Archive -or -not (Test-Path $Archive)) {
  Write-Host "用法: .\unpack.ps1 <checkpoint-codex-migrate-xxx.tar.gz>"
  exit 1
}

$Vault = $env:OBSIDIAN_VAULT
if (-not $Vault) {
  $Default = Join-Path $HOME "obsidian\知识库"
  $Vault = Read-Host "Obsidian vault 路径 [默认: $Default]"
  if (-not $Vault) { $Vault = $Default }
}

Write-Host "[unpack-codex] 知识库 -> $Vault"
New-Item -ItemType Directory -Force -Path $Vault | Out-Null
tar -xzf $Archive -C $Vault --exclude=.codex/* 2>$null
Write-Host "[unpack-codex]   工作记录、项目总结与首页 ok"

Write-Host "[unpack-codex] sessions -> $HOME\.codex\"
New-Item -ItemType Directory -Force -Path (Join-Path $HOME ".codex") | Out-Null
tar -xzf $Archive -C $HOME .codex/sessions/ 2>$null
Write-Host "[unpack-codex]   sessions ok"

Write-Host ""
Write-Host "[unpack-codex] 完成。接下来："
Write-Host "  git clone https://github.com/hjm4839-coder/checkpoint.git"
Write-Host "  cd checkpoint"
Write-Host "  bash .\install.sh"
