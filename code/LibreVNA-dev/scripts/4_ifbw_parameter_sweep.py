#!/usr/bin/env python3
"""
4_ifbw_parameter_sweep.py
--------------------------
Part 2(b) -- IFBW parameter-sweep test for LibreVNA.

What it does (in order):
  1. Opens a TCP connection to LibreVNA-GUI and confirms that a hardware
     device is attached (reuses connect_and_verify from script 2).
  2. Loads the SOLT calibration file into the GUI via SCPI (reuses
     load_calibration from script 2).
  3. For each IFBW in [50 kHz, 10 kHz, 1 kHz]:
       a. Configures the sweep with that IFBW (all params except STOP).
       b. Triggers the first sweep by sending VNA:FREQuency:STOP.
       c. Runs 10 consecutive sweeps, timing each one and reading the
          S11 trace after the timing window closes.
       d. Computes four metrics for that IFBW:
            - Mean sweep time (s)
            - Update rate (Hz) = 1 / mean sweep time
            - Noise floor (dB): mean of the per-sweep mean S11 values
              across all frequency points, then averaged across sweeps.
              More negative is better.
            - Trace jitter (dB): for each frequency point compute the
              std of S11_dB across the 10 sweeps, then take the mean of
              those per-point stds.  This is the mean trace-to-trace
              jitter.
       e. Saves all 10 traces to one CSV with columns
            Frequency_Hz, Sweep_1_S11_dB, ..., Sweep_10_S11_dB
  4. Prints a final PrettyTable comparing all three IFBW settings.
  5. Saves a summary CSV: ifbw_sweep_summary_<timestamp>.csv

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
* A calibrated 50-ohm matched load is connected to port 1 so that the
  S11 trace is deep (high return loss) and the noise floor / jitter
  metrics are meaningful.
* numpy and prettytable are available in the project venv.
* The data/ directory is a sibling of scripts/ under LibreVNA-dev/.

Usage:
    uv run python 4_ifbw_parameter_sweep.py
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
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from libreVNA import libreVNA  # noqa: E402

# ---------------------------------------------------------------------------
# Import connect_and_verify / load_calibration from script 2 via importlib.
# ---------------------------------------------------------------------------
_mod2 = importlib.import_module("2_s11_cal_verification_sweep")
connect_and_verify = _mod2.connect_and_verify
load_calibration   = _mod2.load_calibration

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# -- Sweep parameters (same span / points / power as the baseline) ----------
START_FREQ_HZ  = 2_430_000_000   # 2.430 GHz
STOP_FREQ_HZ   = 2_450_000_000   # 2.450 GHz
NUM_POINTS     = 300
STIM_LVL_DBM   = -10
AVG_COUNT      = 1

# -- IFBW values to characterise (tested in this order) ---------------------
IFBW_VALUES_HZ = [50_000, 10_000, 1_000]   # 50 kHz, 10 kHz, 1 kHz

# -- Per-IFBW sweep count ---------------------------------------------------
SWEEPS_PER_IFBW = 10

# -- Polling / timeout ------------------------------------------------------
POLL_INTERVAL_S   = 0.01
SWEEP_TIMEOUT_S   = 60.0

# ---------------------------------------------------------------------------
# Console-output helpers (identical style to scripts 1, 2, and 3)
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print("  " + title)
    print("=" * width)


def _subsection(title: str) -> None:
    print("\n  --- " + title + " ---")


# ===========================================================================
# SECTION 1  --  Sweep configuration (everything EXCEPT STOP)
# ===========================================================================

def configure_sweep(vna: libreVNA, ifbw_hz: int) -> None:
    """
    Send all sweep-configuration commands to the VNA except for
    VNA:FREQuency:STOP, which is the acquisition trigger.

    This function is called once per IFBW value.  Because IFBW is the
    only parameter that changes between IFBW settings the full
    re-configuration is intentional: it keeps the function self-contained
    and avoids assumptions about residual instrument state.

    SCPI sequence:
        :DEV:MODE VNA
        :VNA:SWEEP FREQUENCY
        :VNA:STIM:LVL <dBm>
        :VNA:ACQ:IFBW  <Hz>        <-- varies per call
        :VNA:ACQ:AVG   <n>
        :VNA:ACQ:POINTS <n>
        :VNA:FREQuency:START <Hz>

    Parameters
    ----------
    vna     : libreVNA
    ifbw_hz : int  -- IF bandwidth in Hz for this sweep setting.
    """

    _section("SWEEP CONFIGURATION  (IFBW = {} kHz)".format(ifbw_hz // 1000))

    vna.cmd(":DEV:MODE VNA")
    print("  Mode            : VNA")

    vna.cmd(":VNA:SWEEP FREQUENCY")
    print("  Sweep type      : FREQUENCY")

    vna.cmd(":VNA:STIM:LVL {}".format(STIM_LVL_DBM))
    print("  Stimulus level  : {} dBm".format(STIM_LVL_DBM))

    # VNA:ACquisition:IFBW  (ProgrammingGuide 4.3.13)
    vna.cmd(":VNA:ACQ:IFBW {}".format(ifbw_hz))
    print("  IF bandwidth    : {} Hz  ({} kHz)".format(
        ifbw_hz, ifbw_hz / 1000))

    vna.cmd(":VNA:ACQ:AVG {}".format(AVG_COUNT))
    print("  Averaging       : {} sweep(s)".format(AVG_COUNT))

    vna.cmd(":VNA:ACQ:POINTS {}".format(NUM_POINTS))
    print("  Points          : {}".format(NUM_POINTS))

    # START only -- STOP is the trigger, sent by the caller.
    vna.cmd(":VNA:FREQuency:START {}".format(START_FREQ_HZ))
    print("  Start freq      : {} Hz  ({:.3f} GHz)".format(
        START_FREQ_HZ, START_FREQ_HZ / 1e9))
    print("  Stop freq       : (will be sent as sweep trigger)")


# ===========================================================================
# SECTION 2  --  Per-IFBW sweep loop
# ===========================================================================

def run_ifbw_test(vna: libreVNA, ifbw_hz: int,
                  num_sweeps: int = SWEEPS_PER_IFBW) -> tuple:
    """
    Run num_sweeps consecutive S11 sweeps at the given IFBW and collect
    all timing and trace data.

    Timing protocol (same as script 3):
      1. Send STOP  -> triggers acquisition.
      2. t_start.
      3. Poll FIN?.
      4. t_end.
      5. Read trace (outside timed window).
      6. Parse + convert to dB.

    Parameters
    ----------
    vna        : libreVNA
    ifbw_hz    : int  -- IF bandwidth in Hz (already configured).
    num_sweeps : int  -- number of sweeps to run.

    Returns
    -------
    tuple[list[float], list[list[float]], list[float]]
        sweep_times  : wall-clock seconds per sweep.
        all_s11_db   : list of num_sweeps lists, each containing NUM_POINTS
                       S11 dB values.  Index [sweep][point].
        freq_hz      : frequency axis (same for every sweep).

    Raises
    ------
    TimeoutError
        If any single sweep does not finish within SWEEP_TIMEOUT_S.
    """

    _subsection("Running {} sweeps at IFBW = {} kHz".format(
        num_sweeps, ifbw_hz // 1000))

    sweep_times = []
    all_s11_db  = []   # list of lists
    freq_hz     = []   # populated on the first sweep, reused thereafter

    for i in range(num_sweeps):

        # -- Trigger ----------------------------------------------------------
        # VNA:FREQuency:STOP  (ProgrammingGuide 4.3.5)
        vna.cmd(":VNA:FREQuency:STOP {}".format(STOP_FREQ_HZ))

        # -- Time: start ------------------------------------------------------
        t_start = time.time()

        # -- Poll for completion ----------------------------------------------
        while True:
            finished = vna.query(":VNA:ACQ:FIN?")
            if finished == "TRUE":
                break
            if time.time() - t_start > SWEEP_TIMEOUT_S:
                raise TimeoutError(
                    "IFBW={} kHz, sweep {}/{}: VNA:ACQ:FIN? did not return "
                    "TRUE within {:.0f} s (last response: '{}')".format(
                        ifbw_hz // 1000, i + 1, num_sweeps,
                        SWEEP_TIMEOUT_S, finished)
                )
            time.sleep(POLL_INTERVAL_S)

        # -- Time: end --------------------------------------------------------
        t_end      = time.time()
        sweep_time = t_end - t_start
        sweep_times.append(sweep_time)

        # -- Read trace (outside timed window) --------------------------------
        raw_data = vna.query(":VNA:TRACE:DATA? S11")
        trace    = libreVNA.parse_VNA_trace_data(raw_data)

        # -- Convert to dB ----------------------------------------------------
        sweep_freq  = []
        sweep_s11db = []
        for fq, gamma in trace:
            magnitude = abs(gamma)
            if magnitude < 1e-12:
                magnitude = 1e-12
            s11_db = 20.0 * math.log10(magnitude)
            sweep_freq.append(float(fq))
            sweep_s11db.append(float(s11_db))

        # Keep the frequency axis from the first sweep (all sweeps share it).
        if i == 0:
            freq_hz = sweep_freq

        all_s11_db.append(sweep_s11db)

        # -- Progress line ----------------------------------------------------
        update_rate = 1.0 / sweep_time if sweep_time > 0 else float('inf')
        print("    Sweep {:>2d}/{:<2d}  :  {:.4f} s  ({:.1f} Hz)".format(
            i + 1, num_sweeps, sweep_time, update_rate))

    return sweep_times, all_s11_db, freq_hz


# ===========================================================================
# SECTION 3  --  Metric computation
# ===========================================================================

def compute_metrics(sweep_times: list, all_s11_db: list) -> dict:
    """
    Derive the four characterisation metrics from raw sweep data.

    Parameters
    ----------
    sweep_times : list[float]
        Wall-clock seconds for each sweep (length = num_sweeps).
    all_s11_db  : list[list[float]]
        S11 dB values.  Outer index = sweep, inner index = freq point.
        All inner lists must have the same length.

    Returns
    -------
    dict with keys:
        mean_sweep_time  : float  (seconds)
        update_rate      : float  (Hz)
        noise_floor      : float  (dB, negative)
        trace_jitter     : float  (dB, positive)

    Noise-floor definition
    ----------------------
    For each sweep compute the arithmetic mean of S11_dB across all
    frequency points.  Then average those per-sweep means across all
    sweeps.  A calibrated matched load should produce a very negative
    number (e.g. -40 dB or better).

    Trace-jitter definition
    -----------------------
    Build a 2-D array [sweep x point].  For each frequency-point column
    compute the sample std (ddof=1) across sweeps.  The trace jitter is
    the mean of those per-point stds.  This captures sweep-to-sweep
    repeatability without sensitivity to absolute offset.
    """

    times_arr = np.array(sweep_times)                # shape (N,)
    s11_arr   = np.array(all_s11_db)                 # shape (N, P)

    mean_sweep_time = float(np.mean(times_arr))
    update_rate     = 1.0 / mean_sweep_time if mean_sweep_time > 0 else float('inf')

    # Noise floor: mean of per-sweep means
    per_sweep_means = np.mean(s11_arr, axis=1)       # shape (N,)
    noise_floor     = float(np.mean(per_sweep_means))

    # Trace jitter: mean of per-point stds across sweeps
    per_point_stds  = np.std(s11_arr, axis=0, ddof=1)  # shape (P,)
    trace_jitter    = float(np.mean(per_point_stds))

    return {
        "mean_sweep_time": mean_sweep_time,
        "update_rate":     update_rate,
        "noise_floor":     noise_floor,
        "trace_jitter":    trace_jitter,
    }


# ===========================================================================
# SECTION 4  --  Console output
# ===========================================================================

def print_comparison_table(results: list) -> None:
    """
    Print a PrettyTable comparing all IFBW settings side by side.

    Parameters
    ----------
    results : list[dict]
        Each dict has keys: ifbw_hz, mean_sweep_time, update_rate,
        noise_floor, trace_jitter.
    """

    _section("IFBW PARAMETER SWEEP -- COMPARISON TABLE")

    table = PrettyTable()
    table.field_names = [
        "IFBW (kHz)",
        "Mean Sweep Time (s)",
        "Update Rate (Hz)",
        "Noise Floor (dB)",
        "Trace Jitter (dB)"
    ]

    for r in results:
        table.add_row([
            "{:>d}".format(r["ifbw_hz"] // 1000),
            "{:.4f}".format(r["mean_sweep_time"]),
            "{:.2f}".format(r["update_rate"]),
            "{:.2f}".format(r["noise_floor"]),
            "{:.4f}".format(r["trace_jitter"])
        ])

    print(table)


# ===========================================================================
# SECTION 5  --  CSV output
# ===========================================================================

def save_traces_csv(ifbw_hz: int, freq_hz: list, all_s11_db: list) -> str:
    """
    Write all sweeps for one IFBW setting to a single CSV.

    Columns: Frequency_Hz, Sweep_1_S11_dB, Sweep_2_S11_dB, ...

    Parameters
    ----------
    ifbw_hz     : int              -- IFBW in Hz (used in filename).
    freq_hz     : list[float]      -- frequency axis.
    all_s11_db  : list[list[float]] -- [sweep][point] S11 dB values.

    Returns the absolute path of the written file.
    """

    output_dir = os.path.normpath(
        os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
    )
    os.makedirs(output_dir, exist_ok=True)

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    ifbw_khz   = ifbw_hz // 1000
    filename   = "ifbw_{}kHz_traces_{}.csv".format(ifbw_khz, timestamp)
    full_path  = os.path.join(output_dir, filename)

    num_sweeps = len(all_s11_db)

    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)

        # Header: Frequency_Hz, Sweep_1_S11_dB, Sweep_2_S11_dB, ...
        header = ["Frequency_Hz"] + [
            "Sweep_{}_S11_dB".format(n + 1) for n in range(num_sweeps)
        ]
        writer.writerow(header)

        # One row per frequency point
        for pt_idx, freq in enumerate(freq_hz):
            row = [freq]
            for sweep_idx in range(num_sweeps):
                row.append(all_s11_db[sweep_idx][pt_idx])
            writer.writerow(row)

    return full_path


def save_summary_csv(results: list) -> str:
    """
    Write the per-IFBW summary metrics to a CSV.

    Columns: IFBW_Hz, IFBW_kHz, Mean_Sweep_Time_s, Update_Rate_Hz,
             Noise_Floor_dB, Trace_Jitter_dB

    Returns the absolute path of the written file.
    """

    output_dir = os.path.normpath(
        os.path.abspath(os.path.join(SCRIPT_DIR, "..", "data"))
    )
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = "ifbw_sweep_summary_{}.csv".format(timestamp)
    full_path = os.path.join(output_dir, filename)

    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "IFBW_Hz", "IFBW_kHz",
            "Mean_Sweep_Time_s", "Update_Rate_Hz",
            "Noise_Floor_dB", "Trace_Jitter_dB"
        ])
        for r in results:
            writer.writerow([
                r["ifbw_hz"],
                r["ifbw_hz"] // 1000,
                "{:.6f}".format(r["mean_sweep_time"]),
                "{:.4f}".format(r["update_rate"]),
                "{:.4f}".format(r["noise_floor"]),
                "{:.6f}".format(r["trace_jitter"])
            ])

    return full_path


# ===========================================================================
# main
# ===========================================================================

def main() -> None:
    """
    Entry point.  Orchestrates connect -> calibrate -> IFBW loop ->
    comparison table -> CSV export.
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
    # 2. IFBW loop
    # ------------------------------------------------------------------
    # Accumulates one result dict per IFBW value.  Also accumulates
    # per-IFBW trace data for the multi-sweep CSVs.
    all_results = []   # list of result dicts (with ifbw_hz added)

    for ifbw_hz in IFBW_VALUES_HZ:

        # -- Configure (everything except STOP) ---------------------------
        configure_sweep(vna, ifbw_hz=ifbw_hz)

        # -- Run sweeps ---------------------------------------------------
        sweep_times, all_s11_db, freq_hz = run_ifbw_test(
            vna, ifbw_hz, num_sweeps=SWEEPS_PER_IFBW
        )

        # -- Compute metrics ----------------------------------------------
        metrics = compute_metrics(sweep_times, all_s11_db)
        metrics["ifbw_hz"] = ifbw_hz   # tag for table / CSV output

        # -- Per-IFBW progress summary ------------------------------------
        _subsection("IFBW {} kHz -- metrics".format(ifbw_hz // 1000))
        print("    Mean sweep time : {:.4f} s".format(
            metrics["mean_sweep_time"]))
        print("    Update rate     : {:.2f} Hz".format(
            metrics["update_rate"]))
        print("    Noise floor     : {:.2f} dB".format(
            metrics["noise_floor"]))
        print("    Trace jitter    : {:.4f} dB".format(
            metrics["trace_jitter"]))

        all_results.append(metrics)

        # -- Save multi-sweep trace CSV for this IFBW ---------------------
        _subsection("Saving traces for IFBW {} kHz".format(
            ifbw_hz // 1000))
        traces_path = save_traces_csv(ifbw_hz, freq_hz, all_s11_db)
        print("    Traces CSV      : {}".format(traces_path))

    # ------------------------------------------------------------------
    # 3. Final comparison table
    # ------------------------------------------------------------------
    print_comparison_table(all_results)

    # ------------------------------------------------------------------
    # 4. Save summary CSV
    # ------------------------------------------------------------------
    _section("SAVING SUMMARY")
    summary_path = save_summary_csv(all_results)
    print("  Summary CSV     : {}".format(summary_path))

    print()  # trailing blank line


if __name__ == "__main__":
    main()
