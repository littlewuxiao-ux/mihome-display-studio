"""MiHome Display Studio entry point."""
from __future__ import annotations

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("米家中枢屏幕工作台")
    window = MainWindow(Path.cwd())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
