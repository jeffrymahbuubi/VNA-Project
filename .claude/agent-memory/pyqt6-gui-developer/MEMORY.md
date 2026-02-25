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
- `VNAPreviewWorker.__init__` takes `cal_file_path` + `ifbw_hz` (no freq/points args)

### ifbw_live Configuration (2026-02-24)
- `SweepConfig.ifbw_live` (int, default 50000 Hz) controls IFBW for live-preview sweep
- Parsed from `configurations.ifbw_live` in `sweep_config.yaml`
- Passed to `VNAPreviewWorker(ifbw_hz=self.model.config.ifbw_live)` at instantiation
- Worker sends `:VNA:ACQ:IFBW {self.ifbw_hz}` SCPI in `run()` after freq config block
- Data-collection path (VNASweepWorker) is NOT affected -- it uses its own IFBW via ContinuousModeSweep

## Monitor Mode Feature (2026-02-25)
- Two radio buttons in Mode Configuration box: "Device Sanity Check" / "Continuous Monitoring"
- `view.mode_changed` Signal(str): emits "sanity_check" or "continuous_monitoring"
- `_on_collect_data_requested()` dispatches to `_start_sanity_check_mode()` or `_start_monitor_mode()`
- `VNAMonitorWorker(QThread)` in presenter.py: warmup -> record -> export CSV
- Worker signals: lifecycle_started, warmup_completed(float), monitor_point(object), monitor_saved(str), error_occurred(str)
- Uses `GUIVNAMonitorAdapter` from backend_wrapper.py for SCPI lifecycle
- Button shows "Stop Monitoring" (orange) during monitor; user clicks to stop -> CSV export -> re-probe
- `_stop_monitor_worker()` disconnects signals, calls `.stop()`, waits 10s, force-terminates if needed
- View frequency display: MHz in UI, Hz in model/backend (populate: Hz/1e6, read: float*1e6)
- `read_sweep_config()` returns `mode`, `monitor_duration_s`, `log_interval_ms` -- popped before SweepConfig
- `MonitorConfig.from_dict(yaml_data)` parses `target.monitor` section of sweep_config.yaml
- `_update_collect_button_state()` skips when `_monitoring=True` (button managed by set_monitoring_state)

### Monitor Mode Live-Preview Fix (2026-02-26)
- **Problem**: S11 plot froze during Monitor recording because VNAPreviewWorker was stopped and VNAMonitorWorker's streaming callback only extracted scalar data (min-freq), never updating the plot.
- **Fix**: Added `sweep_preview = Signal(list, list)` and `elapsed_tick = Signal(float)` to `VNAMonitorWorker`.
- In `backend_wrapper.py`, `GUIVNAMonitorAdapter.start_recording()` gained `preview_callback` param. Inside `_monitor_cb`, after converting S11 to dB, calls `preview_callback(freqs, s11_db)` on every complete sweep.
- Preview callback emits `sweep_preview` signal -> presenter `_on_monitor_sweep_preview()` -> `view.update_plot()`.
- Elapsed tick emits every 0.25s from poll loop -> presenter `_on_monitor_elapsed()` -> `view.set_monitor_elapsed(elapsed_s, count)`.
- `view.set_monitor_elapsed()` shows "Monitor running -- elapsed: Xm Ys | N points captured" in status bar.
- `_on_monitor_point()` simplified to only update model (status display moved to elapsed_tick handler).
- Both new signals must be disconnected in `_stop_monitor_worker()` to prevent stale callbacks.

## Save Data Folder Feature (2026-02-26)
- Default save location changed from `code/LibreVNA-dev/data/` to `code/LibreVNA-dev/gui/data/` (one level up from `_MODULE_DIR` instead of two)
- Three default-path sites changed: `vna_backend.py` export_dataflux_csv (line 147), save_csv_bundle (line 735), `backend_wrapper.py` save_results (line 678)
- `VNADataModel.save_data_folder: Optional[str] = None` -- None means use default
- `QSettings("LibreVNA", "VNAPlotter")` key `"save_data_folder"` persists across app restarts
- View: `show_save_folder_dialog()`, `persist_save_folder()`, `get_persisted_save_folder()`, `show_save_folder_label()`
- Presenter: `_on_save_data_folder_requested()` slot, restores from QSettings in `_on_startup()`
- Workers: `VNASweepWorker` and `VNAMonitorWorker` accept `base_output_dir` param at construction
- Thread path: Presenter reads `model.save_data_folder` -> passes to worker constructor -> worker passes to adapter methods
- `backend_wrapper.py` `save_results()` gained `base_output_dir` param; `stop_recording()` gained `output_dir` param
- When custom folder set, dated YYYYMMDD subdir is created inside it (same pattern as default)

## Key Constants (vna_backend.py)
- SCPI_HOST="localhost", SCPI_PORT=19542, STREAMING_PORT=19001
- GUI_START_TIMEOUT_S=30.0, CONTINUOUS_TIMEOUT_S=300

## Axis Setup Dialog Feature (2026-02-24)
- `_VNAPlotWidget(pg.PlotWidget)` subclass replaces pyqtgraph built-in context menu
- Disable pyqtgraph menu: `self.getViewBox().setMenuEnabled(False)` in `__init__`
- Monkey-patch callback: `self.plot_widget._on_axis_setup = self._open_axis_setup_dialog`
- `AxisSetupDialog(QDialog)`: two QGroupBox columns (Y axis, X axis), OK/Cancel
- X values: displayed in MHz, stored internally in Hz (multiply/divide by 1e6)
- Auto checkboxes disable spinboxes via `toggled` signal
- `_axis_state` dict on VNAMainWindow stores current axis config
- `_apply_axis_settings()` sets Y range, Y ticks, X range/auto, X ticks
- `_nice_step()` picks "nice" round tick spacing (1/2/5/10 multipliers)
- `_frange()` generates inclusive float ranges for tick positions
- `update_plot()` respects `x_auto_range` setting (does not force auto-range when manual)
