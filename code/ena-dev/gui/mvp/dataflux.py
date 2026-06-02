"""dataflux.py — Dataflux-compatible CSV writer (NF-5 / F-10).

Byte-for-byte identical layout to the LibreVNA Monitor Mode export
(`LibreVNA-dev/gui/mvp/vna_backend.py::export_dataflux_csv`) so files load in
`code/LibreVNA-dev/scripts/8_plot_monitor_data.py` with no conversion:

  12 metadata rows · 2 blank rows · 1 column header · N data rows, CRLF endings.
  Data rows: HH:MM:SS.ffffff , +%.9E (Hz) , +%.9E (dB).

Only the values change for the E5063A (VNA Model = "E5063A", real serial).
"""

from __future__ import annotations

import csv
import os
from typing import Optional, Sequence


def write_dataflux_csv(
    records: Sequence,            # objects with .timestamp (datetime), .freq_hz, .s11_db
    *,
    vna_model: str,
    vna_serial: str,
    ifbw_hz: float,
    eff_log_interval_ms: float,
    start_hz: float,
    stop_hz: float,
    num_points: int,
    out_dir: str,
    filename: str,
    scientific: bool = True,
) -> Optional[str]:
    """Write the CSV and return its path (or None if there are no records).

    `scientific` (F-6): True → ``+%.9E`` (default, byte-compatible with the
    LibreVNA export); False → fixed-point decimal.
    """
    if not records:
        return None
    num_fmt = "{:+.9E}" if scientific else "{:.6f}"

    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, filename)

    start_dt = records[0].timestamp
    num_data = len(records)
    freq_start_mhz = start_hz / 1e6
    freq_stop_mhz = stop_hz / 1e6
    freq_span_mhz = freq_stop_mhz - freq_start_mhz
    ifbw_khz = ifbw_hz / 1000.0

    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        # Metadata header block (12 lines) — labels byte-identical to LibreVNA.
        w.writerow(["Application", "VNA-DATAFLUX"])
        w.writerow(["VNA Model", vna_model])
        w.writerow(["VNA Serial", vna_serial])
        w.writerow(["File Name", filename])
        w.writerow(["Start DateTime", start_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")])
        w.writerow(["Number of Data", num_data])
        w.writerow(["Log Interval(ms)", "{:.1f}".format(eff_log_interval_ms)])
        w.writerow(["Freq Start(MHz)", "{:.6f}".format(freq_start_mhz)])
        w.writerow(["Freq Stop(MHz)", "{:.6f}".format(freq_stop_mhz)])
        w.writerow(["Freq Span(MHz)", "{:.6f}".format(freq_span_mhz)])
        w.writerow(["IF Bandwidth(KHz)", "{:.3f}".format(ifbw_khz)])
        w.writerow(["Points", num_points])
        # Two blank lines.
        w.writerow([])
        w.writerow([])
        # Column header.
        w.writerow(["Time", "Marker Stimulus (Hz)", "Marker Y Real Value (dB)"])
        # Data rows.
        for r in records:
            w.writerow([
                r.timestamp.strftime("%H:%M:%S.%f"),
                num_fmt.format(r.freq_hz),
                num_fmt.format(r.s11_db),
            ])
    return csv_path
