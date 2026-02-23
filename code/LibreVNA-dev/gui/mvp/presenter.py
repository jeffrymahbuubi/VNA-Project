"""
Presenter layer for LibreVNA GUI (MVP architecture).

Mediates between Model and View, handles state machine, and manages worker threads.
All backend operations (SCPI, sweeps) run in background QThreads to keep GUI responsive.

Worker threads:
  - DeviceProbeWorker: Lightweight startup device detection (queries serial)
  - VNAPreviewWorker: Continuous live sweep for oscilloscope-style preview
  - VNASweepWorker: Full sweep collection lifecycle (GUI + cal + sweeps + CSV export)
"""

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog
from pathlib import Path
import logging
import shutil
import threading
import time
import yaml
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

from .model import VNADataModel, SweepConfig
from .view import VNAMainWindow
from .backend_wrapper import (
    GUIVNASweepAdapter, probe_device_serial,
    _is_scpi_server_running, _start_gui_subprocess,
)
from .vna_backend import SCPI_HOST, SCPI_PORT, STREAMING_PORT, _MODULE_DIR
from .libreVNA import libreVNA


class DeviceProbeWorker(QThread):
    """
    Lightweight background worker for startup device detection.

    Connects to the LibreVNA-GUI SCPI server (starting the GUI subprocess
    if needed), queries the device serial number via *IDN? and DEV:CONN?,
    and emits the result back to the Presenter on the GUI thread.

    This runs as a separate thread so the GUI remains responsive during
    the potentially slow startup sequence (up to 30 seconds if the GUI
    subprocess needs to be launched).
    """

    # Signals emitted TO presenter (received on GUI thread via Qt signal/slot)
    serial_detected = Signal(dict)  # {'serial': str, 'idn': str, 'gui_process': ...}
    probe_failed = Signal(str)      # error message

    def run(self):
        """
        Execute device probe in background thread.

        Calls probe_device_serial() from the backend wrapper, which handles
        the full detection sequence: check SCPI server -> start GUI if needed
        -> connect -> query *IDN? -> query DEV:CONN?.
        """
        try:
            device_info = probe_device_serial()
            self.serial_detected.emit(device_info)
        except Exception as e:
            self.probe_failed.emit(str(e))


class VNAPreviewWorker(QThread):
    """
    Background worker for oscilloscope-style live preview.

    Connects to the already-running LibreVNA-GUI subprocess (started during
    device probe), loads calibration, registers a streaming callback on port
    19001, and runs continuous sweeps indefinitely until stopped.

    Unlike VNASweepWorker, this worker:
      - Reuses the existing GUI subprocess (does not spawn a new one)
      - Runs indefinitely (no sweep count target)
      - Does NOT save data to disk
      - Can be stopped gracefully via stop()

    Thread safety: The streaming callback runs on libreVNA's TCP background
    thread. It emits Qt signals which are delivered to the GUI thread via
    Qt's cross-thread signal/slot mechanism.
    """

    # Emitted after each sweep completes (same signature as VNASweepWorker)
    preview_sweep = Signal(object, object)  # (freq_hz ndarray, s11_db ndarray)
    preview_started = Signal()               # Preview streaming is active
    preview_error = Signal(str)              # Non-fatal error message
    gui_process_changed = Signal(object)     # New subprocess.Popen if GUI was restarted

    def __init__(self, cal_file_path: str):
        """
        Initialize preview worker.

        Args:
            cal_file_path: Calibration filename (resolved relative to _MODULE_DIR)
        """
        super().__init__()
        self.cal_file_path = cal_file_path

        # Populated via SCPI queries after connecting + loading calibration
        self.start_freq_hz: int = 0
        self.stop_freq_hz: int = 0
        self.num_points: int = 0

        self._cancel_event = threading.Event()
        self._vna: Optional[libreVNA] = None
        self._stream_callback = None

    def stop(self):
        """
        Request graceful shutdown of the preview loop.

        Sets the cancel event which causes the run() loop to exit.
        Call wait() after this to block until the thread finishes.
        """
        self._cancel_event.set()

    def run(self):
        """
        Main preview loop - runs in background thread.

        Sequence:
          1. Connect to SCPI server (already running from probe phase)
          2. Load calibration
          3. Check/enable streaming server on port 19001
          4. Register streaming callback
          5. Start continuous sweeps (ACQ:SINGLE FALSE + ACQ:RUN)
          6. Wait until cancel_event is set
          7. Cleanup: ACQ:STOP, remove callback, close connection
        """
        try:
            # Step 1: Connect to SCPI server
            try:
                self._vna = libreVNA(host=SCPI_HOST, port=SCPI_PORT)
            except Exception as exc:
                self.preview_error.emit(
                    f"Preview: cannot connect to SCPI server: {exc}"
                )
                return

            if self._cancel_event.is_set():
                return

            # Step 2: Load calibration
            try:
                import os
                cal_scpi_path = os.path.basename(self.cal_file_path)
                load_response = self._vna.query(
                    f":VNA:CAL:LOAD? {cal_scpi_path}"
                )
                if load_response != "TRUE":
                    self.preview_error.emit(
                        f"Preview: calibration load failed ({load_response})"
                    )
                    return
            except Exception as exc:
                self.preview_error.emit(
                    f"Preview: calibration load error: {exc}"
                )
                return

            if self._cancel_event.is_set():
                return

            # Step 2b: Read frequency range directly from the cal file JSON.
            # LibreVNA SCPI does not expose query forms of FREQuency:START/STOP
            # or ACQ:POINTS, so we parse the calibration data we already have.
            try:
                import json as _json
                _abs_cal = os.path.join(_MODULE_DIR, os.path.basename(self.cal_file_path))
                with open(_abs_cal, "r") as _f:
                    _cal = _json.load(_f)
                _points = _cal["measurements"][0]["data"]["points"]
                self.start_freq_hz = int(_points[0]["frequency"])
                self.stop_freq_hz = int(_points[-1]["frequency"])
                self.num_points = len(_points)
                logger.info(
                    "Preview cal parse: %.3f-%.3f GHz, %d pts",
                    self.start_freq_hz / 1e9,
                    self.stop_freq_hz / 1e9,
                    self.num_points,
                )
            except Exception as exc:
                self.preview_error.emit(
                    f"Preview: failed to read frequency range from cal file: {exc}"
                )
                return

            if self.num_points <= 0:
                self.preview_error.emit(
                    "Preview: cal file has zero measurement points"
                )
                return

            if self._cancel_event.is_set():
                return

            # Step 2c: Configure sweep parameters to match the calibration file.
            # Without this, ACQ:RUN may sweep with default/stale parameters
            # (wrong num_points or freq range), causing the streaming callback's
            # point_num boundary check to never fire.
            try:
                self._vna.cmd(":VNA:SWEEP FREQUENCY")
                self._vna.cmd(f":VNA:ACQ:POINTS {self.num_points}")
                self._vna.cmd(f":VNA:FREQuency:START {self.start_freq_hz}")
                self._vna.cmd(f":VNA:FREQuency:STOP {self.stop_freq_hz}")
            except Exception as exc:
                self.preview_error.emit(
                    f"Preview: failed to configure sweep parameters: {exc}"
                )
                return

            if self._cancel_event.is_set():
                return

            # Step 3 + 4: Register streaming callback on port 19001.
            # libreVNA.add_live_callback() raises a generic Exception (not
            # ConnectionRefusedError) when the streaming port is unreachable,
            # because it wraps the socket error internally.  Catch Exception.
            freq_hz = np.linspace(
                self.start_freq_hz, self.stop_freq_hz, self.num_points
            )
            current_sweep = []  # accumulates points for current sweep

            def _preview_callback(data):
                """Streaming callback - runs on libreVNA TCP thread."""
                if self._cancel_event.is_set():
                    return
                if "Z0" not in data:
                    return

                point_num = data["pointNum"]
                s11_complex = data["measurements"].get("S11", complex(0, 0))

                if point_num == 0:
                    current_sweep.clear()

                current_sweep.append(s11_complex)

                if point_num == self.num_points - 1:
                    if len(current_sweep) == self.num_points:
                        # Complete sweep - convert to dB and emit
                        s11_arr = np.array(current_sweep)
                        s11_db = 20 * np.log10(
                            np.maximum(np.abs(s11_arr), 1e-12)
                        )
                        # Emit signal (Qt handles thread marshalling)
                        self.preview_sweep.emit(freq_hz, s11_db)

            self._stream_callback = _preview_callback

            try:
                self._vna.add_live_callback(
                    STREAMING_PORT, self._stream_callback
                )
            except Exception:
                # Streaming server not enabled -- enable it now.
                # libreVNA.add_live_callback wraps socket errors in a generic
                # Exception, so we catch Exception (not ConnectionRefusedError).
                # This will kill the GUI subprocess (APPLYPREFERENCES restarts it).
                logger.info("Preview: enabling streaming server (will restart GUI)")
                try:
                    self._vna.cmd(
                        ":DEV:PREF StreamingServers.VNACalibratedData.enabled true",
                        check=False,
                    )
                    self._vna.cmd(":DEV:APPLYPREFERENCES", check=False)
                except Exception:
                    pass  # GUI may have died already

                # Wait for GUI to die
                time.sleep(2)

                # Close stale connection
                try:
                    self._vna.close()
                except Exception:
                    pass
                self._vna = None

                if self._cancel_event.is_set():
                    return

                # Restart GUI subprocess
                try:
                    new_proc = _start_gui_subprocess()
                    self.gui_process_changed.emit(new_proc)
                except Exception as exc:
                    self.preview_error.emit(
                        f"Preview: failed to restart GUI after enabling streaming: {exc}"
                    )
                    return

                if self._cancel_event.is_set():
                    return

                # Reconnect
                try:
                    self._vna = libreVNA(host=SCPI_HOST, port=SCPI_PORT)
                except Exception as exc:
                    self.preview_error.emit(
                        f"Preview: reconnect after streaming enable failed: {exc}"
                    )
                    return

                # Reload calibration
                try:
                    load_response = self._vna.query(
                        f":VNA:CAL:LOAD? {cal_scpi_path}"
                    )
                    if load_response != "TRUE":
                        self.preview_error.emit(
                            f"Preview: calibration reload failed ({load_response})"
                        )
                        return
                except Exception as exc:
                    self.preview_error.emit(
                        f"Preview: calibration reload error: {exc}"
                    )
                    return

                # Register callback on the now-enabled streaming port
                try:
                    self._vna.add_live_callback(
                        STREAMING_PORT, self._stream_callback
                    )
                except Exception as exc:
                    self.preview_error.emit(
                        f"Preview: streaming callback registration failed: {exc}"
                    )
                    return

            if self._cancel_event.is_set():
                return

            # Step 5: Configure and start continuous sweeps
            self._vna.cmd(":VNA:ACQ:STOP")
            self._vna.cmd(":VNA:ACQ:SINGLE FALSE")
            self._vna.cmd(":VNA:ACQ:RUN")

            # Signal that preview is active
            self.preview_started.emit()

            # Step 6: Wait until cancelled
            # Poll cancel_event with short timeout to stay responsive
            while not self._cancel_event.wait(timeout=0.25):
                pass

        except Exception as exc:
            import traceback
            self.preview_error.emit(
                f"Preview error: {exc}\n{traceback.format_exc()}"
            )

        finally:
            # Step 7: Cleanup
            self._cleanup()

    def _cleanup(self):
        """Stop acquisition and close connections."""
        if self._vna is not None:
            try:
                self._vna.cmd(":VNA:ACQ:STOP")
            except Exception:
                pass

            if self._stream_callback is not None:
                try:
                    self._vna.remove_live_callback(
                        STREAMING_PORT, self._stream_callback
                    )
                except Exception:
                    pass
                self._stream_callback = None

            try:
                self._vna.close()
            except Exception:
                pass
            self._vna = None


class VNASweepWorker(QThread):
    """
    Background worker thread for VNA sweep operations.

    Runs all backend operations (GUI subprocess, SCPI, streaming) off main thread
    to prevent GUI freezing. Communicates progress via Qt signals.
    """

    # Progress signals (emitted TO presenter on GUI thread)
    lifecycle_started = Signal(dict)  # Device info: {'serial': ..., 'idn': ...}
    sweep_completed = Signal(int, int, object, object)  # sweep_idx, ifbw_hz, freq, s11_db
    ifbw_completed = Signal(int, dict)  # ifbw_hz, metrics dict
    all_completed = Signal(str)  # output_directory_path (CSV bundle)
    error_occurred = Signal(str)  # error_message

    def __init__(self, config_dict: dict, calibration_file_path: str):
        """
        Initialize worker with sweep configuration.

        Args:
            config_dict: SweepConfig.to_dict() output
            calibration_file_path: Absolute path to .cal file
        """
        super().__init__()
        self.config = config_dict
        self.cal_file_path = calibration_file_path
        self.adapter: Optional[GUIVNASweepAdapter] = None

    def run(self):
        """
        Main worker loop - runs in background thread.

        Sequence:
          1. Start GUI + connect + load cal
          2. For each IFBW: configure + run sweeps (emit progress signals)
          3. Save CSV bundle
          4. Stop GUI subprocess
        """
        try:
            # Create adapter instance
            self.adapter = GUIVNASweepAdapter(self.config, self.cal_file_path)

            # Step 1: Start lifecycle (blocking ~5-10 seconds)
            device_info = self.adapter.start_lifecycle()
            self.lifecycle_started.emit(device_info)

            # Step 2: Loop through each IFBW value
            all_results = []
            for ifbw_hz in self.config['ifbw_values']:

                # Define callback for real-time sweep updates
                def sweep_callback(sweep_idx: int, freq: np.ndarray, s11_db: np.ndarray):
                    """Called after each sweep completes (from streaming thread)."""
                    # Emit signal to GUI thread (Qt handles thread marshalling)
                    self.sweep_completed.emit(sweep_idx, ifbw_hz, freq, s11_db)

                # Run all sweeps for this IFBW (blocking ~2-10 seconds per IFBW)
                result = self.adapter.run_single_ifbw_sweep(ifbw_hz, sweep_callback)

                # Extract metrics
                times_arr = np.array(result.sweep_times)
                metrics = {
                    'mean_time': float(np.mean(times_arr)),
                    'std_time': float(np.std(times_arr, ddof=1)) if len(times_arr) > 1 else 0.0,
                    'sweep_rate': 1.0 / np.mean(times_arr) if np.mean(times_arr) > 0 else 0.0,
                    'noise_floor': float(result.noise_floor),
                    'trace_jitter': float(result.trace_jitter),
                }

                self.ifbw_completed.emit(ifbw_hz, metrics)
                all_results.append(result)

            # Step 3: Save results to CSV bundle
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            custom_dirname = f"gui_sweep_collection_{timestamp}"
            output_dir = self.adapter.save_results(custom_dirname)

            self.all_completed.emit(output_dir)

        except Exception as e:
            # Emit error signal with full traceback
            import traceback
            error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error_occurred.emit(error_msg)

        finally:
            # Always stop GUI subprocess
            if self.adapter:
                self.adapter.stop_lifecycle()


class VNAPresenter(QObject):
    """
    Presenter - mediates between Model and View.

    Handles:
      - Auto-detection on startup (.cal and .yaml files)
      - User action signals from View
      - Worker thread lifecycle
      - Button enable/disable state machine
      - Thread-safe GUI updates from Worker signals
    """

    def __init__(self, model: VNADataModel, view: VNAMainWindow):
        """
        Initialize presenter and wire Model <-> View.

        Args:
            model: Data model instance
            view: Main window instance
        """
        super().__init__()
        self.model = model
        self.view = view

        # Worker thread state
        self._worker: Optional[VNASweepWorker] = None
        self._collecting = False
        self._recording = False  # True only during data collection (not preview)

        # Device probe worker state
        self._probe_worker: Optional[DeviceProbeWorker] = None
        self._gui_process = None  # Subprocess handle if GUI was started by probe

        # Preview worker state
        self._preview_worker: Optional[VNAPreviewWorker] = None
        self._previewing = False  # True when live preview is active

        # Current collection state
        self._current_ifbw_index = 0
        self._total_ifbw_count = 0

        # Connect view signals to presenter slots
        self._connect_view_signals()

        # Run auto-detection on startup
        self._on_startup()

    def _connect_view_signals(self):
        """Wire View signals to Presenter slots."""
        self.view.collect_data_requested.connect(self._on_collect_data_requested)
        self.view.load_calibration_requested.connect(self._on_load_calibration_requested)
        self.view.load_config_requested.connect(self._on_load_config_requested)
        self.view.connect_device_requested.connect(self._on_connect_device_requested)
        self.view.config_changed.connect(self._on_config_changed)
        self.view.window_closing.connect(self._on_window_closing)

    # -----------------------------------------------------------------------
    # Startup - Auto-detection
    # -----------------------------------------------------------------------

    def _on_startup(self):
        """
        Auto-detect calibration and config files on startup.

        Checks gui/mvp/ directory for:
          - Any .cal file (most recently modified is selected)
        Checks gui/ directory for:
          - sweep_config.yaml
        """
        gui_dir = Path(__file__).parent.parent
        mvp_dir = Path(__file__).parent  # gui/mvp/ -- colocated with backend

        # Auto-detect calibration files in gui/mvp/ (colocated with backend).
        # Uses glob to find ALL .cal files rather than hardcoding a filename.
        # Store just the filename -- the backend resolves it relative to
        # _MODULE_DIR and the GUI subprocess CWD is set to gui/mvp/, so the
        # SCPI :VNA:CAL:LOAD? command receives only the filename, avoiding
        # full Windows paths with spaces that break SCPI parsing.
        cal_files = sorted(
            mvp_dir.glob("*.cal"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if cal_files:
            selected_cal = cal_files[0]
            self.model.calibration.file_path = selected_cal.name
            self.model.calibration.loaded = True
            self.view.set_calibration_status(True, selected_cal.name)

            # Extract frequency range and num_points from the cal file.
            # The cal file is the single source of truth for these values.
            try:
                self.model.config.update_from_cal_file(str(selected_cal))
            except (FileNotFoundError, ValueError) as e:
                logger.warning("Failed to parse cal file for freq/points: %s", e)

            if len(cal_files) == 1:
                self.view.show_status_message(
                    f"Auto-loaded: {selected_cal.name}", timeout=0
                )
            else:
                all_names = ", ".join(p.name for p in cal_files)
                self.view.show_status_message(
                    f"Auto-loaded: {selected_cal.name} "
                    f"({len(cal_files)} cal files found: {all_names})",
                    timeout=0,
                )
        else:
            self.view.show_status_message(
                "No calibration file found in gui/mvp/", timeout=0
            )

        # Check for sweep config YAML
        yaml_path = gui_dir / "sweep_config.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path) as f:
                    config_dict = yaml.safe_load(f)

                # Load into model (freq/points remain as zero placeholders)
                self.model.config = SweepConfig.from_dict(config_dict)

                # Re-apply cal-file freq/points onto the new config object.
                # from_dict() does not read these from YAML; the cal file is
                # the single source of truth.
                if self.model.calibration.loaded and self.model.calibration.file_path:
                    try:
                        cal_path = mvp_dir / self.model.calibration.file_path
                        self.model.config.update_from_cal_file(str(cal_path))
                    except (FileNotFoundError, ValueError) as e:
                        logger.warning(
                            "Failed to re-apply cal file after YAML load: %s", e
                        )

                # Populate view widgets
                self.view.populate_sweep_config(self.model.config.to_dict())

                self.view.show_status_message(
                    f"Auto-loaded: {yaml_path.name}",
                    timeout=3000
                )
            except Exception as e:
                self.view.show_error_dialog(
                    "Config Load Error",
                    f"Failed to load {yaml_path.name}:\n{str(e)}"
                )
        else:
            # Use model defaults
            self.view.populate_sweep_config(self.model.config.to_dict())

        # Update button state after auto-detection
        # Device is NOT connected yet (probe worker will detect), so button stays disabled
        self._update_collect_button_state()

        # Launch device probe in background thread
        self._start_device_probe()

    # -----------------------------------------------------------------------
    # Device Probe (Startup Detection)
    # -----------------------------------------------------------------------

    def _start_device_probe(self):
        """
        Launch a background DeviceProbeWorker to detect the connected device.

        The worker connects to the LibreVNA-GUI SCPI server (starting the GUI
        subprocess if needed), queries *IDN? and DEV:CONN?, and emits the
        device serial number back to the Presenter via Qt signal.

        Safe to call multiple times -- a new probe will not start if one is
        already running.
        """
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return  # Probe already in progress

        # Show searching state in menu
        self.view.set_device_searching()
        self.view.show_status_message("Detecting device...", timeout=0)

        # Create and start probe worker
        self._probe_worker = DeviceProbeWorker()
        self._probe_worker.serial_detected.connect(self._on_serial_detected)
        self._probe_worker.probe_failed.connect(self._on_probe_failed)
        self._probe_worker.start()

    @Slot(dict)
    def _on_serial_detected(self, device_info: dict):
        """
        Handle successful device detection from probe worker.

        Updates the Model with device info and the View menu item with
        the serial number in the format "206830535532 (LibreVNA/USB)".

        Args:
            device_info: Dictionary from probe_device_serial() with keys:
                'serial', 'idn', 'gui_started', 'gui_process'
        """
        serial = device_info.get('serial', 'Unknown')
        idn = device_info.get('idn', '')

        # Update model
        self.model.device.serial_number = serial
        self.model.device.idn_string = idn
        self.model.device.connected = True

        # Store GUI subprocess handle if the probe started it
        if device_info.get('gui_process') is not None:
            self._gui_process = device_info['gui_process']

        # Update view (set_device_serial also re-enables the menu action)
        self.view.set_device_serial(serial)
        self.view.show_status_message(
            f"Device detected: {serial}", timeout=5000
        )

        # Update button state (device is now known)
        self._update_collect_button_state()

        # Start live preview automatically after device detection
        self._start_preview()

    @Slot(str)
    def _on_probe_failed(self, error_message: str):
        """
        Handle failed device detection from probe worker.

        Shows "Not found" in the menu and logs the error to the status bar.
        The user can retry by clicking the menu action.

        Args:
            error_message: Description of why the probe failed
        """
        # Update model
        self.model.device.connected = False
        self.model.device.serial_number = ""

        # Update view
        self.view.set_device_not_found()
        self.view.show_status_message(
            f"Device detection failed: {error_message}", timeout=10000
        )

        # Update button state
        self._update_collect_button_state()

    @Slot()
    def _on_connect_device_requested(self):
        """
        Handle Device > Connect to menu action click.

        Re-launches the device probe if not currently running.
        """
        if self._collecting:
            self.view.show_status_message(
                "Cannot probe device during data collection", timeout=3000
            )
            return

        self._start_device_probe()

    def _stop_probe_gui_process(self):
        """
        Terminate the GUI subprocess started by the device probe (if any).

        Called before starting a VNASweepWorker to avoid port conflicts,
        since both the probe and the sweep worker use the same SCPI port.
        """
        if self._gui_process is not None:
            try:
                self._gui_process.terminate()
                self._gui_process.wait(timeout=5)
            except Exception:
                try:
                    self._gui_process.kill()
                    self._gui_process.wait()
                except Exception:
                    pass
            self._gui_process = None

    # -----------------------------------------------------------------------
    # Live Preview (oscilloscope-style continuous sweep before collection)
    # -----------------------------------------------------------------------

    def _start_preview(self):
        """
        Launch VNAPreviewWorker for live sweep visualization.

        Called automatically after device detection succeeds. The preview
        runs continuous sweeps and updates the plot in real time WITHOUT
        saving data. It stops when the user presses 'Collect Data' or
        when the window closes.

        Prerequisites:
          - Device connected (gui_process running, SCPI server available)
          - Calibration file loaded in model
          (Frequency range and num_points are queried via SCPI by the worker)
        """
        # Guard: don't start preview during collection
        if self._collecting:
            return

        # Guard: don't start if already previewing
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return

        # Guard: need calibration loaded (freq range will be queried via SCPI)
        if not self.model.calibration.loaded or not self.model.calibration.file_path:
            logger.info("Preview skipped: no calibration loaded")
            return

        logger.info(
            "Starting live preview (cal=%s)",
            self.model.calibration.file_path,
        )

        # Create and configure preview worker.
        # Frequency range and num_points are queried via SCPI after connecting,
        # so we do NOT require them to be populated in the model config here.
        self._preview_worker = VNAPreviewWorker(
            cal_file_path=self.model.calibration.file_path,
        )

        # Connect preview signals
        self._preview_worker.preview_sweep.connect(self._on_preview_sweep)
        self._preview_worker.preview_started.connect(self._on_preview_started)
        self._preview_worker.preview_error.connect(self._on_preview_error)
        self._preview_worker.gui_process_changed.connect(
            self._on_preview_gui_changed
        )

        # Start the worker thread
        self._preview_worker.start()
        self.view.show_status_message("Starting live preview...", timeout=0)

    def _stop_preview_worker(self):
        """
        Gracefully stop the VNAPreviewWorker if it is running.

        Sets the cancel event, waits up to 5 seconds for the thread to
        finish, then force-terminates if it did not stop in time.

        Safe to call when no preview is active (no-op).
        """
        if self._preview_worker is None:
            return

        if self._preview_worker.isRunning():
            logger.info("Stopping preview worker...")

            # Disconnect signals to prevent stale callbacks
            try:
                self._preview_worker.preview_sweep.disconnect(
                    self._on_preview_sweep
                )
                self._preview_worker.preview_started.disconnect(
                    self._on_preview_started
                )
                self._preview_worker.preview_error.disconnect(
                    self._on_preview_error
                )
                self._preview_worker.gui_process_changed.disconnect(
                    self._on_preview_gui_changed
                )
            except (RuntimeError, TypeError):
                pass  # Signals already disconnected

            # Request graceful shutdown
            self._preview_worker.stop()

            # Wait for thread to finish
            if not self._preview_worker.wait(5000):
                logger.warning("Preview worker did not stop in 5s -- terminating")
                self._preview_worker.terminate()
                self._preview_worker.wait(2000)

            logger.info("Preview worker stopped")

        self._preview_worker = None
        self._previewing = False

    @Slot(object, object)
    def _on_preview_sweep(self, freq: np.ndarray, s11_db: np.ndarray):
        """
        Handle a preview sweep completion (live plot update only).

        Called from the preview worker's streaming callback via Qt signal.
        Updates the plot without saving data to the model.

        Args:
            freq: Frequency array in Hz
            s11_db: S11 magnitude in dB
        """
        self.view.update_plot(freq, s11_db)

    @Slot()
    def _on_preview_started(self):
        """Handle notification that preview streaming is active."""
        self._previewing = True
        self.view.set_preview_state(True)
        self.view.show_status_message(
            "Live Preview -- Press 'Collect Data' to record", timeout=0
        )

    @Slot(str)
    def _on_preview_error(self, error_message: str):
        """
        Handle preview worker error.

        Preview errors are non-fatal -- they just mean live preview is
        unavailable. The user can still click 'Collect Data'.

        Args:
            error_message: Description of the preview error
        """
        logger.warning("Preview error: %s", error_message)
        self._previewing = False
        self.view.set_preview_state(False)
        self.view.show_status_message(
            f"Live preview unavailable: {error_message}", timeout=10000
        )

    @Slot(object)
    def _on_preview_gui_changed(self, new_process):
        """
        Handle GUI subprocess restart by preview worker.

        When the preview worker enables the streaming server, the GUI
        subprocess dies and is restarted. This slot updates the presenter's
        gui_process reference so cleanup works correctly.

        Args:
            new_process: New subprocess.Popen handle
        """
        self._gui_process = new_process

    # -----------------------------------------------------------------------
    # User Actions
    # -----------------------------------------------------------------------

    @Slot()
    def _on_collect_data_requested(self):
        """Handle 'Collect Data' button click."""
        if self._collecting:
            return  # Already running

        # Stop the live preview worker before starting collection.
        # The preview holds an SCPI connection and streaming callback that
        # would conflict with the VNASweepWorker's own connections.
        self._stop_preview_worker()

        # Stop any GUI subprocess started by the device probe to avoid port
        # conflicts -- the VNASweepWorker starts its own GUI subprocess on
        # the same SCPI port (19542).
        self._stop_probe_gui_process()

        # Read config from widgets
        config_dict = self.view.read_sweep_config()

        # Validate config
        try:
            config = SweepConfig(**config_dict)
            if not config.is_valid():
                self.view.show_error_dialog(
                    "Invalid Configuration",
                    "Please check configuration values:\n"
                    "- Start frequency < Stop frequency\n"
                    "- Points > 0\n"
                    "- Sweeps > 0\n"
                    "- IFBW values > 0"
                )
                return
        except (ValueError, TypeError) as e:
            self.view.show_error_dialog(
                "Configuration Error",
                f"Invalid configuration values:\n{str(e)}"
            )
            return

        # Update model
        self.model.config = config
        self.model.clear_sweep_data()

        # Validate calibration
        if not self.model.calibration.loaded or not self.model.calibration.file_path:
            self.view.show_error_dialog(
                "Calibration Missing",
                "Please load a calibration file first."
            )
            return

        # Clear plot
        self.view.clear_plot()

        # Create worker thread
        self._worker = VNASweepWorker(
            config.to_dict(),
            self.model.calibration.file_path
        )

        # Connect worker signals
        self._worker.lifecycle_started.connect(self._on_lifecycle_started)
        self._worker.sweep_completed.connect(self._on_sweep_completed)
        self._worker.ifbw_completed.connect(self._on_ifbw_completed)
        self._worker.all_completed.connect(self._on_all_completed)
        self._worker.error_occurred.connect(self._on_error)

        # Update UI state
        self._collecting = True
        self._recording = True
        self._current_ifbw_index = 0
        self._total_ifbw_count = len(config.ifbw_values)
        self.view.set_collecting_state(True)
        self.view.show_status_message("Starting LibreVNA-GUI...", timeout=0)

        # Start worker
        self._worker.start()

    @Slot()
    def _on_load_calibration_requested(self):
        """
        Handle 'Load Calibration' menu action.

        Opens a file dialog for the user to select a .cal file. If the
        selected file is not already in the gui/mvp/ directory, it is
        copied there so that the SCPI :VNA:CAL:LOAD? command can resolve
        it by filename only (the GUI subprocess CWD is gui/mvp/).

        The model always stores just the filename (never the full path)
        to avoid Windows paths with spaces breaking SCPI parsing.
        """
        mvp_dir = Path(__file__).parent

        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Select Calibration File",
            str(mvp_dir),
            "Calibration Files (*.cal);;All Files (*)"
        )

        if file_path:
            source = Path(file_path)
            target = mvp_dir / source.name

            # If the file is NOT already in gui/mvp/, copy it there so
            # the SCPI command can find it by filename alone.
            if source.parent.resolve() != mvp_dir.resolve():
                try:
                    shutil.copy2(source, target)
                    self.view.show_status_message(
                        f"Copied {source.name} to gui/mvp/", timeout=3000
                    )
                except Exception as e:
                    self.view.show_error_dialog(
                        "Copy Error",
                        f"Could not copy calibration file to gui/mvp/:\n{e}"
                    )
                    return

            # Always store just the filename (not full path)
            self.model.calibration.file_path = source.name
            self.model.calibration.loaded = True
            self.view.set_calibration_status(True, source.name)

            # Extract frequency range and num_points from the new cal file.
            try:
                self.model.config.update_from_cal_file(str(target))
                self.view.populate_sweep_config(self.model.config.to_dict())
            except (FileNotFoundError, ValueError) as e:
                logger.warning("Failed to parse cal file for freq/points: %s", e)

            self.view.show_status_message(f"Loaded: {source.name}")
            self._update_collect_button_state()

            # Restart preview worker so it picks up the new cal file
            if (self._preview_worker is not None
                    and self._preview_worker.isRunning()):
                self._stop_preview_worker()
                self._start_preview()

    @Slot()
    def _on_load_config_requested(self):
        """Handle 'Load Config' menu action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Select Configuration File",
            str(Path.home()),
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path) as f:
                    config_dict = yaml.safe_load(f)

                self.model.config = SweepConfig.from_dict(config_dict)

                # Re-apply cal-file freq/points onto the new config object.
                # from_dict() does not read these from YAML; the cal file is
                # the single source of truth.
                if self.model.calibration.loaded and self.model.calibration.file_path:
                    try:
                        mvp_dir = Path(__file__).parent
                        cal_path = mvp_dir / self.model.calibration.file_path
                        self.model.config.update_from_cal_file(str(cal_path))
                    except (FileNotFoundError, ValueError) as e:
                        logger.warning(
                            "Failed to re-apply cal file after config load: %s", e
                        )

                self.view.populate_sweep_config(self.model.config.to_dict())
                self.view.show_status_message(f"Loaded: {Path(file_path).name}")
                self._update_collect_button_state()

            except Exception as e:
                self.view.show_error_dialog(
                    "Config Load Error",
                    f"Failed to load configuration:\n{str(e)}"
                )

    @Slot()
    def _on_config_changed(self):
        """Handle configuration widget changes (for validation feedback)."""
        # Could add real-time validation here
        self._update_collect_button_state()

    # -----------------------------------------------------------------------
    # Worker Thread Signals (Thread-Safe Slots)
    # -----------------------------------------------------------------------

    @Slot(dict)
    def _on_lifecycle_started(self, device_info: dict):
        """
        Called when worker has started GUI and connected to device.

        Args:
            device_info: Dictionary with 'serial' and 'idn' keys
        """
        # Update model
        self.model.device.connected = True
        self.model.device.serial_number = device_info.get('serial', 'Unknown')
        self.model.device.idn_string = device_info.get('idn', '')

        # Update view
        self.view.set_device_serial(self.model.device.serial_number)
        self.view.show_status_message(
            "Device connected - Starting sweeps...", timeout=0
        )

    @Slot(int, int, object, object)
    def _on_sweep_completed(
        self, sweep_idx: int, ifbw_hz: int,
        freq: np.ndarray, s11_db: np.ndarray
    ):
        """
        Called after each sweep completes (real-time update).

        When recording (during data collection), saves data to model and
        shows sweep progress. When not recording (preview mode), only
        updates the plot without saving data.

        Args:
            sweep_idx: Sequential sweep number (0-based)
            ifbw_hz: Current IFBW value
            freq: Frequency array
            s11_db: S11 magnitude in dB
        """
        # Only save data to model during active recording (not preview)
        if self._recording:
            self.model.add_sweep_data(sweep_idx, ifbw_hz, freq, s11_db)

        # Always update plot (both preview and recording modes)
        self.view.update_plot(freq, s11_db)

        # Update status based on mode
        if self._recording:
            ifbw_khz = ifbw_hz // 1000
            progress = (
                f"IFBW {ifbw_khz} kHz - "
                f"Sweep {sweep_idx + 1}/{self.model.config.num_sweeps}"
            )
            self.view.show_status_message(progress, timeout=0)
            self.view.update_progress_label(progress)

    @Slot(int, dict)
    def _on_ifbw_completed(self, ifbw_hz: int, metrics: dict):
        """
        Called when all sweeps for one IFBW complete.

        Args:
            ifbw_hz: Completed IFBW value
            metrics: Dictionary with timing metrics
        """
        self._current_ifbw_index += 1
        ifbw_khz = ifbw_hz // 1000

        # Show progress
        progress_msg = (
            f"IFBW {ifbw_khz} kHz complete "
            f"({self._current_ifbw_index}/{self._total_ifbw_count}) - "
            f"Rate: {metrics['sweep_rate']:.2f} Hz"
        )
        self.view.show_status_message(progress_msg, timeout=0)

    @Slot(str)
    def _on_all_completed(self, output_dir: str):
        """
        Called when all sweeps and CSV export complete.

        Resets collection state and re-probes the device, which will
        automatically restart the live preview via _on_serial_detected().

        Args:
            output_dir: Absolute path to saved CSV bundle directory
        """
        # Update state
        self._collecting = False
        self._recording = False
        self.model.device.connected = False

        # Update view
        self.view.set_collecting_state(False)
        self.view.show_status_message(
            f"Collection complete - Saved: {Path(output_dir).name}", timeout=0
        )

        # Show success dialog
        stats = self.model.get_sweep_statistics()
        message = (
            f"Data collection complete!\n\n"
            f"Total sweeps: {stats['total_sweeps']}\n"
            f"Mean sweep time: {stats['mean_time']:.3f} s\n"
            f"Sweep rate: {stats['sweep_rate_hz']:.2f} Hz\n\n"
            f"Saved to:\n{output_dir}\n\n"
            f"CSV bundle contains:\n"
            f"  - s11_sweep_1.csv, s11_sweep_2.csv, ...\n"
            f"  - summary.txt"
        )
        self.view.show_success_dialog("Collection Complete", message)

        # Re-probe the device so that device.connected is restored and the
        # Collect Data button becomes enabled again for subsequent runs.
        # The VNASweepWorker's stop_lifecycle() terminated the GUI subprocess,
        # so we need a fresh probe to re-establish the SCPI connection.
        self._start_device_probe()

    @Slot(str)
    def _on_error(self, error_message: str):
        """
        Called when worker encounters an error.

        Args:
            error_message: Full error traceback
        """
        # Update state
        self._collecting = False
        self._recording = False
        self.model.device.connected = False

        # Update view
        self.view.set_collecting_state(False)
        self.view.show_status_message(
            "Error occurred during collection", timeout=0
        )

        # Show error dialog
        self.view.show_error_dialog("Collection Error", error_message)

        # Re-probe the device so that device.connected is restored and the
        # Collect Data button becomes enabled again for subsequent runs.
        self._start_device_probe()

    # -----------------------------------------------------------------------
    # Button State Machine
    # -----------------------------------------------------------------------

    def _update_collect_button_state(self):
        """
        Update collect button enabled/disabled state.

        Button is enabled when ALL conditions are met:
          - Device connected (detected via DeviceProbeWorker)
          - Calibration loaded
          - Config valid
          - NOT currently collecting

        The button stays greyed out with a "Not Ready" label until the
        device probe succeeds. This prevents the user from clicking
        "Collect Data" before the device is fully initialized.
        """
        ready = (
            self.model.device.connected and
            self.model.calibration.loaded and
            self.model.config.is_valid() and
            not self._collecting
        )

        self.view.set_collect_button_enabled(ready)

        # If ready but not collecting, show green button
        if ready and not self._collecting:
            self.view.set_collecting_state(False)

    # -----------------------------------------------------------------------
    # Cleanup / Shutdown
    # -----------------------------------------------------------------------

    @Slot()
    def _on_window_closing(self):
        """
        Handle window close event from View.

        Called when the user closes the window (X button, Alt+F4, or
        programmatic close). Delegates to cleanup() for all resource
        teardown.
        """
        logger.info("Window closing -- starting cleanup")
        self.cleanup()

    def cleanup(self):
        """
        Stop all background operations and release resources before shutdown.

        Cleanup sequence (order matters for avoiding port conflicts):
          1. Stop VNAPreviewWorker (if previewing)
          2. Stop DeviceProbeWorker (if running)
          3. Stop VNASweepWorker and its adapter (if collecting)
          4. Terminate GUI subprocess started by device probe (if any)

        Each step uses graceful shutdown (quit+wait) with a timeout,
        falling back to forced termination if the timeout expires.

        Thread safety: This method runs on the GUI thread. Worker threads
        are stopped via QThread.quit() which posts a quit event to their
        event loop, then wait() blocks until the thread finishes.

        Safe to call multiple times (idempotent).
        """
        # Step 1: Stop preview worker (holds SCPI + streaming connections)
        self._stop_preview_worker()

        # Step 2: Stop device probe worker thread
        self._stop_probe_worker()

        # Step 3: Stop sweep worker thread (and its adapter subprocess)
        self._stop_sweep_worker()

        # Step 4: Terminate probe GUI subprocess (started during detection)
        self._stop_probe_gui_process()

        logger.info("Cleanup complete")

    def _stop_probe_worker(self):
        """
        Stop the DeviceProbeWorker QThread if it is running.

        The probe worker performs blocking socket operations (connecting to
        the SCPI server, querying *IDN?). Since QThread.quit() only works
        for threads with an event loop, and our worker uses run() directly,
        we use wait() with a timeout and then terminate() as fallback.

        Timeout: 3 seconds (the probe typically completes in <2s if the
        server is reachable, or fails fast if not).
        """
        if self._probe_worker is None:
            return

        if self._probe_worker.isRunning():
            logger.info("Stopping device probe worker...")

            # Disconnect signals to prevent stale callbacks after cleanup
            try:
                self._probe_worker.serial_detected.disconnect(self._on_serial_detected)
                self._probe_worker.probe_failed.disconnect(self._on_probe_failed)
            except (RuntimeError, TypeError):
                pass  # Signals already disconnected or never connected

            # Wait for the thread to finish (it's doing blocking I/O)
            if not self._probe_worker.wait(3000):  # 3 second timeout
                logger.warning("Probe worker did not stop in 3s -- terminating")
                self._probe_worker.terminate()
                self._probe_worker.wait(2000)  # Brief wait after terminate

            logger.info("Device probe worker stopped")

        self._probe_worker = None

    def _stop_sweep_worker(self):
        """
        Stop the VNASweepWorker QThread and its backend adapter.

        The sweep worker may be in the middle of:
          - Starting the GUI subprocess (blocking ~5-10s)
          - Running SCPI commands
          - Waiting for streaming callbacks
          - Saving CSV bundle

        Cleanup strategy:
          1. If the worker has an adapter, call stop_lifecycle() to terminate
             the GUI subprocess and close SCPI sockets immediately. This
             unblocks any pending socket reads in the worker thread.
          2. Wait for the thread to finish (the unblocked I/O should cause
             an exception that falls through to the worker's finally block).
          3. Force-terminate the thread if it does not stop within timeout.

        Timeout: 8 seconds total (5s for adapter stop + 3s for thread wait).
        """
        if self._worker is None:
            return

        if self._worker.isRunning():
            logger.info("Stopping sweep worker (collecting=%s)...", self._collecting)

            # Disconnect signals to prevent stale callbacks
            try:
                self._worker.lifecycle_started.disconnect(self._on_lifecycle_started)
                self._worker.sweep_completed.disconnect(self._on_sweep_completed)
                self._worker.ifbw_completed.disconnect(self._on_ifbw_completed)
                self._worker.all_completed.disconnect(self._on_all_completed)
                self._worker.error_occurred.disconnect(self._on_error)
            except (RuntimeError, TypeError):
                pass  # Signals already disconnected

            # Kill the adapter's subprocess to unblock pending I/O in the worker
            if self._worker.adapter is not None:
                logger.info("Stopping sweep adapter (GUI subprocess + SCPI)...")
                try:
                    self._worker.adapter.stop_lifecycle()
                except Exception as e:
                    logger.warning("Adapter stop_lifecycle error: %s", e)

            # Wait for the worker thread to finish
            if not self._worker.wait(5000):  # 5 second timeout
                logger.warning("Sweep worker did not stop in 5s -- terminating")
                self._worker.terminate()
                self._worker.wait(2000)  # Brief wait after terminate

            logger.info("Sweep worker stopped")

        # Reset state
        self._worker = None
        self._collecting = False
