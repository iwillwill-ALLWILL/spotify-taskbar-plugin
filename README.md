# Spotify Taskbar Plugin

A lightweight Windows 11 Spotify taskbar-height overlay written in Python/Win32/GDI.

It keeps the native Windows 11 taskbar intact — no ExplorerPatcher, StartAllBack, DeskBand registration, or taskbar replacement. The plugin runs as a topmost, no-activate overlay snapped to the taskbar height, with a small tray controller and settings window.

## Features

- Album art, title, artist, play/pause, previous/next
- Spotify liked-song heart button via Spotify Desktop's bundled `spotify_cli.exe`
- Smooth local-clock progress bar with a full-width bottom progress line
- Drag/resize overlay; dragging into the taskbar snaps it to taskbar height
- Hide when fullscreen apps are active
- Hide when no media is playing
- Tray controller
  - Left-click tray icon: show/hide overlay
  - Right-click tray icon: open settings directly
- Settings window with startup toggle
- Custom tray/settings icon

## Requirements

- Windows 10/11
- Spotify Desktop installed and logged in
- Python 3.11+ recommended

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

The liked-song feature uses Spotify Desktop's bundled CLI:

```text
%APPDATA%\Spotify\spotify_cli.exe
```

If that file is missing, playback UI still works through Windows GSMTC, but liked-song state/actions may be unavailable.

## Run

From this directory:

```bash
python spotify_taskbar_tray.py
```

For background/no-console startup, run with `pythonw.exe`:

```bash
pythonw spotify_taskbar_tray.py
```

Or create a desktop shortcut:

```bash
python install_desktop_shortcut.py
```

## Settings

Right-click the tray icon to open settings.

Available settings:

- 开机自启动托盘
- 拖进任务栏时自动同高
- 全屏应用时隐藏
- 没有媒体时隐藏
- 保存 / 重置位置 / 打开插件 / 关闭插件

The startup toggle writes this registry value:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\SpotifyTaskbarTrayApp
```

## Files

```text
spotify_taskbar_overlay.py    Main Win32/GDI overlay
spotify_taskbar_tray.py       Tray app/controller
spotify_taskbar_settings.py   Tk settings window and control helpers
spotify_taskbar_icon.ico      Custom icon
install_desktop_shortcut.py   Optional shortcut installer
```

Runtime config/logs are stored under:

```text
%LOCALAPPDATA%\SpotifyTaskbarOverlay\
```

They are intentionally not committed.

## Notes

This project is not affiliated with Spotify. It uses Windows media session APIs and the local Spotify Desktop CLI.
