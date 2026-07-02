# AI Vault setup — Windows
# Run from the cloned repo folder:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
$RepoSlug = "Aaryajain101/ai-vault"
$VaultDir = $PSScriptRoot

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { Write-Host "Python missing. Install from python.org, then re-run setup." -ForegroundColor Red; exit 1 }

Write-Host "1/4 Downloading latest vault.db..." -ForegroundColor Cyan
$dbUrl = "https://github.com/$RepoSlug/releases/latest/download/vault.db"
Invoke-WebRequest -Uri $dbUrl -OutFile (Join-Path $VaultDir "vault.db")

Write-Host "2/4 Installing the /vault-search skill for Claude Code..." -ForegroundColor Cyan
$skillDir = Join-Path $env:USERPROFILE ".claude\skills"
New-Item -ItemType Directory -Force $skillDir | Out-Null
$skill = @"
---
name: vault-search
description: Search the local AI Vault (30K+ skills, tools, MCP servers, LLMs, agents, designs) and install items automatically. Use when the user wants to find or install an AI tool, skill, MCP server, LLM, agent, or design.
---

# AI Vault Search & Install

Local database: ``$VaultDir\vault.db`` (30K+ AI resources from 7 upstream sources, deduplicated).

**Search:**   ``python "$VaultDir\vault_search.py" <query> [--cat skill|mcp_server|tool|llm|agent|design] [--source <name>] [--limit N]``
**Install:**  ``python "$VaultDir\vault_search.py" --install <slug>``
**Details:**  ``python "$VaultDir\vault_search.py" --get <slug>``
**Stats:**    ``python "$VaultDir\vault_search.py" --stats``

Search proactively when the user needs a capability you don't have, asks about a tool by name, or asks "is there a skill/MCP for X?". Skills install via ``npx skills add``; MCP servers via ``claude mcp add``; other categories open their URL.
"@
Set-Content -Path (Join-Path $skillDir "vault-search.md") -Value $skill -Encoding utf8

Write-Host "3/4 Creating the daily auto-update task (7:00 AM)..." -ForegroundColor Cyan
$pull = @"
@echo off
cd /d "$VaultDir"
git pull --quiet
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/$RepoSlug/releases/latest/download/vault.db' -OutFile 'vault.db'"
"@
[System.IO.File]::WriteAllText((Join-Path $VaultDir "pull.cmd"), $pull, (New-Object System.Text.ASCIIEncoding))
$action   = New-ScheduledTaskAction -Execute (Join-Path $VaultDir "pull.cmd")
$trigger  = New-ScheduledTaskTrigger -Daily -At 7:00am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable
Register-ScheduledTask -TaskName "AI Vault Auto-Update" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null

Write-Host "4/4 Testing search..." -ForegroundColor Cyan
& $python (Join-Path $VaultDir "vault_search.py") --stats

Write-Host "`nDone! The vault auto-updates daily at 7 AM. In Claude Code, just ask for any tool/skill/MCP." -ForegroundColor Green
