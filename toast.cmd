@echo off
setlocal
cd /d "%~dp0"
if not exist "runlogs\toast" mkdir "runlogs\toast"
start "" /min pythonw "%~dp0toast.py" >> "%~dp0runlogs\toast\toast.log" 2>&1
endlocal
