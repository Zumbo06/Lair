# config.py

import json
from pathlib import Path
from PyQt6.QtCore import QStandardPaths

class ConfigManager:
    def __init__(self):
        old_config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "EmulatorHub"
        config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "Lair"
        
        # Migrate old config to new config dir if needed
        if old_config_dir.exists() and not config_dir.exists():
            try:
                old_config_dir.rename(config_dir)
            except Exception as e:
                print(f"Failed to migrate config directory: {e}")
                config_dir = old_config_dir
                
        self.covers_dir = config_dir / "covers"
        self.cache_dir = self.covers_dir / "cache"
        self.save_states_dir = config_dir / "save_states"
        
        config_dir.mkdir(parents=True, exist_ok=True)
        self.covers_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        self.save_states_dir.mkdir(exist_ok=True)
        
        self.config_path = config_dir / "config.json"
        self.igdb_cache_path = config_dir / "igdb_cache.json"
        
        self.config = {
            "game_library_paths": [],
            "emulator_search_paths": [],
            "emulators": {},
            "custom_covers": {},
            "game_metadata": {},      # Contains title, notes, tags, developer, release_date, summary, sessions list
            "theme": "Steam Dark",
            "view_mode": "grid",
            "grid_icon_size": 140,
            "favorites": [],
            "recently_played": [],
            "platform_defaults": {},
            "igdb_client_id": "",
            "igdb_client_secret": "",
            "auto_scan_on_startup": True,
            "minimize_to_tray_on_launch": False
        }
        self.igdb_cache = {}
        self.load_config()
        self.load_igdb_cache()

    def load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config.update(json.load(f))
            except Exception as e:
                print(f"Error loading config: {e}")
                
    def save_config(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def load_igdb_cache(self):
        if self.igdb_cache_path.exists():
            try:
                with open(self.igdb_cache_path, 'r', encoding='utf-8') as f:
                    self.igdb_cache = json.load(f)
            except Exception as e:
                print(f"Error loading IGDB cache: {e}")

    def save_igdb_cache(self):
        try:
            with open(self.igdb_cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.igdb_cache, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving IGDB cache: {e}")
