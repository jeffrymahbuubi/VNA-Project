# E5063A GUI Implementation SPEC — port the LibreVNA MVP, swap the backend

**Status:** ✅ Built & live-validated, G-0…G-5 (2026-06-02). Only G-6 (`.exe` packaging)
remains. Lives in `code/ena-dev/gui/`; full phase status in §6.
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
- **Live preview** of the current S11 trace (magnitude/phase) while idle/armed.
- Feature parity with the LibreVNA "Data Collector" GUI (the F-/NF- requirements in
  migration-spec §5.2/§5.3).

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
| G-6 | `.exe` packaging | G-6 | ⬜ Planned | — |

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
| 2026-06-02 | Spec created as the next-session kickoff for migration-spec §5. Port-vs-replace map grounded in the actual `LibreVNA-dev/gui/mvp/` class/method inventory; backend adapter contract, Monitor-mode min-freq extraction, phased G-0…G-6 plan + status table defined. | Claude (with Aunuun) |
| 2026-06-02 | **G-5 feature parity (live-validated).** F-6 sci-notation toggle (`dataflux.write` `scientific` flag; fixed-decimal CSV still loads in `8_plot_monitor_data.py`). F-3/4/5/8 monitor controls: `view_acquire` stop-mode selector (Duration/Query-count/Manual), `queryNumberInput` (1–100000) with presenter count-stop, interval clamp 20–1000 ms, `monitorProgress` + `remainingLabel`. F-7 History page (`view_files.py` `FilesPage` — multi-select list, delete, zip; reached via Setup "Files…"). Sanity xlsx (`sanity_xlsx.py`, openpyxl). `model`: `MonitorRecord`, `scientific_notation`, `stop_mode`, `query_number`. **Sanity-rate fix:** the in-GUI single-sweep trigger path runs ~4× slower than the bench (the `INIT:IMM`+`TRIG:SING`+`*OPC?` single-shot trigger, not GIL/plot contention — throttling + isolating the timing didn't help); switched the sanity benchmark to the proven **continuous latched path** (`read_trace_continuous`) → correct per-IFBW rates 41/36/33/27 Hz @ 300/150/100/50 kHz, matching the bench. **NF-2 indicative stability: 120 s monitor run = 4694 pts at 39.1 Hz sustained, mean interval 25.56 ms, drift +0.32% (1st vs 2nd half) — PASS; the 56% interval-std is the known host-VISA scheduler jitter, not drift.** Instrument left clean (queue empty, live, cal on). | Claude (with Aunuun) |
| 2026-06-02 | **G-4 + bugfix: monitor optimized, Dataflux CSV, USBTMC resync.** Added latched continuous monitor to `backend_e5063a.py` (`monitor_begin`/`monitor_read`/`monitor_end` — `:INIT:CONT ON` + `:STAT:OPER:NTR 16`/`:PTR 0` + bit-4 `:EVEN?` poll) for full rate; `mvp/dataflux.py` writes a byte-identical Dataflux CSV (verified: `8_plot_monitor_data.py` `parse_metadata`+`load_data` loads our E5063A CSV, 229 rows). `model.MonitorRecord` + presenter records per-point datetime and writes CSV to `ena-dev/data/<date>/` on stop. **Bug (user-reported): instrument logged −420 "Query UNTERMINATED."** Root cause = the GUI being `Stop-Process -Force`-killed **mid-monitor-read** (host died addressed-to-talk). Not a logic bug — a fresh reconnect showed a clean error queue. Hardened anyway: `connect()` now does `viClear` + `*CLS` + `:ABOR` to resync a dirty session; general timeout 60→15 s (ECal bumps to 70 s) so a desync surfaces fast; `*CLS` on `monitor_begin`. Also fixed the busy-swallow (stopped disabling action buttons — the controller serializes requests, so clicks queue instead of being lost). Teardown rule: Stop the monitor (idle) before closing; don't force-kill mid-sweep. | Claude (with Aunuun) |
| 2026-06-02 | **G-1/G-2/G-2c/G-3 built + live-verified.** `mvp/backend_e5063a.py` (`E5063ABackend` — one ENAConnection session, probe/apply_config/list_cal_files/recall_cal/detect_ecal/run_ecal/read_single_trace/monitor_min_freq, reusing the proven SCPI) headless-verified 7/7 against the live E5063A+N7550A via `verify_backend_g2.py` (incl. a real in-app ECal). `mvp/controller.py` (`BackendController`) runs all VISA on a dedicated QThread (NF-4) with request/result signals; backend is stub-vs-real by resource (`StubE5063ABackend` added). `main_window.py` presenter rewired to the controller. qt-mcp live flow vs the instrument: Connect→real IDN, Recall→SOLT1 active, Verify→real sweep (−11.29 dB @ 245.062 MHz), Proceed→Acquire, Start→live monitor scroller from real sweeps (badges/count/elapsed/rate), Stop→composed filename; GUI stayed responsive throughout. Monitor rate ~5 Hz because `read_single_trace` reconfigures the trigger each tick — flagged as the G-4 optimization (setup-once/sweep-many). Minor: a click during the busy-disable window is swallowed (retry works). | Claude (with Aunuun) |
| 2026-06-02 | **G-0 built + qt-mcp-verified.** Scaffolded `ena-dev/gui/mvp/` (theme.py = PySide6 translation of paod_app tokens/factories, desktop-retuned; model.py = E5063A deltas; view_setup.py = 5-card Setup; view_acquire.py = mode-adaptive Acquire; stub_backend.py; main_window.py = QStackedWidget shell + compact presenter) + entry `e5063a_data_collector.py`. Launched with `QT_MCP_PROBE=1`; qt-mcp confirmed: 1 window, 0 Qt warnings, 126 objectNames (all key ones resolve by name), Connect→Recall gates Proceed on, Verify renders the S11 dip (`qt_scene_snapshot` → PlotCurveItem), Proceed→Acquire, Monitor Start animates the min-freq scroller (points/elapsed/badges/amber dot), Stop composes the ux-spec filename. Both plots share `setup_plot()`. card() extended to take a name for objectName-scoped QSS. | Claude (with Aunuun) |
| 2026-06-02 | **Scope widened to one-stop Configure + Calibrate + Sanity + Monitor** after collaborator feedback (dynamic experiments need fast in-app re-config + re-cal). Confirmed both are host-drivable: `configure_e5063a.py` (proven) + new `calibrate_e5063a.py` (1-port S11 ECal via N7550A, validated live 14/14 OK, `.sta` round-trips 16/16). §1.1 adds Configure + Calibrate; §1.2 flips in-app 1-port ECal authoring to in-scope (S-18); OQ-2 revised (start/stop/points now editable → trigger re-cal, IFBW free); new status rows B-Cfg/B-Cal (✅ CLI) + G-2c (adapters, planned). | Claude (with Aunuun) |
