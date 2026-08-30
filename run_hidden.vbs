' Runs the AI Vault daily update with no visible console window.
' Scheduled task "AI Vault Daily Update" calls this via wscript.exe.
CreateObject("WScript.Shell").Run """C:\Users\aarya\Claude Code\AI Vault\update.cmd""", 0, False
