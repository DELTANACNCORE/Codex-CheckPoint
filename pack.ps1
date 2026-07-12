$ErrorActionPreference = "Stop"

$Vault = $env:OBSIDIAN_VAULT
if (-not $Vault) {
  $HooksJson = Join-Path $HOME ".codex\hooks.json"
  if (Test-Path $HooksJson) {
    try {
      $raw = Get-Content $HooksJson -Raw -Encoding UTF8
      if ($raw -match '--vault-root\s+("?)([^"\r\n]+)\1') {
        $Vault = $Matches[2]
      }
    } catch {}
  }
}

if (-not $Vault) {
  $Default = Join-Path $HOME "obsidian\知识库"
  $Vault = Read-Host "Obsidian vault 路径 / path [默认 / default: $Default]"
  if (-not $Vault) { $Vault = $Default }
}

$Out = "checkpoint-codex-migrate-$(Get-Date -Format 'yyyyMMdd-HHmmss').tar.gz"

Write-Host "[pack-codex] 知识库 / vault: $Vault"

if (-not (Test-Path (Join-Path $Vault "Codex工作记录"))) {
  Write-Error "[pack-codex] Codex工作记录/ 不存在，目录可能错误 / Codex工作记录/ is missing; check the vault path"
  exit 1
}

$Items = @("Codex工作记录")
foreach ($Item in @("项目总结", "长期经验总结", "知识库首页.md", "Codex协同Obsidian工作流skill更新日志.md")) {
  if (Test-Path (Join-Path $Vault $Item)) { $Items += $Item }
}

tar -czf $Out -C $Vault @Items -C $HOME .codex/sessions 2>$null

$Size = (Get-Item $Out).Length / 1MB
Write-Host "[pack-codex] -> $Out ($([math]::Round($Size,1))MB)"
Write-Host "[pack-codex] 传到新电脑后运行 unpack.ps1 / On a new machine, run unpack.ps1"
