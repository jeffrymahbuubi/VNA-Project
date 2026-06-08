"""e5063a_data_collector.py — entry point for the E5063A Data Collector GUI.

G-0 scaffold: launches the two-screen (Setup → Acquire) shell with a STUB backend
(no instrument required). Applies the global stylesheet once and shows the window.

Run from code/ :
    uv run python ena-dev/gui/e5063a_data_collector.py

With the qt-mcp probe (for agent-driven verification):
    $env:QT_MCP_PROBE=1; uv run python ena-dev/gui/e5063a_data_collector.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `mvp` importable whether run as a script or a module.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from mvp import theme as T
from mvp.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(T.STYLESHEET)
    if T.WTMH_ICO.exists():                       # G-14: WTMH window/taskbar icon
        app.setWindowIcon(QIcon(str(T.WTMH_ICO)))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
