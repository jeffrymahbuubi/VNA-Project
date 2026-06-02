# E5063A GUI UX SPEC — two-screen flow (Setup → Acquire)

**Status:** ✅ Implemented & live-validated (2026-06-02; built across gui-spec G-0…G-5).
Realized in `code/ena-dev/gui/` — see `view_setup.py` (Screen 1), `view_acquire.py`
(Screen 2), `view_files.py` (Screen 3 / History, added during G-5), `main_window.py`
(presenter), `controller.py` (threaded backend). Deviations from this spec are noted in
§10 changelog.
**Owner:** Aunuun + Claude
**Parent spec:** [`docs/e5063a-gui-spec.md`](./e5063a-gui-spec.md) — the port/build plan.
**Sibling specs:** [`docs/e5063a-gui-design-system.md`](./e5063a-gui-design-system.md)
(View tokens/factories), [`docs/e5063a-migration-spec.md`](./e5063a-migration-spec.md)
(validated hardware/SCPI/backend foundation).

> ## What this doc is
> The **deterministic screen specification** for the E5063A Data Collector GUI: exactly
> what is on **Screen 1 (Setup)** and **Screen 2 (Acquire)**, every interactive widget
> with a fixed `objectName`, the navigation/state machine, the filename rule, the model
> deltas, and a control→presenter→backend wiring table. The goal: GUI implementation
> (gui-spec phases G-0…G-5) reads off this doc with **no design decisions left to make
> at code time**.
>
> **Feasibility: ✅ confirmed.** This is a standard `QStackedWidget` two-page wizard over
> four backends that already exist and are validated as CLI scripts:
> `configure_e5063a.py` (S-11a/b), `calibrate_e5063a.py` (S-18), and
> `bench_e5063a_realworld.py` (sanity + monitor sweep, S-12c/d). No new SCPI work.

---

## 0. Decisions (locked 2026-06-02 via user feedback)

| # | Decision | Source |
|---|----------|--------|
| U-1 | **Two screens, not one cram-window.** Screen 1 = Setup (configure + calibrate + filename); Screen 2 = Acquire (live data collection). Replaces the LibreVNA single-window approach. | User feedback |
| U-2 | **Navigation = back-allowed-when-idle.** `QStackedWidget`; a **Back to Setup** button returns to Screen 1 whenever acquisition is stopped/idle (state preserved); disabled while a run is active. | Q-Navigation |
| U-3 | **Mode chosen on Screen 1; Screen 2 adapts.** The acquisition mode (Device Sanity Check vs Continuous Monitor) is selected in Setup; Screen 2 renders the mode-specific panel. | Q-Mode |
| U-4 | **Filename auto-composed from: experiment label + mode+param + freq-grid(+points+IFBW) + timestamp(always).** Instrument serial and full config are stored *inside* the file (F-9/NF-5), not in the name. | Q-Filename |
| U-5 | **Screen 1 has a Verify step** — a "Verify" button fires one sweep into a mini S11 plot so the user confirms DUT + cal before committing. | Q-Setup-verify |
| U-6 | **One window, two stacked pages, single global stylesheet** (`theme.STYLESHEET`), every widget `setObjectName(...)` (design-system D-3). | design-system |

---

## 1. Navigation & state machine

```
            ┌──────────────────────── one QMainWindow ────────────────────────┐
            │  QStackedWidget (central)                                        │
            │    page 0  →  SetupPage   (objectName "setupPage")               │
            │    page 1  →  AcquirePage (objectName "acquirePage")             │
            └──────────────────────────────────────────────────────────────────┘

 Setup page                         Acquire page
 ──────────                         ────────────
 DISCONNECTED                       ARMED  ── start ─►  RUNNING ── stop/duration ─► SAVING ─► SAVED
   │ connect                          ▲                                                   │
   ▼                                  └──────────────── (run again) ◄────────────────────┘
 CONNECTED ── configure ─► CONFIGURED ── calibrate/recall ─► CALIBRATED
   │                                                              │
   └────────────────────── (config valid + cal active) ──────────┤
                                                                  ▼
                                                        READY ── Proceed ─► [page 1, ARMED]
                                          (Back to Setup, enabled only when idle) ◄──────────┘
```

**App states** (held in `presenter._state`, drives widget enable/disable):

| State | Page | Meaning | Key enabled controls |
|-------|------|---------|----------------------|
| `DISCONNECTED` | Setup | no VISA session | `connectButton`, `resourceInput` |
| `CONNECTED` | Setup | `*IDN?` ok, device info shown | config inputs, cal card |
| `CONFIGURED` | Setup | config valid (grid/points/IFBW/power/mode set) | cal card actions |
| `CALIBRATED` | Setup | correction active (recalled `.sta` **or** fresh ECal) | `verifyButton`, `proceedButton` |
| `READY` | Setup | CALIBRATED + filename resolved | `proceedButton` |
| `ARMED` | Acquire | on Acquire page, not yet running | `startButton`, `backButton` |
| `RUNNING` | Acquire | recording/benchmarking | `stopButton` (Back/Start disabled) |
| `SAVING` | Acquire | flushing file | (all disabled, brief) |
| `SAVED` | Acquire | file written, path shown | `startButton`, `backButton` |

**Gating rules (deterministic):**
- `proceedButton.enabled  ⇔  state ∈ {CALIBRATED, READY}` i.e. `device.connected AND calibration.active AND config.is_valid()`. (Filename label may be empty → defaults to `run`; not a gate.)
- `startButton.enabled   ⇔  page==Acquire AND state ∈ {ARMED, SAVED}`.
- `stopButton.enabled    ⇔  state == RUNNING`.
- `backButton.enabled    ⇔  page==Acquire AND state ≠ RUNNING AND state ≠ SAVING`.

---

## 2. Screen 1 — Setup page (`setupPage`)

Layout: a `TopBar` + a vertical scroll of `card()` panels + a sticky footer nav.
All widgets built in code from `theme.py` factories (design-system D-1); **no `.ui`**.

### 2.1 TopBar (`setupTopBar`)
| Element | objectName | Factory | Content |
|---|---|---|---|
| Title | `setupTitle` | `TopBar(title=...)` | "E5063A Data Collector — Setup" |
| Connection dot | `connDot` | `StatusDot` | grey=disconnected, green=connected, red=error |

### 2.2 Connection card (`connectionCard`)
| Widget | objectName | Type / factory | Notes |
|---|---|---|---|
| Resource string | `resourceInput` | `QLineEdit` | default `USB0::0x2A8D::0x5D01::MY54806798::0::INSTR` |
| Connect/Disconnect | `connectButton` | `button()` | toggles; runs `DeviceProbeWorker` (QThread) |
| IDN readout | `idnLabel` | `label()` | from `*IDN?` |
| Serial readout | `serialLabel` | `label()` | `DeviceInfo.serial_number` |
| Firmware readout | `fwLabel` | `label()` | parsed from IDN (A.07.06) |

### 2.3 Configuration card (`configCard`)
| Widget | objectName | Type | Bound model field | Notes |
|---|---|---|---|---|
| Start freq (MHz) | `startFreqInput` | `QDoubleSpinBox` | `config.start_frequency` | editing flags cal **stale** (U-2/§4A.6) |
| Stop freq (MHz) | `stopFreqInput` | `QDoubleSpinBox` | `config.stop_frequency` | "" |
| Points | `pointsInput` | `QSpinBox` | `config.num_points` | 2…1601; editing flags cal stale |
| Power (dBm) | `powerInput` | `QDoubleSpinBox` | `config.stim_lvl_dbm` | −45…+10 |
| Mode | `modeSelector` | `QComboBox` | `model.mode` | items: "Continuous Monitor", "Device Sanity Check" |
| IFBW — monitor (kHz) | `ifbwMonitorInput` | `QComboBox`(editable) | `monitor_config.ifbw_hz` | shown when mode=Monitor; IFBW change ≠ re-cal |
| IFBW set — sanity (kHz) | `ifbwListInput` | `QLineEdit` | `config.ifbw_values` | shown when mode=Sanity; CSV e.g. `300,150,100,50` |
| Sweeps/IFBW — sanity | `numSweepsInput` | `QSpinBox` | `config.num_sweeps` | shown when mode=Sanity |
| Center (derived) | `centerLabel` | `label()` | `config.center_frequency` | read-only, auto |
| Span (derived) | `spanLabel` | `label()` | `config.span_frequency` | read-only, auto |
| Cal-stale hint | `calStaleHint` | `label()` (amber) | — | "Grid changed → re-cal needed. (IFBW changes do not.)" only when grid edited after cal |

> **Mode swap rule:** `modeSelector` toggles visibility of the monitor-only vs
> sanity-only rows (`ifbwMonitorInput` vs `ifbwListInput`+`numSweepsInput`). Everything
> else is shared.

### 2.4 Calibration card (`calCard`)
A radio/segmented `calSourceSelector` chooses one of two branches.

**Branch A — Use existing cal (`calExistingPanel`):**
| Widget | objectName | Type | Notes |
|---|---|---|---|
| Cal file | `calFileInput` | `QComboBox`(editable) | instrument-side `.sta` path; default `D:\cal_S11_200-250MHz_801pt.sta` |
| Browse host… | `calBrowseButton` | `button_sm()` | pick a host `.sta` → auto-upload (`:MMEM:TRAN`) then recall |
| Recall | `recallButton` | `button()` | runs `configure_e5063a.configure()` recall path in a QThread |

**Branch B — Run new ECal (`calEcalPanel`):**
| Widget | objectName | Type | Notes |
|---|---|---|---|
| Port | `ecalPortInput` | `QSpinBox` | default 1 (1-port S11) |
| Run ECal | `runEcalButton` | `button()` | runs `calibrate_e5063a.calibrate()` in `CalibrateWorker(QThread)`; blocks ~10–15 s |
| Progress | `calProgressBar` | `progress_bar()` | indeterminate while ECal runs |

**Shared cal status (`calStatusPanel`):**
| Widget | objectName | Type | Notes |
|---|---|---|---|
| Active dot | `calActiveDot` | `StatusDot` | green when `:SENS1:CORR:STAT?`=1 |
| Cal type | `calTypeLabel` | `label()` | e.g. `SOLT1,+1,+0,+0,+0` |
| Cal source/file | `calSourceLabel` | `label()` | which `.sta` / "fresh ECal @ grid" |
| Confidence min/mean/max | `calConfLabel` | `label()` | from the cal-time confidence sweep |

### 2.5 Filename / metadata card (`filenameCard`)
| Widget | objectName | Type | Notes |
|---|---|---|---|
| Experiment label | `experimentLabelInput` | `QLineEdit` | free text e.g. `bloodvessel-t3`; sanitized |
| Include mode+param | `incModeCheck` | `QCheckBox` | default ✔ (U-4) |
| Include freq-grid | `incGridCheck` | `QCheckBox` | default ✔ (U-4) |
| Timestamp (always) | `incTimestampCheck` | `QCheckBox` | checked + **disabled** (always on) |
| Filename preview | `filenamePreviewLabel` | `label()` (mono) | live-updates as fields change (§5) |
| Save directory | `saveDirInput` | `QLineEdit` | default `code/ena-dev/data/` |
| Browse… | `saveDirButton` | `button_sm()` | folder picker → `model.save_data_folder` |

### 2.6 Verify card (`verifyCard`) — U-5
| Widget | objectName | Type | Notes |
|---|---|---|---|
| Verify trace | `verifyButton` | `button()` | one single sweep (`VNAPreviewWorker`) → `s11PreviewPlot` |
| Mini S11 plot | `s11PreviewPlot` | `pg.PlotWidget` + `setup_plot()` | small; magnitude dB vs freq |
| Verify status | `verifyStatusLabel` | `label()` | "min S11 −11.2 dB @ 233.4 MHz" etc. |

### 2.7 Footer nav (`setupFooter`)
| Widget | objectName | Type | Notes |
|---|---|---|---|
| Gate message | `gateLabel` | `label()` | why Proceed is disabled (e.g. "Run or recall a calibration first") |
| Proceed → Acquire | `proceedButton` | `button_success()` | enabled per §1 gating; switches stack to page 1, sets `ARMED` |

---

## 3. Screen 2 — Acquire page (`acquirePage`)

Common shell + a mode-specific panel. The mode comes from Screen 1 (`model.mode`).

### 3.1 Common shell
| Widget | objectName | Type | Notes |
|---|---|---|---|
| TopBar title | `acquireTitle` | `TopBar` | "Acquiring — {Monitor\|Sanity Check}" |
| Acquire dot | `acqDot` | `StatusDot` | green=armed, amber=running, blue=saved, red=error |
| Back to Setup | `backButton` | `button_sm()` | enabled only when idle (§1) |
| Plot container | `plotContainer` | `QWidget` | hosts the mode plot (§3.2/§3.3) |
| Start | `startButton` | `button()` | label "Start Record" (monitor) / "Start Benchmark" (sanity) |
| Stop / Abort | `stopButton` | `button_danger()` | disabled until RUNNING; blinks while running |
| Elapsed | `elapsedLabel` | `label()` (timer font) | `HH:MM:SS` since start |
| Count | `countLabel` | `label()` | monitor: "points logged: N"; sanity: "sweeps: N/total" |
| Live rate | `rateBadge` | `MetricBadge` | current sweep rate (Hz) |
| Save status | `saveStatusLabel` | `label()` | "Saved → <path>" after SAVED |

### 3.2 Monitor panel (`monitorPanel`) — mode = Continuous Monitor
Backend: `GUIVNAMonitorAdapter` (wraps `bench_e5063a_realworld` continuous + min-freq
extraction). Emits `(t, min_freq_hz, mag_db)` per sweep.

| Widget | objectName | Type | Notes |
|---|---|---|---|
| Min-freq scroller | `monitorPlot` | `pg.PlotWidget`+`setup_plot()` | min-S11 frequency (Hz) vs time; primary plot |
| Duration (s) | `durationInput` | `QDoubleSpinBox` | `monitor_config.duration_s`; 0/checkbox = indefinite |
| Indefinite | `indefiniteCheck` | `QCheckBox` | when ✔, disables `durationInput` (stop = manual) |
| Log interval | `logIntervalInput` | `QComboBox` | `monitor_config.log_interval_ms` ("auto" or ms) |
| Effective floor | `effIntervalBadge` | `MetricBadge` | warmup-measured min log-interval (1/mean-sweep) |
| Min-freq now | `minFreqBadge` | `MetricBadge` | latest `freq_hz` |
| Mag now | `magBadge` | `MetricBadge` | latest `s11_db` |

Output: Dataflux-compatible CSV (NF-5 byte-identical) via `export_dataflux_csv`,
loadable by `8_plot_monitor_data.py` with no conversion.

### 3.3 Sanity panel (`sanityPanel`) — mode = Device Sanity Check
Backend: `GUIVNASweepAdapter.run_single_ifbw_sweep` looped over `config.ifbw_values`.
Bounded run (= `len(ifbw_values) × num_sweeps`), not indefinite — `durationInput` hidden.

| Widget | objectName | Type | Notes |
|---|---|---|---|
| Latest S11 | `s11LivePlot` | `pg.PlotWidget`+`setup_plot()` | latest sweep trace; primary plot |
| Overall progress | `overallProgress` | `progress_bar()` | across all IFBW×sweeps |
| Current IFBW | `currentIfbwLabel` | `label()` | which IFBW is sweeping now |
| Per-IFBW metrics | `metricsTable` | `QTableWidget` | rows = IFBW; cols = mean time, rate Hz, noise floor, jitter |

Output: multi-sheet `.xlsx` (the existing bench schema), one sheet per IFBW.

---

## 4. Model deltas (port `LibreVNA-dev/gui/mvp/model.py` → `ena-dev/gui/mvp/model.py`)

Pure-logic, GUI-free (keeps unit-testability). Changes from the LibreVNA model:

| Dataclass | Change |
|---|---|
| `CalibrationState` | Repurpose for E5063A: `source: str` ∈ {"existing","ecal"}; `sta_path: str` (instrument-side); `active: bool` (was `loaded`, mirrors `:SENS1:CORR:STAT?`); `cal_type: str` (e.g. "SOLT1"); `grid: tuple[int,int,int]` (start,stop,points the cal is valid for); `ecal_port: int = 1`; `conf_min_mean_max: tuple[float,float,float] \| None`. **Drop** JSON `.cal` semantics. |
| `SweepConfig` | `start_frequency/stop_frequency/num_points` become **user-editable** (no `update_from_cal_file`); add `is_grid_stale_vs(cal_grid)` helper to drive `calStaleHint`. Keep `ifbw_values` (sanity), add nothing else. |
| `MonitorConfig` | unchanged (already has `ifbw_hz`, `log_interval_ms`, `duration_s`, `warmup_sweeps`). |
| **NEW** `AcquisitionMode` | `Enum`: `MONITOR`, `SANITY`. Stored as `VNADataModel.mode`. |
| **NEW** `FilenameSpec` | `label: str`, `include_mode: bool`, `include_grid: bool` (timestamp always); method `compose(model, ext) -> str` (§5). |
| `VNADataModel` | add `mode: AcquisitionMode`, `filename: FilenameSpec`; `is_ready_to_collect()` → `device.connected and calibration.active and config.is_valid()`. |

---

## 5. Filename composition rule (deterministic)

```
compose(model, ext) =
    "_".join(filter(None, [
        sanitize(filename.label)                       if filename.label else None,
        f"{mode_tag}_{param}"                           if include_mode else None,   # mode_tag ∈ {monitor, sanity}; param = S11
        grid_tag                                        if include_grid else None,   # see below
        now("%Y%m%d_%H%M%S"),                           # ALWAYS
    ])) + "." + ext

grid_tag (monitor) = f"{start}-{stop}MHz_{points}pt_{ifbw_khz}kHz"     # single IFBW
grid_tag (sanity)  = f"{start}-{stop}MHz_{points}pt_multiIFBW"         # IFBW varies per sheet
sanitize(s) = spaces→'-', strip chars not in [A-Za-z0-9._-]
ext = "csv" (monitor / Dataflux)  |  "xlsx" (sanity / multi-sheet)
```

Examples:
- `bloodvessel-t3_monitor_S11_200-250MHz_801pt_300kHz_20260602_143501.csv`
- `bench1_sanity_S11_200-250MHz_801pt_multiIFBW_20260602_143501.xlsx`

`filenamePreviewLabel` shows the live result; full metadata (Model/Serial/Date/Time/
Start/Stop/Span/IFBW/Points/Log-Interval) lives **inside** the file per F-9/NF-5.

---

## 6. Deterministic wiring table (control → presenter → backend → model → view)

| User action | Presenter slot | Worker / backend call | Model update | View update |
|---|---|---|---|---|
| `connectButton` | `_on_connect` | `DeviceProbeWorker` → `ENAConnection(*IDN?)` | `device.*` | `idn/serial/fwLabel`, `connDot`→green, state→CONNECTED |
| edit config inputs | `_on_config_changed` | — | `config.*` / `monitor_config.*` | `center/spanLabel`, `calStaleHint` if grid changed post-cal, state→CONFIGURED |
| `modeSelector` | `_on_mode_changed` | — | `model.mode` | show/hide monitor vs sanity rows |
| `recallButton` | `_on_recall_cal` | `CalRecallWorker` → `configure_e5063a.configure(recall)` | `calibration.{active,sta_path,cal_type,grid}` | `calActiveDot`, `calTypeLabel`, state→CALIBRATED |
| `runEcalButton` | `_on_run_ecal` | `CalibrateWorker` → `calibrate_e5063a.calibrate()` | `calibration.*` + new `.sta` path | `calProgressBar`, `calConfLabel`, `calActiveDot`, state→CALIBRATED |
| `verifyButton` | `_on_verify` | `VNAPreviewWorker` (1 sweep) | latest trace cache | `s11PreviewPlot`, `verifyStatusLabel` |
| filename fields | `_on_filename_changed` | — | `filename.*` | `filenamePreviewLabel` |
| `proceedButton` | `_on_proceed` | — | — | stack→page1, build `monitorPanel`/`sanityPanel`, state→ARMED |
| `startButton` (monitor) | `_on_start_monitor` | `GUIVNAMonitorAdapter.start_recording(interval, duration, on_point)` | `is_monitoring=True`, append `MonitorRecord` | `monitorPlot` scroll, badges, `elapsed/countLabel`, state→RUNNING |
| `startButton` (sanity) | `_on_start_sanity` | `GUIVNASweepAdapter.run_single_ifbw_sweep` loop | append `SweepData` | `s11LivePlot`, `overallProgress`, `metricsTable`, state→RUNNING |
| `stopButton` | `_on_stop` | adapter `stop_recording(out_dir)` / abort loop | finalize | save file, `saveStatusLabel`, state→SAVED |
| `backButton` | `_on_back` | — | — | stack→page0, state→READY |

All worker classes are `QThread` (NF-4: every VISA call off the GUI thread; GUI holds
60 fps). Cross-thread updates go via Signals → slots, exactly as the LibreVNA presenter
does today.

---

## 7. Mapping to gui-spec phases (no new phases needed)

| gui-spec phase | UX-spec content it implements |
|---|---|
| **G-0** | `QStackedWidget` shell + `setupPage`/`acquirePage` skeletons from `theme.py` factories; all objectNames (§2/§3); stub backend. qt-mcp: assert every objectName resolves. |
| **G-1** | `vna_backend.py` already covers sweep + min-freq (S-12d). |
| **G-2 / G-2c** | adapters incl. **new** `GUIVNAConfigureAdapter` + `GUIVNACalibrateAdapter` wrapping the two CLI scripts (§6). |
| **G-3** | Setup `verifyButton` live preview + Acquire live plots wired (§3). |
| **G-4** | Monitor panel + Dataflux CSV (§3.2, §5). |
| **G-5** | Sanity panel polish, filename preview, history, progress bars (§2.5, §3.3). |

---

## 8. Open questions (UX-level)

- **UX-OQ-1** ~~sanity PNG export?~~ **Resolved (G-5):** xlsx only (`sanity_xlsx.py`); notebook for deeper analysis.
- **UX-OQ-2** ~~History list — Setup panel or 3rd page?~~ **Resolved (G-5):** a third **Files page** (`view_files.py`, stack index 2, reached via the Setup TopBar "Files…" button) with multi-select list + delete + zip. Cleaner than a Setup side-panel.
- **UX-OQ-3** ~~Require a label to proceed?~~ **Resolved:** label defaults to `run` (not a gate), per `FilenameSpec.compose`.

### 8.1 Deviations from the original spec (as built)
- **Third screen added** (`view_files.py` / History) — not in the original two-screen plan; resolves UX-OQ-2.
- **Monitor stop control** is a **stop-mode selector** (Duration / Query-count / Manual) + `queryNumberInput`, instead of the spec's single `durationInput` + `indefiniteCheck` — gives F-4/F-5 (duration↔count) parity. `monitorProgress` + `remainingLabel` added (F-8).
- **`sciNotationCheck`** added to the Filename card (F-6).
- Backend is a single `E5063ABackend` on a threaded `BackendController` (the §3 GUIVNA*Adapter contract is realized as methods on one backend object rather than separate adapter classes — same seam, less boilerplate).
- **Sanity + Monitor both use the continuous latched read** (`read_trace_continuous`) — the single-sweep trigger path is ~4× slower in-GUI.

---

## 9. References
- Backends (validated): `code/ena-dev/scripts/{configure,calibrate,bench}_e5063a*.py`.
- Model to port: `code/LibreVNA-dev/gui/mvp/model.py` (dataclass vocabulary used above).
- View tokens/factories: `docs/e5063a-gui-design-system.md` (`theme.py`).
- Backend adapter contract: `docs/e5063a-gui-spec.md` §3.
- Host cal/config capability: memory `project-e5063a-host-calibration`; migration-spec §8.1, S-18.
- qt-mcp verify loop: `docs/qt-mcp-gui-automation.md`.

## 10. Changelog
| Date | Change | By |
|------|--------|-----|
| 2026-06-02 | Spec created. Two-screen flow locked from user feedback (U-1…U-6): Setup (configure+calibrate+filename+verify) → Acquire (mode-adaptive live collection). Full widget inventories with objectNames, navigation/state machine + gating, filename composition rule, model deltas, deterministic control→presenter→backend wiring table, phase mapping. Feasibility confirmed — wraps existing validated backends. | Claude (with Aunuun) |
| 2026-06-02 | **Implemented & live-validated (G-0…G-5).** Status → ✅. UX-OQ-1/2/3 resolved; §8.1 "Deviations from the original spec" added (third Files page; stop-mode selector + query-count + progress; sci-notation toggle; single threaded `E5063ABackend` realizing the adapter contract; continuous latched read for both modes). Built in `code/ena-dev/gui/` and verified via qt-mcp against `MY54806798`. | Claude (with Aunuun) |
