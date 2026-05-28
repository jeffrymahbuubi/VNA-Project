"""probe_e5063a.py — Phase 1 sanity check: VISA + USBTMC + SCPI roundtrip.

What this script does (mirrors §4.2 of docs/e5063a-migration-spec.md):

1. Discover all VISA resources on the host via pyvisa.
2. Pick the Keysight USB device (vendor IDs 0x2A8D or 0x0957).
3. Open an ENAConnection (the Amp suite's wrapper).
4. Query *IDN? and verify it matches the expected E5063A signature.
5. Dump the current measurement config (start/stop/center/span/IFBW/points).
6. Check the SCPI error queue.

Acceptance: lines marked [OK] all succeed, [FAIL] count is 0.

Run from code/:
    cd code
    uv run python ena-dev/scripts/probe_e5063a.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap: add code/ena-dev/ (parent of scripts/) to sys.path so we can
# import the project-local ena_dev_paths shim. ena_dev_paths.py then adds
# code/ena_qt6_suite/ to sys.path so we can `from core.* import ...`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ena_dev_paths  # noqa: F401, E402  — side-effects only

import pyvisa  # noqa: E402

from core.visa_connection import ENAConnection, ENAConnectionError  # noqa: E402


KEYSIGHT_VIDS = ("0x2A8D", "0x0957")  # Keysight USB vendor IDs (post- and pre-2014)
EXPECTED_MODEL_PREFIX = "Keysight Technologies,E5063A"


def _find_keysight_usb(resources: tuple[str, ...]) -> str | None:
    for res in resources:
        if res.upper().startswith("USB") and any(vid.upper() in res.upper() for vid in KEYSIGHT_VIDS):
            return res
    return None


def main() -> int:
    pass_count = 0
    fail_count = 0

    def ok(msg: str) -> None:
        nonlocal pass_count
        pass_count += 1
        print(f"[OK]    {msg}")

    def fail(msg: str) -> None:
        nonlocal fail_count
        fail_count += 1
        print(f"[FAIL]  {msg}")

    print("=" * 72)
    print("E5063A Probe — Phase 1 sanity check")
    print("=" * 72)

    # --- 1. VISA backend ---
    try:
        rm = pyvisa.ResourceManager()
        ok(f"pyvisa backend loaded: {rm.visalib.library_path}")
    except Exception as exc:
        fail(f"pyvisa ResourceManager could not open: {exc}")
        return 1

    # --- 2. Resource discovery ---
    resources = rm.list_resources()
    print(f"        VISA resources visible: {resources or '(none)'}")
    target = _find_keysight_usb(resources)
    if target is None:
        fail(
            "No Keysight USB device found (looked for VID 0x2A8D or 0x0957). "
            "Is the E5063A powered on and the rear USB-B cable connected?"
        )
        return 1
    ok(f"Target USB resource: {target}")

    # --- 3. Open ENAConnection and query *IDN? ---
    try:
        with ENAConnection(target, timeout=10_000) as ena:
            idn = ena.query("*IDN?")
            if idn.startswith(EXPECTED_MODEL_PREFIX):
                ok(f"*IDN? matches expected E5063A signature: {idn}")
            else:
                fail(f"*IDN? response unexpected: {idn!r}")

            # --- 4. Measurement config dump ---
            config_queries = [
                ("Start freq (Hz)",       ":SENS1:FREQ:STAR?"),
                ("Stop freq (Hz)",        ":SENS1:FREQ:STOP?"),
                ("Center freq (Hz)",      ":SENS1:FREQ:CENT?"),
                ("Span (Hz)",             ":SENS1:FREQ:SPAN?"),
                ("IF bandwidth (Hz)",     ":SENS1:BAND:RES?"),
                ("Sweep points",          ":SENS1:SWE:POIN?"),
                ("Sweep type",            ":SENS1:SWE:TYPE?"),
                ("Source power (dBm)",    ":SOUR1:POW?"),
                ("Trigger source",        ":TRIG:SOUR?"),
                ("Continuous trigger",    ":INIT1:CONT?"),
            ]
            print("        --- Current measurement config ---")
            for label, query in config_queries:
                try:
                    value = ena.query(query)
                    print(f"            {label:<22s} = {value}")
                except ENAConnectionError as exc:
                    fail(f"{label}: query {query} failed — {exc}")

            # --- 5. SCPI error queue check ---
            code, msg = ena.error_check()
            if code == 0:
                ok(f"SCPI error queue clean: {code}, '{msg}'")
            else:
                fail(f"SCPI error queue NOT clean: {code}, '{msg}'")
    except ENAConnectionError as exc:
        fail(f"ENAConnection failed: {exc}")
        return 1

    # --- Summary ---
    print("=" * 72)
    print(f"Result: {pass_count} OK, {fail_count} FAIL")
    print("=" * 72)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
