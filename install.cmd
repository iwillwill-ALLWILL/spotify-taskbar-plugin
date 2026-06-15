@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo Spotify Taskbar Plugin installer
echo ---------------------------------

set "PY_CMD=python"
where py >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"

echo [1/4] Creating local virtual environment...
%PY_CMD% -m venv .venv
if errorlevel 1 (
  echo Failed to create .venv. Please install Python 3.11+ and try again.
  pause
  exit /b 1
)

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "VENV_PYW=%~dp0.venv\Scripts\pythonw.exe"

echo [2/4] Installing dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto fail
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo [3/4] Creating desktop shortcut...
"%VENV_PY%" install_desktop_shortcut.py
if errorlevel 1 goto fail

echo [4/4] Starting tray app...
start "" "%VENV_PYW%" "%~dp0spotify_taskbar_tray.py"

echo.
echo Done. Use the desktop shortcut or tray icon to manage the plugin.
echo Right-click tray icon: settings. Left-click: show/hide overlay.
pause
exit /b 0

:fail
echo.
echo Install failed. See the error above.
pause
exit /b 1
