"""bench_e5063a_rates.py — Phase 3 sweep-rate benchmark for the E5063A.

Implements the five benchmark variants from
``references/reports/20260528/e5063a-speed-potential-and-ifbw-tradeoff.md`` §3.5
at the migration's locked operating point (200–250 MHz, 801 pts, port-1 S11,
display off, host-paced single sweeps unless noted).

| Variant | IFBW    | Format | Trigger        | Expected (Hz)            |
|---------|---------|--------|----------------|--------------------------|
| A       | 300 kHz | ASCII  | BUS + *OPC?    | ~10–15  (ASCII baseline) |
| B       | 300 kHz | REAL32 | BUS + *OPC?    | ~30     (headline)       |
| C       |  30 kHz | REAL32 | BUS + *OPC?    | ~19–20  (DataFlux level) |
| D       |   1 kHz | REAL32 | BUS + *OPC?    | ~1.3    (deep-DR floor)  |
| E       | 300 kHz | REAL32 | INT continuous | up to ~32 (paced reads)  |

Method for each variant:
  - Discard first sweep as cold-cache.
  - Time N=200 sweeps wall-clock (perf_counter_ns).
  - Report mean / median / p95 / p99 inter-sweep delta + sweep rate Hz.
  - Confirm :SYST:ERR? is clean afterwards.

The script ASSUMES the cal recalled by configure_e5063a.py is active; the
instrument should already be at the locked operating point with the cal on.
It will save current IFBW + trigger config and restore them on exit.

Outputs:
  - JSON summary at code/ena-dev/data/YYYYMMDD/bench_e5063a_<timestamp>.json
  - Per-sweep CSV at code/ena-dev/data/YYYYMMDD/bench_e5063a_<timestamp>.csv

Run from code/:
    uv run python ena-dev/scripts/configure_e5063a.py      # one-time setup
    uv run python ena-dev/scripts/bench_e5063a_rates.py    # then this
    uv run python ena-dev/scripts/bench_e5063a_rates.py --variants A,B,C
    uv run python ena-dev/scripts/bench_e5063a_rates.py --n-sweeps 500
    uv run python ena-dev/scripts/bench_e5063a_rates.py --no-save
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# Bootstrap
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ena_dev_paths  # noqa: F401, E402

from core.visa_connection import ENAConnection, ENAConnectionError  # noqa: E402


DEFAULT_RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"
DEFAULT_N_SWEEPS = 200
DEFAULT_TIMEOUT_MS = 30_000
DATA_ROOT = Path(__file__).resolve().parents[1] / "data"


@dataclass
class VariantConfig:
    id: str
    ifbw_hz: float
    fmt: str                 # "ASC" or "REAL32"
    trigger_mode: str        # "bus" or "continuous"
    expected_rate_hz_low: float
    expected_rate_hz_high: float
    purpose: str


# Trigger mode "single" = TRIG:SOUR INT + INIT:CONT OFF (each :INIT:IMM
# arms-and-triggers; *OPC? blocks until sweep done — the cleanest host-paced
# pattern on the E5063A).
#
# Trigger mode "continuous" = TRIG:SOUR INT + INIT:CONT ON (free-running on
# the instrument; host polls the sweep-complete event via :STAT:OPER:COND?).
VARIANTS: dict[str, VariantConfig] = {
    "A": VariantConfig("A", 300e3,  "ASC",    "single",     12.0, 28.0,
                       "ASCII baseline — confirms binary helps"),
    "B": VariantConfig("B", 300e3,  "REAL32", "single",     25.0, 38.0,
                       "Binary 300 kHz — headline number"),
    "C": VariantConfig("C", 30e3,   "REAL32", "single",     15.0, 22.0,
                       "Binary 30 kHz — replicates legacy DataFlux 20 Hz"),
    "D": VariantConfig("D", 1e3,    "REAL32", "single",     1.0,  1.6,
                       "Binary 1 kHz — deep-DR floor"),
    # Variant E is EXCLUDED from the default suite. The polling pattern
    # (:STAT:OPER:COND? each iteration) is itself slower than the sweep
    # period at 300 kHz IFBW, so it under-measures. Proper continuous-mode
    # benchmarking requires SRQ/EOP-based sync (deferred — see SPEC §6.5).
    "E": VariantConfig("E", 300e3,  "REAL32", "continuous", 25.0, 42.0,
                       "Continuous + polling (experimental, see SPEC §6.5)"),
}

# Default variant set — exclude E because its polling overhead dominates.
DEFAULT_VARIANTS = "A,B,C,D"


@dataclass
class VariantResult:
    id: str
    ifbw_hz: float
    fmt: str
    trigger_mode: str
    expected_low_hz: float
    expected_high_hz: float
    purpose: str
    n_sweeps: int
    n_used: int                      # after cold-cache discard
    total_seconds: float
    mean_dt_s: float
    median_dt_s: float
    p95_dt_s: float
    p99_dt_s: float
    stddev_dt_s: float
    sweep_rate_hz: float
    in_expected_range: bool
    p99_over_mean_ratio: float
    error_queue_clean: bool
    error_message: str
    per_sweep_dt_s: list[float] = field(default_factory=list)


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear interpolation percentile. q in [0, 1]."""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _setup_for_variant(ena: ENAConnection, v: VariantConfig) -> None:
    """Put the instrument in the right state for the variant. Cal stays on."""
    # Abort any in-progress sweep and reset status registers.
    ena.write(":ABOR")
    ena.write("*CLS")
    ena.write(":DISP:ENAB OFF")              # display off → +10–20% speed

    if v.trigger_mode == "single":
        # BUS trigger source + INIT:CONT OFF + INIT:IMM (arms wait-for-trigger),
        # then :TRIG:SING per sweep to fire. *OPC? then blocks until done.
        ena.write(":TRIG:SOUR BUS")
        ena.write(":INIT1:CONT OFF")
    elif v.trigger_mode == "continuous":
        ena.write(":TRIG:SOUR INT")
        ena.write(":INIT1:CONT ON")
    ena.opc_wait()

    # Change IFBW and let it settle. IFBW changes don't invalidate cal
    # (see SPEC §4A.6) but the instrument briefly re-tunes.
    ena.write(f":SENS1:BAND:RES {v.ifbw_hz:.6E}")
    ena.opc_wait()

    if v.fmt == "REAL32":
        ena.write(":FORM:DATA REAL32")
        ena.write(":FORM:BORD SWAP")
    else:
        ena.write(":FORM:DATA ASC")
    ena.opc_wait()

    # Drain any residual errors so per-variant error_check() is meaningful.
    while True:
        code, _msg = ena.error_check()
        if code == 0:
            break


def _restore(ena: ENAConnection) -> None:
    """Best-effort restore so the operator sees a usable display when we exit."""
    try:
        ena.write(":DISP:ENAB ON")
        ena.write(":TRIG:SOUR INT")
        ena.write(":INIT1:CONT ON")
        ena.write(":FORM:DATA ASC")
        ena.write("*CLS")
    except Exception:
        pass


def _read_one_sweep(ena: ENAConnection, fmt: str) -> None:
    """Issue one sweep + read the trace. Caller is responsible for timing."""
    if fmt == "REAL32":
        # Use raw pyvisa for the binary read because ENAConnection.query_binary
        # uses datatype="B" which gives bytes; we just need to consume the
        # block and discard contents for benchmarking.
        ena._session.query_binary_values(  # type: ignore[attr-defined]
            ":CALC1:DATA:FDAT?", datatype="f", is_big_endian=False
        )
    else:
        ena.query_values(":CALC1:DATA:FDAT?")


def _bench_variant_single(
    ena: ENAConnection, v: VariantConfig, n_sweeps: int
) -> VariantResult:
    """Variants A/B/C/D — host-paced single sweeps.

    With TRIG:SOUR BUS + INIT:CONT OFF:
      - :INIT1:IMM arms the trigger system (transitions to wait-for-trigger).
      - :TRIG:SING sends the software trigger (fires the sweep).
      - *OPC? blocks until the sweep is complete.

    Without an explicit :TRIG:SING the sweep never fires under BUS source —
    that was the bug in the first attempt.
    """
    timestamps_ns: list[int] = []

    # Arm once. INIT:CONT OFF means after sweep completes we go back to IDLE,
    # so each iteration needs to re-arm with :INIT1:IMM before :TRIG:SING.
    # Cold sweep + read (not timed):
    ena.write(":INIT1:IMM")
    ena.write(":TRIG:SING")
    ena.opc_wait()
    _read_one_sweep(ena, v.fmt)

    start_ns = time.perf_counter_ns()
    for _ in range(n_sweeps):
        ena.write(":INIT1:IMM")
        ena.write(":TRIG:SING")
        ena.opc_wait()
        _read_one_sweep(ena, v.fmt)
        timestamps_ns.append(time.perf_counter_ns())

    return _summarize(v, n_sweeps, start_ns, timestamps_ns, ena)


# Bit 4 of the Keysight ENA Operation Status Condition register is "Measuring"
# (1 during sweep, 0 when idle). Falling edge = sweep just completed.
# We watch for a falling edge of this bit to sync each host read with a fresh
# sweep in continuous mode.
_OPER_MEASURING_BIT = 0x0010


def _wait_for_sweep_complete(ena: ENAConnection, prev_state: int, poll_us: int = 200) -> int:
    """Poll :STAT:OPER:COND? until the MEASURING bit transitions from 1→0
    (sweep just completed). Returns the latest condition value seen.
    Adds a small busy-wait that's tight enough to not lose sweeps."""
    deadline = time.perf_counter_ns() + int(2e9)        # 2 s safety timeout
    state = prev_state
    while True:
        new = int(ena.query(":STAT:OPER:COND?"))
        # Falling edge of bit 4
        if (state & _OPER_MEASURING_BIT) and not (new & _OPER_MEASURING_BIT):
            return new
        state = new
        if time.perf_counter_ns() > deadline:
            return new
        if poll_us:
            time.sleep(poll_us / 1e6)


def _bench_variant_continuous(
    ena: ENAConnection, v: VariantConfig, n_sweeps: int
) -> VariantResult:
    """Variant E — instrument free-runs; host syncs each read to a new sweep
    via the operation-status MEASURING bit."""
    timestamps_ns: list[int] = []

    # Prime: read once so the trace buffer has data, then wait for one full
    # sweep cycle so our edge detection starts on a known transition.
    time.sleep(0.1)
    _read_one_sweep(ena, v.fmt)
    state = int(ena.query(":STAT:OPER:COND?"))
    # Wait until measuring (rising edge), so the next call lands on falling.
    deadline = time.perf_counter_ns() + int(2e9)
    while not (state & _OPER_MEASURING_BIT):
        state = int(ena.query(":STAT:OPER:COND?"))
        if time.perf_counter_ns() > deadline:
            break
        time.sleep(0.0002)

    start_ns = time.perf_counter_ns()
    for _ in range(n_sweeps):
        state = _wait_for_sweep_complete(ena, state)
        _read_one_sweep(ena, v.fmt)
        timestamps_ns.append(time.perf_counter_ns())
        # After the read, the next sweep is already in progress under continuous
        # mode, so re-prime by ensuring measuring bit is set before the next
        # iteration's edge-wait.
        deadline = time.perf_counter_ns() + int(2e9)
        while not (state & _OPER_MEASURING_BIT):
            state = int(ena.query(":STAT:OPER:COND?"))
            if time.perf_counter_ns() > deadline:
                break

    return _summarize(v, n_sweeps, start_ns, timestamps_ns, ena)


def _summarize(
    v: VariantConfig,
    n_sweeps: int,
    start_ns: int,
    timestamps_ns: list[int],
    ena: ENAConnection,
) -> VariantResult:
    end_ns = timestamps_ns[-1]
    total_seconds = (end_ns - start_ns) / 1e9

    # Inter-sweep deltas (seconds). First delta = first read - start.
    prev = start_ns
    deltas_s: list[float] = []
    for t in timestamps_ns:
        deltas_s.append((t - prev) / 1e9)
        prev = t

    sorted_deltas = sorted(deltas_s)
    mean_dt = statistics.fmean(deltas_s)
    median_dt = statistics.median(deltas_s)
    stddev_dt = statistics.pstdev(deltas_s) if len(deltas_s) > 1 else 0.0
    p95 = _percentile(sorted_deltas, 0.95)
    p99 = _percentile(sorted_deltas, 0.99)
    rate_hz = len(deltas_s) / total_seconds if total_seconds > 0 else float("nan")

    code, msg = ena.error_check()
    err_clean = code == 0
    in_range = v.expected_rate_hz_low <= rate_hz <= v.expected_rate_hz_high
    p99_ratio = p99 / mean_dt if mean_dt > 0 else float("nan")

    return VariantResult(
        id=v.id,
        ifbw_hz=v.ifbw_hz,
        fmt=v.fmt,
        trigger_mode=v.trigger_mode,
        expected_low_hz=v.expected_rate_hz_low,
        expected_high_hz=v.expected_rate_hz_high,
        purpose=v.purpose,
        n_sweeps=n_sweeps,
        n_used=len(deltas_s),
        total_seconds=total_seconds,
        mean_dt_s=mean_dt,
        median_dt_s=median_dt,
        p95_dt_s=p95,
        p99_dt_s=p99,
        stddev_dt_s=stddev_dt,
        sweep_rate_hz=rate_hz,
        in_expected_range=in_range,
        p99_over_mean_ratio=p99_ratio,
        error_queue_clean=err_clean,
        error_message=msg,
        per_sweep_dt_s=deltas_s,
    )


def _print_variant_summary(r: VariantResult) -> None:
    print(f"\n--- Variant {r.id}: {r.purpose} ---")
    print(f"  IFBW: {r.ifbw_hz:>9.0f} Hz   Format: {r.fmt:<6}   Trigger: {r.trigger_mode}")
    print(f"  Sweeps: {r.n_used} (timed) over {r.total_seconds:.3f} s")
    print(f"  Rate:   {r.sweep_rate_hz:>6.2f} Hz   (expected {r.expected_low_hz:.1f}–{r.expected_high_hz:.1f} Hz)  "
          f"{'✅' if r.in_expected_range else '⚠ outside expected'}")
    print(f"  ΔT mean   = {r.mean_dt_s*1000:6.2f} ms")
    print(f"  ΔT median = {r.median_dt_s*1000:6.2f} ms")
    print(f"  ΔT p95    = {r.p95_dt_s*1000:6.2f} ms")
    print(f"  ΔT p99    = {r.p99_dt_s*1000:6.2f} ms   (p99/mean = {r.p99_over_mean_ratio:.2f})")
    print(f"  ΔT stddev = {r.stddev_dt_s*1000:6.2f} ms")
    print(f"  Error queue: {'clean' if r.error_queue_clean else 'DIRTY — ' + r.error_message}")


def _save_results(
    results: list[VariantResult], out_dir: Path, label: str
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"bench_e5063a_{label}.json"
    csv_path = out_dir / f"bench_e5063a_{label}.csv"

    json_payload = {
        "label": label,
        "saved_at": datetime.now().isoformat(),
        "summary": [
            {k: v for k, v in asdict(r).items() if k != "per_sweep_dt_s"}
            for r in results
        ],
    }
    json_path.write_text(json.dumps(json_payload, indent=2))

    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "sweep_idx", "delta_t_s"])
        for r in results:
            for i, dt in enumerate(r.per_sweep_dt_s):
                w.writerow([r.id, i, f"{dt:.9f}"])
    return json_path, csv_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--resource", default=DEFAULT_RESOURCE)
    p.add_argument(
        "--variants",
        default=DEFAULT_VARIANTS,
        help="Comma-separated subset of {A,B,C,D,E}. "
             "Default: %(default)s (E excluded — see SPEC §6.5).",
    )
    p.add_argument("--n-sweeps", type=int, default=DEFAULT_N_SWEEPS,
                   help="Sweeps per variant (default: %(default)s)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MS)
    p.add_argument("--no-save", action="store_true",
                   help="Skip writing JSON/CSV outputs.")
    args = p.parse_args(argv)

    requested = [v.strip().upper() for v in args.variants.split(",") if v.strip()]
    unknown = [v for v in requested if v not in VARIANTS]
    if unknown:
        print(f"Unknown variants: {unknown}. Valid: {sorted(VARIANTS)}", file=sys.stderr)
        return 2

    print("=" * 72)
    print("E5063A Sweep-Rate Benchmark — Phase 3 (SPEC §6)")
    print("=" * 72)
    print(f"Resource:  {args.resource}")
    print(f"Variants:  {requested}")
    print(f"Sweeps:    {args.n_sweeps} per variant")
    print("Pre-req:   configure_e5063a.py has been run (cal active, 200–250 MHz, 801 pt)")
    print()

    results: list[VariantResult] = []
    try:
        with ENAConnection(args.resource, timeout=args.timeout) as ena:
            # Confirm we're at the locked operating point
            ena.write("*CLS")
            idn = ena.query("*IDN?")
            print(f"IDN: {idn}")
            corr = ena.query(":SENS1:CORR:STAT?").strip()
            points = ena.query(":SENS1:SWE:POIN?").strip().lstrip("+")
            start_hz = float(ena.query(":SENS1:FREQ:STAR?"))
            stop_hz = float(ena.query(":SENS1:FREQ:STOP?"))
            print(f"Cal on:  {corr}   Points: {points}   "
                  f"Range: {start_hz/1e6:.1f}–{stop_hz/1e6:.1f} MHz")
            if corr != "1":
                print("[WARN] Cal correction NOT active — results will include "
                      "uncorrected systematic error but rate measurements are "
                      "still valid for benchmarking purposes.")

            try:
                for vid in requested:
                    v = VARIANTS[vid]
                    print(f"\n[Running variant {vid}: {v.purpose}...]")
                    _setup_for_variant(ena, v)
                    if v.trigger_mode == "single":
                        r = _bench_variant_single(ena, v, args.n_sweeps)
                    elif v.trigger_mode == "continuous":
                        r = _bench_variant_continuous(ena, v, args.n_sweeps)
                    else:
                        raise ValueError(f"Unknown trigger_mode: {v.trigger_mode}")
                    results.append(r)
                    _print_variant_summary(r)
            finally:
                _restore(ena)
    except ENAConnectionError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    # Summary table
    print()
    print("=" * 72)
    print("Summary")
    print("=" * 72)
    print(f"{'Variant':<8}{'IFBW':>10}{'Fmt':>8}{'Rate (Hz)':>12}{'p99/mean':>11}{'In range':>11}")
    for r in results:
        in_range = "✅" if r.in_expected_range else "⚠"
        print(f"{r.id:<8}{r.ifbw_hz:>10.0f}{r.fmt:>8}"
              f"{r.sweep_rate_hz:>12.2f}{r.p99_over_mean_ratio:>11.2f}{in_range:>11}")

    # Persist
    if not args.no_save and results:
        today = datetime.now().strftime("%Y%m%d")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = DATA_ROOT / today
        json_path, csv_path = _save_results(results, out_dir, stamp)
        print()
        print(f"Saved JSON: {json_path}")
        print(f"Saved CSV:  {csv_path}")

    # Exit code reflects whether all results landed in the expected range
    all_pass = all(r.in_expected_range and r.error_queue_clean for r in results)
    print()
    print("=" * 72)
    print(f"Overall: {'PASS' if all_pass else 'PARTIAL — some variants outside expected range or error queue dirty'}")
    print("=" * 72)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
