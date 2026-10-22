@echo off
REM AI Vault local refresh, PULL MODE since 22 Oct 2026.
REM The database is built in the cloud by the GitHub Actions workflow
REM .github/workflows/build-vault.yml (daily 00:30 UTC, done by about 06:40 IST) and published
REM to the rolling "latest" release. This script downloads that vault.db through
REM pull_release.ps1 (sanity-checked before the swap). Task Scheduler "AI Vault Daily Update"
REM (13:30, via run_hidden.vbs) runs it; vault_search.py also starts it in the background when
REM it sees a newer cloud build. fetch.py remains for a manual local rebuild from the sources.
REM No git pull here: the scripts are authored on this machine and pushed by the 21:00 repo sync.
REM
REM pull_release.ps1 writes its own PULL OK / PULL FAIL line to update.log, so its output is NOT
REM redirected here: a ">> update.log" on that line keeps the file open and the script's append
REM then fails with a sharing violation (seen 22 Oct 2026).
REM Deliberately uses %~dp0 rather than absolute paths, so moving the workspace or changing
REM Windows profile does not break the task.

cd /d "%~dp0"
echo ===== %DATE% %TIME% ===== >> update.log

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0pull_release.ps1" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [update.cmd] pull_release.ps1 exited with %ERRORLEVEL%; see the PULL FAIL line above >> update.log
)
echo. >> update.log
