# -*- coding: utf-8 -*-
"""Small settings/control panel for Spotify taskbar overlay."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import tkinter as tk
import winreg
from pathlib import Path
from tkinter import ttk

import win32con
import win32gui
import win32process

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SpotifyTaskbarOverlay"
CONFIG_PATH = APP_DIR / "settings.json"
OVERLAY_SCRIPT = Path(__file__).with_name("spotify_taskbar_overlay.py")
TRAY_SCRIPT = Path(__file__).with_name("spotify_taskbar_tray.py")
APP_TITLE = "SpotifyTaskbarOverlay"
CLASS_NAME = "SpotifyTaskbarOverlayWin32"
ICON_PATH = Path(__file__).with_name("spotify_taskbar_icon.ico")
AUTOSTART_NAME = "SpotifyTaskbarTrayApp"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

DEFAULT_CONFIG = {
    "auto_position": True,
    "x": None,
    "y": None,
    "width": 520,
    "height": 44,
    "always_on_top": True,
    "hide_fullscreen": True,
    "hide_when_no_media": True,
    "show_widget_on_app_start": True,
    "auto_start": False,
    "avoid_taskbar_overlap": True,
}


def pythonw() -> str:
    p = Path(sys.executable).with_name("pythonw.exe")
    return str(p if p.exists() else sys.executable)


def startup_command() -> str:
    return f'"{pythonw()}" "{TRAY_SCRIPT}"'


def is_auto_start_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _typ = winreg.QueryValueEx(key, AUTOSTART_NAME)
        return str(value).strip() == startup_command()
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_auto_start_enabled(enabled: bool):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        pass
    return cfg


def save_config(cfg: dict):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    out = dict(DEFAULT_CONFIG)
    out.update(cfg or {})
    CONFIG_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def enum_overlay_windows():
    hits = []

    def cb(hwnd, _):
        try:
            if win32gui.GetWindowText(hwnd) == APP_TITLE or win32gui.GetClassName(hwnd) == CLASS_NAME:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                hits.append((hwnd, pid, win32gui.GetWindowRect(hwnd), bool(win32gui.IsWindowVisible(hwnd))))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return hits


def is_overlay_running() -> bool:
    return bool(enum_overlay_windows())


def start_overlay():
    if is_overlay_running():
        return
    subprocess.Popen([pythonw(), str(OVERLAY_SCRIPT)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(0.35)


def stop_overlay():
    hits = enum_overlay_windows()
    pids = set()
    for hwnd, pid, _rect, _visible in hits:
        pids.add(pid)
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not enum_overlay_windows():
            return
        time.sleep(0.1)
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True, encoding="gbk", errors="replace", timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass


def restart_overlay():
    stop_overlay()
    start_overlay()


def reset_auto_position(restart=True):
    cfg = load_config()
    cfg["auto_position"] = True
    cfg["x"] = None
    cfg["y"] = None
    save_config(cfg)
    if restart:
        restart_overlay()


class SettingsWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Spotify 插件设置")
        self.root.geometry("420x370")
        self.root.minsize(400, 350)
        self.root.configure(bg="#111111")
        try:
            if ICON_PATH.exists():
                self.root.iconbitmap(str(ICON_PATH))
        except Exception:
            pass

        self.cfg = load_config()
        self.vars = {
            "avoid_taskbar_overlap": tk.BooleanVar(value=bool(self.cfg.get("avoid_taskbar_overlap", True))),
            "hide_fullscreen": tk.BooleanVar(value=bool(self.cfg.get("hide_fullscreen", True))),
            "hide_when_no_media": tk.BooleanVar(value=bool(self.cfg.get("hide_when_no_media", True))),
            "auto_start": tk.BooleanVar(value=is_auto_start_enabled()),
            "status": tk.StringVar(value=""),
        }

        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure("TFrame", background="#111111")
            style.configure("TLabel", background="#111111", foreground="#f3f3f3")
            style.configure("TCheckbutton", background="#111111", foreground="#f3f3f3")
            style.configure("TButton", padding=6)
        except Exception:
            pass

        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Spotify 任务栏插件", font=("Microsoft YaHei UI", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Checkbutton(frame, text="开机自启动托盘", variable=self.vars["auto_start"]).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="拖进任务栏时自动同高", variable=self.vars["avoid_taskbar_overlap"]).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="全屏应用时隐藏", variable=self.vars["hide_fullscreen"]).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="没有媒体时隐藏", variable=self.vars["hide_when_no_media"]).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)

        ttk.Label(frame, textvariable=self.vars["status"], wraplength=370).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 8))

        ttk.Button(frame, text="保存", command=self.save_and_restart).grid(row=6, column=0, sticky="ew", padx=(0, 5), pady=3)
        ttk.Button(frame, text="重置位置", command=self.reset_position).grid(row=6, column=1, sticky="ew", padx=(5, 0), pady=3)
        ttk.Button(frame, text="打开插件", command=self.show_overlay).grid(row=7, column=0, sticky="ew", padx=(0, 5), pady=3)
        ttk.Button(frame, text="关闭插件", command=self.hide_overlay).grid(row=7, column=1, sticky="ew", padx=(5, 0), pady=3)

        self.refresh_status()

    def collect(self):
        cfg = load_config()
        cfg.update({
            "always_on_top": True,
            "avoid_taskbar_overlap": bool(self.vars["avoid_taskbar_overlap"].get()),
            "hide_fullscreen": bool(self.vars["hide_fullscreen"].get()),
            "hide_when_no_media": bool(self.vars["hide_when_no_media"].get()),
            "auto_start": bool(self.vars["auto_start"].get()),
        })
        return cfg

    def save_and_restart(self):
        cfg = self.collect()
        save_config(cfg)
        set_auto_start_enabled(bool(cfg.get("auto_start", False)))
        restart_overlay()
        self.cfg = cfg
        self.vars["auto_start"].set(is_auto_start_enabled())
        self.refresh_status("已保存")

    def show_overlay(self):
        start_overlay()
        self.refresh_status("已打开")

    def hide_overlay(self):
        stop_overlay()
        self.refresh_status("已关闭")

    def reset_position(self):
        reset_auto_position(restart=True)
        self.cfg = load_config()
        self.refresh_status("已重置位置")

    def refresh_status(self, prefix=""):
        hits = enum_overlay_windows()
        if hits:
            _hwnd, pid, rect, _visible = hits[0]
            text = f"运行中 · PID {pid} · {rect}"
        else:
            text = "插件未运行"
        if prefix:
            text = f"{prefix} · {text}"
        self.vars["status"].set(text)

    def run(self):
        self.root.mainloop()


def cli():
    if "--status" in sys.argv:
        print(json.dumps({"running": is_overlay_running(), "windows": enum_overlay_windows(), "config": load_config()}, ensure_ascii=False, default=str))
        return True
    if "--show" in sys.argv:
        start_overlay(); print("shown"); return True
    if "--hide" in sys.argv:
        stop_overlay(); print("hidden"); return True
    if "--restart" in sys.argv:
        restart_overlay(); print("restarted"); return True
    if "--reset-auto" in sys.argv:
        reset_auto_position(restart=True); print("reset"); return True
    return False


if __name__ == "__main__":
    if not cli():
        SettingsWindow().run()
