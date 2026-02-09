# PyQt6/PySide6 GUI Developer - Agent Memory

## Framework Decision: PySide6 (not PyQt6)
- The project uses **PySide6** (auto-generated UI from pyside6-uic v6.10.2)
- Both PySide6 6.10.2 and PyQt6 6.4.2 are installed; pyqtgraph auto-detects PySide6
- Key API: `pyqtSignal` -> `Signal`, `pyqtSlot` -> `Slot` (from PySide6.QtCore)
- No `uic.loadUi()` for PySide6; use compiled Ui_MainWindow via multiple inheritance

## PySide6 Signal Gotchas
- `QLineEdit.textChanged` emits text arg; connecting to zero-arg Signal needs lambda
- Pattern: `widget.textChanged.connect(lambda _text: self.config_changed.emit())`
- PySide6 is stricter than PyQt6 about argument count mismatches

## Auto-generated Files (DO NOT edit except import fix)
- `mvp/main_window.py` - pyside6-uic output; changed `import resources_rc` -> `from . import resources_rc`
- `mvp/resources_rc.py` - pyside6-rcc output; imports `from PySide6 import QtCore`

## MVP Architecture (Tested Working 2026-02-10)
- Model: Pure Python, no Qt deps (`mvp/model.py`)
- View: PySide6 + Ui_MainWindow multiple inheritance (`mvp/view.py`)
- Presenter: Signal wiring, QThread worker (`mvp/presenter.py`)
- Entry: `7_realtime_vna_plotter_mvp.py`
- Auto-detects `.cal` and `sweep_config.yaml` in `gui/` on startup

## Widget Name Mapping (.ui -> model)
- start_frequency -> startFrequencyLineEdit
- stop_frequency -> stopFrequencyLineEdit
- center_frequency (computed) -> centerFrequencyLineEdit
- span_frequency (computed) -> spanFrequencyLineEdit
- num_points -> pointsLineEdit
- stim_lvl_dbm -> levelLineEdit
- num_sweeps -> numberOfSweepLineEdit
- ifbw_values -> ifbwFrequencyLineEdit (comma-separated)
- avg_count -> NO widget (default=1)

## Running the GUI
```
cd code/LibreVNA-dev/gui
uv run python 7_realtime_vna_plotter_mvp.py
```

## Threading: Device Detection on Startup
- `DeviceProbeWorker(QThread)` runs `probe_device_serial()` from backend_wrapper.py
- Checks if SCPI server running (port 19542), starts GUI subprocess if needed
- Queries `*IDN?` (serial from 3rd comma field) and `:DEV:CONN?` (authoritative serial)
- Emits `serial_detected` signal back to Presenter -> updates menu text
- **Port conflict risk**: Probe's GUI subprocess and VNASweepWorker both use port 19542
  - Presenter calls `_stop_probe_gui_process()` before starting sweep worker
- Menu text format: `"{serial} (LibreVNA/USB)"` (e.g. "206830535532 (LibreVNA/USB)")

## MVP Discipline: Presenter Should Not Touch Widgets Directly
- View display methods should manage their own widget states (enabled/disabled/text)
- Example: `set_device_serial()` both sets text AND re-enables the action
- Presenter calls View methods only, never `self.view.some_widget.method()`

## Key Patterns
- See [patterns.md](patterns.md) for detailed patterns (to be created as needed)
