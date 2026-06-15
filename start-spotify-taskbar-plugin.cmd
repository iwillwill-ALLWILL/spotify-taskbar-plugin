@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0spotify_taskbar_tray.py"
) else (
  start "" pythonw.exe "%~dp0spotify_taskbar_tray.py"
)
