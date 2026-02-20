"""Design-token-based theme system for Book2Audiobook.

Provides light/dark palettes, a QSS generator, and a ThemeManager
that respects macOS system appearance.
"""
from __future__ import annotations

import platform
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Enums & tokens
# ---------------------------------------------------------------------------

class ThemeMode(Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass(frozen=True)
class ThemeColors:
    # Backgrounds
    bg_primary: str        # main window
    bg_secondary: str      # sidebar
    bg_surface: str        # cards
    bg_hover: str          # hover state
    bg_active: str         # active/pressed

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_on_accent: str

    # Accent / brand
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_subtle: str     # light tint for backgrounds

    # Semantic
    success: str
    warning: str
    error: str
    info: str

    # Border & divider
    border: str
    border_subtle: str
    divider: str

    # Misc
    shadow: str
    overlay: str
    scrollbar_bg: str
    scrollbar_handle: str


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

LIGHT_PALETTE = ThemeColors(
    bg_primary="#F8F9FB",
    bg_secondary="#FFFFFF",
    bg_surface="#FFFFFF",
    bg_hover="#F0F1F4",
    bg_active="#E4E6EB",

    text_primary="#1A1D26",
    text_secondary="#4A4F5C",
    text_muted="#8B8FA3",
    text_on_accent="#FFFFFF",

    accent="#4F6EF7",
    accent_hover="#3B5BDE",
    accent_pressed="#2D4BC9",
    accent_subtle="#EEF1FD",

    success="#2BA84A",
    warning="#E5A100",
    error="#DC3545",
    info="#0DCAF0",

    border="#DFE1E6",
    border_subtle="#EDF0F4",
    divider="#E9ECF1",

    shadow="rgba(0, 0, 0, 0.06)",
    overlay="rgba(0, 0, 0, 0.35)",
    scrollbar_bg="#F0F1F4",
    scrollbar_handle="#C4C7CF",
)

DARK_PALETTE = ThemeColors(
    bg_primary="#12141A",
    bg_secondary="#1A1D26",
    bg_surface="#22252F",
    bg_hover="#2A2E3A",
    bg_active="#33384A",

    text_primary="#E8EAF0",
    text_secondary="#A8ACBA",
    text_muted="#6B6F80",
    text_on_accent="#FFFFFF",

    accent="#6B8AFF",
    accent_hover="#8AA2FF",
    accent_pressed="#5474E8",
    accent_subtle="#1E2540",

    success="#3BD860",
    warning="#FFBF30",
    error="#FF5A5A",
    info="#40E0FF",

    border="#2E3240",
    border_subtle="#262A35",
    divider="#262A35",

    shadow="rgba(0, 0, 0, 0.30)",
    overlay="rgba(0, 0, 0, 0.55)",
    scrollbar_bg="#1A1D26",
    scrollbar_handle="#3A3E4C",
)


# ---------------------------------------------------------------------------
# Spacing & radii tokens
# ---------------------------------------------------------------------------

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "xxl": 32,
}

RADII = {
    "sm": 6,
    "md": 10,
    "lg": 14,
    "xl": 20,
}

SIDEBAR_WIDTH = 220
HEADER_HEIGHT = 56


# ---------------------------------------------------------------------------
# QSS generator
# ---------------------------------------------------------------------------

def generate_qss(c: ThemeColors) -> str:
    """Return a full-application QSS string for the given palette."""
    return f"""
/* ============ Global ============ */
QWidget {{
    background-color: {c.bg_primary};
    color: {c.text_primary};
    font-family: "Inter", "SF Pro Display", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}}

QMainWindow {{
    background-color: {c.bg_primary};
}}

/* ============ Scrollbar ============ */
QScrollBar:vertical {{
    background: {c.scrollbar_bg};
    width: 8px;
    border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c.scrollbar_handle};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {c.scrollbar_bg};
    height: 8px;
    border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c.scrollbar_handle};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ============ Labels ============ */
QLabel {{
    background: transparent;
    padding: 0px;
}}

/* ============ LineEdit / SpinBox ============ */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {RADII['sm']}px;
    padding: 6px 10px;
    selection-background-color: {c.accent};
    selection-color: {c.text_on_accent};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c.accent};
}}
QLineEdit:disabled, QSpinBox:disabled {{
    background-color: {c.bg_hover};
    color: {c.text_muted};
}}

/* ============ ComboBox ============ */
QComboBox {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {RADII['sm']}px;
    padding: 6px 10px;
    padding-right: 28px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: {c.accent};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 24px;
    border: none;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c.text_secondary};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {RADII['sm']}px;
    padding: 4px;
    selection-background-color: {c.accent_subtle};
    selection-color: {c.text_primary};
    outline: none;
}}

/* ============ PushButton (default) ============ */
QPushButton {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {RADII['sm']}px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {c.bg_hover};
    border-color: {c.border};
}}
QPushButton:pressed {{
    background-color: {c.bg_active};
}}
QPushButton:disabled {{
    background-color: {c.bg_hover};
    color: {c.text_muted};
    border-color: {c.border_subtle};
}}

/* ============ Primary button ============ */
QPushButton[cssClass="primary"] {{
    background-color: {c.accent};
    color: {c.text_on_accent};
    border: none;
    font-weight: 600;
}}
QPushButton[cssClass="primary"]:hover {{
    background-color: {c.accent_hover};
}}
QPushButton[cssClass="primary"]:pressed {{
    background-color: {c.accent_pressed};
}}
QPushButton[cssClass="primary"]:disabled {{
    background-color: {c.border};
    color: {c.text_muted};
}}

/* ============ Danger button ============ */
QPushButton[cssClass="danger"] {{
    background-color: {c.error};
    color: {c.text_on_accent};
    border: none;
    font-weight: 600;
}}
QPushButton[cssClass="danger"]:hover {{
    background-color: #c82333;
}}

/* ============ Slider ============ */
QSlider::groove:horizontal {{
    background: {c.bg_hover};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {c.accent};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {c.accent};
    border-radius: 3px;
}}

/* ============ ProgressBar ============ */
QProgressBar {{
    background-color: {c.bg_hover};
    border: none;
    border-radius: {RADII['sm']}px;
    text-align: center;
    color: transparent;
    min-height: 8px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    background-color: {c.accent};
    border-radius: {RADII['sm']}px;
}}

/* ============ TabWidget ============ */
QTabWidget::pane {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border};
    border-radius: {RADII['md']}px;
    padding: 12px;
    margin-top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {c.text_secondary};
    padding: 8px 20px;
    border-bottom: 2px solid transparent;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    color: {c.accent};
    border-bottom: 2px solid {c.accent};
}}
QTabBar::tab:hover:!selected {{
    color: {c.text_primary};
}}

/* ============ GroupBox ============ */
QGroupBox {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {RADII['md']}px;
    margin-top: 16px;
    padding-top: 24px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {c.text_secondary};
}}

/* ============ TableView ============ */
QTableView, QTreeView, QListView {{
    background-color: {c.bg_surface};
    alternate-background-color: {c.bg_hover};
    border: 1px solid {c.border_subtle};
    border-radius: {RADII['sm']}px;
    gridline-color: {c.divider};
    selection-background-color: {c.accent_subtle};
    selection-color: {c.text_primary};
}}
QHeaderView::section {{
    background-color: {c.bg_primary};
    color: {c.text_secondary};
    border: none;
    border-bottom: 1px solid {c.divider};
    padding: 6px 12px;
    font-weight: 600;
    font-size: 12px;
}}

/* ============ TextEdit (LogConsole) ============ */
QTextEdit {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border_subtle};
    border-radius: {RADII['sm']}px;
    padding: 8px;
    font-family: "SF Mono", "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}}

/* ============ Dialog ============ */
QDialog {{
    background-color: {c.bg_primary};
}}

/* ============ ToolTip ============ */
QToolTip {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {RADII['sm']}px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ============ Menu ============ */
QMenuBar {{
    background-color: {c.bg_secondary};
    color: {c.text_primary};
    border-bottom: 1px solid {c.divider};
    padding: 2px;
}}
QMenuBar::item:selected {{
    background-color: {c.bg_hover};
    border-radius: 4px;
}}
QMenu {{
    background-color: {c.bg_surface};
    color: {c.text_primary};
    border: 1px solid {c.border};
    border-radius: {RADII['sm']}px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {c.accent_subtle};
}}
QMenu::separator {{
    height: 1px;
    background: {c.divider};
    margin: 4px 8px;
}}

/* ============ Custom classes ============ */
QWidget[cssClass="sidebar"] {{
    background-color: {c.bg_secondary};
    border-right: 1px solid {c.divider};
}}
QWidget[cssClass="header"] {{
    background-color: {c.bg_secondary};
    border-bottom: 1px solid {c.divider};
}}
QWidget[cssClass="card"] {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {RADII['lg']}px;
}}
QLabel[cssClass="title"] {{
    font-size: 22px;
    font-weight: 700;
    color: {c.text_primary};
}}
QLabel[cssClass="subtitle"] {{
    font-size: 14px;
    font-weight: 500;
    color: {c.text_secondary};
}}
QLabel[cssClass="muted"] {{
    font-size: 12px;
    color: {c.text_muted};
}}
QLabel[cssClass="sectionTitle"] {{
    font-size: 15px;
    font-weight: 600;
    color: {c.text_primary};
}}
QLabel[cssClass="fieldLabel"] {{
    font-size: 12px;
    font-weight: 600;
    color: {c.text_secondary};
    letter-spacing: 0.3px;
}}
QLabel[cssClass="error"] {{
    color: {c.error};
    font-size: 12px;
}}
QLabel[cssClass="success"] {{
    color: {c.success};
    font-size: 12px;
}}
"""


# ---------------------------------------------------------------------------
# System dark-mode detection (macOS)
# ---------------------------------------------------------------------------

def _is_macos_dark() -> bool:
    """Detect macOS dark mode via NSUserDefaults."""
    if platform.system() != "Darwin":
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip().lower() == "dark"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------

class ThemeManager(QObject):
    """Manages application theme switching."""

    theme_changed = Signal(str)  # emits "light" or "dark"

    def __init__(self, app: QApplication, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._app = app
        self._mode = ThemeMode.SYSTEM
        self._resolved: str = "light"

        # Poll for macOS system theme changes every 5 seconds
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5000)
        self._poll_timer.timeout.connect(self._check_system_theme)

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self._resolved == "dark"

    def colors(self) -> ThemeColors:
        return DARK_PALETTE if self.is_dark else LIGHT_PALETTE

    def set_mode(self, mode: ThemeMode) -> None:
        self._mode = mode
        if mode == ThemeMode.SYSTEM:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()
        self._apply()

    def cycle_mode(self) -> ThemeMode:
        """Cycle through LIGHT → DARK → SYSTEM → LIGHT..."""
        order = [ThemeMode.LIGHT, ThemeMode.DARK, ThemeMode.SYSTEM]
        idx = (order.index(self._mode) + 1) % len(order)
        self.set_mode(order[idx])
        return self._mode

    def _resolve(self) -> str:
        if self._mode == ThemeMode.LIGHT:
            return "light"
        if self._mode == ThemeMode.DARK:
            return "dark"
        return "dark" if _is_macos_dark() else "light"

    def _apply(self) -> None:
        new_resolved = self._resolve()
        changed = new_resolved != self._resolved
        self._resolved = new_resolved
        colors = self.colors()
        self._app.setStyleSheet(generate_qss(colors))
        if changed:
            self.theme_changed.emit(self._resolved)

    def _check_system_theme(self) -> None:
        if self._mode == ThemeMode.SYSTEM:
            self._apply()

    def initialize(self) -> None:
        """Call once after QApplication is created."""
        self._apply()
        if self._mode == ThemeMode.SYSTEM:
            self._poll_timer.start()
