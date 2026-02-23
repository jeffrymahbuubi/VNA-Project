# Codebase Explorer Memory

## Key Architectural Facts

### MVP File Locations
- Main entry: `code/LibreVNA-dev/gui/7_realtime_vna_plotter_mvp.py`
- Model: `gui/mvp/model.py` — pure Python, no Qt, dataclasses
- View: `gui/mvp/view.py` — PySide6, pyqtgraph PlotWidget replaces QLabel placeholder
- Presenter: `gui/mvp/presenter.py` — state machine, two QThread workers
- Backend adapter: `gui/mvp/backend_wrapper.py` — wraps ContinuousModeSweep for GUI
- Backend logic: `gui/mvp/vna_backend.py` — BaseVNASweep, ContinuousModeSweep (extracted from script 6)
- SCPI wrapper: `gui/mvp/libreVNA.py` (also at scripts/libreVNA.py — keep in sync)

### Presenter State Machine (no enum — booleans only)
- `_collecting: bool` + `_worker: Optional[VNASweepWorker]`
- INITIALIZING → READY: DeviceProbeWorker.serial_detected → _on_serial_detected (line 333)
- READY → COLLECTING: button click → _on_collect_data_requested (line 428)
- COLLECTING → READY: worker.all_completed → _on_all_completed (line 674) + re-probe

### Button Enable Logic (presenter.py line 754)
`ready = device.connected AND cal.loaded AND config.is_valid() AND NOT collecting`

### Streaming Data Path (thread boundary)
TCP thread (libreVNA.__live_thread) → _callback (vna_backend) → gui_aware_callback (backend_wrapper)
→ sweep_completed.emit() [Qt marshals to GUI thread] → _on_sweep_completed (presenter)
→ view.update_plot() → plot_data_item.setData()

### DeviceProbeWorker (startup only)
- Only sends *IDN? and DEV:CONN? — NO sweeping, NO cal loading, NO streaming
- Starts GUI subprocess if SCPI port 19542 not reachable; stores handle in presenter._gui_process
- After probe: GUI subprocess stays alive but idle on port 19542

### Collect Data — Key Side Effects
1. Kills probe's GUI subprocess (_stop_probe_gui_process, line 436)
2. VNASweepWorker cold-starts a NEW GUI subprocess (5-30s in start_lifecycle)
3. stop_lifecycle() in finally block TERMINATES the GUI subprocess
4. After completion, _start_device_probe() re-launches everything from scratch

### Preview Before Collect — Gap Analysis
Gap exists because pre_loop_reset() (which calls add_live_callback) is ONLY called
inside VNASweepWorker.run(). Nothing registers port 19001 during probe phase.
Integration point to add preview: _on_serial_detected() line 363 (after button enable).

### Known Bug: libreVNA.py line 148 (FIXED in gui/mvp copy)
Original bug: `len(self.live_callbacks)` should be `len(self.live_callbacks[port])`
Status: FIXED in gui/mvp/libreVNA.py line 179 (uses port-specific list)

### Calibration File Handling
- Stored as filename only (not full path) in model.calibration.file_path
- Backend resolves against _MODULE_DIR (gui/mvp/) where .cal files are colocated
- SCPI command receives filename only to avoid Windows paths with spaces

See `mvp-architecture.md` for detailed component diagrams.
