# checkpoint 知识库打包脚本 (Windows / PowerShell)
$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Settings = Join-Path $env:USERPROFILE ".claude\settings.json"

# 读安装时存的 OBSIDIAN_VAULT
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

$Plans = Join-Path $Vault "Claude方案"
$Dash = Join-Path $Vault "_知识库首页.md"
$Projects = Join-Path $env:USERPROFILE ".claude\projects"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmm"
$Out = "checkpoint-migrate-$Timestamp.zip"

Write-Host "[pack] vault: $Vault"

if (-not (Test-Path $Plans)) {
    Write-Error "[pack] Claude方案/ 不存在，目录不对？"
    exit 1
}

# 首页如果在 vault 根也打进去
if (Test-Path $Dash) { Copy-Item $Dash $Plans -Force }

# tar 在 Win10 1803+ 可用
tar -czf $Out -C $Vault Claude方案 -C $env:USERPROFILE .claude/projects 2>$null

if (Test-Path (Join-Path $Plans "_知识库首页.md")) {
    Remove-Item (Join-Path $Plans "_知识库首页.md") -Force
}

$Size = (Get-Item $Out).Length / 1MB
Write-Host "[pack] -> $Out ($([math]::Round($Size,1))MB)"
Write-Host "[pack] 传到新电脑后跑 unpack.ps1"
