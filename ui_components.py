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
            "PlayStation 4": "PS4",
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
            "PlayStation 4": "PS4",
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
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        
        self.game_data = game_data
        self.setWindowTitle(f"Info - {game_data.get('title')}")
        self.setMinimumSize(680, 420)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.C_BG_DARK};
                color: {Constants.C_TEXT_PRIMARY};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 12px;
            }}
            QLabel {{ color: {Constants.C_TEXT_PRIMARY}; }}
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(24)
        
        # Left side: Poster with Drop Shadow
        poster_container = QWidget()
        poster_container.setFixedSize(220, 310)
        poster_layout = QVBoxLayout(poster_container)
        poster_layout.setContentsMargins(0, 0, 0, 0)
        
        poster_label = QLabel()
        poster_label.setFixedSize(220, 310)
        poster_label.setScaledContents(True)
        if cover_pixmap and not cover_pixmap.isNull():
            # Add rounded corners to the pixmap
            rounded = QPixmap(cover_pixmap.size())
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(rounded.rect()), 12, 12)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, cover_pixmap)
            painter.end()
            poster_label.setPixmap(rounded.scaled(220, 310, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        else:
            poster_label.setStyleSheet(f"background-color: {Constants.C_BG_PANEL}; border: 1px solid {Constants.C_BORDER}; border-radius: 12px;")
            poster_label.setText("No Cover")
            poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 8)
        poster_label.setGraphicsEffect(shadow)
        
        poster_layout.addWidget(poster_label)
        main_layout.addWidget(poster_container)
        
        # Right side: Details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(12)
        
        # Title
        title_label = QLabel(game_data.get("title"))
        title_label.setFont(QFont("Segoe UI", 22, QFont.Weight.ExtraBold))
        title_label.setWordWrap(True)
        details_layout.addWidget(title_label)
        
        # Badges Layout (Platform, Dev, Year)
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(8)
        
        plat = game_data.get("platform", "N/A")
        rel = game_data.get("release_date", "N/A")
        dev = game_data.get("developer", "Unknown Developer")
        
        def create_badge(text, color):
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl.setStyleSheet(f"background-color: {color}; color: #ffffff; padding: 4px 10px; border-radius: 10px;")
            return lbl
            
        badges_layout.addWidget(create_badge(plat, Constants.C_ACCENT_CYAN))
        if rel != "N/A":
            year = rel.split("-")[0] if "-" in rel else rel
            badges_layout.addWidget(create_badge(year, "#34495e"))
        
        badges_layout.addStretch()
        details_layout.addLayout(badges_layout)
        
        dev_label = QLabel(f"Developed by <b style='color:{Constants.C_TEXT_PRIMARY};'>{dev}</b>")
        dev_label.setFont(QFont("Segoe UI", 10))
        dev_label.setStyleSheet(f"color: {Constants.C_TEXT_SECONDARY};")
        details_layout.addWidget(dev_label)
        
        # Clickable File / Installation path location
        raw_path = game_data.get("path", "")
        if raw_path:
            path_layout = QHBoxLayout()
            path_layout.setContentsMargins(0, 0, 0, 0)
            path_layout.setSpacing(6)
            
            # Shorten the path for clean look
            display_path = raw_path
            if len(raw_path) > 45:
                display_path = "..." + raw_path[-42:]
                
            path_icon = QLabel("📁")
            path_icon.setFont(QFont("Segoe UI", 10))
            path_layout.addWidget(path_icon)
            
            path_btn = QPushButton(display_path)
            path_btn.setFlat(True)
            path_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            path_btn.setToolTip(raw_path)
            path_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Constants.C_TEXT_MUTED};
                    text-align: left;
                    padding: 0px;
                    border: none;
                    background-color: transparent;
                    text-decoration: underline;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    color: {Constants.C_ACCENT_CYAN};
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
            path_layout.addWidget(path_btn)
            path_layout.addStretch()
            details_layout.addLayout(path_layout)
        
        # Playtime hours
        hours = game_data.get("playtime", 0) / 3600.0
        time_text = "⏱ Never Played" if hours == 0 else f"⏱ {hours:.1f} hours on record"
        playtime_label = QLabel(time_text)
        playtime_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        playtime_label.setStyleSheet(f"color: {Constants.C_SUCCESS if hours > 0 else Constants.C_TEXT_MUTED};")
        details_layout.addWidget(playtime_label)
        
        # Summary/Description
        summary_box = QTextEdit()
        summary_box.setReadOnly(True)
        summary_box.setPlainText(game_data.get("summary", "No description available."))
        summary_box.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: {Constants.C_TEXT_SECONDARY};
                padding: 12px;
                font-family: "Segoe UI";
                font-size: 13px;
                line-height: 1.5;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
                margin: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {Constants.C_BORDER};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Constants.C_TEXT_MUTED};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
        """)
        details_layout.addWidget(summary_box, 1)
        
        # Dialog Buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 8, 0, 0)
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(100, 36)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_PRIMARY};
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.05);
                border-color: {Constants.C_TEXT_MUTED};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)
        
        play_btn = QPushButton("▶ PLAY")
        play_btn.setFixedSize(120, 36)
        play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_ACCENT_VIOLET};
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_VIOLET_HOVER};
            }}
        """)
        play_btn.clicked.connect(self.accept)
        button_layout.addWidget(play_btn)
        
        details_layout.addLayout(button_layout)
        main_layout.addWidget(details_widget, 1)

# =============================================================================
# --- PREMIUM GAME HEADER BANNER ---
# =============================================================================
class SteamGameBanner(QWidget):
    play_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    info_clicked = pyqtSignal()
    favorite_toggled = pyqtSignal()
    
    _is_playing = False  # Tracks whether a game is currently running

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
        
        # Modern Violet Play Button (toggles to red STOP when game is running)
        self.play_btn = QPushButton("▶ PLAY")
        self.play_btn.setFixedSize(140, 48)
        self.play_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._play_style = f"""
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
        """
        self._stop_style = """
            QPushButton {
                background-color: #c0392b;
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
        """
        self.play_btn.setStyleSheet(self._play_style)
        self.play_btn.clicked.connect(self._on_play_stop_clicked)
        self.play_btn.setEnabled(False)
        self.actions_layout.addWidget(self.play_btn)
        
        # Secondary buttons layout
        self.secondary_layout = QHBoxLayout()
        
        self.fav_btn = QPushButton("★")
        self.fav_btn.setFixedSize(40, 32)
        self.fav_btn.setFont(QFont("Segoe UI", 14))
        self.fav_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_BG_PANEL};
                border: 1.5px solid {Constants.C_BORDER};
                color: {Constants.C_TEXT_MUTED};
                border-radius: 4px;
                padding: 0px;
                margin: 0px;
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

    def _on_play_stop_clicked(self):
        if self._is_playing:
            self.stop_clicked.emit()
        else:
            self.play_clicked.emit()

    def set_playing(self, is_playing: bool):
        """Toggle the button between PLAY (violet) and STOP (red) states."""
        self._is_playing = is_playing
        if is_playing:
            self.play_btn.setText("⏹ STOP")
            self.play_btn.setStyleSheet(self._stop_style)
            self.play_btn.setEnabled(True)
        else:
            self.play_btn.setText("▶ PLAY")
            self.play_btn.setStyleSheet(self._play_style)
            # Only re-enable if a game is actually selected
            self.play_btn.setEnabled(self.game_data is not None)

    def set_game(self, game_data, cover_pixmap, is_fav):
        self.game_data = game_data
        if not game_data:
            self.title_label.setText("Select a game to start")
            self.meta_label.setText("")
            self.playtime_label.setText("")
            # Only disable play if NOT currently playing something
            if not self._is_playing:
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
        
        # Don't change button state if a game is actively running
        if not self._is_playing:
            self.play_btn.setEnabled(True)
        
        if is_fav:
            self.fav_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Constants.C_WARNING};
                    background-color: {Constants.C_BORDER};
                    border: 1.5px solid {Constants.C_WARNING};
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 179, 0, 0.1);
                }}
            """)
        else:
            self.fav_btn.setStyleSheet(f"""
                QPushButton {{
                    color: {Constants.C_TEXT_MUTED};
                    background-color: {Constants.C_BG_PANEL};
                    border: 1.5px solid {Constants.C_BORDER};
                    border-radius: 4px;
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    background-color: {Constants.C_BORDER};
                    color: #ffffff;
                }}
            """)

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
        scroll.verticalScrollBar().setSingleStep(100)
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(24, 24, 24, 24)
        self.content_layout.setSpacing(24)
        
        # Header block
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        
        title_lbl = QLabel("STATS & ANALYTICS")
        title_lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; letter-spacing: 1.5px;")
        
        subtitle_lbl = QLabel("Track your playtime, platform distribution, and game sessions history.")
        subtitle_lbl.setFont(QFont("Segoe UI", 10))
        subtitle_lbl.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
        
        header_layout.addWidget(title_lbl)
        header_layout.addWidget(subtitle_lbl)
        self.content_layout.addWidget(header_widget)
        
        # 1. Summary Cards Header
        self.cards_grid = QGridLayout()
        self.cards_grid.setHorizontalSpacing(16)
        self.cards_grid.setVerticalSpacing(16)
        self.content_layout.addLayout(self.cards_grid)
        
        # 2. Horizontal layout for the main dashboard body
        self.dashboard_layout = QHBoxLayout()
        self.dashboard_layout.setSpacing(24)
        self.content_layout.addLayout(self.dashboard_layout)
        
        # 2a. Left Column (Leaderboards)
        self.left_column = QWidget()
        self.left_layout = QVBoxLayout(self.left_column)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(12)
        
        left_title = QLabel("🏆 PLAYTIME LEADERBOARDS")
        left_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        left_title.setStyleSheet(f"color: {Constants.C_TEXT_PRIMARY}; letter-spacing: 0.5px;")
        self.left_layout.addWidget(left_title)
        
        self.columns_layout = QHBoxLayout()
        self.columns_layout.setSpacing(16)
        self.left_layout.addLayout(self.columns_layout)
        
        self.dashboard_layout.addWidget(self.left_column, 2) # Stretch factor 2
        
        # 2b. Right Column (Platform + Recent Activity)
        self.right_column = QWidget()
        self.right_layout = QVBoxLayout(self.right_column)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(24)
        
        self.platform_container = QWidget()
        self.platform_layout = QVBoxLayout(self.platform_container)
        self.platform_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.addWidget(self.platform_container)
        
        self.recent_container = QWidget()
        self.recent_layout = QVBoxLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.addWidget(self.recent_container)
        
        self.dashboard_layout.addWidget(self.right_column, 1) # Stretch factor 1
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def clear_layout(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                self.clear_layout(item.layout())

    def format_relative_time(self, timestamp):
        if timestamp <= 0:
            return "Never"
        diff = time.time() - timestamp
        if diff < 60:
            return "Just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins}m ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours}h ago"
        else:
            days = int(diff / 86400)
            if days == 1:
                return "Yesterday"
            return f"{days}d ago"

    def format_duration(self, seconds):
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins}m"
        else:
            hours = seconds / 3600.0
            return f"{hours:.1f}h"

    def create_summary_card(self, title, value, icon, accent_color):
        card = QFrame()
        card.setObjectName("summaryCard")
        card.setStyleSheet(f"""
            QFrame#summaryCard {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 12px;
                padding: 16px;
            }}
            QFrame#summaryCard:hover {{
                border: 1.5px solid {accent_color};
                background-color: #1a1c25;
            }}
        """)
        
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; letter-spacing: 0.5px;")
        
        val_lbl = QLabel(value)
        val_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        val_lbl.setStyleSheet("color: #ffffff;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(val_lbl)
        
        icon_container = QFrame()
        icon_container.setFixedSize(50, 50)
        
        r = int(accent_color[1:3], 16)
        g = int(accent_color[3:5], 16)
        b = int(accent_color[5:7], 16)
        icon_container.setStyleSheet(f"""
            background-color: rgba({r}, {g}, {b}, 0.12);
            border: 1px solid rgba({r}, {g}, {b}, 0.25);
            border-radius: 25px;
        """)
        
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel()
        if len(icon) > 5 and (icon.endswith(".png") or icon.endswith(".jpg")):
            pixmap = QPixmap(icon)
            icon_label.setPixmap(pixmap.scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            icon_label.setText(icon)
            icon_label.setFont(QFont("Segoe UI Emoji", 20))
        icon_label.setStyleSheet("background: transparent;")
        icon_layout.addWidget(icon_label)
        
        layout.addLayout(text_layout, 1)
        layout.addWidget(icon_container)
        
        return card

    def create_ranking_column(self, title, dataset, game_lookup):
        column_frame = QFrame()
        column_frame.setObjectName("rankingColumn")
        column_frame.setStyleSheet(f"""
            QFrame#rankingColumn {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 12px;
            }}
        """)
        
        layout = QVBoxLayout(column_frame)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(4)
        
        header = QWidget()
        header.setFixedHeight(45)
        header.setStyleSheet(f"""
            background-color: rgba(255, 255, 255, 0.015);
            border-bottom: 1px solid {Constants.C_BORDER};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; letter-spacing: 0.5px;")
        header_layout.addWidget(title_lbl)
        layout.addWidget(header)
        
        sorted_ranks = sorted(dataset.items(), key=lambda x: x[1], reverse=True)[:5]
        
        if not sorted_ranks:
            no_data = QLabel("No sessions recorded.")
            no_data.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            no_data.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addStretch()
            layout.addWidget(no_data)
            layout.addStretch()
        else:
            max_duration = sorted_ranks[0][1]
            for idx, (game_hash, duration) in enumerate(sorted_ranks):
                hours = duration / 3600.0
                game = game_lookup.get(game_hash)
                game_title = game["title"] if game else "Unknown Game"
                platform = game["platform"] if game else "Unknown"
                
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(12, 6, 12, 6)
                row_layout.setSpacing(10)
                
                # Rank Badge
                rank_lbl = QLabel(str(idx + 1))
                rank_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rank_lbl.setFixedSize(22, 22)
                if idx == 0:
                    rank_lbl.setStyleSheet("background-color: #ffd700; color: #0d0e12; border-radius: 11px;")
                elif idx == 1:
                    rank_lbl.setStyleSheet("background-color: #e0e0e0; color: #0d0e12; border-radius: 11px;")
                elif idx == 2:
                    rank_lbl.setStyleSheet("background-color: #cd7f32; color: #ffffff; border-radius: 11px;")
                else:
                    rank_lbl.setStyleSheet(f"background-color: {Constants.C_BG_DARK}; color: {Constants.C_TEXT_MUTED}; border-radius: 11px; border: 1px solid {Constants.C_BORDER};")
                
                row_layout.addWidget(rank_lbl)
                
                # Cover Thumbnail
                cover_path = self.config_manager.covers_dir / f"{game_hash}.jpg"
                cover_lbl = QLabel()
                cover_lbl.setFixedSize(32, 44)
                cover_lbl.setScaledContents(True)
                if cover_path.exists():
                    pixmap = QPixmap(str(cover_path))
                    scaled_pixmap = pixmap.scaled(32, 44, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    cover_lbl.setPixmap(scaled_pixmap)
                    cover_lbl.setStyleSheet("border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);")
                else:
                    initials = "".join([w[0].upper() for w in game_title.split() if w])[:2]
                    cover_lbl.setText(initials)
                    cover_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    val_hash = int(hashlib.md5(game_title.encode('utf-8')).hexdigest(), 16)
                    gradients = ["#2b1b54", "#0b3c5d", "#4f3b78", "#1b4d3e", "#5c2538"]
                    bg_color = gradients[val_hash % len(gradients)]
                    cover_lbl.setStyleSheet(f"background-color: {bg_color}; color: #ffffff; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);")
                
                row_layout.addWidget(cover_lbl)
                
                # Title and Platform
                text_widget = QWidget()
                text_layout = QVBoxLayout(text_widget)
                text_layout.setContentsMargins(0, 0, 0, 0)
                text_layout.setSpacing(2)
                
                title_lbl = QLabel(game_title)
                title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                title_lbl.setStyleSheet("color: #ffffff;")
                title_lbl.setWordWrap(True)
                
                plat_lbl = QLabel(platform.upper())
                plat_lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                plat_upper = platform.upper()
                if "PLAYSTATION" in plat_upper or "PS3" in plat_upper or "RPCS3" in plat_upper:
                    badge_bg = "rgba(0, 55, 145, 0.15)"
                    badge_fg = "#6fb3ff"
                elif "STEAM" in plat_upper or "PC" in plat_upper:
                    badge_bg = "rgba(0, 173, 238, 0.15)"
                    badge_fg = "#00adee"
                elif "RETRO" in plat_upper or "RETROARCH" in plat_upper:
                    badge_bg = "rgba(160, 224, 80, 0.15)"
                    badge_fg = "#a0e050"
                else:
                    badge_bg = "rgba(140, 82, 255, 0.15)"
                    badge_fg = "#a175ff"
                
                plat_lbl.setStyleSheet(f"background-color: {badge_bg}; color: {badge_fg}; border-radius: 3px; padding: 1px 4px;")
                plat_layout = QHBoxLayout()
                plat_layout.addWidget(plat_lbl)
                plat_layout.addStretch()
                
                text_layout.addWidget(title_lbl)
                text_layout.addLayout(plat_layout)
                
                row_layout.addLayout(text_layout, 1)
                
                # Progress and Hours
                prog_layout = QVBoxLayout()
                prog_layout.setSpacing(4)
                prog_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                bar = QProgressBar()
                bar.setTextVisible(False)
                bar.setFixedHeight(5)
                bar.setRange(0, 100)
                bar.setValue(int((duration / max_duration) * 100) if max_duration > 0 else 0)
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: {Constants.C_BG_DARK};
                        border: none;
                        border-radius: 2px;
                    }}
                    QProgressBar::chunk {{
                        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_ACCENT_VIOLET}, stop:1 {Constants.C_ACCENT_CYAN});
                        border-radius: 2px;
                    }}
                """)
                bar.setFixedWidth(80)
                
                hours_lbl = QLabel(f"{hours:.1f}h")
                hours_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                hours_lbl.setStyleSheet(f"color: {Constants.C_SUCCESS};")
                hours_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                
                prog_layout.addWidget(bar)
                prog_layout.addWidget(hours_lbl)
                
                row_layout.addLayout(prog_layout)
                
                layout.addWidget(row_widget)
                
                if idx < len(sorted_ranks) - 1:
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setStyleSheet(f"background-color: {Constants.C_BORDER}; border: none; height: 1px; margin-left: 12px; margin-right: 12px;")
                    layout.addWidget(sep)
            
            layout.addStretch()
            
        return column_frame

    def create_platform_breakdown(self, system_playtime, system_games_count):
        panel = QFrame()
        panel.setObjectName("platformPanel")
        panel.setStyleSheet(f"""
            QFrame#platformPanel {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 12px;
            }}
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(4)
        
        header = QWidget()
        header.setFixedHeight(45)
        header.setStyleSheet(f"""
            background-color: rgba(255, 255, 255, 0.015);
            border-bottom: 1px solid {Constants.C_BORDER};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        title_lbl = QLabel("PLATFORM PLAYTIME")
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; letter-spacing: 0.5px;")
        header_layout.addWidget(title_lbl)
        layout.addWidget(header)
        
        sorted_platforms = sorted(system_playtime.items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_platforms:
            no_data = QLabel("No platforms data.")
            no_data.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            no_data.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addStretch()
            layout.addWidget(no_data)
            layout.addStretch()
        else:
            max_duration = max(system_playtime.values()) if system_playtime else 1
            for idx, (platform, duration) in enumerate(sorted_platforms):
                hours = duration / 3600.0
                game_count = system_games_count.get(platform, 0)
                
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(16, 8, 16, 8)
                row_layout.setSpacing(10)
                
                plat_lbl = QLabel(platform.upper())
                plat_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                plat_upper = platform.upper()
                if "PLAYSTATION" in plat_upper or "PS3" in plat_upper or "RPCS3" in plat_upper:
                    badge_bg = "rgba(0, 55, 145, 0.15)"
                    badge_fg = "#6fb3ff"
                elif "STEAM" in plat_upper or "PC" in plat_upper:
                    badge_bg = "rgba(0, 173, 238, 0.15)"
                    badge_fg = "#00adee"
                elif "RETRO" in plat_upper or "RETROARCH" in plat_upper:
                    badge_bg = "rgba(160, 224, 80, 0.15)"
                    badge_fg = "#a0e050"
                else:
                    badge_bg = "rgba(140, 82, 255, 0.15)"
                    badge_fg = "#a175ff"
                
                plat_lbl.setStyleSheet(f"background-color: {badge_bg}; color: {badge_fg}; border-radius: 3px; padding: 2px 6px;")
                plat_layout = QHBoxLayout()
                plat_layout.addWidget(plat_lbl)
                plat_layout.addStretch()
                
                prog_layout = QVBoxLayout()
                prog_layout.setSpacing(4)
                prog_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                bar = QProgressBar()
                bar.setTextVisible(False)
                bar.setFixedHeight(5)
                bar.setRange(0, 100)
                bar.setValue(int((duration / max_duration) * 100) if max_duration > 0 else 0)
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: {Constants.C_BG_DARK};
                        border: none;
                        border-radius: 2px;
                    }}
                    QProgressBar::chunk {{
                        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Constants.C_ACCENT_VIOLET}, stop:1 {Constants.C_ACCENT_CYAN});
                        border-radius: 2px;
                    }}
                """)
                bar.setFixedWidth(120)
                
                games_suffix = "game" if game_count == 1 else "games"
                info_lbl = QLabel(f"{hours:.1f}h ({game_count} {games_suffix})")
                info_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                info_lbl.setStyleSheet(f"color: {Constants.C_TEXT_SECONDARY};")
                info_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                
                prog_layout.addWidget(bar)
                prog_layout.addWidget(info_lbl)
                
                row_layout.addLayout(plat_layout, 1)
                row_layout.addLayout(prog_layout)
                
                layout.addWidget(row_widget)
                
                if idx < len(sorted_platforms) - 1:
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setStyleSheet(f"background-color: {Constants.C_BORDER}; border: none; height: 1px; margin-left: 16px; margin-right: 16px;")
                    layout.addWidget(sep)
            
            layout.addStretch()
            
        return panel

    def create_recent_activity(self, recent_plays):
        panel = QFrame()
        panel.setObjectName("recentPanel")
        panel.setStyleSheet(f"""
            QFrame#recentPanel {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 12px;
            }}
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(4)
        
        header = QWidget()
        header.setFixedHeight(45)
        header.setStyleSheet(f"""
            background-color: rgba(255, 255, 255, 0.015);
            border-bottom: 1px solid {Constants.C_BORDER};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        title_lbl = QLabel("RECENT ACTIVITY")
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN}; letter-spacing: 0.5px;")
        header_layout.addWidget(title_lbl)
        layout.addWidget(header)
        
        if not recent_plays:
            no_data = QLabel("No recent sessions.")
            no_data.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            no_data.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addStretch()
            layout.addWidget(no_data)
            layout.addStretch()
        else:
            for idx, (game, last_ts, session_dur) in enumerate(recent_plays):
                game_title = game["title"]
                game_hash = game["hash"]
                
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(16, 8, 16, 8)
                row_layout.setSpacing(10)
                
                cover_path = self.config_manager.covers_dir / f"{game_hash}.jpg"
                cover_lbl = QLabel()
                cover_lbl.setFixedSize(32, 44)
                cover_lbl.setScaledContents(True)
                if cover_path.exists():
                    pixmap = QPixmap(str(cover_path))
                    scaled_pixmap = pixmap.scaled(32, 44, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    cover_lbl.setPixmap(scaled_pixmap)
                    cover_lbl.setStyleSheet("border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);")
                else:
                    initials = "".join([w[0].upper() for w in game_title.split() if w])[:2]
                    cover_lbl.setText(initials)
                    cover_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    val_hash = int(hashlib.md5(game_title.encode('utf-8')).hexdigest(), 16)
                    gradients = ["#2b1b54", "#0b3c5d", "#4f3b78", "#1b4d3e", "#5c2538"]
                    bg_color = gradients[val_hash % len(gradients)]
                    cover_lbl.setStyleSheet(f"background-color: {bg_color}; color: #ffffff; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);")
                
                row_layout.addWidget(cover_lbl)
                
                details_layout = QVBoxLayout()
                details_layout.setSpacing(2)
                
                title_lbl = QLabel(game_title)
                title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                title_lbl.setStyleSheet("color: #ffffff;")
                title_lbl.setWordWrap(True)
                
                time_lbl = QLabel(self.format_relative_time(last_ts))
                time_lbl.setFont(QFont("Segoe UI", 8))
                time_lbl.setStyleSheet(f"color: {Constants.C_TEXT_MUTED};")
                
                details_layout.addWidget(title_lbl)
                details_layout.addWidget(time_lbl)
                row_layout.addLayout(details_layout, 1)
                
                dur_lbl = QLabel(f"+{self.format_duration(session_dur)}")
                dur_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                dur_lbl.setStyleSheet(f"color: {Constants.C_ACCENT_CYAN};")
                dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row_layout.addWidget(dur_lbl)
                
                layout.addWidget(row_widget)
                
                if idx < len(recent_plays) - 1:
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setStyleSheet(f"background-color: {Constants.C_BORDER}; border: none; height: 1px; margin-left: 16px; margin-right: 16px;")
                    layout.addWidget(sep)
            
            layout.addStretch()
            
        return panel

    def refresh_stats(self, all_games):
        self.clear_layout(self.cards_grid)
        self.clear_layout(self.columns_layout)
        self.clear_layout(self.platform_layout)
        self.clear_layout(self.recent_layout)
        
        game_lookup = {g["hash"]: g for g in all_games}
        
        total_games = len(all_games)
        total_playtime_s = sum(g.get("playtime", 0) for g in all_games)
        total_playtime_h = total_playtime_s / 3600.0
        
        system_games_count = {}
        system_playtime = {}
        for g in all_games:
            plat = g.get("platform", "Unknown")
            system_games_count[plat] = system_games_count.get(plat, 0) + 1
            system_playtime[plat] = system_playtime.get(plat, 0) + g.get("playtime", 0)
            
        favorite_system = "None"
        if system_playtime:
            favorite_system = max(system_playtime, key=system_playtime.get)
            if system_playtime[favorite_system] == 0:
                favorite_system = list(system_playtime.keys())[0]
                
        now = time.time()
        week_ago = now - (7 * 86400)
        month_ago = now - (30 * 86400)
        year_ago = now - (365 * 86400)
        
        week_stats = {}
        month_stats = {}
        year_stats = {}
        
        recent_plays = []
        total_sessions = 0
        
        for g in all_games:
            metadata = self.config_manager.config.get("game_metadata", {}).get(g["hash"], {})
            sessions = metadata.get("sessions", [])
            total_sessions += len(sessions)
            
            if sessions:
                latest_session = max(sessions, key=lambda s: s.get("timestamp", 0))
                recent_plays.append((g, latest_session.get("timestamp", 0), latest_session.get("duration", 0)))
                
            for session in sessions:
                ts = session.get("timestamp", 0)
                dur = session.get("duration", 0)
                
                if ts >= week_ago:
                    week_stats[g["hash"]] = week_stats.get(g["hash"], 0.0) + dur
                if ts >= month_ago:
                    month_stats[g["hash"]] = month_stats.get(g["hash"], 0.0) + dur
                if ts >= year_ago:
                    year_stats[g["hash"]] = year_stats.get(g["hash"], 0.0) + dur
                    
        recent_plays.sort(key=lambda x: x[1], reverse=True)
        top_recent = recent_plays[:5]
        
        import os
        clock_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "clock.png")
        if not os.path.exists(clock_icon):
            clock_icon = "⏱"
        
        gamepad_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "Gamepad.png")
        if not os.path.exists(gamepad_icon):
            gamepad_icon = "🎮"

        self.cards_grid.addWidget(self.create_summary_card("TOTAL GAMES", f"{total_games} games", "📁", Constants.C_ACCENT_CYAN), 0, 0)
        self.cards_grid.addWidget(self.create_summary_card("TOTAL PLAYTIME", f"{total_playtime_h:.1f} hrs", clock_icon, Constants.C_ACCENT_VIOLET), 0, 1)
        self.cards_grid.addWidget(self.create_summary_card("FAVORITE PLATFORM", favorite_system, gamepad_icon, Constants.C_SUCCESS), 0, 2)
        self.cards_grid.addWidget(self.create_summary_card("ACTIVE SESSIONS", f"{total_sessions} sessions", "📈", Constants.C_WARNING), 0, 3)
        
        self.columns_layout.addWidget(self.create_ranking_column("THIS WEEK", week_stats, game_lookup))
        self.columns_layout.addWidget(self.create_ranking_column("THIS MONTH", month_stats, game_lookup))
        self.columns_layout.addWidget(self.create_ranking_column("THIS YEAR", year_stats, game_lookup))
        
        self.platform_layout.addWidget(self.create_platform_breakdown(system_playtime, system_games_count))
        self.recent_layout.addWidget(self.create_recent_activity(top_recent))

# =============================================================================
# --- MANUAL IGDB SEARCH MODAL ---
# =============================================================================
from PyQt6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem

class ManualIGDBSearchModal(QDialog):
    def __init__(self, game_data, igdb_client, parent=None):
        super().__init__(parent)
        self.game_data = game_data
        self.igdb_client = igdb_client
        self.selected_metadata = None
        self._all_results = []   # cache of all fetched results for client-side filtering

        self.setWindowTitle(f"Manual IGDB Search — {game_data.get('title')}")
        self.setMinimumSize(680, 520)
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
            QLineEdit {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 4px;
                color: #ffffff;
                padding: 6px;
                font-size: 13px;
            }}
            QComboBox {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 4px;
                color: #ffffff;
                padding: 4px 8px;
                min-width: 140px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Constants.C_BG_PANEL};
                color: #ffffff;
                selection-background-color: {Constants.C_BORDER};
            }}
            QListWidget {{
                background-color: {Constants.C_BG_PANEL};
                border: 1px solid {Constants.C_BORDER};
                border-radius: 4px;
                color: #ffffff;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {Constants.C_BORDER};
            }}
            QListWidget::item:selected {{
                background-color: {Constants.C_BORDER};
                color: {Constants.C_ACCENT_CYAN};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Row 1: search input + button ──────────────────────────────────
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setText(game_data.get("title", ""))
        self.search_input.returnPressed.connect(self.perform_search)
        search_layout.addWidget(self.search_input, 1)

        self.btn_search = QPushButton("Search IGDB")
        self.btn_search.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_ACCENT_VIOLET};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Constants.C_VIOLET_HOVER};
            }}
        """)
        self.btn_search.clicked.connect(self.perform_search)
        search_layout.addWidget(self.btn_search)
        layout.addLayout(search_layout)

        # ── Row 2: game-type filter ───────────────────────────────────────
        filter_layout = QHBoxLayout()
        type_lbl = QLabel("Filter by type:")
        type_lbl.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; font-size: 11px;")
        filter_layout.addWidget(type_lbl)

        from PyQt6.QtWidgets import QComboBox
        self.combo_type = QComboBox()
        self.combo_type.addItem("All Types", -1)
        self.combo_type.addItem("Main Game", 0)
        self.combo_type.addItem("DLC / Addon", 1)
        self.combo_type.addItem("Expansion", 2)
        self.combo_type.addItem("Bundle", 3)
        self.combo_type.addItem("Standalone Expansion", 4)
        self.combo_type.addItem("Remake", 8)
        self.combo_type.addItem("Remaster", 9)
        self.combo_type.addItem("Port", 11)
        self.combo_type.currentIndexChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.combo_type)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # ── Status label ──────────────────────────────────────────────────
        self.lbl_status = QLabel("Enter a query and click Search to find metadata.")
        self.lbl_status.setStyleSheet(f"color: {Constants.C_TEXT_MUTED}; font-style: italic;")
        layout.addWidget(self.lbl_status)

        # ── Results list ──────────────────────────────────────────────────
        self.results_list = QListWidget()
        layout.addWidget(self.results_list)

        # ── Action buttons ────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_apply = QPushButton("Apply Selected Metadata")
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet(f"""
            QPushButton {{
                background-color: {Constants.C_ACCENT_CYAN};
                color: #000000;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 20px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: #26f5ff;
            }}
            QPushButton:disabled {{
                background-color: {Constants.C_BORDER};
                color: #888888;
            }}
        """)
        self.btn_apply.clicked.connect(self.apply_metadata)
        btn_layout.addWidget(self.btn_apply)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(f"""
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
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        self.results_list.itemSelectionChanged.connect(self.on_selection_changed)

        # Auto-trigger search on open
        self.perform_search()

    def perform_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        self.btn_search.setEnabled(False)
        self.lbl_status.setText("Searching IGDB…")
        self.results_list.clear()
        self.btn_apply.setEnabled(False)
        self._all_results = []

        import threading
        def worker():
            results = self.igdb_client.search_games_manual(query)
            self._all_results = results
            from PyQt6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "on_results_ready", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_filter(self):
        """Re-populate the list according to the current type filter."""
        if not self._all_results:
            return

        cat_filter = self.combo_type.currentData()   # -1 = all
        filtered = self._all_results if cat_filter == -1 else [
            r for r in self._all_results if r.get("category_id", 0) == cat_filter
        ]

        self.results_list.clear()
        self.btn_apply.setEnabled(False)

        if not filtered:
            self.lbl_status.setText(
                f"No results for the selected type filter (showing 0 of {len(self._all_results)})."
            )
            return

        self.lbl_status.setText(
            f"Showing {len(filtered)} of {len(self._all_results)} results. Select one to apply."
        )
        for r in filtered:
            item = QListWidgetItem()
            cat_badge = f"[{r.get('category_name', 'Main Game')}]"
            display_text = (
                f"{cat_badge}  {r['title']}\n"
                f"Released: {r['release_date']}  |  Dev: {r['developer']}\n"
                f"Platforms: {r['platforms_str']}"
            )
            item.setText(display_text)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.results_list.addItem(item)

    from PyQt6.QtCore import pyqtSlot
    @pyqtSlot()
    def on_results_ready(self):
        self.btn_search.setEnabled(True)
        if not self._all_results:
            self.lbl_status.setText("No results found. Try a different search term.")
            return
        self._apply_filter()

    def on_selection_changed(self):
        self.btn_apply.setEnabled(len(self.results_list.selectedItems()) > 0)

    def apply_metadata(self):
        items = self.results_list.selectedItems()
        if items:
            self.selected_metadata = items[0].data(Qt.ItemDataRole.UserRole)
            self.accept()

