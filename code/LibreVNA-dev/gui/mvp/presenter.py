"""
Presenter layer for LibreVNA GUI (MVP architecture).

Mediates between Model and View, handles state machine, and manages worker threads.
All backend operations (SCPI, sweeps) run in background QThreads to keep GUI responsive.

Worker threads:
  - DeviceProbeWorker: Lightweight startup device detection (queries serial)
  - VNASweepWorker: Full sweep collection lifecycle (GUI + cal + sweeps + xlsx)
"""

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog
from pathlib import Path
import logging
import yaml
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

from .model import VNADataModel, SweepConfig
from .view import VNAMainWindow
from .backend_wrapper import GUIVNASweepAdapter, probe_device_serial


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
    all_completed = Signal(str)  # xlsx_file_path
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
          3. Save xlsx workbook
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

            # Step 3: Save results to xlsx
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            custom_filename = f"gui_sweep_collection_{timestamp}"
            xlsx_path = self.adapter.save_results(custom_filename)

            self.all_completed.emit(xlsx_path)

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

        # Device probe worker state
        self._probe_worker: Optional[DeviceProbeWorker] = None
        self._gui_process = None  # Subprocess handle if GUI was started by probe

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
          - SOLT_1_2_43G-2_45G_300pt.cal (colocated with backend)
        Checks gui/ directory for:
          - sweep_config.yaml
        """
        gui_dir = Path(__file__).parent.parent
        mvp_dir = Path(__file__).parent  # gui/mvp/ -- colocated with backend

        # Check for calibration file in gui/mvp/ (colocated with backend scripts).
        # Store just the filename -- the backend resolves it relative to _MODULE_DIR
        # and the GUI subprocess CWD is set to gui/mvp/, so the SCPI :VNA:CAL:LOAD?
        # command receives only the filename, avoiding full Windows paths with spaces
        # that break SCPI parsing.
        cal_path = mvp_dir / "SOLT_1_2_43G-2_45G_300pt.cal"
        if cal_path.exists():
            # Store just the filename -- avoids full Windows paths in SCPI commands
            self.model.calibration.file_path = cal_path.name
            self.model.calibration.loaded = True
            self.view.set_calibration_status(True, cal_path.name)
            self.view.show_status_message(
                f"Auto-loaded: {cal_path.name}", timeout=0
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

                # Load into model
                self.model.config = SweepConfig.from_dict(config_dict)

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
    # User Actions
    # -----------------------------------------------------------------------

    @Slot()
    def _on_collect_data_requested(self):
        """Handle 'Collect Data' button click."""
        if self._collecting:
            return  # Already running

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
        self._current_ifbw_index = 0
        self._total_ifbw_count = len(config.ifbw_values)
        self.view.set_collecting_state(True)
        self.view.show_status_message("Starting LibreVNA-GUI...", timeout=0)

        # Start worker
        self._worker.start()

    @Slot()
    def _on_load_calibration_requested(self):
        """Handle 'Load Calibration' menu action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view,
            "Select Calibration File",
            str(Path.home()),
            "Calibration Files (*.cal);;All Files (*)"
        )

        if file_path:
            self.model.calibration.file_path = file_path
            self.model.calibration.loaded = True
            self.view.set_calibration_status(True, Path(file_path).name)
            self.view.show_status_message(f"Loaded: {Path(file_path).name}")
            self._update_collect_button_state()

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

        Args:
            sweep_idx: Sequential sweep number (0-based)
            ifbw_hz: Current IFBW value
            freq: Frequency array
            s11_db: S11 magnitude in dB
        """
        # Update model
        self.model.add_sweep_data(sweep_idx, ifbw_hz, freq, s11_db)

        # Update plot (overwrite with latest sweep)
        self.view.update_plot(freq, s11_db)

        # Update status
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
    def _on_all_completed(self, xlsx_path: str):
        """
        Called when all sweeps and xlsx export complete.

        Args:
            xlsx_path: Absolute path to saved workbook
        """
        # Update state
        self._collecting = False
        self.model.device.connected = False

        # Update view
        self.view.set_collecting_state(False)
        self.view.show_status_message(
            f"Collection complete - Saved: {Path(xlsx_path).name}", timeout=0
        )

        # Show success dialog
        stats = self.model.get_sweep_statistics()
        message = (
            f"Data collection complete!\n\n"
            f"Total sweeps: {stats['total_sweeps']}\n"
            f"Mean sweep time: {stats['mean_time']:.3f} s\n"
            f"Sweep rate: {stats['sweep_rate_hz']:.2f} Hz\n\n"
            f"Saved to:\n{xlsx_path}"
        )
        self.view.show_success_dialog("Collection Complete", message)

        # Update button state
        self._update_collect_button_state()

    @Slot(str)
    def _on_error(self, error_message: str):
        """
        Called when worker encounters an error.

        Args:
            error_message: Full error traceback
        """
        # Update state
        self._collecting = False
        self.model.device.connected = False

        # Update view
        self.view.set_collecting_state(False)
        self.view.show_status_message(
            "Error occurred during collection", timeout=0
        )

        # Show error dialog
        self.view.show_error_dialog("Collection Error", error_message)

        # Update button state
        self._update_collect_button_state()

    # -----------------------------------------------------------------------
    # Button State Machine
    # -----------------------------------------------------------------------

    def _update_collect_button_state(self):
        """
        Update collect button enabled/disabled state.

        Button is enabled when:
          - Calibration loaded
          - Config valid
          - NOT currently collecting

        Note: Device is NOT connected before collection starts (the worker
        thread handles the GUI subprocess). So we enable the button based
        on calibration + config only.
        """
        ready = (
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
          1. Stop DeviceProbeWorker (if running)
          2. Stop VNASweepWorker and its adapter (if collecting)
          3. Terminate GUI subprocess started by device probe (if any)

        Each step uses graceful shutdown (quit+wait) with a timeout,
        falling back to forced termination if the timeout expires.

        Thread safety: This method runs on the GUI thread. Worker threads
        are stopped via QThread.quit() which posts a quit event to their
        event loop, then wait() blocks until the thread finishes.

        Safe to call multiple times (idempotent).
        """
        # Step 1: Stop device probe worker thread
        self._stop_probe_worker()

        # Step 2: Stop sweep worker thread (and its adapter subprocess)
        self._stop_sweep_worker()

        # Step 3: Terminate probe GUI subprocess (started during detection)
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
          - Saving xlsx output

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
