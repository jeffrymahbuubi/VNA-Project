# E5063A GUI Implementation SPEC — port the LibreVNA MVP, swap the backend

**Status:** ✅ Built & live-validated, G-0…G-5 (2026-06-02) + **G-7** (UI polish +
instrument-hygiene, implemented & live-validated 2026-06-04 — §6.1; crisp SVG arrows
shipped). + **G-8** (visual refresh —
two-column config grid, slate palette, semibold labels, combo open-caret; implemented &
qt-mcp-validated 2026-06-04). + **G-9** (UI micro-polish:
Points↔IFBW spacing, rounded spin corners, card padding, Browse-host removed, save-dir picker
wired — implemented & qt-mcp-validated 2026-06-04). + **G-10** (container dead-zone fix:
transparent layout containers so cards read uniform — implemented & qt-mcp-validated
2026-06-04) + **G-11** (IFBW width align + spin click-feedback — implemented & qt-mcp-validated
2026-06-04). + **G-12** (monitor Y-axis toggle — implemented & qt-mcp-validated 2026-06-04,
§6/§9.9). + **G-13** (live S11 trace preview on Acquire + display modes — **implemented &
qt-mcp-validated 2026-06-04, stub + live `MY54806798`**; §6/§9.10). + **G-14** (WTMH lab
branding — window/taskbar icon + header emblem on all screens — **implemented &
qt-mcp-validated 2026-06-04, stub**; §6/§9.11). ✅ **G-15** (calibration file-listing bug —
new ECal cal not found — **fixed + live-validated 2026-06-04**; §6.2). + **G-6** (`.exe`
packaging — **built + validated 2026-06-04, One-Directory PyInstaller/auto-py-to-exe**;
[`docs/e5063a-packaging.md`](./e5063a-packaging.md)). **All GUI phases complete.**
Lives in `code/ena-dev/gui/`; full phase status in §6.
**Owner:** Aunuun + Claude
**Parent spec:** [`docs/e5063a-migration-spec.md`](./e5063a-migration-spec.md) — this
document is the detailed plan for that spec's **Phase 2 / §5 (DataFlux / Monitor
Mode Replacement)**. The migration spec remains the *validated foundation*
(hardware, SCPI, sweep-rate, cal, data format); this is the *build* doc.

> ## Cold-start orientation (read first if you just ran `/clear`)
> - **What we're building:** a Windows PySide6 desktop app that drives the **Keysight
>   E5063A ENA** to (a) live-preview S11 and (b) run **Monitor mode** — logging the
>   per-sweep **minimum-S11 frequency** (Hz + magnitude dB) over time for the research
>   institute's **blood-vessel prototype**. This replaces the legacy DataFlux web app
>   and the LibreVNA "Data Collector" GUI.
> - **Why E5063A:** monitor rate is floored by mean sweep time; E5063A lifts the
>   ceiling from LibreVNA's ~7 Hz to **~26–39 Hz** at 200–250 MHz/801 pt
>   (~3.7–5.8×). See migration-spec §5.1.1 and memory `project-monitor-loginterval-e5063a`.
> - **The approach (this whole doc):** do **not** write a GUI from scratch. **Port the
>   proven LibreVNA MVP** (`code/LibreVNA-dev/gui/mvp/`) into `code/ena-dev/gui/`,
>   keep Model/View/Presenter, and **replace only the backend** (SCPI/transport)
>   with the E5063A `pyvisa`/`ENAConnection` path.
> - **Instrument:** E5063A SN `MY54806798`, FW A.07.06,
>   `USB0::0x2A8D::0x5D01::MY54806798::0::INSTR`. Cal = 1-port S11 ECal (N7550A),
>   either **run host-driven** via `calibrate_e5063a.py` (no front panel, S-18) or
>   **recall a saved `.sta`** via `configure_e5063a.py` — not a host-parsed JSON.
>   Locked point: 200–250 MHz / 801 pt / S11 / −5 dBm, REAL32 + SWAP. Re-cal only on
>   a grid change (start/stop/points); IFBW changes freely (migration-spec §4A.6).
> - **Backend already exists to adapt:** `code/ena-dev/scripts/bench_e5063a_realworld.py`
>   (single + continuous sweep, latched poll, S11 read) and
>   `code/ena_qt6_suite/core/visa_connection.py` (`ENAConnection`).
> - **Verify loop:** qt-mcp (memory `project-qt-mcp-setup`, `docs/qt-mcp-gui-automation.md`).

---

## 1. Goal & scope

### 1.1 In scope

The GUI is a **one-stop tool** with these capabilities (collaborator feedback
2026-06-02 — real-world experiments change start/stop/points/IFBW often, and a
frequency-grid change needs a fresh ECal; all of that must happen in-app):

- A PySide6 MVP app under `code/ena-dev/gui/` that connects to the E5063A over USB-TMC.
- **Configure**: set start/stop/points/IFBW/power/S11 from the host and read back.
  Backend proven — `code/ena-dev/scripts/configure_e5063a.py` (migration-spec S-11a/b).
- **Calibrate**: host-driven 1-port (S11) **ECal** via the Keysight N7550A, no
  front-panel step. Backend proven & validated live 2026-06-02 —
  `code/ena-dev/scripts/calibrate_e5063a.py` (migration-spec **S-18**). Saves a
  grid-named `.sta` the Configure path can recall. **Re-cal only on a frequency-grid
  change (start/stop/points); IFBW changes freely — migration-spec §4A.6.**
- **Device Sanity Check**: the per-IFBW sweep benchmark `bench_e5063a_realworld.py`
  already does, surfaced in the GUI.
- **Monitor mode**: continuous min-S11-frequency logging → Dataflux-compatible CSV
  loadable by `code/LibreVNA-dev/scripts/8_plot_monitor_data.py` without conversion.
- **Live preview** of the current S11 trace while idle/armed — realized by **G-13**: on the
  Acquire (Monitor) page the full S11 trace (magnitude dB vs frequency) free-runs from the
  moment the user Proceeds and continues through recording, mimicking the instrument screen so
  the signal can be verified before/while collecting. The min-S11 scalar scroller (G-11/G-12)
  is kept as a selectable display mode. See §6 G-13 and ux-spec §1.1/§3.2.
- Feature parity with the LibreVNA "Data Collector" GUI (the F-/NF- requirements in
  migration-spec §5.2/§5.3).
- **WTMH lab branding (G-14)**: the WTMH (NCKU) logo as the window/taskbar icon, a small
  header emblem on every screen, and the `.ico` source for the packaged `.exe` icon (G-6).
  See §6 G-14 and design-system §9.11.

> Both new host-driven backends (Configure, Calibrate) are **validated CLI scripts
> today**; the GUI wraps them behind the §3 adapter contract (add
> `GUIVNAConfigureAdapter` / `GUIVNACalibrateAdapter` alongside the sweep/monitor
> adapters) — no new SCPI research needed.

### 1.2 Out of scope (for now)
- Multi-parameter (S21/S12/S22) acquisition — S11 only, matching the objective.
- Packaging to a standalone `.exe` (PyInstaller) — track as a later phase once the app runs.
- **2-port** calibration — only 1-port S11 ECal is in scope (matches the objective).
  (Note: in-app *1-port ECal authoring* is now **in scope** — see §1.1 Calibrate —
  superseding the earlier "cal is recalled only" assumption, now that host-driven
  ECal is validated, S-18.)

---

## 2. Source structure → target (port-vs-replace map)

Source: `code/LibreVNA-dev/gui/mvp/`  →  Target: `code/ena-dev/gui/mvp/`

| Source file | Disposition | Notes |
|---|---|---|
| `model.py` (`DeviceInfo`, `CalibrationState`, `SweepConfig`, `MonitorConfig`, `MonitorRecord`, `SweepData`, `VNADataModel`) | **PORT ~as-is** | Pure logic, GUI-free. **One change:** `SweepConfig.update_from_cal_file()` parses LibreVNA `.cal` JSON — for E5063A, source freq/points from the instrument (`:SENS:FREQ:STAR/STOP?`, `:SWE:POIN?`) or a small config, since E5063A cal is a `.sta` state file, not host-parsed JSON. `convert_s11_complex_to_db` stays. |
| `view.py` (`VNAMainWindow`, `_VNAPlotWidget`, axis items, `AxisSetupDialog`, monitor plot) | **PORT structure, RESTYLE via design system** | Display-only, instrument-agnostic. pyqtgraph already validated in `code/.venv` (qt-mcp work). **Per [`e5063a-gui-design-system.md`](./e5063a-gui-design-system.md) (D-1): build the view in code from `theme.py` factories — drop inline QSS; `setObjectName(...)` on every interactive widget (styling + qt-mcp).** |
| `main_window.py` (`Ui_MainWindow`) | **DROP (code-built views)** | Design-system decision D-1: retire the compiled `design/main_window.ui` / `Ui_MainWindow`; lay out in code from `theme.py` factories. |
| `presenter.py` (`VNAPresenter` + `DeviceProbeWorker`, `PortCleanupWorker`, `VNAPreviewWorker`, `VNASweepWorker`, `VNAMonitorWorker`) | **PORT structure, repoint backend** | Keep the QThread worker pattern and state machine. Workers call the **adapter contract** (§3); if the adapter keeps its method signatures, presenter changes are minimal. **DROP `PortCleanupWorker`** (LibreVNA-GUI TCP-1234 port cleanup — irrelevant to direct pyvisa). Remove "wait for TCP 1234 / start GUI subprocess" lifecycle assumptions. |
| `backend_wrapper.py` (`GUIVNASweepAdapter`, `GUIVNAMonitorAdapter` + `find_port_owners`/`kill_port_users`/`_start_gui_subprocess`/`_is_scpi_server_running`/`probe_device_serial`) | **REPLACE** | All the LibreVNA-GUI subprocess + TCP-port (1234 / 19001) machinery is gone. E5063A is **direct pyvisa** — no subprocess, no port polling, no streaming server. Keep the **adapter class names + method signatures** (`start_lifecycle`, `run_single_ifbw_sweep`/`run_warmup`/`start_recording`/`stop_recording`, `stop_lifecycle`, `probe_device_serial`) so the presenter contract is preserved; reimplement bodies over `ENAConnection`. |
| `vna_backend.py` (`BaseVNASweep`, `ContinuousModeSweep`, `export_dataflux_csv`, `SweepResult`, `MonitorRecord`) | **REPLACE** | Reimplement using the proven E5063A logic in `ena-dev/scripts/bench_e5063a_realworld.py`: `setup_common`, `setup_mode_single`/`setup_mode_continuous`, `read_s11_trace_db`, `_wait_sweep_complete_latched`. **Keep `export_dataflux_csv` byte-format identical.** Add **min-freq extraction** (argmin of S11 dB → freq, mag) per sweep for Monitor mode. |
| `libreVNA.py` (TCP SCPI wrapper) | **DROP** | Replaced by `core.visa_connection.ENAConnection` (import via `ena_dev_paths` shim) + `pyvisa`. |
| `sweep_config.yaml`, `*.cal` | **REPLACE** | New YAML for E5063A defaults (IFBW, stim, log_interval_ms, duration_s, warmup). Cal = instrument-side `.sta` recall (see `configure_e5063a.py`); no host `.cal` needed. |

**Net:** Model/View/Presenter port over; the backend (`backend_wrapper.py` +
`vna_backend.py` + `libreVNA.py`) is the replaced layer. This is exactly the seam the
MVP was designed around.

---

## 3. Backend adapter contract (the seam)

Preserve these so the presenter/workers are reused with minimal change. Bodies wrap
`ENAConnection` (no subprocess, no TCP ports):

```
class GUIVNASweepAdapter:          # Device Sanity Check
    __init__(config_dict, <no cal_file needed; recall .sta>)
    start_lifecycle() -> {serial, fw, ...}   # open pyvisa, recall cal, pin op-point
    run_single_ifbw_sweep(ifbw_hz, n_sweeps, on_trace) -> SweepResult
    save_results(...) -> path                # xlsx, reuse bench schema
    stop_lifecycle()                         # restore display, close session
    probe_device_serial() -> {serial, fw}    # *IDN? (no GUI subprocess)

class GUIVNAMonitorAdapter:        # Monitor mode (the objective)
    __init__(config_dict)
    start_lifecycle() -> {...}
    run_warmup(warmup_sweeps) -> mean_sweep_s   # also reports the log-interval floor
    start_recording(log_interval_ms, duration_s, on_point)   # emits (t, min_freq_hz, mag_db)
    stop_recording(output_dir) -> csv_path      # export_dataflux_csv
    stop_lifecycle()

class GUIVNAConfigureAdapter:      # Configure capability (wraps configure_e5063a.py)
    __init__(resource)
    apply_config(start_hz, stop_hz, points, ifbw_hz, power_dbm) -> {accepted readback}
    recall_cal(sta_path) -> {active: bool, cal_type, grid}   # :MMEM:LOAD:STAT + verify
    list_cal_files() -> [sta_path, ...]         # instrument-side .sta enumeration

class GUIVNACalibrateAdapter:      # Calibrate capability (wraps calibrate_e5063a.py)
    __init__(resource)
    detect_ecal(port) -> path_str               # :CORR:COLL:ECAL:PATH?  (0 = none)
    run_ecal(start_hz, stop_hz, points, ifbw_hz, power_dbm, port, on_progress)
        -> {active, cal_type, conf_min_mean_max, sta_path}   # :ECAL:SOLT1 + save .sta
```

> The Configure/Calibrate adapters wrap the **validated CLI backends**
> (`configure_e5063a.py` S-11a/b, `calibrate_e5063a.py` S-18) on a QThread — the
> per-control wiring is specified in `docs/e5063a-gui-ux-spec.md` §6.

**Min-freq extraction (Monitor core):** per completed sweep, read the S11 MLOG trace
(`:CALC:DATA:FDAT?`, 2×N, take every other), `idx = argmin(s11_db)`,
`min_freq = freq_axis[idx]`, `mag = s11_db[idx]`. Pace at `log_interval_ms`
(clamped ≥ mean sweep time — surface a warning if the user sets it lower, per the
physical floor in migration-spec §5.1.1).

> **G-12 (monitor Y-axis toggle):** because every monitor point already carries **both**
> `min_freq` and `mag`, letting the user plot the scroller's Y-axis as either min-S11
> frequency (MHz, default) or magnitude (dB, the notch depth) is a **pure View/presenter
> change** — `monitor_read` and the `(t, min_freq_hz, mag_db)` emit are unchanged, and the
> Dataflux CSV (which always writes both columns) is unaffected. See §6 status G-12 and
> ux-spec §3.2/§6.

> **G-13 (live S11 trace preview + Acquire display modes):** the continuous read already
> produces the **whole** trace each sweep (`read_trace_continuous` → `(freqs, s11)`; the
> monitor path argmins it and keeps only the min). So a **live trace preview** = plot that
> full `(freqs, s11)` each sweep — no new backend SCPI. The work is **controller + presenter**:
> split the monitor path so `monitor_begin()` runs on **Proceed** (free-run preview, no
> logging) and `monitor_end()`/`restore_live()` on **Back/close** (not on Stop); add a
> `sigLiveTrace(freqs, s11)` signal + `doStartPreview`/`doStopPreview` slots + a **recording
> flag** that `Start Record` flips on and `Stop` flips off (the preview keeps running). The
> Acquire `monitorPlot` becomes dual-mode (`displaySelector`: Live trace ⇄ Monitor minimum),
> default **Live trace + magnitude**. Monitor mode only (Sanity already plots traces). See §6
> status G-13 and ux-spec §1.1/§3.2/§6.

**Trigger choice for Monitor:** continuous mode (`:INIT:CONT ON` + latched
`:STAT:OPER:EVEN?` bit-4 poll) gives the highest sustained rate (~+15% over single)
and is the natural free-run analog. Single mode is the simpler fallback. Both are
already implemented in `bench_e5063a_realworld.py`.

---

## 4. Key differences vs the LibreVNA GUI (gotchas to design around)

| Concern | LibreVNA GUI | E5063A GUI |
|---|---|---|
| Transport | TCP to LibreVNA-GUI.exe (port 1234) + streaming 19001 | Direct USB-TMC via pyvisa (`ENAConnection`) |
| Process model | Spawn/poll/kill the GUI subprocess | None — open a VISA session |
| Calibration | Host parses `.cal` JSON, loads via `VNA:CAL:LOAD?` | Recall instrument `.sta` state (`configure_e5063a.py`); correction already on |
| Sweep trigger | `ACQ:RUN` + `ACQ:FIN?` / streaming callback | `BUS`+`INIT:IMM`/`TRIG:SING`/`*OPC?` (single) or latched `:STAT:OPER:EVEN?` (continuous) |
| Data read | `TRACE:DATA?` / JSON stream | `:CALC:DATA:FDAT?` REAL32 binary, 2×N for MLOG |
| Threading | SCPI on QThread, signals to GUI | **Same** — keep NF-4 (all VISA on a QThread; GUI 60 fps) |
| ESR/error check | `*ESR?` quirks (CME on DEV:PREF) | `:SYST:ERR?` queue; `ENAConnection.error_check()` |

---

## 5. Phased plan

| Phase | Deliverable | Verify |
|---|---|---|
| G-0 | Copy `mvp/` skeleton into `ena-dev/gui/`, strip LibreVNA-GUI subprocess code, app launches with a stub backend (no instrument) | qt-mcp: window + widgets present, `setObjectName` coverage |
| G-1 | `vna_backend.py` (E5063A) — single + continuous sweep + min-freq extraction, adapted from `bench_e5063a_realworld.py`; unit-run headless against the live instrument | trace read matches bench xlsx; clean error queue |
| G-2 | `backend_wrapper.py` adapters over `ENAConnection`, preserving the §3 contract | probe returns SN/FW; single sweep round-trips |
| G-3 | Presenter wired to E5063A adapters; **live S11 preview** updates from a QThread | qt-mcp: click Collect → plot updates; 60 fps held |
| G-4 | **Monitor mode**: record min-freq over duration, scrolling plot, Dataflux CSV export | CSV loads in `8_plot_monitor_data.py`; rate ≈ 1/mean-sweep |
| G-5 | Feature parity polish (F-1…F-10, NF-1…NF-5): file prefix, interval/duration inputs, history list, progress bar | checklist vs migration-spec §5.2/§5.3 |
| G-6 (later) | Package to standalone `.exe` | launch on a clean Windows path |

## 6. Status table (this spec's source of truth)

| ID | Item | Phase | Status | Updated |
|----|------|-------|--------|---------|
| UX | **Two-screen UX spec** (`docs/e5063a-gui-ux-spec.md`) — Setup→Acquire, widget inventories, state machine, filename rule, wiring | pre-G | ✅ Specified | 2026-06-02 |
| G-0 | MVP skeleton in `ena-dev/gui/mvp/` (theme.py, model.py, view_setup.py, view_acquire.py, stub_backend.py, main_window.py) + entry `e5063a_data_collector.py`; two-screen QStackedWidget launches with stub backend. **qt-mcp verified: window 1080×800, 0 Qt warnings, 126 objectNames, gating + nav + both plots (scene_snapshot) + monitor live-feed + filename compose on Stop all working.** | G-0 | ✅ Validated | 2026-06-02 |
| B-Cfg | **Configure backend** (host sets start/stop/points/IFBW/power/S11 + readback) — `configure_e5063a.py` | pre-G | ✅ Validated (CLI) | 2026-06-02 |
| B-Cal | **Calibrate backend** (host-driven 1-port S11 ECal via N7550A, grid-named `.sta` save+recall) — `calibrate_e5063a.py` | pre-G | ✅ Validated (CLI) | 2026-06-02 |
| G-1 | E5063A backend (sweep + min-freq) — `mvp/backend_e5063a.py` `E5063ABackend` (probe/apply_config/list_cal_files/recall_cal/detect_ecal/run_ecal/read_single_trace/monitor_min_freq), reuses proven SCPI. **Headless live-verified 7/7 vs E5063A+N7550A** (`verify_backend_g2.py`). | G-1/G-2 | ✅ Validated | 2026-06-02 |
| G-2c | Configure + Calibrate folded into `E5063ABackend` (host config + recall + live 1-port ECal) — drives `configure_e5063a`/`calibrate_e5063a` SCPI directly | G-2 | ✅ Validated | 2026-06-02 |
| G-2 | `mvp/controller.py` `BackendController` (QObject on a dedicated QThread, NF-4) — request/result signals, one VISA session on the controller thread; backend selectable stub vs real by resource | G-2 | ✅ Validated | 2026-06-02 |
| G-3 | Presenter (`main_window.py`) rewired to the threaded controller; **live S11 preview + live monitor**. **qt-mcp live-verified vs E5063A: real IDN, recall SOLT1, Verify sweep (−11.29 dB @ 245.062 MHz), Proceed, monitor scroller from real sweeps, Stop→filename; GUI never froze.** Rate ~5 Hz (per-tick trigger reconfig) → G-4 optimizes to setup-once/sweep-many. | G-3 | ✅ Validated | 2026-06-02 |
| G-4 | Monitor mode + Dataflux CSV. Latched continuous monitor (`monitor_begin/read/end`), `mvp/dataflux.py` byte-exact writer, `MonitorRecord` + presenter CSV write to `ena-dev/data/<date>/`. **Live-validated via qt-mcp: 39.3 Hz (26 ms/pt, = bench ceiling), 980-pt CSV loads in `8_plot_monitor_data.py`; graceful teardown leaves instrument clean.** Plus USBTMC-resync + `:DISP:CCL` + busy-swallow fixes. | G-4 | ✅ Validated | 2026-06-02 |
| G-5 | Feature parity (F-/NF- checklist). **Live-validated:** F-6 sci-notation toggle (CSV fixed-decimal still loads in `8_plot_monitor_data.py`); F-3/4/5/8 monitor controls (stop-by Duration/Query-count/Manual, interval clamp 20–1000 ms, progress bar + remaining); F-7 History/Files page (`view_files.py` — list/delete/zip); sanity xlsx write (`sanity_xlsx.py`). **Sanity benchmark rate fixed**: single-sweep trigger path is ~4× slower than the bench in-GUI, so the sanity loop now uses the continuous latched path → correct rates (300/150/100/50 kHz = 41/36/33/27 Hz). **NF-2 indicative: 120 s monitor run = 4694 pts, 39.1 Hz sustained, drift +0.32% (<1% PASS).** | G-5 | ✅ Validated | 2026-06-02 |
| G-7 | **UI polish + instrument-hygiene fixes** (from 2026-06-04 live testing — §6.1). Responsive "flexbox-for-Qt" sizing (design-system D-6/§8), visible combo/spin arrow glyphs (D-7), `ElidedLabel` for long paths (D-8), legible locked timestamp checkbox, `restore_live()` after Verify, and a close-time `restore_live` race fix. **Implemented + live-validated 2026-06-04 (qt-mcp vs `MY54806798`):** #5 combo "auto" full (85→113 px); #6 long path holds window at 1080 px (was 1632); #2 Verify leaves `INT/CONT 1` (was BUS/Hold); #7 close mid-monitor leaves `INT/CONT 1` + clean queue (no −420); #4 "timestamp (always)" + tooltip + locked-checked styling; #1 **crisp ▼/▲ arrows via SVG assets** (`mvp/assets/*.svg`, referenced by absolute path in QSS `image: url(...)`) — the border-triangle was only a dash, so per user decision we shipped SVG carets (supersedes D-7's asset-free constraint). | G-7 | ✅ Validated | 2026-06-04 |
| G-8 | **Visual refresh** (post-G-7 aesthetic feedback). Two-column Configuration grid (kills the maximized empty-card zone), "bigger" slate palette refresh (visible panels + recessed input wells), semibold/brighter field labels, combo open-state (caret flips ▲). View-layer only; full spec in design-system §9 (D-9…D-12). **Implemented + qt-mcp-validated maximized 2026-06-04**; two build gotchas captured in §9.1/§9.4 (whole-combo `:on` accent-fill fallback; drop `field_max_w` inside the grid). | G-8 | ✅ Validated | 2026-06-04 |
| G-9 | **UI micro-polish** (2nd feedback pass). Fix 0 px Points↔IFBW gap (one `ifbwCell` container vs overlapping shared cells + grid spacing 14); round spin-button outer corners; increase card padding (16→~22) so text isn't tight to the border; remove dead "Browse host…", wire save-dir "Browse…" to a folder picker. View-layer only; full spec design-system §9.6 (D-13…D-15). **Implemented + qt-mcp-validated 2026-06-04** (Points↔IFBW gap 0→14 px via an `ifbwCell` QStackedWidget; rounded spin corners; Browse-host removed; card padding ~22). | G-9 | ✅ Validated | 2026-06-04 |
| G-10 | **Container dead-zone fix** (3rd feedback pass). Layout-only `QWidget` containers (IFBW row, Center/Span, connection info, cal status, filename rows, Acquire rows) render with the darker window `bg` → dark bands + info text looks tight to the border. Fix = drop the universal `QWidget` background, set it on `QMainWindow` (containers go transparent, card colour shows through; 22 px card padding gives the spacing). One global QSS change. Full spec design-system §9.7 (D-16). **Implemented + qt-mcp-validated 2026-06-04** (Setup cards uniform, inputs keep recessed wells, Files page + window base correct — no transparency regression). | G-10 | ✅ Validated | 2026-06-04 |
| G-11 | **IFBW width + spin click-feedback** (4th feedback pass). IFBW combo (424 px) wider than Start/Stop (345 px) → rebuild `ifbwCell` pages with a grid mirroring the config columns so the monitor combo == col1 width; add `:hover`/`:pressed` feedback to spin up/down buttons (mirror the combo). View-layer only; full spec design-system §9.8 (D-17/D-18). **Implemented + qt-mcp-validated 2026-06-04** (IFBW 424→352 px ≈ Start 345 px, right edges aligned; spin hover/press QSS clean). | G-11 | ✅ Validated | 2026-06-04 |
| G-12 | **Monitor Y-axis toggle** — plot the Acquire monitor scroller's Y-axis as min-S11 frequency (MHz, default) **or** magnitude (dB) at the tracked notch, via a `yAxisSelector` combo in the monitor options row. Magnitude is **already logged** (`MonitorRecord.s11_db`, emitted per sweep by `backend_e5063a.monitor_read`) → **View + presenter only, zero backend/SCPI/CSV change.** Idle-only (selector locked during RUNNING). Touch points: `view_acquire` (`yAxisSelector` + a `set_monitor_yaxis(metric)` that swaps left-axis label/autorange & re-points the curve), `main_window` presenter (read metric at Start, buffer the chosen series), `model.MonitorConfig.y_axis`. Spec: ux-spec §3.2/§6/§1, design-system §9.9/D-19. **Implemented: `model.py` `MonitorConfig.y_axis`; `view_acquire.py` `yAxisSelector` + `monitor_yaxis_metric()`/`set_monitor_yaxis()` + idle-only gate in `set_running`; `main_window.py` `_on_yaxis_changed` (idle relabel) + metric locked at Start + metric-aware `_mon_yvals` buffer. qt-mcp-validated (stub): default freq, idle relabel freq↔dB, scroller plots dB series autoranged during run, selector disabled while RUNNING + re-enabled after Stop, both badges always shown, 0 Qt/QSS warnings, graceful close. CSV path untouched (writer + `MonitorRecord` unchanged).** | G-12 | ✅ Validated (qt-mcp, stub) | 2026-06-04 |
| G-13 | **Live S11 trace preview + Acquire display modes** (Monitor mode). On Proceed, `monitorPlot` shows a **live full S11 trace** (mag dB vs freq) free-running, mimicking the instrument so the user can verify the signal before/while recording. `displaySelector` (Live trace ⇄ Monitor minimum, default Live trace) toggles the existing min-S11 scalar scroller back in; G-12 `yAxisSelector` re-scoped to the minimum view, default → magnitude. State-machine change: preview armed once on Proceed (`monitor_begin`), torn down on Back/close; `Start`/`Stop` only toggle a recording flag. Controller gains `sigLiveTrace`, `doStartPreview`/`doStopPreview`, recording flag (reuses `read_trace_continuous` — full trace already read). Model: `MonitorConfig.display="trace"`, `y_axis` default `freq`→`mag`. Monitor mode only. Spec: ux-spec §1.1/§3.2/§4/§6, design-system §9.10/D-20. **Implemented: `controller.py` `sigLiveTrace`+`doStartPreview`/`doStopPreview`/`_preview_tick`; `main_window.py` Proceed→preview, recording-flag Start/Stop, `_on_live_trace`/`_on_display_changed`, Back→`doStopPreview`; `view_acquire.py` `displaySelector`+`set_acquire_display`/`set_live_trace`. qt-mcp-validated (stub): live trace on Proceed (no Start), display swap (axis Freq↔Time), yAxisSelector greyed in trace / locked during run, Start fills scroller, display live-switchable mid-record, Stop writes CSV (2287 pts) while preview keeps moving, Back clean, re-Proceed restarts; 0 warnings.** **Live-validated vs `MY54806798` 2026-06-04: real S11 trace (measurement noise + notch ~240 MHz) free-runs on Proceed; real rate eff-interval 26 ms ≈ 38.8 Hz (= continuous ceiling); 1050-pt real CSV loads in `8_plot_monitor_data.py`; Back → `INT`/`CONT 1` + clean queue; close WITH preview running → `INT`/`CONT 1` + clean queue (no BUS+Hold, no −420), exit 0.** | G-13 | ✅ Validated (qt-mcp, stub + live) | 2026-06-04 |
| G-14 | **WTMH lab branding** — WTMH (NCKU) logo as the window/taskbar icon + a ~28 px emblem in every `TopBar` (Setup/Acquire/Files, emblem-only), and the source `.ico` for the G-6 `.exe` icon. Assets → `mvp/assets/` (`WTMH.ico` copied from `LibreVNA-dev/gui/resources/`; downscaled `wtmh_logo.png` ~256 px), absolute-path via `_ASSETS` (not `.qrc`). One `theme.TopBar` `show_logo` change brands all screens; `QApplication.setWindowIcon`/`MainWindow.setWindowIcon`. Spec: design-system §9.11/D-21, ux-spec §2.1/§3.1. **Implemented: `assets/prep_wtmh_assets.py` (copies `WTMH.ico` + scales `wtmh_logo.png` 256 px); `theme.py` `WTMH_ICO`/`WTMH_LOGO` + `TopBar(show_logo=True)` emblem; `e5063a_data_collector.py` + `main_window.py` `setWindowIcon`. qt-mcp-validated (stub): 3× `topbarLogo` 28×28 (Setup+Files headers show the emblem visually, Acquire instance present), window icon = WTMH.ico (multi-res 16/32/48), 0 Qt/QSS warnings, graceful close.** | G-14 | ✅ Validated (qt-mcp, stub) | 2026-06-04 |
| G-15 | **Calibration file listing bug fix** ("new ECal cal not found"). Root cause **live-diagnosed** (§6.2): `list_cal_files` queries `:MMEM:CAT? "D:\\"` (trailing backslash) → firmware **timeout** → silent fallback to 2 hardcoded defaults, so new/different-config cals never list (save+load both work). Fix: query `:MMEM:CAT? "D:"` (strip trailing sep), fail-loud (resync, no silent default-mask), refresh `calFileInput` after ECal/recall, and fix the recall-then-apply-config ordering. Spec: §6.2, ux-spec §2.4/§6. **Implemented + live-validated vs `MY54806798`: dropdown 2→5 after Connect (all `D:\*.sta`); recall 201pt → widgets sync to 201 + correction active at 201pt (`CORR:STAT 1`); fresh ECal at 401pt → new cal saved, dropdown 5→6, auto-selected, active.** | G-15 | ✅ Fixed + live-validated | 2026-06-04 |
| G-6 | `.exe` packaging (PyInstaller via auto-py-to-exe, **One-Directory**). Consumes G-14 (`--icon=mvp/assets/WTMH.ico` + `--add-data mvp/assets`). **Built + validated 2026-06-04** — full guide in [`docs/e5063a-packaging.md`](./e5063a-packaging.md). Key: `--exclude-module PyQt5 PyQt6` (venv has both PyQt6+PySide6 → dual-binding abort otherwise); `--paths` ×3 (`ena-dev/gui`, `ena-dev`, `ena_qt6_suite`) + hidden-imports (`ena_dev_paths`, `core.{visa_connection,scpi_commands,simulator}`) for the `sys.path` hack; **`sys.frozen` guard added to `ena_dev_paths.py`** (else the frozen app raises on the dev-tree dir check). `.exe` launches, WTMH titlebar icon + header emblem + full UI render. ⚠ target PC still needs **Keysight IO Libraries Suite** (native VISA driver, not bundleable). | G-6 | ✅ Built + validated | 2026-06-04 |

## 6.1 G-7 — UI/UX + instrument-hygiene defects (live testing 2026-06-04)

User hands-on testing + a qt-mcp live pass against the instrument (`MY54806798`) validated
six reported issues and surfaced one more (close-time freeze). **Specced here + in the
sibling specs; not yet implemented** — awaiting go-ahead. Detail by owner:

| # | Defect | Validated (how) | Fix & owner spec |
|---|--------|-----------------|------------------|
| 1 | Combo/spin **drop-down arrow invisible** (`modeSelector`, `ifbwMonitorInput`, `calFileInput`, `stopModeSelector`, `logIntervalInput`, all spin boxes) | `qt_screenshot` — only a divider, no caret. Root: `theme.py` styles `::drop-down`/spin-buttons `border:none` but never sets an arrow image. | **View/theme** — token-colored CSS border-triangle carets for `QComboBox::down-arrow` + `QSpinBox::up/down-arrow`. design-system D-7/§8.3. |
| 2 | **Verify trace freezes the instrument** | Live SCPI: before `:TRIG:SOUR? INT`/`:INIT1:CONT? 1`; after pressing Verify `BUS`/`0` (Hold). Root: `controller.doVerify` calls `read_single_trace()` (sets BUS+Hold) but never `restore_live()`. | **Presenter/controller** — `restore_live()` after the verify single sweep (a dedicated `verify_trace()` backend method that restores live before returning is cleanest). §3 contract. |
| 3 | **"Query UNTERMINATED"** lingering on the front panel | Live: `:SYST:ERR?` queue was **clean** (`+0,"No error"`). The −420 is the **sticky display message** (separate from the queue) left by a prior force-kill / thread-quit mid-USBTMC-read; `connect()`'s `:DISP:CCL` clears it. | Already handled by connect-resync; the real *cause* on close is #7. Document the "always Stop→idle→close; never force-kill" rule in-app (status hint). |
| 4 | **Timestamp checkbox** looks like a dead placeholder | `qt_find_widget` → `[disabled]`. By design (U-4: timestamp always on). | **View** — keep disabled+checked, add lock affordance (label " (always)" / tooltip / locked styling). ux-spec §2.5. **Decision: stays non-interactive.** |
| 5 | Interval combo clips **"auto"→"uto"** | `qt_widget_details`: width 85 px, `minimumContentsLength=0`; screenshot shows "uto". | **View** — `setMinimumContentsLength(7)` + `combo_min_w`. ux-spec §3.2 / design-system §8.2. |
| 6 | Long save path **expands the window** (1080→1632 px) | Live: set a 200-char path on `saveStatusLabel` → `qt_list_windows` width jumped to 1632. Root: plain `QLabel`, no elide/max-width; no responsive policy. | **View** — `ElidedLabel` + the responsive `SIZE`/`QSizePolicy` convention. design-system D-6/D-8/§8; ux-spec §3.1. |
| 7 | **App-close leaves the instrument in BUS+Hold** | Live: after a graceful `MainWindow.close()` the instrument was still `BUS`/`0`. Root: `closeEvent` emits `reqClose` (queued, cross-thread) then immediately `self._thread.quit()`, racing the queued `doClose`→`restore_live()`. | **Presenter** — run `restore_live()`/`close()` synchronously (or process the queued slot, e.g. block on a done-signal) **before** `_thread.quit()`. Also a latent −420 source if it tears down mid-read (#3). |

**Responsive sizing (user's broader ask):** implement the "flexbox-for-Qt" convention from
design-system **§8** across both screens (not just #5/#6 offenders): `SIZE` tokens, per-role
`QSizePolicy`, `ElidedLabel` for all arbitrary-length labels, `MainWindow.setMinimumSize`.
**G-7 acceptance** = design-system §8.6 (qt-mcp: no `text_truncated`; long path doesn't
change window width; visible carets; resize-down works) + Verify and app-close both leave
`:TRIG:SOUR? INT`/`:INIT1:CONT? 1` (live free-run) with a clean error queue.

## 6.2 G-15 — Calibration file listing bug ("new ECal cal not found"; FIXED + live-validated 2026-06-04)

**User report:** after running a new ECal at a different configuration, the new `.sta`
cannot be found when trying to recall it (it never appears in the `calFileInput` dropdown).

**Status: ✅ FIXED + live-validated.** After the fix (vs `MY54806798`): dropdown lists **5**
`D:\*.sta` after Connect (was 2 hardcoded); recalling the different-config `…201pt.sta`
syncs the widgets to 201 pt and keeps correction active at 201 pt (`:SENS1:CORR:STAT? 1`);
a fresh ECal at a **new** grid (401 pt) saves `…401pt.sta`, which appears in the dropdown
(5→6) auto-selected and active — without reconnecting.

**Diagnosis — ROOT-CAUSED LIVE vs `MY54806798` (read-only probes):**

| # | Finding | Evidence |
|---|---------|----------|
| 1 | **`list_cal_files` queries the wrong directory string → times out → silent fallback.** `backend_e5063a.list_cal_files(directory=r"D:\\")` sends `:MMEM:CAT? "D:\\"` (trailing backslash). The E5063A firmware **cannot catalog a path with a trailing backslash → `VI_ERROR_TMO` timeout** → `ENAConnectionError` → the method returns **2 hardcoded defaults** (`cal_S11_200-250MHz_801pt.sta`, `State03.sta`). So the recall dropdown is *always* those 2 files, regardless of what's saved. **This is the bug.** | `:MMEM:CAT? "D:\\"` → `VI_ERROR_TMO`; `:MMEM:CAT? "D:"` (no trailing slash) → returns the full catalog. |
| 2 | **The save WORKS; the file is on the instrument.** The user's different-config cal `cal_S11_200-250MHz_201pt.sta` (17 594 B) is present on `D:\` — `run_ecal`'s `:MMEM:STOR` is fine. | `:MMEM:CAT? "D:"` lists `cal_S11_200-250MHz_201pt.sta`, `…801pt.sta`, `State01/02/03.sta` (5 files). |
| 3 | **The existing regex is correct** — it parses all 5 `.sta` from the *working* query. The only fault is the directory string that makes the query time out. | `re.findall(r'([^",\\]+\.sta)', raw)` on the `"D:"` output → all 5 names. |
| 4 | **Load WORKS.** Recalling `cal_S11_200-250MHz_201pt.sta` via `:MMEM:LOAD:STAT` → correction active, `SOLT1`, points→201. So save+load are fine; only **listing** is broken. | `investigate_cal_load.py`: after LOAD, `:SENS1:CORR:STAT? 1`, `:SWE:POIN? +201`. |
| 5 | **The timeout also desyncs the session.** The failed CAT query leaves the session addressed-to-talk → `-420 "Query UNTERMINATED"` + `-257 "File name error"` linger in the queue (cleared only by the next connect's `*CLS`). So the silent fallback is **not** harmless. | `:SYST:ERR?` showed `-420`/`-257` after the timed-out CAT. |
| 6 | **Secondary: the dropdown isn't refreshed after an ECal.** `_on_ecal_done` (and `_on_recalled`) never re-emit `reqListCal`, so even with #1 fixed a *freshly created* cal wouldn't appear until the user reconnects. | `reqListCal.emit()` appears only in `_on_connected` (main_window.py). |
| 7 | **Tertiary (related, Calibration section): recall-then-apply-config.** `_on_recall` recalls the `.sta` then immediately `_emit_apply_config(...)` with the **current widget** grid. If the recalled cal's grid ≠ the widget grid, the apply changes points and **invalidates the just-recalled cal**. | `_on_recall` (main_window.py): `reqRecall.emit(...)` then `_emit_apply_config(...)`. |

**Confirmed symptom (GUI, live):** after Connect, `calFileInput.count == 2` (the hardcoded
defaults); the user's `cal_S11_200-250MHz_201pt.sta` is absent though it exists on `D:\`.
`calFileInput` is editable, so a manually-typed path still recalls (works) — but the list
can't surface new cals.

**Fix (G-15 — ✅ IMPLEMENTED + live-validated):**
1. **Directory string (root fix).** In `list_cal_files`, normalise the directory to drop any
   trailing separator before the query: `d = directory.rstrip("\\/") or "D:"` → send
   `:MMEM:CAT? "D:"`. Keep building recall paths as `d + "\\" + name` (→ `D:\cal_…sta`,
   valid for `:MMEM:LOAD:STAT`). With the query fixed, the existing regex lists every `.sta`.
2. **Fail loud, not silent.** Give the CAT query a short dedicated timeout; on failure
   `session.clear()` + `_drain()` to resync (avoid the #5 `-420` leak) and surface a status
   hint (e.g. "couldn't list cal files") instead of masking with hardcoded defaults. Keep the
   defaults only as an explicit last resort.
3. **Refresh after create.** In `_on_ecal_done` (and `_on_recalled`), re-emit `reqListCal`
   **and** add `res["sta_path"]` to `calFileInput` + select it, so a new cal is immediately
   findable/selectable without reconnecting.
4. **Recall ordering (tertiary).** After a recall, read back the loaded grid
   (`:SENS:FREQ:STAR/STOP?`, `:SWE:POIN?`) and reflect it into the config widgets instead of
   re-applying the stale widget grid — so the recalled cal stays valid and the UI matches.
   (Or apply config *before* recall.) Flagged; smaller than #1–#3.

**G-15 acceptance (qt-mcp + live):** after Connect, `calFileInput` lists **all** `D:\*.sta`
(incl. a different-config cal); run an ECal at a new grid (e.g. 401 pt) → the new
`cal_S11_…401pt.sta` appears in the dropdown without reconnecting and recalls active; the
error queue stays clean across a (now non-timing-out) listing. Diagnostic scripts:
`ena-dev/scripts/investigate_cal_files.py`, `…/investigate_cal_load.py`.

## 7. Open questions

- **OQ-1** Monitor trigger default: continuous (max rate) vs single (simpler/deterministic)? Lean continuous; confirm during G-4.
- **OQ-2** ~~Where does the GUI get freq/points — live or YAML; show read-only with only IFBW editable~~ **Revised 2026-06-02 (S-18):** start/stop/points are now **user-editable** in the Configure capability (host-driven), and editing them triggers a **re-cal** prompt (ECal) since the grid changed. IFBW stays editable with **no** re-cal. On connect, still read the live grid from the instrument as the initial display values.
- **OQ-3** Data root: migration-spec §5.4 says `code/LibreVNA-dev/data/`; but ena-dev outputs currently go to `code/ena-dev/data/`. Pick one for Monitor CSVs (lean `ena-dev/data/` for tool locality) — decide at G-4.
- **OQ-4** Reuse the compiled `.ui`/`main_window.py` as-is, or re-lay-out for the simplified S11-only/Monitor workflow? Lean: reuse first, refine later.

## 8. References
- **UX / screen spec (what's on each screen): [`docs/e5063a-gui-ux-spec.md`](./e5063a-gui-ux-spec.md)** — the deterministic two-screen flow (Setup → Acquire): full widget inventories with objectNames, navigation/state machine, filename rule, model deltas, control→presenter→backend wiring. Read this before coding any view.
- **Design system (View layer): [`docs/e5063a-gui-design-system.md`](./e5063a-gui-design-system.md)** — token+factory pattern adopted from `references/reports/20260602/paod_app`; governs G-0 (theme module) and G-5 (polish). Decision: code-built views consuming `theme.py`, drop the compiled `.ui`.
- Parent: `docs/e5063a-migration-spec.md` (§5 requirements, §6.7 bench, §4A workflow, §12 status).
- SCPI: `docs/E5063A_SCPI_Reference.md` (⛔ never `9018-07931…pdf`).
- Backend to adapt: `code/ena-dev/scripts/bench_e5063a_realworld.py`, `code/ena_qt6_suite/core/visa_connection.py`.
- Source GUI to port: `code/LibreVNA-dev/gui/mvp/` (script 7).
- qt-mcp verify loop: `docs/qt-mcp-gui-automation.md`; memory `project-qt-mcp-setup`.
- Objective + log-interval math: memory `project-monitor-loginterval-e5063a`; `REPORT/20260226/20260205.pdf`.
- Dataflux CSV consumer: `code/LibreVNA-dev/scripts/8_plot_monitor_data.py`.

## 9. Changelog
| Date | Change | By |
|------|--------|-----|
| 2026-07-24 | **Timestamp-integrity fix implemented + headless-validated (post-G; SPEC `docs/e5063a-timestamp-fix-spec.md`).** Fixes the 20260715 professor report (timestamps only; S11 values unaffected). `controller.py`: `sigMonitorPoint` → `Signal(object,float,float)` carrying a `time.perf_counter_ns()` stamp taken right after `read_trace_continuous()` (replaces `time.monotonic()` = GetTickCount64 15.625 ms tick; also fixes GUI-slot re-stamping latency); sanity loop timed with `perf_counter`. `dataflux.py`: new **`DatafluxWriter`** — file opens at Start, rows stream via queue + daemon writer thread (64-row/2 s batches), `Number of Data`/`Log Interval(ms)` written as fixed-width placeholders and patched in place at Stop (byte-compatible with `8_plot_monitor_data.py`; bounded RAM for 24 h+ runs; crash loses ≤2 s). `main_window.py`: wall+QPC anchors at Start, per-run wall-vs-QPC drift audit in save status, `_mon_records`/`_write_monitor_csv` removed, filename stamp = **Start** time, `closeEvent` finalizes an active writer, pre-Start stamps dropped; window title shows the version (`mvp/version.py`, SemVer per `docs/versioning-and-releases.md`). `verify_timestamp_fix.py` (writer unit test + offscreen STUB end-to-end) ALL PASS: 0.000% duplicate timestamps, dt continuum (497 distinct), CSV loads in `8_plot_monitor_data.py`. Committed `4203d78`/`cf46091`; v1.1.0-dev exe rebuilt. **Remaining: live-instrument pass + multi-hour re-validation → v1.1.0 release.** | Claude (with Aunuun) |
| 2026-06-04 | **G-6 `.exe` packaging built + validated (auto-py-to-exe 2.48.1 / PyInstaller 6.19.0, One-Directory).** Validated auto-py-to-exe is installed; added a `sys.frozen` guard to `ena_dev_paths.py` (skip the dev-tree `is_dir()` check when frozen — else the packaged app raises). Build config: `--windowed --icon mvp/assets/WTMH.ico --paths {gui,ena-dev,ena_qt6_suite} --add-data mvp/assets;mvp/assets --hidden-import {ena_dev_paths,core.visa_connection,core.scpi_commands,core.simulator} --exclude-module PyQt5 PyQt6` (the excludes are mandatory — venv has PyQt6+PySide6 → PyInstaller aborts on dual Qt bindings; `--collect-submodules pyqtgraph` re-pulls PyQt6 so it was dropped). Launched the `.exe`: window + WTMH titlebar icon + header emblem + full Setup UI render (screenshot). ⚠ target needs Keysight IO Libraries (VISA driver not bundleable). New `docs/e5063a-packaging.md` (auto-py-to-exe field guide + CLI/.spec + prerequisites); `.gitignore` for build/dist/output; `.spec` kept. **All GUI phases (G-0…G-15 + G-6) complete.** | Claude (with Aunuun) |
| 2026-06-04 | **G-15 fixed + live-validated (E5063A `MY54806798`).** `backend_e5063a.py`: `list_cal_files` now queries `:MMEM:CAT? "D:"` (strips trailing sep — no more timeout) + `session.clear()` on failure (fail-loud, no silent default-mask); `recall_cal` re-asserts only `:FORM:DATA REAL32`/`SWAP` (not the grid) and returns the recalled grid. `main_window.py`: `_on_recall` no longer applies the stale widget grid after recall; `_on_recalled` syncs widgets from the recalled grid (`_apply_grid_to_widgets`) + keeps the file listed; `_on_ecal_done` adds+selects the new `.sta` and re-emits `reqListCal` (`_ensure_cal_file_listed`). qt-mcp+live: dropdown 2→5 after Connect; recall `…201pt.sta` → widgets→201, `CORR:STAT 1` @ 201 pt (concurrent read); fresh ECal @ 401 pt → `…401pt.sta` saved + dropdown 5→6 auto-selected + active. Instrument restored to 801 pt/live/clean. | Claude (with Aunuun) |
| 2026-06-04 | **G-15 calibration file-listing bug live-diagnosed + fix specced (not implemented).** User: a new ECal at a different config can't be found to recall. Root-caused live vs `MY54806798` (read-only SCPI probes): `list_cal_files` queries `:MMEM:CAT? "D:\\"` (trailing backslash) → firmware **VI_ERROR_TMO timeout** → silent fallback to 2 hardcoded defaults; `:MMEM:CAT? "D:"` works and lists all 5 `.sta` incl. the user's `cal_S11_200-250MHz_201pt.sta` (so **save works**); LOAD of that cal works (corr active, 201 pt — so **recall works**); the timeout also desyncs the session (`-420`/`-257`). GUI confirmed `calFileInput.count==2`. Secondary: `_on_ecal_done` never refreshes the dropdown; tertiary: `_on_recall` applies the stale widget grid after recall. New §6.2 defect table + G-15 status row + fix design (query `"D:"`, fail-loud, refresh after create, recall ordering). Diagnostic scripts `ena-dev/scripts/investigate_cal_{files,load}.py`. Awaiting go-ahead to fix. | Claude (with Aunuun) |
| 2026-06-04 | **G-14 implemented + qt-mcp-validated (stub).** `assets/prep_wtmh_assets.py` copied `WTMH.ico` (15 KB) + scaled `wtmh_logo.png` (256 px, 84 KB) into `mvp/assets/`. `theme.py`: `WTMH_ICO`/`WTMH_LOGO` constants + `TopBar(show_logo=True)` renders a 28 px emblem (KeepAspectRatio/Smooth) far-left, tooltip "Wearable Technology & Mobile Healthcare — NCKU". `e5063a_data_collector.py` + `main_window.py`: `setWindowIcon(QIcon(WTMH_ICO))`. qt-mcp vs STUB: 3× `topbarLogo` 28×28 (one per TopBar); Setup + Files headers visually show the emblem; `MainWindow.windowIcon` = multi-res 16/32/48 from the `.ico`; 0 Qt/QSS warnings; graceful close (exit 0). G-6 will add `--icon`/`--add-data`. | Claude (with Aunuun) |
| 2026-06-04 | **G-14 WTMH lab branding specced (not implemented).** User asked to brand the GUI with the WTMH (NCKU) lab logo (`LibreVNA-dev/gui/resources/WTMH.{ico,png}`) so the packaged app carries it. Locked: header emblem on all screens (emblem-only) + window/taskbar icon + `.exe` icon. Decisions: assets → `mvp/assets/` (`WTMH.ico` + a downscaled `wtmh_logo.png` ~256 px from the 6 MB original), absolute-path via `_ASSETS` (not the LibreVNA `.qrc`); one `theme.TopBar` `show_logo` change brands Setup/Acquire/Files; `setWindowIcon` in entry + window; G-6 gains `--icon=mvp/assets/WTMH.ico` + `--add-data mvp/assets`. New G-14 row + §1.1 scope bullet + G-6 row update; full design in design-system §9.11/D-21, ux-spec §2.1/§3.1. Awaiting go-ahead. | Claude (with Aunuun) |
| 2026-06-04 | **G-13 live-instrument validated (E5063A `MY54806798`).** Drove the full G-13 flow via qt-mcp vs the real instrument (recall SOLT1 cal): the **real S11 trace** (measurement noise + a real notch ~240 MHz) free-runs on Proceed with no Start; **real rate eff-interval 26 ms ≈ 38.8 Hz** (= the documented continuous ceiling, not the stub's artificial 64 Hz); Start logged a **1050-pt real CSV** that loads in `8_plot_monitor_data.py` (E5063A/MY54806798, 1050 rows); preview kept free-running after Stop (notch tracked); **Back → `:TRIG:SOUR? INT` / `:INIT1:CONT? 1` + clean `:SYST:ERR?`** (real `restore_live`); **close WITH the preview running → `INT`/`CONT 1` + clean queue** (no BUS+Hold, no −420), process exit 0. State verified with a non-disturbing read-only pyvisa session (`ena-dev/scripts/check_instrument_state.py`). Minor cosmetic (now fixed): pyqtgraph autorange showed a "(×0.001)" SI-prefix on the magnitude axis when a sweep's notch was very shallow — fixed globally by adding `ax.enableAutoSIPrefix(False)` to `setup_plot()` (both axes, all plots); headless-verified `autoSIPrefix == False`. | Claude (with Aunuun) |
| 2026-06-04 | **G-13 implemented + qt-mcp-validated (stub).** `controller.py`: `sigLiveTrace` + `doStartPreview`/`doStopPreview`/`_preview_tick` (reuses `read_trace_continuous`, emits full trace + min each sweep). `main_window.py`: Proceed→`reqStartPreview`, `_start_recording`/`_stop_recording` recording-flag (Start/Stop no longer arm/disarm the instrument), `_on_live_trace`, `_on_display_changed`, `_on_monitor_point` (badges always; record+scroller only while recording, elapsed since Start), Back→`reqStopPreview`. `view_acquire.py`: `displaySelector` + `set_acquire_display`/`set_live_trace`, `yAxisSelector` default magnitude + greyed in trace mode. `model.py`: `MonitorConfig.display="trace"`, `y_axis` default freq→mag. qt-mcp vs STUB: live trace renders the full notch on Proceed (no Start); Display swaps trace↔minimum (X Freq↔Time, yAxis greys/enables); Start fills the scalar scroller + progress; Display live-switchable mid-record; Stop wrote `run_monitor_...csv` (2287 pts) while the preview kept moving (notch tracked 233.69→233.31 post-Stop); Back→Setup clean; re-Proceed restarts; 0 Qt/QSS warnings; graceful close. | Claude (with Aunuun) |
| 2026-06-04 | **G-13 live S11 trace preview + Acquire display modes specced (not implemented).** User redirect: the Acquire monitor plot should mimic the instrument — a **live full S11 trace** (mag dB vs freq) free-running from Proceed so the signal can be verified before/while recording; the min-S11 scalar view kept as a non-default display. Discovery: `read_trace_continuous` already returns the full trace each sweep (the monitor path just argmins it) → live trace = plot `(freqs,s11)`, no new SCPI; the work is controller/presenter + state-machine. User-locked: `displaySelector` (Live trace ⇄ Monitor minimum) + re-scoped G-12 `yAxisSelector` (minimum only); preview from Proceed through record (Start only toggles logging); Monitor mode only; defaults Live trace + magnitude. State machine: `monitor_begin` on Proceed, `monitor_end`/`restore_live` on Back/close, recording flag on Start/Stop; controller `sigLiveTrace`+`doStartPreview`/`doStopPreview`; model `MonitorConfig.display`, `y_axis` default freq→mag. New G-13 row + §1.1 scope + §3 backend note; full UX in ux-spec §1.1/§3.2/§4/§6, design in design-system §9.10/D-20. Awaiting approval. | Claude (with Aunuun) |
| 2026-06-04 | **G-12 implemented + qt-mcp-validated (stub).** `model.py`: `MonitorConfig.y_axis="freq"`. `view_acquire.py`: `yAxisSelector` combo in the monitor options row (+ `field()`), `monitor_yaxis_metric()`, `set_monitor_yaxis()` (label + autorange swap), idle-only gate in `set_running()`; `set_monitor_curve` made metric-agnostic. `main_window.py`: `_on_yaxis_changed` (idle relabel + clear stale curve), metric read & locked at Start, `_mon_freqs`→`_mon_yvals` buffering the chosen metric. qt-mcp vs STUB: default "Min-S11 freq (MHz)"; switching to "Magnitude (dB)" relabels the axis "S11 magnitude (dB)"; Start → scroller plots the dB series autoranged (~−32.5 dB), badges show both freq (233.312 MHz) + mag (−32.50 dB), selector disabled; Stop → selector re-enabled; 0 Qt/QSS warnings; graceful close. Backend/SCPI/Dataflux CSV untouched. | Claude (with Aunuun) |
| 2026-06-04 | **G-12 monitor Y-axis toggle specced (not implemented).** Discovery on user feedback ("let me switch the Acquire scroller Y-axis to Magnitude (dB)"). Read the live code: `backend_e5063a.monitor_read` already returns `(min_freq_hz, mag_db)`, `MonitorRecord` stores both, the presenter already shows both as badges, and `dataflux.py` always writes both columns → **feature is View + presenter only, zero backend/SCPI/CSV change.** User-locked design: combo `yAxisSelector` (matches existing combos), "Magnitude" = S11 mag at the tracked notch minimum, **idle-only** (locked during RUNNING). New G-12 status row + §3 backend-contract note; full widget/wiring in ux-spec §3.2/§6/§1/§4 and design-system §9.9/D-19. Awaiting go-ahead. | Claude (with Aunuun) |
| 2026-06-04 | **G-11 implemented + qt-mcp-validated.** `view_setup.py` `ifbwCell` pages rebuilt as `QGridLayout`s mirroring the config columns (+ a real `QWidget` spacer in monitor col2) → IFBW combo 424→352 px, right edge aligned with Start (345 px). `theme.py` spin `::up/down-button:hover` (border_light) + `:pressed` (accent_dim) — no QSS parse warnings (transient state, not screenshot-captured). | Claude (with Aunuun) |
| 2026-06-04 | **G-11 specced (not implemented).** 4th hands-on pass validated: (a) IFBW combo 424 px > Start 345 px — the G-9 `ifbwCell` monitor page (`[label][combo,1][stretch,1]`) over-widened the combo; fix = rebuild each page with a `QGridLayout` mirroring the config grid (4 cols, stretch 1/3) so the monitor combo lands at col1 width; (b) spin up/down buttons lack click feedback → add `:hover`/`:pressed` QSS mirroring the combo's `::drop-down:pressed`. Spec design-system §9.8/D-17-D-18. Awaiting go-ahead. | Claude (with Aunuun) |
| 2026-06-04 | **G-10 container dead-zone fix implemented + qt-mcp-validated.** Dropped the universal `QWidget{background-color}`, set it on `QMainWindow` (theme.py). Verified across Setup + Files pages: cards uniform (no dark bands behind IFBW/Center-Span/connection-info/cal-status), inputs keep recessed wells, window base + Files list correct (no transparency/black regression); combo popup/msgbox/file-dialog keep explicit backgrounds; Acquire covered by shared factories. | Claude (with Aunuun) |
| 2026-06-04 | **G-10 container dead-zone fix specced (not implemented).** 3rd hands-on pass validated that plain `QWidget` layout-containers inside cards paint the darker window `bg` (global `QWidget{background-color}`), giving dark bands on the IFBW row (#1), Center/Span, connection info, and cal status, and making info text look tight to the border (#2). Single-cause across all sections + both pages. Fix (spec, design-system §9.7/D-16): drop the universal `QWidget` background, set it on `QMainWindow` → containers transparent, card colour shows through; the 22 px card padding then gives the border spacing. Awaiting go-ahead. | Claude (with Aunuun) |
| 2026-06-04 | **G-9 UI micro-polish implemented + qt-mcp-validated.** `theme.py` (card_pad/card_pad_v/input_radius tokens, spin-button corner radius), `view_setup.py` (card padding, grid verticalSpacing 14, **`ifbwCell` QStackedWidget** replacing the overlapping shared cells, removed `calBrowseButton`), `view_acquire.py` (panel/control padding), `main_window.py` (`saveDirButton`→`_on_browse_savedir` folder picker). Verified: Points↔IFBW gap 0→**14 px**, rounded spin corners, Browse-host gone, ~22 px card padding. (Save-dir picker wired but not interactively triggered — native modal.) | Claude (with Aunuun) |
| 2026-06-04 | **G-9 UI micro-polish specced (not implemented).** 2nd hands-on pass validated 4 items: (#1a) Points↔IFBW touch — geometry shows 0 px gap (vs 10 px elsewhere), caused by overlapping shared-cell mode widgets in the IFBW grid row → fix = one `ifbwCell` container + verticalSpacing 14; (#1b) spin up/down buttons don't follow the input's rounded corners → add `border-top/bottom-right-radius`; (#2) `calBrowseButton` + `saveDirButton` both dead — **remove** Browse-host (redundant), **wire** save-dir Browse to a folder picker; (#3) card padding 16→~22 so text isn't tight to the rounded border. Spec in design-system §9.6 / D-13…D-15, ux-spec §2.4/§2.5/§6. View-layer only; awaiting go-ahead. | Claude (with Aunuun) |
| 2026-06-04 | **G-8 visual refresh implemented + qt-mcp-validated.** `theme.py` (slate `CLR` palette, `font()/label()` `weight=` + `field_label()` DemiBold factory, combo `::down-arrow:on`→▲ + `::drop-down:pressed`) and `view_setup.py` (two-column `QGridLayout` config + `_apply_mode_visibility` cell toggling + `_labeled` semibold). Verified maximized: form fills width (no dead zone), panels visible / inputs recessed, labels semibold, caret flips ▲ on open. Two build gotchas fixed: whole-combo `QComboBox:on{border}` made non-editable combos render accent-filled (palette-Highlight fallback) → sub-controls only; `field_max_w` cap inside the 2-col grid left a ~400 px gap → dropped in the grid. | Claude (with Aunuun) |
| 2026-06-04 | **G-8 visual refresh specced (not implemented).** Post-G-7 aesthetic feedback; user locked 4 directions: two-column Configuration grid (removes the maximized empty-card zone — a G-7 `field_max_w` side effect), "bigger" slate palette refresh (near-black→medium slate, visible panels + recessed input wells + stronger borders + brighter secondary text), semibold/brighter field labels, combo open-state (caret flips ▲ + drop-down accent highlight). New G-8 status row; full design in design-system §9 / D-9…D-12. View-layer only; awaiting go-ahead to implement. | Claude (with Aunuun) |
| 2026-06-04 | **G-7 implemented + live-validated.** Built the responsive layer (`theme.py` `SIZE` tokens, glyph QSS, `ElidedLabel`, `field()`), applied across `view_setup`/`view_acquire`, `main_window.setMinimumSize(880,600)`, `controller.doVerify` now `restore_live()` after the sweep, and `main_window.closeEvent` runs `doClose` via `BlockingQueuedConnection` before quitting the controller thread. qt-mcp re-verify vs `MY54806798`: #5 "auto" fits (85→113 px); #6 long path holds window at 1080 px (was 1632); #2 Verify → `INT/CONT 1`; #7 close mid-monitor → `INT/CONT 1` + clean queue (no −420); #4 "timestamp (always)"+tooltip+locked-checked styling. Initially #1 used an asset-free CSS border-triangle, but Qt rendered it as a dash; per user decision, shipped **SVG arrow assets** (`mvp/assets/{down_arrow,down_arrow_dim,up_arrow}.svg`) referenced by absolute-path `image: url(...)` → crisp ▼/▲ verified via qt-mcp. Supersedes D-7's asset-free constraint. | Claude (with Aunuun) |
| 2026-06-04 | **G-7 added (UI polish + instrument hygiene) from live testing.** User hands-on test + a qt-mcp live pass against `MY54806798` validated 6 reported issues and surfaced 1 more: invisible combo/spin arrows, Verify leaving the instrument in BUS+Hold (no `restore_live` in the verify path — confirmed `INT/CONT1`→`BUS/CONT0`), sticky "Query UNTERMINATED" panel msg (queue itself clean), the disabled-by-design timestamp checkbox, "auto"→"uto" combo clipping, a long save path growing the window 1080→1632 px, and a close-time freeze (closeEvent races `reqClose` vs `_thread.quit()`). New §6.1 defect table + G-7 status row. Responsive "flexbox-for-Qt" convention specced in design-system §8 (D-6/D-7/D-8); per-widget fixes in ux-spec §2.5/§3.1/§3.2. **Validation only — no GUI code changed; implementation awaits user go-ahead.** | Claude (with Aunuun) |
| 2026-06-02 | Spec created as the next-session kickoff for migration-spec §5. Port-vs-replace map grounded in the actual `LibreVNA-dev/gui/mvp/` class/method inventory; backend adapter contract, Monitor-mode min-freq extraction, phased G-0…G-6 plan + status table defined. | Claude (with Aunuun) |
| 2026-06-02 | **G-5 feature parity (live-validated).** F-6 sci-notation toggle (`dataflux.write` `scientific` flag; fixed-decimal CSV still loads in `8_plot_monitor_data.py`). F-3/4/5/8 monitor controls: `view_acquire` stop-mode selector (Duration/Query-count/Manual), `queryNumberInput` (1–100000) with presenter count-stop, interval clamp 20–1000 ms, `monitorProgress` + `remainingLabel`. F-7 History page (`view_files.py` `FilesPage` — multi-select list, delete, zip; reached via Setup "Files…"). Sanity xlsx (`sanity_xlsx.py`, openpyxl). `model`: `MonitorRecord`, `scientific_notation`, `stop_mode`, `query_number`. **Sanity-rate fix:** the in-GUI single-sweep trigger path runs ~4× slower than the bench (the `INIT:IMM`+`TRIG:SING`+`*OPC?` single-shot trigger, not GIL/plot contention — throttling + isolating the timing didn't help); switched the sanity benchmark to the proven **continuous latched path** (`read_trace_continuous`) → correct per-IFBW rates 41/36/33/27 Hz @ 300/150/100/50 kHz, matching the bench. **NF-2 indicative stability: 120 s monitor run = 4694 pts at 39.1 Hz sustained, mean interval 25.56 ms, drift +0.32% (1st vs 2nd half) — PASS; the 56% interval-std is the known host-VISA scheduler jitter, not drift.** Instrument left clean (queue empty, live, cal on). | Claude (with Aunuun) |
| 2026-06-02 | **G-4 + bugfix: monitor optimized, Dataflux CSV, USBTMC resync.** Added latched continuous monitor to `backend_e5063a.py` (`monitor_begin`/`monitor_read`/`monitor_end` — `:INIT:CONT ON` + `:STAT:OPER:NTR 16`/`:PTR 0` + bit-4 `:EVEN?` poll) for full rate; `mvp/dataflux.py` writes a byte-identical Dataflux CSV (verified: `8_plot_monitor_data.py` `parse_metadata`+`load_data` loads our E5063A CSV, 229 rows). `model.MonitorRecord` + presenter records per-point datetime and writes CSV to `ena-dev/data/<date>/` on stop. **Bug (user-reported): instrument logged −420 "Query UNTERMINATED."** Root cause = the GUI being `Stop-Process -Force`-killed **mid-monitor-read** (host died addressed-to-talk). Not a logic bug — a fresh reconnect showed a clean error queue. Hardened anyway: `connect()` now does `viClear` + `*CLS` + `:ABOR` to resync a dirty session; general timeout 60→15 s (ECal bumps to 70 s) so a desync surfaces fast; `*CLS` on `monitor_begin`. Also fixed the busy-swallow (stopped disabling action buttons — the controller serializes requests, so clicks queue instead of being lost). Teardown rule: Stop the monitor (idle) before closing; don't force-kill mid-sweep. | Claude (with Aunuun) |
| 2026-06-02 | **G-1/G-2/G-2c/G-3 built + live-verified.** `mvp/backend_e5063a.py` (`E5063ABackend` — one ENAConnection session, probe/apply_config/list_cal_files/recall_cal/detect_ecal/run_ecal/read_single_trace/monitor_min_freq, reusing the proven SCPI) headless-verified 7/7 against the live E5063A+N7550A via `verify_backend_g2.py` (incl. a real in-app ECal). `mvp/controller.py` (`BackendController`) runs all VISA on a dedicated QThread (NF-4) with request/result signals; backend is stub-vs-real by resource (`StubE5063ABackend` added). `main_window.py` presenter rewired to the controller. qt-mcp live flow vs the instrument: Connect→real IDN, Recall→SOLT1 active, Verify→real sweep (−11.29 dB @ 245.062 MHz), Proceed→Acquire, Start→live monitor scroller from real sweeps (badges/count/elapsed/rate), Stop→composed filename; GUI stayed responsive throughout. Monitor rate ~5 Hz because `read_single_trace` reconfigures the trigger each tick — flagged as the G-4 optimization (setup-once/sweep-many). Minor: a click during the busy-disable window is swallowed (retry works). | Claude (with Aunuun) |
| 2026-06-02 | **G-0 built + qt-mcp-verified.** Scaffolded `ena-dev/gui/mvp/` (theme.py = PySide6 translation of paod_app tokens/factories, desktop-retuned; model.py = E5063A deltas; view_setup.py = 5-card Setup; view_acquire.py = mode-adaptive Acquire; stub_backend.py; main_window.py = QStackedWidget shell + compact presenter) + entry `e5063a_data_collector.py`. Launched with `QT_MCP_PROBE=1`; qt-mcp confirmed: 1 window, 0 Qt warnings, 126 objectNames (all key ones resolve by name), Connect→Recall gates Proceed on, Verify renders the S11 dip (`qt_scene_snapshot` → PlotCurveItem), Proceed→Acquire, Monitor Start animates the min-freq scroller (points/elapsed/badges/amber dot), Stop composes the ux-spec filename. Both plots share `setup_plot()`. card() extended to take a name for objectName-scoped QSS. | Claude (with Aunuun) |
| 2026-06-02 | **Scope widened to one-stop Configure + Calibrate + Sanity + Monitor** after collaborator feedback (dynamic experiments need fast in-app re-config + re-cal). Confirmed both are host-drivable: `configure_e5063a.py` (proven) + new `calibrate_e5063a.py` (1-port S11 ECal via N7550A, validated live 14/14 OK, `.sta` round-trips 16/16). §1.1 adds Configure + Calibrate; §1.2 flips in-app 1-port ECal authoring to in-scope (S-18); OQ-2 revised (start/stop/points now editable → trigger re-cal, IFBW free); new status rows B-Cfg/B-Cal (✅ CLI) + G-2c (adapters, planned). | Claude (with Aunuun) |
