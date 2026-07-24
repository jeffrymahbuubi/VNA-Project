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
import queue
import threading
import time
from datetime import datetime
from typing import Optional, Sequence, Tuple


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


class DatafluxWriter:
    """Incremental (streaming) Dataflux CSV writer — timestamp-fix SPEC D-3.

    The batch-at-Stop design (write_dataflux_csv over an in-RAM record list) is
    unbounded in RAM over 18-24 h runs and loses everything on a crash. This
    writer opens the file at Start and appends rows to disk DURING acquisition:

      hot path (any thread):  append(ts, freq, mag)  → queue.put, microseconds
      cold path (own thread): drain queue → format → write, flush every
                              `batch_rows` rows or `flush_s` seconds

    so disk latency can never delay the acquisition loop, RAM stays O(batch),
    and a crash loses at most one flush interval.

    Header: same 15-line layout as write_dataflux_csv. `Number of Data` and
    `Log Interval(ms)` are only known at Stop, so they are written as
    fixed-width space-padded placeholders and patched IN PLACE by finalize()
    (identical byte length → the file stays loadable by 8_plot_monitor_data.py,
    whose parse_metadata() .strip()s values and whose pandas load skips the
    header entirely). A crash before finalize() leaves the padded "0"
    placeholders — the data rows still load.
    """

    _PATCH_W = 10   # fixed field width for the two patched header values

    def __init__(
        self,
        *,
        vna_model: str,
        vna_serial: str,
        ifbw_hz: float,
        start_hz: float,
        stop_hz: float,
        num_points: int,
        out_dir: str,
        filename: str,
        start_dt: datetime,
        scientific: bool = True,
        batch_rows: int = 64,
        flush_s: float = 2.0,
    ):
        os.makedirs(out_dir, exist_ok=True)
        self.csv_path = os.path.join(out_dir, filename)
        self._num_fmt = "{:+.9E}" if scientific else "{:.6f}"
        self._batch = max(1, batch_rows)
        self._flush_s = max(0.1, flush_s)
        # writer-thread-owned tallies (read by finalize() only after join)
        self._count = 0
        self._first_ts: Optional[datetime] = None
        self._last_ts: Optional[datetime] = None
        self._error: Optional[BaseException] = None
        self._finalized = False

        # Binary mode so header patch offsets are exact byte offsets.
        self._fh = open(self.csv_path, "wb")
        self._write_header(vna_model, vna_serial, filename, start_dt,
                           ifbw_hz, start_hz, stop_hz, num_points)
        self._fh.flush()

        self._q: "queue.SimpleQueue" = queue.SimpleQueue()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="dataflux-writer")
        self._thread.start()

    # ── hot path ────────────────────────────────────────────
    def append(self, timestamp: datetime, freq_hz: float, s11_db: float) -> None:
        """Enqueue one row. Never blocks on the disk."""
        self._q.put((timestamp, freq_hz, s11_db))

    def queue_depth(self) -> int:
        """Health metric: rows accepted but not yet written (should stay ~0)."""
        return self._q.qsize()

    # ── header ──────────────────────────────────────────────
    def _write_header(self, vna_model, vna_serial, filename, start_dt,
                      ifbw_hz, start_hz, stop_hz, num_points):
        ph = "0".rjust(self._PATCH_W)   # strip()/int()/float() all tolerate padding
        lines = [
            "Application,VNA-DATAFLUX",
            f"VNA Model,{vna_model}",
            f"VNA Serial,{vna_serial}",
            f"File Name,{filename}",
            f"Start DateTime,{start_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')}",
            f"Number of Data,{ph}",
            f"Log Interval(ms),{ph}",
            "Freq Start(MHz),{:.6f}".format(start_hz / 1e6),
            "Freq Stop(MHz),{:.6f}".format(stop_hz / 1e6),
            "Freq Span(MHz),{:.6f}".format((stop_hz - start_hz) / 1e6),
            "IF Bandwidth(KHz),{:.3f}".format(ifbw_hz / 1000.0),
            f"Points,{num_points}",
            "",
            "",
            "Time,Marker Stimulus (Hz),Marker Y Real Value (dB)",
        ]
        offset = 0
        self._patch_offsets: dict[str, int] = {}
        for ln in lines:
            data = (ln + "\r\n").encode("utf-8")
            if ln.startswith("Number of Data,"):
                self._patch_offsets["count"] = offset + len(b"Number of Data,")
            elif ln.startswith("Log Interval(ms),"):
                self._patch_offsets["interval"] = offset + len(b"Log Interval(ms),")
            self._fh.write(data)
            offset += len(data)

    # ── writer thread ───────────────────────────────────────
    def _write_row(self, item) -> None:
        ts, freq_hz, s11_db = item
        row = "{},{},{}\r\n".format(
            ts.strftime("%H:%M:%S.%f"),
            self._num_fmt.format(freq_hz),
            self._num_fmt.format(s11_db),
        )
        self._fh.write(row.encode("utf-8"))
        self._count += 1
        if self._first_ts is None:
            self._first_ts = ts
        self._last_ts = ts

    def _run(self) -> None:
        try:
            last_flush = time.perf_counter()
            while True:
                try:
                    item = self._q.get(timeout=self._flush_s)
                except queue.Empty:
                    self._fh.flush()
                    last_flush = time.perf_counter()
                    continue
                if item is None:            # finalize sentinel (queue is FIFO,
                    break                   # so every earlier row was written)
                self._write_row(item)
                n = 1
                sentinel = False
                while n < self._batch:      # opportunistic drain up to one batch
                    try:
                        item = self._q.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        sentinel = True
                        break
                    self._write_row(item)
                    n += 1
                now = time.perf_counter()
                if sentinel:
                    break
                if n >= self._batch or now - last_flush >= self._flush_s:
                    self._fh.flush()
                    last_flush = now
            self._fh.flush()
        except BaseException as exc:  # noqa: BLE001 — surfaced by finalize()
            self._error = exc

    # ── finalize ────────────────────────────────────────────
    def finalize(self) -> Tuple[str, int, float]:
        """Drain the queue, patch the header, close. Idempotent.

        Returns (csv_path, n_rows, eff_log_interval_ms). Raises if the writer
        thread hit an I/O error (rows up to the last flush are on disk).
        """
        if self._finalized:
            eff = self._eff_ms()
            return self.csv_path, self._count, eff
        self._finalized = True
        self._q.put(None)
        self._thread.join(timeout=30.0)
        try:
            if self._error is None and not self._fh.closed:
                eff = self._eff_ms()
                self._fh.seek(self._patch_offsets["count"])
                self._fh.write(str(self._count).rjust(self._PATCH_W).encode("utf-8"))
                self._fh.seek(self._patch_offsets["interval"])
                self._fh.write("{:.1f}".format(eff).rjust(self._PATCH_W).encode("utf-8"))
        finally:
            try:
                self._fh.close()
            except OSError:
                pass
        if self._error is not None:
            raise RuntimeError(f"Dataflux writer thread failed: {self._error}")
        return self.csv_path, self._count, self._eff_ms()

    def _eff_ms(self) -> float:
        if self._count > 1 and self._first_ts and self._last_ts:
            span = (self._last_ts - self._first_ts).total_seconds()
            return 1000.0 * span / (self._count - 1)
        return 0.0
