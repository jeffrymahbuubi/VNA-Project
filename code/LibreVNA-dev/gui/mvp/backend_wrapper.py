"""
Backend adapter for GUI integration with script 6 (BaseVNASweep).

This module wraps the monolithic run() method from ContinuousModeSweep into
discrete lifecycle steps suitable for GUI threading:
  - start_lifecycle() -> start GUI, connect, load calibration, register streaming
  - run_single_ifbw_sweep() -> configure + run sweeps for ONE IFBW value
  - save_results() -> write xlsx workbook
  - stop_lifecycle() -> teardown streaming, terminate GUI subprocess

Also provides a lightweight probe_device_serial() function for startup device
detection without requiring the full sweep infrastructure.

Threading contract: All methods except callbacks are called from QThread worker.
Callbacks are passed by caller and should emit Qt signals for thread-safe GUI updates.

Key fix (2026-02-10): The adapter now calls pre_loop_reset() and post_loop_teardown()
to properly register/deregister the streaming callback. Without these calls the
streaming data callback was never connected, causing:
  - Infinite sweep loop (done_event never set, 300s timeout)
  - No plot updates (GUI callback never triggered)
"""

import sys
import os
import socket
import time
import subprocess
import platform
import logging
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Import from local backend module (standalone)
from .vna_backend import (
    ContinuousModeSweep, SweepResult, MonitorRecord,
    export_dataflux_csv,
    SCPI_HOST, SCPI_PORT, GUI_START_TIMEOUT_S,
    GUI_BINARY, STREAMING_PORT, _MODULE_DIR,
)
from .libreVNA import libreVNA


# ---------------------------------------------------------------------------
# Port cleanup utilities (adapted from scripts/0_librevna_cleanup.py)
# ---------------------------------------------------------------------------

# Ports used by LibreVNA-GUI
LIBREVNA_PORTS = {
    1234:  "SCPI server",
    19000: "VNA Raw streaming",
    19001: "VNA Calibrated streaming",
    19002: "VNA De-embedded streaming",
    19542: "Internal LibreVNA TCP",
}

# Process names to exclude from port cleanup (remote/tunneling services)
SAFE_PROCESS_NAMES = {
    "sshd",          # SSH daemon
    "ssh",           # SSH client
    "code-server",   # VS Code remote
    "devtunnel",     # Visual Studio devtunnel
    "openvpn",       # OpenVPN
    "wsl",           # Windows Subsystem for Linux
    "docker",        # Docker Desktop
    "putty",         # PuTTY SSH client
    "remote",        # Generic remote service
}


def _run_powershell(command: str, timeout: float = 15.0) -> str:
    """Run a PowerShell command and return its stdout.

    Args:
        command: PowerShell command string
        timeout: Maximum execution time in seconds

    Returns:
        Stripped stdout output, or empty string on failure
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("PowerShell command failed: %s", exc)
        return ""


def find_port_owners() -> Dict[int, dict]:
    """Find processes currently using LibreVNA ports.

    Uses ``netstat -ano`` via PowerShell to scan for TCP/UDP listeners on
    the ports defined in LIBREVNA_PORTS.

    Returns:
        Dictionary mapping port number to {'pid': int, 'state': str,
        'protocol': str} for each occupied LibreVNA port.  Empty dict
        if no ports are in use or on non-Windows platforms.
    """
    if platform.system() != "Windows":
        logger.debug("Port cleanup is Windows-only; skipping find_port_owners()")
        return {}

    raw = _run_powershell("netstat -ano")
    if not raw:
        return {}

    results = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue

        # Skip header lines
        if parts[0] not in ("TCP", "UDP"):
            continue

        proto = parts[0]        # TCP or UDP
        local = parts[1]        # e.g. 0.0.0.0:19001
        state = parts[3] if proto == "TCP" else "N/A"

        try:
            pid = int(parts[-1])
        except ValueError:
            continue

        # Extract port number from local address
        try:
            port = int(local.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue

        # Only include ports we care about, first match wins
        if port in LIBREVNA_PORTS and port not in results:
            results[port] = {"pid": pid, "state": state, "protocol": proto}

    return results


def _get_process_name(pid: int) -> str:
    """Get the process name for a given PID via PowerShell.

    Args:
        pid: Process ID to look up

    Returns:
        Process name string, or "unknown" on failure
    """
    try:
        ps_script = f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName"
        result = _run_powershell(ps_script)
        return result if result else "unknown"
    except Exception:
        return "unknown"


def kill_port_users(port_owners: Dict[int, dict]) -> int:
    """Terminate processes using LibreVNA ports.

    Skips processes in SAFE_PROCESS_NAMES (SSH, remote development, VPN,
    etc.) to prevent breaking remote sessions.

    Args:
        port_owners: Dictionary from find_port_owners() mapping port to
            {'pid': int, 'state': str, 'protocol': str}

    Returns:
        Number of processes successfully terminated
    """
    if not port_owners:
        return 0

    if platform.system() != "Windows":
        logger.debug("Port cleanup is Windows-only; skipping kill_port_users()")
        return 0

    # Collect unique PIDs
    pids_to_kill = set(info["pid"] for info in port_owners.values())
    killed = 0

    for pid in pids_to_kill:
        # Find which ports this PID is using
        ports_used = [port for port, info in port_owners.items() if info["pid"] == pid]
        port_list = ", ".join(f":{p}" for p in sorted(ports_used))

        proc_name = _get_process_name(pid)

        # Skip critical remote/tunneling processes
        if proc_name.lower() in SAFE_PROCESS_NAMES:
            logger.info(
                "Port cleanup: SKIP PID %d (%s) using ports %s -- critical process",
                pid, proc_name, port_list,
            )
            continue

        logger.info(
            "Port cleanup: Terminating PID %d (%s) using ports %s",
            pid, proc_name, port_list,
        )
        try:
            _run_powershell(f"Stop-Process -Id {pid} -Force")
            killed += 1
        except Exception as exc:
            logger.warning("Port cleanup: Failed to kill PID %d: %s", pid, exc)

    # Brief pause to let the OS release port resources
    if killed > 0:
        time.sleep(1.0)

    return killed


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
        cwd=_MODULE_DIR,  # CWD = gui/mvp/ so .cal filenames resolve correctly
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

    # Explicitly close the SCPI connection before returning.
    # Without this, the socket lingers until GC runs __del__, which can
    # race with VNAPreviewWorker opening a new connection on the same port
    # and cause response misrouting (Root Cause #2 of preview bug).
    try:
        vna.close()
    except Exception:
        pass

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
            cal_file_path=self.cal_file_path,
            mode="continuous",
            summary=False,  # No console output in GUI
            save_data=False  # We'll handle saving separately
        )

        # Lifecycle state
        self.gui_process = None
        self.vna = None
        self.all_results: List[SweepResult] = []

        # Mutable GUI callback reference -- updated per-IFBW by run_single_ifbw_sweep().
        # The streaming callback wrapper reads this to dispatch sweep-complete events
        # to the GUI thread via Qt signals.  Set to None when no GUI callback is needed.
        self._gui_callback: Optional[Callable[[int, np.ndarray, np.ndarray], None]] = None

    def _create_temp_config(self) -> str:
        """
        Create a temporary sweep_config.yaml for BaseVNASweep consumption.

        Returns:
            Absolute path to temporary config file
        """
        import tempfile
        import yaml

        # Convert config_dict to YAML structure expected by BaseVNASweep.
        # Note: start_frequency, stop_frequency, and num_points are now
        # extracted from the .cal file by BaseVNASweep.parse_calibration_file(),
        # so they are NOT included in the YAML config.
        yaml_config = {
            'configurations': {
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
        Start GUI subprocess, connect to SCPI, load calibration, register streaming.

        This method mirrors the startup sequence in BaseVNASweep.run() but broken
        into explicit steps suitable for the GUI adapter:
          1. Start GUI subprocess
          2. Connect to SCPI server and verify device
          3. Load calibration file
          4. Enable streaming server (may require GUI restart)
          5. Install GUI callback hook (ONCE - reads mutable _gui_callback ref)
          6. Register streaming callback via pre_loop_reset()

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

        # Step 3: Enable streaming server (required for continuous mode).
        # enable_streaming_server() returns True if the preference was changed
        # and APPLYPREFERENCES terminated the GUI.  In that case we must restart.
        needs_restart = self.sweep.enable_streaming_server(self.vna)
        if needs_restart:
            logger.info("Streaming server enabled -- restarting GUI subprocess")
            self.sweep.stop_gui(self.gui_process)
            self.gui_process = self.sweep.start_gui()
            self.vna = self.sweep.connect_and_verify()

        # Step 4: Load calibration file (after potential restart so the new
        # GUI instance has the calibration loaded).
        try:
            self.sweep.load_calibration(self.vna, self.cal_file_path)
        except (FileNotFoundError, RuntimeError) as e:
            raise RuntimeError(f"Failed to load calibration: {self.cal_file_path}") from e

        # Step 5: Install the GUI callback hook ONCE.
        # This monkey-patches _make_callback so the streaming callback also
        # dispatches sweep-complete events to the GUI via _gui_callback.
        self._install_callback_hook_once()

        # Step 6: Register streaming callback via pre_loop_reset().
        # This sends ACQ:STOP and calls vna.add_live_callback() to connect
        # the TCP streaming client on port 19001.  Without this call, no
        # streaming data arrives and done_event is never set (root cause of
        # the infinite sweep loop bug).
        self.sweep.pre_loop_reset(self.vna)

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

        The streaming callback was registered ONCE in start_lifecycle() via
        pre_loop_reset().  This method only updates the mutable GUI callback
        reference and runs the sweep loop.

        Args:
            ifbw_hz: IF bandwidth in Hz
            callback: Called after each sweep with (sweep_idx, freq_hz, s11_db).
                      This should emit Qt signals for thread-safe GUI updates.
                      Set to None to disable GUI callbacks for this IFBW.

        Returns:
            SweepResult object with timing metrics and trace data
        """
        # Configure SCPI parameters for this IFBW
        self.sweep.configure_sweep(self.vna, ifbw_hz)

        # Update the mutable GUI callback reference.  The streaming callback
        # wrapper (installed once by _install_callback_hook_once) reads this
        # on every sweep completion.  No re-patching needed per IFBW.
        self._gui_callback = callback

        # Run the sweep loop (blocking until all sweeps complete or timeout).
        # The streaming callback accumulates data and sets done_event when
        # sweep_count reaches num_sweeps.
        result = self.sweep.run_sweeps(self.vna, ifbw_hz)

        # Store result for later xlsx export
        self.all_results.append(result)

        return result

    def _install_callback_hook_once(self):
        """
        Monkey-patch the sweep instance's _make_callback ONCE to inject GUI updates.

        This wraps _make_callback so that the streaming callback (created in
        pre_loop_reset) also dispatches sweep-complete events to the GUI via
        the mutable self._gui_callback reference.

        Must be called BEFORE pre_loop_reset(), which invokes _make_callback
        to create the actual streaming closure.

        The wrapper reads self._gui_callback on each sweep completion, so the
        GUI callback can be updated per-IFBW without re-patching.  This avoids
        the double-wrapping bug that occurred when _install_callback_hook was
        called once per IFBW.

        Thread safety: The wrapper runs on the streaming thread (libreVNA's
        TCP background thread).  It emits data via self._gui_callback which
        should call QThread.signal.emit() -- Qt handles the thread marshalling.
        """
        original_make_callback = self.sweep._make_callback
        adapter = self  # capture for closure

        def wrapped_make_callback(state_holder):
            # Get the original streaming callback (handles data accumulation
            # and done_event signaling)
            original_callback = original_make_callback(state_holder)

            # Wrap it to also dispatch to the GUI callback
            def gui_aware_callback(datapoint):
                # Call original callback first (accumulates data in _SweepState,
                # increments sweep_count, sets done_event when target reached)
                original_callback(datapoint)

                # After sweep completes (last point received), extract data for GUI
                state = state_holder[0]
                if state is None:
                    return

                if datapoint.get('pointNum') == state.num_points - 1:
                    # Last point of sweep -- full sweep data is now available
                    with state.lock:
                        if state.all_s11_complex:
                            sweep_idx = len(state.all_s11_complex) - 1
                            s11_complex = np.array(state.all_s11_complex[-1])

                            # Convert complex S11 to magnitude in dB
                            s11_db = 20 * np.log10(
                                np.maximum(np.abs(s11_complex), 1e-12)
                            )

                            # Build frequency array
                            freq_hz = np.linspace(
                                adapter.sweep.start_freq_hz,
                                adapter.sweep.stop_freq_hz,
                                adapter.sweep.num_points
                            )

                            # Dispatch to current GUI callback (if set)
                            cb = adapter._gui_callback
                            if cb is not None:
                                try:
                                    cb(sweep_idx, freq_hz, s11_db)
                                except Exception as exc:
                                    logger.warning(
                                        "GUI callback error (sweep %d): %s",
                                        sweep_idx, exc
                                    )

            return gui_aware_callback

        # Install monkey patch (ONCE -- never call this method again)
        self.sweep._make_callback = wrapped_make_callback

    def save_results(self, custom_dirname: Optional[str] = None) -> str:
        """
        Export all accumulated results to CSV bundle directory.

        Uses the backend's save_csv_bundle() method which writes to:
          {output_dir}/{mode}_sweep_test_{YYYYMMDD}_{HHMMSS}/
            s11_sweep_1.csv
            s11_sweep_2.csv
            ...
            summary.txt

        Each s11_sweep_N.csv contains columns: "Frequency (Hz)", "Magnitude (dB)"
        summary.txt contains sweep configuration, per-sweep timing, and metrics.

        Args:
            custom_dirname: Optional custom directory name (replaces auto-generated
                timestamp-based name). The directory will be created in the standard
                output directory (../../data/YYYYMMDD/).

        Returns:
            Absolute path to the output directory (not a file)
        """
        if not self.all_results:
            raise ValueError("No sweep results to save")

        # Build output directory (same as vna_backend.py default: ../../data/YYYYMMDD/)
        import datetime
        today = datetime.datetime.now().strftime("%Y%m%d")
        base_out_dir = os.path.join(_MODULE_DIR, "..", "..", "data", today)
        os.makedirs(base_out_dir, exist_ok=True)

        # Call save_csv_bundle() which returns the full output directory path
        bundle_dir = self.sweep.save_csv_bundle(self.all_results, output_dir=base_out_dir)

        if custom_dirname:
            # Rename the auto-generated directory to custom name
            custom_bundle_dir = os.path.join(base_out_dir, custom_dirname)
            try:
                if os.path.exists(custom_bundle_dir):
                    shutil.rmtree(custom_bundle_dir)  # Remove old directory if exists
                os.rename(bundle_dir, custom_bundle_dir)
                bundle_dir = custom_bundle_dir
            except Exception as exc:
                logger.warning("Could not rename bundle directory to custom name: %s", exc)
                # Fall back to auto-generated name (already saved)

        return bundle_dir

    def stop_lifecycle(self):
        """
        Teardown streaming, terminate GUI subprocess, and close connections.

        Cleanup sequence (order matters):
          1. post_loop_teardown() -- stop acquisition, restore single mode,
             remove streaming callback (requires live SCPI connection)
          2. Close SCPI socket and streaming threads (via libreVNA.close())
          3. Terminate LibreVNA-GUI subprocess (SIGTERM -> SIGKILL)
          4. Remove temporary config file

        Safe to call multiple times (idempotent).
        """
        # Step 1: Teardown streaming callback and stop acquisition.
        # This must happen BEFORE closing the SCPI connection because
        # post_loop_teardown sends ACQ:STOP and removes the live callback.
        if self.vna is not None:
            try:
                self.sweep.post_loop_teardown(self.vna)
            except Exception as exc:
                logger.warning("post_loop_teardown error (non-fatal): %s", exc)

        # Step 2: Close SCPI connection and streaming threads
        if self.vna is not None:
            try:
                self.vna.close()
            except Exception:
                pass
            self.vna = None

        # Step 3: Terminate GUI subprocess
        if self.gui_process:
            try:
                self.sweep.stop_gui(self.gui_process)
            except Exception:
                # Fallback: force-kill if stop_gui fails
                try:
                    self.gui_process.kill()
                    self.gui_process.wait(timeout=5)
                except Exception:
                    pass
            self.gui_process = None

        # Step 4: Clean up temp config file
        if hasattr(self, 'temp_config_path') and os.path.exists(self.temp_config_path):
            try:
                os.unlink(self.temp_config_path)
            except Exception:
                pass

        # Clear GUI callback reference
        self._gui_callback = None

    def get_device_serial(self) -> str:
        """Query device serial number (DEV:CONN?)."""
        if not self.vna:
            return "Not connected"

        try:
            serial = self.vna.query(":DEV:CONN?")
            return serial.strip()
        except Exception:
            return "Query failed"


# ===========================================================================
# GUIVNAMonitorAdapter  --  monitor mode backend for GUI
# ===========================================================================


class GUIVNAMonitorAdapter:
    """
    Adapter for monitor mode that captures per-sweep scalar data points
    (min-frequency S11) using the streaming infrastructure from ContinuousModeSweep.

    Lifecycle:
        adapter = GUIVNAMonitorAdapter(config_dict, cal_file_path)
        device_info = adapter.start_lifecycle()
        mean_ms = adapter.run_warmup()
        adapter.start_recording(point_callback, effective_log_interval_ms)
        # ... runs until stop or duration ...
        csv_path = adapter.stop_recording()
        adapter.stop_lifecycle()
    """

    def __init__(self, config_dict: dict, calibration_file_path: str):
        """
        Parameters
        ----------
        config_dict : dict
            Must contain:
                'stim_lvl_dbm': int
                'avg_count': int
                'ifbw_hz': int          -- single IFBW for monitor mode
                'warmup_sweeps': int    -- sweeps used to estimate sweep time
                'num_sweeps': int       -- used for warmup only
        calibration_file_path : str
            Absolute path to .cal file.
        """
        self.config = config_dict
        self.cal_file_path = calibration_file_path

        # Create temporary YAML config for ContinuousModeSweep
        self.temp_config_path = self._create_temp_config()

        # ContinuousModeSweep instance for SCPI lifecycle and streaming
        self.sweep = ContinuousModeSweep(
            config_path=self.temp_config_path,
            cal_file_path=self.cal_file_path,
            mode="continuous",
            summary=False,
            save_data=False,
        )

        # Lifecycle state
        self.gui_process = None
        self.vna = None
        self._vna_serial = "unknown"

        # Monitor recording state
        self._monitor_callback = None
        self._monitor_records: List[MonitorRecord] = []
        self._stop_event = None
        self._effective_log_interval_ms = 0.0

    def _create_temp_config(self) -> str:
        """Create a temporary sweep_config.yaml for ContinuousModeSweep."""
        import tempfile
        import yaml

        ifbw_hz = self.config.get('ifbw_hz', 50000)
        yaml_config = {
            'configurations': {
                'stim_lvl_dbm': self.config.get('stim_lvl_dbm', -10),
                'avg_count': self.config.get('avg_count', 1),
                'num_sweeps': self.config.get('warmup_sweeps', 5),
            },
            'target': {
                'ifbw_values': [ifbw_hz],
            }
        }

        fd, path = tempfile.mkstemp(suffix='.yaml', prefix='gui_monitor_')
        with os.fdopen(fd, 'w') as f:
            yaml.dump(yaml_config, f)

        return path

    def start_lifecycle(self) -> Dict[str, str]:
        """
        Start GUI subprocess, connect, load calibration, enable streaming.

        Returns
        -------
        dict
            Keys: 'serial', 'idn'.
        """
        # Start GUI
        self.gui_process = self.sweep.start_gui()

        # Connect and verify
        self.vna = self.sweep.connect_and_verify()

        # Capture serial
        try:
            idn_raw = self.vna.query("*IDN?")
            parts = [p.strip() for p in idn_raw.split(",")]
            self._vna_serial = parts[2] if len(parts) > 2 else "unknown"
        except Exception:
            idn_raw = "unknown"
            self._vna_serial = "unknown"

        # Enable streaming server (may restart GUI)
        needs_restart = self.sweep.enable_streaming_server(self.vna)
        if needs_restart:
            self.sweep.stop_gui(self.gui_process)
            self.gui_process = self.sweep.start_gui()
            self.vna = self.sweep.connect_and_verify()
            try:
                idn_raw = self.vna.query("*IDN?")
                parts = [p.strip() for p in idn_raw.split(",")]
                self._vna_serial = parts[2] if len(parts) > 2 else "unknown"
            except Exception:
                pass

        # Load calibration
        self.sweep.load_calibration(self.vna, self.cal_file_path)

        # Configure sweep with the single IFBW
        ifbw_hz = self.config.get('ifbw_hz', 50000)
        self.sweep.configure_sweep(self.vna, ifbw_hz)

        # Register streaming callback once
        self.sweep.pre_loop_reset(self.vna)

        return {
            'serial': self._vna_serial,
            'idn': idn_raw,
        }

    def run_warmup(self, warmup_sweeps: int = 5) -> float:
        """
        Run warmup sweeps and return mean sweep time in milliseconds.

        Uses ContinuousModeSweep's streaming loop with a temporary num_sweeps.

        Parameters
        ----------
        warmup_sweeps : int
            Number of warmup sweeps.

        Returns
        -------
        float
            Mean sweep duration in milliseconds.
        """
        ifbw_hz = self.config.get('ifbw_hz', 50000)

        # Temporarily override num_sweeps for warmup
        original_num_sweeps = self.sweep.num_sweeps
        self.sweep.num_sweeps = warmup_sweeps

        try:
            result = self.sweep._continuous_sweep_loop(self.vna, ifbw_hz)
        finally:
            self.sweep.num_sweeps = original_num_sweeps

        if not result.sweep_times:
            raise RuntimeError("Warmup produced no completed sweeps.")

        mean_ms = float(np.mean(result.sweep_times)) * 1000.0
        logger.info("Warmup: %d sweeps, mean=%.1f ms", len(result.sweep_times), mean_ms)
        return mean_ms

    def start_recording(
        self,
        point_callback: Optional[Callable] = None,
        effective_log_interval_ms: float = 0.0,
        preview_callback: Optional[Callable] = None,
    ):
        """
        Start the monitor recording loop.

        Registers a streaming callback that extracts per-sweep scalar data
        (min S11 dB + corresponding frequency) and applies log interval gating.

        Parameters
        ----------
        point_callback : callable or None
            Called with (MonitorRecord) for each logged point.
            Should emit Qt signal for thread-safe GUI update.
        effective_log_interval_ms : float
            Minimum interval between logged points.  0 = log every sweep.
        preview_callback : callable or None
            Called with (freqs_hz: list, s11_db: list) after each complete
            sweep for live plot updates.  The frequency list is in Hz and
            s11_db is magnitude in dB.
        """
        import threading as _threading
        import math as _math
        from datetime import datetime as _dt

        self._effective_log_interval_ms = effective_log_interval_ms
        self._monitor_records = []
        self._stop_event = _threading.Event()

        freq_hz_axis = np.linspace(
            float(self.sweep.start_freq_hz),
            float(self.sweep.stop_freq_hz),
            self.sweep.num_points,
        )

        # Shared mutable state for the callback
        mon_state = {
            "current_s11": [],
            "last_log_time_ms": None,
            "record_count": 0,
        }
        num_points = self.sweep.num_points
        stop_event = self._stop_event
        records = self._monitor_records

        def _monitor_cb(data):
            if stop_event.is_set():
                return
            if "Z0" not in data:
                return

            point_num = data["pointNum"]
            s11_complex = data["measurements"].get("S11", complex(0, 0))
            point_time = time.time()

            if point_num == 0:
                mon_state["current_s11"] = []

            mon_state["current_s11"].append(s11_complex)

            if point_num == num_points - 1:
                collected = list(mon_state["current_s11"])
                if len(collected) != num_points:
                    return  # partial sweep

                sweep_ts = _dt.now()

                # Convert to dB
                s11_db = np.array([
                    20.0 * _math.log10(max(abs(g), 1e-12))
                    for g in collected
                ])

                # Emit full sweep preview for live plot update
                if preview_callback is not None:
                    try:
                        preview_callback(
                            freq_hz_axis.tolist(), s11_db.tolist()
                        )
                    except Exception as exc:
                        logger.warning("Preview callback error: %s", exc)

                # Find minimum
                min_idx = int(np.argmin(s11_db))
                min_freq = float(freq_hz_axis[min_idx])
                min_s11_db = float(s11_db[min_idx])

                # Log-interval gating
                last_ms = mon_state["last_log_time_ms"]
                now_ms = point_time * 1000.0
                if (
                    last_ms is None
                    or (now_ms - last_ms) >= effective_log_interval_ms
                ):
                    record = MonitorRecord(
                        timestamp=sweep_ts,
                        freq_hz=min_freq,
                        s11_db=min_s11_db,
                    )
                    records.append(record)
                    mon_state["last_log_time_ms"] = now_ms
                    mon_state["record_count"] += 1

                    if point_callback is not None:
                        try:
                            point_callback(record)
                        except Exception as exc:
                            logger.warning("Monitor callback error: %s", exc)

        self._monitor_callback = _monitor_cb

        # Register monitor callback on the streaming port
        self.vna.add_live_callback(STREAMING_PORT, _monitor_cb)
        logger.info("Monitor callback registered on port %d", STREAMING_PORT)

        # Start continuous acquisition
        self.vna.cmd(":VNA:ACQ:STOP")
        time.sleep(0.1)  # drain stale data
        self.vna.cmd(":VNA:ACQ:SINGLE FALSE")
        self.vna.cmd(":VNA:ACQ:RUN")
        logger.info("Monitor acquisition started")

    def stop_recording(self) -> Optional[str]:
        """
        Stop the monitor recording and export Dataflux CSV.

        Returns
        -------
        str or None
            Path to the exported CSV, or None if no records.
        """
        # Signal callback to stop
        if self._stop_event:
            self._stop_event.set()

        # Stop acquisition
        if self.vna:
            try:
                self.vna.cmd(":VNA:ACQ:STOP")
            except Exception:
                pass
            try:
                self.vna.cmd(":VNA:ACQ:SINGLE TRUE")
            except Exception:
                pass

        # Remove monitor callback
        if self._monitor_callback and self.vna:
            try:
                self.vna.remove_live_callback(STREAMING_PORT, self._monitor_callback)
            except Exception:
                pass
            self._monitor_callback = None

        # Export Dataflux CSV
        if not self._monitor_records:
            logger.info("No monitor records to export")
            return None

        ifbw_hz = self.config.get('ifbw_hz', 50000)
        csv_path = export_dataflux_csv(
            records=self._monitor_records,
            vna_serial=self._vna_serial,
            ifbw_hz=ifbw_hz,
            effective_log_interval_ms=self._effective_log_interval_ms,
            start_freq_hz=self.sweep.start_freq_hz,
            stop_freq_hz=self.sweep.stop_freq_hz,
            num_points=self.sweep.num_points,
        )
        logger.info("Monitor CSV exported: %s (records=%d)",
                     csv_path, len(self._monitor_records))
        return csv_path

    def stop_lifecycle(self):
        """
        Teardown streaming, terminate GUI subprocess, cleanup.

        Safe to call multiple times (idempotent).
        """
        # Stop recording if still active
        if self._stop_event and not self._stop_event.is_set():
            self.stop_recording()

        # Teardown streaming callback from ContinuousModeSweep
        if self.vna:
            try:
                self.sweep.post_loop_teardown(self.vna)
            except Exception as exc:
                logger.warning("post_loop_teardown error: %s", exc)

        # Close SCPI connection
        if self.vna:
            try:
                self.vna.close()
            except Exception:
                pass
            self.vna = None

        # Terminate GUI subprocess
        if self.gui_process:
            try:
                self.sweep.stop_gui(self.gui_process)
            except Exception:
                try:
                    self.gui_process.kill()
                    self.gui_process.wait(timeout=5)
                except Exception:
                    pass
            self.gui_process = None

        # Cleanup temp config
        if hasattr(self, 'temp_config_path') and os.path.exists(self.temp_config_path):
            try:
                os.unlink(self.temp_config_path)
            except Exception:
                pass
