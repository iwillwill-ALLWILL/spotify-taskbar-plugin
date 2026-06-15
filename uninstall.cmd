@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" uninstall.py
) else (
  python uninstall.py
)

pause
