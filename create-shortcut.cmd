@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcut.ps1"
if errorlevel 1 pause
endlocal
