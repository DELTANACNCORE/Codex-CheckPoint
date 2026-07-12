$ErrorActionPreference = "Stop"

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$HooksJson = Join-Path $CodexHome "hooks.json"
$SkillsDir = Join-Path $CodexHome "skills"
$AgentsDst = Join-Path $CodexHome "AGENTS.md"

Write-Host "[checkpoint-codex] 正在卸载 / Uninstalling..."

if (Test-Path $HooksJson) {
  $py = @'
import json, sys
hooks_path = sys.argv[1]
try:
    with open(hooks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print("[checkpoint-codex] hooks.json 不存在或无效，跳过")
    sys.exit(0)

hooks = data.get("hooks", {})
targets = {
    "Stop": ("checkpoint.py", "stop-wrapper.py", "probe-hook.py"),
    "UserPromptSubmit": ("checkpoint.py", "stop-wrapper.py", "probe-hook.py"),
    "PreToolUse": ("pretool.py", "pretool-wrapper.py", "probe-hook.py"),
}
changed = False
for hook_name, tokens in targets.items():
    entries = hooks.get(hook_name, [])
    if not entries:
        continue
    before = len(entries)
    entries[:] = [
        entry for entry in entries
        if not any(any(token in h.get("command", "") for token in tokens) for h in entry.get("hooks", []))
    ]
    after = len(entries)
    if after != before:
        changed = True
        print(f"[checkpoint-codex] 已清理 hooks.{hook_name}: {before}->{after}")
    if not entries:
        hooks.pop(hook_name, None)

if changed:
    with open(hooks_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[checkpoint-codex] hooks.json 已更新: {hooks_path}")
else:
    print("[checkpoint-codex] 未找到需要清理的 hook")
'@
  $py | python - $HooksJson
}

foreach ($skill in @("checkpoint", "search", "synthesize")) {
  $path = Join-Path $SkillsDir $skill
  if (Test-Path $path) {
    Remove-Item $path -Recurse -Force
    Write-Host "[checkpoint-codex] 已删除 skill / skill removed: $path"
  }
}

foreach ($hook in @("checkpoint.py", "pretool.py", "stop-wrapper.py", "pretool-wrapper.py", "retrieve.py")) {
  $hookPath = Join-Path $CodexHome "hooks/$hook"
  if (Test-Path $hookPath) {
    Remove-Item $hookPath -Force
    Write-Host "[checkpoint-codex] 已删除 hook / hook removed: $hookPath"
  }
}

if ((Test-Path $AgentsDst) -and (Select-String -Path $AgentsDst -Pattern '^# Codex Checkpoint Guide$' -Quiet)) {
  Remove-Item $AgentsDst -Force
  Write-Host "[checkpoint-codex] 已删除自动生成的 AGENTS 模板 / generated AGENTS template removed: $AgentsDst"
}

Write-Host ""
Write-Host "[checkpoint-codex] 卸载完成 / Uninstall complete."
Write-Host "- Obsidian 笔记仍保留在 vault 里 / Obsidian notes remain in the vault"
Write-Host "- 如需继续使用，重新运行 install.ps1 / Run install.ps1 again to resume use"
