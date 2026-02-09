"""
Backend adapter for GUI integration with script 6 (BaseVNASweep).

This module wraps the monolithic run() method from ContinuousModeSweep into
discrete lifecycle steps suitable for GUI threading:
  - start_lifecycle() -> start GUI, connect, load calibration
  - run_single_ifbw_sweep() -> configure + run sweeps for ONE IFBW value
  - save_results() -> write xlsx workbook
  - stop_lifecycle() -> terminate GUI subprocess

Also provides a lightweight probe_device_serial() function for startup device
detection without requiring the full sweep infrastructure.

Threading contract: All methods except callbacks are called from QThread worker.
Callbacks are passed by caller and should emit Qt signals for thread-safe GUI updates.
"""

import sys
import os
import socket
import time
import subprocess
import platform
from pathlib import Path
from typing import Callable, Dict, List, Optional
import numpy as np

# Add scripts directory to path for importing backend
SCRIPT_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from importlib import import_module
from libreVNA import libreVNA

# Dynamically import script 6 to avoid naming conflicts (starts with digit)
script6_module = import_module("6_librevna_gui_mode_sweep_test")
ContinuousModeSweep = script6_module.ContinuousModeSweep
SweepResult = script6_module.SweepResult

# SCPI connection constants (matching script 6)
SCPI_HOST = "localhost"
SCPI_PORT = 19542
GUI_START_TIMEOUT_S = 30.0

# OS-dependent GUI binary path
if platform.system() == "Windows":
    GUI_BINARY = str(Path(SCRIPT_DIR) / ".." / "tools" / "LibreVNA-GUI" / "release" / "LibreVNA-GUI.exe")
else:
    GUI_BINARY = str(Path(SCRIPT_DIR) / ".." / "tools" / "LibreVNA-GUI")
GUI_BINARY = os.path.normpath(GUI_BINARY)


def _is_scpi_server_running(host: str = SCPI_HOST, port: int = SCPI_PORT,
                            timeout: float = 1.0) -> bool:
    """
    Check if the LibreVNA-GUI SCPI server is accepting connections.

    Args:
        host: SCPI server hostname
        port: SCPI server port number
        timeout: Connection attempt timeout in seconds

    Returns:
        True if a TCP connection to the SCPI port succeeds
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        try:
            s.close()
        except Exception:
            pass
        return False


def _start_gui_subprocess() -> subprocess.Popen:
    """
    Launch LibreVNA-GUI in headless/no-gui mode and wait for the SCPI
    server to become available on SCPI_PORT.

    Returns:
        subprocess.Popen handle for the GUI process

    Raises:
        RuntimeError: If the GUI does not start within GUI_START_TIMEOUT_S
        FileNotFoundError: If the GUI binary is not found
    """
    if not os.path.exists(GUI_BINARY):
        raise FileNotFoundError(
            f"LibreVNA-GUI binary not found at: {GUI_BINARY}"
        )

    env = os.environ.copy()
    if platform.system() != "Windows":
        env["QT_QPA_PLATFORM"] = "offscreen"

    proc = subprocess.Popen(
        [GUI_BINARY, "--port", str(SCPI_PORT), "--no-gui"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Poll for SCPI server readiness
    deadline = time.time() + GUI_START_TIMEOUT_S
    while True:
        if _is_scpi_server_running():
            return proc
        if time.time() > deadline:
            proc.terminate()
            proc.wait()
            raise RuntimeError(
                f"LibreVNA-GUI did not open SCPI server on port {SCPI_PORT} "
                f"within {GUI_START_TIMEOUT_S:.0f} s"
            )
        time.sleep(0.25)


def probe_device_serial() -> Dict[str, str]:
    """
    Lightweight device probe for startup detection.

    Attempts to connect to the LibreVNA-GUI SCPI server. If the server is
    not running, starts the GUI subprocess first. Then queries the device
    identity (*IDN?) and connected device serial (DEV:CONN?) to retrieve
    the hardware serial number.

    This function is designed to be called from a background QThread so it
    does not block the GUI event loop.

    Returns:
        Dictionary with device info:
            'serial': Hardware serial number (e.g. '206830535532')
            'idn': Full *IDN? response string
            'gui_started': True if this function started the GUI subprocess
            'gui_process': subprocess.Popen handle if GUI was started, else None

    Raises:
        RuntimeError: If connection fails or no device is connected
        FileNotFoundError: If GUI binary not found (when auto-starting)
    """
    gui_process = None
    gui_started = False

    # Step 1: Check if SCPI server is already running
    if not _is_scpi_server_running():
        # Need to start the GUI subprocess
        gui_process = _start_gui_subprocess()
        gui_started = True

    # Step 2: Connect to SCPI server
    try:
        vna = libreVNA(host=SCPI_HOST, port=SCPI_PORT)
    except Exception as exc:
        if gui_process:
            gui_process.terminate()
            gui_process.wait()
        raise RuntimeError(
            f"Could not connect to LibreVNA-GUI SCPI server at "
            f"{SCPI_HOST}:{SCPI_PORT}: {exc}"
        )

    # Step 3: Query device identity
    try:
        idn_raw = vna.query("*IDN?")
        parts = [p.strip() for p in idn_raw.split(",")]
        idn_serial = parts[2] if len(parts) > 2 else "Unknown"
    except Exception as exc:
        if gui_process:
            gui_process.terminate()
            gui_process.wait()
        raise RuntimeError(f"*IDN? query failed: {exc}")

    # Step 4: Query connected device serial (more authoritative)
    try:
        dev_serial = vna.query(":DEV:CONN?")
        dev_serial = dev_serial.strip()
        if dev_serial == "Not connected":
            raise RuntimeError(
                "LibreVNA-GUI is running but no hardware device is connected."
            )
    except RuntimeError:
        raise
    except Exception as exc:
        # Fall back to *IDN? serial if DEV:CONN? fails
        dev_serial = idn_serial

    return {
        'serial': dev_serial,
        'idn': idn_raw,
        'gui_started': gui_started,
        'gui_process': gui_process,
    }


class GUIVNASweepAdapter:
    """
    Adapter that breaks ContinuousModeSweep into discrete GUI-friendly steps.

    Usage pattern (from QThread worker):
        adapter = GUIVNASweepAdapter(config_dict, cal_file_path)
        adapter.start_lifecycle()

        for ifbw in ifbw_values:
            def callback(sweep_idx, freq_hz, s11_db):
                # Emit Qt signal here for GUI update
                pass

            result = adapter.run_single_ifbw_sweep(ifbw, callback)

        xlsx_path = adapter.save_results(all_results)
        adapter.stop_lifecycle()
    """

    def __init__(self, config_dict: dict, calibration_file_path: str):
        """
        Initialize adapter with configuration.

        Args:
            config_dict: Sweep configuration matching SweepConfig.to_dict() format
            calibration_file_path: Absolute path to .cal file
        """
        self.config = config_dict
        self.cal_file_path = calibration_file_path

        # Create temporary YAML config file for BaseVNASweep
        self.temp_config_path = self._create_temp_config()

        # Initialize sweep instance (continuous mode only)
        self.sweep = ContinuousModeSweep(
            config_path=self.temp_config_path,
            mode="continuous",
            summary=False,  # No console output in GUI
            save_data=False  # We'll handle saving separately
        )

        # Lifecycle state
        self.gui_process = None
        self.vna = None
        self.all_results: List[SweepResult] = []

    def _create_temp_config(self) -> str:
        """
        Create a temporary sweep_config.yaml for BaseVNASweep consumption.

        Returns:
            Absolute path to temporary config file
        """
        import tempfile
        import yaml

        # Convert config_dict to YAML structure expected by script 6
        yaml_config = {
            'configurations': {
                'start_frequency': self.config['start_frequency'],
                'stop_frequency': self.config['stop_frequency'],
                'num_points': self.config['num_points'],
                'stim_lvl_dbm': self.config['stim_lvl_dbm'],
                'avg_count': self.config['avg_count'],
                'num_sweeps': self.config['num_sweeps'],
            },
            'target': {
                'ifbw_values': self.config['ifbw_values']
            }
        }

        # Write to temp file
        fd, path = tempfile.mkstemp(suffix='.yaml', prefix='gui_sweep_')
        with os.fdopen(fd, 'w') as f:
            yaml.dump(yaml_config, f)

        return path

    def start_lifecycle(self) -> Dict[str, str]:
        """
        Start GUI subprocess, connect to SCPI, load calibration.

        Returns:
            Dictionary with device info: {'serial': ..., 'idn': ...}

        Raises:
            RuntimeError: If GUI start, connection, or calibration fails
        """
        # Step 1: Start GUI subprocess
        self.gui_process = self.sweep.start_gui()

        # Step 2: Connect to SCPI server and verify device
        self.vna = self.sweep.connect_and_verify()

        # Extract device info for GUI display
        idn_raw = self.vna.query("*IDN?")
        parts = [p.strip() for p in idn_raw.split(",")]
        serial = parts[2] if len(parts) > 2 else "Unknown"

        # Step 3: Load calibration file
        success = self.sweep.load_calibration(self.vna, self.cal_file_path)
        if not success:
            raise RuntimeError(f"Failed to load calibration: {self.cal_file_path}")

        # Step 4: Enable streaming server (required for continuous mode)
        self.sweep.enable_streaming_server(self.vna)

        return {
            'serial': serial,
            'idn': idn_raw,
        }

    def run_single_ifbw_sweep(
        self,
        ifbw_hz: int,
        callback: Optional[Callable[[int, np.ndarray, np.ndarray], None]] = None
    ) -> SweepResult:
        """
        Configure and run sweeps for a single IFBW value.

        Args:
            ifbw_hz: IF bandwidth in Hz
            callback: Called after each sweep with (sweep_idx, freq_hz, s11_db)
                      This should emit Qt signals for thread-safe GUI updates

        Returns:
            SweepResult object with timing metrics and trace data
        """
        # Configure SCPI parameters for this IFBW
        self.sweep.configure_sweep(self.vna, ifbw_hz)

        # Inject callback wrapper into sweep instance
        if callback:
            self._install_callback_hook(callback)

        # Run the sweep loop (blocking until all sweeps complete)
        result = self.sweep.run_sweeps(self.vna, ifbw_hz)

        # Store result for later xlsx export
        self.all_results.append(result)

        return result

    def _install_callback_hook(self, callback: Callable):
        """
        Monkey-patch the sweep instance to call our callback.

        This intercepts the internal streaming callback to inject GUI updates.
        """
        original_make_callback = self.sweep._make_callback

        def wrapped_make_callback(state_holder):
            # Get the original streaming callback
            original_callback = original_make_callback(state_holder)

            # Wrap it to extract data for GUI
            def gui_callback(datapoint):
                # Call original callback first (accumulates data)
                original_callback(datapoint)

                # After sweep completes, extract data for GUI
                state = state_holder[0]
                if state and datapoint['pointNum'] == state.num_points - 1:
                    # Last point of sweep → full sweep ready
                    with state.lock:
                        if state.all_s11_complex:
                            sweep_idx = len(state.all_s11_complex) - 1
                            s11_complex = state.all_s11_complex[-1]

                            # Convert to dB
                            s11_db = 20 * np.log10(np.abs(s11_complex))

                            # Build frequency array
                            freq_hz = np.linspace(
                                self.sweep.start_freq_hz,
                                self.sweep.stop_freq_hz,
                                self.sweep.num_points
                            )

                            # Call user callback (should emit Qt signal)
                            callback(sweep_idx, freq_hz, s11_db)

            return gui_callback

        # Install monkey patch
        self.sweep._make_callback = wrapped_make_callback

    def save_results(self, custom_filename: Optional[str] = None) -> str:
        """
        Export all accumulated results to multi-sheet xlsx workbook.

        Args:
            custom_filename: Optional custom filename (without extension)

        Returns:
            Absolute path to saved xlsx file
        """
        if not self.all_results:
            raise ValueError("No sweep results to save")

        # Temporarily restore save_data flag
        original_save_data = self.sweep.save_data
        self.sweep.save_data = True

        # Override filename if provided
        if custom_filename:
            import datetime
            today = datetime.datetime.now().strftime("%Y%m%d")
            out_dir = Path(SCRIPT_DIR).parent / "data" / today
            out_dir.mkdir(parents=True, exist_ok=True)
            xlsx_path = out_dir / f"{custom_filename}.xlsx"

            # Temporarily patch the save_xlsx method to use custom path
            original_save = self.sweep.save_xlsx

            def custom_save(results):
                path = original_save(results)
                # Move to custom location
                import shutil
                shutil.move(path, xlsx_path)
                return str(xlsx_path)

            self.sweep.save_xlsx = custom_save

        # Call save method
        xlsx_path = self.sweep.save_xlsx(self.all_results)

        # Restore original state
        self.sweep.save_data = original_save_data

        return xlsx_path

    def stop_lifecycle(self):
        """
        Terminate GUI subprocess gracefully.
        """
        if self.gui_process:
            self.sweep.stop_gui(self.gui_process)

        # Clean up temp config file
        if hasattr(self, 'temp_config_path') and os.path.exists(self.temp_config_path):
            os.unlink(self.temp_config_path)

    def get_device_serial(self) -> str:
        """Query device serial number (DEV:CONN?)."""
        if not self.vna:
            return "Not connected"

        try:
            serial = self.vna.query(":DEV:CONN?")
            return serial.strip()
        except Exception:
            return "Query failed"
