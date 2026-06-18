# -*- coding: utf-8 -*-
"""Small settings/control panel for Spotify taskbar overlay."""
from __future__ import annotations

import ctypes
import json
import locale
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
TRAY_APP_TITLE = "SpotifyTaskbarTrayApp"
TRAY_CLASS_NAME = "SpotifyTaskbarTrayWin32"
ICON_PATH = Path(__file__).with_name("spotify_taskbar_icon.ico")
AUTOSTART_NAME = "SpotifyTaskbarTrayApp"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
CREATE_FLAGS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_FLAGS_DETACHED = CREATE_FLAGS_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x00000008  # DETACHED_PROCESS
OWNER_PID_ENV = "SPOTIFY_TASKBAR_OWNER_PID"
NO_REEXEC_ENV = "SPOTIFY_TASKBAR_NO_REEXEC"

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
    "language": "auto",  # auto | zh | en
}

STRINGS = {
    "zh": {
        "app_name": "Spotify 任务栏悬浮窗",
        "settings_title": "Spotify 悬浮窗设置",
        "language": "语言",
        "language_auto": "自动",
        "language_zh": "中文",
        "language_en": "English",
        "auto_start": "开机自启动托盘",
        "snap_taskbar": "拖进任务栏时自动同高",
        "hide_fullscreen": "全屏应用时隐藏",
        "hide_no_media": "没有媒体时隐藏",
        "save": "保存",
        "reset": "重置位置",
        "open": "打开悬浮窗",
        "close": "关闭悬浮窗",
        "saved": "已保存",
        "opened": "已打开",
        "closed": "已关闭",
        "reset_done": "已重置位置",
        "running": "运行中",
        "not_running": "悬浮窗未运行",
        "shown": "已显示",
        "hidden": "已隐藏",
        "reset_cli": "已重置",
        "refresh_like": "刷新喜欢状态",
        "exit_overlay": "退出悬浮窗",
        "quit_app": "退出插件",
        "quitting": "正在退出插件",
        "quit_done": "插件已退出",
        "media": "媒体",
    },
    "en": {
        "app_name": "Spotify Taskbar Overlay",
        "settings_title": "Spotify Overlay Settings",
        "language": "Language",
        "language_auto": "Auto",
        "language_zh": "中文",
        "language_en": "English",
        "auto_start": "Start tray app on login",
        "snap_taskbar": "Snap to taskbar height when dragged into taskbar",
        "hide_fullscreen": "Hide when fullscreen app is active",
        "hide_no_media": "Hide when no media is playing",
        "save": "Save",
        "reset": "Reset position",
        "open": "Show overlay",
        "close": "Hide overlay",
        "saved": "Saved",
        "opened": "Shown",
        "closed": "Hidden",
        "reset_done": "Position reset",
        "running": "Running",
        "not_running": "Overlay not running",
        "shown": "shown",
        "hidden": "hidden",
        "reset_cli": "reset",
        "refresh_like": "Refresh liked state",
        "exit_overlay": "Exit overlay",
        "quit_app": "Exit app",
        "quitting": "Exiting app",
        "quit_done": "App exited",
        "media": "Media",
    },
}

LANGUAGE_OPTIONS = [("auto", "language_auto"), ("zh", "language_zh"), ("en", "language_en")]


def system_language() -> str:
    try:
        lang = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        lang = ""
    return "zh" if lang.startswith("zh") else "en"


def active_language(cfg: dict | None = None) -> str:
    lang = (cfg or load_config()).get("language", "auto")
    if lang == "zh":
        return "zh"
    if lang == "en":
        return "en"
    return system_language()


def tr(key: str, cfg: dict | None = None) -> str:
    lang = active_language(cfg)
    return STRINGS.get(lang, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))


def language_display(value: str, cfg: dict | None = None) -> str:
    lookup = {code: tr(label_key, cfg) for code, label_key in LANGUAGE_OPTIONS}
    return lookup.get(value, lookup["auto"])


def language_from_display(display: str, cfg: dict | None = None) -> str:
    for code, label_key in LANGUAGE_OPTIONS:
        if display == tr(label_key, cfg):
            return code
    return "auto"


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


def enum_tray_windows():
    hits = []

    def cb(hwnd, _):
        try:
            if win32gui.GetWindowText(hwnd) == TRAY_APP_TITLE or win32gui.GetClassName(hwnd) == TRAY_CLASS_NAME:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                hits.append((hwnd, pid, win32gui.GetWindowRect(hwnd), bool(win32gui.IsWindowVisible(hwnd))))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return hits


def is_tray_running() -> bool:
    return bool(enum_tray_windows())


def stop_tray():
    hits = enum_tray_windows()
    pids = set()
    for hwnd, pid, _rect, _visible in hits:
        pids.add(pid)
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not enum_tray_windows():
            return
        time.sleep(0.1)
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True, encoding="gbk", errors="replace", timeout=3, creationflags=CREATE_FLAGS_NO_WINDOW)
        except Exception:
            pass


def start_overlay(owner_pid: int | None = None):
    if is_overlay_running():
        return
    env = os.environ.copy()
    if owner_pid is None:
        tray_hits = enum_tray_windows()
        if tray_hits:
            owner_pid = int(tray_hits[0][1])
    if owner_pid:
        env[OWNER_PID_ENV] = str(int(owner_pid))
    subprocess.Popen([pythonw(), str(OVERLAY_SCRIPT)], creationflags=CREATE_FLAGS_DETACHED, env=env, close_fds=True)
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
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True, encoding="gbk", errors="replace", timeout=3, creationflags=CREATE_FLAGS_NO_WINDOW)
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
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.geometry("500x430")
        self.root.minsize(480, 410)
        self.root.configure(bg="#111111")
        try:
            if ICON_PATH.exists():
                self.root.iconbitmap(str(ICON_PATH))
        except Exception:
            pass

        self.vars = {
            "avoid_taskbar_overlap": tk.BooleanVar(value=bool(self.cfg.get("avoid_taskbar_overlap", True))),
            "hide_fullscreen": tk.BooleanVar(value=bool(self.cfg.get("hide_fullscreen", True))),
            "hide_when_no_media": tk.BooleanVar(value=bool(self.cfg.get("hide_when_no_media", True))),
            "auto_start": tk.BooleanVar(value=is_auto_start_enabled()),
            "language": tk.StringVar(value=language_display(str(self.cfg.get("language", "auto")), self.cfg)),
            "status": tk.StringVar(value=""),
        }

        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure("TFrame", background="#111111")
            style.configure("TLabel", background="#111111", foreground="#f3f3f3")
            style.configure("TCheckbutton", background="#111111", foreground="#f3f3f3")
            style.configure("TButton", padding=6)
            style.configure("TCombobox", padding=4)
        except Exception:
            pass

        self.frame = ttk.Frame(self.root, padding=14)
        self.frame.pack(fill="both", expand=True)
        self.frame.columnconfigure(0, weight=0)
        self.frame.columnconfigure(1, weight=1)
        self.frame.columnconfigure(2, weight=1)

        self.title_label = ttk.Label(self.frame, font=("Microsoft YaHei UI", 13, "bold"))
        self.title_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.language_label = ttk.Label(self.frame)
        self.language_label.grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        self.language_combo = ttk.Combobox(self.frame, textvariable=self.vars["language"], state="readonly", width=18)
        self.language_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language_selected)

        self.auto_start_check = ttk.Checkbutton(self.frame, variable=self.vars["auto_start"])
        self.auto_start_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        self.snap_check = ttk.Checkbutton(self.frame, variable=self.vars["avoid_taskbar_overlap"])
        self.snap_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        self.fullscreen_check = ttk.Checkbutton(self.frame, variable=self.vars["hide_fullscreen"])
        self.fullscreen_check.grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        self.no_media_check = ttk.Checkbutton(self.frame, variable=self.vars["hide_when_no_media"])
        self.no_media_check.grid(row=5, column=0, columnspan=3, sticky="w", pady=4)

        self.status_label = ttk.Label(self.frame, textvariable=self.vars["status"], wraplength=450)
        self.status_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 8))

        self.save_button = ttk.Button(self.frame, command=self.save_and_restart)
        self.save_button.grid(row=7, column=0, sticky="ew", padx=(0, 5), pady=3)
        self.reset_button = ttk.Button(self.frame, command=self.reset_position)
        self.reset_button.grid(row=7, column=1, sticky="ew", padx=5, pady=3)
        self.open_button = ttk.Button(self.frame, command=self.show_overlay)
        self.open_button.grid(row=8, column=0, sticky="ew", padx=(0, 5), pady=3)
        self.close_button = ttk.Button(self.frame, command=self.hide_overlay)
        self.close_button.grid(row=8, column=1, sticky="ew", padx=5, pady=3)
        self.quit_button = ttk.Button(self.frame, command=self.quit_app)
        self.quit_button.grid(row=9, column=0, columnspan=3, sticky="ew", padx=(0, 5), pady=(8, 3))

        self.apply_language()
        self.refresh_status()

    def selected_language_code(self) -> str:
        return language_from_display(self.vars["language"].get(), self.cfg)

    def on_language_selected(self, _event=None):
        self.cfg["language"] = self.selected_language_code()
        self.apply_language()
        self.refresh_status()

    def apply_language(self):
        lang_value = str(self.cfg.get("language", "auto"))
        self.root.title(tr("settings_title", self.cfg))
        self.title_label.configure(text=tr("app_name", self.cfg))
        self.language_label.configure(text=tr("language", self.cfg))
        values = [tr(label_key, self.cfg) for _code, label_key in LANGUAGE_OPTIONS]
        self.language_combo.configure(values=values)
        self.vars["language"].set(language_display(lang_value, self.cfg))
        self.auto_start_check.configure(text=tr("auto_start", self.cfg))
        self.snap_check.configure(text=tr("snap_taskbar", self.cfg))
        self.fullscreen_check.configure(text=tr("hide_fullscreen", self.cfg))
        self.no_media_check.configure(text=tr("hide_no_media", self.cfg))
        self.save_button.configure(text=tr("save", self.cfg))
        self.reset_button.configure(text=tr("reset", self.cfg))
        self.open_button.configure(text=tr("open", self.cfg))
        self.close_button.configure(text=tr("close", self.cfg))
        self.quit_button.configure(text=tr("quit_app", self.cfg))

    def collect(self):
        cfg = load_config()
        cfg.update({
            "always_on_top": True,
            "avoid_taskbar_overlap": bool(self.vars["avoid_taskbar_overlap"].get()),
            "hide_fullscreen": bool(self.vars["hide_fullscreen"].get()),
            "hide_when_no_media": bool(self.vars["hide_when_no_media"].get()),
            "auto_start": bool(self.vars["auto_start"].get()),
            "language": self.selected_language_code(),
        })
        return cfg

    def save_and_restart(self):
        cfg = self.collect()
        save_config(cfg)
        set_auto_start_enabled(bool(cfg.get("auto_start", False)))
        restart_overlay()
        self.cfg = cfg
        self.vars["auto_start"].set(is_auto_start_enabled())
        self.apply_language()
        self.refresh_status(tr("saved", self.cfg))

    def show_overlay(self):
        start_overlay()
        self.refresh_status(tr("opened", self.cfg))

    def hide_overlay(self):
        stop_overlay()
        self.refresh_status(tr("closed", self.cfg))

    def quit_app(self):
        self.refresh_status(tr("quitting", self.cfg))
        self.root.update_idletasks()
        stop_overlay()
        stop_tray()
        self.vars["status"].set(tr("quit_done", self.cfg))
        self.root.after(250, self.root.destroy)

    def reset_position(self):
        reset_auto_position(restart=True)
        self.cfg = load_config()
        self.apply_language()
        self.refresh_status(tr("reset_done", self.cfg))

    def refresh_status(self, prefix=""):
        hits = enum_overlay_windows()
        if hits:
            _hwnd, pid, rect, _visible = hits[0]
            text = f"{tr('running', self.cfg)} · PID {pid} · {rect}"
        else:
            text = tr("not_running", self.cfg)
        if prefix:
            text = f"{prefix} · {text}"
        self.vars["status"].set(text)

    def run(self):
        self.root.mainloop()


def cli():
    cfg = load_config()
    if "--status" in sys.argv:
        print(json.dumps({
            "running": is_overlay_running(),
            "tray_running": is_tray_running(),
            "windows": enum_overlay_windows(),
            "tray_windows": enum_tray_windows(),
            "config": cfg,
        }, ensure_ascii=False, default=str))
        return True
    if "--show" in sys.argv:
        start_overlay(); print(tr("shown", cfg)); return True
    if "--hide" in sys.argv:
        stop_overlay(); print(tr("hidden", cfg)); return True
    if "--restart" in sys.argv:
        restart_overlay(); print("restarted"); return True
    if "--reset-auto" in sys.argv:
        reset_auto_position(restart=True); print(tr("reset_cli", cfg)); return True
    if "--quit" in sys.argv:
        stop_overlay(); stop_tray(); print(tr("quit_done", cfg)); return True
    return False


if __name__ == "__main__":
    if not cli():
        SettingsWindow().run()
