#!/usr/bin/env python3
"""
6_librevna_gui_mode_sweep_test.py
-----------------------------------
Unified single-sweep / continuous-sweep benchmark and physiological-signal
monitor for LibreVNA.

Reads sweep frequency range and point count from the calibration file
(.cal, JSON format) and remaining parameters (stimulus level, averaging,
IFBW values) from sweep_config.yaml.  Runs the requested mode (single,
continuous, or monitor) and produces the appropriate output.

Class hierarchy
---------------
    BaseVNASweep            (ABC)  -- shared lifecycle, GUI, cal, CSV export
    SingleModeSweep         (BaseVNASweep)  -- single-sweep trigger + poll
    ContinuousModeSweep     (BaseVNASweep)  -- streaming callback loop
    MonitorModeSweep        (ContinuousModeSweep)
                            -- physiological signal capture; warm-up + gated
                               logging; exports Dataflux-compatible CSV
    VNAGUIModeSweepTest     (SingleModeSweep, ContinuousModeSweep)
                            -- dispatches to the correct parent based on mode

SCPI commands used -- all documented in ProgrammingGuide.pdf
------------------------------------------------------------
  *IDN?                        4.1.1   identification string
  DEVice:CONNect?              4.2.2   serial of connected device
  DEVice:MODE VNA              4.2.6   switch to VNA mode
  VNA:SWEEP FREQUENCY          4.3.1   frequency-sweep type
  VNA:STIMulus:LVL    <dBm>    4.3.24  stimulus output power
  VNA:ACquisition:IFBW <Hz>    4.3.13  IF bandwidth
  VNA:ACquisition:AVG  <n>     4.3.16  averaging count
  VNA:ACquisition:POINTS <n>   4.3.15  points per sweep
  VNA:FREQuency:START <Hz>     4.3.3   start frequency
  VNA:FREQuency:STOP  <Hz>     4.3.5   stop frequency
  VNA:ACquisition:FINished?    4.3.18  TRUE when averaging complete
  VNA:ACquisition:SINGLE <B>   4.3.20  TRUE=single / FALSE=continuous
  VNA:ACquisition:STOP         4.3.12  halt acquisition
  VNA:ACquisition:RUN          4.3.11  start acquisition
  VNA:TRACe:DATA? S11          4.3.27  [freq,re,im] tuples
  VNA:CALibration:LOAD? <file> 4.3.55  load cal file (query)
  VNA:CALibration:ACTIVE?      4.3.45  active cal type (query)

Prerequisites
-------------
CONTINUOUS / MONITOR MODE:
  * The VNA Calibrated Data streaming server (port 19001) is automatically
    enabled by the script if not already running.  The first continuous-mode
    run will restart the GUI to enable streaming; subsequent runs will use
    the fast path (no restart needed).

BOTH MODES:
  * A calibrated 50-ohm matched load is connected to port 1.
  * The data/ directory is a sibling of scripts/ under LibreVNA-dev/.

Usage
-----
    uv run python 6_librevna_gui_mode_sweep_test.py --cal-file /path/to/cal.cal
    uv run python 6_librevna_gui_mode_sweep_test.py --cal-file /path/to/cal.cal --mode continuous
    uv run python 6_librevna_gui_mode_sweep_test.py --cal-file /path/to/cal.cal --mode monitor
    uv run python 6_librevna_gui_mode_sweep_test.py --cal-file /path/to/cal.cal --mode monitor --duration 60
    uv run python 6_librevna_gui_mode_sweep_test.py --cal-file /path/to/cal.cal --mode monitor --log-interval 500
    uv run python 6_librevna_gui_mode_sweep_test.py --cal-file /path/to/cal.cal --config /path/to/other.yaml --no-save

Output
------
DEFAULT / SINGLE / CONTINUOUS MODES:
    If save_data is enabled (default), produces:
        data/YYYYMMDD/{mode}_sweep_test_{YYYYMMDD}_{HHMMSS}/
            s11_sweep_1.csv
            s11_sweep_2.csv
            ...
            s11_sweep_N.csv
            summary.txt

MONITOR MODE:
    Produces a single Dataflux-compatible CSV:
        data/YYYYMMDD/vna_monitor_{YYYYMMDD}_{HHMMSS}.csv

    CSV header format:
        Application,VNA-DATAFLUX
        VNA Model,LibreVNA
        VNA Serial,<serial>
        File Name,<filename>
        Start DateTime,<ISO 8601>
        Number of Data,<row count>
        Log Interval(ms),<effective ms>
        Freq Start(MHz),<start>
        Freq Stop(MHz),<stop>
        Freq Span(MHz),<span>
        IF Bandwidth(KHz),<ifbw>
        Points,<n>
        (blank)
        (blank)
        Time,Marker Stimulus (Hz),Marker Y Real Value (dB)
        HH:MM:SS.ffffff,+X.XXXXXXXXXE+008,-X.XXXXXXXXXE+000
        ...
"""

import sys
import os
import platform
import math
import time
import json
import socket
import subprocess
import threading
import importlib
import argparse
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import csv
import yaml
import numpy as np
from prettytable import PrettyTable

# ---------------------------------------------------------------------------
# Paths -- all relative to this script's location so the whole tree is
# portable regardless of where it is checked out.
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Insert SCRIPT_DIR so that "from libreVNA import libreVNA" resolves to the
# co-located wrapper regardless of cwd.
sys.path.insert(0, SCRIPT_DIR)
from libreVNA import libreVNA  # noqa: E402

# ---------------------------------------------------------------------------
# Module-level constants (GUI lifecycle, SCPI connection)
# ---------------------------------------------------------------------------

# OS-dependent GUI binary path
if platform.system() == "Windows":
    GUI_BINARY = os.path.normpath(
        os.path.join(
            SCRIPT_DIR, "..", "tools", "LibreVNA-GUI", "release", "LibreVNA-GUI.exe"
        )
    )
else:
    GUI_BINARY = os.path.normpath(
        os.path.join(SCRIPT_DIR, "..", "tools", "LibreVNA-GUI")
    )
# CAL_FILE_PATH removed -- now supplied via the mandatory --cal-file CLI argument
# and stored as self.cal_file_path on BaseVNASweep instances.
DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "data"))

SCPI_HOST = "localhost"
SCPI_PORT = 19542
GUI_START_TIMEOUT_S = 30.0

# Polling / timeout constants for the single-sweep poll loop
POLL_INTERVAL_S = 0.01
SWEEP_TIMEOUT_S = 60.0

# Streaming port for continuous mode (VNA Calibrated Data)
STREAMING_PORT = 19001
CONTINUOUS_TIMEOUT_S = 300  # hard ceiling on event.wait()

# ---------------------------------------------------------------------------
# Console-output helpers (identical style to scripts 1-5)
# ---------------------------------------------------------------------------


def _section(title):
    """Print a dashed section header."""
    width = 70
    print("\n" + "=" * width)
    print("  " + title)
    print("=" * width)


def _subsection(title):
    """Print a lighter sub-header."""
    print("\n  --- " + title + " ---")


# ---------------------------------------------------------------------------
# SweepResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    """Container for one complete IFBW run (all sweeps at that setting)."""

    mode: str  # "single" or "continuous"
    ifbw_hz: int
    sweep_times: list  # list[float] wall-clock seconds per sweep
    all_s11_db: list  # list[list[float]] [sweep_idx][point_idx]
    freq_hz: list  # list[float] frequency axis
    all_timestamps: list = field(default_factory=list)  # list[list[float]] [sweep_idx][point_idx] epoch timestamps
    noise_floor: float = 0.0  # filled by compute_metrics
    trace_jitter: float = 0.0  # filled by compute_metrics


# ---------------------------------------------------------------------------
# MonitorRecord dataclass
# ---------------------------------------------------------------------------


@dataclass
class MonitorRecord:
    """One logged data point captured during Monitor Mode."""

    timestamp: datetime   # wall-clock time of the completed sweep
    freq_hz: float        # frequency (Hz) where S11 is minimum
    s11_db: float         # S11 magnitude (dB) at that frequency


# ===========================================================================
# BaseVNASweep  --  abstract base class
# ===========================================================================


class BaseVNASweep(ABC):
    """
    Shared lifecycle, GUI management, calibration loading, metric
    computation, console summary, and CSV export.  Concrete sweep
    logic (configure + run) is left to the subclasses.
    """

    @staticmethod
    def parse_calibration_file(cal_file_path):
        """
        Parse a LibreVNA .cal file (JSON) and extract sweep parameters.

        The calibration file contains a 'measurements' array where each
        measurement has 'data.points' -- an array of {frequency, real, imag}
        objects.  The start frequency is the first point's frequency, the
        stop frequency is the last point's frequency, and num_points is
        the length of the points array.

        All measurements within a single .cal file share the same frequency
        grid, so only the first measurement is inspected.

        Parameters
        ----------
        cal_file_path : str
            Absolute or relative path to the .cal file.

        Returns
        -------
        dict
            Keys: 'start_frequency' (int, Hz),
                  'stop_frequency'  (int, Hz),
                  'num_points'      (int).

        Raises
        ------
        FileNotFoundError
            If the file does not exist on disk.
        ValueError
            If the file is not valid JSON, is missing required keys,
            or contains no measurement data.
        """
        cal_abs = os.path.normpath(cal_file_path)

        if not os.path.isfile(cal_abs):
            raise FileNotFoundError(
                "Calibration file not found: {}".format(cal_abs)
            )

        try:
            with open(cal_abs, "r") as fh:
                cal_data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Calibration file is not valid JSON: {}: {}".format(cal_abs, exc)
            )

        # -- Validate required structure ----------------------------------------
        if "measurements" not in cal_data:
            raise ValueError(
                "Calibration file missing 'measurements' key: {}".format(cal_abs)
            )

        measurements = cal_data["measurements"]
        if not isinstance(measurements, list) or len(measurements) == 0:
            raise ValueError(
                "Calibration file has no measurements: {}".format(cal_abs)
            )

        first_meas = measurements[0]

        if "data" not in first_meas:
            raise ValueError(
                "First measurement missing 'data' key: {}".format(cal_abs)
            )

        if "points" not in first_meas["data"]:
            raise ValueError(
                "First measurement missing 'data.points' key: {}".format(cal_abs)
            )

        points = first_meas["data"]["points"]
        if not isinstance(points, list) or len(points) == 0:
            raise ValueError(
                "First measurement has no calibration points: {}".format(cal_abs)
            )

        # -- Extract frequency range and point count ----------------------------
        first_freq = points[0].get("frequency")
        last_freq = points[-1].get("frequency")

        if first_freq is None or last_freq is None:
            raise ValueError(
                "Calibration points missing 'frequency' field: {}".format(cal_abs)
            )

        start_frequency = int(round(first_freq))
        stop_frequency = int(round(last_freq))
        num_points = len(points)

        if start_frequency >= stop_frequency:
            raise ValueError(
                "Invalid frequency range in calibration file: start={} Hz >= "
                "stop={} Hz: {}".format(start_frequency, stop_frequency, cal_abs)
            )

        if num_points < 2:
            raise ValueError(
                "Calibration file has fewer than 2 points ({}): {}".format(
                    num_points, cal_abs
                )
            )

        return {
            "start_frequency": start_frequency,
            "stop_frequency": stop_frequency,
            "num_points": num_points,
        }

    def __init__(self, config_path, cal_file_path, mode, summary=True, save_data=True):
        """
        Parameters
        ----------
        config_path   : str   -- absolute path to the YAML config file.
        cal_file_path : str   -- path to the calibration file (.cal).
        mode          : str   -- "single", "continuous", or "monitor".
        summary       : bool  -- if True, print the PrettyTable at the end.
        save_data     : bool  -- if True, write the CSV bundle.
        """
        self.mode = mode
        self.cal_file_path = os.path.normpath(cal_file_path)
        self.summary = summary
        self.save_data = save_data

        # -- Extract frequency range and num_points from the .cal file ---------
        # The calibration file is the single source of truth for sweep
        # boundaries.  This prevents misconfiguration where the YAML config
        # specifies a different range than what the calibration covers.
        cal_params = self.parse_calibration_file(self.cal_file_path)
        self.start_freq_hz = cal_params["start_frequency"]
        self.stop_freq_hz = cal_params["stop_frequency"]
        self.num_points = cal_params["num_points"]

        # -- Load remaining parameters from YAML config ------------------------
        with open(config_path, "r") as fh:
            raw = yaml.safe_load(fh)

        cfg = raw["configurations"]
        tgt = raw["target"]

        self.stim_lvl_dbm = int(cfg["stim_lvl_dbm"])
        self.avg_count = int(cfg["avg_count"])
        self.num_sweeps = int(cfg["num_sweeps"])

        # -- Normalise ifbw_values: accept new target.default.ifbw_values
        #    or fall back to legacy flat target.ifbw_values with a deprecation
        #    warning.  MonitorModeSweep overrides this entirely.
        if "default" in tgt:
            raw_ifbw = tgt["default"]["ifbw_values"]
        elif "ifbw_values" in tgt:
            print(
                "  [DEPRECATION WARNING] sweep_config.yaml: 'target.ifbw_values' "
                "is deprecated.  Move it under 'target.default.ifbw_values'."
            )
            raw_ifbw = tgt["ifbw_values"]
        else:
            raise KeyError(
                "sweep_config.yaml: 'target' must contain either "
                "'default.ifbw_values' or the legacy 'ifbw_values' key."
            )

        if isinstance(raw_ifbw, list):
            self.ifbw_values = [int(v) for v in raw_ifbw]
        else:
            self.ifbw_values = [int(raw_ifbw)]

    # -----------------------------------------------------------------------
    # GUI lifecycle
    # -----------------------------------------------------------------------

    def start_gui(self):
        """
        Launch LibreVNA-GUI in headless mode and poll TCP port SCPI_PORT
        until the SCPI server accepts a connection.  Returns the Popen handle.
        """
        _section("STARTING LibreVNA-GUI")

        env = os.environ.copy()
        # Only set offscreen platform on Linux/macOS where it's available
        # Windows Qt builds only include qwindows.dll (requires desktop session)
        if platform.system() != "Windows":
            env["QT_QPA_PLATFORM"] = "offscreen"

        proc = subprocess.Popen(
            [GUI_BINARY, "--port", str(SCPI_PORT), "--no-gui"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  GUI PID         : {}".format(proc.pid))

        deadline = time.time() + GUI_START_TIMEOUT_S
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((SCPI_HOST, SCPI_PORT))
                s.close()
                print("  SCPI server     : ready on {}:{}".format(SCPI_HOST, SCPI_PORT))
                return proc
            except (ConnectionRefusedError, OSError):
                s.close()
            if time.time() > deadline:
                proc.terminate()
                proc.wait()
                raise RuntimeError(
                    "LibreVNA-GUI did not open SCPI server on port {} "
                    "within {:.0f} s".format(SCPI_PORT, GUI_START_TIMEOUT_S)
                )
            time.sleep(0.25)

    def stop_gui(self, proc):
        """
        Terminate the GUI subprocess gracefully (SIGTERM) with a 5 s
        timeout, escalating to SIGKILL if needed.
        """
        _section("STOPPING LibreVNA-GUI")
        proc.terminate()
        try:
            proc.wait(timeout=5)
            print("  GUI terminated  : PID {} (clean)".format(proc.pid))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            print("  GUI killed      : PID {} (forced)".format(proc.pid))

    # -----------------------------------------------------------------------
    # Device connection
    # -----------------------------------------------------------------------

    def connect_and_verify(self):
        """
        Open a TCP connection to LibreVNA-GUI and confirm a hardware device
        is attached.  Raises RuntimeError on any failure (the GUI was just
        started by this script so a connection problem is unexpected).

        Returns
        -------
        libreVNA
            Connected and verified wrapper instance.
        """
        _section("DEVICE CONNECTION")

        try:
            vna = libreVNA(host=SCPI_HOST, port=SCPI_PORT)
            print("  TCP connection  : OK  ({}:{})".format(SCPI_HOST, SCPI_PORT))
        except Exception as exc:
            raise RuntimeError(
                "Could not connect to LibreVNA-GUI at {}:{}: {}".format(
                    SCPI_HOST, SCPI_PORT, exc
                )
            )

        _subsection("*IDN? identification")
        try:
            idn_raw = vna.query("*IDN?")
            print("  Raw response    : {}".format(idn_raw))
            parts = [p.strip() for p in idn_raw.split(",")]
            labels = ["Manufacturer", "Model", "Serial (IDN)", "SW Version"]
            for label, val in zip(labels, parts):
                print("    {:<22s}: {}".format(label, val))
        except Exception as exc:
            print("  [WARN] *IDN? query failed: {}".format(exc))

        _subsection("DEVice:CONNect? -- device serial")
        try:
            dev_serial = vna.query(":DEV:CONN?")
            print("  Live serial     : {}".format(dev_serial))
            if dev_serial == "Not connected":
                raise RuntimeError(
                    "LibreVNA-GUI is not connected to any hardware device."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("DEVice:CONNect? query failed: {}".format(exc))

        return vna

    # -----------------------------------------------------------------------
    # Calibration
    # -----------------------------------------------------------------------

    def load_calibration(self, vna: libreVNA) -> None:
        """
        Resolve the calibration file path, verify it exists on the local
        filesystem, and load it into LibreVNA-GUI via SCPI.

        The function sends two queries in order:

        1. VNA:CALibration:LOAD? <filename>   (ProgrammingGuide 4.3.55)
                Instructs the GUI to read and ingest the .cal file.
                Returns "TRUE" on success, "FALSE" otherwise.
                The filename must be absolute or relative to the GUI
                application (see the note at the end of 4.3.54).

        2. VNA:CALibration:ACTIVE?            (ProgrammingGuide 4.3.45)
                Queries the currently active calibration type (e.g. "SOLT").
                Sent only after a successful LOAD to confirm the GUI has
                applied the calibration.

        Both are queries -- vna.query() must be used, not vna.cmd().

        The calibration file path is taken from self.cal_file_path, which
        is set via the --cal-file CLI argument and normalised in __init__.

        Parameters
        ----------
        vna : libreVNA
            Connected wrapper instance returned by connect_and_verify().

        Raises
        ------
        SystemExit
            If the file does not exist on disk or the LOAD query does not
            return "TRUE".
        """

        _section("CALIBRATION LOADING")

        # -- Resolve and validate the path ---------------------------------------
        cal_abs_path = os.path.normpath(self.cal_file_path)
        print("  Cal file path   : {}".format(cal_abs_path))

        if not os.path.isfile(cal_abs_path):
            print("  [FAIL] Calibration file not found on disk:")
            print("         {}".format(cal_abs_path))
            print("         Verify the file exists and the path passed via")
            print("         --cal-file is correct, then re-run.")
            sys.exit(1)

        print("  File exists     : YES")

        # -- VNA:CALibration:LOAD? <filename> ------------------------------------
        # ProgrammingGuide 4.3.55 -- query, returns TRUE or FALSE.
        # Filenames must be absolute or relative to the GUI application; we
        # always send the normalised absolute path to avoid ambiguity.
        load_response = vna.query(":VNA:CAL:LOAD? " + cal_abs_path)
        print("  LOAD? response  : {}".format(load_response))

        if load_response != "TRUE":
            print("  [FAIL] VNA:CALibration:LOAD? returned '{}'".format(load_response))
            print("         Possible causes:")
            print("           - The GUI process cannot access the path above")
            print("             (e.g. it runs on a different machine or as a")
            print("             different user).")
            print("           - The file is not a valid LibreVNA calibration file.")
            print("         Action: confirm the GUI can open the file manually,")
            print("         then re-run this script.")
            sys.exit(1)

        # -- VNA:CALibration:ACTIVE? --------------------------------------------
        # ProgrammingGuide 4.3.45 -- query, returns the active cal type string.
        active_cal = vna.query(":VNA:CAL:ACTIVE?")
        print("  Active cal type : {}".format(active_cal))

    def enable_streaming_server(self, vna):
        """
        Ensure the VNA Calibrated Data streaming server is enabled on port 19001.

        If the streaming server is already enabled (port 19001 is listening),
        this method returns False immediately (fast path).

        If the streaming server is disabled, this method enables it via SCPI:
            :DEV:PREF StreamingServers.VNACalibratedData.enabled true
            :DEV:APPLYPREFERENCES

        Note that APPLYPREFERENCES saves the preference to disk and terminates
        the GUI.  The caller (run()) must stop the old GUI and start a new one.

        Parameters
        ----------
        vna : libreVNA
            The currently active connection (will become stale after this call).

        Returns
        -------
        bool
            True if the preference was set (caller must restart GUI).
            False if streaming was already enabled (no restart needed).
        """
        _section("STREAMING SERVER SETUP")

        # Test if streaming server is already listening
        print("  Testing port {} ...".format(STREAMING_PORT))
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect((SCPI_HOST, STREAMING_PORT))
            s.close()
            print("  Status          : already enabled (fast path)")
            return False  # no restart needed
        except (ConnectionRefusedError, OSError):
            s.close()
            print("  Status          : not enabled, enabling now...")

        # Enable streaming server via SCPI
        # DEV:PREF set returns CME bit even on success -- use check=False
        print(
            "  Sending         : DEV:PREF StreamingServers.VNACalibratedData.enabled true"
        )
        vna.cmd(
            ":DEV:PREF StreamingServers.VNACalibratedData.enabled true", check=False
        )

        print("  Sending         : DEV:APPLYPREFERENCES")
        vna.cmd(":DEV:APPLYPREFERENCES", check=False)

        # APPLYPREFERENCES saves the preference to disk and terminates the GUI.
        # Give it a moment to save, then let the caller handle the restart.
        print("  Preference      : saved to disk")
        print("  [INFO] GUI will terminate now; caller must restart it")
        time.sleep(2)  # brief pause to ensure preference is saved

        return True  # caller must restart GUI

    # -----------------------------------------------------------------------
    # Abstract methods -- implemented by the single / continuous subclasses
    # -----------------------------------------------------------------------

    @abstractmethod
    def configure_sweep(self, vna, ifbw_hz):
        """Configure the VNA for a sweep at the given IFBW."""
        ...

    @abstractmethod
    def run_sweeps(self, vna, ifbw_hz):
        """
        Execute self.num_sweeps sweeps and return a SweepResult.

        Parameters
        ----------
        vna     : libreVNA
        ifbw_hz : int

        Returns
        -------
        SweepResult
        """
        ...

    # -----------------------------------------------------------------------
    # Metric computation (shared)
    # -----------------------------------------------------------------------

    def compute_metrics(self, result):
        """
        Fill result.noise_floor and result.trace_jitter in-place.

        Noise floor  = mean( per-sweep mean S11_dB across all freq points )
        Trace jitter = mean( per-point std across sweeps, ddof=1 )

        Parameters
        ----------
        result : SweepResult
            Must have all_s11_db populated.
        """
        # Filter out any sweeps whose length differs from the expected
        # num_points (e.g. partial sweeps from a streaming boundary miss).
        expected_len = len(result.freq_hz)
        valid_sweeps = [
            s for s in result.all_s11_db if len(s) == expected_len
        ]
        if len(valid_sweeps) < len(result.all_s11_db):
            n_dropped = len(result.all_s11_db) - len(valid_sweeps)
            print(
                "  [WARN] compute_metrics: dropped {} sweep(s) with "
                "wrong point count (expected {})".format(n_dropped, expected_len)
            )
        if len(valid_sweeps) == 0:
            print("  [WARN] compute_metrics: no valid sweeps -- metrics set to 0")
            result.noise_floor = 0.0
            result.trace_jitter = 0.0
            return

        s11_arr = np.array(valid_sweeps)  # shape (num_valid_sweeps, num_points)

        # Noise floor
        per_sweep_means = np.mean(s11_arr, axis=1)  # shape (num_sweeps,)
        result.noise_floor = float(np.mean(per_sweep_means))

        # Trace jitter
        per_point_stds = np.std(s11_arr, axis=0, ddof=1)  # shape (num_points,)
        result.trace_jitter = float(np.mean(per_point_stds))

    # -----------------------------------------------------------------------
    # Console summary (PrettyTable)
    # -----------------------------------------------------------------------

    def print_summary(self, all_results):
        """
        Print a PrettyTable with one row per IFBW result.

        Columns: Mode | IFBW kHz | Mean Time s | Std s | Min s | Max s |
                 Rate Hz | Noise Floor dB | Jitter dB

        Parameters
        ----------
        all_results : list[SweepResult]
        """
        _section("SWEEP TEST SUMMARY  ({} mode)".format(self.mode))

        table = PrettyTable()
        table.field_names = [
            "Mode",
            "IFBW (kHz)",
            "Mean Time (s)",
            "Std Dev (s)",
            "Min Time (s)",
            "Max Time (s)",
            "Rate (Hz)",
            "Noise Floor (dB)",
            "Trace Jitter (dB)",
        ]

        for r in all_results:
            times_arr = np.array(r.sweep_times)
            mean_t = float(np.mean(times_arr))
            std_t = float(np.std(times_arr, ddof=1)) if len(times_arr) > 1 else 0.0
            min_t = float(np.min(times_arr))
            max_t = float(np.max(times_arr))
            rate = 1.0 / mean_t if mean_t > 0 else float("inf")

            table.add_row(
                [
                    r.mode,
                    "{:d}".format(r.ifbw_hz // 1000),
                    "{:.4f}".format(mean_t),
                    "{:.4f}".format(std_t),
                    "{:.4f}".format(min_t),
                    "{:.4f}".format(max_t),
                    "{:.2f}".format(rate),
                    "{:.2f}".format(r.noise_floor),
                    "{:.4f}".format(r.trace_jitter),
                ]
            )

        print(table)

    # -----------------------------------------------------------------------
    # CSV bundle export
    # -----------------------------------------------------------------------

    def save_csv_bundle(self, all_results):
        """
        Write a directory-based CSV bundle.

        Directory structure
        -------------------
        data/YYYYMMDD/{mode}_sweep_test_{YYYYMMDD}_{HHMMSS}/
            s11_sweep_1.csv
            s11_sweep_2.csv
            ...
            s11_sweep_N.csv
            summary.txt

        Each s11_sweep_N.csv contains:
            Time, Frequency (Hz), Magnitude (dB)

        summary.txt contains PrettyTable-formatted sections:
            1. Sweep Configuration (mode, IFBW, freq range, points, etc.)
            2. Per-Sweep Timing (sweep #, sweep time, update rate)
            3. Summary Metrics (mean, std, min, max, rate, noise floor, jitter)

        Parameters
        ----------
        all_results : list[SweepResult]

        Returns
        -------
        str
            Absolute path of the output directory.
        """
        # -- Output directory: ../data/YYYYMMDD/{mode}_sweep_test_{timestamp}/ --
        today = datetime.now().strftime("%Y%m%d")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dir_name = "{}_sweep_test_{}".format(self.mode, timestamp)
        out_dir = os.path.join(DATA_DIR, today, dir_name)
        os.makedirs(out_dir, exist_ok=True)

        # Combine all results for the summary (handles multiple IFBWs)
        # Since all_results is a list of SweepResult (one per IFBW), we'll
        # iterate over each result and write its sweeps to the same output dir.

        # Flatten all sweeps from all IFBW runs into a single numbered sequence
        global_sweep_num = 1

        for result in all_results:
            # Write one CSV per sweep
            for sweep_idx in range(len(result.all_s11_db)):
                csv_filename = "s11_sweep_{}.csv".format(global_sweep_num)
                csv_path = os.path.join(out_dir, csv_filename)

                sweep_db = result.all_s11_db[sweep_idx]
                sweep_ts = (
                    result.all_timestamps[sweep_idx]
                    if sweep_idx < len(result.all_timestamps)
                    else []
                )

                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Time", "Frequency (Hz)", "Magnitude (dB)"])

                    for pt_idx, freq in enumerate(result.freq_hz):
                        # Time column: HH:MM:SS.ffffff from epoch timestamp
                        if pt_idx < len(sweep_ts):
                            ts_str = datetime.fromtimestamp(
                                sweep_ts[pt_idx]
                            ).strftime("%H:%M:%S.%f")
                        else:
                            ts_str = ""

                        if pt_idx < len(sweep_db):
                            s11_db = round(sweep_db[pt_idx], 4)
                        else:
                            s11_db = ""

                        writer.writerow([ts_str, freq, s11_db])

                global_sweep_num += 1

        # -- Write summary.txt ------------------------------------------------
        summary_path = os.path.join(out_dir, "summary.txt")
        with open(summary_path, "w") as f:
            # Section 1: Sweep Configuration (one table for all IFBWs)
            f.write("=" * 70 + "\n")
            f.write("  SWEEP CONFIGURATION\n")
            f.write("=" * 70 + "\n\n")

            config_table = PrettyTable()
            config_table.field_names = ["Parameter", "Value"]
            config_table.align["Parameter"] = "l"
            config_table.align["Value"] = "l"

            config_table.add_row(["Mode", self.mode])
            # IFBW: if multiple values, list them; else single value
            if len(all_results) > 1:
                ifbw_str = ", ".join(
                    [str(r.ifbw_hz // 1000) for r in all_results]
                ) + " kHz"
            else:
                ifbw_str = "{} kHz".format(all_results[0].ifbw_hz // 1000)
            config_table.add_row(["IFBW (kHz)", ifbw_str])
            config_table.add_row(["Start Freq (Hz)", self.start_freq_hz])
            config_table.add_row(["Stop Freq (Hz)", self.stop_freq_hz])
            config_table.add_row(["Points", self.num_points])
            config_table.add_row(["STIM Level (dBm)", self.stim_lvl_dbm])
            config_table.add_row(["Avg Count", self.avg_count])
            config_table.add_row(["Num Sweeps", self.num_sweeps])

            f.write(config_table.get_string())
            f.write("\n\n")

            # Section 2: Per-Sweep Timing (across all IFBWs)
            f.write("=" * 70 + "\n")
            f.write("  PER-SWEEP TIMING\n")
            f.write("=" * 70 + "\n\n")

            timing_table = PrettyTable()
            timing_table.field_names = [
                "Sweep #",
                "Sweep Time (s)",
                "Sweep Time (ms)",
                "Update Rate (Hz)",
            ]
            timing_table.align["Sweep #"] = "r"
            timing_table.align["Sweep Time (s)"] = "r"
            timing_table.align["Sweep Time (ms)"] = "r"
            timing_table.align["Update Rate (Hz)"] = "r"

            global_sweep_num = 1
            for result in all_results:
                for t in result.sweep_times:
                    rate = 1.0 / t if t > 0 else float("inf")
                    timing_table.add_row(
                        [
                            global_sweep_num,
                            round(t, 4),
                            round(t * 1000, 4),
                            round(rate, 2),
                        ]
                    )
                    global_sweep_num += 1

            f.write(timing_table.get_string())
            f.write("\n\n")

            # Section 3: Summary Metrics (one row per IFBW)
            f.write("=" * 70 + "\n")
            f.write("  SUMMARY METRICS\n")
            f.write("=" * 70 + "\n\n")

            metrics_table = PrettyTable()
            metrics_table.field_names = [
                "Mode",
                "IFBW (kHz)",
                "Mean Time (s)",
                "Std Dev (s)",
                "Min Time (s)",
                "Max Time (s)",
                "Rate (Hz)",
                "Noise Floor (dB)",
                "Trace Jitter (dB)",
            ]

            for r in all_results:
                times_arr = np.array(r.sweep_times)
                mean_t = float(np.mean(times_arr))
                std_t = float(np.std(times_arr, ddof=1)) if len(times_arr) > 1 else 0.0
                min_t = float(np.min(times_arr))
                max_t = float(np.max(times_arr))
                rate = 1.0 / mean_t if mean_t > 0 else float("inf")

                metrics_table.add_row(
                    [
                        r.mode,
                        r.ifbw_hz // 1000,
                        round(mean_t, 4),
                        round(std_t, 4),
                        round(min_t, 4),
                        round(max_t, 4),
                        round(rate, 2),
                        round(r.noise_floor, 2),
                        round(r.trace_jitter, 4),
                    ]
                )

            f.write(metrics_table.get_string())
            f.write("\n")

        return out_dir

    # -----------------------------------------------------------------------
    # Lifecycle hooks  --  override in subclasses for one-time setup / teardown
    # -----------------------------------------------------------------------

    def pre_loop_reset(self, vna):
        """Called once before the IFBW loop.  Override for mode-specific one-time setup."""
        pass

    def post_loop_teardown(self, vna):
        """Called once after the IFBW loop completes.  Override for cleanup."""
        pass

    # -----------------------------------------------------------------------
    # Main orchestration
    # -----------------------------------------------------------------------

    def run(self):
        """
        Top-level entry point.

        Sequence
        --------
        1.  start_gui()
        2.  connect_and_verify()
        3.  enable_streaming_server() (continuous mode only; auto-enables + may restart GUI)
        4.  load_calibration()
        5.  pre_loop_reset()   (one-time mode-specific setup)
        6.  For each IFBW: configure_sweep() -> run_sweeps() -> compute_metrics()
        7.  post_loop_teardown()   (one-time mode-specific cleanup)
        8.  print_summary()  (if self.summary)
        9.  save_xlsx()      (if self.save_data)
        10. stop_gui()       (in finally block)
        """
        gui_proc = self.start_gui()
        try:
            vna = self.connect_and_verify()

            # If continuous mode, enable streaming server (may restart GUI)
            if self.mode == "continuous":
                needs_restart = self.enable_streaming_server(vna)
                if needs_restart:
                    # APPLYPREFERENCES terminated the old GUI; restart it
                    _section("RESTARTING GUI")
                    self.stop_gui(gui_proc)
                    gui_proc = self.start_gui()
                    vna = self.connect_and_verify()

            self.load_calibration(vna)

            all_results = []

            self.pre_loop_reset(vna)

            for ifbw_hz in self.ifbw_values:
                _section(
                    "IFBW = {} kHz  --  {} mode".format(ifbw_hz // 1000, self.mode)
                )

                self.configure_sweep(vna, ifbw_hz)
                result = self.run_sweeps(vna, ifbw_hz)
                self.compute_metrics(result)

                # Per-IFBW progress
                _subsection("IFBW {} kHz -- metrics".format(ifbw_hz // 1000))
                times_arr = np.array(result.sweep_times)
                print(
                    "    Mean sweep time : {:.4f} s".format(float(np.mean(times_arr)))
                )
                print(
                    "    Update rate     : {:.2f} Hz".format(
                        1.0 / float(np.mean(times_arr))
                        if float(np.mean(times_arr)) > 0
                        else float("inf")
                    )
                )
                print("    Noise floor     : {:.2f} dB".format(result.noise_floor))
                print("    Trace jitter    : {:.4f} dB".format(result.trace_jitter))

                all_results.append(result)

            self.post_loop_teardown(vna)

            # -- Console summary ----------------------------------------------
            if self.summary:
                self.print_summary(all_results)

            # -- CSV bundle export --------------------------------------------
            if self.save_data:
                _section("SAVING RESULTS")
                out_dir = self.save_csv_bundle(all_results)
                print("  CSV bundle      : {}".format(out_dir))

            print()  # trailing blank line

        finally:
            self.stop_gui(gui_proc)


# ===========================================================================
# SingleModeSweep
# ===========================================================================


class SingleModeSweep(BaseVNASweep):
    """
    Single-sweep mode: trigger via FREQuency:STOP, poll FIN?, read trace.

    configure_sweep() sets all sweep parameters EXCEPT FREQuency:STOP.
    Each sweep in the loop is triggered by sending FREQuency:STOP, which
    both sets the stop frequency and initiates acquisition.  This mirrors
    the proven trigger-and-poll protocol used in script 4.
    """

    def configure_sweep(self, vna, ifbw_hz):
        """
        Single-mode configuration -- everything except STOP.

        SCPI sequence
        -------------
        :DEV:MODE VNA
        :VNA:SWEEP FREQUENCY
        :VNA:STIM:LVL <dBm>
        :VNA:ACQ:IFBW  <Hz>
        :VNA:ACQ:AVG   <n>
        :VNA:ACQ:POINTS <n>
        :VNA:FREQuency:START <Hz>
        (STOP is the acquisition trigger, sent per-sweep in the loop)
        """
        _subsection(
            "Single-mode configuration  (IFBW = {} kHz)".format(ifbw_hz // 1000)
        )

        vna.cmd(":DEV:MODE VNA")
        print("  Mode            : VNA")

        vna.cmd(":VNA:SWEEP FREQUENCY")
        print("  Sweep type      : FREQUENCY")

        vna.cmd(":VNA:STIM:LVL {}".format(self.stim_lvl_dbm))
        print("  Stimulus level  : {} dBm".format(self.stim_lvl_dbm))

        vna.cmd(":VNA:ACQ:IFBW {}".format(ifbw_hz))
        print("  IF bandwidth    : {} Hz  ({} kHz)".format(ifbw_hz, ifbw_hz // 1000))

        vna.cmd(":VNA:ACQ:AVG {}".format(self.avg_count))
        print("  Averaging       : {} sweep(s)".format(self.avg_count))

        vna.cmd(":VNA:ACQ:POINTS {}".format(self.num_points))
        print("  Points          : {}".format(self.num_points))

        vna.cmd(":VNA:FREQuency:START {}".format(self.start_freq_hz))
        print(
            "  Start freq      : {} Hz  ({:.3f} GHz)".format(
                self.start_freq_hz, self.start_freq_hz / 1e9
            )
        )

        print("  Stop freq       : (will be sent as sweep trigger)")

    def run_sweeps(self, vna, ifbw_hz):
        """Dispatch to the timed single-sweep loop."""
        return self._single_sweep_loop(vna, ifbw_hz)

    def _single_sweep_loop(self, vna, ifbw_hz):
        """
        Execute self.num_sweeps consecutive S11 sweeps using the
        trigger-poll-read protocol from scripts 3 and 4.

        Timing protocol per iteration
        -----------------------------
        1. vna.cmd(":VNA:FREQuency:STOP <Hz>")   -- triggers acquisition
        2. t_start = time.time()
        3. Poll :VNA:ACQ:FIN? every POLL_INTERVAL_S until "TRUE"
        4. t_end = time.time()   -- sweep_time = t_end - t_start
        5. Read :VNA:TRACE:DATA? S11             -- OUTSIDE timed window
        6. Parse + convert to dB                 -- OUTSIDE timed window

        Returns
        -------
        SweepResult
        """
        _subsection("Single-sweep loop  ({} sweeps)".format(self.num_sweeps))

        sweep_times = []
        all_s11_db = []
        all_timestamps = []
        freq_hz_axis = []

        for i in range(self.num_sweeps):

            # -- Trigger via FREQuency:STOP (sets endpoint + starts sweep) --------
            vna.cmd(":VNA:FREQuency:STOP {}".format(self.stop_freq_hz))

            # -- Time: start ----------------------------------------------------
            t_start = time.time()

            # -- Poll for completion --------------------------------------------
            while True:
                finished = vna.query(":VNA:ACQ:FIN?")
                if finished == "TRUE":
                    break
                if time.time() - t_start > SWEEP_TIMEOUT_S:
                    raise TimeoutError(
                        "IFBW={} kHz, sweep {}/{}: VNA:ACQ:FIN? did not return "
                        "TRUE within {:.0f} s (last response: '{}')".format(
                            ifbw_hz // 1000,
                            i + 1,
                            self.num_sweeps,
                            SWEEP_TIMEOUT_S,
                            finished,
                        )
                    )
                time.sleep(POLL_INTERVAL_S)

            # -- Time: end ------------------------------------------------------
            t_end = time.time()
            sweep_time = t_end - t_start
            sweep_times.append(sweep_time)

            # -- Read trace (outside timed window) ------------------------------
            raw_data = vna.query(":VNA:TRACE:DATA? S11")
            trace = libreVNA.parse_VNA_trace_data(raw_data)

            # -- Convert to dB --------------------------------------------------
            sweep_freq = []
            sweep_s11db = []
            for fq, gamma in trace:
                magnitude = abs(gamma)
                if magnitude < 1e-12:
                    magnitude = 1e-12
                s11_db = 20.0 * math.log10(magnitude)
                sweep_freq.append(float(fq))
                sweep_s11db.append(float(s11_db))

            if i == 0:
                freq_hz_axis = sweep_freq

            all_s11_db.append(sweep_s11db)

            # -- Interpolated per-point timestamps (Alternative C) --------------
            # No native per-point timestamps; linearly interpolate between
            # sweep start and end times.
            n_pts = len(sweep_freq)
            if n_pts > 1:
                sweep_ts = [
                    t_start + n * ((t_end - t_start) / (n_pts - 1))
                    for n in range(n_pts)
                ]
            else:
                sweep_ts = [t_start]
            all_timestamps.append(sweep_ts)

            # -- Progress line --------------------------------------------------
            update_rate = 1.0 / sweep_time if sweep_time > 0 else float("inf")
            print(
                "    Sweep {:>2d}/{:<2d}  :  {:.4f} s  ({:.1f} Hz)".format(
                    i + 1, self.num_sweeps, sweep_time, update_rate
                )
            )

        return SweepResult(
            mode="single",
            ifbw_hz=ifbw_hz,
            sweep_times=sweep_times,
            all_s11_db=all_s11_db,
            freq_hz=freq_hz_axis,
            all_timestamps=all_timestamps,
        )


# ===========================================================================
# ContinuousModeSweep
# ===========================================================================


class ContinuousModeSweep(BaseVNASweep):
    """
    Continuous-sweep mode: streaming callback on port 19001.

    The streaming callback is registered ONCE in pre_loop_reset() and
    removed ONCE in post_loop_teardown().  Between IFBWs the callback
    stays connected; only the mutable state it reads is swapped.  This
    avoids the remove + re-add path that triggers a known bug in
    libreVNA.py line 148 (the thread-exit guard checks the wrong list
    length).

    configure_sweep sends the full configuration INCLUDING STOP (no
    ACQ:STOP / SINGLE TRUE prefix -- those are handled by
    pre_loop_reset / post_loop_teardown).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state_holder = [None]  # mutable container; callback always reads [0]
        self._stream_callback = None  # the single registered callback closure

    # -- Inner helper: shared mutable state guarded by a Lock -----------------

    class _SweepState:
        """
        All mutable state touched by the streaming callback, bundled into a
        single object so that the lock scope is unambiguous.
        """

        def __init__(self, num_points, num_sweeps):
            self.lock = threading.Lock()
            self.done_event = threading.Event()
            self.num_points = num_points
            self.num_sweeps = num_sweeps
            self.sweep_count = 0
            self.sweep_start_time = 0.0
            self.sweep_end_times = []  # list[float]
            self.sweep_start_times = []  # list[float]
            self.current_s11 = []  # list[complex], current sweep
            self.all_s11_complex = []  # list[list[complex]], all completed sweeps
            self.current_timestamps = []  # list[float], per-point epoch timestamps for current sweep
            self.all_timestamps = []  # list[list[float]], per-point timestamps for all completed sweeps

    # -----------------------------------------------------------------------

    def configure_sweep(self, vna, ifbw_hz):
        """
        Continuous-mode configuration -- full sequence including STOP.

        SCPI sequence
        -------------
        :DEV:MODE VNA
        :VNA:SWEEP FREQUENCY
        :VNA:STIM:LVL <dBm>
        :VNA:ACQ:IFBW  <Hz>
        :VNA:ACQ:AVG   <n>
        :VNA:ACQ:POINTS <n>
        :VNA:FREQuency:START <Hz>
        :VNA:FREQuency:STOP  <Hz>   -- included because STOP is NOT the trigger here
        """
        _subsection(
            "Continuous-mode configuration  (IFBW = {} kHz)".format(ifbw_hz // 1000)
        )

        vna.cmd(":DEV:MODE VNA")
        print("  Mode            : VNA")

        vna.cmd(":VNA:SWEEP FREQUENCY")
        print("  Sweep type      : FREQUENCY")

        vna.cmd(":VNA:STIM:LVL {}".format(self.stim_lvl_dbm))
        print("  Stimulus level  : {} dBm".format(self.stim_lvl_dbm))

        vna.cmd(":VNA:ACQ:IFBW {}".format(ifbw_hz))
        print("  IF bandwidth    : {} Hz  ({} kHz)".format(ifbw_hz, ifbw_hz // 1000))

        vna.cmd(":VNA:ACQ:AVG {}".format(self.avg_count))
        print("  Averaging       : {} sweep(s)".format(self.avg_count))

        vna.cmd(":VNA:ACQ:POINTS {}".format(self.num_points))
        print("  Points          : {}".format(self.num_points))

        vna.cmd(":VNA:FREQuency:START {}".format(self.start_freq_hz))
        print(
            "  Start freq      : {} Hz  ({:.3f} GHz)".format(
                self.start_freq_hz, self.start_freq_hz / 1e9
            )
        )

        vna.cmd(":VNA:FREQuency:STOP {}".format(self.stop_freq_hz))
        print(
            "  Stop freq       : {} Hz  ({:.3f} GHz)".format(
                self.stop_freq_hz, self.stop_freq_hz / 1e9
            )
        )

    def run_sweeps(self, vna, ifbw_hz):
        """Dispatch to the streaming callback loop."""
        return self._continuous_sweep_loop(vna, ifbw_hz)

    def _make_callback(self, state_holder):
        """
        Return a closure that reads its state from state_holder[0].

        state_holder is a one-element list.  The main thread swaps [0] to a
        fresh _SweepState between IFBWs; the callback picks up the new state
        on the next point without any remove/re-add of the TCP connection.
        """

        def _callback(data):
            state = state_holder[0]
            if state is None:
                return  # gap during state swap -- drop silently
            if "Z0" not in data:
                return

            point_num = data["pointNum"]
            s11_complex = data["measurements"].get("S11", complex(0, 0))
            point_time = time.time()

            with state.lock:
                if point_num == 0:
                    state.sweep_start_time = point_time
                    state.current_s11 = []
                    state.current_timestamps = []

                state.current_s11.append(s11_complex)
                state.current_timestamps.append(point_time)

                if point_num == state.num_points - 1:
                    sweep_end = point_time
                    collected = list(state.current_s11)
                    collected_ts = list(state.current_timestamps)

                    if len(collected) == state.num_points:
                        # Complete sweep -- save it
                        state.sweep_end_times.append(sweep_end)
                        state.sweep_start_times.append(state.sweep_start_time)
                        state.all_s11_complex.append(collected)
                        state.all_timestamps.append(collected_ts)
                        state.sweep_count += 1

                        if state.sweep_count >= state.num_sweeps:
                            state.done_event.set()
                    else:
                        # Partial sweep (e.g. streaming started mid-sweep)
                        # -- discard and wait for the next complete one
                        pass

        return _callback

    def pre_loop_reset(self, vna):
        """
        Register streaming callback ONCE and prepare continuous mode.

        The streaming server is guaranteed to be enabled by run() before
        this method is called, so we can directly connect without error
        handling.
        """
        _subsection("Continuous-mode streaming setup (one-time)")

        # Create the persistent callback referencing the mutable state holder
        self._stream_callback = self._make_callback(self._state_holder)

        # Stop any residual acquisition before connecting
        vna.cmd(":VNA:ACQ:STOP")
        print("  Pre-stop        : sent")

        # Register the streaming callback (streaming server is guaranteed enabled)
        vna.add_live_callback(STREAMING_PORT, self._stream_callback)
        print(
            "  Streaming       : callback registered on port {}".format(STREAMING_PORT)
        )

    def post_loop_teardown(self, vna):
        """Stop acquisition, restore single mode, remove the streaming callback."""
        _subsection("Continuous-mode streaming teardown")

        vna.cmd(":VNA:ACQ:STOP")
        print("  Acquisition     : stopped")

        vna.cmd(":VNA:ACQ:SINGLE TRUE")
        print("  Sweep mode      : restored to SINGLE (TRUE)")

        if self._stream_callback is not None:
            vna.remove_live_callback(STREAMING_PORT, self._stream_callback)
            self._stream_callback = None
            print("  Streaming       : callback removed")

    def _continuous_sweep_loop(self, vna, ifbw_hz):
        """
        Run self.num_sweeps continuous sweeps for one IFBW value.

        The streaming callback is already registered (by pre_loop_reset).
        This method only manages per-IFBW acquisition start/stop and state.

        Sequence per IFBW
        ------------------
        1.  ACQ:STOP              -- halt any sweeps from the previous IFBW
        2.  sleep 0.1 s           -- drain buffered streaming points so the
                                     fresh state does not see stale data
        3.  swap state_holder[0]  -- atomically switch the callback to a
                                     new _SweepState (GIL makes list-item
                                     assignment atomic)
        4.  ACQ:SINGLE FALSE      -- ensure continuous mode (idempotent)
        5.  ACQ:RUN               -- start back-to-back sweeps
        6.  wait on done_event    -- callback sets it when sweep_count reaches target
        7.  ACQ:STOP              -- halt after target is reached

        Returns
        -------
        SweepResult
        """
        _subsection(
            "Continuous-sweep loop  ({} sweeps, IFBW {} kHz)".format(
                self.num_sweeps, ifbw_hz // 1000
            )
        )

        # 1. Stop previous IFBW's sweeps
        vna.cmd(":VNA:ACQ:STOP")
        print("  ACQ:STOP        : sent (halt previous IFBW)")

        # 2. Drain any buffered streaming points from the previous sweep
        time.sleep(0.1)

        # 3. Swap in a fresh state -- the callback picks it up on next point
        fresh_state = self._SweepState(self.num_points, self.num_sweeps)
        self._state_holder[0] = fresh_state
        print("  State           : fresh _SweepState installed")

        # 4. Ensure continuous mode (ACQ:STOP does NOT change SINGLE setting,
        #    but belt-and-suspenders is cheap here)
        vna.cmd(":VNA:ACQ:SINGLE FALSE")
        print("  Sweep mode      : CONTINUOUS  (SINGLE FALSE)")

        # 5. Start acquisition
        vna.cmd(":VNA:ACQ:RUN")
        print("  Acquisition     : started (continuous)")
        print(
            "  Collecting {} sweeps via streaming callback ...".format(self.num_sweeps)
        )

        # 6. Wait for completion
        completed = fresh_state.done_event.wait(timeout=CONTINUOUS_TIMEOUT_S)

        if not completed:
            # Tear down before raising
            vna.cmd(":VNA:ACQ:STOP")
            raise TimeoutError(
                "Only {}/{} sweeps received within {} s timeout.  "
                "Check streaming server connectivity.".format(
                    fresh_state.sweep_count, self.num_sweeps, CONTINUOUS_TIMEOUT_S
                )
            )

        # 7. Stop sweeps for this IFBW (do NOT restore SINGLE TRUE here --
        #    that is post_loop_teardown's job)
        vna.cmd(":VNA:ACQ:STOP")
        print("  Acquisition     : stopped")

        # -- Progress printout ---------------------------------------------------
        with fresh_state.lock:
            for i in range(fresh_state.sweep_count):
                duration = (
                    fresh_state.sweep_end_times[i] - fresh_state.sweep_start_times[i]
                )
                dur_rate = 1.0 / duration if duration > 0 else float("inf")
                if i == 0:
                    print(
                        "    Sweep {:>2d}/{:<2d}  :  dur {:.4f} s  ({:.1f} Hz)  "
                        "inter-sweep: --".format(
                            i + 1, fresh_state.sweep_count, duration, dur_rate
                        )
                    )
                else:
                    interval = (
                        fresh_state.sweep_end_times[i]
                        - fresh_state.sweep_end_times[i - 1]
                    )
                    int_rate = 1.0 / interval if interval > 0 else float("inf")
                    print(
                        "    Sweep {:>2d}/{:<2d}  :  dur {:.4f} s  ({:.1f} Hz)  "
                        "inter-sweep: {:.4f} s  ({:.1f} Hz)".format(
                            i + 1,
                            fresh_state.sweep_count,
                            duration,
                            dur_rate,
                            interval,
                            int_rate,
                        )
                    )

        # -- Convert all sweeps to dB -------------------------------------------
        freq_hz = list(
            np.linspace(
                float(self.start_freq_hz), float(self.stop_freq_hz), self.num_points
            )
        )

        all_s11_db = []
        all_timestamps = []
        sweep_times = []

        for i in range(fresh_state.sweep_count):
            t = fresh_state.sweep_end_times[i] - fresh_state.sweep_start_times[i]
            sweep_times.append(t)

            raw_s11 = fresh_state.all_s11_complex[i]
            s11_db_list = []
            for gamma in raw_s11:
                magnitude = abs(gamma)
                if magnitude < 1e-12:
                    magnitude = 1e-12
                s11_db_list.append(20.0 * math.log10(magnitude))
            all_s11_db.append(s11_db_list)
            all_timestamps.append(fresh_state.all_timestamps[i])

        return SweepResult(
            mode="continuous",
            ifbw_hz=ifbw_hz,
            sweep_times=sweep_times,
            all_s11_db=all_s11_db,
            freq_hz=freq_hz,
            all_timestamps=all_timestamps,
        )


# ===========================================================================
# MonitorModeSweep
# ===========================================================================


class MonitorModeSweep(ContinuousModeSweep):
    """
    Physiological signal capture mode (Monitor Mode -- F02).

    Inherits the streaming callback infrastructure from ContinuousModeSweep
    and adds:

    1. Warm-up phase: run N sweeps to measure the actual sweep time,
       compute mean_sweep_time_ms.

    2. Log-interval gating: only record a data point if at least
       effective_log_interval_ms have elapsed since the last log.
       effective_log_interval_ms = max(user_requested_ms, mean_sweep_time_ms).

    3. Recording loop: runs until duration_s wall-clock seconds have
       elapsed (if duration_s > 0) or until KeyboardInterrupt (if
       duration_s == 0 -- continuous until Ctrl-C).

    4. Output: single Dataflux-compatible CSV exported to
       data/YYYYMMDD/vna_monitor_YYYYMMDD_HHMMSS.csv

    Configuration is read from sweep_config.yaml 'target.monitor' section
    and may be overridden by CLI flags (--log-interval, --duration).

    YAML keys (target.monitor):
        ifbw_hz          : int   -- IFBW for monitor mode
        log_interval_ms  : "auto" or int -- "auto" = log every completed sweep
        duration_s       : float -- 0 = Ctrl-C; >0 = stop after N seconds
        warmup_sweeps    : int   -- sweeps used to estimate sweep time

    CLI overrides:
        --log-interval   : "auto" or int ms (overrides YAML)
        --duration       : float seconds (overrides YAML)
    """

    def __init__(
        self,
        config_path,
        cal_file_path,
        summary=True,
        save_data=True,
        log_interval_override=None,
        duration_override=None,
    ):
        """
        Parameters
        ----------
        config_path          : str   -- absolute path to YAML config.
        cal_file_path        : str   -- path to calibration file (.cal).
        summary              : bool  -- unused in monitor mode (no PrettyTable),
                                        kept for API compatibility.
        save_data            : bool  -- if True, export the Dataflux CSV.
        log_interval_override: str or int or None
                               -- CLI override for log_interval_ms.
                                  "auto", an integer (ms), or None to use YAML.
        duration_override    : float or None
                               -- CLI override for duration_s, or None to use YAML.
        """
        # Call ContinuousModeSweep.__init__ -> BaseVNASweep.__init__
        # mode="monitor" is stored on self.mode; BaseVNASweep reads
        # target.default.ifbw_values for self.ifbw_values (not used in
        # monitor mode, but the parse is harmless).
        super().__init__(
            config_path=config_path,
            cal_file_path=cal_file_path,
            mode="monitor",
            summary=summary,
            save_data=save_data,
        )

        # -- Read monitor-specific config from YAML ----------------------------
        with open(config_path, "r") as fh:
            raw = yaml.safe_load(fh)

        mon = raw.get("target", {}).get("monitor", {})

        self.monitor_ifbw_hz = int(mon.get("ifbw_hz", 50000))
        self.warmup_sweeps = int(mon.get("warmup_sweeps", 5))

        # Log interval: YAML value (may be "auto" or int)
        yaml_log_interval = mon.get("log_interval_ms", "auto")

        # Duration: YAML value
        yaml_duration_s = float(mon.get("duration_s", 0))

        # Apply CLI overrides
        if log_interval_override is not None:
            self._raw_log_interval = log_interval_override
        else:
            self._raw_log_interval = yaml_log_interval

        if duration_override is not None:
            self.duration_s = float(duration_override)
        else:
            self.duration_s = yaml_duration_s

        # Override the base-class ifbw_values so that configure_sweep gets
        # the correct single IFBW when called from our run() method.
        self.ifbw_values = [self.monitor_ifbw_hz]

        # Will be filled after warm-up
        self.mean_sweep_time_ms = None
        self.effective_log_interval_ms = None

        # Records list -- populated during _monitor_loop
        self._monitor_records = []  # list[MonitorRecord]

        # VNA serial -- populated in run() after connect_and_verify
        self._vna_serial = "unknown"

    # -----------------------------------------------------------------------
    # Warm-up
    # -----------------------------------------------------------------------

    def _warmup(self, vna, ifbw_hz, warmup_sweeps):
        """
        Run warmup_sweeps continuous sweeps and return mean_sweep_time_ms.

        Re-uses _continuous_sweep_loop with num_sweeps temporarily set to
        warmup_sweeps.

        Parameters
        ----------
        vna           : libreVNA
        ifbw_hz       : int
        warmup_sweeps : int

        Returns
        -------
        float
            Mean sweep duration in milliseconds over the warm-up sweeps.
        """
        _section("MONITOR MODE -- WARM-UP PHASE ({} sweeps)".format(warmup_sweeps))

        # Temporarily override num_sweeps for the warm-up run
        original_num_sweeps = self.num_sweeps
        self.num_sweeps = warmup_sweeps

        try:
            result = self._continuous_sweep_loop(vna, ifbw_hz)
        finally:
            # Always restore num_sweeps regardless of success/failure
            self.num_sweeps = original_num_sweeps

        if not result.sweep_times:
            raise RuntimeError(
                "Warm-up phase produced no completed sweeps -- "
                "check streaming server connectivity."
            )

        mean_ms = float(np.mean(result.sweep_times)) * 1000.0
        print(
            "\n  Warm-up result  : {} sweeps, mean sweep time = {:.1f} ms".format(
                len(result.sweep_times), mean_ms
            )
        )
        return mean_ms

    # -----------------------------------------------------------------------
    # Effective log interval resolution
    # -----------------------------------------------------------------------

    def _resolve_log_interval(self, mean_sweep_time_ms):
        """
        Compute effective_log_interval_ms from the raw user setting and the
        measured sweep time.

        Rules
        -----
        - "auto"    : effective = mean_sweep_time_ms  (log every sweep)
        - int N     : effective = max(N, mean_sweep_time_ms)
                      Prints a warning if N < mean_sweep_time_ms (clamped).

        Parameters
        ----------
        mean_sweep_time_ms : float

        Returns
        -------
        float
            effective_log_interval_ms
        """
        raw = self._raw_log_interval

        if str(raw).lower() == "auto":
            effective = mean_sweep_time_ms
            print(
                "  Log interval    : auto -> {:.1f} ms  "
                "(= measured sweep time)".format(effective)
            )
        else:
            try:
                requested_ms = float(raw)
            except (TypeError, ValueError):
                raise ValueError(
                    "--log-interval must be 'auto' or an integer ms, "
                    "got: '{}'".format(raw)
                )
            if requested_ms < mean_sweep_time_ms:
                print(
                    "  [WARN] --log-interval {} ms is smaller than the "
                    "measured sweep time ({:.1f} ms).  "
                    "Clamping to {:.1f} ms.".format(
                        int(requested_ms), mean_sweep_time_ms, mean_sweep_time_ms
                    )
                )
                effective = mean_sweep_time_ms
            else:
                effective = requested_ms
                print(
                    "  Log interval    : {:.1f} ms  "
                    "(user-requested; >= sweep time)".format(effective)
                )

        return effective

    # -----------------------------------------------------------------------
    # Monitor loop
    # -----------------------------------------------------------------------

    def _monitor_loop(self, vna, ifbw_hz, effective_log_interval_ms, duration_s):
        """
        Run the continuous recording loop.

        Each completed sweep: extract (timestamp, min_freq_hz, min_dB).
        Gate by log interval: only append a record if elapsed since
        last log >= effective_log_interval_ms.
        Stop when duration_s wall-clock seconds have passed (if > 0),
        or on KeyboardInterrupt (if duration_s == 0).

        The method modifies self._monitor_records in-place.

        Parameters
        ----------
        vna                       : libreVNA
        ifbw_hz                   : int
        effective_log_interval_ms : float
        duration_s                : float  (0 = run until Ctrl-C)
        """
        _section(
            "MONITOR MODE -- RECORDING  (IFBW={} kHz, interval={:.1f} ms, "
            "duration={})".format(
                ifbw_hz // 1000,
                effective_log_interval_ms,
                "{:.0f} s".format(duration_s) if duration_s > 0 else "Ctrl-C",
            )
        )

        # Frequency axis (shared across all sweeps)
        freq_hz_axis = np.linspace(
            float(self.start_freq_hz), float(self.stop_freq_hz), self.num_points
        )

        # Mutable state for the monitor callback  --------------------------------
        # We use a separate monitor state dict (not _SweepState) because we
        # need to accumulate records, track last-log time, and handle
        # duration/stop without re-using the done_event mechanism.

        mon_lock = threading.Lock()
        stop_event = threading.Event()

        # Shared mutable dict -- accessed by both the callback and the main thread.
        # Using a dict so that the closure captures the reference (not the value).
        mon_state = {
            "current_s11": [],         # list[complex], current in-progress sweep
            "sweep_start_time": 0.0,   # epoch time of first point in current sweep
            "last_log_time_ms": None,  # epoch time (ms) of last appended record
            "record_count": 0,         # total records appended
        }

        effective_log_interval_s = effective_log_interval_ms / 1000.0

        def _monitor_callback(data):
            """Streaming callback: one call per sweep point."""
            if stop_event.is_set():
                return  # loop is shutting down -- ignore further points
            if "Z0" not in data:
                return

            point_num = data["pointNum"]
            s11_complex = data["measurements"].get("S11", complex(0, 0))
            point_time = time.time()

            with mon_lock:
                if point_num == 0:
                    mon_state["sweep_start_time"] = point_time
                    mon_state["current_s11"] = []

                mon_state["current_s11"].append(s11_complex)

                if point_num == self.num_points - 1:
                    # End of sweep -- process if complete
                    collected = list(mon_state["current_s11"])
                    if len(collected) != self.num_points:
                        # Partial sweep -- discard
                        return

                    sweep_ts = datetime.now()

                    # Convert to dB
                    s11_db = np.array([
                        20.0 * math.log10(max(abs(g), 1e-12))
                        for g in collected
                    ])

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
                        self._monitor_records.append(
                            MonitorRecord(
                                timestamp=sweep_ts,
                                freq_hz=min_freq,
                                s11_db=min_s11_db,
                            )
                        )
                        mon_state["last_log_time_ms"] = now_ms
                        mon_state["record_count"] += 1

                        count = mon_state["record_count"]
                        print(
                            "    [{:>6d}]  {}  freq={:.3f} MHz  S11={:.2f} dB".format(
                                count,
                                sweep_ts.strftime("%H:%M:%S.%f"),
                                min_freq / 1e6,
                                min_s11_db,
                            )
                        )

        # Register monitor callback on the streaming port
        vna.add_live_callback(STREAMING_PORT, _monitor_callback)
        print("  Streaming       : monitor callback registered on port {}".format(
            STREAMING_PORT
        ))

        # Start continuous acquisition
        vna.cmd(":VNA:ACQ:STOP")
        time.sleep(0.1)  # drain stale data
        vna.cmd(":VNA:ACQ:SINGLE FALSE")
        vna.cmd(":VNA:ACQ:RUN")
        print("  Acquisition     : started (continuous)")

        wall_start = time.time()

        if duration_s > 0:
            print(
                "  Recording for   : {:.0f} s  (press Ctrl-C to stop early)".format(
                    duration_s
                )
            )
        else:
            print("  Recording       : continuous -- press Ctrl-C to stop")

        try:
            while True:
                if duration_s > 0 and (time.time() - wall_start) >= duration_s:
                    print("\n  Duration reached: {:.0f} s elapsed".format(
                        time.time() - wall_start
                    ))
                    break
                time.sleep(0.05)  # yield; callback runs on libreVNA TCP thread
        except KeyboardInterrupt:
            print("\n  Ctrl-C received : stopping recording")

        # Signal the callback to stop accepting new points
        stop_event.set()

        # Stop acquisition
        vna.cmd(":VNA:ACQ:STOP")
        print("  Acquisition     : stopped")

        # Restore single mode
        vna.cmd(":VNA:ACQ:SINGLE TRUE")
        print("  Sweep mode      : restored to SINGLE (TRUE)")

        # Remove the monitor callback
        vna.remove_live_callback(STREAMING_PORT, _monitor_callback)
        print("  Streaming       : monitor callback removed")

        print(
            "\n  Total records   : {}".format(len(self._monitor_records))
        )

    # -----------------------------------------------------------------------
    # Dataflux CSV export
    # -----------------------------------------------------------------------

    def _export_dataflux_csv(
        self, records, vna_serial, ifbw_hz, effective_log_interval_ms
    ):
        """
        Write a Dataflux-compatible CSV file.

        Format
        ------
        Application,VNA-DATAFLUX
        VNA Model,LibreVNA
        VNA Serial,<serial>
        File Name,<filename>
        Start DateTime,<ISO 8601>
        Number of Data,<row count>
        Log Interval(ms),<effective_log_interval_ms>
        Freq Start(MHz),<start_freq>
        Freq Stop(MHz),<stop_freq>
        Freq Span(MHz),<span>
        IF Bandwidth(KHz),<ifbw_khz>
        Points,<num_points>
        (blank line)
        (blank line)
        Time,Marker Stimulus (Hz),Marker Y Real Value (dB)
        HH:MM:SS.ffffff,+X.XXXXXXXXXE+008,-X.XXXXXXXXXE+000
        ...

        Parameters
        ----------
        records                   : list[MonitorRecord]
        vna_serial                : str
        ifbw_hz                   : int
        effective_log_interval_ms : float

        Returns
        -------
        str
            Absolute path to the written CSV file.
        """
        if not records:
            print("  [WARN] No monitor records to export -- CSV not written.")
            return None

        today = datetime.now().strftime("%Y%m%d")
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "vna_monitor_{}.csv".format(timestamp_str)

        out_dir = os.path.join(DATA_DIR, today)
        os.makedirs(out_dir, exist_ok=True)
        csv_path = os.path.join(out_dir, filename)

        start_dt = records[0].timestamp
        num_data = len(records)
        freq_start_mhz = self.start_freq_hz / 1e6
        freq_stop_mhz = self.stop_freq_hz / 1e6
        freq_span_mhz = freq_stop_mhz - freq_start_mhz
        ifbw_khz = ifbw_hz / 1000.0

        with open(csv_path, "w", newline="") as fh:
            writer = csv.writer(fh)

            # -- Metadata header block (12 lines) ---------------------------------
            writer.writerow(["Application", "VNA-DATAFLUX"])
            writer.writerow(["VNA Model", "LibreVNA"])
            writer.writerow(["VNA Serial", vna_serial])
            writer.writerow(["File Name", filename])
            writer.writerow(["Start DateTime", start_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")])
            writer.writerow(["Number of Data", num_data])
            writer.writerow(["Log Interval(ms)", "{:.1f}".format(effective_log_interval_ms)])
            writer.writerow(["Freq Start(MHz)", "{:.6f}".format(freq_start_mhz)])
            writer.writerow(["Freq Stop(MHz)", "{:.6f}".format(freq_stop_mhz)])
            writer.writerow(["Freq Span(MHz)", "{:.6f}".format(freq_span_mhz)])
            writer.writerow(["IF Bandwidth(KHz)", "{:.3f}".format(ifbw_khz)])
            writer.writerow(["Points", self.num_points])

            # -- Two blank lines --------------------------------------------------
            writer.writerow([])
            writer.writerow([])

            # -- Column header ----------------------------------------------------
            writer.writerow(
                ["Time", "Marker Stimulus (Hz)", "Marker Y Real Value (dB)"]
            )

            # -- Data rows --------------------------------------------------------
            for rec in records:
                time_str = rec.timestamp.strftime("%H:%M:%S.%f")
                # Scientific notation with 9 decimal places, explicit sign
                freq_str = "{:+.9E}".format(rec.freq_hz)
                s11_str = "{:+.9E}".format(rec.s11_db)
                writer.writerow([time_str, freq_str, s11_str])

        print("  Dataflux CSV    : {}".format(csv_path))
        return csv_path

    # -----------------------------------------------------------------------
    # run() override
    # -----------------------------------------------------------------------

    def run(self):
        """
        Monitor Mode top-level entry point.

        Sequence
        --------
        1.  start_gui()
        2.  connect_and_verify() -- captures VNA serial from *IDN?
        3.  enable_streaming_server() (may restart GUI)
        4.  load_calibration()
        5.  configure_sweep()  (continuous-mode SCPI config)
        6.  pre_loop_reset()   (register streaming callback once)
        7.  _warmup()          (N sweeps to measure actual sweep time)
        8.  _resolve_log_interval() -- compute effective_log_interval_ms
        9.  _monitor_loop()    (record until duration or Ctrl-C)
        10. post_loop_teardown() (stop acquisition, restore SINGLE, remove callback)
        11. _export_dataflux_csv() (if self.save_data)
        12. stop_gui()         (in finally block)
        """
        gui_proc = self.start_gui()
        try:
            vna = self.connect_and_verify()

            # Capture VNA serial from *IDN? for the CSV header
            try:
                idn_raw = vna.query("*IDN?")
                parts = [p.strip() for p in idn_raw.split(",")]
                # *IDN? format: Manufacturer,Model,Serial,SWVersion
                self._vna_serial = parts[2] if len(parts) > 2 else "unknown"
            except Exception:
                self._vna_serial = "unknown"

            # Enable streaming server (monitor mode requires it)
            needs_restart = self.enable_streaming_server(vna)
            if needs_restart:
                _section("RESTARTING GUI")
                self.stop_gui(gui_proc)
                gui_proc = self.start_gui()
                vna = self.connect_and_verify()
                # Re-capture serial after restart
                try:
                    idn_raw = vna.query("*IDN?")
                    parts = [p.strip() for p in idn_raw.split(",")]
                    self._vna_serial = parts[2] if len(parts) > 2 else "unknown"
                except Exception:
                    pass

            self.load_calibration(vna)

            ifbw_hz = self.monitor_ifbw_hz

            # Configure sweep (uses ContinuousModeSweep.configure_sweep)
            self.configure_sweep(vna, ifbw_hz)

            # Register streaming callback once (pre_loop_reset from ContinuousModeSweep)
            self.pre_loop_reset(vna)

            # Warm-up: measure actual sweep time
            self.mean_sweep_time_ms = self._warmup(vna, ifbw_hz, self.warmup_sweeps)

            # Resolve effective log interval
            self.effective_log_interval_ms = self._resolve_log_interval(
                self.mean_sweep_time_ms
            )

            # Clear any records that might have accumulated during warm-up
            self._monitor_records = []

            # Run the recording loop
            self._monitor_loop(
                vna,
                ifbw_hz,
                self.effective_log_interval_ms,
                self.duration_s,
            )

            # post_loop_teardown: stop acquisition, restore SINGLE TRUE, remove callback
            self.post_loop_teardown(vna)

            # Export Dataflux CSV
            if self.save_data:
                _section("SAVING MONITOR DATA")
                self._export_dataflux_csv(
                    self._monitor_records,
                    self._vna_serial,
                    ifbw_hz,
                    self.effective_log_interval_ms,
                )

            print()  # trailing blank line

        finally:
            self.stop_gui(gui_proc)


# ===========================================================================
# VNAGUIModeSweepTest  --  concrete facade
# ===========================================================================


class VNAGUIModeSweepTest(SingleModeSweep, ContinuousModeSweep):
    """
    Dispatching facade.  Inherits from both SingleModeSweep and
    ContinuousModeSweep (MRO: VNAGUIModeSweepTest -> SingleModeSweep ->
    ContinuousModeSweep -> BaseVNASweep).  configure_sweep() and
    run_sweeps() route to the appropriate parent method based on self.mode.
    """

    def __init__(self, config_path, cal_file_path, mode="single", summary=True, save_data=True):
        if mode not in ("single", "continuous"):
            raise ValueError(
                "mode must be 'single' or 'continuous', got '{}'".format(mode)
            )
        # BaseVNASweep.__init__ is called once via super() thanks to MRO.
        super().__init__(
            config_path=config_path,
            cal_file_path=cal_file_path,
            mode=mode,
            summary=summary,
            save_data=save_data,
        )

    def configure_sweep(self, vna, ifbw_hz):
        """Dispatch to SingleModeSweep or ContinuousModeSweep configure."""
        if self.mode == "single":
            SingleModeSweep.configure_sweep(self, vna, ifbw_hz)
        else:
            ContinuousModeSweep.configure_sweep(self, vna, ifbw_hz)

    def run_sweeps(self, vna, ifbw_hz):
        """Dispatch to _single_sweep_loop or _continuous_sweep_loop."""
        if self.mode == "single":
            return self._single_sweep_loop(vna, ifbw_hz)
        else:
            return self._continuous_sweep_loop(vna, ifbw_hz)

    def pre_loop_reset(self, vna):
        """Dispatch to the correct parent's pre_loop_reset."""
        if self.mode == "single":
            SingleModeSweep.pre_loop_reset(self, vna)
        else:
            ContinuousModeSweep.pre_loop_reset(self, vna)

    def post_loop_teardown(self, vna):
        """Dispatch to the correct parent's post_loop_teardown."""
        if self.mode == "single":
            SingleModeSweep.post_loop_teardown(self, vna)
        else:
            ContinuousModeSweep.post_loop_teardown(self, vna)


# ===========================================================================
# argparse entry point
# ===========================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LibreVNA GUI mode sweep test")
    parser.add_argument(
        "--config",
        default=os.path.join(SCRIPT_DIR, "sweep_config.yaml"),
        help="Path to YAML config (default: sweep_config.yaml in scripts/)",
    )
    parser.add_argument(
        "--cal-file",
        required=True,
        help="Path to calibration file (.cal). Required.",
    )
    parser.add_argument(
        "--mode",
        choices=["single", "continuous", "monitor"],
        default="single",
        help="Sweep mode: single, continuous, or monitor (default: single)",
    )
    parser.add_argument(
        "--log-interval",
        default=None,
        metavar="MS_OR_AUTO",
        help=(
            "Monitor mode only. Log interval in ms, or 'auto' to use the "
            "measured sweep time (default: read from sweep_config.yaml "
            "target.monitor.log_interval_ms)"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        metavar="SECONDS",
        help=(
            "Monitor mode only. Recording duration in seconds.  "
            "0 = continuous until Ctrl-C (default: read from sweep_config.yaml "
            "target.monitor.duration_s)"
        ),
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Suppress console summary (single/continuous modes)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip output file export",
    )
    args = parser.parse_args()

    if args.mode == "monitor":
        # Resolve --log-interval: convert to int if it looks like a number,
        # leave as "auto" string otherwise, or pass None to let YAML decide.
        log_interval_override = None
        if args.log_interval is not None:
            if args.log_interval.strip().lower() == "auto":
                log_interval_override = "auto"
            else:
                try:
                    log_interval_override = int(args.log_interval)
                except ValueError:
                    parser.error(
                        "--log-interval must be 'auto' or an integer ms, "
                        "got: '{}'".format(args.log_interval)
                    )

        monitor = MonitorModeSweep(
            config_path=args.config,
            cal_file_path=args.cal_file,
            summary=not args.no_summary,
            save_data=not args.no_save,
            log_interval_override=log_interval_override,
            duration_override=args.duration,
        )
        monitor.run()

    else:
        test = VNAGUIModeSweepTest(
            config_path=args.config,
            cal_file_path=args.cal_file,
            mode=args.mode,
            summary=not args.no_summary,
            save_data=not args.no_save,
        )
        test.run()
