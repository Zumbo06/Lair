# scanner.py

import os
import json
import re
from pathlib import Path


def _title_from_exe(exe_path: Path, fallback: str) -> str:
    """Derive a human-readable game title from an executable filename.

    Strategy (in order):
    1. Take the filename stem  (e.g. "TheWitcher3.exe" -> "TheWitcher3")
    2. Replace common word-separator characters with spaces
    3. Insert a space before every CamelCase boundary
    4. Strip leading version/build prefixes like 'v1.0', 'build_'
    5. Title-case the result
    If the result is empty or obviously generic (e.g. "Game", "Launch"),
    fall back to *fallback* (usually the folder name).
    """
    stem = exe_path.stem.strip()
    if not stem:
        return fallback

    # Replace separators with spaces
    name = re.sub(r'[_\-\.]+', ' ', stem)

    # Split CamelCase / PascalCase boundaries  (e.g. TheWitcher3 -> The Witcher 3)
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name)

    # Remove leading version tags like "v1" or "1.0" at the very start
    name = re.sub(r'^\s*v?\d[\d\.]*\s*', '', name, flags=re.IGNORECASE)

    name = ' '.join(name.split())  # collapse whitespace

    if not name:
        return fallback

    name = name.title()

    # If the cleaned name is a common generic word, prefer the folder name instead
    _GENERIC = {"Game", "Launch", "Launcher", "Play", "Start", "App", "Client", "Main", "Run"}
    if name in _GENERIC:
        return fallback

    return name

class PCGameScanner:
    @staticmethod
    def scan_steam_games():
        games = []
        # Common installation paths for Steam on Windows
        steam_paths = [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam"
        ]
        
        # Read from registry as secondary fallback
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            path, _ = winreg.QueryValueEx(key, "SteamPath")
            if path and path not in steam_paths:
                steam_paths.insert(0, os.path.normpath(path))
        except:
            pass
            
        for base_path in steam_paths:
            path_obj = Path(base_path)
            if not path_obj.exists():
                continue
                
            library_folders_file = path_obj / "steamapps" / "libraryfolders.vdf"
            libraries = [path_obj]
            
            # Parse secondary Steam libraries
            if library_folders_file.exists():
                try:
                    content = library_folders_file.read_text(encoding='utf-8', errors='ignore')
                    # Find all "path" attributes in libraryfolders
                    paths = re.findall(r'"path"\s+"([^"]+)"', content)
                    for p in paths:
                        lib_path = Path(os.path.normpath(p))
                        if lib_path.exists() and lib_path not in libraries:
                            libraries.append(lib_path)
                except Exception as e:
                    print(f"Error reading Steam libraryfolders: {e}")
            
            # Scan manifest files inside libraries
            for lib in libraries:
                steamapps = lib / "steamapps"
                if not steamapps.exists():
                    continue
                
                for acf in steamapps.glob("appmanifest_*.acf"):
                    try:
                        content = acf.read_text(encoding='utf-8', errors='ignore')
                        appid_match = re.search(r'"appid"\s+"([^"]+)"', content)
                        name_match = re.search(r'"name"\s+"([^"]+)"', content)
                        install_match = re.search(r'"installdir"\s+"([^"]+)"', content)
                        
                        if appid_match and name_match:
                            appid = appid_match.group(1)
                            title = name_match.group(1)
                            installdir = install_match.group(1) if install_match else ""
                            
                            # Construct steam URI to launch
                            launch_uri = f"steam://rungameid/{appid}"
                            game_dir = steamapps / "common" / installdir
                            
                            # Search for main executable inside the folder
                            exe_path = ""
                            if game_dir.exists():
                                exe_files = list(game_dir.rglob("*.exe"))
                                if exe_files:
                                    # Select the largest executable or one with common name as the launch tracker target
                                    exe_files.sort(key=lambda x: x.stat().st_size, reverse=True)
                                    exe_path = str(exe_files[0])
                            
                            games.append({
                                "title": title,
                                "path": launch_uri,
                                "platform": "PC",
                                "tracking_exe": exe_path,  # Exe to monitor for tracking
                                "game_dir": str(game_dir) if game_dir.exists() else ""
                            })
                    except Exception as e:
                        print(f"Error parsing acf file {acf.name}: {e}")
        return games

    @staticmethod
    def scan_epic_games():
        games = []
        epic_manifest_path = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")
        if not epic_manifest_path.exists():
            return games
            
        for item_file in epic_manifest_path.glob("*.item"):
            try:
                with open(item_file, 'r', encoding='utf-8', errors='ignore') as f:
                    manifest = json.load(f)
                title = manifest.get("DisplayName")
                install_dir = manifest.get("InstallLocation")
                launch_exe = manifest.get("LaunchExecutable")
                
                if title and install_dir and launch_exe:
                    abs_exe_path = os.path.join(install_dir, launch_exe)
                    if os.path.exists(abs_exe_path):
                        games.append({
                            "title": title,
                            "path": abs_exe_path,
                            "platform": "PC",
                            "tracking_exe": abs_exe_path,
                            "game_dir": install_dir
                        })
            except Exception as e:
                print(f"Error parsing Epic Game manifest {item_file.name}: {e}")
        return games

    @staticmethod
    def scan_common_game_folders(custom_paths):
        games = []
        common_folders = [
            r"C:\Games",
            r"D:\Games",
            r"E:\Games",
            r"C:\Program Files (x86)\GOG Galaxy\Games"
        ]
        
        # Merge with custom paths
        for path in custom_paths:
            if path not in common_folders and os.path.exists(path):
                common_folders.append(path)
                
        for folder in common_folders:
            folder_path = Path(folder)
            if not folder_path.exists():
                continue
                
            # Scan subfolders (up to 2 levels deep) for main game executables
            try:
                for entry in folder_path.iterdir():
                    if entry.is_dir() and not entry.name.startswith('.'):
                        # Look for largest .exe files in game directory
                        exe_files = list(entry.rglob("*.exe"))
                            
                        if exe_files:
                            exe_files.sort(key=lambda x: x.stat().st_size, reverse=True)
                            main_exe = exe_files[0]
                            
                            # Exclude uninstallers and setup
                            if not any(kw in main_exe.name.lower() for kw in ["unins", "setup", "install", "config"]):
                                # Derive title from exe name; fall back to folder name
                                title = _title_from_exe(main_exe, fallback=entry.name)
                                games.append({
                                    "title": title,
                                    "path": str(main_exe),
                                    "platform": "PC",
                                    "tracking_exe": str(main_exe),
                                    "game_dir": str(entry)
                                })
            except Exception as e:
                print(f"Error scanning folder {folder}: {e}")
        return games

    # Keywords that indicate a non-game helper executable
    _HELPER_EXE_KEYWORDS = [
        "unins", "setup", "install", "config", "helper",
        "crash", "reporter", "webview", "update", "launcher",
        "redist", "vcredist", "dxsetup", "dotnet"
    ]

    @staticmethod
    def scan_xbox_games(custom_paths=None):
        """Scan directories named 'Xbox' or 'XboxGames' for PC games.
        
        Searches standard drive roots (C/D/E) and any user-defined custom
        library paths.  Every discovered game is labelled as platform='PC'.
        """
        games = []
        target_folder_names = {"xbox", "xboxgames"}

        # --- 1. Build candidate root list ---
        candidate_roots = []

        # Standard drive roots
        for drive in ("C", "D", "E"):
            for name in ("Xbox", "XboxGames"):
                candidate_roots.append(os.path.join(f"{drive}:\\", name))

        # Custom library paths – check the folder itself AND its children
        if custom_paths:
            for cp in custom_paths:
                cp_path = Path(cp)
                if not cp_path.exists():
                    continue
                # If the custom path itself is an Xbox folder, use it directly
                if cp_path.name.lower() in target_folder_names:
                    candidate_roots.append(str(cp_path))
                else:
                    # Check immediate children for Xbox folders
                    try:
                        for child in cp_path.iterdir():
                            if child.is_dir() and child.name.lower() in target_folder_names:
                                candidate_roots.append(str(child))
                    except PermissionError:
                        pass

        # Deduplicate while preserving order
        seen = set()
        unique_roots = []
        for r in candidate_roots:
            nr = os.path.normpath(r).lower()
            if nr not in seen:
                seen.add(nr)
                unique_roots.append(r)

        # --- 2. Scan each root for game sub-folders ---
        for xbox_path in unique_roots:
            path_obj = Path(xbox_path)
            if not path_obj.exists():
                continue
            try:
                for entry in path_obj.iterdir():
                    if not entry.is_dir() or entry.name.startswith('.'):
                        continue

                    # Collect executables
                    exe_files = list(entry.rglob("*.exe"))
                    if not exe_files:
                        continue

                    # Filter out helper/utility executables
                    filtered = [
                        f for f in exe_files
                        if not any(kw in f.name.lower() for kw in PCGameScanner._HELPER_EXE_KEYWORDS)
                    ]

                    # Fall back to unfiltered list if everything was filtered
                    candidates = filtered if filtered else exe_files

                    # Pick the largest remaining executable as the main game binary
                    try:
                        candidates.sort(key=lambda x: x.stat().st_size, reverse=True)
                    except OSError:
                        continue
                    main_exe = candidates[0]

                    # Derive title from exe name; fall back to folder name
                    title = _title_from_exe(main_exe, fallback=entry.name)
                    games.append({
                        "title": title,
                        "path": str(main_exe),
                        "platform": "PC",
                        "tracking_exe": str(main_exe),
                        "game_dir": str(entry)
                    })
            except PermissionError:
                print(f"Permission denied scanning Xbox folder: {xbox_path}")
            except Exception as e:
                print(f"Error scanning Xbox folder {xbox_path}: {e}")

        return games
