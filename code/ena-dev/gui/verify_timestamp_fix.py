"""verify_timestamp_fix.py — headless checks for the timestamp-integrity fix (F-5).

SPEC: docs/e5063a-timestamp-fix-spec.md. Two parts:

  A. No-Qt unit test of mvp.dataflux.DatafluxWriter: streaming append from a
     tight loop, mid-run file growth (crash durability), header patched in
     place at finalize, byte-exact 15-line layout, loader-compatible parse,
     dt continuum + ~zero duplicate timestamps.

  B. Offscreen end-to-end of the full GUI path with the STUB backend:
     connect → recall → proceed (preview) → Start → Stop, then the produced
     Dataflux CSV is parsed and checked with the 20260715 report's own metrics.

Run (from `code/`):
    uv run python ena-dev/gui/verify_timestamp_fix.py
Exit code 0 = all checks pass.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).parent))

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# shared: Dataflux CSV analysis (mirrors 8_plot_monitor_data.py's parsing)
# ---------------------------------------------------------------------------

def parse_metadata(csv_path: Path) -> dict:
    meta = {}
    with open(csv_path, encoding="utf-8") as fh:
        for i, raw in enumerate(fh):
            if i >= 12:
                break
            line = raw.rstrip("\n").rstrip("\r")
            if "," in line:
                key, _, val = line.partition(",")
                meta[key.strip()] = val.strip()
    return meta


def analyze_csv(csv_path: Path) -> dict:
    """Rows + the report's timestamp metrics (dt values, duplicates, monotonic)."""
    with open(csv_path, encoding="utf-8", newline="") as fh:
        raw_lines = fh.read().split("\r\n")
    data_lines = [ln for ln in raw_lines[15:] if ln]
    times = []
    for ln in data_lines:
        t_str = ln.split(",", 1)[0]
        times.append(datetime.strptime(t_str, "%H:%M:%S.%f"))
    secs = [(t - times[0]).total_seconds() for t in times]
    dts = [b - a for a, b in zip(secs, secs[1:])]
    dups = sum(1 for d in dts if d == 0.0)
    return {
        "n": len(data_lines),
        "distinct_dt_us": len({round(d * 1e6) for d in dts}),
        "dup_ratio": dups / len(dts) if dts else 0.0,
        "non_decreasing": all(d >= 0 for d in dts),
        "mean_dt_ms": 1000.0 * sum(dts) / len(dts) if dts else 0.0,
    }


# ---------------------------------------------------------------------------
# Part A — DatafluxWriter unit test (no Qt)
# ---------------------------------------------------------------------------

def part_a() -> None:
    print("\n== Part A: DatafluxWriter (streaming, header patch, timestamps) ==")
    for name in ("monotonic", "perf_counter"):
        info = time.get_clock_info(name)
        print(f"  clock {name}: {info.implementation}, res {info.resolution}")

    from mvp.dataflux import DatafluxWriter

    tmp = Path(tempfile.mkdtemp(prefix="ts_fix_A_"))
    anchor_wall = datetime.now()
    anchor_ns = time.perf_counter_ns()
    w = DatafluxWriter(
        vna_model="E5063A", vna_serial="TEST", ifbw_hz=300e3,
        start_hz=200e6, stop_hz=250e6, num_points=801,
        out_dir=str(tmp), filename="unit_test.csv",
        start_dt=anchor_wall, scientific=True,
    )
    N = 5000
    header_size = Path(w.csv_path).stat().st_size
    for i in range(N):
        t_ns = time.perf_counter_ns()
        gap_ns = 30_000 + (i % 64) * 2_000   # jittered 30–156 µs spacing (sweep-like)
        while time.perf_counter_ns() - t_ns < gap_ns:
            pass
        stamp_ns = time.perf_counter_ns()
        ts = anchor_wall + timedelta(seconds=(stamp_ns - anchor_ns) / 1e9)
        w.append(ts, 233.5e6 + i, -30.0)
        if i == 2500:
            time.sleep(2.5)   # > flush_s → rows must be durably on disk mid-run
            grown = Path(w.csv_path).stat().st_size
            check("file grows during acquisition (crash durability)",
                  grown > header_size + 100_000, f"{grown} bytes mid-run")
    path, n, eff_ms = w.finalize()
    check("finalize row count", n == N, f"n={n}")

    meta = parse_metadata(Path(path))
    check("header 'Number of Data' patched", meta.get("Number of Data") == str(N),
          repr(meta.get("Number of Data")))
    try:
        eff_hdr = float(meta.get("Log Interval(ms)", "nan"))
        check("header 'Log Interval(ms)' patched ≈ eff",
              abs(eff_hdr - eff_ms) < 0.1, f"hdr={eff_hdr} eff={eff_ms:.2f}")
    except ValueError:
        check("header 'Log Interval(ms)' patched ≈ eff", False,
              repr(meta.get("Log Interval(ms)")))

    with open(path, "rb") as fh:
        blob = fh.read()
    lines = blob.split(b"\r\n")
    check("15-line header layout (blank 13/14, col header 15)",
          lines[12] == b"" and lines[13] == b"" and lines[14].startswith(b"Time,"),
          f"line13={lines[12]!r} line15={lines[14][:20]!r}")
    check("patched header keeps fixed byte width",
          len(lines[5]) == len(b"Number of Data,") + 10, f"len={len(lines[5])}")

    m = analyze_csv(Path(path))
    check("dt continuum (broken clock gave ≤4 values)", m["distinct_dt_us"] > 50,
          f"{m['distinct_dt_us']} distinct dt values")
    check("duplicate timestamps ≈ 0 (was 16–26%)", m["dup_ratio"] < 0.01,
          f"{100*m['dup_ratio']:.3f}%")
    check("timestamps non-decreasing", m["non_decreasing"])


# ---------------------------------------------------------------------------
# Part B — offscreen GUI end-to-end with the STUB backend
# ---------------------------------------------------------------------------

def part_b() -> None:
    print("\n== Part B: offscreen STUB end-to-end (connect→recall→proceed→record) ==")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from mvp.main_window import MainWindow

    tmp = Path(tempfile.mkdtemp(prefix="ts_fix_B_"))
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.setup_page.resourceInput.setText("STUB")
    win.setup_page.saveDirInput.setText(str(tmp))
    win.acquire_page.stopModeSelector.setCurrentIndex(2)   # Manual (until Stop)

    QTimer.singleShot(0, win._on_connect)
    QTimer.singleShot(900, win._on_recall)
    QTimer.singleShot(1800, win._on_proceed)          # starts free-run preview
    QTimer.singleShot(2700, win._on_start)            # Start Record (opens writer)
    QTimer.singleShot(5700, win._on_stop)             # Stop (finalize CSV)
    QTimer.singleShot(6600, app.quit)
    app.exec()

    status = win.acquire_page.saveStatusLabel.text()
    print(f"  saveStatus: {status}")
    check("recording saved", status.startswith("Saved"), status[:100])
    csvs = list(tmp.glob("**/*.csv"))
    check("exactly one CSV produced", len(csvs) == 1, str(csvs))
    if csvs:
        meta = parse_metadata(csvs[0])
        m = analyze_csv(csvs[0])
        print(f"  rows={m['n']} mean_dt={m['mean_dt_ms']:.2f} ms "
              f"distinct_dt={m['distinct_dt_us']} dup={100*m['dup_ratio']:.2f}%")
        check("row count sane (~3 s of stub sweeps)", m["n"] > 100, f"n={m['n']}")
        check("'Number of Data' matches rows", meta.get("Number of Data") == str(m["n"]),
              f"hdr={meta.get('Number of Data')} rows={m['n']}")
        check("dt continuum in real pipeline", m["distinct_dt_us"] > 20,
              f"{m['distinct_dt_us']} distinct")
        check("duplicates ≈ 0 in real pipeline", m["dup_ratio"] < 0.01,
              f"{100*m['dup_ratio']:.3f}%")
        check("timestamps non-decreasing", m["non_decreasing"])
        check("Start DateTime header parses",
              bool(datetime.strptime(meta["Start DateTime"], "%Y-%m-%dT%H:%M:%S.%f")))
    win.close()


if __name__ == "__main__":
    part_a()
    part_b()
    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else 'FAILURES: ' + ', '.join(FAILURES)}")
    sys.exit(0 if not FAILURES else 1)
