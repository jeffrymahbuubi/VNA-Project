#!/usr/bin/env python3
"""
librevna_cal_check.py
---------------------
Calibration-file loader and live device connection check for LibreVNA.

What it does (in order):
  1. Loads and parses the SOLT calibration JSON file, printing a structured
     summary of every field that matters for verification.
  2. Connects to LibreVNA-GUI over TCP on the user-configured port (1234).
  3. Runs the standard SCPI identification / health / serial-number sequence
     documented in the Programming Guide sections 4.1.1 (*IDN), 4.1.5 (*ESR),
     and 4.2.2 (DEVice:CONNect?).
  4. Compares the live device serial to the one recorded in the cal file and
     prints a consolidated info block.

All paths are relative to the script's own location so the tree is
portable.  No third-party packages are required beyond the project's own
libreVNA module, which lives in the same directory as this script.

Usage:
    python3 librevna_cal_check.py
"""

import sys
import os
import json
import time

# ---------------------------------------------------------------------------
# Paths -- all relative to this script's location so the whole tree is
# portable regardless of where it is checked out.
# ---------------------------------------------------------------------------

# Directory this script lives in.  libreVNA.py is co-located here so that
# all downstream scripts in this folder can share it.  sys.path.insert is
# used so that "import libreVNA" resolves correctly regardless of cwd.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# The SOLT calibration file produced by LibreVNA-GUI.
# Layout: script/ is a sibling of calibration/ under LibreVNA-dev/
CAL_FILE_PATH = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "calibration", "SOLT_1_2_43G-2_45G_300pt.cal")
)

# TCP connection parameters.  The user has configured LibreVNA-GUI to serve
# SCPI on port 1234 instead of the default 19542.
SCPI_HOST = "localhost"
SCPI_PORT = 1234

# ---------------------------------------------------------------------------
# Section divider helper (keeps output scannable without colour codes)
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


# ===========================================================================
# SECTION 1  --  Calibration file parsing
# ===========================================================================

def load_calibration(path):
    """
    Read the .cal JSON file and return the raw dict.
    Raises FileNotFoundError or json.JSONDecodeError on trouble.
    """
    with open(path, "r") as fh:
        return json.load(fh)


def summarise_calibration(cal):
    """
    Extract and print every piece of the calibration file that is relevant
    to a pre-measurement sanity check.  Returns a dict with the parsed
    summary so the rest of the script can use it without re-parsing.

    Key fields extracted
    --------------------
    cal_type        : top-level "type" (e.g. "SOLT")
    device_serial   : top-level "device" string
    cal_version     : top-level "version"
    calkit_version  : calkit.version (may differ from top-level)
    calkit_standards: list of {type, name} dicts from calkit.standards
    freq_min_hz     : lowest frequency across ALL measurement points
    freq_max_hz     : highest frequency across ALL measurement points
    measurements    : list of {type, port_info, num_points, is_2port}
    """

    summary = {}

    # -- Top-level metadata ------------------------------------------------
    summary["cal_type"]      = cal.get("type", "UNKNOWN")
    summary["device_serial"] = cal.get("device", "UNKNOWN")
    summary["cal_version"]   = cal.get("version", "UNKNOWN")
    summary["format"]        = cal.get("format", "UNKNOWN")
    summary["ports"]         = cal.get("ports", [])

    # -- Calkit block ------------------------------------------------------
    calkit = cal.get("calkit", {})
    summary["calkit_version"] = calkit.get("version", "UNKNOWN")

    # Each standard in calkit.standards has a "type" and params.name
    standards = calkit.get("standards", [])
    summary["calkit_standards"] = []
    for std in standards:
        std_type = std.get("type", "?")
        std_name = std.get("params", {}).get("name", "unnamed")
        summary["calkit_standards"].append({"type": std_type, "name": std_name})

    # -- Measurement blocks ------------------------------------------------
    # Walk every measurement entry, collect per-standard point counts and the
    # global frequency envelope.  1-port standards have frequency/real/imag
    # directly on each point; the Through (2-port) standard has frequency plus
    # an Sparam sub-dict.
    measurements_raw = cal.get("measurements", [])
    freq_all = []          # will hold every frequency value seen
    meas_summary = []      # per-measurement metadata

    for meas in measurements_raw:
        mtype   = meas.get("type", "?")
        data    = meas.get("data", {})
        points  = data.get("points", [])
        num_pts = len(points)

        # Determine whether this is a 1-port or 2-port measurement by
        # inspecting the first point (if any).  Through measurements carry
        # an "Sparam" key; the others carry "real"/"imag" at the top level.
        is_2port = False
        if num_pts > 0:
            is_2port = "Sparam" in points[0]

        # Collect frequencies (present on every point regardless of type)
        for pt in points:
            freq_all.append(pt["frequency"])

        # Port identification: 1-port uses "port", 2-port uses "port1"/"port2"
        if is_2port:
            port_info = "port1={}, port2={}".format(
                data.get("port1", "?"), data.get("port2", "?")
            )
        else:
            port_info = "port={}".format(data.get("port", "?"))

        meas_summary.append({
            "type":      mtype,
            "port_info": port_info,
            "num_points": num_pts,
            "is_2port":  is_2port,
            "timestamp": data.get("timestamp", None)
        })

    summary["measurements"] = meas_summary

    # Global frequency envelope (in Hz)
    if freq_all:
        summary["freq_min_hz"] = min(freq_all)
        summary["freq_max_hz"] = max(freq_all)
    else:
        summary["freq_min_hz"] = None
        summary["freq_max_hz"] = None

    # -- Print everything --------------------------------------------------
    _section("CALIBRATION FILE SUMMARY")
    print("  File            : {}".format(CAL_FILE_PATH))
    print("  Calibration type: {}".format(summary["cal_type"]))
    print("  Format version  : {}".format(summary["format"]))
    print("  Cal version     : {}".format(summary["cal_version"]))
    print("  Calkit version  : {}".format(summary["calkit_version"]))
    print("  Device serial   : {}".format(summary["device_serial"]))
    print("  Ports used      : {}".format(summary["ports"]))

    # Frequency range -- convert to GHz for readability, keep raw Hz too
    if summary["freq_min_hz"] is not None:
        print("  Freq range      : {:.6f} GHz  --  {:.6f} GHz".format(
            summary["freq_min_hz"] / 1e9,
            summary["freq_max_hz"] / 1e9
        ))
        print("                    ({} Hz  --  {} Hz)".format(
            int(summary["freq_min_hz"]),
            int(summary["freq_max_hz"])
        ))
    else:
        print("  Freq range      : NO MEASUREMENT POINTS FOUND")

    _subsection("Calkit standards")
    for std in summary["calkit_standards"]:
        print("    [{:<8s}] {}".format(std["type"], std["name"]))

    _subsection("Measurement records")
    # Header row
    print("    {:>2s}  {:<10s}  {:>8s}  {:<20s}  {:<12s}  {}".format(
        "#", "Type", "Points", "Port info", "2-port?", "Timestamp"
    ))
    print("    " + "-" * 66)
    for idx, m in enumerate(summary["measurements"], start=1):
        ts_str = str(m["timestamp"]) if m["timestamp"] else "N/A"
        print("    {:>2d}  {:<10s}  {:>8d}  {:<20s}  {:<12s}  {}".format(
            idx,
            m["type"],
            m["num_points"],
            m["port_info"],
            "YES" if m["is_2port"] else "no",
            ts_str
        ))

    return summary


# ===========================================================================
# SECTION 2  --  SCPI device connection and identification
# ===========================================================================

def connect_and_check(cal_summary):
    """
    Attempt to connect to LibreVNA-GUI via the libreVNA TCP wrapper, run the
    standard identification sequence, and return a dict with the results.

    The function NEVER raises.  On any failure it prints the error, fills in
    "FAILED" / None for the affected fields, and continues so that the
    consolidated info block in Section 3 can still print whatever is available.

    SCPI commands used (all documented in ProgrammingGuide.pdf)
    ------------------------------------------------------------
    *IDN?               -- 4.1.1  identification string
    *ESR?               -- 4.1.5  event status register (via get_status())
    DEVice:CONNect?     -- 4.2.2  serial of the connected device (or
                                  "Not connected")
    """

    result = {
        "connection_ok" : False,
        "idn_response"  : None,
        "esr_value"     : None,
        "esr_healthy"   : None,     # True / False / None (if query failed)
        "device_serial" : None,     # from DEVice:CONNect?
        "error_log"     : []        # human-readable errors encountered
    }

    _section("DEVICE CONNECTION CHECK")

    # -- Step A: import the module and instantiate the connection -----------
    # Insert the script's own directory at the front of sys.path so that
    # "import libreVNA" finds the co-located copy, not any system-installed one.
    sys.path.insert(0, SCRIPT_DIR)
    try:
        import libreVNA as libreVNA_mod   # module object
    except ImportError as exc:
        msg = (
            "ImportError: could not import libreVNA module from\n"
            "    {}\n"
            "  Detail: {}".format(SCRIPT_DIR, exc)
        )
        print("  [FAIL] " + msg)
        result["error_log"].append(msg)
        return result

    print("  Module path     : {}".format(
        os.path.abspath(libreVNA_mod.__file__)
    ))

    # The libreVNA class constructor opens the TCP socket immediately.
    # If LibreVNA-GUI is not running or the port is wrong, it raises.
    vna = None
    try:
        vna = libreVNA_mod.libreVNA(host=SCPI_HOST, port=SCPI_PORT)
        result["connection_ok"] = True
        print("  TCP connection  : OK  ({}:{})".format(SCPI_HOST, SCPI_PORT))
    except Exception as exc:
        msg = (
            "Connection failed to {}:{}.\n"
            "  Detail: {}\n"
            "  Action: verify that LibreVNA-GUI is running and that the\n"
            "          SCPI TCP server is enabled on port {}.".format(
                SCPI_HOST, SCPI_PORT, exc, SCPI_PORT
            )
        )
        print("  [FAIL] " + msg)
        result["error_log"].append(msg)
        return result   # nothing else can proceed without a socket

    # -- Step B: *IDN? -- identification ------------------------------------
    # Per the Programming Guide (4.1.1), the response format is:
    #   LibreVNA,LibreVNA-GUI,<serial>,<software version>
    # where <serial> is the connected device serial or "Not connected".
    _subsection("*IDN? identification")
    try:
        idn_raw = vna.query("*IDN?")
        result["idn_response"] = idn_raw
        print("  Raw response    : {}".format(idn_raw))

        # Parse the four comma-separated fields for display
        parts = [p.strip() for p in idn_raw.split(",")]
        labels = ["Manufacturer", "Model", "Serial (IDN)", "SW Version"]
        for label, val in zip(labels, parts):
            print("    {:<22s}: {}".format(label, val))
        # Pad with empty strings if fewer than 4 fields
        while len(parts) < 4:
            parts.append("")

    except Exception as exc:
        msg = "*IDN? query failed: {}".format(exc)
        print("  [FAIL] " + msg)
        result["error_log"].append(msg)
        # Not fatal -- continue to ESR and serial queries

    # -- Step C: *ESR? -- event status register ------------------------------
    # Per the Programming Guide (4.1.5) the return value is an integer.
    # Bit meanings (IEEE 488 standard, reproduced in the Guide):
    #   bit 0  (1)   OPC  - Operation complete
    #   bit 2  (4)   QYE  - Query error
    #   bit 3  (8)   DDE  - Device dependent error
    #   bit 4  (16)  EXE  - Execution error
    #   bit 5  (32)  CME  - Command error
    # A value of 0 means no flags are set -- the register is healthy.
    # Note: the libreVNA.get_status() method sends *ESR? internally and
    # returns the parsed integer, so we use it directly.
    _subsection("*ESR? status register")
    try:
        esr = vna.get_status()
        result["esr_value"] = esr

        if esr == 0:
            result["esr_healthy"] = True
            print("  ESR value       : {} (no flags set -- healthy)".format(esr))
        else:
            result["esr_healthy"] = False
            print("  ESR value       : {} (flags detected)".format(esr))
            # Decode and print every set bit
            bit_map = {
                1:   "OPC  - Operation complete",
                2:   "RQC  - Request control",
                4:   "QYE  - Query error",
                8:   "DDE  - Device dependent error",
                16:  "EXE  - Execution error",
                32:  "CME  - Command error",
                64:  "URQ  - User request",
                128: "PON  - Power on"
            }
            for bit_val in sorted(bit_map.keys()):
                if esr & bit_val:
                    print("    [SET] bit {:>3d}  {}".format(
                        bit_val, bit_map[bit_val]
                    ))

    except Exception as exc:
        msg = "*ESR? query failed: {}".format(exc)
        print("  [FAIL] " + msg)
        result["error_log"].append(msg)

    # -- Step D: DEVice:CONNect? -- device serial ----------------------------
    # Per the Programming Guide (4.2.2):
    #   Syntax  : DEVice:CONNect?
    #   Returns : <serialnumber>  OR the literal string "Not connected"
    # This is the authoritative source for the serial of whichever device
    # the GUI currently has open.
    _subsection("DEVice:CONNect? -- device serial")
    try:
        dev_serial = vna.query(":DEV:CONN?")
        result["device_serial"] = dev_serial
        print("  Live serial     : {}".format(dev_serial))

        if dev_serial == "Not connected":
            print("  [WARN] LibreVNA-GUI is not connected to any hardware device.")
            result["error_log"].append(
                "DEVice:CONNect? returned 'Not connected' -- "
                "no hardware device is open in the GUI."
            )
    except Exception as exc:
        msg = "DEVice:CONNect? query failed: {}".format(exc)
        print("  [FAIL] " + msg)
        result["error_log"].append(msg)

    # -- Step E: VNA:CALibration:LOAD? -- load calibration file into GUI ------
    # Per the Programming Guide (4.3.55):
    #   Syntax  : VNA:CALibration:LOAD? <filename>
    #   Returns : TRUE or FALSE
    #   Note    : filenames must be absolute or relative to the GUI application.
    # After a successful load we confirm the active calibration type with:
    #   Syntax  : VNA:CALibration:ACTIVE?   (ProgrammingGuide 4.3.45)
    #   Returns : currently active calibration type (e.g. "SOLT")
    # Both are queries -- use vna.query(), not vna.cmd().
    # This step is non-fatal: a failure is logged and the script continues so
    # that the consolidated info block can still print everything else.
    _subsection("VNA:CAL:LOAD? -- loading calibration")
    try:
        cal_abs_path = os.path.normpath(os.path.abspath(CAL_FILE_PATH))
        print("  Cal file path   : {}".format(cal_abs_path))

        load_response = vna.query(":VNA:CAL:LOAD? " + cal_abs_path)
        print("  LOAD? response  : {}".format(load_response))

        if load_response == "TRUE":
            active_cal = vna.query(":VNA:CAL:ACTIVE?")
            print("  Active cal type : {}".format(active_cal))
        else:
            msg = (
                "VNA:CALibration:LOAD? returned '{}' for file\n"
                "    {}\n"
                "  The GUI may not be able to access this path.  If the GUI\n"
                "  runs on a different machine the path must be valid there.".format(
                    load_response, cal_abs_path
                )
            )
            print("  [WARN] " + msg)
            result["error_log"].append(msg)
    except Exception as exc:
        msg = "VNA:CALibration:LOAD? query failed: {}".format(exc)
        print("  [FAIL] " + msg)
        result["error_log"].append(msg)

    return result


# ===========================================================================
# SECTION 3  --  Consolidated info block
# ===========================================================================

def print_info_block(cal_summary, device_info):
    """
    Print the final side-by-side comparison block that lets the operator
    confirm everything in one glance before proceeding with a measurement.
    """

    _section("CONSOLIDATED DEVICE / CALIBRATION INFO")

    # -- Connection status --------------------------------------------------
    conn_status = "OK" if device_info["connection_ok"] else "FAILED"
    print("  Connection status : {}".format(conn_status))

    # -- Serial comparison --------------------------------------------------
    cal_serial  = cal_summary.get("device_serial", "N/A")
    live_serial = device_info.get("device_serial")

    print("  Cal file serial   : {}".format(cal_serial))

    if live_serial is None:
        print("  Live serial       : N/A  (not retrieved)")
        match_tag = "UNKNOWN"
    else:
        print("  Live serial       : {}".format(live_serial))
        if live_serial == "Not connected":
            match_tag = "UNKNOWN (device not connected)"
        elif live_serial == cal_serial:
            match_tag = "MATCH"
        else:
            match_tag = "*** MISMATCH ***"

    print("  Serial match      : {}".format(match_tag))

    # -- Calibration metadata -----------------------------------------------
    print("  Cal type          : {}".format(cal_summary.get("cal_type", "N/A")))
    if cal_summary.get("freq_min_hz") is not None:
        print("  Cal freq range    : {:.6f} GHz  --  {:.6f} GHz".format(
            cal_summary["freq_min_hz"] / 1e9,
            cal_summary["freq_max_hz"] / 1e9
        ))
    else:
        print("  Cal freq range    : N/A")

    # -- IDN echo -----------------------------------------------------------
    if device_info.get("idn_response"):
        print("  IDN response      : {}".format(device_info["idn_response"]))

    # -- ESR status echo ----------------------------------------------------
    if device_info.get("esr_value") is not None:
        healthy_str = "healthy" if device_info["esr_healthy"] else "FLAGS SET"
        print("  ESR value         : {}  ({})".format(
            device_info["esr_value"], healthy_str
        ))

    # -- Any errors that were collected along the way -----------------------
    if device_info["error_log"]:
        _subsection("Errors / warnings encountered")
        for i, err in enumerate(device_info["error_log"], start=1):
            print("    {}. {}".format(i, err))

    print()  # trailing blank line for visual separation


# ===========================================================================
# main
# ===========================================================================

def main():
    """
    Entry point.  Orchestrates the three sections:
      1. Load + summarise the calibration file.
      2. Connect to LibreVNA-GUI and run SCPI checks.
      3. Print the consolidated info block.

    Errors in either section are caught locally so that the other sections
    can still execute and print whatever information was successfully obtained.
    """

    # ------------------------------------------------------------------
    # 1. Calibration file
    # ------------------------------------------------------------------
    cal_summary = None
    try:
        cal_data    = load_calibration(CAL_FILE_PATH)
        cal_summary = summarise_calibration(cal_data)
    except FileNotFoundError:
        _section("CALIBRATION FILE SUMMARY")
        print("  [FAIL] File not found:\n"
              "         {}".format(CAL_FILE_PATH))
        cal_summary = {"device_serial": None, "freq_min_hz": None,
                       "freq_max_hz": None, "cal_type": "N/A"}
    except json.JSONDecodeError as exc:
        _section("CALIBRATION FILE SUMMARY")
        print("  [FAIL] JSON decode error in calibration file:\n"
              "         {}".format(exc))
        cal_summary = {"device_serial": None, "freq_min_hz": None,
                       "freq_max_hz": None, "cal_type": "N/A"}

    # ------------------------------------------------------------------
    # 2. Live device connection + SCPI queries
    # ------------------------------------------------------------------
    device_info = connect_and_check(cal_summary)

    # ------------------------------------------------------------------
    # 3. Consolidated info block
    # ------------------------------------------------------------------
    print_info_block(cal_summary, device_info)


if __name__ == "__main__":
    main()
