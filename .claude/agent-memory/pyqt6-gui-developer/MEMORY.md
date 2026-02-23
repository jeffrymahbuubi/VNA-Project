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
