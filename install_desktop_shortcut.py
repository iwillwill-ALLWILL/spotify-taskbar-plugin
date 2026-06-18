# -*- coding: utf-8 -*-
"""Create a desktop shortcut for the Spotify taskbar overlay."""
from __future__ import annotations

import os
from pathlib import Path

import win32com.client

import spotify_taskbar_settings as ctl

ROOT = Path(__file__).resolve().parent
LAUNCHER_SCRIPT = ROOT / "start-spotify-taskbar-overlay.vbs"
ICON_PATH = ROOT / "spotify_taskbar_icon.ico"


def wscript() -> str:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    exe = windir / "System32" / "wscript.exe"
    return str(exe if exe.exists() else "wscript.exe")


def shortcut_name() -> str:
    lang = ctl.active_language(ctl.load_config())
    return "Spotify 任务栏悬浮窗.lnk" if lang == "zh" else "Spotify Taskbar Overlay.lnk"


def main() -> None:
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)
    lnk = desktop / shortcut_name()

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(lnk))
    shortcut.TargetPath = wscript()
    shortcut.Arguments = f'"{LAUNCHER_SCRIPT}"'
    shortcut.WorkingDirectory = str(ROOT)
    shortcut.WindowStyle = 7
    shortcut.Description = ctl.tr("app_name")
    if ICON_PATH.exists():
        shortcut.IconLocation = str(ICON_PATH)
    shortcut.Save()
    print(lnk)


if __name__ == "__main__":
    main()
