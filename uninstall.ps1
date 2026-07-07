# checkpoint 卸载脚本 (Windows / PowerShell)
$ErrorActionPreference = "Stop"

$Settings = Join-Path $env:USERPROFILE ".claude\settings.json"
$SkillsDir = Join-Path $env:USERPROFILE ".claude\skills"

Write-Host "[checkpoint] 正在卸载..."

if (-not (Test-Path $Settings)) {
    Write-Host "[checkpoint] $Settings 不存在，无需卸载"
} else {
    $py = @'
import json, sys, os
sp = os.path.expanduser(sys.argv[1])
try:
    with open(sp, "r", encoding="utf-8") as f: data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print("[checkpoint] 配置文件不存在或无效，跳过")
    sys.exit(0)

cleaned = False
for hook_type in ("Stop", "PreToolUse"):
    hooks = data.get("hooks", {}).get(hook_type, [])
    if not hooks: continue
    before = len(hooks)
    hooks[:] = [e for e in hooks if not any(
        "checkpoint.py" in h.get("command", "") or "pretool.py" in h.get("command", "")
        for h in e.get("hooks", [])
    )]
    after = len(hooks)
    if after < before:
        cleaned = True
        print(f"[checkpoint] 已清理 hooks.{hook_type}: {before}->{after}")
    if not hooks:
        data["hooks"].pop(hook_type, None)

env = data.get("env", {})
vault = env.pop("OBSIDIAN_VAULT", None)
if vault:
    cleaned = True
    print(f"[checkpoint] 已移除 env.OBSIDIAN_VAULT ({vault})")
if not env:
    data.pop("env", None)
if not data.get("hooks"):
    data.pop("hooks", None)

if cleaned:
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[checkpoint] 配置已更新: {sp}")
else:
    print("[checkpoint] 未找到 checkpoint 相关配置")
'@
    $py | python - $Settings
}

# 清理 skills
foreach ($skill in @("checkpoint", "synthesize")) {
    $d = Join-Path $SkillsDir $skill
    if (Test-Path $d) {
        Remove-Item -Recurse -Force $d
        Write-Host "[checkpoint] 已删除 skill: $d"
    }
}

# 清理 bak
$Bak = "$Settings.bak"
if (Test-Path $Bak) {
    Remove-Item -Force $Bak
    Write-Host "[checkpoint] 已删除备份: $Bak"
}

Write-Host ""
Write-Host "[checkpoint] 卸载完成。"
Write-Host "  - 断点笔记/每日索引仍保留在 vault（如需删除：删 Claude方案/会话断点/ 和 Claude方案/会话索引/）"
