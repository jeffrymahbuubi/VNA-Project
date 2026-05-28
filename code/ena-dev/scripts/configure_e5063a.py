"""configure_e5063a.py — recall cal state and pin the locked operating point.

What this does (per SPEC §4A.4 and §4A.5):

1. Connect to the E5063A over USBTMC.
2. Resolve the cal state path:
     - If it points to an EXISTING FILE on the host, upload it to the
       instrument first (:MMEM:TRAN binary block) and recall from there.
     - Otherwise treat it as an INSTRUMENT-SIDE path (e.g. "D:\\State03.sta")
       and recall directly.
3. Verify cal is active via :SENS1:CORR:STAT?.
4. Idempotently re-assert the locked operating point:
       Start  =  200 MHz
       Stop   =  250 MHz
       Points =  801
       IFBW   =  300 kHz
       Power  = -5 dBm
       Meas   =  S11 (channel 1, trace 1, format MLOG)
5. Set binary transfer (REAL32 + SWAP) so subsequent reads are fast.
6. Print a one-screen summary.

This is the canonical "start-of-session" setup for any ena-dev script that
needs the instrument in the migration's locked state.

Run from code/:
    # Instrument-side path (already on the E5063A)
    uv run python ena-dev/scripts/configure_e5063a.py
    uv run python ena-dev/scripts/configure_e5063a.py --cal-state "D:\\State03.sta"

    # Host-side path (auto-upload to D:\\<basename> on the instrument)
    uv run python ena-dev/scripts/configure_e5063a.py \\
        --cal-state ../references/reports/20260528/myCal_200M_250M_801pt.sta

    # Custom upload destination on the instrument
    uv run python ena-dev/scripts/configure_e5063a.py \\
        --cal-state <host_path> --upload-to "D:\\myCal.sta"

    # Skip binary transfer (keep ASCII)
    uv run python ena-dev/scripts/configure_e5063a.py --no-binary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap: register ena_qt6_suite on sys.path and apply the Windows VISA
# PATH fix at import time.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ena_dev_paths  # noqa: F401, E402

from core.visa_connection import ENAConnection, ENAConnectionError  # noqa: E402


DEFAULT_RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"
DEFAULT_CAL_STATE = r"D:\State03.sta"
DEFAULT_TIMEOUT_MS = 15_000

# Locked operating point from SPEC §4A.4 (decided 2026-05-28)
LOCKED = {
    "start_hz": 200e6,
    "stop_hz":  250e6,
    "points":   801,
    "ifbw_hz":  300e3,
    "power_dbm": -5.0,
    "param":    "S11",
    "format":   "MLOG",
}


def _ok(msg: str, counter: dict) -> None:
    counter["pass"] += 1
    print(f"[OK]    {msg}")


def _fail(msg: str, counter: dict) -> None:
    counter["fail"] += 1
    print(f"[FAIL]  {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN]  {msg}")


def _info(msg: str) -> None:
    print(f"        {msg}")


def _is_close(actual_str: str, expected: float, rel_tol: float = 1e-6) -> bool:
    """E5063A returns numbers like '+2.00000000000E+008'. Compare with tolerance."""
    try:
        actual = float(actual_str)
    except (ValueError, TypeError):
        return False
    if expected == 0:
        return abs(actual) <= rel_tol
    return abs(actual - expected) / abs(expected) <= rel_tol


def _resolve_cal_path(
    cal_state_arg: str,
    upload_to: str | None,
) -> tuple[str, Path | None]:
    """Decide whether the argument is a host file (needs upload) or an
    instrument-side path (used as-is).

    Returns (instrument_path, host_path_to_upload_or_None).
    """
    host_candidate = Path(cal_state_arg).expanduser()
    if host_candidate.is_file():
        # Local file exists → upload to instrument first.
        dest = upload_to or f"D:\\{host_candidate.name}"
        return dest, host_candidate.resolve()
    # Otherwise treat as already-on-instrument path.
    return cal_state_arg, None


def configure(
    resource: str,
    cal_state_path: str,
    upload_to: str | None,
    enforce_binary: bool,
    timeout_ms: int,
) -> int:
    counter = {"pass": 0, "fail": 0}

    instrument_path, host_file = _resolve_cal_path(cal_state_path, upload_to)

    print("=" * 72)
    print("E5063A Configure — recall cal + pin locked operating point")
    print("=" * 72)
    print(f"Resource:        {resource}")
    if host_file is not None:
        print(f"Host file:       {host_file}  ({host_file.stat().st_size} bytes)")
        print(f"Upload target:   {instrument_path}")
    else:
        print(f"Instrument path: {instrument_path}")
    print(f"Binary I/O:      {'REAL32 + SWAP' if enforce_binary else 'ASCII (no change)'}")
    print()

    try:
        with ENAConnection(resource, timeout=timeout_ms) as ena:
            # --- 1. Clear status and identify ---
            ena.write("*CLS")
            idn = ena.query("*IDN?")
            if "E5063A" in idn:
                _ok(f"Connected: {idn}", counter)
            else:
                _fail(f"Unexpected instrument: {idn}", counter)
                return 1

            # --- 2a. Optional: upload host file → instrument ---
            if host_file is not None:
                print()
                print("--- Uploading cal state to instrument ---")
                file_bytes = host_file.read_bytes()
                # :MMEM:TRAN takes the destination path and an IEEE 488.2
                # binary block of the file contents.
                try:
                    ena.write_binary(
                        f':MMEM:TRAN "{instrument_path}",',
                        file_bytes,
                    )
                    ena.opc_wait()
                except ENAConnectionError as exc:
                    _fail(f"Upload via :MMEM:TRAN failed: {exc}", counter)
                    return 1
                code, msg = ena.error_check()
                if code != 0:
                    _fail(f"Upload error queue: {code}, '{msg}'", counter)
                    return 1
                _ok(
                    f"Uploaded {len(file_bytes):,} bytes → {instrument_path}",
                    counter,
                )

            # --- 2b. Recall cal state from instrument-side path ---
            print()
            print("--- Recalling cal state ---")
            ena.write(f':MMEM:LOAD:STAT "{instrument_path}"')
            ena.opc_wait()
            code, msg = ena.error_check()
            if code != 0:
                _fail(f"Cal recall failed: {code}, '{msg}'", counter)
                if host_file is None:
                    _info(
                        "Hint: --cal-state expects an instrument-side path like "
                        "'D:\\\\State03.sta'. Pass a host file path (must exist "
                        "on this PC) to auto-upload it first."
                    )
                return 1
            _ok(f"Cal state recalled from {instrument_path}", counter)

            # --- 3. Verify cal is active ---
            corr_state = ena.query(":SENS1:CORR:STAT?").strip()
            if corr_state == "1":
                _ok("Cal correction ACTIVE (:SENS1:CORR:STAT? = 1)", counter)
            else:
                _fail(
                    f"Cal correction NOT active after recall (got '{corr_state}'). "
                    "Was the cal state file saved with corrected data?",
                    counter,
                )

            corr_type = ena.query(":SENS1:CORR:TYPE1?").strip()
            _info(f"Cal type on port 1: {corr_type}")
            if corr_type.startswith("SOLT"):
                _ok(f"Cal method is SOLT-family: {corr_type.split(',')[0]}", counter)
            else:
                _warn(f"Cal method is not SOLT (got '{corr_type}') — proceeding anyway")

            # --- 4. Idempotently set locked operating point ---
            print()
            print("--- Pinning locked operating point ---")
            ena.write(f':SENS1:FREQ:STAR {LOCKED["start_hz"]:.6E}')
            ena.write(f':SENS1:FREQ:STOP {LOCKED["stop_hz"]:.6E}')
            ena.write(f':SENS1:SWE:POIN {LOCKED["points"]}')
            ena.write(f':SENS1:BAND:RES {LOCKED["ifbw_hz"]:.6E}')
            ena.write(f':SOUR1:POW {LOCKED["power_dbm"]:.3f}')
            ena.write(":SENS1:SWE:TYPE LIN")
            ena.write(":CALC1:PAR:COUN 1")
            ena.write(f':CALC1:PAR1:DEF {LOCKED["param"]}')
            ena.write(":CALC1:PAR1:SEL")
            ena.write(f':CALC1:FORM {LOCKED["format"]}')
            ena.opc_wait()
            code, msg = ena.error_check()
            if code != 0:
                _fail(f"Operating-point set failed: {code}, '{msg}'", counter)
                return 1
            _ok("Locked operating point written", counter)

            # --- 5. Verify what the instrument actually accepted ---
            start = ena.query(":SENS1:FREQ:STAR?")
            stop = ena.query(":SENS1:FREQ:STOP?")
            points = ena.query(":SENS1:SWE:POIN?")
            ifbw = ena.query(":SENS1:BAND:RES?")
            power = ena.query(":SOUR1:POW?")
            sweep_type = ena.query(":SENS1:SWE:TYPE?")
            param = ena.query(":CALC1:PAR1:DEF?")
            fmt = ena.query(":CALC1:FORM?")

            checks = [
                ("Start = 200 MHz",   _is_close(start, LOCKED["start_hz"])),
                ("Stop  = 250 MHz",   _is_close(stop, LOCKED["stop_hz"])),
                ("Points = 801",      points.strip().lstrip("+") == "801"),
                ("IFBW = 300 kHz",    _is_close(ifbw, LOCKED["ifbw_hz"])),
                ("Power = -5 dBm",    _is_close(power, LOCKED["power_dbm"], rel_tol=1e-3)),
                ("Sweep = LIN",       sweep_type.strip() == "LIN"),
                ("Param 1 = S11",     param.strip() == "S11"),
                ("Format = MLOG",     fmt.strip() == "MLOG"),
            ]
            print()
            print("--- Verification ---")
            for label, ok in checks:
                if ok:
                    _ok(label, counter)
                else:
                    _fail(label + " (mismatch — instrument did not accept the setting)", counter)

            # --- 6. Switch to binary transfer (optional) ---
            print()
            print("--- Data transfer format ---")
            if enforce_binary:
                ena.write(":FORM:DATA REAL32")
                ena.write(":FORM:BORD SWAP")
                ena.opc_wait()
                fmt_data = ena.query(":FORM:DATA?")
                fmt_bord = ena.query(":FORM:BORD?")
                if fmt_data.strip() in ("REAL32", "REAL,32"):
                    _ok(f"Data format set to REAL32 (got '{fmt_data.strip()}')", counter)
                else:
                    _fail(f"REAL32 not accepted: got '{fmt_data.strip()}'", counter)
                if fmt_bord.strip() == "SWAP":
                    _ok("Byte order SWAP (little-endian for PC)", counter)
                else:
                    _fail(f"Byte order SWAP not accepted: got '{fmt_bord.strip()}'", counter)
            else:
                _info("Skipping binary format (--no-binary). Default ASCII transfer in effect.")

            # --- 7. Final clean error check ---
            print()
            code, msg = ena.error_check()
            if code == 0:
                _ok(f"Final error queue clean: 0, '{msg}'", counter)
            else:
                _fail(f"Final error queue NOT clean: {code}, '{msg}'", counter)

    except ENAConnectionError as exc:
        _fail(f"Connection error: {exc}", counter)
        return 1

    print()
    print("=" * 72)
    print(f"Result: {counter['pass']} OK, {counter['fail']} FAIL")
    print("=" * 72)
    return 0 if counter["fail"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Recall E5063A cal state and pin locked operating point."
    )
    p.add_argument("--resource", default=DEFAULT_RESOURCE,
                   help="VISA resource string (default: %(default)s)")
    p.add_argument("--cal-state", default=DEFAULT_CAL_STATE,
                   help="Cal state path. Accepts EITHER an instrument-side "
                        "path (e.g. 'D:\\\\State03.sta', used as-is) OR a "
                        "host file path that EXISTS on this PC (auto-uploaded "
                        "to the instrument first). Default: %(default)s")
    p.add_argument("--upload-to", default=None,
                   help="Destination filename on the instrument when "
                        "--cal-state is a host file. "
                        "Default: 'D:\\\\<basename-of-cal-state>'.")
    p.add_argument("--no-binary", action="store_true",
                   help="Leave data format as ASCII (skip REAL32 + SWAP)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS,
                   help="VISA timeout in ms (default: %(default)s)")
    args = p.parse_args(argv)
    return configure(
        resource=args.resource,
        cal_state_path=args.cal_state,
        upload_to=args.upload_to,
        enforce_binary=not args.no_binary,
        timeout_ms=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
