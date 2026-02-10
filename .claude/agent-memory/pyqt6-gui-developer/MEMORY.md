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

## Calibration File Path Strategy (Updated 2026-02-11)
- `.cal` files live in `gui/mvp/` (colocated with backend scripts)
- **Auto-detection:** `presenter._on_startup()` uses `mvp_dir.glob("*.cal")` sorted by mtime (most recent first)
  - Previously hardcoded `SOLT_1_2_43G-2_45G_300pt.cal` -- caused new cal files to be ignored
  - Now discovers any `.cal` file; picks most recently modified
  - If multiple found, status bar shows all filenames
- **Manual loading:** `_on_load_calibration_requested()` copies external files into `gui/mvp/`
  - Uses `shutil.copy2()` if selected file is NOT already in gui/mvp/
  - Always stores just the filename (never full path) in model
- Presenter stores just the FILENAME (not full path) in model.calibration.file_path
- **Both** `parse_calibration_file()` and `load_calibration()` in `vna_backend.py` resolve relative paths against `_MODULE_DIR`
  - Fixed 2026-02-11: `parse_calibration_file()` previously did only `os.path.normpath()` (no `_MODULE_DIR` fallback)
  - Now uses identical `os.path.isabs()` / `os.path.join(_MODULE_DIR, ...)` pattern as `load_calibration()`
- SCPI `:VNA:CAL:LOAD?` receives ONLY the filename (e.g. `SOLT_1_200M-250M_801pt.cal`)
- GUI subprocess CWD is set to `_MODULE_DIR` (`gui/mvp/`) so filename resolves correctly
- **Why:** Full Windows paths with spaces (e.g. `D:\AUNUUN JEFFRY MAHBUUBI\...`) break SCPI parsing
- **sweep_config.yaml:** Must match the cal file frequency range (was 2.43-2.45GHz, updated to 200-250MHz)

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
- `GUIVNASweepAdapter.stop_lifecycle()` calls `post_loop_teardown()` -> `vna.close()` -> `stop_gui()` -> delete temp
- Signal disconnection before thread stop prevents stale callbacks into destroyed View
- QThread.wait(timeout_ms) with terminate() fallback for threads doing blocking I/O
- Logging via `logging.getLogger(__name__)` in presenter; configured in entry point

## Critical Bug Fix: Streaming Callback Not Registered (Fixed 2026-02-10)
**Root cause of BOTH infinite sweep loop AND missing plot updates.**

The `GUIVNASweepAdapter` was missing calls to `pre_loop_reset()` and `post_loop_teardown()`:
- `pre_loop_reset()` registers the TCP streaming callback via `vna.add_live_callback(19001, cb)`
- Without it, the callback created by `_make_callback()` was never connected to the TCP stream
- `done_event.wait(300)` would timeout because no streaming data arrived to increment sweep_count
- The GUI callback (for plot updates) was also never triggered because it was wired into the missing callback chain

**Fix (backend_wrapper.py):**
1. `start_lifecycle()` now calls `_install_callback_hook_once()` then `self.sweep.pre_loop_reset(self.vna)`
2. `stop_lifecycle()` now calls `self.sweep.post_loop_teardown(self.vna)` BEFORE closing connection
3. `_install_callback_hook_once()` replaces per-IFBW `_install_callback_hook()` -- avoids double-wrapping
4. Uses mutable `self._gui_callback` reference that's updated per-IFBW (no re-patching)
5. `enable_streaming_server()` restart case properly handled (stop old GUI -> restart -> reconnect)

**Lesson:** When extracting a monolithic `run()` method into lifecycle steps, ALL lifecycle hooks must be preserved. The adapter skipped `pre_loop_reset()` and `post_loop_teardown()` which were called in `BaseVNASweep.run()`.

## Button Blink Fix (2026-02-10)
- Old: `setVisible(True/False)` caused layout shifts and "button disappearing"
- New: Color alternation between bright red `rgb(239,68,68)` and dark red `rgb(185,28,28)`
- Timer interval: 600ms (from 500ms) for smoother visual pulse

## save_results() SCRIPT_DIR Bug (Fixed 2026-02-10)
- Old code referenced `SCRIPT_DIR` (from removed dynamic import) -- caused NameError
- Fixed to use `_MODULE_DIR` from vna_backend.py

## Key Patterns
- See [patterns.md](patterns.md) for detailed patterns (to be created as needed)
