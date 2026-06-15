# Spotify Taskbar Plugin

A lightweight Windows 11 Spotify taskbar-height mini-player written in Python + Win32/GDI.

It keeps the native Windows taskbar intact — no ExplorerPatcher, StartAllBack, DeskBand registration, or taskbar replacement. The plugin runs as a topmost no-activate overlay snapped to taskbar height, with a tray controller and a small settings window.

![icon preview](spotify_taskbar_icon_preview.png)

## Features

- Album art, title, artist, play/pause, previous/next
- Spotify liked-song heart button via Spotify Desktop's bundled `spotify_cli.exe`
- Smooth local-clock progress bar with a full-width bottom progress line
- Drag/resize overlay; dragging into the taskbar snaps it to taskbar height
- Hide when fullscreen apps are active
- Hide when no media is playing
- Tray controller
  - Left-click tray icon: show/hide overlay
  - Right-click tray icon: open settings
- Settings window with startup toggle
- Custom tray/settings icon

## Quick install

### Option A — Download ZIP

1. Open the GitHub repo page.
2. Click **Code → Download ZIP**.
3. Extract the ZIP anywhere you like.
4. Double-click:

```text
install.cmd
```

The installer will:

- create a local `.venv`
- install Python dependencies
- create a desktop shortcut
- start the tray app

### Option B — Git clone

```bash
git clone https://github.com/iwillwill-ALLWILL/spotify-taskbar-plugin.git
cd spotify-taskbar-plugin
install.cmd
```

## Requirements

- Windows 10/11
- Spotify Desktop installed and logged in
- Python 3.11+ recommended

If Python is not installed, install it from:

```text
https://www.python.org/downloads/windows/
```

Make sure **Add python.exe to PATH** is enabled during Python installation.

## Usage

After installing:

- Use the **desktop shortcut** to start the plugin
- **Left-click** the tray icon to show/hide the overlay
- **Right-click** the tray icon to open settings

Settings:

- 开机自启动托盘
- 拖进任务栏时自动同高
- 全屏应用时隐藏
- 没有媒体时隐藏
- 保存 / 重置位置 / 打开插件 / 关闭插件

## Uninstall

Double-click:

```text
uninstall.cmd
```

It will:

- stop the tray app and overlay
- remove the startup registry entry
- remove the desktop shortcut

It intentionally does **not** delete the project folder. Delete the folder manually if you no longer need it.

## Manual run

If you prefer not to use `install.cmd`, install dependencies manually:

```bash
python -m pip install -r requirements.txt
python spotify_taskbar_tray.py
```

For background/no-console startup, run with `pythonw.exe`:

```bash
pythonw spotify_taskbar_tray.py
```

## How liked songs work

The liked-song feature uses Spotify Desktop's bundled CLI:

```text
%APPDATA%\Spotify\spotify_cli.exe
```

If that file is missing, playback UI still works through Windows GSMTC, but liked-song state/actions may be unavailable.

## Files

```text
install.cmd                         One-click installer
uninstall.cmd / uninstall.py         Stop/remove startup/shortcut
start-spotify-taskbar-plugin.cmd     Start helper
install_desktop_shortcut.py          Desktop shortcut creator
spotify_taskbar_overlay.py           Main Win32/GDI overlay
spotify_taskbar_tray.py              Tray app/controller
spotify_taskbar_settings.py          Tk settings window and control helpers
spotify_taskbar_icon.ico             Custom icon
```

Runtime config/logs are stored under:

```text
%LOCALAPPDATA%\SpotifyTaskbarOverlay\
```

They are intentionally not committed.

## Notes

This project is not affiliated with Spotify. It uses Windows media session APIs and the local Spotify Desktop CLI.

## License

MIT
