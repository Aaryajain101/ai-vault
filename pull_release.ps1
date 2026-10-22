# pull_release.ps1: download the cloud-built vault.db from the rolling "latest" GitHub release,
# sanity-check it, then swap it in. Called by update.cmd (pull mode since 22 Oct 2026).
# Windows PowerShell 5.1 compatible (Task Scheduler runs the 5.1 powershell.exe).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$dir   = $PSScriptRoot
$url   = 'https://github.com/Aaryajain101/ai-vault/releases/latest/download/vault.db'
$db    = Join-Path $dir 'vault.db'
$tmp   = Join-Path $dir 'vault.db.tmp'
$stamp = Join-Path $dir '.last_pull'
$t0 = Get-Date

Invoke-WebRequest -Uri $url -OutFile $tmp -TimeoutSec 900 -UseBasicParsing
$mb = [math]::Round((Get-Item $tmp).Length / 1MB, 1)
if ($mb -lt 40) { Remove-Item $tmp -Force; throw "downloaded vault.db is only $mb MB; current file kept" }

# Same floor as the cloud build's own sanity check (10,000 items), plus the local guard that the
# catalogue never shrinks below 60% of what we have.
$py = 'py'; $pyArgs = @('-3')
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { $py = 'python'; $pyArgs = @() }
$code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('select count(*) from items').fetchone()[0])"
$new = [int](& $py @pyArgs -c $code $tmp)
$old = 0
if (Test-Path $db) { $old = [int](& $py @pyArgs -c $code $db) }
if ($new -lt 10000 -or ($old -gt 0 -and $new -lt 0.6 * $old)) {
    Remove-Item $tmp -Force
    throw "downloaded vault.db has $new items (local has $old); current file kept"
}

Move-Item -Force $tmp $db
Set-Content -Path $stamp -Value (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
$secs = [math]::Round(((Get-Date) - $t0).TotalSeconds)
"PULL OK  vault.db $mb MB, $new items (local before: $old), ${secs}s"
