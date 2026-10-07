@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "http://127.0.0.1:5173"
