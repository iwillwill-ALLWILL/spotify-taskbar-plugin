# Spotify Taskbar Overlay

A lightweight Windows 11 Spotify taskbar widget / plugin-style mini player written in Python + Win32/GDI.

If you searched for a **Spotify taskbar plugin**, **Spotify taskbar widget**, **Spotify mini player for Windows 11**, or **Spotify overlay with liked songs**, this is the kind of app you're looking for.

> Naming note: technically this is an **overlay**, not a native Windows DeskBand/taskbar plugin. It does not patch or replace the Windows taskbar. The repo keeps `spotify-taskbar-plugin` in the URL because that is what many people search for, but the accurate product name is **Spotify Taskbar Overlay**.

It keeps the native Windows taskbar intact — no ExplorerPatcher, StartAllBack, DeskBand registration, or taskbar replacement. The app runs as a topmost no-activate overlay snapped to taskbar height, with a tray controller and a small settings window.

**Search keywords:** Spotify taskbar plugin, Spotify taskbar widget, Spotify Windows 11 mini player, Spotify taskbar overlay, Spotify liked songs widget, Windows media controls overlay.

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
- Language: Auto / 中文 / English
- Custom tray/settings icon

## Language / 语言

The UI supports Chinese and English.

- Default: **Auto** — follows your Windows UI language
- Manual switch: open Settings → Language → choose `中文` or `English` → Save

界面支持中文和英文。

- 默认：**自动** — 跟随 Windows 系统语言
- 手动切换：右键托盘图标打开设置 → 语言 → 选择 `中文` 或 `English` → 保存

## Quick install

### Option A — Download ZIP

1. Open the GitHub repo page.
2. Click **Code → Download ZIP**, or download the release ZIP.
3. Extract the ZIP anywhere you like.
4. Double-click:

```text
install.cmd
```

The installer will:

- create a local `.venv`
- install Python dependencies
- create a desktop shortcut
- start the tray app through a hidden launcher, so no terminal window stays on the taskbar

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

- Use the **desktop shortcut** to start the overlay
- **Left-click** the tray icon to show/hide the overlay
- **Right-click** the tray icon to open settings

Settings:

English:

- Language
- Start tray app on login
- Snap to taskbar height when dragged into taskbar
- Hide when fullscreen app is active
- Hide when no media is playing
- Save / Reset position / Show overlay / Hide overlay / Exit app

中文：

- 语言
- 开机自启动托盘
- 拖进任务栏时自动同高
- 全屏应用时隐藏
- 没有媒体时隐藏
- 保存 / 重置位置 / 打开悬浮窗 / 关闭悬浮窗 / 退出插件

Notes:

- The desktop shortcut and `start-spotify-taskbar-plugin.cmd` use a hidden WScript launcher; they should not leave a console/terminal window on the taskbar.
- If the tray app exits or is killed, the overlay detects that and exits too, so it should not remain as an orphan window.

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
start-spotify-taskbar-overlay.vbs    Hidden no-console launcher used by shortcuts
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
