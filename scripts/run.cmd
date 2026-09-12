@echo off
chcp 65001 >nul
cd /d "%~dp0.."
rem 依次找可用的入口：打包版 EXE → 本项目 .venv → 系统 py 启动器 → 系统 pythonw。
rem 全程不写死任何解释器路径，换机器、换盘符、换用户名都不用改。
if exist "IdentityVMapAssistant.exe" (
  start "" "IdentityVMapAssistant.exe" %*
  exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m mapmatching.launch %*
  exit /b
)
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 -m mapmatching.launch %*
  exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw -m mapmatching.launch %*
  exit /b
)
echo.
echo 没有找到 Python。请任选一种：
echo   1. 双击 setup.cmd 安装依赖（需要 64 位 Python 3.13）
echo   2. 下载打包版 ZIP，解压后直接跑，不需要装 Python
pause
