# -*- coding: utf-8 -*-
"""System tray manager for Spotify taskbar overlay."""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

import win32api
import win32con
import win32gui

import spotify_taskbar_settings as ctl

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_TITLE = "SpotifyTaskbarTrayApp"
CLASS_NAME = "SpotifyTaskbarTrayWin32"
WM_TRAYICON = win32con.WM_USER + 20
WM_TASKBARCREATED = win32gui.RegisterWindowMessage("TaskbarCreated")

ID_SHOW_HIDE = 1001
ID_SETTINGS = 1002
ID_RESTART = 1003
ID_RESET = 1004
ID_EXIT = 1005
ID_EXIT_ALL = 1006
ICON_PATH = Path(__file__).with_name("spotify_taskbar_icon.ico")


class TrayApp:
    def __init__(self):
        self.hwnd = None
        self.hicon = None
        self.settings_proc = None

    def register_class(self):
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = CLASS_NAME
        wc.lpfnWndProc = self.wndproc
        wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        wc.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)
        try:
            win32gui.RegisterClass(wc)
        except win32gui.error:
            pass

    def create_window(self):
        self.register_class()
        self.hwnd = win32gui.CreateWindowEx(
            0,
            CLASS_NAME,
            APP_TITLE,
            win32con.WS_OVERLAPPED,
            0,
            0,
            0,
            0,
            0,
            0,
            win32api.GetModuleHandle(None),
            None,
        )

    def load_icon(self):
        if ICON_PATH.exists():
            try:
                return win32gui.LoadImage(
                    0,
                    str(ICON_PATH),
                    win32con.IMAGE_ICON,
                    0,
                    0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
                )
            except Exception:
                pass
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def add_icon(self):
        self.hicon = self.load_icon()
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        cfg = ctl.load_config()
        nid = (self.hwnd, 0, flags, WM_TRAYICON, self.hicon, ctl.tr("app_name", cfg))
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        except win32gui.error:
            # If Explorer restarted and the icon already exists, modify it.
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)

    def remove_icon(self):
        try:
            nid = (self.hwnd, 0)
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        except Exception:
            pass

    def open_settings(self):
        script = Path(__file__).with_name("spotify_taskbar_settings.py")
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = str(pyw if pyw.exists() else sys.executable)
        try:
            if self.settings_proc and self.settings_proc.poll() is None:
                return
            self.settings_proc = subprocess.Popen([exe, str(script)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            self.settings_proc = None

    def toggle_overlay(self):
        if ctl.is_overlay_running():
            ctl.stop_overlay()
        else:
            ctl.start_overlay()

    def show_menu(self):
        running = ctl.is_overlay_running()
        menu = win32gui.CreatePopupMenu()
        cfg = ctl.load_config()
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_SHOW_HIDE, ctl.tr("close", cfg) if running else ctl.tr("open", cfg))
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_SETTINGS, ctl.tr("settings_title", cfg))
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_RESET, ctl.tr("reset", cfg))
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_RESTART, "Restart" if ctl.active_language(cfg) == "en" else "重启")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, None)
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_EXIT, "Exit tray" if ctl.active_language(cfg) == "en" else "退出托盘")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_EXIT_ALL, "Close and exit" if ctl.active_language(cfg) == "en" else "关闭并退出")
        x, y = win32gui.GetCursorPos()
        try:
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass
        cmd = win32gui.TrackPopupMenu(menu, win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON, x, y, 0, self.hwnd, None)
        if cmd == ID_SHOW_HIDE:
            if running:
                ctl.stop_overlay()
            else:
                ctl.start_overlay()
        elif cmd == ID_SETTINGS:
            self.open_settings()
        elif cmd == ID_RESTART:
            ctl.restart_overlay()
        elif cmd == ID_RESET:
            ctl.reset_auto_position(restart=True)
        elif cmd == ID_EXIT:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        elif cmd == ID_EXIT_ALL:
            ctl.stop_overlay()
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)

    def wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TASKBARCREATED:
            self.add_icon()
            return 0
        if msg == WM_TRAYICON:
            if lparam in (win32con.WM_RBUTTONUP, win32con.WM_CONTEXTMENU):
                # Win11 notification-area context menus can be swallowed on some
                # machines. Make right-click deterministic: open settings directly.
                self.open_settings()
                return 0
            if lparam == win32con.WM_LBUTTONUP:
                self.toggle_overlay()
                return 0
        if msg == win32con.WM_CLOSE:
            self.remove_icon()
            win32gui.DestroyWindow(hwnd)
            return 0
        if msg == win32con.WM_DESTROY:
            self.remove_icon()
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def run(self):
        self.create_window()
        self.add_icon()
        cfg = ctl.load_config()
        if cfg.get("show_widget_on_app_start", True) and not ctl.is_overlay_running():
            ctl.start_overlay()
        win32gui.PumpMessages()


if __name__ == "__main__":
    app = TrayApp()
    app.run()
