@echo off
rem ---------------------------------------------------------------
rem  Launcher for the map-assistant updater.
rem
rem  This file is deliberately ASCII-only. cmd.exe locates the next
rem  line of a batch file by BYTE OFFSET; mixing GBK Chinese into it
rem  makes that offset wrong and cmd resumes in the middle of a line
rem  (we measured `where git >nul 2>nul` being entered as `ul 2>nul`,
rem  which cmd reports as "The syntax of the command is incorrect").
rem  All the Chinese text lives in scripts\update-client.ps1 instead,
rem  which PowerShell reads as Unicode and has no such problem.
rem ---------------------------------------------------------------

rem  No pause here on purpose: the PowerShell script switches the console to
rem  UTF-8 for its Chinese output, and cmd would then fall back to English
rem  for its own "Press any key" prompt. That script handles the final
rem  keypress itself, so the console is never handed back to cmd.
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update-client.ps1"
