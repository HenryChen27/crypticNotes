@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\update-client.ps1"
