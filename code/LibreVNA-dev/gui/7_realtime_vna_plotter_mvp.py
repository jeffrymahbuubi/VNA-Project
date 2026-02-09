#!/usr/bin/env python3
"""
7_realtime_vna_plotter_mvp.py
=============================
PySide6 GUI for LibreVNA real-time S11 trace visualization.

Architecture: MVP (Model-View-Presenter) pattern
  - Model (mvp/model.py): Pure Python business logic, no GUI dependencies
  - View (mvp/view.py): PySide6 UI using compiled Ui_MainWindow, display-only
  - Presenter (mvp/presenter.py): Mediates Model <-> View, manages worker thread

Backend: Reuses script 6 (ContinuousModeSweep) via adapter wrapper
  - All SCPI operations run in QThread worker to keep GUI responsive
  - Real-time plot updates via Qt signals (thread-safe)

User Workflow:
  1. Launch GUI -> auto-detects .cal and .yaml in gui/ directory
  2. GUI populates device info and configuration widgets
  3. User edits config as needed
  4. User clicks "Collect Data" -> button turns red with animation
  5. Real-time S11 plot updates during collection
  6. Auto-saves to data/YYYYMMDD/gui_sweep_collection_YYYYMMDD_HHMMSS.xlsx

Usage:
    cd code/LibreVNA-dev/gui
    uv run python 7_realtime_vna_plotter_mvp.py

Requirements:
    - LibreVNA device connected via USB (for data collection)
    - Calibration file: gui/SOLT_1_2_43G-2_45G_300pt.cal
    - Config file: gui/sweep_config.yaml (optional, uses defaults if missing)

Dependencies:
    - PySide6 >= 6.6.0
    - pyqtgraph >= 0.13.3
    - All script 6 dependencies (numpy, yaml, openpyxl, prettytable)
"""

import sys
import os
from pathlib import Path

# Change to gui/ directory for relative path resolution
GUI_DIR = Path(__file__).parent
os.chdir(GUI_DIR)

# Import Qt before other imports (required on some platforms)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Import MVP components
from mvp.model import VNADataModel
from mvp.view import VNAMainWindow
from mvp.presenter import VNAPresenter


def main():
    """
    Main entry point for LibreVNA real-time plotter GUI.

    Instantiates Model, View, Presenter in the standard MVP wiring pattern,
    then enters the Qt event loop.
    """
    # Enable high DPI scaling (for 4K monitors)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("LibreVNA Real-Time Plotter")
    app.setOrganizationName("LibreVNA")

    # Instantiate MVP components
    model = VNADataModel()
    view = VNAMainWindow()
    presenter = VNAPresenter(model, view)  # noqa: F841 (prevent GC)

    # Show window
    view.show()

    # Enter event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
