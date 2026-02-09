# PyQt6 GUI Developer - Agent Memory

## Environment Setup
- PyQt6 installed via `uv run pip install PyQt6` (v6.10.2, PyQt6-Qt6 v6.10.2, pyqt6-sip v13.11.0)
- pyuic6 installed at `C:\Users\LENOVO X1E\AppData\Roaming\Python\Python310\Scripts` (not on PATH)
- Offscreen rendering works: `os.environ['QT_QPA_PLATFORM'] = 'offscreen'`

## Project .ui Files
- Custom GUI: `code/LibreVNA-dev/gui/LibreVNA_GUI_v_1_0.ui` (QMainWindow, 1280x720)
  - Key widgets: startFrequencyLineEdit, stopFrequencyLineEdit, centerFrequencyLineEdit, spanFrequencyLineEdit, numberOfSweepLineEdit, levelLineEdit, pointsLineEdit, ifbwFrequencyLineEdit, pushButton ("Collect Data")
  - Images dir: `code/LibreVNA-dev/gui/images/` (WTMH.png logo, placeholder-s11.png)
  - Must `os.chdir()` to gui/ dir for relative image paths to resolve
- LibreVNA-source has 60+ .ui files in `code/LibreVNA-source/Software/PC_Application/LibreVNA-GUI/`

## Loading .ui Files in PyQt6
- Runtime: `uic.loadUi(ui_path, self)` -- widgets become `self.<objectName>` attributes
- Compiled: `pyuic6 file.ui -o ui_file.py` then `from ui_file import Ui_MainWindow`
- Runtime approach is better for rapid iteration; compiled is better for IDE auto-complete
- Preview script created at: `code/LibreVNA-dev/gui/preview_ui.py`

## Key Patterns
- See [patterns.md](patterns.md) for detailed PyQt6 patterns (to be created as needed)
