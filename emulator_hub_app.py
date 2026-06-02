# emulator_hub_app.py

import sys
import os
import subprocess
import shutil
from pathlib import Path
import hashlib
import shlex
import time
import threading

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
    QStatusBar, QListWidgetItem, QPushButton, QMessageBox, QFileDialog, QLabel,
    QDialog, QLineEdit, QDialogButtonBox, QSplitter, QComboBox, QTreeWidget,
    QTreeWidgetItem, QCheckBox, QFormLayout, QGroupBox, QStackedWidget, QFrame, QMenu,
    QTextEdit
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor, QBrush, QPen, QPainter, QLinearGradient
from PyQt6.QtCore import Qt, QSize, QRect, pyqtSignal, QTimer

# --- Import Modular Subcomponents ---
from constants import Constants
from config import ConfigManager
from api import IGDBClient
from scanner import PCGameScanner
from tracker import PlaytimeTracker
from ui_components import (
    GridItemDelegate, SpacedListItemDelegate, GameBriefInfoModal,
    SteamGameBanner, StatsDashboard
)

# =============================================================================
# --- MAIN APPLICATION WINDOW ---
# =============================================================================
class EmulatorHubWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.image_cache = {} # Local in-memory QPixmap cache
        self.enriching_hashes = set() # Track games currently fetching metadata to prevent duplicate threads
        
        # Instantiate logical managers
        self.igdb_client = IGDBClient(
            self.config_manager.config.get("igdb_client_id", ""),
            self.config_manager.config.get("igdb_client_secret", ""),
            self.config_manager
        )
        self.playtime_tracker = PlaytimeTracker(self.config_manager)
        self.playtime_tracker.playtime_updated.connect(self.on_playtime_finished)
        
        self.games_data_map = {} # Loaded games maps
        self.games_by_platform = {}
        
        self.setWindowTitle(f"{Constants.APP_NAME} v{Constants.VERSION}")
        self.setMinimumSize(1260, 800)
        
        self.setup_theme()
        self.setup_ui()
        self.load_game_cache()
        
        # Auto scan games on startup if configured
        if self.config_manager.config.get("auto_scan_on_startup", True):
            QTimer.singleShot(1000, self.trigger_silent_pc_game_autoscan)

    def setup_theme(self):
        # Deep premium Obsidian & Velvet Violet QSS stylesheet
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Constants.C_BG_DARK};
            }}
            QWidget {{
                color: {Constants.C_TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Helvetica Neue', Arial;
            }}
            QStatusBar {{
                background-color: {Constants.C_BG_DARK};
                border-top: 1px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_MUTED};
                font-size: 11px;
            }}
            QSplitter::handle {{
                background-color: {Constants.C_BORDER};
            }}
            QListWidget {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 6px;
                outline: none;
            }}
            QListWidget::item:hover {{
                background-color: #1e1f29;
            }}
            QListWidget::item:selected {{
                background-color: {Constants.C_BORDER};
                color: #ffffff;
                border: 1.5px solid {Constants.C_ACCENT_CYAN};
            }}
            QTreeWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 12px 16px;
                margin-bottom: 8px;
                border-radius: 8px;
                color: #a0a5b8;
                font-weight: 500;
                background-color: transparent;
                border: 1px solid transparent;
            }}
            QTreeWidget::item:hover {{
                background-color: #1c1d24;
                color: #ffffff;
                border: 1px solid #2d303f;
            }}
            QTreeWidget::item:selected {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #251847, stop:1 #17112c);
                color: {Constants.C_ACCENT_CYAN};
                border: 1px solid {Constants.C_BORDER};
                border-left: 4px solid {Constants.C_ACCENT_CYAN};
                font-weight: bold;
            }}
            QTreeWidget::branch {{
                background: transparent;
            }}
            QPushButton {{
                background-color: {Constants.C_BG_PANEL};
                border: 1.5px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_PRIMARY};
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_BORDER};
                border-color: {Constants.C_ACCENT_CYAN};
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {Constants.C_BG_DARK};
                border: 1.5px solid {Constants.C_BORDER};
                border-radius: 6px;
                padding: 6px;
                color: #ffffff;
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border-color: {Constants.C_ACCENT_CYAN};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Constants.C_BG_PANEL};
                border: 1.5px solid {Constants.C_BORDER};
                selection-background-color: {Constants.C_BORDER};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 2px solid {Constants.C_BORDER};
                border-radius: 8px;
                margin-top: 12px;
                background-color: {Constants.C_BG_PANEL};
            }}
            QMenu {{
                background-color: {Constants.C_BG_PANEL};
                border: 1.5px solid {Constants.C_BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 6px 24px 6px 16px;
                border-radius: 4px;
                color: #ffffff;
            }}
            QMenu::item:selected {{
                background-color: {Constants.C_BORDER};
                color: {Constants.C_ACCENT_CYAN};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {Constants.C_BORDER};
                margin: 4px 0px;
            }}
        """)

    def setup_ui(self):
        # 1. Main Layout with Top Navigation
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 2. Top Obsidian Menu header
        top_nav = QFrame()
        top_nav.setFixedHeight(54)
        top_nav.setStyleSheet(f"background-color: {Constants.C_BG_DARK}; border-bottom: 1.5px solid {Constants.C_BORDER};")
        top_layout = QHBoxLayout(top_nav)
        top_layout.setContentsMargins(20, 0, 20, 0)
        
        # Logo Text
        logo_label = QLabel(Constants.APP_NAME)
        logo_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        logo_label.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; letter-spacing: 1px;")
        top_layout.addWidget(logo_label)
        
        # Navigation Tabs
        self.nav_tabs = QHBoxLayout()
        self.nav_tabs.setSpacing(12)
        
        self.btn_lib = self.create_nav_button("LIBRARY", active=True)
        self.btn_dash = self.create_nav_button("DASHBOARD")
        self.btn_emu = self.create_nav_button("EMULATORS")
        self.btn_set = self.create_nav_button("SETTINGS")
        
        self.btn_lib.clicked.connect(lambda: self.switch_tab(0))
        self.btn_dash.clicked.connect(lambda: self.switch_tab(1))
        self.btn_emu.clicked.connect(lambda: self.switch_tab(2))
        self.btn_set.clicked.connect(lambda: self.switch_tab(3))
        
        self.nav_tabs.addWidget(self.btn_lib)
        self.nav_tabs.addWidget(self.btn_dash)
        self.nav_tabs.addWidget(self.btn_emu)
        self.nav_tabs.addWidget(self.btn_set)
        
        top_layout.addSpacing(40)
        top_layout.addLayout(self.nav_tabs)
        top_layout.addStretch()
        
        # Add Search Bar into top right area
        self.top_search = QLineEdit()
        self.top_search.setPlaceholderText("🔍 Search games in library...")
        self.top_search.setFixedWidth(240)
        self.top_search.textChanged.connect(self.on_filter_changed)
        top_layout.addWidget(self.top_search)
        
        main_layout.addWidget(top_nav)
        
        # 3. Stacked View Area
        self.stacked_widget = QStackedWidget()
        
        # --- TAB 0: LIBRARY VIEW ---
        self.stacked_widget.addWidget(self.setup_library_view())
        
        # --- TAB 1: DASHBOARD ---
        self.stats_dashboard = StatsDashboard(self.config_manager)
        self.stacked_widget.addWidget(self.stats_dashboard)
        
        # --- TAB 2: EMULATORS ---
        self.stacked_widget.addWidget(self.setup_emulators_view())
        
        # --- TAB 3: SETTINGS ---
        self.stacked_widget.addWidget(self.setup_settings_view())
        
        main_layout.addWidget(self.stacked_widget)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready.")

    def create_nav_button(self, label, active=False):
        btn = QPushButton(label)
        btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn.setFlat(True)
        if active:
            btn.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; border-bottom: 2.5px solid {Constants.C_ACCENT_CYAN}; background-color: transparent;")
        else:
            btn.setStyleSheet("color: #8f98a0; border: none; background-color: transparent;")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def switch_tab(self, index):
        self.stacked_widget.setCurrentIndex(index)
        
        # Update tab visual highlights
        buttons = [self.btn_lib, self.btn_dash, self.btn_emu, self.btn_set]
        for idx, btn in enumerate(buttons):
            if idx == index:
                btn.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; border-bottom: 2.5px solid {Constants.C_ACCENT_CYAN}; background-color: transparent;")
            else:
                btn.setStyleSheet("color: #8f98a0; border: none; background-color: transparent;")
                
        # If dashboard, refresh metrics
        if index == 1:
            self.stats_dashboard.refresh_stats(list(self.games_data_map.values()))

    # =============================================================================
    # --- UI GENERATION FOR INDIVIDUAL TABS ---
    # =============================================================================
    def setup_library_view(self):
        lib_widget = QWidget()
        lib_layout = QHBoxLayout(lib_widget)
        lib_layout.setContentsMargins(0, 0, 0, 0)
        lib_layout.setSpacing(0)
        
        # Splitter to divide left sidebar categories and main listing
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # --- Left Category Sidebar ---
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(f"""
            background-color: {Constants.C_BG_PANEL};
            border-right: 1.5px solid {Constants.C_BORDER};
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 16)
        sidebar_layout.setSpacing(16)
        
        sidebar_title = QLabel("MY LIBRARY")
        sidebar_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        sidebar_title.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; letter-spacing: 1.5px; border: none; background-color: transparent;")
        sidebar_layout.addWidget(sidebar_title)
        
        self.sidebar_tree = QTreeWidget()
        self.sidebar_tree.setHeaderHidden(True)
        self.sidebar_tree.setIndentation(14)
        self.sidebar_tree.itemClicked.connect(self.on_sidebar_item_clicked)
        sidebar_layout.addWidget(self.sidebar_tree)
        
        splitter.addWidget(sidebar)
        
        # --- Right Game Listing Area ---
        main_content = QWidget()
        main_content_layout = QVBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(0)
        
        # Steam game header banner
        self.banner = SteamGameBanner()
        self.banner.play_clicked.connect(self.launch_selected_game)
        self.banner.info_clicked.connect(self.show_current_game_info_modal)
        self.banner.favorite_toggled.connect(self.toggle_selected_favorite)
        main_content_layout.addWidget(self.banner)
        
        # View Options Header
        view_hdr = QFrame()
        view_hdr.setFixedHeight(40)
        view_hdr.setStyleSheet(f"background-color: {Constants.C_BG_DARK}; border-bottom: 1px solid {Constants.C_BORDER};")
        view_layout = QHBoxLayout(view_hdr)
        view_layout.setContentsMargins(16, 0, 16, 0)
        
        # Grid/List switcher
        self.btn_grid = QPushButton("Grid View")
        self.btn_list = QPushButton("List View")
        self.btn_grid.setCheckable(True)
        self.btn_list.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.clicked.connect(self.set_view_grid)
        self.btn_list.clicked.connect(self.set_view_list)
        
        view_layout.addWidget(self.btn_grid)
        view_layout.addWidget(self.btn_list)
        view_layout.addStretch()
        
        # Sorting
        view_layout.addWidget(QLabel("SORT BY:"))
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Name", "Total Playtime", "File Size"])
        self.combo_sort.currentTextChanged.connect(self.on_filter_changed)
        view_layout.addWidget(self.combo_sort)
        
        main_content_layout.addWidget(view_hdr)
        
        # Main Listing Area
        self.games_list = QListWidget()
        self.games_list.verticalScrollBar().setSingleStep(32)
        self.games_list.setSpacing(8)
        self.games_list.itemClicked.connect(self.on_game_selected)
        self.games_list.itemDoubleClicked.connect(self.launch_selected_game)
        self.games_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.games_list.customContextMenuRequested.connect(self.show_game_context_menu)
        
        # Setup Grid Delegating Default view mode
        self.grid_delegate = GridItemDelegate(self.config_manager, self.games_list)
        self.list_delegate = SpacedListItemDelegate(self.games_list)
        
        main_content_layout.addWidget(self.games_list)
        
        splitter.addWidget(main_content)
        splitter.setSizes([240, 1020])
        lib_layout.addWidget(splitter)
        
        # Select grid style first
        self.set_view_grid()
        
        return lib_widget

    def setup_emulators_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        title = QLabel("🎮 EMULATOR SETTINGS")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN};")
        layout.addWidget(title)
        
        # Emulator table tree
        self.emu_tree = QTreeWidget()
        self.emu_tree.setHeaderLabels(["Emulator", "Systems supported", "Executable Location"])
        self.emu_tree.setColumnWidth(0, 160)
        self.emu_tree.setColumnWidth(1, 240)
        layout.addWidget(self.emu_tree)
        
        # Buttons panel
        btn_layout = QHBoxLayout()
        
        btn_add = QPushButton("+ ADD CUSTOM EMULATOR")
        btn_add.clicked.connect(self.add_custom_emulator_dialog)
        btn_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("🗑 REMOVE SELECTED")
        btn_remove.clicked.connect(self.remove_selected_emulator)
        btn_layout.addWidget(btn_remove)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        return widget

    def setup_settings_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        title = QLabel("⚙ SYSTEM SETTINGS")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN};")
        layout.addWidget(title)
        
        from PyQt6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        scroll.verticalScrollBar().setSingleStep(32)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)
        
        # 1. Library Folders Manager
        box_folders = QGroupBox("GAME LIBRARY FOLDERS")
        folder_layout = QVBoxLayout(box_folders)
        folder_layout.setContentsMargins(12, 20, 12, 12)
        
        self.folders_list = QListWidget()
        self.folders_list.addItems(self.config_manager.config["game_library_paths"])
        folder_layout.addWidget(self.folders_list)
        
        f_btn_layout = QHBoxLayout()
        btn_add_f = QPushButton("+ ADD FOLDER")
        btn_add_f.clicked.connect(self.add_library_folder)
        f_btn_layout.addWidget(btn_add_f)
        
        btn_rem_f = QPushButton("🗑 REMOVE SELECTED")
        btn_rem_f.clicked.connect(self.remove_library_folder)
        f_btn_layout.addWidget(btn_rem_f)
        f_btn_layout.addStretch()
        
        folder_layout.addLayout(f_btn_layout)
        content_layout.addWidget(box_folders)
        
        # 2. IGDB API Settings
        box_igdb = QGroupBox("Twitch / IGDB API SETTINGS (For posters, dev, and release dates)")
        igdb_layout = QFormLayout(box_igdb)
        igdb_layout.setContentsMargins(12, 20, 12, 12)
        igdb_layout.setSpacing(12)
        
        self.edit_client_id = QLineEdit(self.config_manager.config.get("igdb_client_id", ""))
        self.edit_client_id.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.edit_client_id.textChanged.connect(self.save_settings)
        igdb_layout.addRow("Twitch Client ID:", self.edit_client_id)
        
        self.edit_client_secret = QLineEdit(self.config_manager.config.get("igdb_client_secret", ""))
        self.edit_client_secret.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.edit_client_secret.textChanged.connect(self.save_settings)
        igdb_layout.addRow("Twitch Client Secret:", self.edit_client_secret)
        
        tip_lbl = QLabel("How to get keys: Register a developer application on twitch at dev.twitch.tv dashboard for free, and fetch posters instantly!")
        tip_lbl.setFont(QFont("Segoe UI", 9))
        tip_lbl.setWordWrap(True)
        tip_lbl.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        igdb_layout.addRow("", tip_lbl)
        
        content_layout.addWidget(box_igdb)
        
        # 3. Actions Panel
        box_actions = QGroupBox("LIBRARY ACTIONS")
        actions_layout = QHBoxLayout(box_actions)
        actions_layout.setContentsMargins(12, 20, 12, 12)
        
        btn_scan = QPushButton("🔍 AUTO-SCAN PC GAMES")
        btn_scan.setStyleSheet(f"QPushButton {{ background-color: {Constants.C_BORDER}; color: white; }}")
        btn_scan.clicked.connect(self.trigger_pc_game_autoscan)
        actions_layout.addWidget(btn_scan)
        
        btn_refresh_lib = QPushButton("🔄 FULL PLATFORM RESCAN")
        btn_refresh_lib.clicked.connect(self.trigger_full_rom_scan)
        actions_layout.addWidget(btn_refresh_lib)
        actions_layout.addStretch()
        
        content_layout.addWidget(box_actions)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return widget

    # =============================================================================
    # --- LOGICAL CORE REDESIGNS ---
    # =============================================================================
    def load_game_cache(self):
        # Read from configuration data map
        self.games_data_map.clear()
        metadata_map = self.config_manager.config.get("game_metadata", {})
        
        for g_hash, game in metadata_map.items():
            # Hydrate game properties
            self.games_data_map[g_hash] = {
                "title": game.get("title", ""),
                "path": game.get("path", ""),
                "hash": g_hash,
                "platform": game.get("platform", ""),
                "size": game.get("size", 0),
                "playtime": game.get("playtime", 0),
                "developer": game.get("developer", "Unknown Developer"),
                "release_date": game.get("release_date", "N/A"),
                "summary": game.get("summary", ""),
                "tracking_exe": game.get("tracking_exe", ""),
                "game_dir": game.get("game_dir", "")
            }
            
        self.rebuild_platform_mappings()
        self.repopulate_sidebar_tree()
        self.repopulate_game_list()
        self.update_emulators_tree()

    def rebuild_platform_mappings(self):
        self.games_by_platform.clear()
        for g in self.games_data_map.values():
            plat = g.get("platform", "Unknown")
            if plat not in self.games_by_platform:
                self.games_by_platform[plat] = []
            self.games_by_platform[plat].append(g)

    def trigger_silent_pc_game_autoscan(self):
        # Auto-scan games quietly on startup without modals
        self.statusBar().showMessage("Quietly scanning for local Steam and Epic games in background...")
        threading.Thread(target=self._run_silent_scan, daemon=True).start()

    def _run_silent_scan(self):
        try:
            # 1. Scan Steam
            steam_games = PCGameScanner.scan_steam_games()
            # 2. Scan Epic
            epic_games = PCGameScanner.scan_epic_games()
            # 3. Scan Xbox folders as PC games
            xbox_games = PCGameScanner.scan_xbox_games(self.config_manager.config.get("game_library_paths", []))
            
            all_pc_games = steam_games + epic_games + xbox_games
            added_count = 0
            
            for p_game in all_pc_games:
                g_path = p_game["path"]
                g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
                
                if g_hash not in self.config_manager.config["game_metadata"]:
                    dev = "Unknown Developer"
                    rel = "N/A"
                    summary = "Local PC Game"
                    cover_id = ""
                    
                    details = self.igdb_client.fetch_game_details(p_game["title"])
                    if details:
                        dev = details["developer"]
                        rel = details["release_date"]
                        summary = details["summary"]
                        cover_id = details["cover_image_id"]
                        
                    self.config_manager.config["game_metadata"][g_hash] = {
                        "title": p_game["title"],
                        "path": g_path,
                        "platform": p_game.get("platform", "PC"),
                        "playtime": 0,
                        "sessions": [],
                        "developer": dev,
                        "release_date": rel,
                        "summary": summary,
                        "cover_image_id": cover_id,
                        "tracking_exe": p_game.get("tracking_exe", ""),
                        "game_dir": p_game.get("game_dir", ""),
                        "size": 0
                    }
                    
                    if cover_id:
                        cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                        self.igdb_client.download_cover(cover_id, cover_path)
                        
                    added_count += 1
            
            if added_count > 0:
                self.config_manager.save_config()
                # Safely refresh UI on main thread
                from PyQt6.QtCore import QMetaObject, Q_ARG
                QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)
        except Exception as e:
            print(f"Error in background silent scan: {e}")

    def trigger_pc_game_autoscan(self):
        self.statusBar().showMessage("Auto-scanning PC Games folder, Steam, Epic Games, Xbox libraries...")
        QApplication.processEvents()
        
        # 1. Scan Steam
        steam_games = PCGameScanner.scan_steam_games()
        # 2. Scan Epic
        epic_games = PCGameScanner.scan_epic_games()
        # 3. Scan GOG & common directories
        common_games = PCGameScanner.scan_common_game_folders(self.config_manager.config["game_library_paths"])
        # 4. Scan Xbox folders as PC games
        xbox_games = PCGameScanner.scan_xbox_games(self.config_manager.config.get("game_library_paths", []))
        
        all_pc_games = steam_games + epic_games + common_games + xbox_games
        added_count = 0
        
        for p_game in all_pc_games:
            g_path = p_game["path"]
            g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
            
            if g_hash not in self.config_manager.config["game_metadata"]:
                dev = "Unknown Developer"
                rel = "N/A"
                summary = "Local PC Game"
                cover_id = ""
                
                details = self.igdb_client.fetch_game_details(p_game["title"])
                if details:
                    dev = details["developer"]
                    rel = details["release_date"]
                    summary = details["summary"]
                    cover_id = details["cover_image_id"]
                    
                self.config_manager.config["game_metadata"][g_hash] = {
                    "title": p_game["title"],
                    "path": g_path,
                    "platform": p_game.get("platform", "PC"),
                    "playtime": 0,
                    "sessions": [],
                    "developer": dev,
                    "release_date": rel,
                    "summary": summary,
                    "cover_image_id": cover_id,
                    "tracking_exe": p_game.get("tracking_exe", ""),
                    "game_dir": p_game.get("game_dir", ""),
                    "size": 0
                }
                
                # Fetch background poster
                if cover_id:
                    cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                    threading.Thread(target=self.igdb_client.download_cover, args=(cover_id, cover_path), daemon=True).start()
                    
                added_count += 1
                
        self.config_manager.save_config()
        self.load_game_cache()
        QMessageBox.information(self, "Auto Scan Complete", f"Scan complete! Discovered and added {added_count} PC/Xbox games to library.")
        self.statusBar().showMessage("Ready.")

    def parse_param_sfo(self, sfo_path):
        import struct
        try:
            if not os.path.exists(sfo_path):
                return None
            with open(sfo_path, 'rb') as f:
                data = f.read()
            if len(data) < 20 or data[:4] != b'\x00PSF':
                return None
                
            key_table_start, value_table_start, num_entries = struct.unpack('<III', data[8:20])
            for i in range(num_entries):
                offset = 20 + i * 16
                if offset + 16 > len(data):
                    break
                key_off, data_type, data_fmt, data_len, max_len, val_off = struct.unpack('<HBBIII', data[offset:offset+16])
                
                # Extract Key Name
                key_start = key_table_start + key_off
                if key_start >= len(data):
                    continue
                key_end = data.find(b'\x00', key_start)
                if key_end == -1:
                    key_end = len(data)
                key = data[key_start:key_end].decode('utf-8', errors='ignore')
                
                if key == "TITLE":
                    val_start = value_table_start + val_off
                    if val_start >= len(data):
                        continue
                    val_end = data.find(b'\x00', val_start)
                    if val_end == -1:
                        val_end = len(data)
                    title = data[val_start:val_end].decode('utf-8', errors='ignore')
                    return title.strip()
        except Exception as e:
            print(f"Error parsing PARAM.SFO offline: {e}")
        return None

    def trigger_full_rom_scan(self):
        # Classic emulator scanner based on standard library folders and platform mapping suffixes
        self.statusBar().showMessage("Rescanning library directories...")
        QApplication.processEvents()
        
        PLATFORM_SUFFIXES = {
            ".iso": "PlayStation 2",
            ".gcz": "GameCube",
            ".rvz": "GameCube",
            ".wbfs": "Wii",
            ".nsp": "Nintendo Switch",
            ".xci": "Nintendo Switch",
            ".gba": "Game Boy Advance",
            ".gbc": "Game Boy Color",
            ".gb": "Game Boy",
            ".nds": "Nintendo DS",
            ".3ds": "Nintendo 3DS",
            ".nes": "NES",
            ".sfc": "Super Nintendo",
            ".z64": "Nintendo 64",
            ".chd": "PlayStation",
            ".cue": "PlayStation",
            ".cso": "PSP",
            ".sfb": "PlayStation 3"
        }
        
        roms_found = []
        
        for path in self.config_manager.config["game_library_paths"]:
            path_obj = Path(path)
            if not path_obj.exists():
                continue
                
            for root, dirs, files in os.walk(path):
                # 1. Check for directory-based PlayStation 3 games (PS3_GAME folders)
                if "PS3_GAME" in dirs:
                    ps3_root = Path(root)
                    ps3_game_dir = ps3_root / "PS3_GAME"
                    eboot_path = ps3_game_dir / "USRDIR" / "EBOOT.BIN"
                    sfb_files = list(ps3_root.glob("*.SFB")) + list(ps3_root.glob("*.sfb"))
                    
                    target_path = str(eboot_path) if eboot_path.exists() else (str(sfb_files[0]) if sfb_files else str(ps3_game_dir))
                    roms_found.append({
                        "title": ps3_root.name,
                        "path": target_path,
                        "platform": "PlayStation 3",
                        "size": 0
                    })
                    # Prune recursion into the game folder
                    dirs.remove("PS3_GAME")
                    
                # 2. File suffix scanning
                for f in files:
                    file_path = Path(root) / f
                    suffix = file_path.suffix.lower()
                    if suffix in PLATFORM_SUFFIXES:
                        platform = PLATFORM_SUFFIXES[suffix]
                        # Avoid duplicates for PS3 disc file if folder was scanned
                        if platform == "PlayStation 3" and file_path.name.upper() == "PS3_DISC.SFB":
                            continue
                        roms_found.append({
                            "title": file_path.stem,
                            "path": str(file_path),
                            "platform": platform,
                            "size": file_path.stat().st_size
                        })
                        
        # 3. Automatically locate and scan RPCS3 dev_hdd0/game folder if RPCS3 is configured!
        rpcs3_game_dirs = []
        for name, emu in self.config_manager.config.get("emulators", {}).items():
            is_rpcs3 = "rpcs3" in name.lower() or "rpcs3" in emu.get("path", "").lower() or "playstation 3" in [s.lower() for s in emu.get("systems", [])]
            if is_rpcs3:
                emu_path = emu.get("path", "")
                if emu_path and os.path.exists(emu_path):
                    rpcs3_dir = Path(emu_path).parent
                    dev_hdd0_game = rpcs3_dir / "dev_hdd0" / "game"
                    if dev_hdd0_game.exists():
                        rpcs3_game_dirs.append(dev_hdd0_game)
                        
        # Check in standard scanned library paths too in case user pointed directly to a dev_hdd0 directory
        for path in self.config_manager.config["game_library_paths"]:
            path_obj = Path(path)
            if "dev_hdd0" in str(path_obj).lower():
                if path_obj.name.lower() == "dev_hdd0":
                    game_folder = path_obj / "game"
                    if game_folder.exists() and game_folder not in rpcs3_game_dirs:
                        rpcs3_game_dirs.append(game_folder)
                elif path_obj.name.lower() == "game" and path_obj.parent.name.lower() == "dev_hdd0":
                    if path_obj not in rpcs3_game_dirs:
                        rpcs3_game_dirs.append(path_obj)
                        
        # Now perform the scan on dev_hdd0/game directories
        for game_folder in rpcs3_game_dirs:
            try:
                for entry in game_folder.iterdir():
                    if entry.is_dir() and not entry.name.startswith('.'):
                        # Locate target executable (EBOOT.BIN)
                        eboot_path = entry / "USRDIR" / "EBOOT.BIN"
                        target_path = str(eboot_path) if eboot_path.exists() else str(entry)
                        
                        # Get game title from PARAM.SFO offline using our new binary parser!
                        parsed_title = None
                        sfo_path = entry / "PARAM.SFO"
                        if sfo_path.exists():
                            parsed_title = self.parse_param_sfo(str(sfo_path))
                            
                        # Use parsed title, otherwise fall back to serial/folder name
                        title = parsed_title if parsed_title else entry.name
                        
                        # Check for duplicates in roms_found list
                        already_added = False
                        for r in roms_found:
                            if r["path"] == target_path:
                                already_added = True
                                break
                                
                        if not already_added:
                            roms_found.append({
                                "title": title,
                                "path": target_path,
                                "platform": "PlayStation 3",
                                "size": 0
                            })
            except Exception as e:
                print(f"Error scanning RPCS3 dev_hdd0 folder {game_folder}: {e}")
                
        added_count = 0
        for rom in roms_found:
            g_path = rom["path"]
            g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
            
            if g_hash not in self.config_manager.config["game_metadata"]:
                # Fetch metadata
                dev = "Unknown Developer"
                rel = "N/A"
                summary = f"Local ROM for {rom['platform']}"
                cover_id = ""
                
                details = self.igdb_client.fetch_game_details(rom["title"])
                if details:
                    dev = details["developer"]
                    rel = details["release_date"]
                    summary = details["summary"]
                    cover_id = details["cover_image_id"]
                    
                self.config_manager.config["game_metadata"][g_hash] = {
                    "title": rom["title"],
                    "path": g_path,
                    "platform": rom["platform"],
                    "playtime": 0,
                    "sessions": [],
                    "developer": dev,
                    "release_date": rel,
                    "summary": summary,
                    "cover_image_id": cover_id,
                    "size": rom["size"]
                }
                
                if cover_id:
                    cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                    threading.Thread(target=self.igdb_client.download_cover, args=(cover_id, cover_path), daemon=True).start()
                    
                added_count += 1
                
        self.config_manager.save_config()
        self.load_game_cache()
        QMessageBox.information(self, "ROM Scan Complete", f"Scan complete! Discovered and added {added_count} ROMs to library.")
        self.statusBar().showMessage("Ready.")

    # =============================================================================
    # --- INTERACTION CONTROLLERS ---
    # =============================================================================
    def repopulate_sidebar_tree(self):
        self.sidebar_tree.clear()
        
        # ALL GAMES root
        all_item = QTreeWidgetItem([f"🎮  {Constants.ALL_GAMES_CATEGORY}"])
        all_item.setData(0, Qt.ItemDataRole.UserRole, Constants.ALL_GAMES_CATEGORY)
        self.sidebar_tree.addTopLevelItem(all_item)
        
        # FAVORITES root
        fav_item = QTreeWidgetItem([f"⭐  {Constants.FAVORITES_CATEGORY}"])
        fav_item.setData(0, Qt.ItemDataRole.UserRole, Constants.FAVORITES_CATEGORY)
        self.sidebar_tree.addTopLevelItem(fav_item)
        
        # RECENTS root
        recent_item = QTreeWidgetItem([f"⏱  {Constants.RECENTS_CATEGORY}"])
        recent_item.setData(0, Qt.ItemDataRole.UserRole, Constants.RECENTS_CATEGORY)
        self.sidebar_tree.addTopLevelItem(recent_item)
        
        # Platforms root
        plat_item = QTreeWidgetItem(["📁  PLATFORMS"])
        plat_item.setData(0, Qt.ItemDataRole.UserRole, "PLATFORMS_ROOT")
        
        platform_emojis = {
            "PC": "💻",
            "Xbox": "💚",
            "PlayStation 3": "💿",
            "PlayStation 2": "💿",
            "PlayStation": "💿",
            "PSP": "🎮",
            "Nintendo Switch": "🕹️",
            "Nintendo 3DS": "📱",
            "Nintendo DS": "📱",
            "GameCube": "👾",
            "Wii": "🎳",
            "Wii U": "📺",
            "NES": "📺",
            "Super Nintendo": "🕹️",
            "Nintendo 64": "🎮",
            "Game Boy": "👾",
            "Game Boy Color": "👾",
            "Game Boy Advance": "👾"
        }
        
        for platform in sorted(self.games_by_platform.keys()):
            count = len(self.games_by_platform[platform])
            emoji = platform_emojis.get(platform, "💿")
            child = QTreeWidgetItem([f"{emoji}  {platform} ({count})"])
            child.setData(0, Qt.ItemDataRole.UserRole, platform)
            plat_item.addChild(child)
            
        self.sidebar_tree.addTopLevelItem(plat_item)
        plat_item.setExpanded(True)
        
        # Select first tab by default
        self.sidebar_tree.setCurrentItem(all_item)

    def set_view_grid(self):
        self.btn_grid.setChecked(True)
        self.btn_list.setChecked(False)
        self.games_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.games_list.setFlow(QListWidget.Flow.LeftToRight)
        self.games_list.setWrapping(True)
        self.games_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.games_list.setItemDelegate(self.grid_delegate)
        self.games_list.setIconSize(QSize(140, 200))
        self.repopulate_game_list()

    def set_view_list(self):
        self.btn_grid.setChecked(False)
        self.btn_list.setChecked(True)
        self.games_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.games_list.setFlow(QListWidget.Flow.TopToBottom)
        self.games_list.setWrapping(False)
        self.games_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.games_list.setItemDelegate(self.list_delegate)
        self.repopulate_game_list()

    def on_sidebar_item_clicked(self, item, column):
        self.repopulate_game_list()

    def on_filter_changed(self):
        self.repopulate_game_list()

    def get_selected_sidebar_filter(self):
        item = self.sidebar_tree.currentItem()
        if not item:
            return Constants.ALL_GAMES_CATEGORY, None
            
        role_val = item.data(0, Qt.ItemDataRole.UserRole)
        parent = item.parent()
        
        if parent and parent.data(0, Qt.ItemDataRole.UserRole) == "PLATFORMS_ROOT":
            return "PLATFORM", role_val
            
        return role_val or Constants.ALL_GAMES_CATEGORY, None

    def repopulate_game_list(self):
        # Remember currently selected game hash to prevent resetting selection when metadata updates in background
        selected_hash = None
        current_item = self.games_list.currentItem()
        if current_item:
            old_game = current_item.data(Qt.ItemDataRole.UserRole)
            if old_game:
                selected_hash = old_game.get("hash")

        self.games_list.clear()
        filter_mode, filter_val = self.get_selected_sidebar_filter()
        
        # Get matching games base set
        games_subset = []
        if filter_mode == Constants.ALL_GAMES_CATEGORY:
            games_subset = list(self.games_data_map.values())
        elif filter_mode == Constants.FAVORITES_CATEGORY:
            favs = self.config_manager.config.get("favorites", [])
            games_subset = [g for g in self.games_data_map.values() if g["hash"] in favs]
        elif filter_mode == Constants.RECENTS_CATEGORY:
            recents = self.config_manager.config.get("recently_played", [])
            # Preserve order
            games_subset = []
            for g_hash in recents:
                if g_hash in self.games_data_map:
                    games_subset.append(self.games_data_map[g_hash])
        elif filter_mode == "PLATFORM":
            games_subset = self.games_by_platform.get(filter_val, [])
            
        # Apply Search Filter (Debounce/Instant)
        query = self.top_search.text().strip().lower()
        if query:
            games_subset = [g for g in games_subset if query in g["title"].lower()]
            
        # Apply Sorting
        sort_key = self.combo_sort.currentText()
        if sort_key == "Name":
            games_subset.sort(key=lambda x: x["title"].lower())
        elif sort_key == "Total Playtime":
            games_subset.sort(key=lambda x: x.get("playtime", 0), reverse=True)
        elif sort_key == "File Size":
            games_subset.sort(key=lambda x: x.get("size", 0), reverse=True)

        for game in games_subset:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, game)
            
            # Load cover pixmap
            cover_path = self.config_manager.covers_dir / f"{game['hash']}.jpg"
            pixmap = QPixmap()
            if cover_path.exists():
                pixmap.load(str(cover_path))
                
            icon = QIcon(pixmap) if not pixmap.isNull() else self.generate_gradient_fallback(game["title"])
            item.setData(Qt.ItemDataRole.DecorationRole, icon)
            
            self.games_list.addItem(item)
            
        # Restore selection if the previously selected game is still in the subset
        restored = False
        if selected_hash:
            for row in range(self.games_list.count()):
                item = self.games_list.item(row)
                game_data = item.data(Qt.ItemDataRole.UserRole)
                if game_data and game_data.get("hash") == selected_hash:
                    self.games_list.setCurrentRow(row)
                    restored = True
                    break
                    
        if not restored:
            if self.games_list.count() > 0:
                self.games_list.setCurrentRow(0)
                self.on_game_selected(self.games_list.currentItem())
            else:
                self.banner.set_game(None, None, False)

    def generate_gradient_fallback(self, title):
        cache_key = f"fallback_{title}"
        if cache_key in self.image_cache:
            return self.image_cache[cache_key]
            
        pix = QPixmap(140, 200)
        pix.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Modern curated high-contrast midnight gradients
        gradients = [
            ("#2b1b54", "#0f0826"),  # Midnight Velvet
            ("#0b3c5d", "#041520"),  # Slate Ocean
            ("#4f3b78", "#1c142b"),  # Royal Plum
            ("#1b4d3e", "#0a1c16"),  # Deep Emerald
            ("#5c2538", "#240e16"),  # Wine Crimson
            ("#1f2833", "#0b0c10"),  # Charcoal Steel
            ("#324851", "#111b1e")   # Muted Pine
        ]
        
        val_hash = int(hashlib.md5(title.encode('utf-8')).hexdigest(), 16)
        c1_hex, c2_hex = gradients[val_hash % len(gradients)]
        
        # Linear diagonal gradient
        grad = QLinearGradient(0, 0, 140, 200)
        grad.setColorAt(0, QColor(c1_hex))
        grad.setColorAt(1, QColor(c2_hex))
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 140, 200, 12, 12)
        
        # Subtle internal border for a floating paper feel
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(1, 1, 138, 198, 11, 11)
        
        # Render clean geometric watermark pattern (5% opacity circle)
        painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
        painter.drawEllipse(70 - 45, 100 - 45, 90, 90)
        painter.drawEllipse(70 - 25, 100 - 25, 50, 50)
        
        # Render Initials
        initials = "".join([w[0].upper() for w in title.split() if w])[:3]
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        painter.drawText(0, 0, 140, 140, Qt.AlignmentFlag.AlignCenter, initials)
        
        # Render clean title text at bottom
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QColor(Constants.C_TEXT_PRIMARY))
        text_rect = QRect(8, 130, 124, 60)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title[:36])
        
        painter.end()
        icon = QIcon(pix)
        self.image_cache[cache_key] = icon
        return icon

    def fetch_metadata_in_background(self, game_hash, title):
        def worker():
            try:
                details = self.igdb_client.fetch_game_details(title)
                if details:
                    meta = self.config_manager.config["game_metadata"].get(game_hash)
                    if meta:
                        meta["developer"] = details["developer"]
                        meta["release_date"] = details["release_date"]
                        meta["summary"] = details["summary"]
                        
                        # Save and trigger UI reload instantly so text metadata shows up on the screen immediately!
                        self.config_manager.save_config()
                        from PyQt6.QtCore import QMetaObject, Qt
                        QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)
                        
                        # Now download cover image quietly in the background
                        if details["cover_image_id"]:
                            cover_path = self.config_manager.covers_dir / f"{game_hash}.jpg"
                            if self.igdb_client.download_cover(details["cover_image_id"], cover_path):
                                meta["cover_image_id"] = details["cover_image_id"]
                                self.config_manager.save_config()
                                # Trigger second UI reload for the freshly downloaded cover image
                                QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)
            except Exception as e:
                print(f"Background metadata enrichment failed for {title}: {e}")
            finally:
                self.enriching_hashes.discard(game_hash)
                
        threading.Thread(target=worker, daemon=True).start()

    def on_game_selected(self, item):
        if not item:
            self.banner.set_game(None, None, False)
            return
            
        game_data = item.data(Qt.ItemDataRole.UserRole)
        cover_path = self.config_manager.covers_dir / f"{game_data['hash']}.jpg"
        
        pix = QPixmap()
        if cover_path.exists():
            pix.load(str(cover_path))
            
        favs = self.config_manager.config.get("favorites", [])
        is_fav = game_data["hash"] in favs
        
        self.banner.set_game(game_data, pix, is_fav)
        
        # Prevent thread duplication and auto-enrich metadata silently in background if keys are configured
        if game_data["hash"] not in self.enriching_hashes:
            if self.igdb_client.is_configured():
                summary = game_data.get("summary", "")
                is_placeholder = (
                    not summary or 
                    summary.startswith("Local ROM") or 
                    summary.startswith("Local PC Game") or 
                    game_data.get("developer") == "Unknown Developer" or 
                    not cover_path.exists()
                )
                if is_placeholder:
                    self.enriching_hashes.add(game_data["hash"])
                    self.fetch_metadata_in_background(game_data["hash"], game_data["title"])

    def toggle_selected_favorite(self):
        item = self.games_list.currentItem()
        if not item:
            return
            
        game_data = item.data(Qt.ItemDataRole.UserRole)
        g_hash = game_data["hash"]
        
        favs = self.config_manager.config.setdefault("favorites", [])
        if g_hash in favs:
            favs.remove(g_hash)
            self.statusBar().showMessage(f"Removed '{game_data['title']}' from favorites.")
        else:
            favs.append(g_hash)
            self.statusBar().showMessage(f"Added '{game_data['title']}' to favorites.")
            
        self.config_manager.save_config()
        self.repopulate_sidebar_tree()
        self.repopulate_game_list()

    def show_current_game_info_modal(self):
        item = self.games_list.currentItem()
        if not item:
            return
        game_data = item.data(Qt.ItemDataRole.UserRole)
        cover_path = self.config_manager.covers_dir / f"{game_data['hash']}.jpg"
        
        pix = QPixmap()
        if cover_path.exists():
            pix.load(str(cover_path))
            
        dialog = GameBriefInfoModal(game_data, pix, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.launch_selected_game()

    def show_game_context_menu(self, pos):
        item = self.games_list.itemAt(pos)
        if not item:
            return
            
        # Select the item that was right-clicked
        self.games_list.setCurrentItem(item)
        
        game_data = item.data(Qt.ItemDataRole.UserRole)
        g_hash = game_data["hash"]
        
        menu = QMenu(self)
        
        act_play = menu.addAction("▶ Play Game")
        act_info = menu.addAction("ℹ See Game Info")
        act_fav = menu.addAction("⭐ Toggle Favorite")
        act_edit = menu.addAction("✏ Edit Details...")
        
        act_fetch_igdb = menu.addAction("🔍 Fetch IGDB Metadata")
        act_fetch_igdb.setEnabled(self.igdb_client.is_configured())
        
        menu.addSeparator()
        
        is_pc_or_xbox = game_data.get("platform") in ["PC", "Xbox"]
        act_open_dir = menu.addAction("📂 Open Installation Folder" if is_pc_or_xbox else "📂 Open File Location")
        act_delete = menu.addAction("🗑 Delete Game from Library")
        
        action = menu.exec(self.games_list.viewport().mapToGlobal(pos))
        if action == act_play:
            self.launch_selected_game()
        elif action == act_info:
            self.show_current_game_info_modal()
        elif action == act_fav:
            self.toggle_selected_favorite()
        elif action == act_edit:
            self.show_edit_game_details_dialog(game_data)
        elif action == act_fetch_igdb:
            self.statusBar().showMessage(f"Fetching metadata for '{game_data['title']}'...")
            self.fetch_metadata_in_background(game_data["hash"], game_data["title"])
        elif action == act_open_dir:
            file_path = game_data.get("path")
            if file_path:
                if is_pc_or_xbox:
                    game_dir = game_data.get("game_dir")
                    if game_dir and os.path.exists(game_dir):
                        os.startfile(game_dir)
                    elif os.path.exists(file_path) and not file_path.lower().startswith("shell:"):
                        subprocess.Popen(f'explorer /select,"{os.path.normpath(file_path)}"')
                    else:
                        QMessageBox.warning(self, "Unavailable", "No game installation directory is mapped or exists for this title.")
                else:
                    if os.path.exists(file_path):
                        subprocess.Popen(f'explorer /select,"{os.path.normpath(file_path)}"')
                    else:
                        QMessageBox.warning(self, "Unavailable", f"Game ROM file does not exist at:\n{file_path}")
            else:
                QMessageBox.warning(self, "Unavailable", "No file path is mapped for this title.")
        elif action == act_delete:
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to remove '{game_data['title']}' from your library?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.config_manager.config["game_metadata"].pop(g_hash, None)
                if g_hash in self.config_manager.config.get("favorites", []):
                    self.config_manager.config["favorites"].remove(g_hash)
                if g_hash in self.config_manager.config.get("recently_played", []):
                    self.config_manager.config["recently_played"].remove(g_hash)
                    
                self.config_manager.save_config()
                self.load_game_cache()

    def show_edit_game_details_dialog(self, game_data):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Game Metadata")
        dialog.setMinimumWidth(400)
        
        layout = QFormLayout(dialog)
        
        title_edit = QLineEdit(game_data.get("title", ""))
        dev_edit = QLineEdit(game_data.get("developer", ""))
        rel_edit = QLineEdit(game_data.get("release_date", ""))
        desc_edit = QTextEdit()
        desc_edit.setPlainText(game_data.get("summary", ""))
        
        layout.addRow("Title:", title_edit)
        layout.addRow("Developer:", dev_edit)
        layout.addRow("Release Date:", rel_edit)
        layout.addRow("Description:", desc_edit)
        
        btn_cover = QPushButton("Select Custom Poster Art...")
        layout.addRow("Cover Art:", btn_cover)
        
        selected_cover = [None]
        def choose_cover():
            path, _ = QFileDialog.getOpenFileName(dialog, "Choose Poster Cover Art", "", "Images (*.jpg *.png *.jpeg *.webp)")
            if path:
                btn_cover.setText("Poster selected.")
                selected_cover[0] = path
        btn_cover.clicked.connect(choose_cover)
        
        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(dialog.accept)
        bbox.rejected.connect(dialog.reject)
        layout.addRow(bbox)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            g_hash = game_data["hash"]
            meta = self.config_manager.config["game_metadata"].setdefault(g_hash, {})
            meta["title"] = title_edit.text().strip()
            meta["developer"] = dev_edit.text().strip()
            meta["release_date"] = rel_edit.text().strip()
            meta["summary"] = desc_edit.toPlainText().strip()
            
            if selected_cover[0]:
                cover_dest = self.config_manager.covers_dir / f"{g_hash}.jpg"
                try:
                    shutil.copy(selected_cover[0], cover_dest)
                except Exception as e:
                    print(f"Error copying cover: {e}")
                    
            self.config_manager.save_config()
            self.load_game_cache()

    # =============================================================================
    # --- GAME LAUNCH ENGINE ---
    # =============================================================================
    def launch_selected_game(self):
        item = self.games_list.currentItem()
        if not item:
            return
            
        game_data = item.data(Qt.ItemDataRole.UserRole)
        platform = game_data.get("platform")
        g_path = game_data.get("path")
        g_hash = game_data.get("hash")
        
        self.statusBar().showMessage(f"Launching {game_data['title']}...")
        
        if platform == "PC":
            self.launch_pc_game(game_data)
            return
            
        defaults = self.config_manager.config.get("platform_defaults", {})
        default_emu_name = defaults.get(platform)
        
        available = []
        for name, emu in self.config_manager.config.get("emulators", {}).items():
            if platform.lower() in [sys.lower() for sys in emu.get("systems", [])]:
                available.append((name, emu))
                
        if not available:
            QMessageBox.critical(self, "Emulator Required", f"No emulator configured for platform {platform}. Configure an emulator first in the Emulators tab!")
            return
            
        emu_config = None
        if default_emu_name and default_emu_name in self.config_manager.config["emulators"]:
            emu_config = self.config_manager.config["emulators"][default_emu_name]
        elif len(available) == 1:
            emu_config = available[0][1]
        else:
            choices = [a[0] for a in available]
            dialog = QDialog(self)
            dialog.setWindowTitle("Choose Emulator")
            dialog_layout = QVBoxLayout(dialog)
            
            combo = QComboBox()
            combo.addItems(choices)
            dialog_layout.addWidget(QLabel(f"Multiple emulators support {platform}. Select emulator to launch:"))
            dialog_layout.addWidget(combo)
            
            chk_default = QCheckBox("Set as default for this platform")
            dialog_layout.addWidget(chk_default)
            
            bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            bbox.accepted.connect(dialog.accept)
            bbox.rejected.connect(dialog.reject)
            dialog_layout.addWidget(bbox)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_name = combo.currentText()
                emu_config = self.config_manager.config["emulators"][selected_name]
                if chk_default.isChecked():
                    self.config_manager.config["platform_defaults"][platform] = selected_name
                    self.config_manager.save_config()
            else:
                return

        if emu_config:
            self.execute_emulator_process(g_hash, g_path, emu_config)

    def launch_pc_game(self, game_data):
        g_path = game_data["path"]
        g_hash = game_data["hash"]
        
        self.mark_game_recently_played(g_hash)
        
        try:
            if g_path.lower().startswith("steam://"):
                os.startfile(g_path)
                tracking_exe = game_data.get("tracking_exe", "")
                game_dir = game_data.get("game_dir", "")
                self.playtime_tracker.start_tracking(g_hash, 0, tracking_exe, game_dir)
                
            elif g_path.lower().endswith(".lnk") or g_path.lower().endswith(".url"):
                os.startfile(g_path)
                tracking_exe = game_data.get("tracking_exe", "")
                game_dir = game_data.get("game_dir", "")
                self.playtime_tracker.start_tracking(g_hash, 0, tracking_exe, game_dir)
                
            else:
                dir_name = os.path.dirname(g_path)
                proc = subprocess.Popen([g_path], cwd=dir_name if os.path.exists(dir_name) else None)
                self.playtime_tracker.start_tracking(g_hash, proc, g_path, dir_name)
                
        except Exception as e:
            QMessageBox.critical(self, "Launch Failed", f"Could not launch PC game: {e}")

    def execute_emulator_process(self, game_hash, game_path, emu_config):
        self.mark_game_recently_played(game_hash)
        
        emu_path = emu_config["path"]
        args = emu_config.get("args", "")
        
        norm_emu = os.path.normpath(emu_path)
        norm_game = os.path.normpath(game_path)
        
        cmd = [norm_emu]
        if args:
            if "%ROM%" in args:
                formatted_args = args.replace("%ROM%", f'"{norm_game}"')
                cmd.extend(shlex.split(formatted_args))
            else:
                cmd.extend(shlex.split(args))
                cmd.append(norm_game)
        else:
            cmd.append(norm_game)
            
        try:
            proc = subprocess.Popen(cmd)
            self.playtime_tracker.start_tracking(game_hash, proc)
        except Exception as e:
            QMessageBox.critical(self, "Launch Emulator Failed", f"Could not start emulator process:\n{e}")

    def mark_game_recently_played(self, game_hash):
        recents = self.config_manager.config.setdefault("recently_played", [])
        if game_hash in recents:
            recents.remove(game_hash)
        recents.insert(0, game_hash)
        self.config_manager.config["recently_played"] = recents[:24]
        self.config_manager.save_config()
        self.repopulate_sidebar_tree()

    def on_playtime_finished(self, game_hash, total_playtime):
        self.load_game_cache()
        self.statusBar().showMessage(f"Play session recorded. Stats synced.", 5000)

    # =============================================================================
    # --- SETTINGS / EMULATORS / DIRECTORIES CONFIG MANAGEMENT ---
    # =============================================================================
    def update_emulators_tree(self):
        self.emu_tree.clear()
        emus = self.config_manager.config.get("emulators", {})
        for name, config in emus.items():
            systems = ", ".join(config.get("systems", []))
            exe = config.get("path", "")
            item = QTreeWidgetItem([name, systems, exe])
            self.emu_tree.addTopLevelItem(item)

    def add_custom_emulator_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Custom Emulator")
        dialog.setMinimumWidth(440)
        
        layout = QFormLayout(dialog)
        edit_name = QLineEdit()
        edit_exe = QLineEdit()
        btn_browse = QPushButton("Browse...")
        
        def choose_exe():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Emulator Executable", "", "Executables (*.exe);;All Files (*)")
            if path:
                edit_exe.setText(path)
                if not edit_name.text():
                    edit_name.setText(Path(path).stem.upper())
        btn_browse.clicked.connect(choose_exe)
        
        exe_lay = QHBoxLayout()
        exe_lay.addWidget(edit_exe)
        exe_lay.addWidget(btn_browse)
        
        edit_systems = QLineEdit()
        edit_systems.setPlaceholderText("e.g. PlayStation 3, PlayStation 2, GameCube, Wii")
        edit_args = QLineEdit("%ROM%")
        edit_args.setPlaceholderText("Default launch arguments. Use %ROM% for game file target")
        
        layout.addRow("Emulator Name:", edit_name)
        layout.addRow("Executable Path:", exe_lay)
        layout.addRow("Supported Systems:", edit_systems)
        layout.addRow("Launch Args:", edit_args)
        
        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(dialog.accept)
        bbox.rejected.connect(dialog.reject)
        layout.addRow(bbox)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = edit_name.text().strip()
            exe = edit_exe.text().strip()
            systems = [s.strip() for s in edit_systems.text().split(",") if s.strip()]
            args = edit_args.text().strip()
            
            if name and exe:
                self.config_manager.config.setdefault("emulators", {})[name] = {
                    "path": exe,
                    "systems": systems,
                    "args": args
                }
                self.config_manager.save_config()
                self.update_emulators_tree()

    def remove_selected_emulator(self):
        item = self.emu_tree.currentItem()
        if not item:
            return
        name = item.text(0)
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Remove emulator '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.config.setdefault("emulators", {}).pop(name, None)
            self.config_manager.save_config()
            self.update_emulators_tree()

    def add_library_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Add Game Library Folder")
        if dir_path:
            dir_path = os.path.normpath(dir_path)
            paths = self.config_manager.config.setdefault("game_library_paths", [])
            if dir_path not in paths:
                paths.append(dir_path)
                self.config_manager.save_config()
                self.folders_list.addItem(dir_path)
                self.trigger_full_rom_scan()

    def remove_library_folder(self):
        item = self.folders_list.currentItem()
        if not item:
            return
        path = item.text()
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove folder from libraries list?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.config["game_library_paths"].remove(path)
            self.config_manager.save_config()
            self.folders_list.takeItem(self.folders_list.row(item))

    def save_settings(self):
        self.config_manager.config["igdb_client_id"] = self.edit_client_id.text().strip()
        self.config_manager.config["igdb_client_secret"] = self.edit_client_secret.text().strip()
        self.config_manager.save_config()
        
        self.igdb_client = IGDBClient(
            self.config_manager.config["igdb_client_id"],
            self.config_manager.config["igdb_client_secret"],
            self.config_manager
        )

    def closeEvent(self, event):
        self.config_manager.save_config()
        event.accept()

# =============================================================================
# --- MAIN APPLICATION BLOCK ---
# =============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    
    config_obj = ConfigManager()
    window = EmulatorHubWindow(config_obj)
    window.show()
    sys.exit(app.exec())