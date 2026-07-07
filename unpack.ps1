# checkpoint 知识库解包脚本 (Windows / PowerShell)
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

param(
    [string]$Archive = ""
)

if (-not $Archive -or -not (Test-Path $Archive)) {
    Write-Host "用法: .\unpack.ps1 <checkpoint-migrate-xxx.zip>"
    exit 1
}

$Settings = Join-Path $env:USERPROFILE ".claude\settings.json"
$Vault = $null
if (Test-Path $Settings) {
    try {
        $data = Get-Content $Settings -Raw -Encoding UTF8 | ConvertFrom-Json
        $Vault = $data.env.OBSIDIAN_VAULT
    } catch {}
}

if (-not $Vault) {
    $Default = Join-Path $env:USERPROFILE "obsidian\知识库"
    $Vault = Read-Host "Obsidian vault 路径 [默认: $Default]"
    if (-not $Vault) { $Vault = $Default }
}

Write-Host "[unpack] 知识库 -> $Vault"
New-Item -ItemType Directory -Force -Path $Vault | Out-Null
tar -xzf $Archive -C $Vault Claude方案/ 2>$null
Write-Host "[unpack]   Claude方案/  ok"

$Dash = Join-Path $Vault "Claude方案\_知识库首页.md"
if (Test-Path $Dash) {
    Move-Item $Dash (Join-Path $Vault "_知识库首页.md") -Force
    Write-Host "[unpack]   _知识库首页.md -> vault 根  ok"
}

Write-Host "[unpack] transcript -> $env:USERPROFILE\.claude\"
New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE ".claude") | Out-Null
tar -xzf $Archive -C $env:USERPROFILE .claude/projects/ 2>$null
Write-Host "[unpack]   transcript  ok"

Write-Host ""
Write-Host "[unpack] 完成。接下来："
Write-Host "  git clone https://github.com/hjm4839-coder/checkpoint.git $env:USERPROFILE\obsidian"
Write-Host "  cd $env:USERPROFILE\obsidian"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\install.ps1"
