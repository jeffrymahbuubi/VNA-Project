"""investigate_cal_load.py — confirm the 'different-config' .sta actually LOADS (G-15).

Loads the already-present D:\cal_S11_200-250MHz_201pt.sta (the user's different-config
ECal), checks correction is active + the grid switched to 201 pt, then restores the
801 pt cal + live free-run so the instrument is left clean. Proves save+load work and
isolates the bug to list_cal_files (the catalog query), not the cal itself.

    uv run python ena-dev/scripts/investigate_cal_load.py
"""
from __future__ import annotations

import sys

RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"
CAL_201 = r"D:\cal_S11_200-250MHz_201pt.sta"
CAL_801 = r"D:\cal_S11_200-250MHz_801pt.sta"


def main() -> int:
    import pyvisa
    r = pyvisa.ResourceManager().open_resource(RESOURCE)
    r.timeout = 15000
    try:
        print("IDN        :", r.query("*IDN?").strip())
        print("before     : points=", r.query(":SENS1:SWE:POIN?").strip(),
              "corr=", r.query(":SENS1:CORR:STAT?").strip())

        r.write(f':MMEM:LOAD:STAT "{CAL_201}"'); r.query("*OPC?")
        print(f"\nLOAD {CAL_201}")
        print("  err      :", r.query(":SYST:ERR?").strip())
        print("  corr     :", r.query(":SENS1:CORR:STAT?").strip(),
              "type=", r.query(":SENS1:CORR:TYPE1?").strip(),
              "points=", r.query(":SENS1:SWE:POIN?").strip())

        # restore the locked 801 pt cal + live free-run (leave instrument clean)
        r.write(f':MMEM:LOAD:STAT "{CAL_801}"'); r.query("*OPC?")
        r.write(":ABOR"); r.write(":TRIG:SOUR INT"); r.write(":INIT1:CONT ON"); r.query("*OPC?")
        print(f"\nrestored {CAL_801} + live: points=", r.query(":SENS1:SWE:POIN?").strip(),
              "corr=", r.query(":SENS1:CORR:STAT?").strip(),
              "trig=", r.query(":TRIG:SOUR?").strip(),
              "cont=", r.query(":INIT1:CONT?").strip())
        print("final err  :", r.query(":SYST:ERR?").strip())
    finally:
        r.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
