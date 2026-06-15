# -*- coding: utf-8 -*-
"""Create a desktop shortcut for the Spotify taskbar plugin."""
from __future__ import annotations

import sys
from pathlib import Path

import win32com.client


ROOT = Path(__file__).resolve().parent
TRAY_SCRIPT = ROOT / "spotify_taskbar_tray.py"
ICON_PATH = ROOT / "spotify_taskbar_icon.ico"
SHORTCUT_NAME = "Spotify 任务栏插件.lnk"


def pythonw() -> Path:
    p = Path(sys.executable).with_name("pythonw.exe")
    return p if p.exists() else Path(sys.executable)


def main() -> None:
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    lnk = desktop / SHORTCUT_NAME

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(lnk))
    shortcut.TargetPath = str(pythonw())
    shortcut.Arguments = f'"{TRAY_SCRIPT}"'
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.WindowStyle = 7
    shortcut.Description = "Spotify 任务栏插件"
    if ICON_PATH.exists():
        shortcut.IconLocation = str(ICON_PATH)
    shortcut.Save()
    print(lnk)


if __name__ == "__main__":
    main()
