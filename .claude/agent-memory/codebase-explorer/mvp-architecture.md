# MVP Architecture — Detailed Notes

## File: gui/mvp/presenter.py

### State Variables
- Line 176: `self._worker: Optional[VNASweepWorker] = None`
- Line 177: `self._collecting = False`
- Line 180: `self._probe_worker: Optional[DeviceProbeWorker] = None`
- Line 181: `self._gui_process = None` — probe's GUI subprocess handle

### Signal Wiring (_connect_view_signals, lines 193-200)
- view.collect_data_requested → _on_collect_data_requested
- view.load_calibration_requested → _on_load_calibration_requested
- view.load_config_requested → _on_load_config_requested
- view.connect_device_requested → _on_connect_device_requested
- view.config_changed → _on_config_changed
- view.window_closing → _on_window_closing

### Worker Signal Wiring (inside _on_collect_data_requested, lines 483-487)
- worker.lifecycle_started → _on_lifecycle_started
- worker.sweep_completed → _on_sweep_completed
- worker.ifbw_completed → _on_ifbw_completed
- worker.all_completed → _on_all_completed
- worker.error_occurred → _on_error

### Key Slot: _on_sweep_completed (line 624)
```python
def _on_sweep_completed(self, sweep_idx, ifbw_hz, freq, s11_db):
    self.model.add_sweep_data(sweep_idx, ifbw_hz, freq, s11_db)  # line 639
    self.view.update_plot(freq, s11_db)                            # line 642
```
This is the ONLY place view.update_plot is called. If preview data needs to update
the plot, it must also call this (or equivalent) on the GUI thread.

### Re-probe After Collection (line 709 in _on_all_completed)
stop_lifecycle() kills GUI subprocess → _start_device_probe() restarts GUI → probe
stores new handle in self._gui_process → _on_serial_detected enables button again.
Full cold-start cycle every time collection completes.

## File: gui/mvp/backend_wrapper.py

### GUIVNASweepAdapter.start_lifecycle() sequence (line 279)
1. start_gui() — Popen(LibreVNA-GUI.exe --port 19542 --no-gui), poll until port open
2. connect_and_verify() — libreVNA(host, port), query *IDN? and DEV:CONN?
3. enable_streaming_server() — test port 19001; if closed, send DEV:PREF + APPLYPREFERENCES
   NOTE: APPLYPREFERENCES terminates the GUI; must restart (lines 313-317)
4. load_calibration() — :VNA:CAL:LOAD? filename
5. _install_callback_hook_once() — monkey-patches _make_callback ONCE
6. pre_loop_reset() — ACQ:STOP + add_live_callback(19001, ...)

### _install_callback_hook_once() (line 382)
Critical method: wraps _make_callback so streaming callback ALSO emits to GUI.
Must be called BEFORE pre_loop_reset() (which calls _make_callback internally).
Reads self._gui_callback per-sweep — allows updating GUI callback per IFBW
without re-patching. Thread-safe because GUI callback emits Qt signal.

### mutable GUI callback pattern (line 245)
`self._gui_callback` is set to None initially, then updated per-IFBW by
run_single_ifbw_sweep(). The streaming closure reads it at call time, not at
registration time. This decouples the streaming infrastructure from the GUI.

## File: gui/mvp/vna_backend.py

### ContinuousModeSweep._continuous_sweep_loop() (line 1055)
Per-IFBW sequence:
1. ACQ:STOP (line 1086)
2. sleep(0.1) — drain buffered points (line 1090)
3. _state_holder[0] = new _SweepState (line 1094) — atomic under GIL
4. ACQ:SINGLE FALSE (line 1099)
5. ACQ:RUN (line 1103)
6. done_event.wait(CONTINUOUS_TIMEOUT_S=300) (line 1110)
7. ACQ:STOP (line 1124)

### _SweepState inner class (line 889)
Threading: Uses threading.Lock() for data access, threading.Event() for completion.
Fields: num_points, num_sweeps, sweep_count, current_s11, all_s11_complex, all_timestamps.
done_event is set when sweep_count >= num_sweeps (line 1009).

### pre_loop_reset / post_loop_teardown (lines 1017, 1040)
Streaming callback registered ONCE in pre_loop_reset to avoid the libreVNA.py bug
(double remove/add can leave the thread in an inconsistent state).
post_loop_teardown sends ACQ:STOP, ACQ:SINGLE TRUE, and removes callback.

## File: gui/mvp/libreVNA.py

### add_live_callback (line 156)
- Creates TCP socket to port (19001 for calibrated data)
- Spawns __live_thread (daemon-like — runs while live_callbacks[port] is non-empty)
- Thread calls cb(data) for each JSON line (line 204)

### __live_thread (line 183)
- Loop condition: `while len(self.live_callbacks[port]) > 0`
- Catches all exceptions (line 206) — timeouts silently ignored
- Converts VNA measurements from split real/imag to Python complex (lines 193-203)

### Known Bug Status (line 179 in gui copy)
Original scripts/libreVNA.py line 148 had: `len(self.live_callbacks)` (wrong — counts ports)
gui/mvp/libreVNA.py line 179 has: `len(self.live_callbacks[port])` (correct — counts callbacks)
If fixing scripts copy, change line 148 to match.

## File: gui/mvp/view.py

### Plot Setup (_setup_plot_widget, line 76)
- Replaces s11TracePlot QLabel with pg.PlotWidget
- Creates self.plot_data_item = plot_widget.plot([], [], pen=yellow, width=2)
- Y-axis auto-range enabled with 5% padding (lines 101-103)

### update_plot (line 231)
```python
self.plot_data_item.setData(freq_hz, s11_db)
self.plot_widget.getViewBox().enableAutoRange(YAxis, enable=True)
```
Re-enables Y auto-range on every update (recovers from manual zoom).

### set_collecting_state(collecting=True) (line 172)
- collecting=True: red button, blinking (600ms timer), disabled
- collecting=False: green button, enabled, blink timer stopped

## File: gui/mvp/model.py

### SweepConfig.from_dict() (line 80)
Sets start/stop/num_points to 0 — only populated by update_from_cal_file().
is_valid() returns False until cal file applied (enforces cal as source of truth).

### VNADataModel._latest_freq / _latest_s11 (line 166)
Cache for most recent sweep — updated by add_sweep_data() (line 211).
Accessed via get_latest_sweep() for real-time display.

## Integration Points for Preview Before Collect

### Where to Start Preview
File: presenter.py, function: _on_serial_detected(), after line 363
Needs: New VNAPreviewWorker that runs an infinite sweep loop
Dependency: Must reuse the GUI subprocess already started by probe_device_serial()
           (stored in self._gui_process) rather than starting a new one

### Where to Stop Preview and Start Collect
File: presenter.py, function: _on_collect_data_requested(), around line 436
Currently: kills probe GUI process (_stop_probe_gui_process)
Needs: Stop preview worker cleanly, then either reuse or restart GUI for collect

### Where to Resume Preview After Collect
File: presenter.py, function: _on_all_completed(), after line 709
Currently: _start_device_probe() already re-launches everything
If preview auto-starts from _on_serial_detected(), the resume is automatic

### Streaming Data to Plot (Preview Mode)
The existing _on_sweep_completed slot (line 624) already does the right thing.
For preview, skip model.add_sweep_data() to avoid accumulating non-recording data.
Or introduce a flag: self._recording = False during preview, True during collect.
