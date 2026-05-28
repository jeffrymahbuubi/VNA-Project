# LibreVNA Custom Data Collector — Project Overview

This document captures the structure and purpose of the LibreVNA Vector Network Analyzer
project so that future tasks have ready context. It is the canonical narrative companion
to `CLAUDE.md`.

## 1. Project Purpose

A Python-based automation and custom GUI suite for the **LibreVNA** (open-source Vector
Network Analyzer). It originated from the "LibreVNA Validation Test Assignment" and
evolved into:

- A series of progressively complex SCPI automation scripts (`0` → `8`) that benchmark
  and characterize VNA performance.
- A **PySide6 real-time data collector GUI** (`script 7`) built on the MVP pattern that
  wraps the validated `script 6` backend behind a user-friendly interface.

Sweep-rate engineering is the central technical theme: the codebase moves from
~3.5 Hz (single-sweep polling) up to ~17 Hz (continuous + streaming) and documents a
path to ~33 Hz via direct USB.

### Biomedical Objective

The deeper application goal is a **portable, low-cost replacement for the Keysight E5063A
VNA** for non-invasive physiological monitoring. A resonant RF sensor placed near biological
tissue or a pulsatile flow phantom exhibits a resonant-frequency shift (min S11) of
±0.15–0.25 MHz around ~233.5 MHz as the nearby material deforms. The time-varying pattern
of that shift encodes breathing rate (~0.2–0.4 Hz) and heartbeat (~1–2 Hz). The LibreVNA
(`~$150`, USB-powered) targets field or bedside deployment as an alternative to the
lab-grade Keysight instrument. The **Monitor Mode** feature (script 7 / `VNAMonitorWorker`)
implements the Keysight "Dataflux" equivalent — logging one scalar `(timestamp, min_freq_Hz,
min_dB)` per sweep into a compatible CSV that `8_plot_monitor_data.py` can analyse directly.

## 2. Top-level Layout

```
6-LibreVNA-Vector-Network-Analyzer/
├── code/                          ← actual application code
│   ├── LibreVNA-dev/              ← project working tree (scripts + GUI + data)
│   ├── LibreVNA-source/           ← upstream LibreVNA C++/FPGA source (read-only reference)
│   └── pyproject.toml, requirements.txt, uv.lock, .venv/
├── docs/                          ← project docs (this file lives here)
├── references/                    ← spec PDFs, RF fundamentals, prior validation reports
├── scripts/                       ← repo helper scripts (bash launchers, MCP/skill scanners)
├── .claude/, .claude-flow/, .mcp.json   ← Claude Code agent + MCP configuration
└── CLAUDE.md                      ← project memory / instructions for Claude
```

## 3. `code/LibreVNA-dev/` — The Application

| Subfolder       | Contents                                                                    | Purpose                                                       |
| --------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `scripts/`      | `0_*.py` … `6_*.py`, `libreVNA.py`, `sweep_config.yaml`                     | CLI automation/benchmarking scripts                           |
| `gui/`          | `7_realtime_vna_plotter_mvp.py`, `mvp/`, `design/`, `resources/`, YAML/cal  | The **custom data collector GUI**                             |
| `calibration/`  | `SOLT_*.cal` (JSON)                                                         | SOLT calibration files                                        |
| `data/YYYYMMDD/`| `.xlsx` workbooks                                                           | Timestamped sweep outputs                                     |
| `notebook/`     | `1_*.ipynb`, `2_*.ipynb`, `3_*.ipynb`                                       | Post-run analysis (Jupyter)                                   |
| `markdown/YYYYMMDD/` | Analysis docs, bug reports, refactor summaries                         | Engineering changelog                                         |
| `tools/`        | `LibreVNA-GUI` binary                                                       | Headless-launchable Qt GUI exposing SCPI on port 1234         |

### CLI scripts (build on each other)

| Script | Role |
|--------|------|
| `0_librevna_cleanup.py` | Diagnose/kill stuck LibreVNA-GUI processes & free ports (1234, 19000–19002) |
| `1_librevna_cal_check.py` | Verify cal file + `*IDN?` |
| `2_s11_cal_verification_sweep.py` | Single S11 sweep → CSV; exports `connect_and_verify` and `load_calibration` helpers |
| `3_sweep_speed_baseline.py` | 30-sweep single-sweep benchmark; auto-launches GUI |
| `4_ifbw_parameter_sweep.py` | IFBW impact on speed/jitter |
| `5_continuous_sweep_speed.py` | Enables streaming server; registers callback on port 19001 |
| `6_librevna_gui_mode_sweep_test.py` | **Unified single/continuous benchmark**, YAML-driven, multi-sheet xlsx export. `BaseVNASweep` → `SingleModeSweep` / `ContinuousModeSweep`. This is the backend the GUI wraps. |
| `8_plot_monitor_data.py` | Visualize Dataflux-compatible CSV produced by Monitor Mode — scrolling time-series of min-freq, peak detection, BPM estimate. |
| `libreVNA.py` | Thin SCPI/socket wrapper with `add_live_callback` for streaming. Known harmless bug at line 148. |

## 4. The Custom GUI — `code/LibreVNA-dev/gui/`

A PySide6 application that visualizes S11 in real time, orchestrates a multi-IFBW
collection run, and auto-exports to Excel.

### Entry point
`gui/7_realtime_vna_plotter_mvp.py` — wires Model/View/Presenter and starts the Qt
event loop. `cwd` is forced to `gui/` so relative `.cal` / `.yaml` lookups work.

### MVP package — `gui/mvp/`

| File | Layer | Responsibility |
|------|-------|----------------|
| `model.py` | Model (pure Python, no Qt) | Dataclasses `DeviceInfo`, `CalibrationState`, `SweepConfig`, `SweepData`, `MonitorConfig`, `MonitorRecord`. `VNADataModel` holds device/cal/config/monitor state, validates config, computes statistics, converts S11 complex → dB. `SweepConfig.update_from_cal_file()` enforces the invariant that the cal file is the single source of truth for freq range and point count. |
| `view.py` | View (PySide6) | `VNAMainWindow(QMainWindow, Ui_MainWindow)`. Two `pyqtgraph.PlotWidget`s — S11 trace (always visible) and scrolling min-freq time-series (`monitor_plot_widget`, hidden by default). Orange `monitor_button`. Blink animation timer. All display-only; no business logic. |
| `presenter.py` | Presenter | Mediates Model ↔ View. Five `QThread` workers: `DeviceProbeWorker` (startup detection), `PortCleanupWorker` (kill stale port-holders), `VNAPreviewWorker` (oscilloscope-style live preview, no save), `VNASweepWorker` (full multi-IFBW collection + xlsx export), `VNAMonitorWorker` (indefinite min-freq logging → Dataflux CSV). All cross-thread updates via Qt signals. |
| `backend_wrapper.py` | Adapter | `GUIVNASweepAdapter` decomposes script 6's `run()` into `start_lifecycle()` / `run_single_ifbw_sweep()` / `save_results()` / `stop_lifecycle()`. `GUIVNAMonitorAdapter` for monitor mode. `probe_device_serial()` for startup. Port cleanup utilities (`find_port_owners`, `kill_port_users`). |
| `vna_backend.py` | Standalone backend | Extracted `BaseVNASweep` and `ContinuousModeSweep` from script 6, with paths made configurable. Also defines `MonitorRecord`, `export_dataflux_csv()`. |
| `main_window.py` | Auto-generated | Compiled from `design/main_window.ui` via `pyside6-uic`. Provides `Ui_MainWindow`. |
| `libreVNA.py` | SCPI wrapper | Functional copy of `scripts/libreVNA.py` for GUI use. |
| `resources_rc.py` | Auto-generated | Compiled Qt resource bundle (logos, icons, placeholder image). |
| `SOLT_*.cal` | Cal files | Auto-detected by GUI on startup. |

### Supporting subdirs
- `gui/design/main_window.ui` — Qt Designer source (recompile to `mvp/main_window.py`).
- `gui/resources/` — `WTMH.png/.ico`, `placeholder-s11.png`, `resources.qrc`.
- `gui/sweep_config.yaml` — Defaults (`stim_lvl_dbm: -10`, `avg_count: 1`, `num_sweeps: 30`, single IFBW `50000`). Frequency range comes from `.cal`, not YAML.

### Threading contract
- Main thread: all Qt widgets, plot updates, slot handlers.
- `QThread` workers: GUI subprocess lifecycle, SCPI traffic, streaming-callback receiver
  (TCP thread on port 19001).
- Streaming callback emits a Qt signal → slot on GUI thread → `plot.setData()`. All GUI
  updates must go through signals/slots.

### User flow
1. Launch → auto-detects `.cal` + `.yaml` in `gui/`, populates widgets, button turns
   GREEN when device + cal + valid config are ready.
2. User edits config (IFBW list, sweeps, stimulus level).
3. "Collect Data" → button turns RED + blinks; status bar shows
   `IFBW X kHz – Sweep N/M`; pyqtgraph plot updates per sweep.
4. On completion → `data/YYYYMMDD/gui_sweep_collection_YYYYMMDD_HHMMSS.xlsx` written
   (Summary sheet + per-IFBW detail sheets).
5. **Monitor Mode** → click orange "Monitor" button; GUI switches to scrolling time-series
   plot (`monitor_plot_widget`); each sweep logs `(timestamp, min_freq_Hz, min_dB)`. Click
   "Stop Monitor" → `data/YYYYMMDD/vna_monitor_YYYYMMDD_HHMMSS.csv` written in
   Dataflux-compatible format (12 metadata lines + column header + data rows).

## 5. Calibration — Active vs Test

Two SOLT calibration files exist:

| File | Range / Points | Status |
|------|----------------|--------|
| `SOLT_1_200M-250M_801pt.cal` | 200–250 MHz, 801 points | **Active** — used for real measurements |
| `SOLT_1_2_43G-2_45G_300pt.cal` | 2.43–2.45 GHz, 300 points | **Test only** — exists to verify that the GUI can load and switch between different cal files correctly |

Both copies live in `code/LibreVNA-dev/calibration/` and `code/LibreVNA-dev/gui/`.

## 6. Engineering Notes

- **Python via `uv`** (`code/.venv`, `code/requirements.txt`). Always run with
  `uv run python …`.
- **SCPI gotchas (from `CLAUDE.md`)**:
  - Use `ACQ:RUN` to retrigger single sweeps (re-sending `FREQ:STOP` doesn't work).
  - Script 5 leaves the GUI in continuous mode → subsequent single-sweep scripts must
    start with `ACQ:STOP` + `ACQ:SINGLE TRUE`.
  - Streaming servers default-off; enable via
    `:DEV:PREF StreamingServers.VNACalibratedData.enabled true` then
    `:DEV:APPLYPREFERENCES` (which restarts the GUI).
  - `DEV:PREF` set commands return CME in ESR even on success — pass `check=False`.
  - `VNA:CAL:LOAD?` is a query despite no question mark in some docs. Use `vna.query()`.
- **Calibration is the source of truth** for sweep boundaries. Both script 6 and the
  GUI read frequency range and point count from the `.cal` JSON, not from YAML.
- **Streaming ports**: 19000 (raw), 19001 (calibrated, used by GUI), 19002 (de-embedded).
- **Sweep rate reference**: single-sweep poll ≈ 3.5–5 Hz; hot re-trigger ≈ 24 Hz;
  continuous + streaming ≈ 17 Hz; USB direct (theoretical, not implemented) ≈ 33 Hz.
- **Specialized agents** (`.claude/agents/`): `librevna-python-expert`,
  `rf-data-analyst`, `pyqt6-gui-developer`, plus a top-level `librevna-orchestrator`
  for routing.
- **Monitor Mode** (added 2026-02-25): `VNAMonitorWorker` runs indefinite streaming sweeps
  and extracts `min_freq_Hz` per sweep via `np.argmin(s11_db)`. Output is a Dataflux-compatible
  CSV readable by `8_plot_monitor_data.py`. IFBW ≥ 50 kHz required for heartbeat capture
  (Nyquist limit). For BPM: bandpass-filter the min-freq time-series (0.8–2.5 Hz window)
  then apply `scipy.signal.find_peaks` — do not use raw peak count.
- **Planned — F-01 Log Interval Mode** (`markdown/20260225/planned_feature.md`): Auto/Manual
  warm-up algorithm to estimate sweep speed before Monitor recording begins. Touch points:
  `model.py` (add `estimate_log_interval()`), `presenter.py` (warm-up phase in
  `VNAMonitorWorker`), `view.py` (radio buttons + read-only estimated-sweep-time label),
  `sweep_config.yaml` (new `log_interval_mode` field). Status: Draft/Planned.
- **Windows exe packaging**: `auto-py-to-exe` config exists at
  `markdown/20260226/auto-py-to-exe-config.json`. Output directory: `gui/output/`.
- **Documented next step**: USB direct protocol implementation (specs already
  summarized in `code/LibreVNA-dev/markdown/20260205/part2-continuous-sweep-implementation.md` §7.11)
  to bypass the GUI/SCPI layer for ~33 Hz sustained sweep rates.
