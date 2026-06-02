"""calibrate_e5063a.py — host-driven 1-port (S11) ECal on the Keysight E5063A.

Proves and performs **electronic calibration from the host PC** using the
Keysight N7550A ECal module — no front-panel interaction, no manual standard
swapping. This is the missing backend piece for the "one-stop" GUI
(configure → calibrate → sanity-check → continuous-measure); the configure /
sanity-check / continuous paths already exist (configure_e5063a.py,
bench_e5063a_realworld.py).

What it does
------------
1. Connect over USBTMC, *CLS, verify it is the E5063A.
2. Best-effort detect the ECal module on the target port
   (:SENS1:CORR:COLL:ECAL:PATH? <port>) — informational; the authoritative
   check is the error queue after the cal (codes 31/32 = ECal config failed /
   module not in RF path).
3. **Set the measurement geometry FIRST** — a cal is only valid at the
   start/stop/points/power/param present when it runs. (IFBW is set too, but
   note IFBW does NOT affect cal validity — SPEC §4A.6 — it is a free runtime
   knob; only the frequency grid forces a re-cal.)
4. Run the one-shot ECal:  :SENS1:CORR:COLL:ECAL:SOLT1 <port>  + *OPC?
   (the module internally measures Open/Short/Load, computes, auto-enables
   correction; blocks ~10–15 s).
5. Verify correction is active (:SENS1:CORR:STAT? = 1) and the applied type is
   SOLT-family (:SENS1:CORR:TYPE1?), and the error queue is clean.
6. Confidence read — one host-paced single sweep
   (:INIT1:IMM → :TRIG:SING → *OPC? → :CALC1:DATA:FDAT?) and report
   min / mean / max S11 (dB). NOT asserted — eyeball against expectation.
6b. **Restore live free-run** (:ABOR → :TRIG:SOUR INT → :INIT1:CONT ON) — the
   confidence sweep leaves the instrument in BUS-trigger + Hold, which FREEZES the
   front-panel live preview. This is done BEFORE the save so the .sta also captures
   the continuous state (otherwise recalling it would re-freeze the panel). This is
   the fix for the "preview hung after calibration" bug.
7. Auto-save the cal as a named state file on the instrument
   (:MMEM:STOR:STYP CST → :MMEM:STOR "D:\\cal_S11_<start>-<stop>MHz_<pts>pt.sta")
   so the exact grid can be recalled later WITHOUT re-cal, and pull a host-side
   copy (best-effort, :MMEM:TRAN?).
8. Leave the instrument in the canonical fast state (REAL32 + SWAP), correction ON,
   front-panel sweeping live.

Run from code/ :
    uv run python ena-dev/scripts/calibrate_e5063a.py                  # locked 200-250 MHz / 801 pt
    uv run python ena-dev/scripts/calibrate_e5063a.py --start-mhz 232 --stop-mhz 234 --points 401
    uv run python ena-dev/scripts/calibrate_e5063a.py --ifbw-khz 50 --power-dbm -5
    uv run python ena-dev/scripts/calibrate_e5063a.py --no-save        # cal hot in memory, do not write .sta
    uv run python ena-dev/scripts/calibrate_e5063a.py --no-host-copy   # save on instrument only

After this completes, configure_e5063a.py can recall the saved .sta, and
bench_e5063a_realworld.py can sweep at the calibrated grid.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Bootstrap: register ena_qt6_suite on sys.path and apply the Windows VISA
# PATH fix at import time.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ena_dev_paths  # noqa: F401, E402

from core.visa_connection import ENAConnection, ENAConnectionError  # noqa: E402


DEFAULT_RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"
# ECal blocks ~10-15 s; give *OPC? generous headroom.
DEFAULT_TIMEOUT_MS = 60_000

# Locked operating point from SPEC §4A.4 (decided 2026-05-28).
DEFAULT_START_MHZ = 200.0
DEFAULT_STOP_MHZ = 250.0
DEFAULT_POINTS = 801
DEFAULT_IFBW_KHZ = 300.0
DEFAULT_POWER_DBM = -5.0
DEFAULT_PORT = 1

# ECal error codes (SPEC / E5063A_SCPI_Reference §9 error map).
_ECAL_ERR_CODES = {31, 32}


def _ok(msg: str, c: dict) -> None:
    c["pass"] += 1
    print(f"[OK]    {msg}")


def _fail(msg: str, c: dict) -> None:
    c["fail"] += 1
    print(f"[FAIL]  {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN]  {msg}")


def _info(msg: str) -> None:
    print(f"        {msg}")


def _is_close(actual_str: str, expected: float, rel_tol: float = 1e-6) -> bool:
    try:
        actual = float(actual_str)
    except (ValueError, TypeError):
        return False
    if expected == 0:
        return abs(actual) <= rel_tol
    return abs(actual - expected) / abs(expected) <= rel_tol


def _drain_errors(ena: ENAConnection) -> list[tuple[int, str]]:
    """Drain the whole error queue. Returns the list of (code, msg) seen."""
    seen: list[tuple[int, str]] = []
    for _ in range(20):  # bounded — never loop forever on a stuck queue
        code, msg = ena.error_check()
        if code == 0:
            break
        seen.append((code, msg))
    return seen


def calibrate(
    resource: str,
    start_hz: float,
    stop_hz: float,
    points: int,
    ifbw_hz: float,
    power_dbm: float,
    port: int,
    save_sta: bool,
    instr_dir: str,
    host_copy: bool,
    skip_confidence: bool,
    timeout_ms: int,
) -> int:
    c = {"pass": 0, "fail": 0}

    start_mhz = start_hz / 1e6
    stop_mhz = stop_hz / 1e6
    cal_name = f"cal_S11_{start_mhz:g}-{stop_mhz:g}MHz_{points}pt.sta"
    instr_path = instr_dir.rstrip("\\/") + "\\" + cal_name

    print("=" * 72)
    print("E5063A Calibrate — host-driven 1-port (S11) ECal via N7550A")
    print("=" * 72)
    print(f"Resource:   {resource}")
    print(f"Geometry:   {start_mhz:g}–{stop_mhz:g} MHz, {points} pt, "
          f"IFBW {ifbw_hz/1e3:g} kHz, {power_dbm:g} dBm, S11, port {port}")
    print(f"Save .sta:  {'yes → ' + instr_path if save_sta else 'no (hot in memory only)'}")
    print("Note: IFBW does NOT affect cal validity (SPEC §4A.6) — only the "
          "frequency grid (start/stop/points) does.")
    print()

    try:
        with ENAConnection(resource, timeout=timeout_ms) as ena:
            # --- 1. Identify ---
            ena.write("*CLS")
            idn = ena.query("*IDN?")
            if "E5063A" in idn:
                _ok(f"Connected: {idn}", c)
            else:
                _fail(f"Unexpected instrument: {idn}", c)
                return 1

            # --- 2. Best-effort ECal module detection (informational) ---
            print()
            print("--- ECal module detection (informational) ---")
            try:
                path = ena.query(f":SENS{1}:CORR:COLL:ECAL:PATH? {port}").strip()
                errs = _drain_errors(ena)
                if errs:
                    _warn(f"ECAL:PATH? query set error(s): {errs} — proceeding; "
                          "the cal itself is the authoritative check")
                # 0 = no module on this instrument port; 1-4 = module port A-D.
                if path.lstrip("+").startswith("0"):
                    _warn(f"ECAL:PATH? port {port} = {path} (0 ⇒ no module seen). "
                          "If the N7550A is connected, it may report only at cal "
                          "time — continuing.")
                else:
                    _ok(f"ECal module reported on port {port}: PATH? = {path}", c)
            except ENAConnectionError as exc:
                _warn(f"ECAL:PATH? not answered ({exc}); continuing — the post-cal "
                      "error queue (31/32) is the real module check.")
                _drain_errors(ena)

            # --- 3. Geometry FIRST (cal is only valid at these settings) ---
            print()
            print("--- Setting measurement geometry (before cal) ---")
            ena.write(f":SENS1:FREQ:STAR {start_hz:.6E}")
            ena.write(f":SENS1:FREQ:STOP {stop_hz:.6E}")
            ena.write(f":SENS1:SWE:POIN {points}")
            ena.write(":SENS1:SWE:TYPE LIN")
            ena.write(f":SENS1:BAND:RES {ifbw_hz:.6E}")
            ena.write(f":SOUR1:POW {power_dbm:.3f}")
            ena.write(":CALC1:PAR:COUN 1")
            ena.write(":CALC1:PAR1:DEF S11")
            ena.write(":CALC1:PAR1:SEL")
            ena.write(":CALC1:FORM MLOG")
            ena.opc_wait()
            code, msg = ena.error_check()
            if code != 0:
                _fail(f"Geometry set failed: {code}, '{msg}'", c)
                return 1
            _ok("Geometry written (start/stop/points/IFBW/power/S11/MLOG)", c)

            # Verify readback of the cal-critical grid.
            checks = [
                ("Start", ena.query(":SENS1:FREQ:STAR?"), start_hz),
                ("Stop",  ena.query(":SENS1:FREQ:STOP?"), stop_hz),
                ("IFBW",  ena.query(":SENS1:BAND:RES?"),   ifbw_hz),
            ]
            for label, got, exp in checks:
                if _is_close(got, exp):
                    _ok(f"{label} readback = {float(got)/1e6:g} MHz"
                        if label != "IFBW" else f"{label} readback = {float(got)/1e3:g} kHz", c)
                else:
                    _fail(f"{label} readback mismatch: got '{got.strip()}', want {exp:g}", c)
            pts_got = ena.query(":SENS1:SWE:POIN?").strip().lstrip("+")
            if pts_got == str(points):
                _ok(f"Points readback = {pts_got}", c)
            else:
                _fail(f"Points readback mismatch: got '{pts_got}', want {points}", c)

            # --- 4. Run the one-shot ECal ---
            print()
            print(f"--- Running 1-port ECal on port {port} "
                  "(:CORR:COLL:ECAL:SOLT1) — blocks ~10–15 s ---")
            ena.write(f":SENS1:CORR:COLL:ECAL:SOLT1 {port}")
            ena.opc_wait()  # blocks until the module finishes O/S/L + compute
            errs = _drain_errors(ena)
            ecal_errs = [e for e in errs if e[0] in _ECAL_ERR_CODES]
            if ecal_errs:
                _fail(f"ECal reported module/path error(s): {ecal_errs}. "
                      "Check the N7550A is USB-connected to the E5063A and its "
                      f"Port A is cabled to instrument Port {port}.", c)
                return 1
            if errs:
                _fail(f"ECal left error(s) in the queue: {errs}", c)
                return 1
            _ok("ECal sequence completed with a clean error queue", c)

            # --- 5. Verify correction is active + SOLT ---
            print()
            print("--- Verifying calibration ---")
            corr_state = ena.query(":SENS1:CORR:STAT?").strip().lstrip("+")
            if corr_state == "1":
                _ok("Correction ACTIVE (:SENS1:CORR:STAT? = 1)", c)
            else:
                _fail(f"Correction NOT active after ECal (got '{corr_state}')", c)
            corr_type = ena.query(":SENS1:CORR:TYPE1?").strip()
            if corr_type.upper().startswith("SOLT") or "1" in corr_type.upper():
                _ok(f"Applied cal type on port {port}: {corr_type}", c)
            else:
                _warn(f"Cal type on port {port} = '{corr_type}' (expected SOLT-family)")

            # --- 6. Confidence sweep (report only, not asserted) ---
            # Use BINARY REAL32 for the trace read — ASCII :CALC:DATA:FDAT?
            # reads are flaky on this firmware (-410 Query INTERRUPTED /
            # truncation), the same issue the bench's Variant A hit.
            if not skip_confidence:
                print()
                print("--- Confidence sweep (host-paced single, REAL32) ---")
                try:
                    ena.write(":FORM:DATA REAL32")
                    ena.write(":FORM:BORD SWAP")
                    ena.write(":ABOR")
                    ena.write(":TRIG:SOUR BUS")
                    ena.write(":INIT1:CONT OFF")
                    ena.opc_wait()
                    ena.write(":INIT1:IMM")    # arm
                    ena.write(":TRIG:SING")    # fire
                    ena.opc_wait()             # block until sweep complete
                    raw = ena._session.query_binary_values(  # type: ignore[union-attr]
                        ":CALC1:DATA:FDAT?", datatype="f", is_big_endian=False
                    )
                    s11_db = list(raw[0::2])  # MLOG → (mag_dB, 0.0) pairs
                    if len(s11_db) == points:
                        lo, hi = min(s11_db), max(s11_db)
                        mean = sum(s11_db) / len(s11_db)
                        _ok(f"Read {len(s11_db)} pts — S11 min {lo:.3f} / "
                            f"mean {mean:.3f} / max {hi:.3f} dB", c)
                        _info("Eyeball: a well-matched 50 Ω load reads very "
                              "negative S11; a reflective/open termination reads "
                              "near 0 dB. Reconnect the real DUT for measurements.")
                    else:
                        _fail(f"Confidence read length {len(s11_db)} != {points}", c)
                    code, msg = ena.error_check()
                    if code != 0:
                        _warn(f"Confidence sweep left error: {code}, '{msg}'")
                except ENAConnectionError as exc:
                    _warn(f"Confidence sweep skipped (I/O error: {exc})")
                    _drain_errors(ena)

            # --- 6b. Restore live free-run BEFORE saving ---
            # The confidence sweep left the instrument in BUS-trigger + CONT OFF
            # (Hold), which FREEZES the front-panel live preview until a trigger
            # arrives. Restore internal free-run so the operator's display keeps
            # sweeping. Done before the save so the .sta also captures the live
            # (continuous) state — otherwise recalling it would re-freeze the panel.
            print()
            print("--- Restoring live front-panel sweep ---")
            ena.write(":ABOR")
            ena.write(":TRIG:SOUR INT")
            ena.write(":INIT1:CONT ON")
            ena.opc_wait()
            code, msg = ena.error_check()
            cont = ena.query(":INIT1:CONT?").strip().lstrip("+")
            trig = ena.query(":TRIG:SOUR?").strip()
            if code == 0 and cont == "1" and trig.upper().startswith("INT"):
                _ok(f"Live free-run restored (TRIG:SOUR={trig}, INIT:CONT={cont})", c)
            else:
                _fail(f"Live-restore not confirmed (code {code}, CONT={cont}, TRIG={trig})", c)

            # --- 7. Auto-save named .sta (hot + on-instrument + host copy) ---
            if save_sta:
                print()
                print("--- Saving calibrated state ---")
                ena.write(":MMEM:STOR:STYP CST")  # state + cal coefficients
                ena.write(f':MMEM:STOR "{instr_path}"')
                ena.opc_wait()
                code, msg = ena.error_check()
                if code != 0:
                    _fail(f"State save failed: {code}, '{msg}'", c)
                else:
                    _ok(f"Cal state saved on instrument: {instr_path}", c)
                    if host_copy:
                        _save_host_copy(ena, instr_path, cal_name, c)
            else:
                _info("--no-save: cal is hot in active memory only (no .sta written).")

            # --- 8. Leave instrument in canonical fast state ---
            print()
            print("--- Restoring fast transfer format ---")
            ena.write(":FORM:DATA REAL32")
            ena.write(":FORM:BORD SWAP")
            ena.opc_wait()
            code, msg = ena.error_check()
            if code == 0:
                _ok("REAL32 + SWAP set; final error queue clean", c)
            else:
                _fail(f"Final error queue NOT clean: {code}, '{msg}'", c)

    except ENAConnectionError as exc:
        _fail(f"Connection error: {exc}", c)
        return 1

    print()
    print("=" * 72)
    print(f"Result: {c['pass']} OK, {c['fail']} FAIL")
    if save_sta and c["fail"] == 0:
        print(f"Recall later with: configure_e5063a.py --cal-state \"{instr_path}\"")
    print("=" * 72)
    return 0 if c["fail"] == 0 else 1


def _save_host_copy(
    ena: ENAConnection, instr_path: str, cal_name: str, c: dict
) -> None:
    """Best-effort pull of the saved .sta back to the host for archival."""
    try:
        data = ena.query_binary(f':MMEM:TRAN? "{instr_path}"')
        if not data:
            _warn("Host copy: :MMEM:TRAN? returned no data — skipped.")
            _drain_errors(ena)
            return
        stamp = datetime.now().strftime("%Y%m%d")
        out_dir = Path(__file__).resolve().parent.parent / "data" / stamp / "cal"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / cal_name
        out_path.write_bytes(data)
        _ok(f"Host copy saved: {out_path} ({len(data):,} bytes)", c)
        _drain_errors(ena)
    except ENAConnectionError as exc:
        _warn(f"Host copy skipped (:MMEM:TRAN? failed: {exc})")
        _drain_errors(ena)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Host-driven 1-port (S11) ECal on the Keysight E5063A.")
    p.add_argument("--resource", default=DEFAULT_RESOURCE,
                   help="VISA resource string (default: %(default)s)")
    p.add_argument("--start-mhz", type=float, default=DEFAULT_START_MHZ,
                   help="Start frequency in MHz (default: %(default)s)")
    p.add_argument("--stop-mhz", type=float, default=DEFAULT_STOP_MHZ,
                   help="Stop frequency in MHz (default: %(default)s)")
    p.add_argument("--points", type=int, default=DEFAULT_POINTS,
                   help="Sweep points (default: %(default)s)")
    p.add_argument("--ifbw-khz", type=float, default=DEFAULT_IFBW_KHZ,
                   help="IF bandwidth in kHz (default: %(default)s; does NOT "
                        "affect cal validity)")
    p.add_argument("--power-dbm", type=float, default=DEFAULT_POWER_DBM,
                   help="Source power in dBm (default: %(default)s)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help="Instrument port for the 1-port cal (default: %(default)s)")
    p.add_argument("--no-save", action="store_true",
                   help="Do not write a .sta; keep the cal hot in memory only.")
    p.add_argument("--instr-dir", default="D:\\",
                   help="Instrument-side directory for the .sta (default: D:\\)")
    p.add_argument("--no-host-copy", action="store_true",
                   help="Do not pull a host-side copy of the saved .sta.")
    p.add_argument("--skip-confidence", action="store_true",
                   help="Skip the post-cal confidence sweep.")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS,
                   help="VISA timeout in ms (default: %(default)s)")
    args = p.parse_args(argv)

    return calibrate(
        resource=args.resource,
        start_hz=args.start_mhz * 1e6,
        stop_hz=args.stop_mhz * 1e6,
        points=args.points,
        ifbw_hz=args.ifbw_khz * 1e3,
        power_dbm=args.power_dbm,
        port=args.port,
        save_sta=not args.no_save,
        instr_dir=args.instr_dir,
        host_copy=not args.no_host_copy,
        skip_confidence=args.skip_confidence,
        timeout_ms=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
