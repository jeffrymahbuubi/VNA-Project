# Changelog — E5063A Data Collector

All notable changes to the E5063A Data Collector (`code/ena-dev/gui/`) are
documented here. Format follows [Keep a Changelog](https://keepachangelog.com);
versioning follows [SemVer](https://semver.org) as interpreted in
`docs/versioning-and-releases.md` (MAJOR = data-contract break, MINOR =
functional change to recorded data, PATCH = cosmetic).

## [Unreleased] — v1.1.0 draft (timestamp-integrity fix)

Pending live-instrument pass + multi-hour re-validation
(`docs/e5063a-timestamp-fix-spec.md` §6) + `.exe` rebuild before tagging.

### Changed
- **Monitor timestamps are now QPC-true (~100 ns resolution).** Rows are stamped
  with `time.perf_counter_ns()` on the acquisition thread the instant the sweep
  read returns — replacing `time.monotonic()` (GetTickCount64, 15.625 ms tick on
  Python 3.11/Windows) re-stamped in the GUI thread. Kills the dt quantization
  {15,16,31,32} ms and the 16–26 % duplicate timestamps found in the 20260715
  report; measured 0.000 % duplicates in verification.
- **Monitor CSV streams to disk during acquisition** (`DatafluxWriter`): file
  opens at Start, rows append in ≤2 s batches, header patched in place at Stop.
  RAM stays constant for 24 h+ runs (was: unbounded in-RAM buffer, CSV written
  only at Stop); a crash now loses at most ~2 s of data instead of the whole run.
  File layout is byte-compatible with `8_plot_monitor_data.py` (verified).
- **CSV filename timestamp = recording Start time** (was: Stop/write time),
  matching the header's `Start DateTime`.
- Sanity-benchmark sweep timing also uses `perf_counter` (was tick-quantized).

### Added
- Per-run **wall-clock vs QPC drift audit** in the save status and stdout log.
- `verify_timestamp_fix.py` — headless verification (writer unit test +
  offscreen STUB end-to-end recomputing the 20260715 report's metrics).
- Window title now shows the version (`mvp/version.py`, single source).

### Known issues
- Hour-scale gap growth (20260715 report finding 3) is attributed to the removed
  RAM buffering — hypothesis to be confirmed by the multi-hour re-validation run.

## [1.0.0] — 2026-06-04 (retro-tagged `f1b0cf3`)

First field version, distributed as a standalone `.exe`
(auto-py-to-exe/PyInstaller One-Directory, `docs/e5063a-packaging.md`).

### Added
- Two-screen PySide6 GUI (Setup → Acquire, + Files/History): connect/configure,
  host-driven 1-port S11 ECal (N7550A) or `.sta` recall, verify sweep,
  Continuous Monitor (min-S11 Dataflux CSV, ~39 Hz) and Device Sanity Check
  (per-IFBW benchmark xlsx). Phases G-0…G-15 + G-6.
- Live S11 trace preview free-running from Proceed (G-13), monitor Y-axis
  toggle (G-12), WTMH lab branding (G-14), cal file-listing fix (G-15).

### Known issues
- **Timestamp instability in long recordings** (20260715 report): dt quantized
  to the 15.625 ms Windows tick, 16–26 % duplicate timestamps, hour-scale
  growing gaps. Measured S11 values unaffected. Fixed in v1.1.0.
