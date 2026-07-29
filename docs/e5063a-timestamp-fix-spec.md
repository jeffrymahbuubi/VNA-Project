# E5063A Data Collector — Timestamp Integrity Fix SPEC

**Status:** IMPLEMENTED (F-1…F-5) + headless-validated 2026-07-24 — pending live-instrument
pass + multi-hour re-validation (§6), then release **v1.1.0**
**Date:** 2026-07-24 (spec + implementation same day)
**State of the world:** fix committed+pushed (`4203d78`); **v1.1.0-dev `.exe` rebuilt,
validated (title shows v1.1.0-dev) and zipped** (`E5063A-Data-Collector-v1.1.0-dev-win64.zip`,
135 MB) — this is the build to take to the instrument for §6. Versioning/release process:
`docs/versioning-and-releases.md` (§6.1 = exact v1.1.0 release commands); v1.0.0 retro-tag +
GitHub Release published 2026-07-24.

> **Implementation notes (2026-07-24):**
> - `verify_timestamp_fix.py` ALL CHECKS PASSED: writer unit test (5000 rows,
>   mid-run file growth, header patched in place at fixed byte width, 0.000%
>   duplicate timestamps, 177 distinct dt values) + offscreen STUB end-to-end
>   (598 rows @ 200 Hz stub cadence, 497 distinct dt, 0 duplicates, drift audit
>   +0.4 ms/3 s). The produced CSV loads unchanged in `8_plot_monitor_data.py`
>   (mean gap 5.0 ms, max 7.0 ms — continuum, not tick-quantized).
> - Filename semantic change: the CSV filename timestamp is now the **Start**
>   time (file is created at Start for streaming), matching the header's
>   `Start DateTime`; previously it was the Stop/write time.
> - `_on_monitor_point` drops any preview sweep stamped before Start
>   (`rec_elapsed < 0`) — previously an in-flight queued point could land in
>   the record buffer with a negative-ish elapsed.
> - `closeEvent` finalizes an active writer before controller teardown, so a
>   window-close mid-recording yields a complete, patched CSV.
**Owner:** ena-dev track (`code/ena-dev/gui/`)
**Problem source:** `references/reports/20260715/時間序不穩定分析報告.pdf` (+ English write-up
`Timestamp_Instability_Analysis_Report_EN.md`), validated against code 2026-07-21.
**Related docs:** `docs/e5063a-gui-spec.md`, `docs/e5063a-gui-ux-spec.md`, `docs/e5063a-packaging.md`.

---

## 1. Problem statement (validated)

Long Monitor-mode recordings (18 h on 2026-06-25, 24 h on 2026-07-02; 801 pt / 300 kHz,
~56.8 rows/s) show **unstable timestamps**. The measured S11 values are **not** affected
(report §6: gap size vs |Δfreq|/|ΔdB| uncorrelated, p > 0.05) — only *when rows are stamped*
is unreliable. Three scales:

1. **ms-scale quantization:** inter-row dt takes only the values {15, 16, 31, 32} ms
   (63–78 distinct dt values in 3.7–4.9 M rows).
2. **Duplicate timestamps:** 16.4 % (18 h) / 25.9 % (24 h) of rows share a timestamp with a
   neighbour — two *real* sweeps stamped inside one clock tick.
3. **Hour-scale growing gaps:** >100 ms "pause" gaps grow monotonically with elapsed time
   within each file (Spearman ρ = 0.956 / 0.857); max gap 1.3–1.7 s; cumulative skew
   39 ms (18 h) vs 668 ms (24 h).

### Root causes (confirmed in code + empirically on the project venv)

| # | Cause | Evidence |
|---|-------|----------|
| R-1 | Record timestamps derive from `time.monotonic()`, which on this venv (CPython 3.11.9 / Windows) is **`GetTickCount64()` with 15.625 ms resolution** | `time.get_clock_info('monotonic')` → `implementation='GetTickCount64()', resolution=0.015625` (re-confirmed 2026-07-24). Sweep interval ~17.6 ms ≈ one tick → explains ALL of (1) and (2). |
| R-2 | **Unbounded in-RAM buffer**: `_mon_records` accumulates every `MonitorRecord` for the whole run (3.7–4.9 M objects over 18–24 h); the CSV is written **only at Stop** (`_write_monitor_csv`) | `main_window.py:90,483,565`. Growing allocator/GC pressure is the leading hypothesis for (3) — plausible, **not proven**; the re-validation run doubles as the test. |
| R-3 | Timestamp is stamped in the **GUI-thread slot**, not at sweep completion: `controller._preview_tick` emits a queued cross-thread signal, and `main_window._on_monitor_point` *re-stamps* `rec_elapsed = time.monotonic() - self._t0` on arrival | `controller.py:170`, `main_window.py:482-484`. Signal-queue + GUI-event-loop latency (whatever the GUI is doing: repaints, resize) is folded into the data timestamp. |

Stamping is 100 % host-side (the report's "PC-side, not instrument" conclusion holds).

### Non-problems (established — do not re-derive)

- The CSV header `Log Interval(ms)` is **derived post-run** (`1000·span/(N−1)` of achieved
  rows, `main_window.py` `_write_monitor_csv`), not a target setting.
- 18 h vs 24 h differences are a **day/PC-environment effect**, not run-duration.
- Duplicates do **not** grow with elapsed time; they are a rate-vs-clock-tick collision
  effect (worst at high IFBW where sweep interval ≈ tick).
- Timing jitter here (ms, OS clock) is unrelated to IFBW trace jitter (dB, RF noise).

---

## 2. Timing requirement (what "good enough" means)

The downstream analysis is a **time-series analysis of min-S11-frequency(t)**: PSD/FFT for
physiological modulation (cardiac ~1–1.5 Hz, respiration ~0.2–0.3 Hz), gap/dropout detection,
rate stability. For a sample interval of **17–25 ms** (40–57 Hz):

- **T-1** Timestamp resolution must be ≪ sample interval. Target: **≤ 1 µs** (10⁴× margin);
  the current 15.625 ms tick is ~90 % of a sample interval — useless for jitter analysis.
- **T-2** Timestamps must be **strictly monotonically increasing** within a run
  (no duplicates), immune to NTP/DST/system-clock adjustments.
- **T-3** The stamp must be taken **at the moment the sweep data becomes available**
  (instrument read returns), not after cross-thread delivery (kills R-3).
- **T-4** RAM use must be **bounded (O(1))** w.r.t. run duration; a 24 h run on a modest
  consumer PC must not degrade (kills R-2) and must not lose the whole dataset on a crash
  at hour 23.
- **T-5** Absolute (wall-clock) time only needs ~1 s accuracy for run identification;
  *relative* inter-sample timing carries the analysis. (QPC is not UTC-synchronized —
  acceptable, see D-2.)

---

## 3. Timing-function survey (official documentation)

Sources: CPython 3.11 `time` docs via Context7 (`/python/cpython/v3.11.14`), Qt 6 docs via
Context7 (`/websites/doc_qt_io_qt-6`), Microsoft "Acquiring high-resolution time stamps",
PEP 418, CPython gh-88494/bpo-44328. Resolutions below **measured on the project venv**
(`code/.venv`, CPython 3.11.9, Windows 11) via `time.get_clock_info()` on 2026-07-24.

### 3.1 Python `time` / `datetime` clocks

| Function | Windows implementation (this venv) | Resolution | Monotonic | Adjustable | Verdict for record timestamps |
|---|---|---|---|---|---|
| `time.monotonic()` *(current code)* | `GetTickCount64()` | **15.625 ms** | yes | no | ❌ Root cause R-1. (Python ≥3.13 switches this to QPC — but we fix in code, not by interpreter upgrade.) |
| `time.perf_counter()` / `perf_counter_ns()` | `QueryPerformanceCounter()` (QPC) | **100 ns** | yes | no | ✅ **CHOSEN.** Docs: "clock with the highest available resolution"; "include[s] time elapsed during sleep"; "system-wide" (valid across threads). `_ns` variant returns int nanoseconds — no float representation concerns. |
| `time.time()` | `GetSystemTimeAsFileTime()` | 15.625 ms | **no** | **yes** (NTP/admin/DST) | ❌ Same coarse tick AND can step backwards mid-run. |
| `datetime.datetime.now()` | same wall clock as `time.time()` | ~15.6 ms | no | yes | ⚠ Only as the **once-per-run wall anchor** (D-2), never per-row. |
| `time.process_time()` / `thread_time()` | CPU time | — | — | — | ❌ Excludes sleep/blocking — meaningless for wall-time stamping. |

### 3.2 Qt / PySide6 facilities

| Facility | What it is | Verdict |
|---|---|---|
| `QElapsedTimer` | Elapsed-time measurement; since Qt 6.6 always `std::chrono::steady_clock` (on Windows backed by QPC) | ✅ Equivalent to `perf_counter` in quality, but adds a Qt dependency to the stamping path for no gain over `time.perf_counter_ns()`. Not chosen. |
| `QDateTime.currentDateTime()` | Wall clock | ❌ Same objections as `datetime.now()` per-row. |
| `QTimer` with `Qt.PreciseTimer` | *Scheduling* accuracy (~1 ms target, "never times out earlier") | ⚠ Orthogonal: timers decide *when code runs*; they don't improve *how a moment is stamped*. Our tick is paced by the blocking instrument read anyway. Deferred hardening only (D-5). |

### 3.3 Windows native APIs (via ctypes — for reference / future need)

| API | Note |
|---|---|
| `QueryPerformanceCounter` | Microsoft's primary recommendation "when you need time stamps with a resolution of 1 microsecond or better and you don't need the time stamps to be synchronized to an external time reference". Invariant-TSC based: unaffected by Turbo Boost/power management; reliable on multi-core; no thread-affinity needed. Already exposed as `perf_counter` — no ctypes required. |
| `GetSystemTimePreciseAsFileTime` | UTC-synchronized µs wall clock (Win8+). Only needed if we ever require precise *absolute* time per-row; T-5 says we don't. Python ≥3.13's `time.time()` uses it. |
| `timeBeginPeriod(1)` | Raises the *system timer interrupt* rate; affects `Sleep`/coarse timers, **not** GetTickCount64 and not needed for QPC stamping. Deferred (D-5). |

### 3.4 Known QPC caveats (assessed — none blocking)

- **Not UTC-synchronized; may drift vs wall clock** (ppm-scale over 24 h). Mitigated by D-2
  (anchor at Start *and* Stop lets us measure the actual drift per run).
- **Historic pre-Windows-XP-SP2 multi-core bugs / VM HPET bugs** (PEP 418): Microsoft's
  current guidance declares QPC reliable on XP+; CPython itself adopted QPC for
  `time.monotonic` in 3.13 on this basis.
- **Suspend/resume semantics** differ across Windows versions. A laptop sleeping mid-run is
  already a broken recording for this application; out of scope.

---

## 4. Design decisions

### D-1 — Per-row clock: `time.perf_counter_ns()`, stamped at acquisition

- Replace every timestamp-bearing `time.monotonic()` with `time.perf_counter_ns()`
  (integer ns; divide once at CSV-write time).
- **Stamp location moves to the controller thread** (`controller._preview_tick`), taken
  immediately after `read_trace_continuous()` returns — the closest host-observable moment
  to sweep completion. The stamp rides *inside* the signal payload
  (`sigMonitorPoint(stamp_ns, minf, mag)`); the GUI slot never re-stamps (fixes R-3).
  QPC is system-wide, so a controller-thread stamp compared against a Start-anchor taken on
  any thread is valid.
- Rate badges / elapsed displays / stop conditions may use the same clock (one clock
  everywhere; no mixed-clock arithmetic).

### D-2 — Absolute-time anchoring (unchanged concept, better bookkeeping)

- At **Start**: capture `anchor_wall = datetime.now()` and `anchor_ns = perf_counter_ns()`.
  Row timestamp = `anchor_wall + (stamp_ns − anchor_ns)`.
- At **Stop**: also capture `(datetime.now(), perf_counter_ns())` and log the wall-vs-QPC
  residual into the CSV header/footer notes — a free per-run drift audit (validates the
  ppm-drift assumption; T-5).

### D-3 — Incremental (streaming) CSV writer — bounded RAM

**Clarification of intent (this is the opposite of buffering):** the *current, broken*
design holds everything in RAM and writes once at Stop. "Incremental CSV" means the file is
**opened at Start and rows are appended to disk during acquisition**, so RAM stays constant
for 24 h+ runs and data up to the last flush survives a crash.

Producer/consumer split so disk latency can never perturb timestamps:

```
controller thread (producer, hot path):        writer (consumer, cold path):
  read_trace_continuous() returns                pop batch from queue
  stamp_ns = perf_counter_ns()   ← only this      format rows → file.write()
  queue.put((stamp_ns, f0, mag))                  flush every N rows or T seconds
  emit signal for GUI plot
```

- **Queue:** `queue.SimpleQueue` (unbounded but drained continuously; depth is a health
  metric — log a warning if it exceeds ~10× batch size).
- **Writer placement:** a plain `threading.Thread` (daemon) owned by the recording session;
  file I/O never touches the GUI or controller threads. (A QThread works too; plain thread
  keeps it Qt-free and testable headless.)
- **Flush policy:** batch-write every **64 rows or 2 s**, whichever first (~1–2 s worst-case
  data loss on crash; negligible I/O rate ~3 KB/s).
- **Header patching:** the Dataflux header needs `Number of Data` and the derived
  `Log Interval(ms)`, known only at Stop. Write the header at Start with fixed-width
  placeholders (space-padded), then at Stop `seek(0)` and overwrite in place — the file
  stays **byte-compatible with `8_plot_monitor_data.py`** (same line lengths, same format).
  Crash-recovery consequence: an un-patched header still parses if the loader tolerates the
  placeholder; verify during implementation, else document the recovery step.
- **Stop path:** signal writer to drain queue → final flush → patch header → close → then
  report "Saved". `_mon_records` (full-run list) is **deleted**; the GUI keeps only its
  existing bounded plot buffers (600-point trim, `main_window.py:487`) and running
  aggregates (count, min/max) for badges.

### D-4 — What is explicitly NOT changed

- Sweep acquisition path (`monitor_begin`/`read_trace_continuous`/latched `:STAT:OPER`
  polling) — proven at ~39 Hz; untouched.
- CSV column format & value formatting — Dataflux byte-compatibility is a hard constraint.
- Sanity-check (xlsx) path — short runs; not exposed to R-1/R-2 at hour scale. (It may
  adopt D-1's clock for consistency, but it is not in the validated problem's scope.)

### D-5 — Deferred options (record, don't build)

- `Qt.PreciseTimer` on poll timers + `timeBeginPeriod(1)`: unnecessary once D-1/D-3 land —
  pacing is dominated by the blocking instrument read, and stamping no longer depends on
  the system timer interrupt.
- Python 3.13 upgrade (native `monotonic`→QPC, `time.time`→precise): correct long-term but
  a venv+packaging migration; D-1 achieves the same result now with a code-level change.
- Parabolic min-freq interpolation: separate accuracy question, tracked in
  `docs/e5063a-20260604-sweep-rate-analysis.md`; unrelated to timestamps.

---

## 5. Fix plan (implementation order)

| # | Change | Files (current anchors) |
|---|--------|------------------------|
| F-1 | Clock swap + stamp-at-acquisition: `perf_counter_ns` stamp in `_preview_tick` right after the trace read; signal signature carries the stamp; GUI slot stops re-stamping | `controller.py:139,170` (and sanity uses at 196–257 for consistency); `main_window.py:399,420,471,482-484` |
| F-2 | Streaming writer: `mvp/dataflux.py` gains an incremental `DatafluxWriter` (open-at-start / append / patch-header-at-stop); recording session owns writer thread + queue | `dataflux.py`; `main_window.py` `_start_recording`/`_stop_recording`/`_on_monitor_point`/`_write_monitor_csv:565` |
| F-3 | Drop `_mon_records` full-run buffer; keep bounded plot buffers + running aggregates | `main_window.py:90,283,418,436,483,489,551` |
| F-4 | Start/Stop wall-anchor bookkeeping + drift note in header comments | `main_window.py:400,419` + `dataflux.py` header writer |
| F-5 | Headless unit check (stub backend): dt continuum, zero duplicates, file grows during run, header patched correctly, loads in `8_plot_monitor_data.py` | new `verify_timestamp_fix.py` beside `verify_backend_g2.py` |

Both copies of the world must get the fix: the repo GUI **and** the packaged `.exe`
(rebuild per `docs/e5063a-packaging.md`).

## 6. Re-validation plan (recompute the report's own metrics)

Multi-hour Monitor run (≥ 4 h; ideally repeat the 18–24 h class), then recompute on the new CSV:

| Metric (report) | Broken value | Acceptance |
|---|---|---|
| Distinct dt values / dt histogram | {15,16,31,32} ms only | Continuum around mean sweep time (hundreds of distinct values) |
| Duplicate-timestamp ratio | 16.4–25.9 % | **≈ 0 %** (µs resolution at ~17 ms spacing) |
| Gap(>100 ms) count vs elapsed-time Spearman ρ | 0.86–0.96, p≪0.05 | No significant positive trend (tests the R-2 hypothesis) |
| Cumulative skew vs wall clock | 39–668 ms | Reported per-run via D-2 anchor audit; expected ppm-scale |
| GUI rate badge / CSV effective interval | ~56.8 Hz (that band) | Unchanged (fix must not cost acquisition rate) |
| RAM (Task Manager, whole run) | grows ~MB/h | Flat after warm-up |

If hour-scale gaps persist with flat RAM → R-2 hypothesis falsified; escalate to profiling
(GC stats, `tracemalloc`, Windows scheduling) before further design.

## 7. References

- Python 3.11 `time` docs — `perf_counter`/`perf_counter_ns`/`monotonic`/`get_clock_info` (Context7 `/python/cpython/v3.11.14`)
- Measured venv clock info (2026-07-24): `monotonic` = `GetTickCount64()` @ 0.015625 s; `perf_counter` = `QueryPerformanceCounter()` @ 1e-7 s; `time` = `GetSystemTimeAsFileTime()` @ 0.015625 s, adjustable
- Microsoft, *Acquiring high-resolution time stamps* — https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps
- Microsoft, *QueryPerformanceCounter* — https://learn.microsoft.com/en-us/windows/win32/api/profileapi/nf-profileapi-queryperformancecounter
- PEP 418 (clock survey; GetTickCount64 ≈ 16 ms; QPC-vs-tick drift discussion) — https://peps.python.org/pep-0418
- CPython bpo-44328 / gh-88494 — `time.monotonic()` should use QPC on Windows (landed in 3.13) — https://bugs.python.org/issue44328
- Qt 6 docs — `QElapsedTimer` (steady_clock since 6.6), `QTimer` accuracy & `Qt::PreciseTimer` (Context7 `/websites/doc_qt_io_qt-6`)
- Problem report: `references/reports/20260715/` (PDF + EN markdown)

## 8. FAQ (questions raised during review)

**Q: The docs say `perf_counter` is "a clock with the highest available resolution to
measure a short duration" — is that why it's recommended? What about a 24 h run?**
Resolution is half the reason; the full rationale is in §3.1/§3.4: on *this* interpreter
`monotonic` is a 15.625 ms tick counter while `perf_counter` is QPC at 100 ns, and both are
equally monotonic/non-adjustable. "Short duration" describes the *typical use* (benchmarks),
not a validity limit — QPC is a fixed-frequency 64-bit counter that Microsoft explicitly
endorses for interval timestamping without external sync; its only long-run cost is
ppm-scale drift vs UTC, which T-5 tolerates and D-2 audits. CPython itself made this exact
swap the default in 3.13.

**Q: Doesn't "incremental CSV" mean buffering in RAM and saving at the end?**
No — that is the *current broken* design (R-2). Incremental means the opposite: append to
disk continuously during acquisition (D-3), so RAM is O(1) and a crash loses ≤ one flush
interval, not the whole run.
