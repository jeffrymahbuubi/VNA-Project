#!/usr/bin/env python3
"""
5_continuous_sweep_speed.py
-----------------------------
Future Work 3.1 -- Continuous-sweep speed benchmark for LibreVNA.

Motivation
----------
Script 3 (3_sweep_speed_baseline.py) established a single-sweep-mode
baseline: each sweep was re-triggered by re-sending VNA:FREQuency:STOP,
then polled with VNA:ACQ:FIN? until TRUE.  That approach pays a GUI
"Step 2" sweep-preparation overhead on every cycle (~165 ms), capping
the measured rate at roughly 5 Hz.

This script eliminates both overheads:
  * The GUI is placed into CONTINUOUS sweep mode via
    VNA:ACquisition:SINGLE FALSE (ProgrammingGuide 4.3.20).  Sweeps
    execute back-to-back with no per-sweep re-preparation.
  * Completed point data is pushed in real-time over a TCP streaming
    server (ProgrammingGuide Section 6).  A callback registered on
    port 19000 timestamps each sweep as its last point arrives,
    removing all polling dead-time.

Two timing metrics are reported and compared against script 3:
  Sweep Duration      = time from pointNum==0 to pointNum==NUM_POINTS-1
                        within a single sweep.  Measures pure acquisition
                        time.
  Inter-Sweep Interval = time between consecutive sweep completions
                        (sweep_end[N] - sweep_end[N-1]).  This is the
                        apples-to-apples comparison to script 3's per-
                        cycle wall time because it includes any back-to-
                        back overhead the GUI imposes.

SCPI commands used -- all documented in ProgrammingGuide.pdf (Jan 27 2026)
-------------------------------------------------------------------------
  *IDN?                        4.1.1   identification string
  DEVice:CONNect?              4.2.2   serial of connected device
  DEVice:MODE VNA              4.2.6   switch to vector-analyzer mode
  VNA:SWEEP FREQUENCY          4.3.1   select frequency-sweep type
  VNA:STIMulus:LVL    <dBm>    4.3.24  stimulus output power in dBm
  VNA:ACquisition:IFBW <Hz>    4.3.13  IF bandwidth in Hz
  VNA:ACquisition:AVG  <n>     4.3.16  number of averaging sweeps
  VNA:ACquisition:POINTS <n>   4.3.15  points per sweep
  VNA:FREQuency:START <Hz>     4.3.3   start frequency in Hz
  VNA:FREQuency:STOP  <Hz>     4.3.5   stop  frequency in Hz
  VNA:ACquisition:SINGLE <B>   4.3.20  FALSE = continuous sweep mode
  VNA:ACquisition:STOP         4.3.12  halt continuous acquisition
  VNA:ACquisition:RUN          4.3.11  start acquisition
  VNA:CALibration:LOAD? <file> 4.3.55  load calibration file (query)
  VNA:CALibration:ACTIVE?      4.3.45  active calibration type (query)

Streaming (ProgrammingGuide Section 6)
---------------------------------------
The LibreVNA-GUI streaming server pushes one JSON line per measurement
point.  For VNA frequency sweeps the line contains:
  "Z0"            : reference impedance (float)
  "pointNum"      : 0-based index within the current sweep (int)
  "measurements"  : dict with S-parameter keys (after the wrapper
                    reassembles _real/_imag pairs into complex numbers)
The wrapper's __live_thread does the JSON decode and complex conversion
before our callback is invoked.

What it does (in order):
  0. Launches LibreVNA-GUI in headless mode and waits for its SCPI server
     to come up.
  1. Opens a TCP connection to LibreVNA-GUI and confirms that a hardware
     device is attached.
  2. Loads the SOLT calibration file into the GUI via SCPI (reuses
     load_calibration from script 2).
  3. Configures a single S11 frequency sweep over 2.43-2.45 GHz at 300
     points, IFBW = 50 kHz, stimulus = -10 dBm, averaging = 1.
  4. Runs 30 continuous sweeps via streaming callback and collects timing
     data.
  5. Converts the last sweep's raw S11 to dB (deferred from callback).
  6. Prints timing statistics and comparison tables.
  7. Saves two CSVs to the project data/ directory:
       - continuous_sweep_speed_<YYYYMMDD_HHMMSS>.csv   (timing records)
       - continuous_sweep_last_trace_<YYYYMMDD_HHMMSS>.csv  (last S11 trace)
  8. Shuts down the LibreVNA-GUI process.

Prerequisites
-------------
* The streaming server for "VNA Calibrated Data" must be enabled.
  Default port is 19001.  Enable via GUI (Window >> Preferences >>
  Streaming Servers) or via SCPI:
      :DEV:PREF StreamingServers.VNACalibratedData.enabled true
      :DEV:APPLYPREFERENCES
  Note: APPLYPREFERENCES may restart the GUI; reconnect after.
  If add_live_callback raises a connection error, verify the streaming
  server is listening on STREAMING_PORT.
* A calibrated 50-ohm matched load is connected to port 1.
* numpy and prettytable are available in the project venv.
* The data/ directory is a sibling of scripts/ under LibreVNA-dev/.

Usage:
    uv run python 5_continuous_sweep_speed.py
"""

import sys
import os
import csv
import math
import time
import socket
import subprocess
import threading
import importlib
from datetime import datetime

import numpy as np
from prettytable import PrettyTable

# ---------------------------------------------------------------------------
# Paths -- all relative to this script's location so the whole tree is
# portable regardless of where it is checked out.
# ---------------------------------------------------------------------------

# Directory this script lives in.  libreVNA.py is co-located here.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Insert SCRIPT_DIR so that "from libreVNA import libreVNA" resolves to the
# co-located wrapper regardless of cwd.
sys.path.insert(0, SCRIPT_DIR)
from libreVNA import libreVNA  # noqa: E402

# ---------------------------------------------------------------------------
# Import load_calibration from script 2 via importlib.
# Script 2's filename begins with a digit, which is not a valid Python
# identifier, so a normal "import" statement cannot be used.
# connect_and_verify is defined locally (see below) because this script
# manages the GUI lifecycle itself and needs RuntimeError, not sys.exit.
# ---------------------------------------------------------------------------
_mod2 = importlib.import_module("2_s11_cal_verification_sweep")
load_calibration   = _mod2.load_calibration

# ---------------------------------------------------------------------------
# Module-level configuration constants
# ---------------------------------------------------------------------------

# -- GUI lifecycle ----------------------------------------------------------
GUI_BINARY          = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "tools", "LibreVNA-GUI"))
SCPI_HOST           = "localhost"
SCPI_PORT           = 1234
GUI_START_TIMEOUT_S = 30.0   # max seconds to wait for SCPI server to come up

# -- Sweep parameters (identical to scripts 3 and 4) ----------------------
START_FREQ_HZ  = 2_430_000_000   # 2.430 GHz
STOP_FREQ_HZ   = 2_450_000_000   # 2.450 GHz
NUM_POINTS     = 300
IFBW_HZ        = 50_000          # 50 kHz
STIM_LVL_DBM   = -10
AVG_COUNT      = 1               # single sweep, no moving average

# -- Continuous-sweep benchmark parameters ---------------------------------
NUM_SWEEPS        = 30           # total sweeps to collect
STREAMING_PORT    = 19001        # VNA Calibrated Data streaming server port
SWEEP_TIMEOUT_S   = 300          # hard ceiling on event.wait() (seconds)

# -- Script 3 reference values (hardcoded from the baseline run) -----------
# These are used only for the side-by-side comparison table.  If you re-run
# script 3 and get different numbers, update these three constants.
SCRIPT3_MEAN_CYCLE_S  = 0.1949   # mean cycle time (s)
SCRIPT3_MEAN_RATE_HZ  = 5.13     # mean rate (Hz)
SCRIPT3_STD_S         = 0.0012   # std dev of cycle time (s)

# ---------------------------------------------------------------------------
# Console-output helpers (identical style to scripts 1–4)
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    """Print a dashed section header."""
    width = 70
    print("\n" + "=" * width)
    print("  " + title)
    print("=" * width)


def _subsection(title: str) -> None:
    """Print a lighter sub-header."""
    print("\n  --- " + title + " ---")


# ===========================================================================
# GUI LIFECYCLE
# ===========================================================================

def start_gui():
    """
    Launch LibreVNA-GUI in headless mode and poll TCP port SCPI_PORT
    until the SCPI server accepts a connection.  Returns the Popen handle.

    The GUI is started with QT_QPA_PLATFORM=offscreen so it does not
    need a display.  The --port flag sets the SCPI TCP server port.
    """
    _section("STARTING LibreVNA-GUI")

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    proc = subprocess.Popen(
        [GUI_BINARY, "--port", str(SCPI_PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("  GUI PID         : {}".format(proc.pid))

    # Poll until the SCPI TCP server is listening.
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


def stop_gui(proc):
    """
    Terminate the GUI subprocess gracefully (SIGTERM) and wait.
    If it does not exit within 5 s, escalate to SIGKILL.
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


# ===========================================================================
# DEVICE CONNECTION  --  local connect_and_verify (raises, does not exit)
# ===========================================================================

def connect_and_verify():
    """
    Open a TCP connection to LibreVNA-GUI and confirm a hardware device
    is attached.  Raises RuntimeError on any failure (the GUI was just
    started by this script so a connection problem is unexpected).
    """
    _section("DEVICE CONNECTION")

    try:
        vna = libreVNA(host=SCPI_HOST, port=SCPI_PORT)
        print("  TCP connection  : OK  ({}:{})".format(SCPI_HOST, SCPI_PORT))
    except Exception as exc:
        raise RuntimeError(
            "Could not connect to LibreVNA-GUI at {}:{}: {}".format(
                SCPI_HOST, SCPI_PORT, exc)
        )

    _subsection("*IDN? identification")
    try:
        idn_raw = vna.query("*IDN?")
        print("  Raw response    : {}".format(idn_raw))
        parts  = [p.strip() for p in idn_raw.split(",")]
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
        raise RuntimeError(
            "DEVice:CONNect? query failed: {}".format(exc)
        )

    return vna


# ===========================================================================
# SECTION 1  --  Sweep configuration (full sequence including STOP)
# ===========================================================================

def configure_sweep(vna: libreVNA) -> None:
    """
    Send all sweep-configuration commands to the VNA, INCLUDING STOP.

    In continuous-sweep mode we are NOT using STOP as a per-sweep trigger.
    The full configuration is sent once before acquisition starts, so STOP
    must be included in order for the GUI to know the complete frequency
    window.

    SCPI sequence (order matters):
        :DEV:MODE VNA
        :VNA:SWEEP FREQUENCY
        :VNA:STIM:LVL  <dBm>
        :VNA:ACQ:IFBW  <Hz>
        :VNA:ACQ:AVG   <n>
        :VNA:ACQ:POINTS <n>
        :VNA:FREQuency:START <Hz>
        :VNA:FREQuency:STOP  <Hz>

    Parameters
    ----------
    vna : libreVNA
        Connected wrapper instance.
    """

    _section("SWEEP CONFIGURATION")

    # DEVice:MODE VNA  (ProgrammingGuide 4.2.6)
    vna.cmd(":DEV:MODE VNA")
    print("  Mode            : VNA")

    # VNA:SWEEP FREQUENCY  (ProgrammingGuide 4.3.1)
    vna.cmd(":VNA:SWEEP FREQUENCY")
    print("  Sweep type      : FREQUENCY")

    # VNA:STIMulus:LVL  (ProgrammingGuide 4.3.24)
    vna.cmd(":VNA:STIM:LVL {}".format(STIM_LVL_DBM))
    print("  Stimulus level  : {} dBm".format(STIM_LVL_DBM))

    # VNA:ACquisition:IFBW  (ProgrammingGuide 4.3.13)
    vna.cmd(":VNA:ACQ:IFBW {}".format(IFBW_HZ))
    print("  IF bandwidth    : {} Hz  ({} kHz)".format(
        IFBW_HZ, IFBW_HZ / 1000))

    # VNA:ACquisition:AVG  (ProgrammingGuide 4.3.16)
    vna.cmd(":VNA:ACQ:AVG {}".format(AVG_COUNT))
    print("  Averaging       : {} sweep(s)".format(AVG_COUNT))

    # VNA:ACquisition:POINTS  (ProgrammingGuide 4.3.15)
    vna.cmd(":VNA:ACQ:POINTS {}".format(NUM_POINTS))
    print("  Points          : {}".format(NUM_POINTS))

    # VNA:FREQuency:START  (ProgrammingGuide 4.3.3)
    vna.cmd(":VNA:FREQuency:START {}".format(START_FREQ_HZ))
    print("  Start freq      : {} Hz  ({:.3f} GHz)".format(
        START_FREQ_HZ, START_FREQ_HZ / 1e9))

    # VNA:FREQuency:STOP  (ProgrammingGuide 4.3.5)
    # Included here (unlike scripts 3/4) because we are not using STOP as
    # a per-sweep trigger.  The GUI needs the complete window before we
    # enter continuous mode.
    vna.cmd(":VNA:FREQuency:STOP {}".format(STOP_FREQ_HZ))
    print("  Stop freq       : {} Hz  ({:.3f} GHz)".format(
        STOP_FREQ_HZ, STOP_FREQ_HZ / 1e9))


# ===========================================================================
# SECTION 2  --  Shared state and streaming callback
# ===========================================================================

class _SweepState:
    """
    All mutable state touched by the streaming callback, bundled into a
    single object so that the lock scope is unambiguous.

    Attributes
    ----------
    lock : threading.Lock
        Guards every attribute below.
    done_event : threading.Event
        Set when sweep_count reaches NUM_SWEEPS.  The main thread blocks
        on this instead of busy-looping.
    sweep_count : int
        Number of fully-received sweeps so far.
    sweep_start_time : float
        time.time() recorded when pointNum == 0 of the current sweep.
    sweep_end_times : list[float]
        Appended with time.time() each time a sweep completes (pointNum ==
        NUM_POINTS - 1).  Length == sweep_count after the run.
    sweep_start_times : list[float]
        Appended with the recorded sweep_start_time each time a sweep
        completes.  Parallel to sweep_end_times.
    current_s11 : list[complex]
        Accumulates raw complex S11 values for the sweep currently in
        progress.  Overwritten (not appended) at pointNum == 0.  After the
        run completes this holds the last sweep's data.
    last_s11 : list[complex]
        Snapshot of current_s11 taken when the sweep completes.  This is
        the trace that will be converted to dB for the output CSV.
    """

    def __init__(self):
        self.lock            = threading.Lock()
        self.done_event      = threading.Event()
        self.sweep_count     = 0
        self.sweep_start_time = 0.0
        self.sweep_end_times  = []   # list[float]
        self.sweep_start_times = []  # list[float]
        self.current_s11      = []   # list[complex], current sweep
        self.last_s11         = []   # list[complex], snapshot of last completed sweep


def make_callback(state: _SweepState) -> callable:
    """
    Return a closure that captures *state* and implements the streaming
    callback contract.

    The callback is intentionally minimal: it only records timestamps and
    accumulates raw complex S11 values.  No dB conversion or heavy
    computation happens here -- that is deferred to convert_last_trace()
    after the sweep loop ends.

    Parameters
    ----------
    state : _SweepState
        The shared-state container.  All mutations go through state.lock.

    Returns
    -------
    callable
        A function with signature  callback(data: dict) -> None  suitable
        for passing to libreVNA.add_live_callback().
    """

    def _callback(data: dict) -> None:
        # Guard: only process VNA streaming data.  The wrapper sets
        # data["Z0"] only for VNA data (see __live_thread in libreVNA.py).
        if "Z0" not in data:
            return

        point_num = data["pointNum"]

        # Extract the raw complex S11 value.  The wrapper has already
        # reassembled the _real/_imag split (see libreVNA.py lines 160-171).
        s11_complex = data["measurements"].get("S11", complex(0, 0))

        with state.lock:
            # --- pointNum == 0: start of a new sweep ----------------------
            if point_num == 0:
                state.sweep_start_time = time.time()
                # Reset the accumulator for this sweep.  Do NOT clear
                # last_s11 -- it holds the previous completed sweep until
                # the next one finishes.
                state.current_s11 = []

            # --- accumulate the S11 sample for this point -----------------
            state.current_s11.append(s11_complex)

            # --- pointNum == NUM_POINTS - 1: sweep complete ---------------
            if point_num == NUM_POINTS - 1:
                sweep_end = time.time()

                state.sweep_end_times.append(sweep_end)
                state.sweep_start_times.append(state.sweep_start_time)

                # Snapshot the completed trace before current_s11 is reset
                # on the next pointNum == 0.
                state.last_s11 = list(state.current_s11)

                state.sweep_count += 1

                # Signal the main thread if we have collected enough sweeps.
                if state.sweep_count >= NUM_SWEEPS:
                    state.done_event.set()

    return _callback


# ===========================================================================
# SECTION 3  --  Continuous acquisition orchestration
# ===========================================================================

def run_continuous_sweeps(vna: libreVNA) -> _SweepState:
    """
    Register the streaming callback, place the VNA into continuous sweep
    mode, wait for NUM_SWEEPS to complete, then tear down cleanly.

    Sequence
    --------
    1. Stop any currently running acquisition.
    2. Set continuous mode: VNA:ACquisition:SINGLE FALSE
    3. Register the streaming callback on STREAMING_PORT.
    4. Start acquisition: VNA:ACquisition:RUN
    5. Block on done_event with SWEEP_TIMEOUT_S timeout.
    6. Stop acquisition: VNA:ACquisition:STOP
    7. Restore single-sweep mode: VNA:ACquisition:SINGLE TRUE
    8. Remove the streaming callback.

    Parameters
    ----------
    vna : libreVNA
        Connected and configured wrapper instance.

    Returns
    -------
    _SweepState
        The populated state object; caller reads timing lists and last_s11
        from it.

    Raises
    ------
    TimeoutError
        If done_event is not set within SWEEP_TIMEOUT_S seconds.
    """

    _section("CONTINUOUS SWEEP ACQUISITION  ({} sweeps)".format(NUM_SWEEPS))

    state    = _SweepState()
    callback = make_callback(state)

    # -- 1. Stop any pre-existing acquisition -------------------------------
    # VNA:ACquisition:STOP  (ProgrammingGuide 4.3.12)
    vna.cmd(":VNA:ACQ:STOP")
    print("  Pre-stop        : sent")

    # -- 2. Select continuous sweep mode -------------------------------------
    # VNA:ACquisition:SINGLE FALSE  (ProgrammingGuide 4.3.20)
    # When SINGLE is FALSE the GUI free-runs sweeps back-to-back without
    # the per-sweep re-preparation that SINGLE TRUE imposes.
    vna.cmd(":VNA:ACQ:SINGLE FALSE")
    print("  Sweep mode      : CONTINUOUS  (SINGLE FALSE)")

    # -- 3. Register streaming callback BEFORE starting acquisition ---------
    # add_live_callback opens a TCP connection to the streaming server and
    # spawns a reader thread.  If the streaming server is not enabled in
    # the GUI this will raise an exception with a clear message.
    try:
        vna.add_live_callback(STREAMING_PORT, callback)
        print("  Streaming       : callback registered on port {}".format(
            STREAMING_PORT))
    except Exception as exc:
        print("  [FAIL] Could not connect to streaming server on port {}.".format(
            STREAMING_PORT))
        print("         Detail: {}".format(exc))
        print("         Action: enable a VNA streaming server in the GUI:")
        print("                 Window >> Preferences >> Streaming Servers")
        sys.exit(1)

    # -- 4. Start continuous acquisition ------------------------------------
    # VNA:ACquisition:RUN  (ProgrammingGuide 4.3.11)
    vna.cmd(":VNA:ACQ:RUN")
    print("  Acquisition     : started (continuous)")
    print("  Collecting {} sweeps via streaming callback ...".format(NUM_SWEEPS))

    # -- 5. Block until NUM_SWEEPS have been received -----------------------
    # done_event is set by the callback when sweep_count reaches NUM_SWEEPS.
    # The timeout is a safety net; normal completion is much faster.
    completed = state.done_event.wait(timeout=SWEEP_TIMEOUT_S)

    if not completed:
        # Tear down before raising so the VNA is left in a clean state.
        vna.cmd(":VNA:ACQ:STOP")
        vna.cmd(":VNA:ACQ:SINGLE TRUE")   # restore before raising
        vna.remove_live_callback(STREAMING_PORT, callback)
        raise TimeoutError(
            "Only {}/{} sweeps received within {} s timeout.  "
            "Check streaming server connectivity and sweep parameters.".format(
                state.sweep_count, NUM_SWEEPS, SWEEP_TIMEOUT_S)
        )

    # -- 6. Stop continuous acquisition -------------------------------------
    # VNA:ACquisition:STOP  (ProgrammingGuide 4.3.12)
    vna.cmd(":VNA:ACQ:STOP")
    print("  Acquisition     : stopped")

    # -- 7. Restore single-sweep mode ---------------------------------------
    # ACQ:STOP halts the sweep loop but does not change ACQ:SINGLE.
    # Restore the default so that any script run afterward in the same
    # GUI session gets the expected single-sweep trigger behaviour.
    vna.cmd(":VNA:ACQ:SINGLE TRUE")
    print("  Sweep mode      : restored to SINGLE (TRUE)")

    # -- 8. Remove the streaming callback ------------------------------------
    vna.remove_live_callback(STREAMING_PORT, callback)
    print("  Streaming       : callback removed")

    # Progress: print each sweep as it was received (reconstructed from the
    # state lists, which are already fully populated by this point).
    with state.lock:
        for i in range(state.sweep_count):
            duration  = state.sweep_end_times[i] - state.sweep_start_times[i]
            dur_rate  = 1.0 / duration if duration > 0 else float('inf')
            if i == 0:
                print("  Sweep {:>2d}/{:<2d}  :  dur {:.4f} s  ({:.1f} Hz)  "
                      "inter-sweep: --".format(
                          i + 1, state.sweep_count, duration, dur_rate))
            else:
                interval = state.sweep_end_times[i] - state.sweep_end_times[i - 1]
                int_rate = 1.0 / interval if interval > 0 else float('inf')
                print("  Sweep {:>2d}/{:<2d}  :  dur {:.4f} s  ({:.1f} Hz)  "
                      "inter-sweep: {:.4f} s  ({:.1f} Hz)".format(
                          i + 1, state.sweep_count, duration, dur_rate,
                          interval, int_rate))

    return state


# ===========================================================================
# SECTION 4  --  dB conversion (deferred, runs after the callback loop)
# ===========================================================================

def convert_last_trace(state: _SweepState) -> tuple:
    """
    Convert the last completed sweep's raw complex S11 values to dB, and
    build the frequency axis using numpy.linspace.

    The frequency array is computed deterministically from START, STOP, and
    NUM_POINTS -- this is mathematically exact and identical to what the
    VNA uses internally for a linear frequency sweep.  No extra SCPI
    round-trip is needed.

    dB conversion
    -------------
    S11_dB = 20 * log10(|gamma|)
    |gamma| is clamped to >= 1e-12 to avoid log(0).

    Parameters
    ----------
    state : _SweepState
        Populated state object; only state.last_s11 is read.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        (freq_hz, s11_db) -- both float64 arrays of length NUM_POINTS.
    """

    freq_hz = np.linspace(float(START_FREQ_HZ),
                          float(STOP_FREQ_HZ),
                          NUM_POINTS)

    # Work from the snapshot taken under the lock by the callback.
    # No lock needed here -- the callback thread has exited and the
    # done_event guarantees a happens-before relationship.
    raw_s11 = state.last_s11

    magnitudes = np.array([abs(c) for c in raw_s11])
    magnitudes = np.maximum(magnitudes, 1e-12)   # clamp
    s11_db     = 20.0 * np.log10(magnitudes)

    return freq_hz, s11_db


# ===========================================================================
# SECTION 5  --  Statistics and console summary
# ===========================================================================

def print_timing_summary(state: _SweepState) -> None:
    """
    Compute and print two PrettyTables:
      Table 1 -- per-metric stats (mean / std / min / max) for sweep
                 duration and inter-sweep interval, plus their Hz rates.
      Table 2 -- side-by-side comparison against script 3's baseline.

    All statistics use ddof=1 (sample std).

    Parameters
    ----------
    state : _SweepState
        Populated state object.
    """

    # --- Derive raw arrays ------------------------------------------------
    end_times   = np.array(state.sweep_end_times)     # shape (N,)
    start_times = np.array(state.sweep_start_times)   # shape (N,)

    durations       = end_times - start_times          # shape (N,)
    duration_rates  = 1.0 / durations                  # Hz

    # Inter-sweep intervals: end[N] - end[N-1], so length N-1.
    # Skip sweep 0 which has no predecessor.
    intervals       = np.diff(end_times)               # shape (N-1,)
    interval_rates  = 1.0 / intervals                  # Hz

    # --- Table 1: CONTINUOUS SWEEP TIMING ---------------------------------
    _section("CONTINUOUS SWEEP TIMING")

    table1 = PrettyTable()
    table1.field_names = ["Metric", "Mean", "Std Dev", "Min", "Max"]

    table1.add_row([
        "Sweep Duration (s)",
        "{:.4f}".format(float(np.mean(durations))),
        "{:.4f}".format(float(np.std(durations, ddof=1))),
        "{:.4f}".format(float(np.min(durations))),
        "{:.4f}".format(float(np.max(durations)))
    ])

    table1.add_row([
        "Duration Rate (Hz)",
        "{:.2f}".format(float(np.mean(duration_rates))),
        "{:.2f}".format(float(np.std(duration_rates, ddof=1))),
        "{:.2f}".format(float(np.min(duration_rates))),
        "{:.2f}".format(float(np.max(duration_rates)))
    ])

    table1.add_row([
        "Inter-Sweep Interval (s)",
        "{:.4f}".format(float(np.mean(intervals))),
        "{:.4f}".format(float(np.std(intervals, ddof=1))),
        "{:.4f}".format(float(np.min(intervals))),
        "{:.4f}".format(float(np.max(intervals)))
    ])

    table1.add_row([
        "Inter-Sweep Rate (Hz)",
        "{:.2f}".format(float(np.mean(interval_rates))),
        "{:.2f}".format(float(np.std(interval_rates, ddof=1))),
        "{:.2f}".format(float(np.min(interval_rates))),
        "{:.2f}".format(float(np.max(interval_rates)))
    ])

    print(table1)

    # --- Table 2: COMPARISON against script 3 -----------------------------
    _section("COMPARISON: CONTINUOUS vs SINGLE-SWEEP")

    # Use inter-sweep interval as the "cycle time" for the continuous run
    # because it is the direct equivalent of script 3's end-to-end wall
    # time per cycle.
    cont_mean_cycle_s  = float(np.mean(intervals))
    cont_mean_rate_hz  = float(np.mean(interval_rates))
    cont_std_s         = float(np.std(intervals, ddof=1))

    # Speedup for times: script3 / script5 (bigger script3 value means
    # script5 is faster -> speedup > 1).
    # Speedup for rates: script5 / script3 (bigger script5 rate means
    # script5 is faster -> speedup > 1).
    speedup_cycle = SCRIPT3_MEAN_CYCLE_S / cont_mean_cycle_s if cont_mean_cycle_s > 0 else float('inf')
    speedup_rate  = cont_mean_rate_hz    / SCRIPT3_MEAN_RATE_HZ if SCRIPT3_MEAN_RATE_HZ > 0 else float('inf')
    speedup_std   = SCRIPT3_STD_S        / cont_std_s           if cont_std_s > 0 else float('inf')

    table2 = PrettyTable()
    table2.field_names = [
        "Metric",
        "Single-Sweep (Script 3)",
        "Continuous (Script 5)",
        "Speedup"
    ]

    table2.add_row([
        "Mean cycle time (s)",
        "{:.4f}".format(SCRIPT3_MEAN_CYCLE_S),
        "{:.4f}".format(cont_mean_cycle_s),
        "{:.2f}x".format(speedup_cycle)
    ])

    table2.add_row([
        "Mean rate (Hz)",
        "{:.2f}".format(SCRIPT3_MEAN_RATE_HZ),
        "{:.2f}".format(cont_mean_rate_hz),
        "{:.2f}x".format(speedup_rate)
    ])

    table2.add_row([
        "Std Dev (s)",
        "{:.4f}".format(SCRIPT3_STD_S),
        "{:.4f}".format(cont_std_s),
        "{:.2f}x".format(speedup_std)
    ])

    print(table2)

    # --- 25 Hz target assessment --------------------------------------------
    target_hz = 25.0
    print("\n  Target update rate : {:.1f} Hz".format(target_hz))
    print("  Measured mean rate : {:.2f} Hz  (inter-sweep)".format(
        cont_mean_rate_hz))
    if cont_mean_rate_hz >= target_hz:
        print("  Status             : MEETS TARGET")
    else:
        print("  Status             : BELOW TARGET")


# ===========================================================================
# SECTION 6  --  CSV export
# ===========================================================================

def save_timing_csv(state: _SweepState) -> str:
    """
    Write per-sweep timing records to a time-stamped CSV.

    Columns
    -------
    Sweep_Number            : 1-based sweep index
    Duration_s              : sweep_end - sweep_start for that sweep
    InterSweep_Interval_s   : sweep_end[N] - sweep_end[N-1]  (blank for row 1)
    Duration_Rate_Hz        : 1 / Duration_s
    InterSweep_Rate_Hz      : 1 / InterSweep_Interval_s  (blank for row 1)

    Returns
    -------
    str
        Absolute path of the written file.
    """

    output_dir = os.path.normpath(
        os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
    )
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = "continuous_sweep_speed_{}.csv".format(timestamp)
    full_path = os.path.join(output_dir, filename)

    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "Sweep_Number",
            "Duration_s",
            "InterSweep_Interval_s",
            "Duration_Rate_Hz",
            "InterSweep_Rate_Hz"
        ])

        for i in range(state.sweep_count):
            duration     = state.sweep_end_times[i] - state.sweep_start_times[i]
            dur_rate     = 1.0 / duration if duration > 0 else float('inf')

            if i == 0:
                # No predecessor -- leave inter-sweep columns blank.
                writer.writerow([
                    i + 1,
                    "{:.6f}".format(duration),
                    "",
                    "{:.4f}".format(dur_rate),
                    ""
                ])
            else:
                interval = state.sweep_end_times[i] - state.sweep_end_times[i - 1]
                int_rate = 1.0 / interval if interval > 0 else float('inf')
                writer.writerow([
                    i + 1,
                    "{:.6f}".format(duration),
                    "{:.6f}".format(interval),
                    "{:.4f}".format(dur_rate),
                    "{:.4f}".format(int_rate)
                ])

    return full_path


def save_trace_csv(freq_hz: np.ndarray, s11_db: np.ndarray) -> str:
    """
    Write the last sweep's S11 trace to a time-stamped CSV.

    Columns: Frequency_Hz, S11_dB  (same layout as scripts 2 and 3).

    Parameters
    ----------
    freq_hz : numpy.ndarray
        Frequency axis in Hz (length NUM_POINTS).
    s11_db  : numpy.ndarray
        S11 magnitude in dB (length NUM_POINTS).

    Returns
    -------
    str
        Absolute path of the written file.
    """

    output_dir = os.path.normpath(
        os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
    )
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = "continuous_sweep_last_trace_{}.csv".format(timestamp)
    full_path = os.path.join(output_dir, filename)

    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Frequency_Hz", "S11_dB"])
        for f, s in zip(freq_hz, s11_db):
            writer.writerow([float(f), float(s)])

    return full_path


# ===========================================================================
# main
# ===========================================================================

def main() -> None:
    """
    Entry point.  Orchestrates GUI start -> connect -> calibrate ->
    configure -> continuous acquisition -> statistics -> CSV export ->
    GUI stop.
    """

    gui_proc = start_gui()
    try:
        # --------------------------------------------------------------
        # 1. Connect and verify device presence
        # --------------------------------------------------------------
        vna = connect_and_verify()

        # --------------------------------------------------------------
        # 1b. Load calibration into the GUI
        # --------------------------------------------------------------
        load_calibration(vna)

        # --------------------------------------------------------------
        # 2. Configure sweep (full sequence including STOP)
        # --------------------------------------------------------------
        configure_sweep(vna)

        # --------------------------------------------------------------
        # 3. Run continuous sweeps and collect timing via streaming callback
        # --------------------------------------------------------------
        state = run_continuous_sweeps(vna)

        # --------------------------------------------------------------
        # 4. Convert the last sweep's raw S11 to dB (deferred from callback)
        # --------------------------------------------------------------
        _section("TRACE CONVERSION")
        freq_hz, s11_db = convert_last_trace(state)
        print("  Converted       : {} points (linspace freq axis)".format(
            len(freq_hz)))
        print("  S11 range       : {:.2f} dB  to  {:.2f} dB".format(
            float(np.min(s11_db)), float(np.max(s11_db))))

        # --------------------------------------------------------------
        # 5. Print timing statistics and comparison tables
        # --------------------------------------------------------------
        print_timing_summary(state)

        # --------------------------------------------------------------
        # 6. Save timing CSV
        # --------------------------------------------------------------
        _section("SAVING RESULTS")
        timing_csv_path = save_timing_csv(state)
        print("  Timing CSV      : {}".format(timing_csv_path))

        # --------------------------------------------------------------
        # 7. Save last-sweep trace CSV
        # --------------------------------------------------------------
        trace_csv_path = save_trace_csv(freq_hz, s11_db)
        print("  Last trace CSV  : {}".format(trace_csv_path))

        print()  # trailing blank line

    finally:
        stop_gui(gui_proc)


if __name__ == "__main__":
    main()
