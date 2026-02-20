"""Book2Audiobook — application entrypoint.

Initializes the QApplication, theme system, and main window.
"""
from __future__ import annotations

import logging
import sys
import warnings

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from book2audiobook.ui.main_window import MainWindow
from book2audiobook.ui.theme import ThemeManager, ThemeMode


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("phonemizer").setLevel(logging.ERROR)
    warnings.filterwarnings(
        "ignore",
        message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+",
    )


def main() -> int:
    configure_logging()

    # High-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # Application font
    font = QFont()
    # Use system UI fonts; Inter is preferred if installed, but not required
    font.setFamilies(["Inter", "-apple-system", "SF Pro Display", "Segoe UI", "Helvetica Neue", "sans-serif"])
    font.setPointSize(13)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # Application name for macOS menu bar
    app.setApplicationName("Book2Audiobook")
    app.setOrganizationName("Book2Audiobook")

    # Theme system
    theme_manager = ThemeManager(app)
    theme_manager.set_mode(ThemeMode.SYSTEM)
    theme_manager.initialize()

    # Main window
    window = MainWindow(theme_manager=theme_manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
