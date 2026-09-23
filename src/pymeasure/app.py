"""Entry point: build the application, apply the theme, show the window."""

import sys

from PySide6.QtWidgets import QApplication

from .gui.theme import apply_theme
from .gui.window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PyMeasure")
    app.setApplicationVersion("2.0")
    # Fusion first: it is the one style that honours a palette identically on
    # every platform, so the theme applied next lands the same way everywhere.
    app.setStyle("Fusion")
    apply_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
