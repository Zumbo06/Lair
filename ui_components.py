# ui_components.py

import time
import hashlib
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QPushButton,
    QTextEdit, QDialog, QFrame, QScrollArea, QProgressBar, QGroupBox,
    QStyledItemDelegate, QStyle
)
from PyQt6.QtGui import (
    QFont, QIcon, QPixmap, QColor, QBrush, QPen, QPainter, QPainterPath,
    QLinearGradient
)
from PyQt6.QtCore import Qt, QSize, QRect, QRectF, pyqtSignal

from constants import Constants
from config import ConfigManager

# =============================================================================
# --- PREMIUM FULL-BLEED GAME CARD DELEGATE ---
# =============================================================================
class GridItemDelegate(QStyledItemDelegate):
    """Breathtaking full-bleed vertical game card with hover zoom, glowing borders, and playtime overlays"""
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        
    def sizeHint(self, option, index):
        width = self.config_manager.config.get("grid_icon_size", Constants.DEFAULT_GRID_WIDTH)
        height = int(width * 1.45) # Taller cinematic aspect ratio
        return QSize(width, height)
        
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        game_data = index.data(Qt.ItemDataRole.UserRole)
        if not game_data:
            painter.restore()
            return
            
        game_hash = game_data['hash']
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver
        is_selected = option.state & QStyle.StateFlag.State_Selected
        
        # 1. Base boundaries & Physical lift on hover
        if is_hovered:
            card_rect = rect.adjusted(4, 1, -4, -7) # Shifted up by 4px
        else:
            card_rect = rect.adjusted(4, 5, -4, -3)
        
        # Clip path for round corners of the entire card
        clip_path = QPainterPath()
        clip_path.addRoundedRect(QRectF(card_rect), 12, 12)
        
        # 2. Draw Glow / Shadow beneath the card (Multi-layered neon bloom)
        if is_selected:
            # Draw beautiful cyan neon glow layers
            for i in range(4):
                alpha = 40 - i * 10
                pen_color = QColor(Constants.C_ACCENT_CYAN)
                pen_color.setAlpha(alpha)
                painter.setPen(QPen(pen_color, 1.5 + i * 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(card_rect.adjusted(-i, -i, i, i), 12, 12)
            
            painter.setPen(QPen(QColor(Constants.C_ACCENT_CYAN), 2))
            painter.setBrush(QColor(Constants.C_BG_PANEL))
            painter.drawRoundedRect(card_rect, 12, 12)
        elif is_hovered:
            # Draw beautiful violet neon glow layers
            for i in range(3):
                alpha = 30 - i * 10
                pen_color = QColor(Constants.C_ACCENT_VIOLET)
                pen_color.setAlpha(alpha)
                painter.setPen(QPen(pen_color, 1.0 + i * 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(card_rect.adjusted(-i, -i, i, i), 12, 12)
                
            painter.setPen(QPen(QColor(Constants.C_ACCENT_VIOLET), 1.5))
            painter.setBrush(QColor("#15161c"))
            painter.drawRoundedRect(card_rect, 12, 12)
        else:
            painter.setPen(QPen(QColor(Constants.C_BORDER), 1))
            painter.setBrush(QColor(Constants.C_BG_PANEL))
            painter.drawRoundedRect(card_rect, 12, 12)

        # 3. Draw Full-Bleed Cover Image
        cover_icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(cover_icon, QIcon):
            pixmap = cover_icon.pixmap(card_rect.size())
            
            # Clip drawing to card rounded corners
            painter.save()
            painter.setClipPath(clip_path)
            
            if is_hovered:
                # Cinematic Zoom effect on hover
                scale_w = int(card_rect.width() * 1.08)
                scale_h = int(card_rect.height() * 1.08)
                dx = (scale_w - card_rect.width()) // 2
                dy = (scale_h - card_rect.height()) // 2
                scaled_pixmap = pixmap.scaled(scale_w, scale_h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(card_rect.adjusted(-dx, -dy, dx, dy), scaled_pixmap)
            else:
                painter.drawPixmap(card_rect, pixmap)
                
            painter.restore()
            
        # 4. Draw Dark Gradient overlay at bottom to read titles clearly
        overlay_height = 60
        overlay_rect = QRect(card_rect.left(), card_rect.bottom() - overlay_height, card_rect.width(), overlay_height)
        
        painter.save()
        painter.setClipPath(clip_path)
        
        grad = QLinearGradient(0, overlay_rect.top(), 0, overlay_rect.bottom())
        grad.setColorAt(0, QColor(13, 14, 18, 0))       # Transparent top
        grad.setColorAt(0.3, QColor(13, 14, 18, 120))   # Soft semi-transparent
        grad.setColorAt(0.7, QColor(13, 14, 18, 200))   # Medium obsidian
        grad.setColorAt(1, QColor(13, 14, 18, 255))     # Deep solid obsidian at bottom
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(overlay_rect)
        painter.restore()

        # 5. Draw Game Title on top of Gradient overlay
        title_rect = QRect(card_rect.left() + 8, card_rect.bottom() - 26, card_rect.width() - 16, 20)
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        
        if is_selected:
            painter.setPen(QColor(Constants.C_ACCENT_CYAN))
        elif is_hovered:
            painter.setPen(QColor("#ffffff"))
        else:
            painter.setPen(QColor(Constants.C_TEXT_PRIMARY))
            
        elided_title = painter.fontMetrics().elidedText(game_data.get("title", ""), Qt.TextElideMode.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_title)

        # 6. Playtime Badge Overlay (Top Left - Glassmorphic Pill)
        playtime = game_data.get('playtime', 0)
        hours = playtime / 3600.0
        
        if hours > 0:
            pill_text = f"⏱ {hours:.1f}h"
            pill_color = QColor(140, 82, 255, 200) # Glowing Violet Glass
            pill_border = QColor(161, 117, 255, 230)
            text_color = QColor("#ffffff")
        else:
            pill_text = "NEW"
            pill_color = QColor(22, 23, 30, 180) # Sleek Dark Glass
            pill_border = QColor(Constants.C_BORDER)
            text_color = QColor(Constants.C_TEXT_SECONDARY)
            
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        text_width = painter.fontMetrics().boundingRect(pill_text).width() + 12
        pill_rect = QRect(card_rect.left() + 6, card_rect.top() + 6, text_width, 16)
        
        painter.save()
        painter.setBrush(pill_color)
        painter.setPen(QPen(pill_border, 1))
        painter.drawRoundedRect(pill_rect, 4, 4)
        
        painter.setPen(text_color)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, pill_text)
        painter.restore()

        # 7. Favorite Bookmark Overlay (Top Right - Hanging Ribbon)
        favorites = self.config_manager.config.get("favorites", [])
        if game_hash in favorites:
            bookmark_rect = QRect(card_rect.right() - 22, card_rect.top(), 16, 22)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(Constants.C_WARNING)) # Golden ribbon
            
            bookmark_path = QPainterPath()
            bookmark_path.moveTo(bookmark_rect.left(), bookmark_rect.top())
            bookmark_path.lineTo(bookmark_rect.right(), bookmark_rect.top())
            bookmark_path.lineTo(bookmark_rect.right(), bookmark_rect.bottom())
            bookmark_path.lineTo(bookmark_rect.left() + 8, bookmark_rect.bottom() - 5)
            bookmark_path.lineTo(bookmark_rect.left(), bookmark_rect.bottom())
            bookmark_path.closeSubpath()
            painter.drawPath(bookmark_path)
            
            # Tiny star symbol inside the bookmark ribbon
            painter.setPen(QColor("#000000"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(bookmark_rect.adjusted(0, 0, 0, -3), Qt.AlignmentFlag.AlignCenter, "★")
            painter.restore()
            
        # 8. Platform Floating Badge (Bottom Right, above title)
        platform_mapping = {
            "PlayStation 3": "PS3",
            "PlayStation 2": "PS2",
            "PlayStation": "PS1",
            "GameCube": "GCN",
            "Wii": "WII",
            "Nintendo Switch": "SW",
            "Game Boy Advance": "GBA",
            "Game Boy Color": "GBC",
            "Game Boy": "GB",
            "Nintendo DS": "NDS",
            "Nintendo 3DS": "3DS",
            "NES": "NES",
            "Super Nintendo": "SNES",
            "Nintendo 64": "N64",
            "PSP": "PSP",
            "PC": "PC"
        }
        platform_name = game_data.get("platform", "ROM")
        short_platform = platform_mapping.get(platform_name, platform_name[:4].upper())
        
        plat_rect = QRect(card_rect.right() - 44, card_rect.bottom() - 44, 38, 14)
        
        painter.save()
        painter.setPen(QPen(QColor(Constants.C_BORDER), 1))
        painter.setBrush(QColor(13, 14, 18, 200))
        painter.drawRoundedRect(plat_rect, 3, 3)
        
        painter.setPen(QColor(Constants.C_ACCENT_CYAN))
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.drawText(plat_rect, Qt.AlignmentFlag.AlignCenter, short_platform)
        painter.restore()
        
        painter.restore()

class SpacedListItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 48)
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        game_data = index.data(Qt.ItemDataRole.UserRole)
        if not game_data:
            painter.restore()
            return
            
        is_hovered = option.state & QStyle.StateFlag.State_MouseOver
        is_selected = option.state & QStyle.StateFlag.State_Selected
        
        if is_selected:
            painter.setBrush(QColor(Constants.C_BORDER))
            painter.setPen(QPen(QColor(Constants.C_ACCENT_CYAN), 1))
        elif is_hovered:
            painter.setBrush(QColor("#1e1f29"))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(QColor(Constants.C_BG_PANEL))
            painter.setPen(Qt.PenStyle.NoPen)
            
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
        
        # Cover thumbnail
        cover_icon = index.data(Qt.ItemDataRole.DecorationRole)
        thumb_rect = QRect(rect.left() + 8, rect.top() + 6, 26, 36)
        if isinstance(cover_icon, QIcon):
            painter.drawPixmap(thumb_rect, cover_icon.pixmap(thumb_rect.size()))
            
        # Title
        title_rect = QRect(thumb_rect.right() + 12, rect.top(), rect.width() - 250, rect.height())
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor(Constants.C_TEXT_PRIMARY))
        elided_title = painter.fontMetrics().elidedText(game_data.get("title", ""), Qt.TextElideMode.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_title)
        
        # Platform Pill badge in List View
        platform_mapping = {
            "PlayStation 3": "PS3",
            "PlayStation 2": "PS2",
            "PlayStation": "PS1",
            "GameCube": "GCN",
            "Wii": "WII",
            "Nintendo Switch": "SW",
            "Game Boy Advance": "GBA",
            "Game Boy Color": "GBC",
            "Game Boy": "GB",
            "Nintendo DS": "NDS",
            "Nintendo 3DS": "3DS",
            "NES": "NES",
            "Super Nintendo": "SNES",
            "Nintendo 64": "N64",
            "PSP": "PSP",
            "PC": "PC"
        }
        platform_text = game_data.get("platform", "N/A")
        short_platform = platform_mapping.get(platform_text, platform_text[:4].upper())
        
        platform_rect = QRect(rect.right() - 230, rect.top() + 14, 52, 20)
        
        painter.save()
        painter.setPen(QPen(QColor(Constants.C_BORDER), 1))
        painter.setBrush(QColor(13, 14, 18, 180))
        painter.drawRoundedRect(platform_rect, 4, 4)
        
        painter.setPen(QColor(Constants.C_ACCENT_CYAN))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(platform_rect, Qt.AlignmentFlag.AlignCenter, short_platform)
        painter.restore()
        
        # Playtime
        playtime_rect = QRect(rect.right() - 150, rect.top(), 130, rect.height())
        hours = game_data.get("playtime", 0) / 3600.0
        playtime_text = "Never Played" if hours == 0 else f"{hours:.1f} hours"
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold if hours > 0 else QFont.Weight.Normal))
        painter.setPen(QColor(Constants.C_SUCCESS if hours > 0 else Constants.C_TEXT_MUTED))
        painter.drawText(playtime_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, playtime_text)
        
        painter.restore()

# =============================================================================
# --- BRIEF INFO MODAL ---
# =============================================================================
class GameBriefInfoModal(QDialog):
    def __init__(self, game_data, cover_pixmap, parent=None):
        super().__init__(parent)
        self.game_data = game_data
        self.setWindowTitle(f"Brief Info - {game_data.get('title')}")
        self.setMinimumSize(560, 360)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.C_BG_DARK};
                color: {Constants.C_TEXT_PRIMARY};
                border: 2px solid {Constants.C_BORDER};
                border-radius: 8px;
            }}
            QLabel {{
                color: {Constants.C_TEXT_PRIMARY};
            }}
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)
        
        # Left side: Poster
        poster_label = QLabel()
        poster_label.setFixedSize(180, 260)
        poster_label.setScaledContents(True)
        if cover_pixmap and not cover_pixmap.isNull():
            poster_label.setPixmap(cover_pixmap.scaled(180, 260, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            poster_label.setStyleSheet(f"background-color: {Constants.C_BG_PANEL}; border: 1px solid {Constants.C_BORDER}; border-radius: 4px;")
            poster_label.setText("No Cover")
            poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(poster_label)
        
        # Right side: Details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title_label = QLabel(game_data.get("title"))
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setWordWrap(True)
        details_layout.addWidget(title_label)
        
        # Developer & Release Date
        dev = game_data.get("developer", "Unknown Developer")
        rel = game_data.get("release_date", "N/A")
        sub_info = QLabel(f"Developer: <b style='color:{Constants.C_ACCENT_CYAN};'>{dev}</b><br>Released: <b>{rel}</b>")
        sub_info.setFont(QFont("Segoe UI", 9))
        sub_info.setTextFormat(Qt.TextFormat.RichText)
        details_layout.addWidget(sub_info)
        
        # Platform
        plat = game_data.get("platform", "N/A")
        platform_info = QLabel(f"Platform: <b>{plat}</b>")
        platform_info.setFont(QFont("Segoe UI", 10))
        details_layout.addWidget(platform_info)
        
        # Clickable File / Installation path location
        raw_path = game_data.get("path", "")
        if raw_path:
            path_widget = QWidget()
            path_layout = QHBoxLayout(path_widget)
            path_layout.setContentsMargins(0, 0, 0, 0)
            path_layout.setSpacing(4)
            
            path_title = QLabel("Location:")
            path_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            path_title.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
            path_layout.addWidget(path_title)
            
            # Shorten the path for clean look
            display_path = raw_path
            if len(raw_path) > 40:
                display_path = "..." + raw_path[-37:]
                
            path_btn = QPushButton(display_path)
            path_btn.setFlat(True)
            path_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            path_btn.setToolTip(raw_path)
            path_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Constants.C_ACCENT_CYAN};
                    text-align: left;
                    padding: 0px;
                    border: none;
                    background-color: transparent;
                    text-decoration: underline;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    color: #ffffff;
                }}
            """)
            
            def open_and_select_file():
                import subprocess
                import os
                if os.path.exists(raw_path):
                    subprocess.Popen(f'explorer /select,"{os.path.normpath(raw_path)}"')
                else:
                    game_dir = game_data.get("game_dir", "")
                    if game_dir and os.path.exists(game_dir):
                        os.startfile(game_dir)
                    else:
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "Unavailable", f"File path does not exist:\n{raw_path}")
                        
            path_btn.clicked.connect(open_and_select_file)
            path_layout.addWidget(path_btn, 1)
            details_layout.addWidget(path_widget)
        
        # Playtime hours
        hours = game_data.get("playtime", 0) / 3600.0
        time_text = "Never Played" if hours == 0 else f"{hours:.1f} hours played"
        playtime_label = QLabel(time_text)
        playtime_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        playtime_label.setStyleSheet(f"color: {Constants.C_SUCCESS if hours > 0 else Constants.C_TEXT_MUTED};")
        details_layout.addWidget(playtime_label)
        
        details_layout.addSpacing(10)
        
        # Summary/Description
        summary_title = QLabel("Description:")
        summary_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        summary_title.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        details_layout.addWidget(summary_title)
        
        summary_box = QTextEdit()
        summary_box.setReadOnly(True)
        summary_box.setPlainText(game_data.get("summary", "No details fetched yet. Enter your IGDB API keys in settings to automatically fetch metadata!"))
        summary_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 4px;
                color: {Constants.C_TEXT_SECONDARY};
                padding: 6px;
            }}
        """)
        details_layout.addWidget(summary_box)
        
        # Dialog Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        play_btn = QPushButton("▶ PLAY")
        play_btn.setMinimumHeight(32)
        play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_ACCENT_VIOLET};
                color: #ffffff;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 20px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_VIOLET_HOVER};
            }}
        """)
        play_btn.clicked.connect(self.accept)
        button_layout.addWidget(play_btn)
        
        close_btn = QPushButton("Close")
        close_btn.setMinimumHeight(32)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_PRIMARY};
                border-radius: 4px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_BORDER};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)
        
        details_layout.addLayout(button_layout)
        main_layout.addWidget(details_widget, 1)

# =============================================================================
# --- PREMIUM GAME HEADER BANNER ---
# =============================================================================
class SteamGameBanner(QWidget):
    play_clicked = pyqtSignal()
    info_clicked = pyqtSignal()
    favorite_toggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(180)
        self.game_data = None
        self.setup_ui()

    def setup_ui(self):
        # Translucent Banner layout with absolute background
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)
        
        # Banner cover thumbnail
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(90, 130)
        self.cover_label.setScaledContents(True)
        self.cover_label.setStyleSheet(f"border: 1px solid {Constants.C_BORDER}; border-radius: 4px; background-color: {Constants.C_BG_DARK};")
        self.layout.addWidget(self.cover_label)
        
        # Details layout
        self.info_layout = QVBoxLayout()
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel("Select a game to start")
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #ffffff;")
        self.info_layout.addWidget(self.title_label)
        
        self.meta_label = QLabel("")
        self.meta_label.setFont(QFont("Segoe UI", 10))
        self.meta_label.setStyleSheet(f"color: {Constants.C_TEXT_SECONDARY};")
        self.info_layout.addWidget(self.meta_label)
        
        self.playtime_label = QLabel("")
        self.playtime_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.playtime_label.setStyleSheet(f"color: {Constants.C_SUCCESS};")
        self.info_layout.addWidget(self.playtime_label)
        
        self.info_layout.addStretch()
        self.layout.addLayout(self.info_layout, 1)
        
        # Action Buttons Layout
        self.actions_layout = QVBoxLayout()
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        
        # Modern Violet Play Button
        self.play_btn = QPushButton("▶ PLAY")
        self.play_btn.setFixedSize(140, 48)
        self.play_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_ACCENT_VIOLET};
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_VIOLET_HOVER};
            }}
            QPushButton:disabled {{
                background-color: #232530;
                color: #5d6275;
            }}
        """)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        self.play_btn.setEnabled(False)
        self.actions_layout.addWidget(self.play_btn)
        
        # Secondary buttons layout
        self.secondary_layout = QHBoxLayout()
        
        self.fav_btn = QPushButton("★")
        self.fav_btn.setFixedSize(40, 32)
        self.fav_btn.setFont(QFont("Segoe UI", 12))
        self.fav_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_MUTED};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_BORDER};
                color: #ffffff;
            }}
        """)
        self.fav_btn.clicked.connect(self.favorite_toggled.emit)
        self.secondary_layout.addWidget(self.fav_btn)
        
        self.info_btn = QPushButton("Info")
        self.info_btn.setFixedSize(92, 32)
        self.info_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.info_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_PRIMARY};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_BORDER};
            }}
        """)
        self.info_btn.clicked.connect(self.info_clicked.emit)
        self.secondary_layout.addWidget(self.info_btn)
        
        self.actions_layout.addLayout(self.secondary_layout)
        self.layout.addLayout(self.actions_layout)

    def paintEvent(self, event):
        # Draw gorgeous background gradient banner
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor("#2b1b54")) # Velvet deep glow
        gradient.setColorAt(0.5, QColor("#14151a")) # Deep obsidian
        gradient.setColorAt(1, QColor(Constants.C_BG_DARK))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        
        # Subtle separator line at bottom
        painter.setPen(QPen(QColor(Constants.C_BORDER), 1.5))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

    def set_game(self, game_data, cover_pixmap, is_fav):
        self.game_data = game_data
        if not game_data:
            self.title_label.setText("Select a game to start")
            self.meta_label.setText("")
            self.playtime_label.setText("")
            self.play_btn.setEnabled(False)
            self.cover_label.setPixmap(QPixmap())
            self.fav_btn.setStyleSheet(f"color: #8f98a0; background-color: {Constants.C_BG_PANEL};")
            return
            
        self.title_label.setText(game_data.get("title"))
        
        dev = game_data.get("developer", "Unknown Developer")
        rel = game_data.get("release_date", "N/A")
        self.meta_label.setText(f"{game_data.get('platform')}  |  Developer: {dev}  |  Released: {rel}")
        
        hours = game_data.get("playtime", 0) / 3600.0
        self.playtime_label.setText("Never Played" if hours == 0 else f"{hours:.1f} hours played")
        
        if cover_pixmap and not cover_pixmap.isNull():
            self.cover_label.setPixmap(cover_pixmap.scaled(self.cover_label.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover_label.setText("No Cover")
            
        self.play_btn.setEnabled(True)
        
        if is_fav:
            self.fav_btn.setStyleSheet(f"color: {Constants.C_WARNING}; background-color: {Constants.C_BORDER}; border: 1.5px solid {Constants.C_WARNING};")
        else:
            self.fav_btn.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; background-color: {Constants.C_BG_PANEL}; border: 1.5px solid {Constants.C_BORDER};")

# =============================================================================
# --- DETAILED STATISTICS DASHBOARD (WEEK, MONTH, YEAR BREAKDOWNS) ---
# =============================================================================
class StatsDashboard(QWidget):
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()

    def setup_ui(self):
        # Main layout is scrollable
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        scroll.verticalScrollBar().setSingleStep(32)
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(24, 24, 24, 24)
        self.content_layout.setSpacing(20)
        
        # 1. Summary Cards Header
        self.cards_grid = QGridLayout()
        self.content_layout.addLayout(self.cards_grid)
        
        # 2. Detailed statistics sections
        self.content_layout.addWidget(QLabel("YOUR PLAYTIME BREAKDOWN"))
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def refresh_stats(self, all_games):
        # Clear cards grid
        for i in reversed(range(self.cards_grid.count())):
            self.cards_grid.itemAt(i).widget().setParent(None)
            
        # Re-calc stats
        total_games = len(all_games)
        total_playtime_s = sum(g.get("playtime", 0) for g in all_games)
        total_playtime_h = total_playtime_s / 3600.0
        
        # Calculate favorite system
        system_stats = {}
        for g in all_games:
            plat = g.get("platform", "Unknown")
            system_stats[plat] = system_stats.get(plat, 0) + g.get("playtime", 0)
            
        favorite_system = "None"
        if system_stats:
            favorite_system = max(system_stats, key=system_stats.get)
            if system_stats[favorite_system] == 0:
                favorite_system = list(system_stats.keys())[0]

        # Populate Overview Cards
        self.add_summary_card("TOTAL GAMES", str(total_games), "📁", 0, 0)
        self.add_summary_card("TOTAL HOURS PLAYED", f"{total_playtime_h:.1f} hrs", "⏱", 0, 1)
        self.add_summary_card("FAVORITE PLATFORM", favorite_system, "🎮", 0, 2)
        
        # Remove old stat boxes
        for child in list(self.children()):
            if isinstance(child, QGroupBox):
                child.setParent(None)
                
        # Calculate playtimes for periods
        # Session struct: {"timestamp": float, "duration": float}
        now = time.time()
        week_ago = now - (7 * 86400)
        month_ago = now - (30 * 86400)
        year_ago = now - (365 * 86400)
        
        week_stats = {}
        month_stats = {}
        year_stats = {}
        
        for g in all_games:
            metadata = self.config_manager.config.get("game_metadata", {}).get(g["hash"], {})
            sessions = metadata.get("sessions", [])
            for session in sessions:
                ts = session.get("timestamp", 0)
                dur = session.get("duration", 0)
                
                if ts >= week_ago:
                    week_stats[g["title"]] = week_stats.get(g["title"], 0.0) + dur
                if ts >= month_ago:
                    month_stats[g["title"]] = month_stats.get(g["title"], 0.0) + dur
                if ts >= year_ago:
                    year_stats[g["title"]] = year_stats.get(g["title"], 0.0) + dur
                    
        # Add Breakdown Panels
        self.add_ranking_panel("MOST PLAYED THIS WEEK (LAST 7 DAYS)", week_stats)
        self.add_ranking_panel("MOST PLAYED THIS MONTH (LAST 30 DAYS)", month_stats)
        self.add_ranking_panel("MOST PLAYED THIS YEAR (LAST 365 DAYS)", year_stats)

    def add_summary_card(self, title, value, icon, row, col):
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setObjectName("summaryCard")
        card.setStyleSheet(f"""
            QFrame#summaryCard {{
                background-color: {Constants.C_BG_PANEL};
                border: 2px solid {Constants.C_BORDER};
                border-radius: 8px;
                padding: 16px;
            }}
        """)
        layout = QHBoxLayout(card)
        
        text_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        
        val_label = QLabel(value)
        val_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        val_label.setStyleSheet("color: #ffffff;")
        
        text_layout.addWidget(title_label)
        text_layout.addWidget(val_label)
        
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 26))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN};")
        
        layout.addLayout(text_layout, 1)
        layout.addWidget(icon_label)
        
        self.cards_grid.addWidget(card, row, col)

    def add_ranking_panel(self, title, dataset):
        box = QGroupBox(title)
        box.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        box.setStyleSheet(f"""
            QGroupBox {{
                background-color: {Constants.C_BG_PANEL};
                border: 2px solid {Constants.C_BORDER};
                border-radius: 8px;
                margin-top: 16px;
                padding-top: 20px;
                padding-bottom: 12px;
            }}
            QGroupBox::title {{
                color: {Constants.C_ACCENT_CYAN};
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 2px 8px;
            }}
        """)
        
        layout = QVBoxLayout(box)
        layout.setSpacing(12)
        
        # Sort and select top 5 games
        sorted_ranks = sorted(dataset.items(), key=lambda x: x[1], reverse=True)[:5]
        
        if not sorted_ranks:
            no_data = QLabel("No games played during this period yet.")
            no_data.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            no_data.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; padding: 10px;")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_data)
        else:
            max_duration = sorted_ranks[0][1]
            for idx, (game_title, duration) in enumerate(sorted_ranks):
                hours = duration / 3600.0
                
                game_row = QHBoxLayout()
                
                lbl_rank = QLabel(f"#{idx+1}")
                lbl_rank.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                lbl_rank.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN};")
                lbl_rank.setFixedWidth(28)
                game_row.addWidget(lbl_rank)
                
                lbl_title = QLabel(game_title)
                lbl_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                lbl_title.setWordWrap(True)
                game_row.addWidget(lbl_title, 1)
                
                # Visual Hours bar (Velvet Violet chunk)
                bar = QProgressBar()
                bar.setTextVisible(False)
                bar.setFixedHeight(8)
                bar.setRange(0, 100)
                bar.setValue(int((duration / max_duration) * 100))
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: {Constants.C_BG_DARK};
                        border: none;
                        border-radius: 4px;
                    }}
                    QProgressBar::chunk {{
                        background-color: {Constants.C_ACCENT_VIOLET};
                        border-radius: 4px;
                    }}
                """)
                bar.setFixedWidth(160)
                game_row.addWidget(bar)
                
                lbl_hours = QLabel(f"{hours:.1f} hrs")
                lbl_hours.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                lbl_hours.setStyleSheet(f"color: {Constants.C_SUCCESS};")
                lbl_hours.setFixedWidth(50)
                lbl_hours.setAlignment(Qt.AlignmentFlag.AlignRight)
                game_row.addWidget(lbl_hours)
                
                layout.addLayout(game_row)
                
        self.content_layout.addWidget(box)
