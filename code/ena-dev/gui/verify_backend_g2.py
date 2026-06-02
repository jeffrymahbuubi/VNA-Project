"""verify_backend_g2.py — headless live check of E5063ABackend (gui-spec G-2).

Exercises every backend method against the live E5063A (+ N7550A for ECal) without
the GUI, so the adapter layer is de-risked before it's wired into the presenter (G-3).

Run from code/ :
    uv run python ena-dev/gui/verify_backend_g2.py
    uv run python ena-dev/gui/verify_backend_g2.py --no-ecal   # skip the ~15 s ECal
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mvp.backend_e5063a import E5063ABackend, BackendError, DEFAULT_RESOURCE


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--resource", default=DEFAULT_RESOURCE)
    p.add_argument("--no-ecal", action="store_true", help="skip the live ECal step")
    args = p.parse_args(argv)

    ok = 0
    be = E5063ABackend(args.resource)
    print("=" * 64)
    print("E5063ABackend — G-2 live verification")
    print("=" * 64)
    try:
        info = be.connect()
        print(f"[OK]  connect/probe: {info['idn']}"); ok += 1

        rb = be.apply_config(200e6, 250e6, 801, 300e3, -5.0)
        print(f"[OK]  apply_config readback: {rb['start_hz']/1e6:g}-{rb['stop_hz']/1e6:g} MHz, "
              f"{rb['points']} pt, IFBW {rb['ifbw_hz']/1e3:g} kHz, {rb['power_dbm']:g} dBm"); ok += 1

        files = be.list_cal_files()
        print(f"[OK]  list_cal_files: {files}"); ok += 1

        path = be.detect_ecal(1)
        print(f"[OK]  detect_ecal(port 1): PATH? = {path}"); ok += 1

        if not args.no_ecal:
            res = be.run_ecal(200e6, 250e6, 801, 300e3, -5.0, port=1,
                              on_progress=lambda pct: print(f"        ECal progress {pct}%"))
            lo, mid, hi = res["conf_min_mean_max"]
            print(f"[OK]  run_ecal: {res['cal_type']}, conf S11 min {lo:.2f}/mean {mid:.2f}/max {hi:.2f} dB, "
                  f"saved {res['sta_path']}"); ok += 1
        else:
            res = be.recall_cal(files[0])
            print(f"[OK]  recall_cal: {res['cal_type']} active"); ok += 1

        freqs, s11 = be.read_single_trace()
        idx = min(range(len(s11)), key=lambda i: s11[i])
        print(f"[OK]  read_single_trace: {len(s11)} pts, "
              f"min S11 {s11[idx]:.2f} dB @ {freqs[idx]/1e6:.3f} MHz"); ok += 1

        f0, mag = be.monitor_min_freq()
        print(f"[OK]  monitor_min_freq: {f0/1e6:.3f} MHz @ {mag:.2f} dB"); ok += 1

    except BackendError as exc:
        print(f"[FAIL] {exc}")
        be.close()
        return 1
    finally:
        be.close()

    print("=" * 64)
    print(f"Result: {ok} OK")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
