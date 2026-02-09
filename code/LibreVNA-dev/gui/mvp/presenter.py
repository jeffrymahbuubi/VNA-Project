"""
Presenter layer for LibreVNA GUI (MVP architecture).

Mediates between Model and View, handles state machine, and manages worker thread.
All backend operations (SCPI, sweeps) run in VNASweepWorker to keep GUI responsive.
"""

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog
from pathlib import Path
import yaml
import numpy as np
from typing import Optional

from .model import VNADataModel, SweepConfig
from .view import VNAMainWindow
from .backend_wrapper import GUIVNASweepAdapter


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
        self.view.config_changed.connect(self._on_config_changed)

    # -----------------------------------------------------------------------
    # Startup - Auto-detection
    # -----------------------------------------------------------------------

    def _on_startup(self):
        """
        Auto-detect calibration and config files on startup.

        Checks gui/ directory for:
          - SOLT_1_2_43G-2_45G_300pt.cal
          - sweep_config.yaml
        """
        gui_dir = Path(__file__).parent.parent

        # Check for calibration file
        cal_path = gui_dir / "SOLT_1_2_43G-2_45G_300pt.cal"
        if cal_path.exists():
            self.model.calibration.file_path = str(cal_path)
            self.model.calibration.loaded = True
            self.view.set_calibration_status(True, cal_path.name)
            self.view.show_status_message(
                f"Auto-loaded: {cal_path.name}", timeout=0
            )
        else:
            self.view.show_status_message(
                "No calibration file found in gui/", timeout=0
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
        # Device is NOT connected yet (worker will connect), so button stays disabled
        self._update_collect_button_state()

    # -----------------------------------------------------------------------
    # User Actions
    # -----------------------------------------------------------------------

    @Slot()
    def _on_collect_data_requested(self):
        """Handle 'Collect Data' button click."""
        if self._collecting:
            return  # Already running

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
