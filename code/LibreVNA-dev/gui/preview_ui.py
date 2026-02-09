#!/usr/bin/env python3
"""
Preview script for LibreVNA_GUI_v_1_0.ui

Loads the .ui file at runtime using PyQt6.uic.loadUi() and displays it.
All named widgets from the .ui file become attributes on the MainWindow instance.

Usage:
    uv run python preview_ui.py
    uv run python preview_ui.py --ui-file path/to/other.ui

Run from the gui/ directory so that relative image paths (images/WTMH.png) resolve correctly.
"""

import sys
import os
import argparse
from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import Qt


class MainWindow(QtWidgets.QMainWindow):
    """Main window that loads its layout from a .ui file at runtime."""

    def __init__(self, ui_file_path: str):
        super().__init__()

        # Load the .ui file -- all widgets become self.<objectName>
        uic.loadUi(ui_file_path, self)

        # Set window title to something descriptive
        self.setWindowTitle("LibreVNA GUI - Preview")

        # Connect the "Collect Data" button to a demo slot
        if hasattr(self, "pushButton"):
            self.pushButton.clicked.connect(self.on_collect_data_clicked)

        # Print all widgets found in the .ui for reference
        print("--- Widgets loaded from .ui file ---")
        for name, widget in self.__dict__.items():
            if isinstance(widget, QtWidgets.QWidget):
                print(f"  {name}: {type(widget).__name__}")
        print("------------------------------------")

    def on_collect_data_clicked(self):
        """Demo slot for the Collect Data button."""
        fields = {
            "Start Frequency": getattr(self, "startFrequencyLineEdit", None),
            "Center Frequency": getattr(self, "centerFrequencyLineEdit", None),
            "Stop Frequency": getattr(self, "stopFrequencyLineEdit", None),
            "Span": getattr(self, "spanFrequencyLineEdit", None),
            "No. of Sweeps": getattr(self, "numberOfSweepLineEdit", None),
            "Level": getattr(self, "levelLineEdit", None),
            "Points": getattr(self, "pointsLineEdit", None),
            "IF BW": getattr(self, "ifbwFrequencyLineEdit", None),
        }

        print("\n--- Collect Data clicked ---")
        for label, widget in fields.items():
            value = widget.text() if widget else "(not found)"
            print(f"  {label}: {value}")
        print("----------------------------\n")

        # Show a status bar message
        self.statusbar.showMessage("Collect Data pressed!", 3000)


def main():
    parser = argparse.ArgumentParser(description="Preview a .ui file with PyQt6")
    parser.add_argument(
        "--ui-file",
        default=None,
        help="Path to the .ui file. Defaults to LibreVNA_GUI_v_1_0.ui in the same directory.",
    )
    args = parser.parse_args()

    # Determine .ui file path
    if args.ui_file:
        ui_path = os.path.abspath(args.ui_file)
    else:
        # Default: look for the .ui file next to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ui_path = os.path.join(script_dir, "LibreVNA_GUI_v_1_0.ui")

    if not os.path.isfile(ui_path):
        print(f"ERROR: .ui file not found at: {ui_path}")
        sys.exit(1)

    # Change working directory to the .ui file's directory so that
    # relative resource paths (e.g., images/WTMH.png) resolve correctly.
    ui_dir = os.path.dirname(ui_path)
    os.chdir(ui_dir)
    print(f"Loading .ui file: {ui_path}")
    print(f"Working directory: {ui_dir}")

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(ui_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
