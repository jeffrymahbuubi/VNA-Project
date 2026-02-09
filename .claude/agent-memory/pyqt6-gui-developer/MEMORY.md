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
- Backend: `mvp/vna_backend.py` (standalone, extracted from script 6)
- Backend adapter: `mvp/backend_wrapper.py` (GUI-friendly lifecycle steps)
- SCPI wrapper: `mvp/libreVNA.py` (local copy, line 148 bug fixed)
- Entry: `7_realtime_vna_plotter_mvp.py`
- Auto-detects `.cal` in `gui/mvp/` and `sweep_config.yaml` in `gui/` on startup

## Calibration File Path Strategy (Fixed 2026-02-10)
- `.cal` file lives in `gui/mvp/` (colocated with backend scripts)
- Presenter stores just the FILENAME (not full path) in model.calibration.file_path
- `vna_backend.py` `load_calibration()` resolves filename relative to `_MODULE_DIR` for existence check
- SCPI `:VNA:CAL:LOAD?` receives ONLY the filename (e.g. `SOLT_1_2_43G-2_45G_300pt.cal`)
- GUI subprocess CWD is set to `_MODULE_DIR` (`gui/mvp/`) so filename resolves correctly
- **Why:** Full Windows paths with spaces (e.g. `D:\AUNUUN JEFFRY MAHBUUBI\...`) break SCPI parsing

## Backend Standalone Deployment (Refactored 2026-02-10)
- `backend_wrapper.py` imports from local `vna_backend` (NOT dynamic import from scripts/)
- Key imports: `ContinuousModeSweep, SweepResult, SCPI_HOST, SCPI_PORT, GUI_START_TIMEOUT_S, GUI_BINARY, _MODULE_DIR`
- GUI binary path built from `_MODULE_DIR`: `../../tools/LibreVNA-GUI/release/LibreVNA-GUI.exe` (Windows)
- No dependency on `scripts/` directory -- GUI is deployment-independent

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

## Cleanup/Shutdown Pattern (Implemented 2026-02-10)
- View emits `window_closing` signal in `closeEvent()` (passive -- no business logic)
- Presenter `_on_window_closing()` -> `cleanup()` orchestrates all teardown
- Cleanup order: (1) stop probe worker, (2) stop sweep worker + adapter, (3) kill probe GUI subprocess
- `libreVNA.close()` explicitly stops streaming threads (clears callbacks -> thread loop exits) + closes SCPI socket
- `GUIVNASweepAdapter.stop_lifecycle()` calls `vna.close()` then `stop_gui()` then deletes temp config
- Signal disconnection before thread stop prevents stale callbacks into destroyed View
- QThread.wait(timeout_ms) with terminate() fallback for threads doing blocking I/O
- Logging via `logging.getLogger(__name__)` in presenter; configured in entry point

## Key Patterns
- See [patterns.md](patterns.md) for detailed patterns (to be created as needed)
