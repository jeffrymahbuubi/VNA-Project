#!/usr/bin/env python3
"""
3_sweep_speed_baseline.py
--------------------------
Part 2(a) -- Sweep-speed baseline test for LibreVNA.

What it does (in order):
  1. Opens a TCP connection to LibreVNA-GUI and confirms that a hardware
     device is attached (reuses connect_and_verify from script 2).
  2. Loads the SOLT calibration file into the GUI via SCPI (reuses
     load_calibration from script 2).
  3. Configures a single S11 frequency sweep over 2.43-2.45 GHz at 300
     points, IFBW = 50 kHz, stimulus = -10 dBm, averaging = 1.
  4. Runs 30 consecutive sweeps.  Each sweep is timed from the moment the
     poll loop begins until VNA:ACQ:FIN? returns TRUE.  The S11 trace is
     read *after* the timing window closes so that TCP round-trip latency
     on the trace read does not inflate the measured sweep time.  After
     each trace read the next sweep is re-triggered by re-sending
     VNA:FREQuency:STOP (the established codebase pattern).
  5. Computes mean, std, min, max of sweep times and of per-sweep update
     rates (1 / sweep_time).
  6. Prints a PrettyTable summary.
  7. Saves two CSVs to the project data/ directory:
       - sweep_speed_baseline_<YYYYMMDD_HHMMSS>.csv   (timing records)
       - sweep_speed_last_trace_<YYYYMMDD_HHMMSS>.csv  (last S11 trace)

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
  VNA:FREQuency:STOP  <Hz>     4.3.5   stop  frequency in Hz  (also re-trigger)
  VNA:ACquisition:FINished?    4.3.18  TRUE when averaging is complete
  VNA:TRACe:DATA? S11          4.3.27  comma-separated [freq,re,im] tuples
  VNA:CALibration:LOAD? <file> 4.3.55  load calibration file (query)
  VNA:CALibration:ACTIVE?      4.3.45  active calibration type (query)

Assumptions
-----------
* LibreVNA-GUI is running with its SCPI TCP server enabled on port 1234.
* A 50-ohm matched load is connected to port 1 so that S11 is deep after
  calibration is applied.
* numpy and prettytable are available in the project venv (both confirmed
  present at venv creation time).
* The data/ directory is a sibling of scripts/ under LibreVNA-dev/.

Usage:
    uv run python 3_sweep_speed_baseline.py
"""

import sys
import os
import csv
import math
import time
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
# Import connect_and_verify / load_calibration from script 2 via importlib.
# Script 2's filename begins with a digit, which is not a valid Python
# identifier, so a normal "import" statement cannot be used.
# ---------------------------------------------------------------------------
_mod2 = importlib.import_module("2_s11_cal_verification_sweep")
connect_and_verify = _mod2.connect_and_verify
load_calibration   = _mod2.load_calibration

# ---------------------------------------------------------------------------
# Module-level configuration constants
# ---------------------------------------------------------------------------

# -- Sweep parameters (identical to the Part 2 baseline in script 2) --------
START_FREQ_HZ  = 2_430_000_000   # 2.430 GHz
STOP_FREQ_HZ   = 2_450_000_000   # 2.450 GHz
NUM_POINTS     = 300
IFBW_HZ        = 50_000          # 50 kHz -- fixed for this baseline test
STIM_LVL_DBM   = -10
AVG_COUNT      = 1               # single sweep, no averaging

# -- Timing loop parameters -------------------------------------------------
NUM_SWEEPS        = 30
POLL_INTERVAL_S   = 0.01         # seconds between FINished? queries
SWEEP_TIMEOUT_S   = 60.0         # hard ceiling per sweep

# ---------------------------------------------------------------------------
# Console-output helpers (identical style to scripts 1 and 2)
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print("  " + title)
    print("=" * width)


def _subsection(title: str) -> None:
    print("\n  --- " + title + " ---")


# ===========================================================================
# SECTION 1  --  Sweep configuration (everything EXCEPT STOP frequency)
# ===========================================================================

def configure_sweep(vna: libreVNA, ifbw_hz: int) -> None:
    """
    Send all sweep-configuration commands to the VNA *except* for
    VNA:FREQuency:STOP.  Holding STOP back prevents the GUI from
    triggering acquisition prematurely; the caller issues STOP explicitly
    when it is ready to start timing.

    SCPI sequence (order matters):
        :DEV:MODE VNA
        :VNA:SWEEP FREQUENCY
        :VNA:STIM:LVL <dBm>
        :VNA:ACQ:IFBW  <Hz>
        :VNA:ACQ:AVG   <n>
        :VNA:ACQ:POINTS <n>
        :VNA:FREQuency:START <Hz>

    Parameters
    ----------
    vna     : libreVNA   -- connected wrapper instance.
    ifbw_hz : int        -- IF bandwidth in Hz for this sweep.
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
    vna.cmd(":VNA:ACQ:IFBW {}".format(ifbw_hz))
    print("  IF bandwidth    : {} Hz  ({} kHz)".format(
        ifbw_hz, ifbw_hz / 1000))

    # VNA:ACquisition:AVG  (ProgrammingGuide 4.3.16)
    vna.cmd(":VNA:ACQ:AVG {}".format(AVG_COUNT))
    print("  Averaging       : {} sweep(s)".format(AVG_COUNT))

    # VNA:ACquisition:POINTS  (ProgrammingGuide 4.3.15)
    vna.cmd(":VNA:ACQ:POINTS {}".format(NUM_POINTS))
    print("  Points          : {}".format(NUM_POINTS))

    # VNA:FREQuency:START  (ProgrammingGuide 4.3.3)
    # STOP is intentionally omitted here -- it is the trigger.
    vna.cmd(":VNA:FREQuency:START {}".format(START_FREQ_HZ))
    print("  Start freq      : {} Hz  ({:.3f} GHz)".format(
        START_FREQ_HZ, START_FREQ_HZ / 1e9))
    print("  Stop freq       : (will be sent as sweep trigger)")


# ===========================================================================
# SECTION 2  --  Timed sweep loop
# ===========================================================================

def run_timed_sweeps(vna: libreVNA, num_sweeps: int) -> tuple:
    """
    Execute num_sweeps consecutive S11 sweeps, timing each one, and
    return the raw timing data plus the last S11 trace converted to dB.

    Timing protocol for every iteration
    ------------------------------------
    1. Send :VNA:FREQuency:STOP <Hz>   -- triggers acquisition.
    2. Record t_start = time.time().
    3. Poll :VNA:ACQ:FIN? until "TRUE" or timeout.
    4. Record t_end  = time.time().  sweep_time = t_end - t_start.
    5. Read :VNA:TRACE:DATA? S11       -- OUTSIDE the timed window.
    6. Parse and convert to dB.        -- OUTSIDE the timed window.

    The trace read on iteration N also serves as the implicit "wait"
    that lets the instrument settle before iteration N+1's STOP command
    re-triggers.  No additional sleep is needed.

    Parameters
    ----------
    vna        : libreVNA  -- connected wrapper instance.
    num_sweeps : int       -- number of sweeps to run.

    Returns
    -------
    tuple[list[float], list[float], list[float]]
        sweep_times  : wall-clock seconds per sweep.
        last_freq_hz : frequency axis of the final sweep (Hz).
        last_s11_db  : S11 magnitude of the final sweep (dB).

    Raises
    ------
    TimeoutError
        If any single sweep does not finish within SWEEP_TIMEOUT_S.
    """

    _section("TIMED SWEEP LOOP  ({} sweeps)".format(num_sweeps))

    sweep_times   = []
    last_freq_hz  = []
    last_s11_db   = []

    for i in range(num_sweeps):

        # -- Trigger the sweep by sending STOP --------------------------------
        # Per the codebase convention (confirmed in script 2) setting STOP
        # completes the frequency window and starts acquisition.
        # VNA:FREQuency:STOP  (ProgrammingGuide 4.3.5)
        vna.cmd(":VNA:FREQuency:STOP {}".format(STOP_FREQ_HZ))

        # -- Time: start ------------------------------------------------------
        t_start = time.time()

        # -- Poll for completion ----------------------------------------------
        # VNA:ACquisition:FINished?  (ProgrammingGuide 4.3.18)
        while True:
            finished = vna.query(":VNA:ACQ:FIN?")
            if finished == "TRUE":
                break
            if time.time() - t_start > SWEEP_TIMEOUT_S:
                raise TimeoutError(
                    "Sweep {}/{}: VNA:ACQ:FIN? did not return TRUE within "
                    "{:.0f} s (last response: '{}')".format(
                        i + 1, num_sweeps, SWEEP_TIMEOUT_S, finished)
                )
            time.sleep(POLL_INTERVAL_S)

        # -- Time: end --------------------------------------------------------
        t_end      = time.time()
        sweep_time = t_end - t_start
        sweep_times.append(sweep_time)

        # -- Read trace (outside the timed window) ----------------------------
        # VNA:TRACe:DATA? S11  (ProgrammingGuide 4.3.27)
        raw_data = vna.query(":VNA:TRACE:DATA? S11")
        trace    = libreVNA.parse_VNA_trace_data(raw_data)

        # -- Convert to dB ----------------------------------------------------
        # Identical clamping logic to script 2.
        freq_hz_list = []
        s11_db_list  = []
        for freq_hz, gamma in trace:
            magnitude = abs(gamma)
            if magnitude < 1e-12:
                magnitude = 1e-12
            s11_db = 20.0 * math.log10(magnitude)
            freq_hz_list.append(float(freq_hz))
            s11_db_list.append(float(s11_db))

        # Keep the last sweep's trace for the output CSV.
        last_freq_hz = freq_hz_list
        last_s11_db  = s11_db_list

        # -- Progress line ----------------------------------------------------
        update_rate = 1.0 / sweep_time if sweep_time > 0 else float('inf')
        print("  Sweep {:>2d}/{:<2d}  :  {:.4f} s  ({:.1f} Hz)".format(
            i + 1, num_sweeps, sweep_time, update_rate))

    return sweep_times, last_freq_hz, last_s11_db


# ===========================================================================
# SECTION 3  --  Statistics and console summary
# ===========================================================================

def print_timing_summary(sweep_times: list) -> None:
    """
    Compute and print mean / std / min / max for both sweep times and
    the derived update rates using a PrettyTable.

    Parameters
    ----------
    sweep_times : list[float]
        Wall-clock seconds for each sweep.
    """

    _section("TIMING SUMMARY")

    times_arr  = np.array(sweep_times)
    rates_arr  = 1.0 / times_arr   # update rate in Hz

    # -- Build PrettyTable -------------------------------------------------------
    table = PrettyTable()
    table.field_names = ["Metric", "Mean", "Std Dev", "Min", "Max"]

    table.add_row([
        "Sweep Time (s)",
        "{:.4f}".format(float(np.mean(times_arr))),
        "{:.4f}".format(float(np.std(times_arr, ddof=1))),
        "{:.4f}".format(float(np.min(times_arr))),
        "{:.4f}".format(float(np.max(times_arr)))
    ])

    table.add_row([
        "Update Rate (Hz)",
        "{:.2f}".format(float(np.mean(rates_arr))),
        "{:.2f}".format(float(np.std(rates_arr, ddof=1))),
        "{:.2f}".format(float(np.min(rates_arr))),
        "{:.2f}".format(float(np.max(rates_arr)))
    ])

    print(table)

    # -- Target comparison ------------------------------------------------------
    mean_rate = float(np.mean(rates_arr))
    target_hz = 25.0
    print("\n  Target update rate : {:.1f} Hz".format(target_hz))
    print("  Measured mean rate : {:.2f} Hz".format(mean_rate))
    if mean_rate >= target_hz:
        print("  Status             : MEETS TARGET")
    else:
        print("  Status             : BELOW TARGET")


# ===========================================================================
# SECTION 4  --  CSV output
# ===========================================================================

def save_timing_csv(sweep_times: list) -> str:
    """
    Write per-sweep timing records to a time-stamped CSV.

    Columns: Sweep_Number, Sweep_Time_s, Update_Rate_Hz

    Returns the absolute path of the written file.
    """

    output_dir = os.path.normpath(
        os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
    )
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = "sweep_speed_baseline_{}.csv".format(timestamp)
    full_path = os.path.join(output_dir, filename)

    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Sweep_Number", "Sweep_Time_s", "Update_Rate_Hz"])
        for idx, t in enumerate(sweep_times, start=1):
            rate = 1.0 / t if t > 0 else float('inf')
            writer.writerow([idx, "{:.6f}".format(t), "{:.4f}".format(rate)])

    return full_path


def save_trace_csv(freq_hz: list, s11_db: list, prefix: str) -> str:
    """
    Write a single S11 trace to a time-stamped CSV.

    Columns: Frequency_Hz, S11_dB

    Parameters
    ----------
    freq_hz : list[float]  -- frequency axis in Hz.
    s11_db  : list[float]  -- S11 magnitude in dB.
    prefix  : str          -- filename prefix (e.g. "sweep_speed_last_trace").

    Returns the absolute path of the written file.
    """

    output_dir = os.path.normpath(
        os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
    )
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = "{}_{}.csv".format(prefix, timestamp)
    full_path = os.path.join(output_dir, filename)

    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Frequency_Hz", "S11_dB"])
        for f, s in zip(freq_hz, s11_db):
            writer.writerow([f, s])

    return full_path


# ===========================================================================
# main
# ===========================================================================

def main() -> None:
    """
    Entry point.  Orchestrates connect -> calibrate -> configure ->
    timed loop -> statistics -> CSV export.
    """

    # ------------------------------------------------------------------
    # 1. Connect and verify device presence
    # ------------------------------------------------------------------
    vna = connect_and_verify()

    # ------------------------------------------------------------------
    # 1b. Load calibration into the GUI
    # ------------------------------------------------------------------
    load_calibration(vna)

    # ------------------------------------------------------------------
    # 2. Configure sweep (everything except STOP)
    # ------------------------------------------------------------------
    configure_sweep(vna, ifbw_hz=IFBW_HZ)

    # ------------------------------------------------------------------
    # 3. Run the timed sweep loop
    # ------------------------------------------------------------------
    sweep_times, last_freq_hz, last_s11_db = run_timed_sweeps(
        vna, NUM_SWEEPS
    )

    # ------------------------------------------------------------------
    # 4. Print statistics
    # ------------------------------------------------------------------
    print_timing_summary(sweep_times)

    # ------------------------------------------------------------------
    # 5. Save timing CSV
    # ------------------------------------------------------------------
    _section("SAVING RESULTS")
    timing_csv_path = save_timing_csv(sweep_times)
    print("  Timing CSV      : {}".format(timing_csv_path))

    # ------------------------------------------------------------------
    # 6. Save last-sweep trace CSV
    # ------------------------------------------------------------------
    trace_csv_path = save_trace_csv(
        last_freq_hz, last_s11_db, "sweep_speed_last_trace"
    )
    print("  Last trace CSV  : {}".format(trace_csv_path))

    print()  # trailing blank line


if __name__ == "__main__":
    main()
