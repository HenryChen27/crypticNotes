@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem PySide6 没有 32 位 wheel，32 位解释器会在下面 pip 那步才失败，
rem 报错还看不出原因。先卡住位数，把话说在前面。
py -3 -c "import sys;raise SystemExit(0 if sys.maxsize>2**32 else 1)" 2>nul
if errorlevel 1 goto nopython
py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r mapmatching\requirements-ui.txt
if errorlevel 1 goto failed
echo.
echo 依赖安装完成。双击「crypticNotes.cmd」即可。
pause
exit /b 0
:nopython
echo.
echo 没有找到 64 位 Python。
echo 请先到 python.org 安装 64 位 Python 3.13，再运行本脚本；
echo 或者直接下载打包版 ZIP，解压即用，不需要装 Python。
pause
exit /b 1
:failed
echo.
echo 依赖安装失败。请确认网络可用，且 Python 是 64 位的 3.13。
pause
exit /b 1
