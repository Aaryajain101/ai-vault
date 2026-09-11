@echo off
REM Daily AI Vault refresh. Called by run_hidden.vbs from the scheduled task
REM "AI Vault Daily Update". Run it directly to refresh on demand.
REM
REM Deliberately uses %~dp0 and the py launcher rather than absolute paths, so
REM moving the workspace or changing Windows profile does not break the task.
REM The previous version hardcoded a python.exe inside one user's AppData and
REM broke when the machine changed.

cd /d "%~dp0"
echo ===== %DATE% %TIME% ===== >> update.log

REM Prefer the py launcher, fall back to python on PATH.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 fetch.py >> update.log 2>&1
) else (
    python fetch.py >> update.log 2>&1
)

if %ERRORLEVEL% NEQ 0 (
    echo [update.cmd] fetch.py exited with %ERRORLEVEL% >> update.log
)
echo. >> update.log
