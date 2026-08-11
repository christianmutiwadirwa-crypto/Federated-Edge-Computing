@echo off
echo Killing Raspberry Pi Edge Node server...
wmic process where "CommandLine LIKE '%%python%%main.py%%' and Name='python.exe'" call terminate >nul 2>&1
echo Server killed (if it was running).
pause
