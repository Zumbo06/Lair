# constants.py

class Constants:
    VERSION = "3.00"
    APP_NAME = "Lair"
    
    # Default Theme Colors
    DEFAULT_C_BG_DARK = "#0d0e12"
    DEFAULT_C_BG_PANEL = "#16171e"
    DEFAULT_C_BORDER = "#232530"
    DEFAULT_C_ACCENT_CYAN = "#00e5ff"
    DEFAULT_C_ACCENT_VIOLET = "#8c52ff"
    DEFAULT_C_VIOLET_HOVER = "#a175ff"
    DEFAULT_C_TEXT_PRIMARY = "#ffffff"
    DEFAULT_C_TEXT_SECONDARY = "#b0b5c6"
    DEFAULT_C_TEXT_MUTED = "#6e7387"
    DEFAULT_C_SUCCESS = "#a0e050"
    DEFAULT_C_WARNING = "#ffb300"
    DEFAULT_C_ERROR = "#ff557f"

    # High Contrast Theme Colors
    HC_C_BG_DARK = "#000000"
    HC_C_BG_PANEL = "#000000"
    HC_C_BORDER = "#ffffff"
    HC_C_ACCENT_CYAN = "#ffff00"  # High contrast yellow
    HC_C_ACCENT_VIOLET = "#00ffff"  # High contrast cyan
    HC_C_VIOLET_HOVER = "#00ffff"
    HC_C_TEXT_PRIMARY = "#ffffff"
    HC_C_TEXT_SECONDARY = "#ffffff"
    HC_C_TEXT_MUTED = "#ffffff"
    HC_C_SUCCESS = "#00ff00"
    HC_C_WARNING = "#ffff00"
    HC_C_ERROR = "#ff0000"

    # Active Colors
    C_BG_DARK = DEFAULT_C_BG_DARK
    C_BG_PANEL = DEFAULT_C_BG_PANEL
    C_BORDER = DEFAULT_C_BORDER
    C_ACCENT_CYAN = DEFAULT_C_ACCENT_CYAN
    C_ACCENT_VIOLET = DEFAULT_C_ACCENT_VIOLET
    C_VIOLET_HOVER = DEFAULT_C_VIOLET_HOVER
    C_TEXT_PRIMARY = DEFAULT_C_TEXT_PRIMARY
    C_TEXT_SECONDARY = DEFAULT_C_TEXT_SECONDARY
    C_TEXT_MUTED = DEFAULT_C_TEXT_MUTED
    C_SUCCESS = DEFAULT_C_SUCCESS
    C_WARNING = DEFAULT_C_WARNING
    C_ERROR = DEFAULT_C_ERROR

    @classmethod
    def apply_high_contrast(cls, enable=True):
        if enable:
            cls.C_BG_DARK = cls.HC_C_BG_DARK
            cls.C_BG_PANEL = cls.HC_C_BG_PANEL
            cls.C_BORDER = cls.HC_C_BORDER
            cls.C_ACCENT_CYAN = cls.HC_C_ACCENT_CYAN
            cls.C_ACCENT_VIOLET = cls.HC_C_ACCENT_VIOLET
            cls.C_VIOLET_HOVER = cls.HC_C_VIOLET_HOVER
            cls.C_TEXT_PRIMARY = cls.HC_C_TEXT_PRIMARY
            cls.C_TEXT_SECONDARY = cls.HC_C_TEXT_SECONDARY
            cls.C_TEXT_MUTED = cls.HC_C_TEXT_MUTED
            cls.C_SUCCESS = cls.HC_C_SUCCESS
            cls.C_WARNING = cls.HC_C_WARNING
            cls.C_ERROR = cls.HC_C_ERROR
        else:
            cls.C_BG_DARK = cls.DEFAULT_C_BG_DARK
            cls.C_BG_PANEL = cls.DEFAULT_C_BG_PANEL
            cls.C_BORDER = cls.DEFAULT_C_BORDER
            cls.C_ACCENT_CYAN = cls.DEFAULT_C_ACCENT_CYAN
            cls.C_ACCENT_VIOLET = cls.DEFAULT_C_ACCENT_VIOLET
            cls.C_VIOLET_HOVER = cls.DEFAULT_C_VIOLET_HOVER
            cls.C_TEXT_PRIMARY = cls.DEFAULT_C_TEXT_PRIMARY
            cls.C_TEXT_SECONDARY = cls.DEFAULT_C_TEXT_SECONDARY
            cls.C_TEXT_MUTED = cls.DEFAULT_C_TEXT_MUTED
            cls.C_SUCCESS = cls.DEFAULT_C_SUCCESS
            cls.C_WARNING = cls.DEFAULT_C_WARNING
            cls.C_ERROR = cls.DEFAULT_C_ERROR
    
    ALL_GAMES_CATEGORY = "ALL GAMES"
    FAVORITES_CATEGORY = "FAVORITES"
    RECENTS_CATEGORY = "RECENTLY PLAYED"
    COLLECTIONS_CATEGORY = "COLLECTIONS"
    
    DEFAULT_GRID_WIDTH = 140
    DEFAULT_GRID_HEIGHT = 200
