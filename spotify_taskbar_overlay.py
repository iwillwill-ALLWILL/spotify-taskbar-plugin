# -*- coding: utf-8 -*-
"""
Spotify taskbar-height overlay for native Windows 11.

No ExplorerPatcher, no registry taskbar tweaks, no DeskBand/COM registration.
Runtime only: creates a child window under Shell_TrayWnd and draws with Win32/GDI.
When the process exits, the window is gone and taskbar layout/style is untouched.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import win32api
import win32con
import win32gui
import win32process

try:
    from PIL import Image, ImageFilter, ImageWin
except Exception:
    Image = None
    ImageFilter = None
    ImageWin = None

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
)

try:
    import spotify_taskbar_settings as ctl
except Exception:
    ctl = None

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_TITLE = "SpotifyTaskbarOverlay"
CLASS_NAME = "SpotifyTaskbarOverlayWin32"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SpotifyTaskbarOverlay"
LOG_PATH = APP_DIR / "overlay.log"
CONFIG_PATH = APP_DIR / "settings.json"
SETTINGS_APP = Path(__file__).with_name("spotify_taskbar_settings.py")
ICON_PATH = Path(__file__).with_name("spotify_taskbar_icon.ico")
SPOTIFY_CLI = Path(os.environ.get("APPDATA", "")) / "Spotify" / "spotify_cli.exe"

BASE_WIDTH = 520
MIN_WIDTH = 330
MIN_HEIGHT = 34
MAX_WIDTH = 1100
MAX_HEIGHT = 140
POLL_SEC = 0.50
LIKE_POLL_SEC = 2.5
REPOSITION_SEC = 3.0
UI_TIMER_MS = 250
TOPMOST_ASSERT_SEC = 1.0
PAUSED_REPAINT_SEC = 1.5
LOG_MAX_BYTES = 512 * 1024
OWNER_PID_ENV = "SPOTIFY_TASKBAR_OWNER_PID"
NO_REEXEC_ENV = "SPOTIFY_TASKBAR_NO_REEXEC"
CREATE_FLAGS_DETACHED = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x00000008  # DETACHED_PROCESS
OWNER_CHECK_SEC = 1.0

WM_APP_REFRESH = win32con.WM_APP + 10
WM_APP_REPOSITION = win32con.WM_APP + 11


def ui_text(key: str, fallback: str) -> str:
    try:
        if ctl:
            return ctl.tr(key)
    except Exception:
        pass
    return fallback


def process_is_alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        # PROCESS_QUERY_LIMITED_INFORMATION
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def relaunch_with_pythonw_if_needed() -> bool:
    return False


def rgb(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


C_BG = rgb("111111")
C_BG2 = rgb("1f1f1f")
C_BORDER = rgb("303030")
C_FG = rgb("f3f3f3")
C_MUTED = rgb("aaaaaa")
C_DIM = rgb("555555")
C_GREEN = rgb("1DB954")
C_RED = rgb("ff6b6b")


def log(*parts):
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        # Keep logs bounded. This app is long-lived and Spotify CLI timeouts can
        # otherwise grow the log forever.
        try:
            if LOG_PATH.exists() and LOG_PATH.stat().st_size > LOG_MAX_BYTES:
                old = LOG_PATH.with_suffix(".log.1")
                try:
                    old.unlink(missing_ok=True)
                except TypeError:
                    if old.exists():
                        old.unlink()
                LOG_PATH.replace(old)
        except Exception:
            pass
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(map(str, parts)) + "\n")
    except Exception:
        pass


_LAST_ERROR_LOG = {}


def log_throttled(key: str, *parts, interval: float = 30.0):
    now = time.time()
    last = _LAST_ERROR_LOG.get(key, 0.0)
    if now - last >= interval:
        _LAST_ERROR_LOG[key] = now
        log(*parts)


DEFAULT_CONFIG = {
    "auto_position": True,
    "x": None,
    "y": None,
    "width": BASE_WIDTH,
    "height": 44,
    "always_on_top": True,
    "hide_fullscreen": True,
    "hide_when_no_media": True,
    "show_widget_on_app_start": True,
    "avoid_taskbar_overlap": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
    except Exception as e:
        log("config load failed", repr(e))
    return cfg


def save_config(cfg: dict):
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        out = dict(DEFAULT_CONFIG)
        out.update(cfg or {})
        CONFIG_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log("config save failed", repr(e))


def clamp_int(value, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(value)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def enum_overlay_windows():
    hits = []

    def walk(hwnd, level=0):
        try:
            if win32gui.GetWindowText(hwnd) == APP_TITLE:
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                hits.append((hwnd, pid))
            if level < 7:
                win32gui.EnumChildWindows(hwnd, lambda c, _: (walk(c, level + 1), True)[1], None)
        except Exception:
            pass

    try:
        win32gui.EnumWindows(lambda hwnd, _: (walk(hwnd), True)[1], None)
    except Exception:
        pass
    return hits


def close_existing_instances():
    current_pid = os.getpid()
    pids = set()
    for hwnd, pid in enum_overlay_windows():
        if pid == current_pid:
            continue
        pids.add(pid)
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
    time.sleep(0.25)
    for pid in pids:
        if pid == current_pid:
            continue
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                encoding="gbk",
                errors="replace",
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass


@dataclass
class MediaState:
    title: str = "Spotify"
    artist: str = ""
    album: str = ""
    pos: float = 0.0
    dur: float = 1.0
    playing: bool = False
    has_media: bool = False
    appid: str = ""
    art_key: str = ""
    art_hash: str = ""
    art_bytes: bytes = b""
    reported_at: float = 0.0


@dataclass
class SpotifyState:
    uri: str = ""
    description: str = ""
    liked: Optional[bool] = None
    cli_ok: bool = False
    error: str = ""


def td_seconds(v) -> float:
    try:
        return max(0.0, float(v.total_seconds()))
    except Exception:
        return 0.0


def fmt_time(sec: float) -> str:
    sec = int(max(0, sec))
    return f"{sec // 60}:{sec % 60:02d}"


def playback_is_playing(status) -> bool:
    s = str(status).lower()
    if "playing" in s:
        return True
    try:
        return int(status) == 4
    except Exception:
        return False


def session_appid(session) -> str:
    for name in ("source_app_user_model_id", "SourceAppUserModelId"):
        try:
            value = getattr(session, name)
            if callable(value):
                value = value()
            return str(value or "")
        except Exception:
            pass
    return ""


_THUMB_CACHE_KEY = ""
_THUMB_CACHE_HASH = ""
_THUMB_CACHE_BYTES = b""


async def read_thumbnail_bytes(props, key: str):
    global _THUMB_CACHE_KEY, _THUMB_CACHE_HASH, _THUMB_CACHE_BYTES
    if key and key == _THUMB_CACHE_KEY:
        return _THUMB_CACHE_BYTES, _THUMB_CACHE_HASH
    thumb = getattr(props, "thumbnail", None)
    if not thumb:
        _THUMB_CACHE_KEY = key
        _THUMB_CACHE_HASH = ""
        _THUMB_CACHE_BYTES = b""
        return b"", ""
    try:
        from winrt.windows.storage.streams import DataReader
        stream = await thumb.open_read_async()
        size = int(getattr(stream, "size", 0) or 0)
        if size <= 0 or size > 5_000_000:
            return b"", ""
        reader = DataReader(stream)
        await reader.load_async(size)
        buf = bytearray(size)
        reader.read_bytes(buf)
        data = bytes(buf)
        art_hash = hashlib.sha1(data).hexdigest()[:16]
        _THUMB_CACHE_KEY = key
        _THUMB_CACHE_HASH = art_hash
        _THUMB_CACHE_BYTES = data
        return data, art_hash
    except Exception as e:
        log("thumbnail read failed", repr(e))
        return _THUMB_CACHE_BYTES if key == _THUMB_CACHE_KEY else b"", _THUMB_CACHE_HASH if key == _THUMB_CACHE_KEY else ""


async def choose_media_session():
    mgr = await MediaManager.request_async()
    if not mgr:
        return None
    try:
        sessions = list(mgr.get_sessions())
    except Exception:
        sessions = []

    spotify_playing = None
    any_playing = None
    spotify_any = None
    for s in sessions:
        appid = session_appid(s).lower()
        is_spotify = "spotify" in appid
        try:
            playing = playback_is_playing(s.get_playback_info().playback_status)
        except Exception:
            playing = False
        if is_spotify and playing:
            spotify_playing = s
            break
        if playing and any_playing is None:
            any_playing = s
        if is_spotify and spotify_any is None:
            spotify_any = s
    return spotify_playing or any_playing or spotify_any or mgr.get_current_session()


async def read_media_state() -> MediaState:
    session = await choose_media_session()
    if not session:
        return MediaState(title=ui_text("not_running", "No media"), dur=1.0, has_media=False)
    props = await session.try_get_media_properties_async()
    timeline = session.get_timeline_properties()
    playback = session.get_playback_info()
    dur = td_seconds(timeline.end_time - timeline.start_time)
    pos = td_seconds(timeline.position)
    title = str(props.title or "Spotify")
    artist = str(props.artist or props.album_artist or "")
    album = str(getattr(props, "album_title", "") or "")
    appid = session_appid(session)
    art_key = f"{appid}|{title}|{artist}|{album}"
    art_bytes, art_hash = await read_thumbnail_bytes(props, art_key)
    return MediaState(
        title=title,
        artist=artist,
        album=album,
        pos=pos,
        dur=max(dur, 1.0),
        playing=playback_is_playing(playback.playback_status),
        has_media=bool(title and title != "Spotify") or bool(artist),
        appid=appid,
        art_key=art_key,
        art_hash=art_hash,
        art_bytes=art_bytes,
        reported_at=time.perf_counter(),
    )


async def media_command(cmd: str) -> bool:
    session = await choose_media_session()
    if not session:
        return False
    if cmd == "prev":
        return bool(await session.try_skip_previous_async())
    if cmd == "next":
        return bool(await session.try_skip_next_async())
    if cmd == "playpause":
        return bool(await session.try_toggle_play_pause_async())
    return False


async def seek_to_ratio(ratio: float) -> bool:
    session = await choose_media_session()
    if not session:
        return False
    timeline = session.get_timeline_properties()
    dur = td_seconds(timeline.end_time - timeline.start_time)
    if dur <= 1:
        return False
    try:
        return bool(await session.try_change_playback_position_async(int(max(0, min(1, ratio)) * dur * 10_000_000)))
    except Exception as e:
        log("seek failed", repr(e))
        return False


def spotify_cli_json(*args: str, timeout: float = 5.0) -> dict:
    if not SPOTIFY_CLI.exists():
        raise FileNotFoundError(str(SPOTIFY_CLI))
    cp = subprocess.run(
        [str(SPOTIFY_CLI), *args, "--format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or "spotify_cli failed").strip())
    out = (cp.stdout or "").strip()
    return json.loads(out) if out else {}


def read_spotify_state() -> SpotifyState:
    st = SpotifyState()
    try:
        data = spotify_cli_json("now-playing", timeout=1.5)
        cur = data.get("currently_playing") or {}
        st.uri = cur.get("uri") or ""
        st.description = cur.get("description") or ""
        st.cli_ok = True
        if st.uri:
            contains = spotify_cli_json("library", "contains", st.uri, timeout=1.5)
            st.liked = bool((contains.get("contains") or {}).get(st.uri))
    except Exception as e:
        st.error = str(e)
        log_throttled("spotify-state", "spotify state failed", repr(e), interval=30.0)
    return st


def set_spotify_liked(uri: str, liked: bool) -> bool:
    if not uri:
        return False
    if not SPOTIFY_CLI.exists():
        raise FileNotFoundError(str(SPOTIFY_CLI))
    cp = subprocess.run(
        [str(SPOTIFY_CLI), "library", "add" if liked else "remove", uri],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=6,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or "spotify_cli library update failed").strip())
    return True


def find_child_recursive(parent: int, class_names: tuple[str, ...]) -> Optional[int]:
    found = None

    def enum_cb(hwnd, _):
        nonlocal found
        try:
            if win32gui.GetClassName(hwnd) in class_names:
                found = hwnd
                return False
            win32gui.EnumChildWindows(hwnd, enum_cb, None)
        except Exception:
            pass
        return found is None

    try:
        win32gui.EnumChildWindows(parent, enum_cb, None)
    except Exception:
        pass
    return found


def get_taskbar_layout():
    tb = win32gui.FindWindow("Shell_TrayWnd", None)
    if not tb:
        sw = win32api.GetSystemMetrics(0)
        sh = win32api.GetSystemMetrics(1)
        return None, (0, sh - 48, sw, sh), None
    tb_rect = win32gui.GetWindowRect(tb)
    # On native Windows 11, Shell_TrayWnd contains a full-width XAML bridge
    # above classic child windows. Parenting to Shell_TrayWnd can paint behind it.
    host = find_child_recursive(tb, ("Windows.UI.Composition.DesktopWindowContentBridge", "XamlExplorerHostIslandWindow")) or tb
    task = find_child_recursive(tb, ("MSTaskSwWClass", "MSTaskListWClass"))
    task_rect = None
    if task:
        try:
            r = win32gui.GetWindowRect(task)
            if r[2] > r[0] and r[3] > r[1]:
                task_rect = r
        except Exception:
            pass
    return host, tb_rect, task_rect


def foreground_is_fullscreen() -> bool:
    try:
        fg = win32gui.GetForegroundWindow()
        if not fg:
            return False
        title = win32gui.GetWindowText(fg)
        cls = win32gui.GetClassName(fg)
        if title == APP_TITLE or cls in {"Shell_TrayWnd", "WorkerW", "Progman"}:
            return False
        rect = win32gui.GetWindowRect(fg)
        mon = win32api.MonitorFromWindow(fg, win32con.MONITOR_DEFAULTTONEAREST)
        mr = win32api.GetMonitorInfo(mon).get("Monitor")
        return rect[0] <= mr[0] + 2 and rect[1] <= mr[1] + 2 and rect[2] >= mr[2] - 2 and rect[3] >= mr[3] - 2
    except Exception:
        return False


class OverlayApp:
    def __init__(self):
        self.hwnd = None
        self.parent = None
        self.media = MediaState()
        self.spotify = SpotifyState()
        self.lock = threading.Lock()
        self.running = True
        self.hover = ""
        self.regions: dict[str, tuple[int, int, int, int]] = {}
        self.geometry = (0, 0, BASE_WIDTH, 40)
        self.last_like_poll = 0.0
        self.last_reposition = 0.0
        self.visible = True
        self.font_main = None
        self.font_small = None
        self.font_icon = None
        self.config = load_config()
        self.drag_mode: Optional[str] = None
        self.drag_start_cursor = (0, 0)
        self.drag_start_geometry = (0, 0, BASE_WIDTH, 44)
        self.last_cursor = None
        self.art_hash = ""
        self.art_size = 0
        self.art_dib = None
        self.force_spotify_poll = True
        self.last_timer_repaint = 0.0
        self.last_topmost_assert = 0.0
        try:
            self.owner_pid = int(os.environ.get(OWNER_PID_ENV, "0") or 0)
        except Exception:
            self.owner_pid = 0
        self.last_owner_check = 0.0

    def make_font(self, height: int, face: str, weight=win32con.FW_NORMAL):
        lf = win32gui.LOGFONT()
        lf.lfHeight = height
        lf.lfWeight = weight
        lf.lfCharSet = win32con.DEFAULT_CHARSET
        lf.lfOutPrecision = win32con.OUT_DEFAULT_PRECIS
        lf.lfClipPrecision = win32con.CLIP_DEFAULT_PRECIS
        lf.lfQuality = win32con.CLEARTYPE_QUALITY
        lf.lfPitchAndFamily = win32con.DEFAULT_PITCH
        lf.lfFaceName = face
        return win32gui.CreateFontIndirect(lf)

    def create_fonts(self):
        self.font_main = self.make_font(-14, "Microsoft YaHei UI")
        self.font_small = self.make_font(-11, "Segoe UI")
        self.font_icon = self.make_font(-18, "Segoe UI Symbol")

    def register_class(self):
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = CLASS_NAME
        wc.lpfnWndProc = self.wndproc
        wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        try:
            if ICON_PATH.exists():
                icon = win32gui.LoadImage(0, str(ICON_PATH), win32con.IMAGE_ICON, 0, 0, win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
                wc.hIcon = icon
        except Exception:
            pass
        wc.hbrBackground = win32gui.GetStockObject(win32con.BLACK_BRUSH)
        try:
            return win32gui.RegisterClass(wc)
        except win32gui.error:
            return None

    def compute_geometry(self):
        cfg = load_config()
        self.config = cfg
        if not cfg.get("auto_position", True) and cfg.get("x") is not None and cfg.get("y") is not None:
            w = clamp_int(cfg.get("width"), BASE_WIDTH, MIN_WIDTH, MAX_WIDTH)
            h = clamp_int(cfg.get("height"), 44, MIN_HEIGHT, MAX_HEIGHT)
            x = clamp_int(cfg.get("x"), 100, -10000, 10000)
            y = clamp_int(cfg.get("y"), 100, -10000, 10000)
            orig = (x, y, w, h)
            x, y, w, h = self.avoid_taskbar_overlap_rect(x, y, w, h)
            if (x, y, w, h) != orig:
                cfg.update({"x": int(x), "y": int(y), "width": int(w), "height": int(h)})
                save_config(cfg)
            return None, x, y, w, h

        _host_hwnd, tb, task = get_taskbar_layout()
        tb_l, tb_t, tb_r, tb_b = tb
        tb_w, tb_h = tb_r - tb_l, tb_b - tb_t
        horizontal = tb_w >= tb_h
        if not horizontal:
            w = 420
            h = 42
            return None, tb_l + tb_w + 4, tb_t + 80, w, h
        # Reset/auto-position should follow the user's preferred taskbar mode:
        # live inside the taskbar and match its height.
        h = max(MIN_HEIGHT, min(MAX_HEIGHT, tb_h))
        w = min(BASE_WIDTH, max(MIN_WIDTH, int(tb_w * 0.34)))
        y = tb_t
        if task:
            task_l, _task_t, _task_r, _task_b = task
            left_space = task_l - tb_l - 12
            if left_space >= MIN_WIDTH:
                w = min(w, left_space)
                x = task_l - w - 8
            else:
                x = tb_l + 8
                w = min(w, max(260, left_space)) if left_space > 260 else min(w, 320)
        else:
            x = tb_l + max(8, int(tb_w * 0.08))
        x = max(tb_l + 4, min(x, tb_r - w - 4))
        return None, int(x), int(y), int(w), int(h)

    def create_window(self):
        self.create_fonts()
        self.register_class()
        parent_hwnd, x, y, w, h = self.compute_geometry()
        self.parent = None
        self.geometry = (x, y, w, h)
        self.hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE,
            CLASS_NAME,
            APP_TITLE,
            win32con.WS_POPUP | win32con.WS_VISIBLE,
            x,
            y,
            w,
            h,
            0,
            0,
            win32api.GetModuleHandle(None),
            None,
        )
        win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, x, y, w, h, win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)
        ctypes.windll.user32.SetTimer(int(self.hwnd), 1, UI_TIMER_MS, 0)
        win32gui.InvalidateRect(self.hwnd, None, True)
        win32gui.UpdateWindow(self.hwnd)
        log("created", "hwnd", self.hwnd, "parent", parent_hwnd, "screen", self.geometry, "spotify_cli", SPOTIFY_CLI)

    def reposition(self):
        if not self.hwnd:
            return
        _parent_hwnd, x, y, w, h = self.compute_geometry()
        self.geometry = (x, y, w, h)
        z = win32con.HWND_TOPMOST if bool(self.config.get("always_on_top", True)) else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(self.hwnd, z, x, y, w, h, win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)
        win32gui.InvalidateRect(self.hwnd, None, True)
        win32gui.UpdateWindow(self.hwnd)

    def close_if_owner_gone(self) -> bool:
        if not self.owner_pid:
            return False
        now = time.perf_counter()
        if now - self.last_owner_check < OWNER_CHECK_SEC:
            return False
        self.last_owner_check = now
        owner_alive = process_is_alive(self.owner_pid)
        tray_window_alive = True
        try:
            if ctl and hasattr(ctl, "is_tray_running"):
                tray_window_alive = bool(ctl.is_tray_running())
        except Exception:
            tray_window_alive = True
        if owner_alive and tray_window_alive:
            return False
        log("owner/tray gone; closing overlay", "owner_pid", self.owner_pid, "owner_alive", owner_alive, "tray_window_alive", tray_window_alive)
        try:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            self.running = False
        return True

    def persist_geometry(self):
        x, y, w, h = self.geometry
        self.config.update({
            "auto_position": False,
            "x": int(x),
            "y": int(y),
            "width": int(w),
            "height": int(h),
        })
        save_config(self.config)

    def avoid_taskbar_overlap_rect(self, x, y, w, h):
        if not bool(self.config.get("avoid_taskbar_overlap", True)):
            return int(x), int(y), int(w), int(h)
        try:
            _host, tb, _task = get_taskbar_layout()
            tb_l, tb_t, tb_r, tb_b = tb
            tb_w, tb_h = tb_r - tb_l, tb_b - tb_t
            horizontal = tb_w >= tb_h
            if horizontal:
                # User wants to drag it into the taskbar. Native Win11 still owns
                # that z-band, so make a taskbar-height topmost overlay and keep
                # aggressively re-asserting topmost during refresh.
                overlaps_taskbar = (y + h > tb_t) and (y < tb_b)
                if overlaps_taskbar:
                    h = tb_h
                    y = tb_t
                x = max(tb_l + 4, min(int(x), tb_r - int(w) - 4))
            else:
                overlaps_taskbar = (x < tb_r) and (x + w > tb_l)
                if overlaps_taskbar:
                    w = tb_w
                    x = tb_l
                    y = max(tb_t + 4, min(int(y), tb_b - int(h) - 4))
        except Exception:
            pass
        return int(x), int(y), int(w), int(h)

    def reset_auto_position(self):
        self.config.update({"auto_position": True})
        save_config(self.config)
        self.reposition()

    def open_settings(self):
        try:
            pyw = Path(sys.executable).with_name("pythonw.exe")
            exe = str(pyw if pyw.exists() else sys.executable)
            subprocess.Popen([exe, str(SETTINGS_APP)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:
            log("open settings failed", repr(e))

    def update_visibility(self):
        hide = bool(self.config.get("hide_fullscreen", True)) and foreground_is_fullscreen()
        with self.lock:
            if bool(self.config.get("hide_when_no_media", True)) and not self.media.has_media and not self.spotify.description:
                hide = True
        if hide and self.visible:
            win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
            self.visible = False
        elif not hide and not self.visible:
            win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNOACTIVATE)
            self.visible = True
            self.reposition()

    def media_loop(self):
        while self.running:
            try:
                media = asyncio.run(read_media_state())
                with self.lock:
                    old = self.media
                    old_key = old.art_key
                    old_title = (old.title, old.artist, old.album)
                    new_title = (media.title, media.artist, media.album)
                    same_track = media.art_key == old.art_key and new_title == old_title and media.has_media and old.has_media
                    if same_track and media.playing and old.playing:
                        # GSMTC/Spotify often returns the same raw timeline.position
                        # for several seconds. Do not reset the local smoothing anchor
                        # to that stale raw value; carry the displayed position forward.
                        smooth_now = self.display_pos(old)
                        if media.pos < smooth_now + 0.75:
                            media.pos = smooth_now
                            media.reported_at = time.perf_counter()
                        elif media.pos > smooth_now + 4.0:
                            # Real seek / track correction: trust the new raw sample.
                            media.reported_at = time.perf_counter()
                        else:
                            # Small forward correction from GSMTC, accept it.
                            media.reported_at = time.perf_counter()
                    self.media = media
                    if media.art_key != old_key or new_title != old_title:
                        self.force_spotify_poll = True
            except Exception as e:
                log("media read failed", repr(e))
            now = time.time()
            if self.hwnd:
                try:
                    win32gui.PostMessage(self.hwnd, WM_APP_REFRESH, 0, 0)
                    if now - self.last_reposition >= REPOSITION_SEC:
                        self.last_reposition = now
                        win32gui.PostMessage(self.hwnd, WM_APP_REPOSITION, 0, 0)
                except Exception:
                    pass
            time.sleep(POLL_SEC)

    def spotify_loop(self):
        while self.running:
            now = time.time()
            do_poll = False
            with self.lock:
                if self.force_spotify_poll or now - self.last_like_poll >= LIKE_POLL_SEC:
                    self.force_spotify_poll = False
                    self.last_like_poll = now
                    do_poll = True
            if do_poll:
                try:
                    spotify = read_spotify_state()
                    with self.lock:
                        self.spotify = spotify
                except Exception as e:
                    log("spotify poll failed", repr(e))
                if self.hwnd:
                    try:
                        win32gui.PostMessage(self.hwnd, WM_APP_REFRESH, 0, 0)
                    except Exception:
                        pass
            time.sleep(0.25)

    def start_workers(self):
        threading.Thread(target=self.media_loop, daemon=True).start()
        threading.Thread(target=self.spotify_loop, daemon=True).start()

    def text(self, hdc, s, rect, color=C_FG, font=None, flags=None):
        if flags is None:
            flags = win32con.DT_LEFT | win32con.DT_VCENTER | win32con.DT_SINGLELINE | win32con.DT_END_ELLIPSIS
        old_font = win32gui.SelectObject(hdc, font or self.font_main)
        win32gui.SetTextColor(hdc, color)
        win32gui.SetBkMode(hdc, win32con.TRANSPARENT)
        win32gui.DrawText(hdc, str(s), -1, rect, flags)
        win32gui.SelectObject(hdc, old_font)

    def fill(self, hdc, rect, color):
        brush = win32gui.CreateSolidBrush(color)
        win32gui.FillRect(hdc, rect, brush)
        win32gui.DeleteObject(brush)

    def add_region(self, name, rect):
        self.regions[name] = rect

    def prepare_art(self, media: MediaState, target_size: int):
        if not Image or not ImageWin or not media.art_bytes:
            if not media.art_bytes:
                self.art_hash = ""
                self.art_size = 0
                self.art_dib = None
            return
        target_size = max(1, int(target_size or 1))
        art_hash = media.art_hash or hashlib.sha1(media.art_bytes).hexdigest()[:16]
        if art_hash == self.art_hash and target_size == self.art_size and self.art_dib is not None:
            return
        try:
            img = Image.open(io.BytesIO(media.art_bytes)).convert("RGB")
            # Square crop center, then downsample with Pillow's high-quality
            # filter. Letting ImageWin/GDI shrink a 300px+ cover into a tiny
            # taskbar-height square uses a poor stretch mode and turns detailed
            # covers into noisy speckles.
            w, h = img.size
            side = min(w, h)
            if side > 0:
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
            if img.size != (target_size, target_size):
                if ImageFilter and target_size <= 72 and max(img.size) / max(target_size, 1) >= 3:
                    img = img.filter(ImageFilter.GaussianBlur(0.55))
                resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", getattr(Image, "LANCZOS", 1))
                img = img.resize((target_size, target_size), resample)
            self.art_dib = ImageWin.Dib(img)
            self.art_hash = art_hash
            self.art_size = target_size
        except Exception as e:
            log("prepare art failed", repr(e))
            self.art_hash = ""
            self.art_size = 0
            self.art_dib = None

    def draw_art(self, hdc, rect, media: MediaState):
        size = max(1, min(int(rect[2] - rect[0]), int(rect[3] - rect[1])))
        self.prepare_art(media, size)
        if self.art_dib is not None:
            try:
                self.art_dib.draw(hdc, rect)
                return True
            except Exception as e:
                log("draw art failed", repr(e))
        return False

    def draw_button(self, hdc, name, label, rect, color=C_FG):
        self.fill(hdc, rect, C_BG2 if self.hover == name else C_BG)
        self.text(hdc, label, rect, color=color, font=self.font_icon, flags=win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE)
        self.add_region(name, rect)

    def display_pos(self, media: MediaState) -> float:
        pos = float(media.pos or 0.0)
        dur = max(float(media.dur or 1.0), 1.0)
        if media.playing and media.reported_at:
            # Spotify/GSMTC reports timeline.position in coarse jumps. Smooth it
            # locally between authoritative samples so the progress bar tracks
            # real playback instead of waiting for the next GSMTC jump.
            pos += max(0.0, time.perf_counter() - media.reported_at)
        return max(0.0, min(dur, pos))

    def paint(self):
        paint_hdc, ps = win32gui.BeginPaint(self.hwnd)
        mem_dc = None
        mem_bmp = None
        old_bmp = None
        w = h = 0
        try:
            _x, _y, w, h = self.geometry
            mem_dc = win32gui.CreateCompatibleDC(paint_hdc)
            mem_bmp = win32gui.CreateCompatibleBitmap(paint_hdc, int(w), int(h))
            old_bmp = win32gui.SelectObject(mem_dc, mem_bmp)
            hdc = mem_dc
            self.regions.clear()
            self.fill(hdc, (0, 0, w, h), C_BG)
            self.fill(hdc, (0, 0, w, 1), C_BORDER)
            self.fill(hdc, (0, h - 1, w, h), C_BORDER)

            with self.lock:
                media = self.media
                spotify = self.spotify

            pad = 6
            art = max(24, h - 12)
            art_y = (h - art) // 2
            art_rect = (pad, art_y, pad + art, art_y + art)
            if not self.draw_art(hdc, art_rect, media):
                self.fill(hdc, art_rect, rgb("252525"))
                self.text(hdc, "♪", art_rect, color=C_GREEN, font=self.font_icon, flags=win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE)

            controls_w = 4 * 34
            time_w = 76
            text_x = pad + art + 8
            controls_x = w - pad - controls_w
            text_right = controls_x - time_w - 8

            title, artist = media.title, media.artist
            if not media.has_media and spotify.description:
                if " — " in spotify.description:
                    title, artist = spotify.description.split(" — ", 1)
                else:
                    title, artist = spotify.description, ""
            line = title if not artist else f"{title} — {artist}"
            self.text(hdc, line, (text_x, 3, max(text_x + 40, text_right), h // 2 + 4), C_FG, self.font_main)

            app_hint = "Spotify" if ("spotify" in media.appid.lower() or spotify.uri) else ui_text("media", "Media")
            self.text(hdc, app_hint, (text_x, h // 2 + 4, text_x + 44, h - 2), C_MUTED, self.font_small)

            prog_x1 = text_x + 48
            prog_x2 = max(prog_x1, text_right)
            prog_y = h - 10
            display_pos = self.display_pos(media)
            ratio = max(0.0, min(1.0, display_pos / media.dur if media.dur else 0.0))
            if prog_x2 - prog_x1 > 20:
                self.fill(hdc, (prog_x1, prog_y, prog_x2, prog_y + 3), C_DIM)
                self.fill(hdc, (prog_x1, prog_y, prog_x1 + int((prog_x2 - prog_x1) * ratio), prog_y + 3), C_GREEN)
                self.add_region("seek", (prog_x1, prog_y - 5, prog_x2, prog_y + 8))

            self.text(hdc, f"{fmt_time(display_pos)}/{fmt_time(media.dur)}", (text_right + 4, 0, controls_x - 4, h), C_MUTED, self.font_small, flags=win32con.DT_RIGHT | win32con.DT_VCENTER | win32con.DT_SINGLELINE)

            bx = controls_x
            self.draw_button(hdc, "like", "♥" if spotify.liked else "♡", (bx, 3, bx + 32, h - 3), C_GREEN if spotify.liked else (C_RED if spotify.error else C_FG))
            bx += 34
            self.draw_button(hdc, "prev", "⏮", (bx, 3, bx + 32, h - 3))
            bx += 34
            self.draw_button(hdc, "playpause", "⏸" if media.playing else "▶", (bx, 3, bx + 32, h - 3))
            bx += 34
            self.draw_button(hdc, "next", "⏭", (bx, 3, bx + 32, h - 3))
            # Full-width bottom progress: the compact in-row bar is too short for
            # long tracks, so it may only move one pixel every few seconds.
            self.fill(hdc, (0, h - 3, w, h - 1), C_DIM)
            self.fill(hdc, (0, h - 3, int(w * ratio), h - 1), C_GREEN)
            # Small resize grip; drag any empty area to move, drag the lower-right corner to resize.
            self.fill(hdc, (w - 15, h - 3, w - 3, h - 1), C_DIM)
            self.fill(hdc, (w - 10, h - 7, w - 3, h - 5), C_DIM)
            self.fill(hdc, (w - 5, h - 11, w - 3, h - 9), C_DIM)
        finally:
            try:
                if mem_dc and mem_bmp and w and h:
                    win32gui.BitBlt(paint_hdc, 0, 0, int(w), int(h), mem_dc, 0, 0, win32con.SRCCOPY)
            finally:
                try:
                    if mem_dc and old_bmp:
                        win32gui.SelectObject(mem_dc, old_bmp)
                    if mem_bmp:
                        win32gui.DeleteObject(mem_bmp)
                    if mem_dc:
                        win32gui.DeleteDC(mem_dc)
                finally:
                    win32gui.EndPaint(self.hwnd, ps)

    def hit(self, x, y):
        for name, (l, t, r, b) in self.regions.items():
            if l <= x <= r and t <= y <= b:
                return name
        return ""

    def hit_test_nonclient(self, hwnd, lparam):
        sx = ctypes.c_short(lparam & 0xFFFF).value
        sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        try:
            x, y = win32gui.ScreenToClient(hwnd, (sx, sy))
        except Exception:
            return win32con.HTCLIENT
        name = self.hit(x, y)
        if name in {"like", "prev", "playpause", "next", "seek"}:
            return win32con.HTCLIENT
        _gx, _gy, w, h = self.geometry
        right = x >= w - 12
        bottom = y >= h - 10
        left = x <= 4
        top = y <= 4
        if right and bottom:
            return win32con.HTBOTTOMRIGHT
        if left and bottom:
            return win32con.HTBOTTOMLEFT
        if right and top:
            return win32con.HTTOPRIGHT
        if left and top:
            return win32con.HTTOPLEFT
        if right:
            return win32con.HTRIGHT
        if bottom:
            return win32con.HTBOTTOM
        if left:
            return win32con.HTLEFT
        if top:
            return win32con.HTTOP
        return win32con.HTCAPTION

    def persist_current_rect(self):
        try:
            l, t, r, b = win32gui.GetWindowRect(self.hwnd)
            x, y, w, h = self.avoid_taskbar_overlap_rect(l, t, r - l, b - t)
            self.geometry = (x, y, w, h)
            win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, x, y, w, h, win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)
            self.persist_geometry()
        except Exception:
            pass

    def edge_hit(self, x, y):
        _gx, _gy, w, h = self.geometry
        right = x >= w - 14
        bottom = y >= h - 12
        if right and bottom:
            return "resize"
        return ""

    def set_cursor_for(self, x, y, hit_name=""):
        if hit_name in {"like", "prev", "playpause", "next", "seek"}:
            cursor = win32con.IDC_HAND
        elif self.edge_hit(x, y) == "resize":
            cursor = win32con.IDC_SIZENWSE
        else:
            cursor = win32con.IDC_SIZEALL
        if cursor != self.last_cursor:
            self.last_cursor = cursor
            try:
                win32gui.SetCursor(win32gui.LoadCursor(0, cursor))
            except Exception:
                pass

    def begin_drag_or_resize(self, x, y):
        name = self.hit(x, y)
        if name in {"like", "prev", "playpause", "next", "seek"}:
            return False
        self.drag_mode = self.edge_hit(x, y) or "move"
        self.drag_start_cursor = win32gui.GetCursorPos()
        self.drag_start_geometry = self.geometry
        try:
            win32gui.SetCapture(self.hwnd)
        except Exception:
            pass
        return True

    def apply_drag(self):
        if not self.drag_mode:
            return
        cx, cy = win32gui.GetCursorPos()
        sx, sy = self.drag_start_cursor
        gx, gy, gw, gh = self.drag_start_geometry
        dx, dy = cx - sx, cy - sy
        if self.drag_mode == "resize":
            w = clamp_int(gw + dx, BASE_WIDTH, MIN_WIDTH, MAX_WIDTH)
            h = clamp_int(gh + dy, 44, MIN_HEIGHT, MAX_HEIGHT)
            x, y = gx, gy
        else:
            x, y, w, h = gx + dx, gy + dy, gw, gh
        x, y, w, h = self.avoid_taskbar_overlap_rect(x, y, w, h)
        self.geometry = (int(x), int(y), int(w), int(h))
        win32gui.SetWindowPos(self.hwnd, win32con.HWND_TOPMOST, int(x), int(y), int(w), int(h), win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)
        win32gui.InvalidateRect(self.hwnd, None, True)
        win32gui.UpdateWindow(self.hwnd)

    def end_drag(self):
        if not self.drag_mode:
            return False
        self.apply_drag()
        self.drag_mode = None
        try:
            win32gui.ReleaseCapture()
        except Exception:
            pass
        self.persist_geometry()
        return True

    def do_media_cmd(self, cmd):
        def worker():
            try:
                asyncio.run(media_command(cmd))
            except Exception as e:
                log("cmd failed", cmd, repr(e))
        threading.Thread(target=worker, daemon=True).start()

    def do_seek(self, x):
        rect = self.regions.get("seek")
        if not rect:
            return
        l, _t, r, _b = rect
        ratio = (x - l) / max(1, r - l)
        def worker():
            try:
                asyncio.run(seek_to_ratio(ratio))
            except Exception as e:
                log("seek worker failed", repr(e))
        threading.Thread(target=worker, daemon=True).start()

    def toggle_like(self):
        with self.lock:
            uri = self.spotify.uri
            target = not bool(self.spotify.liked)
            self.spotify.liked = target
        win32gui.InvalidateRect(self.hwnd, None, True)
        if not uri:
            return
        def worker():
            ok = False
            err = ""
            try:
                ok = set_spotify_liked(uri, target)
            except Exception as e:
                err = str(e)
                log("like failed", repr(e))
            with self.lock:
                if ok:
                    self.spotify.liked = target
                    self.spotify.error = ""
                else:
                    self.spotify.liked = not target
                    self.spotify.error = err
                # Force fresh state soon.
                self.last_like_poll = 0
                self.force_spotify_poll = True
            try:
                win32gui.PostMessage(self.hwnd, WM_APP_REFRESH, 0, 0)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def show_context_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, 1, ui_text("reset", "Reset position"))
        win32gui.AppendMenu(menu, win32con.MF_STRING, 2, ui_text("refresh_like", "Refresh liked state"))
        win32gui.AppendMenu(menu, win32con.MF_STRING, 4, ui_text("settings_title", "Settings"))
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, None)
        win32gui.AppendMenu(menu, win32con.MF_STRING, 3, ui_text("exit_overlay", "Exit overlay"))
        x, y = win32gui.GetCursorPos()
        cmd = win32gui.TrackPopupMenu(menu, win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON, x, y, 0, self.hwnd, None)
        if cmd == 1:
            self.reset_auto_position()
        elif cmd == 2:
            self.last_like_poll = 0
        elif cmd == 4:
            self.open_settings()
        elif cmd == 3:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)

    def wndproc(self, hwnd, msg, wparam, lparam):
        # Keep the whole borderless popup as client area. We implement drag/resize
        # manually below; returning HTCAPTION/HT* here lets Windows perform native
        # moves and produced unstable coordinates around the Win11 taskbar z-band.
        if msg == win32con.WM_NCHITTEST:
            return win32con.HTCLIENT
        if msg == win32con.WM_PAINT:
            self.paint()
            return 0
        if msg == win32con.WM_ERASEBKGND:
            return 1
        if msg == win32con.WM_MOUSEACTIVATE:
            return win32con.MA_NOACTIVATE
        if msg == win32con.WM_MOUSEMOVE:
            x = lparam & 0xFFFF
            y = (lparam >> 16) & 0xFFFF
            if self.drag_mode:
                self.apply_drag()
                return 0
            name = self.hit(x, y)
            self.set_cursor_for(x, y, name)
            if name != self.hover:
                self.hover = name
                win32gui.InvalidateRect(hwnd, None, False)
            return 0
        if msg == win32con.WM_LBUTTONDOWN:
            x = lparam & 0xFFFF
            y = (lparam >> 16) & 0xFFFF
            if self.begin_drag_or_resize(x, y):
                return 0
        if msg == win32con.WM_LBUTTONUP:
            if self.end_drag():
                return 0
            x = lparam & 0xFFFF
            y = (lparam >> 16) & 0xFFFF
            name = self.hit(x, y)
            if name == "like":
                self.toggle_like()
            elif name in {"prev", "playpause", "next"}:
                self.do_media_cmd(name)
            elif name == "seek":
                self.do_seek(x)
            return 0
        if msg == win32con.WM_RBUTTONUP:
            self.show_context_menu()
            return 0
        if msg == win32con.WM_CAPTURECHANGED:
            self.drag_mode = None
            return 0
        if msg == win32con.WM_TIMER:
            if self.close_if_owner_gone():
                return 0
            if self.visible:
                now = time.perf_counter()
                if now - self.last_topmost_assert >= TOPMOST_ASSERT_SEC:
                    self.last_topmost_assert = now
                    try:
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_NOOWNERZORDER | win32con.SWP_SHOWWINDOW)
                    except Exception:
                        pass
                with self.lock:
                    playing = bool(self.media.playing)
                if playing or now - self.last_timer_repaint >= PAUSED_REPAINT_SEC:
                    self.last_timer_repaint = now
                    win32gui.InvalidateRect(hwnd, None, False)
                    win32gui.UpdateWindow(hwnd)
            return 0
        if msg == WM_APP_REFRESH:
            self.update_visibility()
            if bool(self.config.get("always_on_top", True)) and self.visible:
                now = time.perf_counter()
                if now - self.last_topmost_assert >= TOPMOST_ASSERT_SEC:
                    self.last_topmost_assert = now
                    try:
                        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_NOOWNERZORDER)
                    except Exception:
                        pass
            win32gui.InvalidateRect(hwnd, None, False)
            win32gui.UpdateWindow(hwnd)
            return 0
        if msg == WM_APP_REPOSITION:
            self.reposition()
            return 0
        if msg == win32con.WM_CLOSE:
            self.running = False
            try:
                ctypes.windll.user32.KillTimer(int(hwnd), 1)
            except Exception:
                pass
            win32gui.DestroyWindow(hwnd)
            return 0
        if msg == win32con.WM_DESTROY:
            self.running = False
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def run(self):
        self.create_window()
        self.start_workers()
        win32gui.PumpMessages()
        self.running = False


if __name__ == "__main__":
    if relaunch_with_pythonw_if_needed():
        sys.exit(0)
    close_existing_instances()
    app = OverlayApp()
    app.run()
