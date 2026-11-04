@echo off
rem One-click start for the DeFi bot on Windows: sets up Python packages once,
rem asks for the bot token the first time, then runs the bot.
cd /d "%~dp0"
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
if not exist ".venv\Scripts\python.exe" (
  echo Preparing Python environment ^(first run only^)...
  %PY% -m venv .venv
  if errorlevel 1 goto nopython
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pipfail
".venv\Scripts\python.exe" start_bot.py %*
pause
exit /b

:nopython
echo.
echo Python 3.10 or newer is needed: https://www.python.org/downloads/
echo During install tick "Add python.exe to PATH", then double-click this file again.
pause
exit /b 1

:pipfail
echo.
echo Installing the Python packages failed - check the internet connection and try again.
pause
exit /b 1
