"""investigate_cal_files.py — diagnose the 'new ECal .sta not found' bug (G-15).

Read-only probe of the E5063A's mass-memory catalog + the GUI's list_cal_files()
parsing, so we can see whether (a) :MMEM:CAT? actually lists the .sta files on D:\,
(b) the list_cal_files regex parses them (or silently falls back to 2 hardcoded
defaults), and (c) the N7550A ECal module is attached (so a live re-cal is possible).

    uv run python ena-dev/scripts/investigate_cal_files.py
"""
from __future__ import annotations

import re
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
    r.timeout = 8000
    try:
        print("IDN        :", r.query("*IDN?").strip())
        for d in (r'D:\\', r'D:', r'D:\\State'):
            try:
                raw = r.query(f':MMEM:CAT? "{d}"')
                print(f'\n:MMEM:CAT? "{d}" raw =\n{raw.strip()[:1500]}')
                # replicate backend.list_cal_files regex on the raw output:
                found = re.findall(r'([^",\\]+\.sta)', raw, flags=re.IGNORECASE)
                print(f'  regex .sta matches ({len(found)}): {found}')
            except Exception as exc:  # noqa: BLE001
                print(f'\n:MMEM:CAT? "{d}" -> ERROR {exc}')
        # ECal module presence on port 1 (0 = none, +1 = module A in path)
        try:
            print("\nECAL:PATH? 1 :", r.query(":SENS1:CORR:COLL:ECAL:PATH? 1").strip())
        except Exception as exc:  # noqa: BLE001
            print(f"\nECAL:PATH? 1 -> ERROR {exc}")
        print("SYST:ERR   :", r.query(":SYST:ERR?").strip())
    finally:
        r.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
