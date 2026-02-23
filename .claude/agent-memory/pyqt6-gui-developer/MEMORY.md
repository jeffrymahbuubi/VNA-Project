# PyQt6 GUI Developer Memory

## MVP Architecture Patterns

### Device Connection Lifecycle Bug (Fixed 2026-02-23)
- `VNASweepWorker` terminates its GUI subprocess in `finally` block via `adapter.stop_lifecycle()`
- This means `device.connected` must be set to `False` after collection (SCPI connection is gone)
- **Key insight:** After collection completes, must re-probe the device via `_start_device_probe()` so that `device.connected` gets restored to `True` and the Collect Data button re-enables
- Same applies to the error handler `_on_error()` -- always re-probe after collection ends
- The `_start_device_probe()` method is idempotent (safe to call if probe already running)
- The probe worker updates `device.connected = True` via `_on_serial_detected()` signal, which triggers `_update_collect_button_state()`

### Button State Machine
- `_update_collect_button_state()` requires ALL conditions: `device.connected AND cal.loaded AND config.is_valid() AND NOT collecting`
- Any state transition that changes these conditions must call `_update_collect_button_state()` or trigger the probe which calls it on completion

## File Locations
- Presenter: `code/LibreVNA-dev/gui/mvp/presenter.py`
- Model: `code/LibreVNA-dev/gui/mvp/model.py`
- View: `code/LibreVNA-dev/gui/mvp/view.py`
- Backend wrapper: `code/LibreVNA-dev/gui/mvp/backend_wrapper.py`
- Entry point: `code/LibreVNA-dev/gui/7_realtime_vna_plotter_mvp.py`

## Project Uses PySide6 (not PyQt6)
Despite the agent name, this project uses PySide6. Import `Signal`, `Slot` from `PySide6.QtCore`.

## Live Preview Feature (2026-02-24)
- `VNAPreviewWorker` (QThread) in presenter.py: oscilloscope-style continuous sweep
- Starts automatically after device probe succeeds via `_on_serial_detected()` -> `_start_preview()`
- Reuses existing GUI subprocess from probe phase (no new subprocess spawned)
- Directly uses `libreVNA.py`: connect SCPI port 19542, load cal, `add_live_callback(19001, cb)`, `ACQ:RUN`
- Handles streaming server enable (APPLYPREFERENCES kills GUI -> auto-restart + reconnect)
- `_recording` flag in presenter guards `model.add_sweep_data()` -- preview updates plot only
- `_previewing` flag + `_preview_worker` reference track preview state
- Flow: probe -> `_on_serial_detected` -> `_start_preview` -> `_on_preview_started` -> blue-accent button
- On "Collect Data": `_stop_preview_worker()` -> stop probe GUI -> start `VNASweepWorker`
- After collection: `_on_all_completed` -> re-probe -> auto-starts preview again
- View method `set_preview_state(True)` shows blue border accent on green button

### Live Preview Bug Fix (2026-02-24) -- 3 Root Causes
1. **Frequency guard silently exited** `_start_preview()` when `config.start_frequency == 0`. Fix: removed guard; worker queries SCPI for freq range after loading cal (`SENS:FREQ:START?`, `SENS:FREQ:STOP?`, `SENS:SWE:POIN?`).
2. **`probe_device_serial()` leaked SCPI socket** causing race with preview worker. Fix: added explicit `vna.close()` in `backend_wrapper.py` before return.
3. **Test-connect socket drained early streaming data**. Fix: removed socket test; `add_live_callback()` directly, catch `ConnectionRefusedError` for streaming enable path.
- `VNAPreviewWorker.__init__` now takes only `cal_file_path` (no freq/points args)

## Key Constants (vna_backend.py)
- SCPI_HOST="localhost", SCPI_PORT=19542, STREAMING_PORT=19001
- GUI_START_TIMEOUT_S=30.0, CONTINUOUS_TIMEOUT_S=300
