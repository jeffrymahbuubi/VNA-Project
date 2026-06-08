"""check_instrument_state.py — observe E5063A trigger/sweep state WITHOUT disturbing it.

Raw pyvisa, read-only: opens the session and queries *IDN? / :TRIG:SOUR? / :INIT1:CONT?
/ :SYST:ERR? only. Deliberately does NOT clear/abort/*CLS (unlike ENAConnection.connect),
so it reports the TRUE left-behind state — used to verify G-13 leaves the instrument in
live free-run (TRIG:SOUR INT, INIT1:CONT 1, clean queue) after Back/close.

Safe to run while the GUI holds its own session (USBTMC concurrent read works on this
E5063A) AS LONG AS the GUI is idle (not mid-query) — run it on the Setup page or after close.

    uv run python ena-dev/scripts/check_instrument_state.py
"""
from __future__ import annotations

import sys

RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"


def main() -> int:
    try:
        import pyvisa
    except ImportError as exc:  # noqa: BLE001
        print(f"FAIL import pyvisa: {exc}")
        return 2
    rm = pyvisa.ResourceManager()
    try:
        r = rm.open_resource(RESOURCE)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL open {RESOURCE}: {exc}")
        return 1
    r.timeout = 5000
    try:
        for label, q in (("IDN", "*IDN?"), ("TRIG:SOUR", ":TRIG:SOUR?"),
                         ("INIT1:CONT", ":INIT1:CONT?"), ("SYST:ERR", ":SYST:ERR?")):
            try:
                print(f"{label:12s} = {r.query(q).strip()}")
            except Exception as exc:  # noqa: BLE001
                print(f"{label:12s} = QUERY-ERROR {exc}")
    finally:
        r.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
