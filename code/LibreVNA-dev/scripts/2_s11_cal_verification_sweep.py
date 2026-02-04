#!/usr/bin/env python3
"""
2_s11_cal_verification_sweep.py
--------------------------------
S11 calibration-verification sweep for LibreVNA.

What it does (in order):
  1. Opens a TCP connection to LibreVNA-GUI and confirms that a hardware
     device is attached (connect_and_verify).
  2. Configures a single-shot frequency sweep over the 2.43-2.45 GHz WiFi
     band, waits for acquisition to finish, reads the S11 trace, and
     converts every point to dB (run_s11_sweep).
  3. Writes the (frequency, S11_dB) pairs to a time-stamped CSV in the
     project data/ directory (save_csv).
  4. Evaluates a return-loss pass/fail criterion: the calibration plane
     is considered healthy when the minimum return loss across the band
     exceeds 30 dB (main).

SCPI commands used -- all documented in ProgrammingGuide.pdf (Jan 27 2026)
-------------------------------------------------------------------------
  *IDN?                        4.1.1   identification string
  DEVice:CONNect?              4.2.2   serial of connected device
  DEVice:MODE VNA              4.2.6   switch to vector-analyzer mode
  VNA:SWEEP FREQUENCY          4.3.1   select frequency-sweep type
  VNA:FREQuency:START <Hz>     4.3.3   start frequency in Hz
  VNA:FREQuency:STOP  <Hz>     4.3.5   stop  frequency in Hz
  VNA:STIMulus:LVL    <dBm>    4.3.24  stimulus output power in dBm
  VNA:ACquisition:IFBW <Hz>    4.3.13  IF bandwidth in Hz
  VNA:ACquisition:AVG  <n>     4.3.16  number of averaging sweeps
  VNA:ACquisition:POINTS <n>   4.3.15  points per sweep
  VNA:ACquisition:FINished?    4.3.18  TRUE when averaging is complete
  VNA:TRACe:DATA? S11          4.3.27  comma-separated [freq,re,im] tuples

Assumptions
-----------
* LibreVNA-GUI is running with its SCPI TCP server enabled on port 1234
  (the user's non-default port, consistent with 1_librevna_cal_check.py).
* A calibration has already been applied in the GUI so that the S11 trace
  reflects the calibrated reflection coefficient at the reference plane.
* The data/ directory is a sibling of scripts/ under LibreVNA-dev/.

Usage:
    python3 2_s11_cal_verification_sweep.py
"""

import sys
import os
import csv
import math
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths -- all relative to this script's location so the whole tree is
# portable regardless of where it is checked out.
# ---------------------------------------------------------------------------

# Directory this script lives in.  libreVNA.py is co-located here.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Insert SCRIPT_DIR at the front of sys.path so "from libreVNA import
# libreVNA" resolves to the co-located wrapper regardless of cwd.
sys.path.insert(0, SCRIPT_DIR)
from libreVNA import libreVNA  # noqa: E402  (import after sys.path tweak)

# ---------------------------------------------------------------------------
# Module-level sweep configuration constants
# ---------------------------------------------------------------------------

SCPI_HOST      = "localhost"
SCPI_PORT      = 1234            # user's custom port (matches script 1)

START_FREQ_HZ  = 2_430_000_000   # 2.430 GHz -- lower edge of band
STOP_FREQ_HZ   = 2_450_000_000   # 2.450 GHz -- upper edge of band
NUM_POINTS     = 300             # frequency points across the span
IFBW_HZ        = 50_000          # 50 kHz IF bandwidth (in Hz, per 4.3.13)
STIM_LVL_DBM   = -10             # stimulus power in dBm  (per 4.3.24)
AVG_COUNT      = 1               # single sweep, no moving average

# ---------------------------------------------------------------------------
# Acquisition-completion polling parameters
# ---------------------------------------------------------------------------

POLL_INTERVAL_S   = 0.1   # seconds between FINished? queries
SWEEP_TIMEOUT_S   = 60.0  # hard ceiling -- raise if exceeded

# ---------------------------------------------------------------------------
# Pass / fail criterion
# ---------------------------------------------------------------------------

RETURN_LOSS_THRESHOLD_DB = 30.0   # minimum return loss (positive dB) to PASS

# ---------------------------------------------------------------------------
# Console-output helpers (same style as 1_librevna_cal_check.py)
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
# SECTION 1  --  Connection and device verification
# ===========================================================================

def connect_and_verify() -> libreVNA:
    """
    Open a TCP connection to LibreVNA-GUI and confirm a hardware device is
    attached.

    Steps performed:
      1. Instantiate the libreVNA wrapper (opens TCP socket immediately).
      2. Query *IDN? and print the four-field identification string.
      3. Query DEVice:CONNect? -- abort with a clear message if the response
         is the literal string "Not connected".

    Returns
    -------
    libreVNA
        The connected and verified wrapper instance, ready for SCPI commands.

    Raises
    ------
    SystemExit
        If the TCP connection fails or the device is not connected.
    """

    _section("DEVICE CONNECTION")

    # -- TCP connection ------------------------------------------------------
    try:
        vna = libreVNA(host=SCPI_HOST, port=SCPI_PORT)
        print("  TCP connection  : OK  ({}:{})".format(SCPI_HOST, SCPI_PORT))
    except Exception as exc:
        print("  [FAIL] Could not connect to LibreVNA-GUI at {}:{}".format(
            SCPI_HOST, SCPI_PORT))
        print("         Detail: {}".format(exc))
        print("         Action: verify LibreVNA-GUI is running and the SCPI")
        print("                 server is enabled on port {}.".format(SCPI_PORT))
        sys.exit(1)

    # -- *IDN? identification ------------------------------------------------
    # Per ProgrammingGuide 4.1.1 the response is:
    #   LibreVNA,LibreVNA-GUI,<serial>,<software version>
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
        # Not fatal on its own -- the DEVice:CONNect? check below is the
        # authoritative gate.

    # -- DEVice:CONNect? -- device serial -------------------------------------
    # Per ProgrammingGuide 4.2.2 returns <serialnumber> or "Not connected".
    _subsection("DEVice:CONNect? -- device serial")
    try:
        dev_serial = vna.query(":DEV:CONN?")
        print("  Live serial     : {}".format(dev_serial))

        if dev_serial == "Not connected":
            print("  [FAIL] LibreVNA-GUI is not connected to any hardware device.")
            print("         Connect the device in the GUI and re-run this script.")
            sys.exit(1)
    except Exception as exc:
        print("  [FAIL] DEVice:CONNect? query failed: {}".format(exc))
        print("         Cannot confirm device presence -- aborting.")
        sys.exit(1)

    return vna


# ===========================================================================
# SECTION 2  --  Sweep configuration, acquisition, and data conversion
# ===========================================================================

def run_s11_sweep(vna: libreVNA) -> tuple:
    """
    Configure the VNA for a frequency sweep, wait for acquisition to
    complete, read the S11 trace, and convert every point to dB.

    SCPI command sequence (order matters)
    --------------------------------------
    :DEV:MODE VNA                  -- ensure VNA mode is active
    :VNA:SWEEP FREQUENCY           -- select frequency-sweep type
    :VNA:STIM:LVL  <dBm>          -- output power
    :VNA:ACQ:IFBW  <Hz>           -- IF bandwidth
    :VNA:ACQ:AVG   <n>            -- averaging count
    :VNA:ACQ:POINTS <n>           -- points per sweep
    :VNA:FREQuency:START <Hz>     -- start freq (integer Hz)
    :VNA:FREQuency:STOP  <Hz>     -- stop  freq (integer Hz)
                                     ^^^ setting STOP last triggers the sweep
    Polling
    -------
    :VNA:ACQ:FIN?                  -- returns "TRUE" when the required number
                                      of averages have been acquired

    Data retrieval
    --------------
    :VNA:TRACE:DATA? S11           -- returns [freq,real,imag],... string;
                                      parsed by parse_VNA_trace_data into
                                      list[(freq_hz, complex)]

    dB conversion
    -------------
    S11_dB = 20 * log10(|gamma|)   -- linear magnitude clamped to >= 1e-12
                                      to avoid log(0)

    Parameters
    ----------
    vna : libreVNA
        Connected wrapper instance returned by connect_and_verify().

    Returns
    -------
    tuple[list[float], list[float]]
        (freq_hz_list, s11_db_list) -- parallel lists, plain Python floats.

    Raises
    ------
    TimeoutError
        If VNA:ACQ:FIN? does not return "TRUE" within SWEEP_TIMEOUT_S seconds.
    """

    _section("SWEEP CONFIGURATION")

    # -- Switch to VNA mode --------------------------------------------------
    # DEVice:MODE VNA  (ProgrammingGuide 4.2.6)
    vna.cmd(":DEV:MODE VNA")
    print("  Mode            : VNA")

    # -- Sweep type: frequency sweep -----------------------------------------
    # VNA:SWEEP FREQUENCY  (ProgrammingGuide 4.3.1)
    vna.cmd(":VNA:SWEEP FREQUENCY")
    print("  Sweep type      : FREQUENCY")

    # -- Stimulus level (output power) ---------------------------------------
    # VNA:STIMulus:LVL <dBm>  (ProgrammingGuide 4.3.24)
    vna.cmd(":VNA:STIM:LVL {}".format(STIM_LVL_DBM))
    print("  Stimulus level  : {} dBm".format(STIM_LVL_DBM))

    # -- IF bandwidth --------------------------------------------------------
    # VNA:ACquisition:IFBW <Hz>  (ProgrammingGuide 4.3.13)
    # NOTE: the unit is Hz, not kHz -- confirmed in the Guide.
    vna.cmd(":VNA:ACQ:IFBW {}".format(IFBW_HZ))
    print("  IF bandwidth    : {} Hz  ({} kHz)".format(
        IFBW_HZ, IFBW_HZ / 1000))

    # -- Averaging count -----------------------------------------------------
    # VNA:ACquisition:AVG <n>  (ProgrammingGuide 4.3.16)
    vna.cmd(":VNA:ACQ:AVG {}".format(AVG_COUNT))
    print("  Averaging       : {} sweep(s)".format(AVG_COUNT))

    # -- Number of frequency points ------------------------------------------
    # VNA:ACquisition:POINTS <n>  (ProgrammingGuide 4.3.15)
    vna.cmd(":VNA:ACQ:POINTS {}".format(NUM_POINTS))
    print("  Points          : {}".format(NUM_POINTS))

    # -- Frequency range (START then STOP) -----------------------------------
    # VNA:FREQuency:START <Hz>  (ProgrammingGuide 4.3.3)
    # VNA:FREQuency:STOP  <Hz>  (ProgrammingGuide 4.3.5)
    # Both values are integers in Hz.  Setting STOP after START completes the
    # sweep window and the GUI begins acquisition automatically.
    vna.cmd(":VNA:FREQuency:START {}".format(START_FREQ_HZ))
    vna.cmd(":VNA:FREQuency:STOP {}".format(STOP_FREQ_HZ))
    print("  Frequency range : {} Hz  --  {} Hz  ({:.3f} - {:.3f} GHz)".format(
        START_FREQ_HZ, STOP_FREQ_HZ,
        START_FREQ_HZ / 1e9, STOP_FREQ_HZ / 1e9))

    # -- Poll for acquisition completion -------------------------------------
    # VNA:ACquisition:FINished?  (ProgrammingGuide 4.3.18)
    # Returns "TRUE" when <acquired sweeps> == <averaging sweeps>.
    _subsection("Waiting for sweep completion")
    sweep_start = time.time()
    while True:
        finished = vna.query(":VNA:ACQ:FIN?")
        elapsed  = time.time() - sweep_start

        if finished == "TRUE":
            print("  Sweep finished  : {:.2f} s".format(elapsed))
            break

        if elapsed > SWEEP_TIMEOUT_S:
            raise TimeoutError(
                "VNA:ACQ:FIN? did not return TRUE within {:.0f} s "
                "(last response: '{}')".format(SWEEP_TIMEOUT_S, finished)
            )

        time.sleep(POLL_INTERVAL_S)

    # -- Read trace data -----------------------------------------------------
    # VNA:TRACe:DATA? S11  (ProgrammingGuide 4.3.27)
    # Response: comma-separated [freq,real,imag] tuples (no newlines between
    # points; single trailing newline stripped by the wrapper).
    _subsection("Reading S11 trace data")
    raw_data = vna.query(":VNA:TRACE:DATA? S11")
    trace    = vna.parse_VNA_trace_data(raw_data)
    # trace is list[(freq_hz: float, gamma: complex)]

    print("  Points received : {}".format(len(trace)))

    # -- Convert to dB -------------------------------------------------------
    # S11_dB = 20 * log10(|gamma|)
    # Clamp |gamma| to a minimum of 1e-12 so that a perfect match (gamma = 0)
    # does not produce -inf.
    freq_hz_list: list = []
    s11_db_list:  list = []

    for freq_hz, gamma in trace:
        magnitude = abs(gamma)
        if magnitude < 1e-12:
            magnitude = 1e-12
        s11_db = 20.0 * math.log10(magnitude)
        freq_hz_list.append(float(freq_hz))
        s11_db_list.append(float(s11_db))

    print("  Conversion      : complete ({} points -> dB)".format(
        len(s11_db_list)))

    return (freq_hz_list, s11_db_list)


# ===========================================================================
# SECTION 3  --  CSV export
# ===========================================================================

def save_csv(freq_hz: list, s11_db: list,
             output_dir: str = None) -> str:
    """
    Write the sweep results to a time-stamped CSV file.

    File layout
    -----------
    Header row : Frequency_Hz,S11_dB
    Data rows  : one row per frequency point, plain decimal notation.

    Filename convention
    --------------------
    s11_sweep_<YYYYMMDD_HHMMSS>.csv

    Parameters
    ----------
    freq_hz   : list[float]
        Frequency values in Hz (length must equal len(s11_db)).
    s11_db    : list[float]
        Corresponding S11 magnitudes in dB.
    output_dir : str, optional
        Directory in which to create the CSV.  Defaults to the data/
        folder that is a sibling of scripts/ under LibreVNA-dev/.

    Returns
    -------
    str
        Absolute path of the written CSV file.

    Raises
    ------
    ValueError
        If freq_hz and s11_db have different lengths.
    """

    if len(freq_hz) != len(s11_db):
        raise ValueError(
            "freq_hz and s11_db must have the same length "
            "(got {} vs {})".format(len(freq_hz), len(s11_db))
        )

    # Default output directory: <SCRIPT_DIR>/../data/
    if output_dir is None:
        output_dir = os.path.join(SCRIPT_DIR, "..", "data")

    # Resolve to an absolute, normalised path and create if missing
    output_dir = os.path.normpath(os.path.abspath(output_dir))
    os.makedirs(output_dir, exist_ok=True)

    # Build filename with current timestamp
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = "s11_sweep_{}.csv".format(timestamp)
    full_path  = os.path.join(output_dir, filename)

    # Write CSV (standard library only)
    with open(full_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Frequency_Hz", "S11_dB"])
        for f, s in zip(freq_hz, s11_db):
            writer.writerow([f, s])

    return full_path


# ===========================================================================
# SECTION 4  --  Main orchestration and pass / fail evaluation
# ===========================================================================

def main() -> None:
    """
    Entry point.  Runs the three public functions in sequence and prints a
    structured summary including a pass/fail verdict based on return loss.

    Pass / fail rule
    ----------------
    Return loss at each point = -S11_dB  (positive when S11_dB is negative).
    If the minimum return loss across all points exceeds
    RETURN_LOSS_THRESHOLD_DB the calibration plane is declared healthy (PASS).
    Otherwise the script reports FAIL together with the worst-case frequency
    and return-loss value.
    """

    # ------------------------------------------------------------------
    # 1. Connect and verify
    # ------------------------------------------------------------------
    vna = connect_and_verify()

    # ------------------------------------------------------------------
    # 2. Run the S11 sweep
    # ------------------------------------------------------------------
    freq_hz_list, s11_db_list = run_s11_sweep(vna)

    # ------------------------------------------------------------------
    # 3. Save to CSV
    # ------------------------------------------------------------------
    _section("SAVING RESULTS")
    csv_path = save_csv(freq_hz_list, s11_db_list)
    print("  CSV written     : {}".format(csv_path))

    # ------------------------------------------------------------------
    # 4. Summary and pass / fail
    # ------------------------------------------------------------------
    _section("SWEEP SUMMARY")

    num_points   = len(freq_hz_list)
    freq_min_ghz = freq_hz_list[0]  / 1e9
    freq_max_ghz = freq_hz_list[-1] / 1e9
    s11_min_db   = min(s11_db_list)
    s11_max_db   = max(s11_db_list)

    print("  Points          : {}".format(num_points))
    print("  Frequency range : {:.6f} GHz  --  {:.6f} GHz".format(
        freq_min_ghz, freq_max_ghz))
    print("  S11 min         : {:.4f} dB".format(s11_min_db))
    print("  S11 max         : {:.4f} dB".format(s11_max_db))
    print("  CSV file        : {}".format(csv_path))

    # -- Return-loss evaluation ----------------------------------------------
    # Return loss = -S11_dB.  S11 is always <= 0 dB for a passive device so
    # return loss is always >= 0.  The worst case (lowest return loss) is at
    # the point where S11_dB is closest to 0 (i.e. max of s11_db_list).
    _subsection("Return-loss pass / fail")

    # Find the index of the worst-case point (highest S11_dB == lowest RL)
    worst_idx       = s11_db_list.index(s11_max_db)
    worst_freq_ghz  = freq_hz_list[worst_idx] / 1e9
    worst_rl_db     = -s11_max_db             # return loss at that point

    print("  Threshold       : {:.1f} dB return loss".format(
        RETURN_LOSS_THRESHOLD_DB))
    print("  Worst-case freq : {:.6f} GHz".format(worst_freq_ghz))
    print("  Worst-case RL   : {:.4f} dB  (S11 = {:.4f} dB)".format(
        worst_rl_db, s11_max_db))

    # Compute minimum return loss across the entire band.
    # min(RL) == -max(S11_dB) because RL = -S11_dB at every point.
    min_rl_db = -s11_max_db

    if min_rl_db > RETURN_LOSS_THRESHOLD_DB:
        print("\n  *** PASS -- minimum return loss {:.4f} dB > {:.1f} dB ***".format(
            min_rl_db, RETURN_LOSS_THRESHOLD_DB))
    else:
        print("\n  *** FAIL -- minimum return loss {:.4f} dB <= {:.1f} dB ***".format(
            min_rl_db, RETURN_LOSS_THRESHOLD_DB))
        print("             Worst case at {:.6f} GHz".format(worst_freq_ghz))

    print()  # trailing blank line for visual separation


if __name__ == "__main__":
    main()
