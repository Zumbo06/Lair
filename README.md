# EmulatorHub v3.00 🎮

A premium, all-in-one game library manager for emulated and PC games — featuring IGDB metadata, automatic game scanning, playtime tracking, and a stunning modern UI.

![Version](https://img.shields.io/badge/version-3.00-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![PyQt6](https://img.shields.io/badge/PyQt6-6.4+-orange)

## ✨ Key Features

### 🎮 Universal Game Library
- **Auto-scan Steam, Epic Games & Xbox** libraries — games appear instantly
- **ROM scanning** across configured library folders with automatic platform detection
- **PS3 folder detection** — finds `PS3_GAME/USRDIR/EBOOT.BIN` structures, parses `PARAM.SFO` for real game titles
- **PS4 folder detection** — detects `sce_sys/param.sfo` structures
- **Manual game adding** — browse for files or folders, select executables, auto-detect platform from file extension
- **Custom collections** — organize games into personal groups

### 🌐 IGDB Metadata Integration
- **Automatic metadata fetching** — developer, release date, summary, genres, cover art, and IGDB scores
- **Smart title matching** — cleans serial codes, strips brackets/version numbers, handles trademark symbols
- **Serial code resolution** — resolves PS1/PS2/PS3 serial codes to real game titles via SerialStation & RPCS3 compatibility DB
- **Manual IGDB search** — right-click any game to search and pick the correct metadata match
- **Cover art downloads** — high-quality 720p poster art from IGDB
- **Persistent cache** — metadata is cached locally so repeat lookups are instant

### ⏱ Playtime Tracking
- **Automatic process tracking** via `psutil` — monitors game PIDs and child processes
- **Smart process detection** — scans by folder path and executable name when launchers restart
- **Grace period logic** — prevents false session ends during game/launcher restarts
- **Session history** — every play session is recorded with timestamp and duration
- **Last played date** — shows relative dates (Today, Yesterday, 3 days ago, 2 weeks ago, etc.) on the banner, info modal, and facts grid
- **Total playtime** — accumulated across all sessions, displayed in hours

### 📊 Statistics Dashboard
- **Total games & library size** — full overview of your collection
- **Total playtime** — track your gaming hours across all titles
- **Top 5 most played** — see your favorite games at a glance
- **Platform distribution** — top platforms by game count

### 🎨 Premium UI/UX
- **Obsidian & Velvet Violet theme** — deep dark backgrounds with neon cyan and violet accents
- **Game card grid** — full-bleed cover art with cinematic zoom on hover, neon glow selection borders
- **Glassmorphic badges** — playtime pills, platform tags, and favorite bookmarks overlaid on cards
- **Steam-style banner** — large header showing selected game with cover, metadata, and play/stop button
- **Info modal** — poster art with drop shadow, facts grid (developer, released, playtime, last played, file size, IGDB score), clickable file path, and full description
- **Smooth animations** — hover effects, gradient overlays, and transitions throughout
- **Grid & list views** — toggle with Ctrl+Tab

### 🔍 Search & Filtering
- **Smart search bar** with clear button and debounced input (300ms)
- **Platform filter dropdown** — quick filter by console/platform
- **Sorting options** — Name, Size (Asc/Desc), Time Played, Date Added
- **Game count** — filtered results shown in status bar

### 🚀 PC Game Support
- **Steam** — reads `libraryfolders.vdf` and `appmanifest_*.acf` to discover all installed games across multiple Steam libraries; launches via `steam://rungameid/`
- **Epic Games** — parses manifest files from `ProgramData\Epic\EpicGamesLauncher\Data\Manifests`
- **Xbox / Game Pass** — scans `XboxGames` folders on all drives and custom library paths
- **Common folders** — scans `C:\Games`, `D:\Games`, GOG Galaxy, and user-defined paths
- **Executable selection** — when a folder has multiple `.exe` files, pick the right one to launch and remember the choice

### 🕹 Emulator Management
- **Auto-detection** of popular emulators (RPCS3, Dolphin, PCSX2, Citra, Yuzu, PPSSPP, etc.)
- **Manual emulator configuration** — add custom emulators with launch arguments
- **Platform defaults** — set a default emulator per platform
- **`%ROM%` token** — custom argument placement for ROM path
- **RPCS3 auto-discovery** — automatically finds RPCS3 when launching PS3 games
- **shadPS4 support** — smart handling of launcher vs. core executable

### 📁 File Size Calculation
- **Installation folder sizing** — when a game has an installation directory (`game_dir`), the total folder size is calculated by walking the entire directory tree
- **Background calculation** — sizes for games with `size=0` are computed lazily in a background thread and the UI updates automatically
- **Works for all game types** — folder-based games (Steam, Epic, Xbox, PS3), single-file ROMs, and manually added games

## 📋 Requirements

```
PyQt6>=6.4.0
psutil>=5.9.0
requests
```

Optional:
```
Pillow>=9.0.0    # Enhanced image processing
```

## 🚀 Installation

### Quick Start (Recommended)
1. **Clone or download** this repository
2. **Run setup**:
   ```bash
   setup.bat
   ```
3. **Launch the app**:
   ```bash
   run.bat
   ```

### Manual Setup
1. **Install dependencies**:
   ```bash
   pip install -r Requirements.txt
   ```
2. **Run the application**:
   ```bash
   python emulator_hub_app.py
   ```

## 🎮 Supported Platforms

### Auto-Detected (ROM Scanning)
| Platform | Extensions |
|----------|-----------|
| PlayStation 4 | `.pkg` |
| PlayStation 3 | `.sfb` + folder detection |
| PlayStation 2 | `.iso` |
| PlayStation 1 | `.chd`, `.cue` |
| PSP | `.cso` |
| Nintendo Switch | `.nsp`, `.xci` |
| Wii | `.wbfs` |
| GameCube | `.gcz`, `.rvz` |
| Nintendo 64 | `.z64` |
| Super Nintendo | `.sfc` |
| NES | `.nes` |
| Nintendo DS | `.nds` |
| Nintendo 3DS | `.3ds` |
| Game Boy Advance | `.gba` |
| Game Boy Color | `.gbc` |
| Game Boy | `.gb` |
| Sega Dreamcast | `.cdi`, `.gdi` |
| Sega Saturn | `.sat` |
| Sega 32X | `.32x` |
| Sega Master System | `.sms` |
| Game Gear | `.gg` |

### Manually Addable
| Platform | Notes |
|----------|-------|
| Sega Genesis / Mega Drive | `.md`, `.gen`, `.smd` — add via "Add Game" dialog |
| PC | Auto-scanned from Steam/Epic/Xbox or added manually |
| Xbox | Auto-scanned from XboxGames folders |

### PC Game Sources (Auto-Scanned)
- Steam (all library folders)
- Epic Games Store
- Xbox / Game Pass
- GOG Galaxy
- Custom game folders

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **F5** | Refresh Library |
| **Ctrl+F** | Focus Search Bar |
| **Ctrl+Tab** | Toggle Grid/List View |
| **Enter** | Launch Selected Game |
| **Delete** | Delete Selected Game(s) |
| **Ctrl+A** | Select All Games |
| **Ctrl+I** | Show Detailed Info |
| **Ctrl+B** | Toggle Batch Mode |

## 📖 Usage Guide

### Adding Games
1. **Automatic scanning** — Click the scan button or press F5 to discover games from configured folders, Steam, Epic, and Xbox
2. **Manual add** — Use the "Add Game" dialog to browse for a file or folder; select platform, executable, and cover art
3. **Library folders** — Configure folder paths in the settings; all supported ROM types are auto-detected

### Launching Games
1. **Select a game** and click ▶ PLAY or press Enter
2. **PC games** — launched directly or via Steam URI
3. **Console games** — launched through the configured emulator for that platform
4. **Multiple emulators** — if several emulators support the same platform, you'll be prompted to choose (with option to set a default)

### IGDB Metadata
1. **Configure API keys** — set your Twitch Client ID & Secret in the settings (required for IGDB)
2. **Auto-fetch** — metadata is fetched automatically when games are scanned
3. **Manual search** — right-click a game → "Search IGDB" to find and apply the correct metadata
4. **Enrichment** — clicking a game with missing metadata triggers a background fetch

### System Tray
- **Minimize to tray** — optionally hide the app to system tray when launching a game
- **Tray notifications** — get notified when the app is minimized
- **Restore** — click the tray icon to bring the window back

## 🔧 Architecture

```
EmulatorHub/
├── emulator_hub_app.py    # Main application window & logic
├── ui_components.py       # UI delegates, banner, info modal, stats dashboard
├── config.py              # Configuration management & persistence
├── api.py                 # IGDB API client with caching
├── scanner.py             # PC game scanner (Steam, Epic, Xbox, common folders)
├── tracker.py             # Playtime tracking with psutil process monitoring
├── constants.py           # App constants, colors, version
├── setup.bat              # One-click environment setup
├── run.bat                # Launch script
├── Requirements.txt       # Python dependencies
└── icons/                 # Platform & UI icons
```

## 🐛 Troubleshooting

### Game not launching?
- Check emulator path in the **Emulators** tab
- Verify the emulator supports the game file format
- For PC games, right-click → Edit Details to set the correct executable

### Playtime not tracking?
- Install psutil: `pip install psutil`
- Restart the application after installing

### No metadata / covers?
- Configure your Twitch Client ID & Secret in settings for IGDB access
- Right-click a game → "Search IGDB" to manually find metadata

### File sizes showing 0?
- Sizes are calculated in the background on startup — wait a moment for them to populate
- Games need a valid `game_dir` or file path that exists on disk

## 📜 License

This project is open source and available for personal use.

## 🙏 Credits

Built with:
- **PyQt6** — Modern Qt bindings for Python
- **psutil** — Process monitoring and system utilities
- **requests** — HTTP client for IGDB API
- **IGDB** — Game metadata, covers, and ratings
- **Pillow** — Image processing (optional)

---

**Enjoy your premium gaming library! 🎮✨**

For issues or feature requests, please create an issue on the repository.
