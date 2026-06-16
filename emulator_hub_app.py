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
    QTextEdit, QSystemTrayIcon
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QColor, QBrush, QPen, QPainter, QLinearGradient, QAction
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
    # Emitted from background thread when a single game's metadata has been enriched
    metadata_enriched = pyqtSignal(str)  # game_hash
    # Emitted from background thread when a single game's metadata enrichment fails/not found
    metadata_fetch_failed = pyqtSignal(str, str)  # game_hash, title

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.image_cache = {} # Local in-memory QPixmap cache
        self._cover_cache = {}  # Hash -> QIcon cache for covers (avoids disk reads on every refresh)
        self.enriching_hashes = set() # Track games currently fetching metadata to prevent duplicate threads
        self._pending_enrichments = 0  # Count of in-flight background enrichments

        # Debounce timer: collapses rapid load_game_cache calls from concurrent enrichments
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(600)  # ms
        self._refresh_timer.timeout.connect(self.load_game_cache)

        # Connect metadata_enriched signal to in-place hot-refresh slot
        self.metadata_enriched.connect(self._on_single_enrichment_done)
        self.metadata_fetch_failed.connect(self._on_metadata_fetch_failed)

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
        self.currently_playing_hash = None  # Hash of the game currently running
        
        self.setWindowTitle(f"{Constants.APP_NAME} v{Constants.VERSION}")
        self.setMinimumSize(1260, 800)
        
        self.setup_theme()
        self.setup_ui()
        self.load_game_cache()
        
        # Auto scan games on startup if configured
        if self.config_manager.config.get("auto_scan_on_startup", True):
            QTimer.singleShot(1000, self.trigger_silent_pc_game_autoscan)
            QTimer.singleShot(2500, self._run_quick_rom_scan_startup)
            
        self.setup_tray()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Use gamepad icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "Gamepad.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            self.tray_icon.setIcon(QIcon())
            
        tray_menu = QMenu()
        
        show_action = QAction("Show Lair", self)
        show_action.triggered.connect(self.showNormal)
        tray_menu.addAction(show_action)
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        self.config_manager.save_config()
        if self.config_manager.config.get("minimize_to_tray_on_launch", False):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Lair",
                "App minimized to tray. Right-click the icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            event.accept()

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
        self.btn_dash = self.create_nav_button("STATS")
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
        
        # --- TAB 1: STATS ---
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
                
        # If stats page, refresh metrics
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
        sidebar.setFixedWidth(286)
        sidebar.setStyleSheet(f"""
            background-color: {Constants.C_BG_PANEL};
            border-right: 1.5px solid {Constants.C_BORDER};
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(18, 20, 18, 18)
        sidebar_layout.setSpacing(14)
        
        sidebar_header = QFrame()
        sidebar_header.setFixedHeight(72)
        sidebar_header.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(140, 82, 255, 0.16), stop:1 rgba(0, 229, 255, 0.08));
            border: 1px solid {Constants.C_BORDER};
            border-radius: 14px;
        """)
        header_layout = QVBoxLayout(sidebar_header)
        header_layout.setContentsMargins(14, 10, 14, 8)
        header_layout.setSpacing(4)
        
        sidebar_title = QLabel("LIBRARY")
        sidebar_title.setFont(QFont("Segoe UI", 14, QFont.Weight.ExtraBold))
        sidebar_title.setStyleSheet(f"color: {Constants.C_TEXT_PRIMARY}; letter-spacing: 1.5px;")
        sidebar_subtitle = QLabel("Browse, filter, and organize your collection")
        sidebar_subtitle.setFont(QFont("Segoe UI", 8, QFont.Weight.Normal))
        sidebar_subtitle.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        header_layout.addWidget(sidebar_title)
        header_layout.addWidget(sidebar_subtitle)
        sidebar_layout.addWidget(sidebar_header)
        
        self.sidebar_tree = QTreeWidget()
        self.sidebar_tree.setHeaderHidden(True)
        self.sidebar_tree.setIndentation(14)
        self.sidebar_tree.setAnimated(True)
        self.sidebar_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sidebar_tree.setIconSize(QSize(22, 22))
        self.sidebar_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {Constants.C_TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 500;
                outline: 0;
            }}
            QTreeWidget::item {{
                padding: 9px 8px;
                margin: 3px 0px;
                border-radius: 9px;
                border: 1px solid transparent;
                background-color: transparent;
            }}
            QTreeWidget::item:hover {{
                background-color: rgba(0, 229, 255, 0.10);
                border-color: rgba(0, 229, 255, 0.16);
            }}
            QTreeWidget::item:selected {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(0, 229, 255, 0.20), stop:1 rgba(140, 82, 255, 0.20));
                color: {Constants.C_ACCENT_CYAN};
                border-color: rgba(0, 229, 255, 0.22);
                font-weight: bold;
            }}
            QTreeView::branch:has-children:!has-siblings:closed,
            QTreeView::branch:closed:has-children:has-siblings {{
                border-image: none;
                image: none;
            }}
            QTreeView::branch:open:has-children:!has-siblings,
            QTreeView::branch:open:has-children:has-siblings  {{
                border-image: none;
                image: none;
            }}
        """)
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
        self.banner.stop_clicked.connect(self.stop_current_game)
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
        
        # + ADD GAME button
        btn_add_game = QPushButton("＋ ADD GAME")
        btn_add_game.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_game.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_ACCENT_VIOLET}, stop:1 #6a3de8);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_VIOLET_HOVER}, stop:1 #7b5af0);
            }}
        """)
        btn_add_game.clicked.connect(self.add_custom_game_dialog)
        view_layout.addWidget(btn_add_game)
        
        # Refresh library button
        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedSize(32, 28)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setToolTip("Refresh Library")
        btn_refresh.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1.5px solid {Constants.C_BORDER};
                border-radius: 5px;
                color: {Constants.C_TEXT_SECONDARY};
                font-size: 14px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_BORDER};
                color: #ffffff;
            }}
        """)
        btn_refresh.clicked.connect(self.refresh_library)
        view_layout.addWidget(btn_refresh)
        
        # Scan for new games button
        btn_scan = QPushButton("🔍 SCAN")
        btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_scan.setToolTip("Scan all library folders for new games")
        btn_scan.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_ACCENT_CYAN}, stop:1 #0097a7);
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26f5ff, stop:1 #00bcd4);
            }}
        """)
        btn_scan.clicked.connect(self._trigger_quick_scan_all)
        view_layout.addWidget(btn_scan)
        
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
        self.games_list.verticalScrollBar().setSingleStep(100)
        self.games_list.setSpacing(8)
        self.games_list.itemClicked.connect(self.on_game_selected)
        self.games_list.currentItemChanged.connect(lambda curr, prev: self.on_game_selected(curr))
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
        layout.setSpacing(20)
        
        # Header block
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 5)
        header_layout.setSpacing(4)
        
        title = QLabel("🎮 EMULATORS & ENGINES")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; letter-spacing: 1.5px;")
        
        subtitle = QLabel("Configure supported systems, map game file extensions, and scan local drives for emulator executables.")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_widget)
        
        # Emulator table tree
        self.emu_tree = QTreeWidget()
        self.emu_tree.setHeaderLabels(["Emulator", "Systems supported", "Executable Location"])
        self.emu_tree.setColumnWidth(0, 200)
        self.emu_tree.setColumnWidth(1, 300)
        
        # Style tree widget beautifully
        self.emu_tree.setAlternatingRowColors(False)
        self.emu_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.emu_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 12px;
                padding: 12px;
                color: #ffffff;
            }}
            QTreeWidget::item {{
                height: 40px;
                border-bottom: 1px solid {Constants.C_BORDER};
                color: #ffffff;
            }}
            QTreeWidget::item:hover {{
                background-color: rgba(255, 255, 255, 0.025);
            }}
            QTreeWidget::item:selected {{
                background-color: rgba(0, 229, 255, 0.08);
                color: {Constants.C_ACCENT_CYAN};
            }}
            QHeaderView::section {{
                background-color: rgba(255, 255, 255, 0.015);
                color: {Constants.C_ACCENT_CYAN};
                padding: 10px 14px;
                border: none;
                border-bottom: 1px solid {Constants.C_BORDER};
                font-weight: bold;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
        """)
        layout.addWidget(self.emu_tree)
        
        # Buttons panel
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        btn_style_violet = f"""
            QPushButton {{
                background-color: {Constants.C_ACCENT_VIOLET};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_VIOLET_HOVER};
            }}
        """
        
        btn_style_border = f"""
            QPushButton {{
                background-color: transparent;
                color: {Constants.C_TEXT_PRIMARY};
                border: 1.5px solid {Constants.C_BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.03);
                border-color: {Constants.C_TEXT_MUTED};
            }}
        """
        
        btn_style_cyan = f"""
            QPushButton {{
                background-color: transparent;
                color: {Constants.C_ACCENT_CYAN};
                border: 1.5px solid {Constants.C_ACCENT_CYAN};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 229, 255, 0.06);
            }}
        """
        
        btn_style_error = f"""
            QPushButton {{
                background-color: transparent;
                color: {Constants.C_ERROR};
                border: 1.5px solid {Constants.C_ERROR};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 85, 127, 0.06);
            }}
        """
        
        btn_scan = QPushButton("🔍 AUTO-DETECT EMULATORS")
        btn_scan.setStyleSheet(btn_style_violet)
        btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_scan.clicked.connect(self.auto_detect_emulators)
        btn_layout.addWidget(btn_scan)
        
        btn_add = QPushButton("+ ADD CUSTOM EMULATOR")
        btn_add.setStyleSheet(btn_style_border)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.add_custom_emulator_dialog)
        btn_layout.addWidget(btn_add)
        
        btn_edit_emu = QPushButton("✏ EDIT SELECTED")
        btn_edit_emu.setStyleSheet(btn_style_cyan)
        btn_edit_emu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit_emu.clicked.connect(self.edit_selected_emulator)
        btn_layout.addWidget(btn_edit_emu)
        
        btn_run_emu = QPushButton("▶ RUN EMULATOR")
        btn_run_emu.setStyleSheet(btn_style_cyan)
        btn_run_emu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_run_emu.clicked.connect(self.run_selected_emulator)
        btn_layout.addWidget(btn_run_emu)
        
        btn_remove = QPushButton("🗑 REMOVE SELECTED")
        btn_remove.setStyleSheet(btn_style_error)
        btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
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
        scroll.verticalScrollBar().setSingleStep(100)
        
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
        
        # 1b. Emulator Search Folders Manager
        box_emu_folders = QGroupBox("EMULATOR SEARCH FOLDERS (For auto-detecting emulators)")
        emu_folder_layout = QVBoxLayout(box_emu_folders)
        emu_folder_layout.setContentsMargins(12, 20, 12, 12)
        
        self.emu_folders_list = QListWidget()
        self.emu_folders_list.addItems(self.config_manager.config.get("emulator_search_paths", []))
        emu_folder_layout.addWidget(self.emu_folders_list)
        
        emu_btn_layout = QHBoxLayout()
        btn_add_ef = QPushButton("+ ADD FOLDER")
        btn_add_ef.clicked.connect(self.add_emulator_folder)
        emu_btn_layout.addWidget(btn_add_ef)
        
        btn_rem_ef = QPushButton("🗑 REMOVE SELECTED")
        btn_rem_ef.clicked.connect(self.remove_emulator_folder)
        emu_btn_layout.addWidget(btn_rem_ef)
        emu_btn_layout.addStretch()
        
        emu_folder_layout.addLayout(emu_btn_layout)
        content_layout.addWidget(box_emu_folders)
        
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
        
        # 4. App Behavior Panel
        box_behavior = QGroupBox("APPLICATION BEHAVIOR")
        behavior_layout = QVBoxLayout(box_behavior)
        behavior_layout.setContentsMargins(12, 20, 12, 12)
        
        self.chk_tray = QCheckBox("Minimize to system tray on close / game launch")
        self.chk_tray.setChecked(self.config_manager.config.get("minimize_to_tray_on_launch", False))
        self.chk_tray.setStyleSheet(f"color: {Constants.C_TEXT_PRIMARY}; font-weight: normal;")
        
        def save_behavior():
            self.config_manager.config["minimize_to_tray_on_launch"] = self.chk_tray.isChecked()
            self.config_manager.save_config()
            
        self.chk_tray.stateChanged.connect(save_behavior)
        behavior_layout.addWidget(self.chk_tray)
        content_layout.addWidget(box_behavior)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return widget

    # =============================================================================
    # --- LOGICAL CORE REDESIGNS ---
    # =============================================================================
    @staticmethod
    def _calculate_folder_size(folder_path):
        """Walk a directory tree and return total size in bytes."""
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for fn in filenames:
                    fp = os.path.join(dirpath, fn)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def _calculate_missing_sizes_worker(self):
        """Background worker that calculates folder sizes for games with size=0."""
        try:
            updated = False
            metadata_map = self.config_manager.config.get("game_metadata", {})
            for g_hash, game in list(metadata_map.items()):
                if game.get("size", 0) > 0:
                    continue
                # Determine the best folder or file to measure
                game_dir = game.get("game_dir", "")
                game_path = game.get("path", "")
                computed_size = 0
                if game_dir and os.path.isdir(game_dir):
                    computed_size = self._calculate_folder_size(game_dir)
                elif game_path and os.path.isdir(game_path):
                    computed_size = self._calculate_folder_size(game_path)
                elif game_path and os.path.isfile(game_path):
                    try:
                        computed_size = os.path.getsize(game_path)
                    except OSError:
                        pass
                if computed_size > 0:
                    game["size"] = computed_size
                    updated = True
            if updated:
                self.config_manager.save_config()
                from PyQt6.QtCore import QMetaObject
                QMetaObject.invokeMethod(self, "_apply_calculated_sizes", Qt.ConnectionType.QueuedConnection)
        except Exception as e:
            print(f"Error calculating game sizes: {e}")

    def _apply_calculated_sizes(self):
        """Update in-memory game data map with newly calculated sizes (called on main thread)."""
        metadata_map = self.config_manager.config.get("game_metadata", {})
        changed = False
        for g_hash, cached in self.games_data_map.items():
            meta = metadata_map.get(g_hash)
            if meta and meta.get("size", 0) > 0 and cached.get("size", 0) == 0:
                cached["size"] = meta["size"]
                changed = True
        if changed:
            self.repopulate_game_list()

    def load_game_cache(self):
        # Read from configuration data map
        self.games_data_map.clear()
        metadata_map = self.config_manager.config.get("game_metadata", {})
        
        has_missing_sizes = False
        for g_hash, game in metadata_map.items():
            # Hydrate game properties
            # Compute last played timestamp from sessions
            sessions = game.get("sessions", [])
            last_played_ts = 0
            if sessions:
                last_played_ts = max(s.get("timestamp", 0) for s in sessions)
            self.games_data_map[g_hash] = {
                "title": game.get("title", ""),
                "path": game.get("path", ""),
                "hash": g_hash,
                "platform": game.get("platform", ""),
                "size": game.get("size", 0),
                "playtime": game.get("playtime", 0),
                "last_played": last_played_ts,
                "developer": game.get("developer", "Unknown Developer"),
                "release_date": game.get("release_date", "N/A"),
                "summary": game.get("summary", ""),
                "genres": game.get("genres", []),
                "igdb_score": game.get("igdb_score"),
                "igdb_rating_count": game.get("igdb_rating_count", 0),
                "tracking_exe": game.get("tracking_exe", ""),
                "game_dir": game.get("game_dir", ""),
                "auto_fetch_disabled": game.get("auto_fetch_disabled", False)
            }
            if game.get("size", 0) == 0:
                has_missing_sizes = True
            
        self.rebuild_platform_mappings()
        self.repopulate_sidebar_tree()
        self.repopulate_game_list()
        self.update_emulators_tree()
        
        # Lazily calculate missing game sizes in background
        if has_missing_sizes:
            threading.Thread(target=self._calculate_missing_sizes_worker, daemon=True).start()

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
            
            games_to_fetch = []
            for p_game in all_pc_games:
                g_path = p_game["path"]
                g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
                if g_hash not in self.config_manager.config["game_metadata"]:
                    games_to_fetch.append((g_hash, p_game))
            
            if games_to_fetch:
                import concurrent.futures
                def fetch_silent(item):
                    ghash, pg = item
                    details = self.igdb_client.fetch_game_details(pg["title"], platform=pg.get("platform", "PC"))
                    return ghash, pg, details
                    
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {executor.submit(fetch_silent, item): item for item in games_to_fetch}
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            ghash, pg, details = future.result()
                        except Exception:
                            continue
                        
                        dev = "Unknown Developer"
                        rel = "N/A"
                        summary = "Local PC Game"
                        cover_id = ""
                        score = None
                        score_count = 0
                        
                        if details:
                            dev = details["developer"]
                            rel = details["release_date"]
                            summary = details["summary"]
                            cover_id = details["cover_image_id"]
                            score = details.get("igdb_score")
                            score_count = details.get("igdb_rating_count", 0)
                            
                        self.config_manager.config["game_metadata"][ghash] = {
                            "title": pg["title"],
                            "path": pg["path"],
                            "platform": pg.get("platform", "PC"),
                            "playtime": 0,
                            "sessions": [],
                            "developer": dev,
                            "release_date": rel,
                            "summary": summary,
                            "cover_image_id": cover_id,
                            "igdb_score": score,
                            "igdb_rating_count": score_count,
                            "tracking_exe": pg.get("tracking_exe", ""),
                            "game_dir": pg.get("game_dir", ""),
                            "size": 0
                        }
                        
                        if cover_id:
                            cover_path = self.config_manager.covers_dir / f"{ghash}.jpg"
                            try:
                                self.igdb_client.download_cover(cover_id, cover_path)
                            except Exception:
                                pass
                                
                        added_count += 1
            
            if added_count > 0:
                self.igdb_client.flush_cache()
                self.config_manager.save_config()
                from PyQt6.QtCore import QMetaObject
                QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)
        except Exception as e:
            print(f"Error in background silent scan: {e}")

    def trigger_pc_game_autoscan(self):
        self.statusBar().showMessage("Auto-scanning PC Games folder, Steam, Epic Games, Xbox libraries...")
        QApplication.processEvents()
        threading.Thread(target=self._run_pc_game_autoscan, daemon=True).start()

    def _run_pc_game_autoscan(self):
        try:
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
            
            games_to_fetch = []
            for p_game in all_pc_games:
                g_path = p_game["path"]
                g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
                if g_hash not in self.config_manager.config["game_metadata"]:
                    games_to_fetch.append((g_hash, p_game))
            
            if games_to_fetch:
                import concurrent.futures
                
                def fetch_pc_meta(item):
                    ghash, pg = item
                    details = self.igdb_client.fetch_game_details(pg["title"], platform=pg.get("platform", "PC"))
                    return ghash, pg, details
                    
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {executor.submit(fetch_pc_meta, item): item for item in games_to_fetch}
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            ghash, pg, details = future.result()
                        except Exception:
                            continue
                            
                        dev = "Unknown Developer"
                        rel = "N/A"
                        summary = "Local PC Game"
                        cover_id = ""
                        score = None
                        score_count = 0
                        
                        if details:
                            dev = details["developer"]
                            rel = details["release_date"]
                            summary = details["summary"]
                            cover_id = details["cover_image_id"]
                            score = details.get("igdb_score")
                            score_count = details.get("igdb_rating_count", 0)
                            
                        self.config_manager.config["game_metadata"][ghash] = {
                            "title": pg["title"],
                            "path": pg["path"],
                            "platform": pg.get("platform", "PC"),
                            "playtime": 0,
                            "sessions": [],
                            "developer": dev,
                            "release_date": rel,
                            "summary": summary,
                            "cover_image_id": cover_id,
                            "igdb_score": score,
                            "igdb_rating_count": score_count,
                            "tracking_exe": pg.get("tracking_exe", ""),
                            "game_dir": pg.get("game_dir", ""),
                            "size": 0
                        }
                        
                        if cover_id:
                            cover_path = self.config_manager.covers_dir / f"{ghash}.jpg"
                            try:
                                self.igdb_client.download_cover(cover_id, cover_path)
                            except Exception:
                                pass
                                
                        added_count += 1
                
                # Batch-save cache and config once after all fetches
                self.igdb_client.flush_cache()
                
            self.config_manager.save_config()
            from PyQt6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)
        except Exception as e:
            print(f"Error in PC game autoscan: {e}")

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
            ".sfb": "PlayStation 3",
            ".pkg": "PlayStation 4",
            # Sega
            ".32x": "Sega 32X",
            ".cdi": "Sega Dreamcast",
            ".gdi": "Sega Dreamcast",
            ".sat": "Sega Saturn",
            ".gg": "Game Gear",
            ".sms": "Sega Master System",
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

                # 1.5 Check for directory-based PlayStation 4 games (folders containing sce_sys)
                lower_dirs = [d.lower() for d in dirs]
                if "sce_sys" in lower_dirs:
                    sce_sys_dir = dirs[lower_dirs.index("sce_sys")]
                    ps4_root = Path(root)
                    sfo_path = ps4_root / sce_sys_dir / "param.sfo"
                    if not sfo_path.exists():
                        sfo_path = ps4_root / sce_sys_dir / "PARAM.SFO"
                        
                    parsed_title = None
                    if sfo_path.exists():
                        parsed_title = self.parse_param_sfo(str(sfo_path))
                        
                    title = parsed_title if parsed_title else ps4_root.name
                    
                    roms_found.append({
                        "title": title,
                        "path": str(ps4_root),
                        "platform": "PlayStation 4",
                        "size": 0
                    })
                    # Prune recursion into sce_sys
                    dirs.remove(sce_sys_dir)
                    
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
                        
        # 3. Automatically locate and scan RPCS3 dev_hdd0/game and games folders if RPCS3 is configured!
        rpcs3_game_dirs = []
        shadps4_game_dirs = []
        for name, emu in self.config_manager.config.get("emulators", {}).items():
            is_rpcs3 = "rpcs3" in name.lower() or "rpcs3" in emu.get("path", "").lower() or "playstation 3" in [s.lower() for s in emu.get("systems", [])]
            if is_rpcs3:
                emu_path = emu.get("path", "")
                if emu_path and os.path.exists(emu_path):
                    rpcs3_dir = Path(emu_path).parent
                    dev_hdd0_game = rpcs3_dir / "dev_hdd0" / "game"
                    if dev_hdd0_game.exists():
                        rpcs3_game_dirs.append(dev_hdd0_game)
                    games_folder = rpcs3_dir / "games"
                    if games_folder.exists() and games_folder not in rpcs3_game_dirs:
                        rpcs3_game_dirs.append(games_folder)
                        
            is_shadps4 = "shadps4" in name.lower() or "shadps4" in emu.get("path", "").lower() or "playstation 4" in [s.lower() for s in emu.get("systems", [])]
            if is_shadps4:
                emu_path = emu.get("path", "")
                if emu_path and os.path.exists(emu_path):
                    shad_dir = Path(emu_path).parent
                    shad_games = shad_dir / "user" / "games"
                    if not shad_games.exists():
                        shad_games = shad_dir / "games"
                    if shad_games.exists():
                        shadps4_game_dirs.append(shad_games)
                        
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
                        
        # Now perform the scan on dev_hdd0/game and games directories
        for game_folder in rpcs3_game_dirs:
            try:
                for entry in game_folder.iterdir():
                    if entry.is_dir() and not entry.name.startswith('.'):
                        # Handle both standard (PKG) and disc game folder structures (with PS3_GAME subdirectory)
                        game_root = entry
                        if (entry / "PS3_GAME").is_dir():
                            game_root = entry / "PS3_GAME"
                            
                        eboot_path = game_root / "USRDIR" / "EBOOT.BIN"
                        target_path = str(eboot_path) if eboot_path.exists() else str(game_root)
                        
                        # Get game title from PARAM.SFO offline using our new binary parser!
                        parsed_title = None
                        sfo_path = game_root / "PARAM.SFO"
                        if not sfo_path.exists() and entry != game_root:
                            sfo_path = entry / "PARAM.SFO"
                            
                        if sfo_path.exists():
                            parsed_title = self.parse_param_sfo(str(sfo_path))
                            
                        # Use parsed title, otherwise fall back to serial/folder name
                        title = parsed_title if parsed_title else entry.name
                        
                        # Check for duplicates in roms_found list (path, title, or serial)
                        already_added = False
                        current_serial = entry.name.upper()
                        
                        for r in roms_found:
                            if r.get("platform") == "PlayStation 3":
                                # 1. Check path
                                if r["path"] == target_path:
                                    already_added = True
                                    break
                                # 2. Check title match
                                if r.get("title", "").strip().lower() == title.strip().lower():
                                    already_added = True
                                    break
                                # 3. Check serial/folder name match
                                r_path = r.get("path", "")
                                if r_path:
                                    path_parts = Path(r_path).parts
                                    r_serial = None
                                    for part in path_parts:
                                        cleaned_part = part.replace("-", "").upper()
                                        if len(cleaned_part) == 9 and cleaned_part.isalnum() and cleaned_part[4:].isdigit():
                                            r_serial = cleaned_part
                                            break
                                    
                                    cleaned_current = current_serial.replace("-", "")
                                    if r_serial and len(cleaned_current) == 9 and cleaned_current.isalnum() and cleaned_current[4:].isdigit():
                                        if r_serial == cleaned_current:
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
                print(f"Error scanning RPCS3 folder {game_folder}: {e}")

        # Now perform the scan on shadPS4 games directories
        for game_folder in shadps4_game_dirs:
            try:
                for entry in game_folder.iterdir():
                    if entry.is_dir() and not entry.name.startswith('.'):
                        target_path = str(entry)
                        parsed_title = None
                        
                        # param.sfo is usually in sce_sys folder
                        sfo_path = entry / "sce_sys" / "param.sfo"
                        if not sfo_path.exists():
                            sfo_path = entry / "PARAM.SFO"
                            
                        if sfo_path.exists():
                            parsed_title = self.parse_param_sfo(str(sfo_path))
                            
                        title = parsed_title if parsed_title else entry.name
                        
                        already_added = False
                        for r in roms_found:
                            if r["path"] == target_path:
                                already_added = True
                                break
                                
                        if not already_added:
                            roms_found.append({
                                "title": title,
                                "path": target_path,
                                "platform": "PlayStation 4",
                                "size": 0
                            })
            except Exception as e:
                print(f"Error scanning shadPS4 games folder {game_folder}: {e}")
        added_count = 0
        games_to_fetch = []
        for rom in roms_found:
            g_path = rom["path"]
            g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
            if g_hash not in self.config_manager.config["game_metadata"]:
                games_to_fetch.append((g_hash, rom))
                
        if not games_to_fetch:
            self.load_game_cache()
            self.statusBar().showMessage("No new ROMs found.")
            return
        
        self.statusBar().showMessage(f"Fetching metadata for {len(games_to_fetch)} new ROMs in background...")
        QApplication.processEvents()
        
        def _rom_fetch_worker():
            nonlocal added_count
            import concurrent.futures
            
            def fetch_rom_meta(item):
                ghash, r = item
                details = self.igdb_client.fetch_game_details(r["title"], platform=r.get("platform"))
                return ghash, r, details
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(fetch_rom_meta, item): item for item in games_to_fetch}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        ghash, r, details = future.result()
                    except Exception:
                        continue
                        
                    dev = "Unknown Developer"
                    rel = "N/A"
                    summary = f"Local ROM for {r['platform']}"
                    cover_id = ""
                    score = None
                    score_count = 0
                    
                    if details:
                        dev = details["developer"]
                        rel = details["release_date"]
                        summary = details["summary"]
                        cover_id = details["cover_image_id"]
                        score = details.get("igdb_score")
                        score_count = details.get("igdb_rating_count", 0)
                        
                    self.config_manager.config["game_metadata"][ghash] = {
                        "title": r["title"],
                        "path": r["path"],
                        "platform": r["platform"],
                        "playtime": 0,
                        "sessions": [],
                        "developer": dev,
                        "release_date": rel,
                        "summary": summary,
                        "cover_image_id": cover_id,
                        "igdb_score": score,
                        "igdb_rating_count": score_count,
                        "size": r["size"]
                    }
                    
                    if cover_id:
                        cover_path = self.config_manager.covers_dir / f"{ghash}.jpg"
                        try:
                            self.igdb_client.download_cover(cover_id, cover_path)
                        except Exception:
                            pass
                            
                    added_count += 1
            
            # Batch-save everything once
            self.igdb_client.flush_cache()
            self.config_manager.save_config()
            from PyQt6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)
        
        threading.Thread(target=_rom_fetch_worker, daemon=True).start()

    # =============================================================================
    # --- INTERACTION CONTROLLERS ---
    # =============================================================================
    def repopulate_sidebar_tree(self):
        # Remember current sidebar selection so we can restore it after rebuild
        prev_item = self.sidebar_tree.currentItem()
        prev_role = prev_item.data(0, Qt.ItemDataRole.UserRole) if prev_item else None
        
        self.sidebar_tree.clear()
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        
        # ALL GAMES root
        all_item = QTreeWidgetItem([f"  {Constants.ALL_GAMES_CATEGORY}"])
        all_item.setData(0, Qt.ItemDataRole.UserRole, Constants.ALL_GAMES_CATEGORY)
        icon_path_gamepad = os.path.join(icons_dir, "Gamepad.png")
        if os.path.exists(icon_path_gamepad):
            all_item.setIcon(0, QIcon(icon_path_gamepad))
        else:
            all_item.setText(0, f"🎮  {Constants.ALL_GAMES_CATEGORY}")
        self.sidebar_tree.addTopLevelItem(all_item)
        
        # FAVORITES root
        fav_item = QTreeWidgetItem([f"⭐  {Constants.FAVORITES_CATEGORY}"])
        fav_item.setData(0, Qt.ItemDataRole.UserRole, Constants.FAVORITES_CATEGORY)
        self.sidebar_tree.addTopLevelItem(fav_item)
        
        # RECENTS root
        recent_item = QTreeWidgetItem([f"  {Constants.RECENTS_CATEGORY}"])
        recent_item.setData(0, Qt.ItemDataRole.UserRole, Constants.RECENTS_CATEGORY)
        icon_path_clock = os.path.join(icons_dir, "clock.png")
        if os.path.exists(icon_path_clock):
            recent_item.setIcon(0, QIcon(icon_path_clock))
        else:
            recent_item.setText(0, f"⏱  {Constants.RECENTS_CATEGORY}")
        self.sidebar_tree.addTopLevelItem(recent_item)
        
        # Platforms root
        plat_item = QTreeWidgetItem(["PLATFORMS"])
        plat_item.setData(0, Qt.ItemDataRole.UserRole, "PLATFORMS_ROOT")
        
        platform_icons = {
            "PC": ("💻", None),
            "Xbox": (None, "xbox .png"),
            "PlayStation 4": (None, "PlayStation_logo.svg.png"),
            "PlayStation 3": (None, "PlayStation_logo.svg.png"),
            "PlayStation 2": (None, "PlayStation_logo.svg.png"),
            "PlayStation": (None, "PlayStation_logo.svg.png"),
            "PSP": (None, "PlayStation_logo.svg.png"),
            "Nintendo Switch": (None, "nintendo.png"),
            "Nintendo 3DS": (None, "nintendo.png"),
            "Nintendo DS": (None, "nintendo.png"),
            "GameCube": (None, "nintendo.png"),
            "Wii": (None, "nintendo.png"),
            "Wii U": (None, "nintendo.png"),
            "NES": (None, "nintendo.png"),
            "Super Nintendo": (None, "nintendo.png"),
            "Nintendo 64": (None, "nintendo.png"),
            "Game Boy": (None, "nintendo.png"),
            "Game Boy Color": (None, "nintendo.png"),
            "Game Boy Advance": (None, "nintendo.png"),
            # Sega consoles
            "Sega Dreamcast": (None, "sega.png"),
            "Dreamcast": (None, "sega.png"),
            "Sega Genesis": (None, "sega.png"),
            "Genesis": (None, "sega.png"),
            "Mega Drive": (None, "sega.png"),
            "Sega Mega Drive": (None, "sega.png"),
            "Sega Saturn": (None, "sega.png"),
            "Saturn": (None, "sega.png"),
            "Sega CD": (None, "sega.png"),
            "Sega 32X": (None, "sega.png"),
            "Sega Master System": (None, "sega.png"),
            "Master System": (None, "sega.png"),
            "Game Gear": (None, "sega.png"),
            "Sega Game Gear": (None, "sega.png"),
        }
        
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        
        for platform in sorted(self.games_by_platform.keys()):
            count = len(self.games_by_platform[platform])
            emoji, icon_file = platform_icons.get(platform, ("💿", None))
            
            child = QTreeWidgetItem([f"{emoji if emoji else ''}  {platform} ({count})".strip()])
            child.setData(0, Qt.ItemDataRole.UserRole, platform)
            
            if icon_file:
                icon_path = os.path.join(icons_dir, icon_file)
                if os.path.exists(icon_path):
                    child.setIcon(0, QIcon(icon_path))
                    
            plat_item.addChild(child)
            
        self.sidebar_tree.addTopLevelItem(plat_item)
        plat_item.setExpanded(False)
        
        # Restore previous selection, or default to All Games on first load
        restored = False
        if prev_role:
            for i in range(self.sidebar_tree.topLevelItemCount()):
                top = self.sidebar_tree.topLevelItem(i)
                if top.data(0, Qt.ItemDataRole.UserRole) == prev_role:
                    self.sidebar_tree.setCurrentItem(top)
                    restored = True
                    break
                # Check children (platform nodes)
                for j in range(top.childCount()):
                    child = top.child(j)
                    if child.data(0, Qt.ItemDataRole.UserRole) == prev_role:
                        self.sidebar_tree.setCurrentItem(child)
                        restored = True
                        break
                if restored:
                    break
        if not restored:
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
        if item.data(0, Qt.ItemDataRole.UserRole) == "PLATFORMS_ROOT":
            item.setExpanded(not item.isExpanded())
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
            # Preserve order, and only include games that have actually been played
            games_subset = []
            for g_hash in recents:
                if g_hash in self.games_data_map:
                    game = self.games_data_map[g_hash]
                    if game.get("playtime", 0) > 0:
                        games_subset.append(game)
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
            
            # Load cover icon — use in-memory cache to avoid repeated disk reads
            g_hash = game['hash']
            if g_hash in self._cover_cache:
                icon = self._cover_cache[g_hash]
            else:
                cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                pixmap = QPixmap()
                if cover_path.exists():
                    pixmap.load(str(cover_path))
                icon = QIcon(pixmap) if not pixmap.isNull() else self.generate_gradient_fallback(game["title"])
                self._cover_cache[g_hash] = icon
                
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
        else:
            # Re-trigger selection to ensure banner reflects updated metadata
            self.on_game_selected(self.games_list.currentItem())

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

    def fetch_metadata_in_background(self, game_hash, title, platform=None):
        self._pending_enrichments += 1

        def worker():
            enriched = False
            try:
                details = self.igdb_client.fetch_game_details(title, platform=platform)
                if details:
                    meta = self.config_manager.config["game_metadata"].get(game_hash)
                    if meta:
                        meta["developer"] = details["developer"]
                        meta["release_date"] = details["release_date"]
                        meta["summary"] = details["summary"]
                        meta["igdb_score"] = details.get("igdb_score")
                        meta["igdb_rating_count"] = details.get("igdb_rating_count", 0)

                        # Download cover inline (same thread) to avoid spawning another thread
                        if details["cover_image_id"]:
                            cover_path = self.config_manager.covers_dir / f"{game_hash}.jpg"
                            if self.igdb_client.download_cover(details["cover_image_id"], cover_path):
                                meta["cover_image_id"] = details["cover_image_id"]

                        self.igdb_client.flush_cache()
                        self.config_manager.save_config()
                        enriched = True
            except Exception as e:
                print(f"Background metadata enrichment failed for {title}: {e}")
            finally:
                self.enriching_hashes.discard(game_hash)
                self._pending_enrichments = max(0, self._pending_enrichments - 1)

            if enriched:
                # Emit signal — safely crosses thread boundary via Qt queued connection
                self.metadata_enriched.emit(game_hash)
            else:
                self.metadata_fetch_failed.emit(game_hash, title)

        threading.Thread(target=worker, daemon=True).start()

    def _invalidate_cover_cache(self, game_hash: str):
        """Remove a single entry from the cover icon cache so it is reloaded from disk."""
        self._cover_cache.pop(game_hash, None)
        self.image_cache.pop(game_hash, None)

    def _on_single_enrichment_done(self, game_hash: str):
        """Called on the UI thread after a single game's metadata has been enriched.
        Performs a hot in-place update so the banner reflects new data immediately,
        then schedules a debounced full reload to update covers/sidebar."""
        # 1. Re-read fresh metadata from config into games_data_map
        meta = self.config_manager.config["game_metadata"].get(game_hash)
        if meta and game_hash in self.games_data_map:
            gd = self.games_data_map[game_hash]
            gd["developer"] = meta.get("developer", gd["developer"])
            gd["release_date"] = meta.get("release_date", gd["release_date"])
            gd["summary"] = meta.get("summary", gd["summary"])
            gd["igdb_score"] = meta.get("igdb_score", gd.get("igdb_score"))
            gd["igdb_rating_count"] = meta.get("igdb_rating_count", gd.get("igdb_rating_count", 0))

        # Invalidate cover cache so fresh image is shown next repopulate
        self._invalidate_cover_cache(game_hash)

        # 2. If this game is currently shown in the banner, refresh it immediately
        selected = self.games_list.currentItem()
        if selected:
            sel_data = selected.data(Qt.ItemDataRole.UserRole)
            if sel_data and sel_data.get("hash") == game_hash:
                # Build updated game_data
                updated = self.games_data_map.get(game_hash, sel_data)
                cover_path = self.config_manager.covers_dir / f"{game_hash}.jpg"
                pix = QPixmap()
                if cover_path.exists():
                    pix.load(str(cover_path))
                favs = self.config_manager.config.get("favorites", [])
                is_fav = game_hash in favs
                self.banner.set_game(updated, pix, is_fav)
                self.statusBar().showMessage(
                    f"✅ Metadata loaded for '{updated.get('title', '')}'.", 4000
                )

        # 3. Schedule a debounced full reload (covers grid thumbnails, sidebar counts, etc.)
        #    If more enrichments complete within 600ms, the timer resets — only one reload fires.
        self._refresh_timer.start()

    def _on_metadata_fetch_failed(self, game_hash: str, title: str):
        """Called on the UI thread if metadata enrichment failed or could not be found."""
        print(f"[IGDB] Could not find metadata for '{title}' (hash: {game_hash})")
        selected = self.games_list.currentItem()
        if selected:
            sel_data = selected.data(Qt.ItemDataRole.UserRole)
            if sel_data and sel_data.get("hash") == game_hash:
                self.statusBar().showMessage(f"❌ Couldn't find game details for '{title}' on IGDB.", 4000)

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
                if is_placeholder and not game_data.get("auto_fetch_disabled", False):
                    self.enriching_hashes.add(game_data["hash"])
                    self.fetch_metadata_in_background(game_data["hash"], game_data["title"], platform=game_data.get("platform"))

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
        
        # Force active banner update for the current selection
        current_item = self.games_list.currentItem()
        if current_item:
            self.on_game_selected(current_item)

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
        
        act_fetch_igdb = menu.addAction("🔍 Auto-Fetch Metadata")
        act_fetch_igdb.setEnabled(self.igdb_client.is_configured())
        act_manual_search = menu.addAction("🔎 Search IGDB Manually...")
        act_manual_search.setEnabled(self.igdb_client.is_configured())
        act_remove_metadata = menu.addAction("❌ Remove Metadata")
        
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
            meta_ref = self.config_manager.config["game_metadata"].get(g_hash)
            if meta_ref:
                meta_ref["auto_fetch_disabled"] = False
                self.config_manager.save_config()
            self.fetch_metadata_in_background(game_data["hash"], game_data["title"], platform=game_data.get("platform"))
        elif action == act_manual_search:
            from ui_components import ManualIGDBSearchModal
            modal = ManualIGDBSearchModal(game_data, self.igdb_client, self)
            if modal.exec() == QDialog.DialogCode.Accepted and modal.selected_metadata:
                self.statusBar().showMessage(f"Applying manual metadata for '{game_data['title']}'...")
                # Apply metadata
                new_meta = modal.selected_metadata
                meta_ref = self.config_manager.config["game_metadata"].get(g_hash)
                if meta_ref:
                    meta_ref["title"] = new_meta["title"]
                    meta_ref["developer"] = new_meta["developer"]
                    meta_ref["release_date"] = new_meta["release_date"]
                    meta_ref["summary"] = new_meta["summary"]
                    meta_ref["igdb_score"] = new_meta.get("igdb_score")
                    meta_ref["igdb_rating_count"] = new_meta.get("igdb_rating_count", 0)
                    meta_ref["auto_fetch_disabled"] = False

                    # Hot-patch games_data_map immediately so banner updates now
                    if g_hash in self.games_data_map:
                        gd = self.games_data_map[g_hash]
                        gd["title"] = new_meta["title"]
                        gd["developer"] = new_meta["developer"]
                        gd["release_date"] = new_meta["release_date"]
                        gd["summary"] = new_meta["summary"]
                        gd["igdb_score"] = new_meta.get("igdb_score")
                        gd["igdb_rating_count"] = new_meta.get("igdb_rating_count", 0)

                    self.config_manager.save_config()

                    if new_meta["cover_image_id"]:
                        def download_worker():
                            cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                            if self.igdb_client.download_cover(new_meta["cover_image_id"], cover_path):
                                meta_ref["cover_image_id"] = new_meta["cover_image_id"]
                                self.config_manager.save_config()
                            # Emit signal for in-place banner refresh (cover now on disk)
                            self.metadata_enriched.emit(g_hash)
                        threading.Thread(target=download_worker, daemon=True).start()
                        # Immediately refresh banner without cover (cover arrives later via signal)
                        self._on_single_enrichment_done(g_hash)
                    else:
                        self._on_single_enrichment_done(g_hash)
        elif action == act_remove_metadata:
            meta_ref = self.config_manager.config["game_metadata"].get(g_hash)
            if meta_ref:
                meta_ref["summary"] = "Local ROM" if meta_ref.get("platform") not in ["PC", "Xbox"] else "Local PC Game"
                meta_ref["developer"] = "Unknown Developer"
                meta_ref["release_date"] = "N/A"
                meta_ref["cover_image_id"] = ""
                meta_ref["auto_fetch_disabled"] = True
                cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                if cover_path.exists():
                    try:
                        cover_path.unlink()
                    except Exception:
                        pass
                self.config_manager.save_config()
                self.load_game_cache()
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
    # --- ADD CUSTOM GAME DIALOG ---
    # =============================================================================
    def add_custom_game_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Game to Library")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.C_BG_PANEL};
            }}
            QLabel {{
                color: {Constants.C_TEXT_PRIMARY};
                font-weight: 500;
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        
        # Dialog title
        dlg_title = QLabel("🎮  ADD A GAME TO YOUR LIBRARY")
        dlg_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        dlg_title.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; margin-bottom: 4px;")
        layout.addWidget(dlg_title)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {Constants.C_BORDER};")
        layout.addWidget(sep)
        
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Game Title
        edit_title = QLineEdit()
        edit_title.setPlaceholderText("Enter game title (e.g. God of War 3)")
        edit_title.setMinimumHeight(32)
        form.addRow("Game Title:", edit_title)
        
        # Platform selector
        combo_platform = QComboBox()
        combo_platform.setMinimumHeight(32)
        platforms = [
            "PlayStation 3", "PlayStation 2", "PlayStation", "PSP",
            "Nintendo Switch", "Nintendo 3DS", "Nintendo DS",
            "GameCube", "Wii", "Wii U",
            "NES", "Super Nintendo", "Nintendo 64",
            "Game Boy", "Game Boy Color", "Game Boy Advance",
            "PC", "Xbox"
        ]
        combo_platform.addItems(platforms)
        form.addRow("Platform:", combo_platform)
        
        # Game path (file or folder)
        edit_path = QLineEdit()
        edit_path.setPlaceholderText("Select game folder or executable/ROM file")
        edit_path.setMinimumHeight(32)
        edit_path.setReadOnly(True)
        
        btn_browse_folder = QPushButton("📁 Folder")
        btn_browse_folder.setMinimumHeight(32)
        btn_browse_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_file = QPushButton("📄 File")
        btn_browse_file.setMinimumHeight(32)
        btn_browse_file.setCursor(Qt.CursorShape.PointingHandCursor)
        
        path_layout = QHBoxLayout()
        path_layout.setSpacing(6)
        path_layout.addWidget(edit_path, 1)
        path_layout.addWidget(btn_browse_folder)
        path_layout.addWidget(btn_browse_file)
        
        # Executable selector (populated when folder is chosen)
        combo_exe = QComboBox()
        combo_exe.setMinimumHeight(32)
        combo_exe.setPlaceholderText("Select a folder first to scan for executables")
        combo_exe.setEnabled(False)
        
        exe_label = QLabel("Game Executable:")
        exe_label.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        
        def scan_folder_for_exes(folder_path):
            """Scan a folder (1 level deep) for .exe files and populate combo."""
            combo_exe.clear()
            combo_exe.setEnabled(False)
            exe_files = []
            try:
                folder = Path(folder_path)
                # Scan root level
                for f in folder.iterdir():
                    if f.is_file() and f.suffix.lower() == '.exe':
                        exe_files.append(str(f))
                # Also scan one level deep for common structures (bin/, game/)
                for sub in folder.iterdir():
                    if sub.is_dir() and sub.name.lower() in ('bin', 'binaries', 'game', 'x64', 'win64', 'win32'):
                        for f in sub.iterdir():
                            if f.is_file() and f.suffix.lower() == '.exe':
                                exe_files.append(str(f))
            except Exception:
                pass
            
            if exe_files:
                # Sort and add to combo with relative display names
                exe_files.sort(key=lambda x: Path(x).name.lower())
                for exe_path in exe_files:
                    rel_name = os.path.relpath(exe_path, folder_path)
                    combo_exe.addItem(f"🎮 {rel_name}", exe_path)
                combo_exe.setEnabled(True)
                combo_exe.setPlaceholderText("")
                
                # Try to auto-select the most likely game exe (largest exe, or name-matching)
                folder_name = Path(folder_path).name.lower().replace(' ', '')
                best_idx = 0
                best_size = 0
                for i in range(combo_exe.count()):
                    ep = combo_exe.itemData(i)
                    try:
                        sz = os.path.getsize(ep)
                        fname = Path(ep).stem.lower().replace(' ', '')
                        # Prefer name match
                        if folder_name in fname or fname in folder_name:
                            best_idx = i
                            break
                        if sz > best_size:
                            best_size = sz
                            best_idx = i
                    except Exception:
                        pass
                combo_exe.setCurrentIndex(best_idx)
            else:
                combo_exe.setPlaceholderText("No .exe files found in folder")
        
        def browse_folder():
            folder = QFileDialog.getExistingDirectory(dialog, "Select Game Installation Folder")
            if folder:
                edit_path.setText(os.path.normpath(folder))
                # Auto-fill title from folder name if empty
                if not edit_title.text().strip():
                    edit_title.setText(Path(folder).name)
                # Scan for executables in folder
                scan_folder_for_exes(os.path.normpath(folder))
                    
        def browse_file():
            file_filter = "Game Files (*.iso *.bin *.cue *.chd *.cso *.nsp *.xci *.gcz *.rvz *.wbfs *.gba *.gbc *.gb *.nds *.3ds *.nes *.sfc *.z64 *.sfb *.exe *.lnk);;All Files (*)"
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Game File", "", file_filter)
            if path:
                edit_path.setText(os.path.normpath(path))
                # Auto-fill title from file name if empty
                if not edit_title.text().strip():
                    edit_title.setText(Path(path).stem)
                # Clear exe combo since a direct file was picked
                combo_exe.clear()
                combo_exe.setEnabled(False)
                combo_exe.setPlaceholderText("Not needed — direct file selected")
                # Auto-detect platform from extension
                suffix = Path(path).suffix.lower()
                platform_map = {
                    ".iso": "PlayStation 2", ".gcz": "GameCube", ".rvz": "GameCube",
                    ".wbfs": "Wii", ".nsp": "Nintendo Switch", ".xci": "Nintendo Switch",
                    ".gba": "Game Boy Advance", ".gbc": "Game Boy Color", ".gb": "Game Boy",
                    ".nds": "Nintendo DS", ".3ds": "Nintendo 3DS", ".nes": "NES",
                    ".sfc": "Super Nintendo", ".z64": "Nintendo 64",
                    ".chd": "PlayStation", ".cue": "PlayStation", ".cso": "PSP",
                    ".sfb": "PlayStation 3", ".exe": "PC"
                }
                if suffix in platform_map:
                    idx = combo_platform.findText(platform_map[suffix])
                    if idx >= 0:
                        combo_platform.setCurrentIndex(idx)
                        
        btn_browse_folder.clicked.connect(browse_folder)
        btn_browse_file.clicked.connect(browse_file)
        form.addRow("Game Location:", path_layout)
        form.addRow(exe_label, combo_exe)
        
        # Optional cover art
        btn_cover = QPushButton("🖼  Select Poster Art (optional)")
        btn_cover.setMinimumHeight(32)
        btn_cover.setCursor(Qt.CursorShape.PointingHandCursor)
        selected_cover = [None]
        
        def choose_cover():
            path, _ = QFileDialog.getOpenFileName(dialog, "Choose Poster Cover Art", "", "Images (*.jpg *.png *.jpeg *.webp)")
            if path:
                btn_cover.setText(f"✅ Poster selected: {Path(path).name}")
                btn_cover.setStyleSheet(f"color: {Constants.C_SUCCESS};")
                selected_cover[0] = path
        btn_cover.clicked.connect(choose_cover)
        form.addRow("Cover Art:", btn_cover)
        
        layout.addLayout(form)
        
        # Info hint for PS3 users
        ps3_hint = QLabel("💡 PS3 games: Select the game's installation folder (containing PS3_GAME). "
                          "When you launch a PS3 game, RPCS3 will be opened automatically if configured.")
        ps3_hint.setWordWrap(True)
        ps3_hint.setFont(QFont("Segoe UI", 8))
        ps3_hint.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; padding: 8px 4px;")
        layout.addWidget(ps3_hint)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setMinimumWidth(100)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_add = QPushButton("＋  ADD GAME")
        btn_add.setMinimumHeight(36)
        btn_add.setMinimumWidth(140)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_ACCENT_VIOLET}, stop:1 #6a3de8);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_VIOLET_HOVER}, stop:1 #7b5af0);
            }}
        """)
        btn_add.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_add)
        
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            title = edit_title.text().strip()
            game_path = edit_path.text().strip()
            platform = combo_platform.currentText()
            
            if not title:
                QMessageBox.warning(self, "Missing Title", "Please enter a game title.")
                return
            if not game_path:
                QMessageBox.warning(self, "Missing Path", "Please select a game file or folder.")
                return
                
            # Resolve game path for PS3 folder-based games
            resolved_path = game_path
            game_dir = ""
            if platform == "PlayStation 3" and os.path.isdir(game_path):
                game_dir = game_path
                # Check for PS3_GAME/USRDIR/EBOOT.BIN structure
                eboot = os.path.join(game_path, "PS3_GAME", "USRDIR", "EBOOT.BIN")
                if os.path.exists(eboot):
                    resolved_path = eboot
                else:
                    # Check for USRDIR/EBOOT.BIN directly (if user selected the PS3_GAME folder itself)
                    eboot_alt = os.path.join(game_path, "USRDIR", "EBOOT.BIN")
                    if os.path.exists(eboot_alt):
                        resolved_path = eboot_alt
                    # Otherwise keep the folder path as-is for RPCS3
                    
            elif os.path.isdir(game_path):
                game_dir = game_path
                
            # Try to parse PARAM.SFO for real title (PS3 games)
            if platform == "PlayStation 3":
                sfo_paths = [
                    os.path.join(game_path, "PS3_GAME", "PARAM.SFO"),
                    os.path.join(game_path, "PARAM.SFO"),
                ]
                for sfo_path in sfo_paths:
                    if os.path.exists(sfo_path):
                        parsed_title = self.parse_param_sfo(sfo_path)
                        if parsed_title and title == Path(game_path).name:
                            # Only override if user didn't manually type something custom
                            title = parsed_title
                        break
            
            g_hash = hashlib.md5(resolved_path.encode('utf-8')).hexdigest()
            
            # Check for duplicates
            if g_hash in self.config_manager.config["game_metadata"]:
                QMessageBox.information(self, "Already Exists", f"'{title}' is already in your library.")
                return
            
            # Fetch metadata from IGDB if configured
            dev = "Unknown Developer"
            rel = "N/A"
            summary = f"Custom added {platform} game"
            cover_id = ""
            score = None
            score_count = 0
            
            if self.igdb_client.is_configured():
                details = self.igdb_client.fetch_game_details(title, platform=platform)
                if details:
                    dev = details["developer"]
                    rel = details["release_date"]
                    summary = details["summary"]
                    cover_id = details["cover_image_id"]
                    score = details.get("igdb_score")
                    score_count = details.get("igdb_rating_count", 0)
            
            # Calculate size — prefer game_dir (installation folder) over single file
            game_size = 0
            try:
                if game_dir and os.path.isdir(game_dir):
                    game_size = self._calculate_folder_size(game_dir)
                elif os.path.isdir(resolved_path):
                    game_size = self._calculate_folder_size(resolved_path)
                elif os.path.isfile(resolved_path):
                    game_size = os.path.getsize(resolved_path)
            except Exception:
                pass
            
            # Save to config
            self.config_manager.config["game_metadata"][g_hash] = {
                "title": title,
                "path": resolved_path,
                "platform": platform,
                "playtime": 0,
                "sessions": [],
                "developer": dev,
                "release_date": rel,
                "summary": summary,
                "cover_image_id": cover_id,
                "igdb_score": score,
                "igdb_rating_count": score_count,
                "tracking_exe": combo_exe.currentData() if combo_exe.isEnabled() and combo_exe.currentData() else "",
                "game_dir": game_dir,
                "size": game_size
            }
            
            # Handle cover art
            if selected_cover[0]:
                cover_dest = self.config_manager.covers_dir / f"{g_hash}.jpg"
                try:
                    shutil.copy(selected_cover[0], cover_dest)
                except Exception as e:
                    print(f"Error copying cover: {e}")
            elif cover_id:
                cover_path = self.config_manager.covers_dir / f"{g_hash}.jpg"
                threading.Thread(target=self.igdb_client.download_cover, args=(cover_id, cover_path), daemon=True).start()
            
            self.config_manager.save_config()
            self.load_game_cache()
            self.statusBar().showMessage(f"✅ '{title}' added to library as {platform} game.", 5000)
            
            # Auto-configure RPCS3 hint for PS3 games if no PS3 emulator is configured
            if platform == "PlayStation 3":
                has_ps3_emu = False
                for name, emu in self.config_manager.config.get("emulators", {}).items():
                    if "playstation 3" in [s.lower() for s in emu.get("systems", [])]:
                        has_ps3_emu = True
                        break
                if not has_ps3_emu:
                    QMessageBox.information(
                        self, "PS3 Emulator Needed",
                        "You added a PlayStation 3 game! To launch it, go to the EMULATORS tab "
                        "and add RPCS3 as a custom emulator with 'PlayStation 3' as the supported system.\n\n"
                        "Lair will then automatically open RPCS3 when you boot this game."
                    )

    # =============================================================================
    # --- AUTO-DISCOVER RPCS3 FOR PS3 GAMES ---
    # =============================================================================
    def _auto_discover_rpcs3(self):
        """Try to find rpcs3.exe in common locations if no PS3 emulator is configured."""
        common_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\RPCS3\rpcs3.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\RPCS3\rpcs3.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\RPCS3\rpcs3.exe"),
            os.path.expanduser(r"~\Desktop\rpcs3\rpcs3.exe"),
            os.path.expanduser(r"~\Downloads\rpcs3\rpcs3.exe"),
            r"C:\RPCS3\rpcs3.exe",
            r"D:\RPCS3\rpcs3.exe",
            r"E:\RPCS3\rpcs3.exe",
        ]
        for p in common_paths:
            if os.path.isfile(p):
                return p
        # Search PATH
        rpcs3_in_path = shutil.which("rpcs3")
        if rpcs3_in_path:
            return rpcs3_in_path
        return None

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
        
        # Auto-discover RPCS3 for PS3 games if no emulator is configured
        if not available and platform == "PlayStation 3":
            rpcs3_path = self._auto_discover_rpcs3()
            if rpcs3_path:
                # Auto-register the discovered RPCS3
                self.config_manager.config.setdefault("emulators", {})["RPCS3 (Auto-Detected)"] = {
                    "path": rpcs3_path,
                    "systems": ["PlayStation 3"],
                    "args": ""
                }
                self.config_manager.save_config()
                self.update_emulators_tree()
                available.append(("RPCS3 (Auto-Detected)", self.config_manager.config["emulators"]["RPCS3 (Auto-Detected)"]))
                self.statusBar().showMessage(f"Auto-detected RPCS3 at: {rpcs3_path}")
                
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
        tracking_exe = game_data.get("tracking_exe", "")
        game_dir = game_data.get("game_dir", "")
        
        self.mark_game_recently_played(g_hash)
        
        try:
            if g_path.lower().startswith("steam://"):
                os.startfile(g_path)
                self.playtime_tracker.start_tracking(g_hash, 0, tracking_exe, game_dir)
                self._on_game_launched(g_hash)
                self.statusBar().showMessage(f"Launched '{game_data['title']}' via Steam.")
                
            elif g_path.lower().endswith(".lnk") or g_path.lower().endswith(".url"):
                os.startfile(g_path)
                self.playtime_tracker.start_tracking(g_hash, 0, tracking_exe, game_dir)
                self._on_game_launched(g_hash)
            
            elif tracking_exe and os.path.isfile(tracking_exe):
                # Custom-added game with a selected executable — run the exe directly
                exe_dir = os.path.dirname(tracking_exe)
                proc = subprocess.Popen([tracking_exe], cwd=exe_dir if os.path.exists(exe_dir) else None)
                self.playtime_tracker.start_tracking(g_hash, proc, tracking_exe, exe_dir)
                self._on_game_launched(g_hash)
                
            elif os.path.isdir(g_path):
                # Folder-based game without a tracking_exe — scan for exe and ask user
                exe_files = []
                try:
                    for f in Path(g_path).iterdir():
                        if f.is_file() and f.suffix.lower() == '.exe':
                            exe_files.append(str(f))
                    for sub in Path(g_path).iterdir():
                        if sub.is_dir() and sub.name.lower() in ('bin', 'binaries', 'game', 'x64', 'win64', 'win32'):
                            for f in sub.iterdir():
                                if f.is_file() and f.suffix.lower() == '.exe':
                                    exe_files.append(str(f))
                except Exception:
                    pass
                    
                if not exe_files:
                    QMessageBox.warning(self, "No Executable Found", f"No .exe files found in:\n{g_path}\n\nRight-click the game → Edit Details to set an executable.")
                    return
                    
                if len(exe_files) == 1:
                    chosen_exe = exe_files[0]
                else:
                    # Let user pick from discovered executables
                    pick_dialog = QDialog(self)
                    pick_dialog.setWindowTitle("Select Game Executable")
                    pick_dialog.setMinimumWidth(420)
                    pick_layout = QVBoxLayout(pick_dialog)
                    pick_layout.addWidget(QLabel(f"Multiple executables found in {Path(g_path).name}.\nSelect which one to launch:"))
                    
                    exe_combo = QComboBox()
                    exe_files.sort(key=lambda x: Path(x).name.lower())
                    for ep in exe_files:
                        rel = os.path.relpath(ep, g_path)
                        exe_combo.addItem(f"🎮 {rel}", ep)
                    pick_layout.addWidget(exe_combo)
                    
                    chk_remember = QCheckBox("Remember this choice for next time")
                    chk_remember.setChecked(True)
                    pick_layout.addWidget(chk_remember)
                    
                    bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
                    bbox.accepted.connect(pick_dialog.accept)
                    bbox.rejected.connect(pick_dialog.reject)
                    pick_layout.addWidget(bbox)
                    
                    if pick_dialog.exec() != QDialog.DialogCode.Accepted:
                        return
                    chosen_exe = exe_combo.currentData()
                    
                    if chk_remember.isChecked():
                        meta = self.config_manager.config["game_metadata"].get(g_hash)
                        if meta:
                            meta["tracking_exe"] = chosen_exe
                            self.config_manager.save_config()
                
                exe_dir = os.path.dirname(chosen_exe)
                proc = subprocess.Popen([chosen_exe], cwd=exe_dir if os.path.exists(exe_dir) else None)
                self.playtime_tracker.start_tracking(g_hash, proc, chosen_exe, exe_dir)
                self._on_game_launched(g_hash)
                
            else:
                dir_name = os.path.dirname(g_path)
                proc = subprocess.Popen([g_path], cwd=dir_name if os.path.exists(dir_name) else None)
                self.playtime_tracker.start_tracking(g_hash, proc, g_path, dir_name)
                self._on_game_launched(g_hash)
                
        except Exception as e:
            QMessageBox.critical(self, "Launch Failed", f"Could not launch PC game: {e}")

    def _on_game_launched(self, game_hash):
        self.currently_playing_hash = game_hash
        self.banner.set_playing(True)
        # Minimize main window to save GPU/CPU resources during gameplay
        if self.config_manager.config.get("minimize_to_tray_on_launch", False):
            self.hide()
            self.tray_icon.showMessage(
                "Lair",
                "App minimized to tray while game is running.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self.showMinimized()

    def execute_emulator_process(self, game_hash, game_path, emu_config):
        self.mark_game_recently_played(game_hash)
        
        emu_path = emu_config["path"]
        args = emu_config.get("args", "")
        
        norm_emu = os.path.normpath(emu_path)
        norm_game = os.path.normpath(game_path)
        
        # Hardcode fallback: shadPS4 QT launcher often swallows CLI args. Use core exe directly.
        if "shadps4" in norm_emu.lower() and "launcher" in norm_emu.lower():
            direct_exe = os.path.join(os.path.dirname(norm_emu), "shadPS4.exe")
            if os.path.exists(direct_exe):
                norm_emu = direct_exe
                
        cmd = [norm_emu]
        if args:
            # Split args first using posix=False to preserve backslashes
            split_args = shlex.split(args, posix=False)
            has_rom_token = False
            
            for arg in split_args:
                # Remove surrounding quotes if shlex kept them
                if arg.startswith('"') and arg.endswith('"'):
                    arg = arg[1:-1]
                elif arg.startswith("'") and arg.endswith("'"):
                    arg = arg[1:-1]
                    
                if "%ROM%" in arg:
                    cmd.append(arg.replace("%ROM%", norm_game))
                    has_rom_token = True
                else:
                    cmd.append(arg)
                    
            if not has_rom_token:
                cmd.append(norm_game)
        else:
            cmd.append(norm_game)
            
        # Hardcode fallback logic for specific emulators
        if "shadps4" in norm_emu.lower():
            # If the user selected a directory for the game, launch using Title ID
            if os.path.isdir(norm_game):
                folder_name = os.path.basename(norm_game)
                if cmd[-1] == norm_game:
                    cmd[-1] = folder_name
                if "-g" in cmd:
                    cmd.remove("-g")
            else:
                # It's a direct file (e.g. .elf or .bin)
                if "-g" not in cmd:
                    cmd.insert(-1, "-g")
            
        try:
            emu_dir = os.path.dirname(norm_emu)
            proc = subprocess.Popen(cmd, cwd=emu_dir if os.path.exists(emu_dir) else None)
            self.playtime_tracker.start_tracking(game_hash, proc)
            self._on_game_launched(game_hash)
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
        # Reset playing state — game has exited
        self.currently_playing_hash = None
        self.banner.set_playing(False)
        self.load_game_cache()
        self.statusBar().showMessage("Play session recorded. Stats synced.", 5000)
        
        # Restore window if it was minimized or hidden to tray
        if self.isMinimized() or self.isHidden():
            self.showNormal()
            self.activateWindow()

    def stop_current_game(self):
        """Force-stop the currently tracked game process."""
        if not self.currently_playing_hash:
            return
        game_hash = self.currently_playing_hash
        game_title = self.games_data_map.get(game_hash, {}).get("title", "Game")
        
        # Terminate PIDs via psutil if available
        session = self.playtime_tracker.active_sessions.get(game_hash)
        if session:
            try:
                import psutil
                for pid in list(session.get("pids", [])):
                    try:
                        p = psutil.Process(pid)
                        p.terminate()
                    except Exception:
                        pass
            except ImportError:
                pass
        
        # Also call stop_tracking to save session time
        self.playtime_tracker.stop_tracking(game_hash)
        self.currently_playing_hash = None
        self.banner.set_playing(False)
        self.statusBar().showMessage(f"Stopped '{game_title}'.", 4000)

    def refresh_library(self):
        """Reload game cache and trigger a quick background scan for any newly added games."""
        self.statusBar().showMessage("Refreshing library & scanning for new games...")
        self.load_game_cache()
        # Quick background scan for new games
        threading.Thread(target=self._quick_scan_worker, daemon=True).start()

    def _trigger_quick_scan_all(self):
        """Triggered by the SCAN button in library toolbar."""
        self.statusBar().showMessage("Scanning all library folders for new games...")
        QApplication.processEvents()
        threading.Thread(target=self._quick_scan_worker, daemon=True).start()

    def _run_quick_rom_scan_startup(self):
        """Silent quick ROM scan at startup."""
        threading.Thread(target=self._quick_scan_worker, daemon=True).start()

    def _quick_scan_worker(self):
        """Background worker that does a fast filesystem-only scan for new games.
        New games are written to metadata immediately so they appear in the library,
        then an automatic IGDB enrichment batch is kicked off for all new entries."""
        try:
            new_games = []  # list of (g_hash, entry_dict) for newly discovered games

            # ----------------------------------------------------------------
            # 1. Quick PC game scan (Steam, Epic, Xbox, common folders)
            # ----------------------------------------------------------------
            steam_games = PCGameScanner.scan_steam_games()
            epic_games = PCGameScanner.scan_epic_games()
            xbox_games = PCGameScanner.scan_xbox_games(self.config_manager.config.get("game_library_paths", []))
            common_games = PCGameScanner.scan_common_game_folders(self.config_manager.config["game_library_paths"])

            for pg in steam_games + epic_games + xbox_games + common_games:
                g_path = pg["path"]
                g_hash = hashlib.md5(g_path.encode('utf-8')).hexdigest()
                if g_hash not in self.config_manager.config["game_metadata"]:
                    entry = {
                        "title": pg["title"],
                        "path": pg["path"],
                        "platform": pg.get("platform", "PC"),
                        "playtime": 0,
                        "sessions": [],
                        "developer": "Unknown Developer",
                        "release_date": "N/A",
                        "summary": "Local PC Game",
                        "cover_image_id": "",
                        "tracking_exe": pg.get("tracking_exe", ""),
                        "game_dir": pg.get("game_dir", ""),
                        "size": 0
                    }
                    self.config_manager.config["game_metadata"][g_hash] = entry
                    new_games.append((g_hash, entry))

            # ----------------------------------------------------------------
            # 2. Quick ROM scan from library paths
            # ----------------------------------------------------------------
            PLATFORM_SUFFIXES = {
                ".iso": "PlayStation 2", ".gcz": "GameCube", ".rvz": "GameCube",
                ".wbfs": "Wii", ".nsp": "Nintendo Switch", ".xci": "Nintendo Switch",
                ".gba": "Game Boy Advance", ".gbc": "Game Boy Color", ".gb": "Game Boy",
                ".nds": "Nintendo DS", ".3ds": "Nintendo 3DS", ".nes": "NES",
                ".sfc": "Super Nintendo", ".z64": "Nintendo 64", ".chd": "PlayStation",
                ".cue": "PlayStation", ".cso": "PSP", ".sfb": "PlayStation 3",
                ".pkg": "PlayStation 4",
                # Sega
                ".32x": "Sega 32X", ".cdi": "Sega Dreamcast", ".gdi": "Sega Dreamcast",
                ".sat": "Sega Saturn", ".gg": "Game Gear", ".sms": "Sega Master System",
            }

            for path in self.config_manager.config["game_library_paths"]:
                path_obj = Path(path)
                if not path_obj.exists():
                    continue
                for root, dirs, files in os.walk(path):
                    # Detect PS3 disc-based folders (PS3_GAME subfolder)
                    if "PS3_GAME" in dirs:
                        ps3_root = Path(root)
                        ps3_game_dir = ps3_root / "PS3_GAME"
                        eboot_path = ps3_game_dir / "USRDIR" / "EBOOT.BIN"
                        target_path = str(eboot_path) if eboot_path.exists() else str(ps3_game_dir)
                        # Try to get real title from PARAM.SFO
                        parsed_title = None
                        sfo_candidates = [
                            ps3_game_dir / "PARAM.SFO",
                            ps3_root / "PARAM.SFO",
                        ]
                        for sfo in sfo_candidates:
                            if sfo.exists():
                                parsed_title = self.parse_param_sfo(str(sfo))
                                if parsed_title:
                                    break
                        title = parsed_title if parsed_title else ps3_root.name
                        g_hash = hashlib.md5(target_path.encode('utf-8')).hexdigest()
                        if g_hash not in self.config_manager.config["game_metadata"]:
                            entry = {
                                "title": title, "path": target_path,
                                "platform": "PlayStation 3", "playtime": 0, "sessions": [],
                                "developer": "Unknown Developer", "release_date": "N/A",
                                "summary": "Local ROM for PlayStation 3", "cover_image_id": "", "size": 0
                            }
                            self.config_manager.config["game_metadata"][g_hash] = entry
                            new_games.append((g_hash, entry))
                        dirs.remove("PS3_GAME")

                    # Detect PS4 folders (sce_sys)
                    lower_dirs = [d.lower() for d in dirs]
                    if "sce_sys" in lower_dirs:
                        sce_sys_dir = dirs[lower_dirs.index("sce_sys")]
                        ps4_root = Path(root)
                        sfo_path = ps4_root / sce_sys_dir / "param.sfo"
                        if not sfo_path.exists():
                            sfo_path = ps4_root / sce_sys_dir / "PARAM.SFO"
                        parsed_title = None
                        if sfo_path.exists():
                            parsed_title = self.parse_param_sfo(str(sfo_path))
                        title = parsed_title if parsed_title else ps4_root.name
                        target_path = str(ps4_root)
                        g_hash = hashlib.md5(target_path.encode('utf-8')).hexdigest()
                        if g_hash not in self.config_manager.config["game_metadata"]:
                            entry = {
                                "title": title, "path": target_path,
                                "platform": "PlayStation 4", "playtime": 0, "sessions": [],
                                "developer": "Unknown Developer", "release_date": "N/A",
                                "summary": "Local ROM for PlayStation 4", "cover_image_id": "", "size": 0
                            }
                            self.config_manager.config["game_metadata"][g_hash] = entry
                            new_games.append((g_hash, entry))
                        dirs.remove(sce_sys_dir)

                    # File suffix scanning
                    for f in files:
                        file_path = Path(root) / f
                        suffix = file_path.suffix.lower()
                        if suffix in PLATFORM_SUFFIXES:
                            platform = PLATFORM_SUFFIXES[suffix]
                            if platform == "PlayStation 3" and file_path.name.upper() == "PS3_DISC.SFB":
                                continue
                            target_path = str(file_path)
                            g_hash = hashlib.md5(target_path.encode('utf-8')).hexdigest()
                            if g_hash not in self.config_manager.config["game_metadata"]:
                                entry = {
                                    "title": file_path.stem, "path": target_path,
                                    "platform": platform, "playtime": 0, "sessions": [],
                                    "developer": "Unknown Developer", "release_date": "N/A",
                                    "summary": f"Local ROM for {platform}", "cover_image_id": "",
                                    "size": file_path.stat().st_size
                                }
                                self.config_manager.config["game_metadata"][g_hash] = entry
                                new_games.append((g_hash, entry))

            # ----------------------------------------------------------------
            # 3. Scan RPCS3 dev_hdd0/game folders (fixes PS3 new-game detection)
            # ----------------------------------------------------------------
            rpcs3_game_dirs = []
            for name, emu in self.config_manager.config.get("emulators", {}).items():
                is_rpcs3 = (
                    "rpcs3" in name.lower() or
                    "rpcs3" in emu.get("path", "").lower() or
                    "playstation 3" in [s.lower() for s in emu.get("systems", [])]
                )
                if is_rpcs3:
                    emu_path = emu.get("path", "")
                    if emu_path and os.path.exists(emu_path):
                        rpcs3_dir = Path(emu_path).parent
                        dev_hdd0_game = rpcs3_dir / "dev_hdd0" / "game"
                        if dev_hdd0_game.exists() and dev_hdd0_game not in rpcs3_game_dirs:
                            rpcs3_game_dirs.append(dev_hdd0_game)
                        games_folder = rpcs3_dir / "games"
                        if games_folder.exists() and games_folder not in rpcs3_game_dirs:
                            rpcs3_game_dirs.append(games_folder)

            # Also check library paths that point to dev_hdd0
            for path in self.config_manager.config["game_library_paths"]:
                path_obj = Path(path)
                if "dev_hdd0" in str(path_obj).lower():
                    if path_obj.name.lower() == "dev_hdd0":
                        candidate = path_obj / "game"
                        if candidate.exists() and candidate not in rpcs3_game_dirs:
                            rpcs3_game_dirs.append(candidate)
                    elif path_obj.name.lower() == "game" and path_obj.parent.name.lower() == "dev_hdd0":
                        if path_obj not in rpcs3_game_dirs:
                            rpcs3_game_dirs.append(path_obj)

            for game_folder in rpcs3_game_dirs:
                try:
                    for entry in game_folder.iterdir():
                        if not entry.is_dir() or entry.name.startswith('.'):
                            continue
                        game_root = entry
                        if (entry / "PS3_GAME").is_dir():
                            game_root = entry / "PS3_GAME"
                            
                        eboot_path = game_root / "USRDIR" / "EBOOT.BIN"
                        target_path = str(eboot_path) if eboot_path.exists() else str(game_root)
                        g_hash = hashlib.md5(target_path.encode('utf-8')).hexdigest()
                        if g_hash not in self.config_manager.config["game_metadata"]:
                            parsed_title = None
                            sfo_path = game_root / "PARAM.SFO"
                            if not sfo_path.exists() and entry != game_root:
                                sfo_path = entry / "PARAM.SFO"
                                
                            if sfo_path.exists():
                                parsed_title = self.parse_param_sfo(str(sfo_path))
                            title = parsed_title if parsed_title else entry.name
                            
                            # Check if this PS3 game is already in the library (under a different path)
                            is_duplicate = False
                            current_serial = entry.name.upper()
                            
                            for existing_meta in self.config_manager.config["game_metadata"].values():
                                if existing_meta.get("platform") == "PlayStation 3":
                                    # 1. Check title match
                                    if existing_meta.get("title", "").strip().lower() == title.strip().lower():
                                        is_duplicate = True
                                        break
                                    # 2. Check serial/folder name match
                                    existing_path = existing_meta.get("path", "")
                                    if existing_path:
                                        path_parts = Path(existing_path).parts
                                        existing_serial = None
                                        for part in path_parts:
                                            cleaned_part = part.replace("-", "").upper()
                                            if len(cleaned_part) == 9 and cleaned_part.isalnum() and cleaned_part[4:].isdigit():
                                                existing_serial = cleaned_part
                                                break
                                        
                                        cleaned_current = current_serial.replace("-", "")
                                        if existing_serial and len(cleaned_current) == 9 and cleaned_current.isalnum() and cleaned_current[4:].isdigit():
                                            if existing_serial == cleaned_current:
                                                is_duplicate = True
                                                break
                                                
                            if is_duplicate:
                                continue
                                
                            meta_entry = {
                                "title": title, "path": target_path,
                                "platform": "PlayStation 3", "playtime": 0, "sessions": [],
                                "developer": "Unknown Developer", "release_date": "N/A",
                                "summary": "Local ROM for PlayStation 3", "cover_image_id": "", "size": 0
                            }
                            self.config_manager.config["game_metadata"][g_hash] = meta_entry
                            new_games.append((g_hash, meta_entry))
                except Exception as e:
                    print(f"Error scanning RPCS3 dev_hdd0/games in quick scan: {e}")

            if not new_games:
                return

            # Save the skeleton entries so the library shows up immediately
            self.config_manager.save_config()
            from PyQt6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "load_game_cache", Qt.ConnectionType.QueuedConnection)

            # ----------------------------------------------------------------
            # 4. Auto-fetch IGDB metadata for all newly discovered games
            # ----------------------------------------------------------------
            if self.igdb_client.is_configured():
                import concurrent.futures

                def _fetch_new_game_meta(item):
                    ghash, entry = item
                    details = self.igdb_client.fetch_game_details(
                        entry["title"], platform=entry.get("platform")
                    )
                    return ghash, entry, details

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {executor.submit(_fetch_new_game_meta, item): item for item in new_games}
                    for future in concurrent.futures.as_completed(futures):
                        try:
                            ghash, entry, details = future.result()
                        except Exception:
                            continue

                        if not details:
                            continue

                        meta_ref = self.config_manager.config["game_metadata"].get(ghash)
                        if not meta_ref:
                            continue

                        meta_ref["developer"] = details["developer"]
                        meta_ref["release_date"] = details["release_date"]
                        meta_ref["summary"] = details["summary"]
                        meta_ref["igdb_score"] = details.get("igdb_score")
                        meta_ref["igdb_rating_count"] = details.get("igdb_rating_count", 0)

                        cover_id = details.get("cover_image_id", "")
                        if cover_id:
                            meta_ref["cover_image_id"] = cover_id
                            cover_path = self.config_manager.covers_dir / f"{ghash}.jpg"
                            try:
                                self.igdb_client.download_cover(cover_id, cover_path)
                            except Exception:
                                pass

                        # Emit signal so banner and grid update on the UI thread
                        self.metadata_enriched.emit(ghash)

                self.igdb_client.flush_cache()
                self.config_manager.save_config()

        except Exception as e:
            print(f"Error in quick scan: {e}")

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

    def auto_detect_emulators(self):
        self.statusBar().showMessage("Scanning system for installed emulators...")
        
        # Common locations to search
        search_roots = [
            os.path.expandvars(r"%LOCALAPPDATA%"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
            os.path.expandvars(r"%PROGRAMFILES%"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%"),
            os.path.expanduser(r"~\Desktop"),
            os.path.expanduser(r"~\Downloads"),
            r"C:",
            r"D:",
            r"E:"
        ]
        
        # Prepend user custom emulator search paths
        custom_roots = self.config_manager.config.get("emulator_search_paths", [])
        for cr in custom_roots:
            if cr not in search_roots:
                search_roots.insert(0, cr)
        
        valid_roots = []
        for r in search_roots:
            if os.path.isdir(r) and r not in valid_roots:
                valid_roots.append(r)
                
        emu_defs = [
            {
                "name": "RPCS3",
                "exes": ["rpcs3.exe"],
                "systems": ["PlayStation 3"],
                "args": "",
                "subdirs": ["RPCS3"]
            },
            {
                "name": "Dolphin",
                "exes": ["Dolphin.exe"],
                "systems": ["GameCube", "Wii"],
                "args": "/e %ROM%",
                "subdirs": ["Dolphin", "Dolphin-x64", "Dolphin Emulator"]
            },
            {
                "name": "PCSX2",
                "exes": ["pcsx2.exe", "pcsx2-qtx64.exe", "pcsx2-x64.exe"],
                "systems": ["PlayStation 2"],
                "args": "%ROM%",
                "subdirs": ["PCSX2", "PCSX2 2.0"]
            },
            {
                "name": "RetroArch",
                "exes": ["retroarch.exe"],
                "systems": ["NES", "Super Nintendo", "Nintendo 64", "Game Boy", "Game Boy Color", "Game Boy Advance", "PlayStation"],
                "args": "%ROM%",
                "subdirs": ["RetroArch"]
            },
            {
                "name": "PPSSPP",
                "exes": ["PPSSPPWindows64.exe", "PPSSPPWindows.exe"],
                "systems": ["PSP"],
                "args": "%ROM%",
                "subdirs": ["PPSSPP", "PPSSPPWindows"]
            },
            {
                "name": "Citra",
                "exes": ["citra-qt.exe"],
                "systems": ["Nintendo 3DS"],
                "args": "%ROM%",
                "subdirs": ["Citra", "citra-emu", "local\\local-citra"]
            },
            {
                "name": "shadPS4",
                "exes": ["shadPS4.exe", "shadPS4QTLauncher.exe"],
                "systems": ["PlayStation 4"],
                "args": "",
                "subdirs": ["shadPS4", "shadps4", "shadps4-win64"]
            },
            {
                "name": "Ryujinx",
                "exes": ["Ryujinx.exe"],
                "systems": ["Nintendo Switch"],
                "args": "%ROM%",
                "subdirs": ["Ryujinx"]
            },
            {
                "name": "Yuzu",
                "exes": ["yuzu.exe"],
                "systems": ["Nintendo Switch"],
                "args": "%ROM%",
                "subdirs": ["yuzu", "yuzu-windows-msvc"]
            },
            {
                "name": "Cemu",
                "exes": ["Cemu.exe"],
                "systems": ["Wii U"],
                "args": "-g %ROM%",
                "subdirs": ["Cemu", "cemu"]
            },
            {
                "name": "Xenia",
                "exes": ["xenia.exe", "xenia_canary.exe"],
                "systems": ["Xbox 360"],
                "args": "%ROM%",
                "subdirs": ["Xenia", "xenia", "xenia-canary"]
            }
        ]
        
        detected_count = 0
        registered = {}
        
        # 1. Search PATH
        import shutil
        for emu in emu_defs:
            for exe_name in emu["exes"]:
                resolved_path = shutil.which(exe_name.replace(".exe", ""))
                if not resolved_path:
                    resolved_path = shutil.which(exe_name)
                if resolved_path and os.path.isfile(resolved_path) and resolved_path.lower().endswith(".exe"):
                    registered[emu["name"]] = {
                        "path": os.path.normpath(resolved_path),
                        "systems": emu["systems"],
                        "args": emu["args"]
                    }
                    break
                    
        # 2. Search common folders dynamically
        def search_dir_for_emus(search_dir, max_depth=2):
            dirs_to_check = [(Path(search_dir), 0)]
            while dirs_to_check:
                current_dir, depth = dirs_to_check.pop(0)
                try:
                    for emu in emu_defs:
                        if emu["name"] in registered:
                            continue
                        for exe_name in emu["exes"]:
                            p = current_dir / exe_name
                            if p.is_file():
                                registered[emu["name"]] = {
                                    "path": os.path.normpath(str(p)),
                                    "systems": emu["systems"],
                                    "args": emu["args"]
                                }
                                break
                    if depth < max_depth:
                        for entry in current_dir.iterdir():
                            if entry.is_dir() and not entry.name.startswith('$') and not entry.name.startswith('.'):
                                dirs_to_check.append((entry, depth + 1))
                except Exception:
                    pass

        # Determine which roots are custom user-provided ones
        custom_roots_set = set([os.path.normpath(cr) for cr in self.config_manager.config.get("emulator_search_paths", [])])
        
        for root in valid_roots:
            is_custom = os.path.normpath(root) in custom_roots_set
            if is_custom:
                # Deep scan for custom directories (e.g. user added D:\MyEmulators)
                search_dir_for_emus(root, max_depth=2)
            else:
                # Fast scan for system roots using known subdirs
                for emu in emu_defs:
                    if emu["name"] in registered:
                        continue
                    for subdir in emu["subdirs"]:
                        candidate = Path(root) / subdir
                        if candidate.is_dir():
                            search_dir_for_emus(candidate, max_depth=2)
                            
                # Also check root directly
                for emu in emu_defs:
                    if emu["name"] in registered:
                        continue
                    for exe_name in emu["exes"]:
                        p = Path(root) / exe_name
                        if p.is_file():
                            registered[emu["name"]] = {
                                "path": os.path.normpath(str(p)),
                                "systems": emu["systems"],
                                "args": emu["args"]
                            }
                            break
                        
        if registered:
            emulators_config = self.config_manager.config.setdefault("emulators", {})
            for name, emu_data in registered.items():
                if name not in emulators_config:
                    emulators_config[name] = emu_data
                    detected_count += 1
            if detected_count > 0:
                self.config_manager.save_config()
                self.update_emulators_tree()
                
        self.statusBar().showMessage(f"Scan complete. Registered {detected_count} emulators.", 4000)
        
        # Show results modal dialog
        msg = f"Auto-scan complete! Discovered and registered {detected_count} new emulators.\n\n"
        if detected_count > 0:
            msg += "Newly detected:\n"
            for name, data in registered.items():
                # only list if it was newly added during this scan
                if name in self.config_manager.config.get("emulators", {}):
                    msg += f"• {name} ({', '.join(data['systems'])})\n"
        else:
            msg += "No new emulators discovered. If they are already in the table, they won't be re-added."
            
        QMessageBox.information(self, "Emulator Auto-Scan", msg)

    def add_custom_emulator_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Custom Emulator")
        dialog.setMinimumWidth(480)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.C_BG_PANEL};
            }}
        """)
        
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        
        edit_name = QLineEdit()
        edit_name.setMinimumHeight(30)
        edit_name.setPlaceholderText("e.g. RPCS3, Dolphin, PCSX2")
        
        edit_exe = QLineEdit()
        edit_exe.setMinimumHeight(30)
        edit_exe.setPlaceholderText("Select executable file path or directory")
        
        btn_browse = QPushButton("Browse...")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def choose_exe():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Emulator Executable", "", "Executables (*.exe);;All Files (*)")
            if path:
                edit_exe.setText(os.path.normpath(path))
                if not edit_name.text().strip():
                    edit_name.setText(Path(path).stem.upper())
        btn_browse.clicked.connect(choose_exe)
        
        exe_lay = QHBoxLayout()
        exe_lay.addWidget(edit_exe)
        exe_lay.addWidget(btn_browse)
        
        edit_systems = QLineEdit()
        edit_systems.setMinimumHeight(30)
        edit_systems.setPlaceholderText("e.g. PlayStation 3, PlayStation 2, GameCube, Wii")
        
        edit_args = QLineEdit("%ROM%")
        edit_args.setMinimumHeight(30)
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
            
            if not name or not exe:
                QMessageBox.warning(self, "Invalid Input", "Emulator name and executable path are required.")
                return
                
            # Verify and resolve executable file path (in case directory is selected)
            resolved_exe = os.path.normpath(exe)
            if os.path.isdir(resolved_exe):
                # Search for executables inside the directory
                exes_found = []
                try:
                    for entry in Path(resolved_exe).iterdir():
                        if entry.is_file() and entry.suffix.lower() == '.exe':
                            exes_found.append(entry)
                    # Check 1 level deep
                    for sub in Path(resolved_exe).iterdir():
                        if sub.is_dir() and sub.name.lower() in ('bin', 'binaries', 'game', 'x64', 'win64', 'win32'):
                            for entry in sub.iterdir():
                                if entry.is_file() and entry.suffix.lower() == '.exe':
                                    exes_found.append(entry)
                except Exception:
                    pass
                    
                if exes_found:
                    exes_found.sort(key=lambda x: x.stat().st_size, reverse=True)
                    chosen = exes_found[0]
                    QMessageBox.information(
                        self, "Executable Selected",
                        f"You selected a directory instead of an executable file.\n\n"
                        f"Lair scanned the directory and selected the main emulator executable:\n"
                        f"• {chosen.name}"
                    )
                    resolved_exe = str(chosen)
                else:
                    QMessageBox.warning(
                        self, "No Executable Found",
                        "The selected directory does not contain any executable (.exe) files. Please select the emulator executable file directly."
                    )
                    return
            elif not os.path.isfile(resolved_exe) or not resolved_exe.lower().endswith(".exe"):
                QMessageBox.warning(
                    self, "Invalid File",
                    "The selected path is not a valid executable (.exe) file."
                )
                return
                
            self.config_manager.config.setdefault("emulators", {})[name] = {
                "path": resolved_exe,
                "systems": systems,
                "args": args
            }
            self.config_manager.save_config()
            self.update_emulators_tree()
            self.statusBar().showMessage(f"✅ Emulator '{name}' registered.", 4000)

    def edit_selected_emulator(self):
        item = self.emu_tree.currentItem()
        if not item:
            QMessageBox.information(self, "No Selection", "Select an emulator from the list to edit.")
            return
            
        old_name = item.text(0)
        emu_data = self.config_manager.config.get("emulators", {}).get(old_name)
        if not emu_data:
            return
            
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Emulator — {old_name}")
        dialog.setMinimumWidth(480)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.C_BG_PANEL};
            }}
        """)
        
        layout = QFormLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        
        edit_name = QLineEdit(old_name)
        edit_name.setMinimumHeight(30)
        
        edit_exe = QLineEdit(emu_data.get("path", ""))
        edit_exe.setMinimumHeight(30)
        btn_browse = QPushButton("Browse...")
        btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def choose_exe():
            path, _ = QFileDialog.getOpenFileName(dialog, "Select Emulator Executable", "", "Executables (*.exe);;All Files (*)")
            if path:
                edit_exe.setText(os.path.normpath(path))
        btn_browse.clicked.connect(choose_exe)
        
        exe_lay = QHBoxLayout()
        exe_lay.addWidget(edit_exe)
        exe_lay.addWidget(btn_browse)
        
        edit_systems = QLineEdit(", ".join(emu_data.get("systems", [])))
        edit_systems.setMinimumHeight(30)
        edit_systems.setPlaceholderText("e.g. PlayStation 3, PlayStation 2, GameCube, Wii")
        
        edit_args = QLineEdit(emu_data.get("args", "%ROM%"))
        edit_args.setMinimumHeight(30)
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
            new_name = edit_name.text().strip()
            exe = edit_exe.text().strip()
            systems = [s.strip() for s in edit_systems.text().split(",") if s.strip()]
            args = edit_args.text().strip()
            
            if not new_name or not exe:
                QMessageBox.warning(self, "Invalid Input", "Emulator name and executable path are required.")
                return
                
            # Verify and resolve executable file path
            resolved_exe = os.path.normpath(exe)
            if os.path.isdir(resolved_exe):
                exes_found = []
                try:
                    for entry in Path(resolved_exe).iterdir():
                        if entry.is_file() and entry.suffix.lower() == '.exe':
                            exes_found.append(entry)
                    for sub in Path(resolved_exe).iterdir():
                        if sub.is_dir() and sub.name.lower() in ('bin', 'binaries', 'game', 'x64', 'win64', 'win32'):
                            for entry in sub.iterdir():
                                if entry.is_file() and entry.suffix.lower() == '.exe':
                                    exes_found.append(entry)
                except Exception:
                    pass
                    
                if exes_found:
                    exes_found.sort(key=lambda x: x.stat().st_size, reverse=True)
                    chosen = exes_found[0]
                    QMessageBox.information(
                        self, "Executable Selected",
                        f"You selected a directory instead of an executable file.\n\n"
                        f"Lair scanned the directory and selected the main emulator executable:\n"
                        f"• {chosen.name}"
                    )
                    resolved_exe = str(chosen)
                else:
                    QMessageBox.warning(
                        self, "No Executable Found",
                        "The selected directory does not contain any executable (.exe) files. Please select the emulator executable file directly."
                    )
                    return
            elif not os.path.isfile(resolved_exe) or not resolved_exe.lower().endswith(".exe"):
                QMessageBox.warning(
                    self, "Invalid File",
                    "The selected path is not a valid executable (.exe) file."
                )
                return
            
            emus = self.config_manager.config.setdefault("emulators", {})
            
            if new_name != old_name:
                emus.pop(old_name, None)
                for plat, def_name in self.config_manager.config.get("platform_defaults", {}).items():
                    if def_name == old_name:
                        self.config_manager.config["platform_defaults"][plat] = new_name
            
            emus[new_name] = {
                "path": resolved_exe,
                "systems": systems,
                "args": args
            }
            self.config_manager.save_config()
            self.update_emulators_tree()
            self.statusBar().showMessage(f"✅ Emulator '{new_name}' updated.", 4000)

    def run_selected_emulator(self):
        item = self.emu_tree.currentItem()
        if not item:
            return
            
        emu_name = item.text(0)
        emu_config = self.config_manager.config.get("emulators", {}).get(emu_name)
        if emu_config and "path" in emu_config:
            emu_path = emu_config["path"]
            if os.path.exists(emu_path):
                import subprocess
                try:
                    subprocess.Popen([emu_path], cwd=os.path.dirname(emu_path))
                except Exception as e:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Error", f"Failed to run emulator:\n{e}")
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Found", f"Emulator executable not found at:\n{emu_path}")

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

    def add_emulator_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Add Emulator Search Folder")
        if dir_path:
            dir_path = os.path.normpath(dir_path)
            paths = self.config_manager.config.setdefault("emulator_search_paths", [])
            if dir_path not in paths:
                paths.append(dir_path)
                self.config_manager.save_config()
                self.emu_folders_list.addItem(dir_path)
                self.auto_detect_emulators()

    def remove_emulator_folder(self):
        item = self.emu_folders_list.currentItem()
        if not item:
            return
        path = item.text()
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove folder from emulator search list?\n\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.config.setdefault("emulator_search_paths", []).remove(path)
            self.config_manager.save_config()
            self.emu_folders_list.takeItem(self.emu_folders_list.row(item))

    def save_settings(self):
        self.config_manager.config["igdb_client_id"] = self.edit_client_id.text().strip()
        self.config_manager.config["igdb_client_secret"] = self.edit_client_secret.text().strip()
        self.config_manager.save_config()
        
        self.igdb_client = IGDBClient(
            self.config_manager.config["igdb_client_id"],
            self.config_manager.config["igdb_client_secret"],
            self.config_manager
        )



# =============================================================================
# --- MAIN APPLICATION BLOCK ---
# =============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Allow minimizing to tray without quitting
    app.setFont(QFont("Segoe UI", 9))
    
    config_obj = ConfigManager()
    window = EmulatorHubWindow(config_obj)
    window.show()
    sys.exit(app.exec())