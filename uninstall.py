# -*- coding: utf-8 -*-
"""Uninstall helper for Spotify Taskbar Plugin.

Stops the tray/overlay, removes HKCU Run startup entry, and deletes the desktop shortcut.
It intentionally does not delete this project directory.
"""
from __future__ import annotations

import time
import winreg
from pathlib import Path

import win32con
import win32gui
import win32process

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "SpotifyTaskbarTrayApp"
SHORTCUT_NAME = "Spotify 任务栏插件.lnk"
TRAY_CLASS = "SpotifyTaskbarTrayWin32"
TRAY_TITLE = "SpotifyTaskbarTrayApp"
OVERLAY_CLASS = "SpotifyTaskbarOverlayWin32"
OVERLAY_TITLE = "SpotifyTaskbarOverlay"


def post_close_matching(class_name: str, title: str) -> list[int]:
    pids: list[int] = []

    def cb(hwnd, _):
        try:
            if win32gui.GetClassName(hwnd) == class_name or win32gui.GetWindowText(hwnd) == title:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                pids.append(pid)
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return sorted(set(pids))


def remove_startup() -> bool:
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def remove_shortcut() -> bool:
    lnk = Path.home() / "Desktop" / SHORTCUT_NAME
    if lnk.exists():
        lnk.unlink()
        return True
    return False


def main() -> None:
    tray_pids = post_close_matching(TRAY_CLASS, TRAY_TITLE)
    overlay_pids = post_close_matching(OVERLAY_CLASS, OVERLAY_TITLE)
    time.sleep(0.5)
    startup_removed = remove_startup()
    shortcut_removed = remove_shortcut()
    print("Stopped tray PIDs:", tray_pids or "none")
    print("Stopped overlay PIDs:", overlay_pids or "none")
    print("Removed startup:", startup_removed)
    print("Removed desktop shortcut:", shortcut_removed)
    print("Project files were left in place. Delete this folder manually if desired.")


if __name__ == "__main__":
    main()
