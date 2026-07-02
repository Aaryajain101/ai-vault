@echo off
cd /d "C:\Users\aarya\Claude Code\AI Vault"
echo ===== %DATE% %TIME% ===== >> update.log
"C:\Users\aarya\AppData\Local\Python\pythoncore-3.14-64\python.exe" fetch.py >> update.log 2>&1
echo. >> update.log