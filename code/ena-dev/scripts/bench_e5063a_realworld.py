"""bench_e5063a_realworld.py — real-world IFBW benchmark on the E5063A.

Mirrors the LibreVNA workflow documented in
``REPORT/20260205/20260205.pdf`` (formal sweep-speed report) at the E5063A
migration's locked operating point (200–250 MHz, 801 pts, port-1 S11).

What it does
------------
For each mode in {single, continuous}, sweep 8 IFBW values
(300/150/125/100/75/50/10/1 kHz) running N=30 sweeps per IFBW, capturing:

  * Per-sweep timing (s, ms, Hz)
  * Full S11 trace per sweep (dB)
  * Noise floor (mean of all S11 samples across all sweeps × points)
  * Trace jitter (mean over points of per-point std-dev across sweeps)

Trigger modes
-------------
* **Single**  — BUS source + INIT:CONT OFF; per sweep:
                ``:INIT1:IMM`` (arm) → ``:TRIG:SING`` (fire) → ``*OPC?`` (block)
                → ``:CALC1:DATA:FDAT?`` (read). This is the proven host-paced
                pattern from Phase 3 / SPEC §6.5.

* **Continuous** — INT source + INIT:CONT ON (instrument free-runs); per sweep:
                poll ``:STAT:OPER:EVEN?`` for bit-4 latched falling-edge of the
                Measuring bit. The Operation status NTR is set to ``0x10`` so
                each *end-of-sweep* sets the latch; reading the register clears
                it, so no events are missed even with millisecond-scale jitter
                in poll cadence. This is the closest pyvisa-friendly analog to
                LibreVNA's async streaming callback on port 19001.

Output
------
Two xlsx workbooks (one per mode) written to
``code/ena-dev/data/YYYYMMDD/``:

  * ``single_sweep_test_e5063a_YYYYMMDD_HHMMSS.xlsx``
  * ``continuous_sweep_test_e5063a_YYYYMMDD_HHMMSS.xlsx``

Each workbook has a ``Summary`` sheet plus one sheet per IFBW value
(``IFBW_<value>kHz``). The schema is byte-compatible with the LibreVNA
templates ``REPORT/20260205/{single,continuous}_sweep_test_20260205_*.xlsx``
so the user's report pipeline works unchanged.

Pre-requisites
--------------
Run ``configure_e5063a.py`` first to recall the calibration and pin the
operating point. This script will fail loudly if cal is not active.

Run from ``code/``::

    uv run python ena-dev/scripts/configure_e5063a.py
    uv run python ena-dev/scripts/bench_e5063a_realworld.py
    uv run python ena-dev/scripts/bench_e5063a_realworld.py --modes continuous
    uv run python ena-dev/scripts/bench_e5063a_realworld.py --ifbw 300,50,1
    uv run python ena-dev/scripts/bench_e5063a_realworld.py --n-sweeps 60
    uv run python ena-dev/scripts/bench_e5063a_realworld.py --format real64
    uv run python ena-dev/scripts/bench_e5063a_realworld.py --no-save

Data format (--format): real32 (REAL32, 4 B/num — default & recommended),
real64 (:FORM:DATA REAL, 8 B/num), or ascii. Empirically (2026-06-02, single
mode) real64 costs ~2-5 ms/sweep more than real32 (~4-13% rate hit, largest at
high IFBW) for no usable accuracy gain on S11 dB-mag — so real32 is the default.
Output filename embeds the format: ``{mode}_sweep_test_e5063a_{format}_<stamp>.xlsx``.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Bootstrap: make `core.*` importable + apply Windows VISA PATH fix.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ena_dev_paths  # noqa: F401, E402

from core.visa_connection import ENAConnection, ENAConnectionError  # noqa: E402


# ----- Defaults ------------------------------------------------------------
DEFAULT_RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"
DEFAULT_N_SWEEPS = 30
DEFAULT_IFBW_KHZ = [300, 150, 125, 100, 75, 50, 10, 1]
DEFAULT_MODES = ["single", "continuous"]
DEFAULT_TIMEOUT_MS = 30_000
DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

# Bit 4 of the Keysight ENA Operation Status register = Measuring.
# When INIT:CONT ON, this bit pulses 1 (sweep in progress) → 0 (sweep done).
_OPER_MEASURING_BIT = 0x0010

# Data-transfer format → (`:FORM:DATA` token, pyvisa binary datatype).
# NOTE: on the Keysight ENA the 64-bit token is `REAL` (not "REAL64"); `REAL32`
# is the 32-bit form; `ASC` is comma-separated text. datatype None = ASCII path.
#   "f" = IEEE-754 binary32 (4 B), "d" = IEEE-754 binary64 (8 B).
_FORMAT_MAP: dict[str, tuple[str, str | None]] = {
    "ascii":  ("ASC",    None),
    "real32": ("REAL32", "f"),
    "real64": ("REAL",   "d"),
}


# ----- Result container ----------------------------------------------------
@dataclass
class IfbwResult:
    mode: str
    ifbw_hz: float
    start_hz: float
    stop_hz: float
    points: int
    stim_dbm: float
    avg_count: int
    num_sweeps: int

    # Per-sweep wall-clock duration (s). Length = num_sweeps.
    sweep_times_s: list[float] = field(default_factory=list)

    # Frequency axis (Hz). Length = points.
    freq_axis_hz: list[float] = field(default_factory=list)

    # S11 magnitude (dB) per sweep. Shape: [num_sweeps][points].
    s11_traces_db: list[list[float]] = field(default_factory=list)

    # Derived metrics
    mean_time_s: float = 0.0
    mean_time_ms: float = 0.0
    std_dev_s: float = 0.0
    min_time_s: float = 0.0
    max_time_s: float = 0.0
    rate_hz: float = 0.0
    noise_floor_db: float = 0.0
    trace_jitter_db: float = 0.0
    error_queue_clean: bool = True
    error_message: str = ""


# ----- Instrument helpers --------------------------------------------------
def setup_common(
    ena: ENAConnection,
    start_hz: float,
    stop_hz: float,
    points: int,
    stim_dbm: float,
    fmt_token: str = "REAL32",
) -> None:
    """Pin the configuration shared by all variants. Cal must already be on.

    ``fmt_token`` is the ``:FORM:DATA`` argument: ``REAL32`` (32-bit binary),
    ``REAL`` (64-bit binary), or ``ASC`` (text). ``:FORM:BORD SWAP`` is applied
    for the binary formats only.
    """
    ena.write(":ABOR")
    ena.write("*CLS")
    ena.write(":DISP:ENAB OFF")
    ena.write(f":SENS1:FREQ:STAR {start_hz:.6E}")
    ena.write(f":SENS1:FREQ:STOP {stop_hz:.6E}")
    ena.write(f":SENS1:SWE:POIN {points}")
    ena.write(f":SOUR1:POW {stim_dbm}")
    ena.write(":CALC1:PAR:COUN 1")
    ena.write(":CALC1:PAR1:DEF S11")
    ena.write(":CALC1:PAR1:SEL")
    ena.write(":CALC1:FORM MLOG")
    ena.write(f":FORM:DATA {fmt_token}")
    if fmt_token != "ASC":
        ena.write(":FORM:BORD SWAP")
    ena.opc_wait()


def setup_mode_single(ena: ENAConnection) -> None:
    ena.write(":ABOR")
    ena.write(":TRIG:SOUR BUS")
    ena.write(":INIT1:CONT OFF")
    ena.opc_wait()


def setup_mode_continuous(ena: ENAConnection) -> None:
    """Configure Operation Status so :EVEN? latches falling edge of MEAS bit."""
    ena.write(":ABOR")
    # Default OPER PTR=0x7FFF (positive transitions latched), NTR=0 — we want
    # the opposite for the MEASuring bit so end-of-sweep is the latch event.
    ena.write(":STAT:OPER:PTR 0")
    ena.write(":STAT:OPER:NTR 16")           # bit 4 negative-transition latch
    ena.query(":STAT:OPER:EVEN?")            # clear any stale latched events
    ena.write(":TRIG:SOUR INT")
    ena.write(":INIT1:CONT ON")
    ena.opc_wait()


def fetch_freq_axis(
    ena: ENAConnection, points: int, datatype: str | None = "f"
) -> list[float]:
    """Read the stimulus frequency axis once. Returns N floats (Hz).

    ``datatype`` is the pyvisa binary datatype (``"f"``=REAL32, ``"d"``=REAL64),
    or ``None`` to read comma-separated ASCII. Must match the active ``:FORM:DATA``.
    """
    if datatype is None:
        data = ena.query_values(":SENS1:FREQ:DATA?")
    else:
        data = ena._session.query_binary_values(  # type: ignore[attr-defined]
            ":SENS1:FREQ:DATA?", datatype=datatype, is_big_endian=False
        )
    if len(data) != points:
        raise RuntimeError(
            f"Frequency axis length mismatch: got {len(data)}, expected {points}"
        )
    return list(data)


def read_s11_trace_db(
    ena: ENAConnection, points: int, datatype: str | None = "f"
) -> list[float]:
    """Read the S11 MLOG trace as N magnitudes (dB).

    ``:CALC1:DATA:FDAT?`` returns 2*N values for scalar formats like MLOG —
    pairs of ``(magnitude_dB, 0.0)``. We take every-other element. ``datatype``
    selects the transfer path (``"f"``=REAL32, ``"d"``=REAL64, ``None``=ASCII)
    and must match the active ``:FORM:DATA``.
    """
    if datatype is None:
        raw = ena.query_values(":CALC1:DATA:FDAT?")
    else:
        raw = ena._session.query_binary_values(  # type: ignore[attr-defined]
            ":CALC1:DATA:FDAT?", datatype=datatype, is_big_endian=False
        )
    if len(raw) != 2 * points:
        raise RuntimeError(
            f"FDAT length mismatch: got {len(raw)}, expected {2 * points}"
        )
    return list(raw[0::2])


# ----- Benchmark loops -----------------------------------------------------
def _bench_single_one_ifbw(
    ena: ENAConnection,
    ifbw_hz: float,
    n_sweeps: int,
    points: int,
    start_hz: float,
    stop_hz: float,
    stim_dbm: float,
    avg_count: int,
    freq_axis: list[float],
    datatype: str | None = "f",
) -> IfbwResult:
    """30-sweep run at a single IFBW, single mode."""
    ena.write(f":SENS1:BAND:RES {ifbw_hz:.6E}")
    setup_mode_single(ena)

    # Cold sweep + read (discarded — warmup so the LO is settled).
    ena.write(":INIT1:IMM")
    ena.write(":TRIG:SING")
    ena.opc_wait()
    read_s11_trace_db(ena, points, datatype)

    sweep_times_s: list[float] = []
    s11_traces_db: list[list[float]] = []
    for _ in range(n_sweeps):
        t0 = time.perf_counter_ns()
        ena.write(":INIT1:IMM")
        ena.write(":TRIG:SING")
        ena.opc_wait()
        trace = read_s11_trace_db(ena, points, datatype)
        t1 = time.perf_counter_ns()
        sweep_times_s.append((t1 - t0) / 1e9)
        s11_traces_db.append(trace)

    result = IfbwResult(
        mode="single",
        ifbw_hz=ifbw_hz,
        start_hz=start_hz,
        stop_hz=stop_hz,
        points=points,
        stim_dbm=stim_dbm,
        avg_count=avg_count,
        num_sweeps=n_sweeps,
        sweep_times_s=sweep_times_s,
        freq_axis_hz=freq_axis,
        s11_traces_db=s11_traces_db,
    )
    _finalize_metrics(result, ena)
    return result


def _wait_sweep_complete_latched(
    ena: ENAConnection, timeout_ns: int = int(15e9), poll_us: int = 1500
) -> bool:
    """Block until the Operation Event register's MEAS bit shows a fresh
    falling edge (sweep just ended). Returns True on success, False on timeout.

    The Event register latches transitions and clears on read, so even a slow
    poll loop (~1.5 ms cadence) cannot miss a completed sweep — at worst it
    detects multiple back-to-back sweeps as one event (we accept that and
    measure inter-poll time, which is what 'continuous' real-world rate is).
    """
    deadline = time.perf_counter_ns() + timeout_ns
    while True:
        ev = int(ena.query(":STAT:OPER:EVEN?"))
        if ev & _OPER_MEASURING_BIT:
            return True
        if time.perf_counter_ns() > deadline:
            return False
        time.sleep(poll_us / 1e6)


def _bench_continuous_one_ifbw(
    ena: ENAConnection,
    ifbw_hz: float,
    n_sweeps: int,
    points: int,
    start_hz: float,
    stop_hz: float,
    stim_dbm: float,
    avg_count: int,
    freq_axis: list[float],
    datatype: str | None = "f",
) -> IfbwResult:
    """30-sweep run at a single IFBW, continuous mode (free-run + latched poll)."""
    ena.write(f":SENS1:BAND:RES {ifbw_hz:.6E}")
    setup_mode_continuous(ena)

    # Drain stale latched events accumulated during IFBW switch / setup.
    ena.query(":STAT:OPER:EVEN?")

    # Warmup: wait for one sweep boundary then read & discard.
    if not _wait_sweep_complete_latched(ena):
        raise RuntimeError(
            f"Timed out waiting for first sweep at IFBW={ifbw_hz:.0f} Hz "
            f"(continuous mode warmup)"
        )
    read_s11_trace_db(ena, points, datatype)
    # Drain any latched events that fired during the warmup read.
    ena.query(":STAT:OPER:EVEN?")

    sweep_times_s: list[float] = []
    s11_traces_db: list[list[float]] = []
    t_prev = time.perf_counter_ns()
    for i in range(n_sweeps):
        if not _wait_sweep_complete_latched(ena):
            raise RuntimeError(
                f"Timed out waiting for sweep #{i + 1} at IFBW={ifbw_hz:.0f} Hz"
            )
        trace = read_s11_trace_db(ena, points, datatype)
        t_now = time.perf_counter_ns()
        sweep_times_s.append((t_now - t_prev) / 1e9)
        s11_traces_db.append(trace)
        t_prev = t_now

    result = IfbwResult(
        mode="continuous",
        ifbw_hz=ifbw_hz,
        start_hz=start_hz,
        stop_hz=stop_hz,
        points=points,
        stim_dbm=stim_dbm,
        avg_count=avg_count,
        num_sweeps=n_sweeps,
        sweep_times_s=sweep_times_s,
        freq_axis_hz=freq_axis,
        s11_traces_db=s11_traces_db,
    )
    _finalize_metrics(result, ena)
    return result


def _finalize_metrics(r: IfbwResult, ena: ENAConnection) -> None:
    """Compute mean/std/rate/noise-floor/jitter and check the error queue."""
    times = r.sweep_times_s
    r.mean_time_s = statistics.fmean(times)
    r.mean_time_ms = r.mean_time_s * 1000.0
    r.std_dev_s = statistics.pstdev(times) if len(times) > 1 else 0.0
    r.min_time_s = min(times)
    r.max_time_s = max(times)
    r.rate_hz = 1.0 / r.mean_time_s if r.mean_time_s > 0 else float("nan")

    n_sweeps = len(r.s11_traces_db)
    n_points = len(r.freq_axis_hz)
    if n_sweeps == 0 or n_points == 0:
        r.noise_floor_db = float("nan")
        r.trace_jitter_db = float("nan")
    else:
        # Noise floor = mean of S11(sweep, point) across all sweeps × points.
        all_vals = [v for trace in r.s11_traces_db for v in trace]
        r.noise_floor_db = sum(all_vals) / len(all_vals)
        # Trace jitter = mean over points of std across sweeps (population std).
        per_point_std: list[float] = []
        for pi in range(n_points):
            col = [r.s11_traces_db[si][pi] for si in range(n_sweeps)]
            per_point_std.append(statistics.pstdev(col) if len(col) > 1 else 0.0)
        r.trace_jitter_db = sum(per_point_std) / len(per_point_std)

    code, msg = ena.error_check()
    r.error_queue_clean = code == 0
    r.error_message = msg


# ----- xlsx writer ---------------------------------------------------------
def write_mode_xlsx(
    results: list[IfbwResult], out_path: Path, mode: str
) -> None:
    """Write one xlsx mirroring REPORT/20260205/{mode}_sweep_test_*.xlsx layout."""
    from openpyxl import Workbook

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append([f"VNA Sweep Test Summary -- {mode} mode"])
    summary.append([])
    summary.append([
        "Mode", "IFBW (kHz)",
        "Mean Time (s)", "Mean Time (ms)",
        "Std Dev (s)", "Min Time (s)", "Max Time (s)",
        "Rate (Hz)", "Noise Floor (dB)", "Trace Jitter (dB)",
    ])
    for r in results:
        ifbw_khz = r.ifbw_hz / 1e3
        summary.append([
            r.mode,
            int(ifbw_khz) if float(ifbw_khz).is_integer() else round(ifbw_khz, 4),
            round(r.mean_time_s, 4),
            round(r.mean_time_ms, 4),
            round(r.std_dev_s, 4),
            round(r.min_time_s, 4),
            round(r.max_time_s, 4),
            round(r.rate_hz, 2),
            round(r.noise_floor_db, 4),
            round(r.trace_jitter_db, 4),
        ])

    for r in results:
        ifbw_khz = r.ifbw_hz / 1e3
        ifbw_label = (
            f"{int(ifbw_khz)}kHz"
            if float(ifbw_khz).is_integer()
            else f"{ifbw_khz:g}kHz"
        )
        ws = wb.create_sheet(f"IFBW_{ifbw_label}")

        # Configuration block
        ws.append(["Configuration"])
        ws.append(["Mode", r.mode])
        ws.append(["IFBW (kHz)",
                   int(ifbw_khz) if float(ifbw_khz).is_integer() else round(ifbw_khz, 4)])
        ws.append(["Start Freq (Hz)", r.start_hz])
        ws.append(["Stop Freq (Hz)", r.stop_hz])
        ws.append(["Points", r.points])
        ws.append(["STIM Level (dBm)", r.stim_dbm])
        ws.append(["Avg Count", r.avg_count])
        ws.append(["Num Sweeps", r.num_sweeps])

        # Timing block
        ws.append(["Timing"])
        ws.append(["Sweep #", "Sweep Time (s)", "Sweep Time (ms)", "Update Rate (Hz)"])
        for i, t in enumerate(r.sweep_times_s, 1):
            rate = (1.0 / t) if t > 0 else 0.0
            ws.append([
                i,
                round(t, 4),
                round(t * 1000.0, 4),
                round(rate, 2),
            ])

        # blank row separator
        ws.append([])

        # S11 Traces block
        ws.append(["S11 Traces"])
        ws.append(["Frequency (Hz)"] +
                  [f"Sweep_{i + 1} S11 (dB)" for i in range(r.num_sweeps)])
        for fi, f_hz in enumerate(r.freq_axis_hz):
            row = [f_hz]
            for si in range(r.num_sweeps):
                row.append(round(r.s11_traces_db[si][fi], 4))
            ws.append(row)

        # blank row separator
        ws.append([])

        # Metrics block
        ws.append(["Metrics"])
        ws.append(["Noise Floor (dB)", round(r.noise_floor_db, 4)])
        ws.append(["Trace Jitter (dB)", round(r.trace_jitter_db, 4)])

    wb.save(out_path)


# ----- Console printing ----------------------------------------------------
def _print_ifbw_summary(r: IfbwResult) -> None:
    print(
        f"  IFBW={r.ifbw_hz/1e3:>6.1f} kHz  "
        f"rate={r.rate_hz:>6.2f} Hz  "
        f"mean_t={r.mean_time_ms:>7.2f} ms  "
        f"min/max={r.min_time_s*1000:>6.2f}/{r.max_time_s*1000:>6.2f} ms  "
        f"NF={r.noise_floor_db:>+7.2f} dB  "
        f"jitter={r.trace_jitter_db:>5.3f} dB  "
        f"{'OK' if r.error_queue_clean else 'ERR'}"
    )


def _print_mode_table(mode: str, results: list[IfbwResult]) -> None:
    print()
    print("=" * 90)
    print(f"Summary — mode={mode}")
    print("=" * 90)
    print(f"{'IFBW (kHz)':>12}{'Mean (ms)':>12}{'Rate (Hz)':>12}"
          f"{'Std (ms)':>10}{'Min (ms)':>10}{'Max (ms)':>10}"
          f"{'NF (dB)':>10}{'Jitter (dB)':>12}")
    for r in results:
        print(
            f"{r.ifbw_hz/1e3:>12.1f}"
            f"{r.mean_time_ms:>12.2f}"
            f"{r.rate_hz:>12.2f}"
            f"{r.std_dev_s*1000:>10.2f}"
            f"{r.min_time_s*1000:>10.2f}"
            f"{r.max_time_s*1000:>10.2f}"
            f"{r.noise_floor_db:>10.2f}"
            f"{r.trace_jitter_db:>12.3f}"
        )


# ----- Restore -------------------------------------------------------------
def _restore(ena: ENAConnection) -> None:
    """Best-effort restore so the operator sees a usable display when we exit."""
    try:
        ena.write(":ABOR")
        ena.write(":DISP:ENAB ON")
        ena.write(":STAT:OPER:PTR 32767")
        ena.write(":STAT:OPER:NTR 0")
        ena.write(":TRIG:SOUR INT")
        ena.write(":INIT1:CONT ON")
        ena.write(":FORM:DATA ASC")
        ena.write("*CLS")
    except Exception:
        pass


# ----- Main ----------------------------------------------------------------
def _parse_int_list(arg: str) -> list[int]:
    return [int(x.strip()) for x in arg.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--resource", default=DEFAULT_RESOURCE)
    p.add_argument(
        "--modes",
        default=",".join(DEFAULT_MODES),
        help='Comma-separated list. Subset of {single,continuous}. Default: %(default)s',
    )
    p.add_argument(
        "--ifbw",
        default=",".join(str(v) for v in DEFAULT_IFBW_KHZ),
        help="Comma-separated IFBW values in kHz. Default: %(default)s",
    )
    p.add_argument(
        "--n-sweeps", type=int, default=DEFAULT_N_SWEEPS,
        help="Sweeps per IFBW per mode (default: %(default)s)",
    )
    p.add_argument(
        "--format", choices=sorted(_FORMAT_MAP), default="real32",
        help="Data-transfer format: real32 (REAL32, 4 B), real64 (REAL, 8 B), "
             "or ascii. Default: %(default)s",
    )
    p.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_MS,
        help="VISA timeout in ms (default: %(default)s)",
    )
    p.add_argument(
        "--no-save", action="store_true",
        help="Skip writing xlsx outputs.",
    )
    args = p.parse_args(argv)

    modes = [m.strip().lower() for m in args.modes.split(",") if m.strip()]
    bad = [m for m in modes if m not in ("single", "continuous")]
    if bad:
        print(f"Unknown modes: {bad}. Valid: single, continuous",
              file=sys.stderr)
        return 2

    try:
        ifbw_khz_list = _parse_int_list(args.ifbw)
    except ValueError as exc:
        print(f"Invalid --ifbw value: {exc}", file=sys.stderr)
        return 2

    if not ifbw_khz_list:
        print("--ifbw must contain at least one value", file=sys.stderr)
        return 2

    fmt_token, datatype = _FORMAT_MAP[args.format]

    print("=" * 90)
    print("E5063A Real-World IFBW Benchmark — mirrors REPORT/20260205 (SPEC §6, S-12c)")
    print("=" * 90)
    print(f"Resource:   {args.resource}")
    print(f"Modes:      {modes}")
    print(f"IFBW set:   {ifbw_khz_list} kHz")
    print(f"Sweeps/IFBW:{args.n_sweeps}")
    print(f"Format:     {args.format} (:FORM:DATA {fmt_token})")
    print("Pre-req:    configure_e5063a.py has been run (cal active, 200–250 MHz, 801 pt)")
    print()

    saved_paths: list[Path] = []
    try:
        with ENAConnection(args.resource, timeout=args.timeout) as ena:
            ena.write("*CLS")
            idn = ena.query("*IDN?")
            print(f"IDN: {idn}")

            corr = ena.query(":SENS1:CORR:STAT?").strip().lstrip("+")
            points = int(float(ena.query(":SENS1:SWE:POIN?")))
            start_hz = float(ena.query(":SENS1:FREQ:STAR?"))
            stop_hz = float(ena.query(":SENS1:FREQ:STOP?"))
            stim_dbm = float(ena.query(":SOUR1:POW?"))
            avg_state = ena.query(":SENS1:AVER:STAT?").strip().lstrip("+")
            avg_count = (
                int(float(ena.query(":SENS1:AVER:COUN?")))
                if avg_state in ("1", "ON")
                else 1
            )

            print(
                f"Cal on: {corr}   Points: {points}   "
                f"Range: {start_hz/1e6:.3f}–{stop_hz/1e6:.3f} MHz   "
                f"Power: {stim_dbm:.1f} dBm   Avg: {avg_count}"
            )
            if corr != "1":
                print(
                    "[WARN] Cal correction is NOT active. The benchmark will run "
                    "but S11 values will include uncorrected systematic error. "
                    "Run configure_e5063a.py first.",
                    file=sys.stderr,
                )

            setup_common(ena, start_hz, stop_hz, points, stim_dbm, fmt_token)
            freq_axis = fetch_freq_axis(ena, points, datatype)

            today = datetime.now().strftime("%Y%m%d")
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = DATA_ROOT / today

            try:
                for mode in modes:
                    print()
                    print(f"--- Running mode: {mode} ---")
                    results: list[IfbwResult] = []
                    for ifbw_khz in ifbw_khz_list:
                        ifbw_hz = float(ifbw_khz) * 1e3
                        print(f"  [IFBW={ifbw_khz} kHz] running {args.n_sweeps} sweeps...",
                              end="", flush=True)
                        t_run = time.perf_counter()
                        if mode == "single":
                            r = _bench_single_one_ifbw(
                                ena, ifbw_hz, args.n_sweeps,
                                points, start_hz, stop_hz, stim_dbm,
                                avg_count, freq_axis, datatype,
                            )
                        else:
                            r = _bench_continuous_one_ifbw(
                                ena, ifbw_hz, args.n_sweeps,
                                points, start_hz, stop_hz, stim_dbm,
                                avg_count, freq_axis, datatype,
                            )
                        elapsed = time.perf_counter() - t_run
                        print(f" done in {elapsed:.1f}s")
                        _print_ifbw_summary(r)
                        results.append(r)

                    _print_mode_table(mode, results)

                    if not args.no_save:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"{mode}_sweep_test_e5063a_{args.format}_{stamp}.xlsx"
                        out_path = out_dir / fname
                        write_mode_xlsx(results, out_path, mode)
                        saved_paths.append(out_path)
                        print(f"  Saved: {out_path}")
            finally:
                _restore(ena)

    except ENAConnectionError as exc:
        print(f"[FAIL] VISA connection: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print()
    print("=" * 90)
    print(f"DONE. Saved {len(saved_paths)} workbook(s).")
    for p in saved_paths:
        print(f"  {p}")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
