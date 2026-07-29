# E5063A Migration SPEC — LibreVNA → Keysight E5063A

**Document type:** Living spec — updated in place as work progresses.
**Created:** 2026-05-28
**Owner:** Aunuun Jeffry Mahbuubi
**Canonical companion:** `docs/project-overview.md` (LibreVNA narrative), `CLAUDE.md` (project rules)
**Dated analyses:** `docs/e5063a-20260604-sweep-rate-analysis.md` (sweep-rate vs points/IFBW/span +
the speed↔accuracy trade-off mental model for the blood-vessel monitor; open accuracy question +
next-session plan to deep-dive the `bloodvessel_monitor` CSVs)

---

## 0. Status Legend

Each section/item is marked with one of:

| Marker | Meaning |
|--------|---------|
| ⬜ **Planned** | Decided but not started |
| 🟦 **In Progress** | Actively being worked on |
| ✅ **Validated** | Done and verified against real hardware/data |
| 🟨 **Blocked** | Cannot proceed until a dependency resolves |
| ⏸ **Deferred** | Intentionally postponed |

The **Status Table** in §12 is the single source of truth; per-section markers mirror it.

---

## 1. Background & Motivation

### 1.1 Why E5063A is now in scope

The LibreVNA effort in this repository is a sweep-rate engineering study on
open-source hardware. The host-side ceiling on the LibreVNA GUI/SCPI path is
**16.95 Hz** (continuous + streaming, script 6). The legacy operating point
inherited from the previous vendor's **DataFlux** application is **20 Hz** at
±10 MHz / 801 points, and the original SRD target was **25 Hz**. LibreVNA does
not reach that target on the host SCPI path; the only remaining route is a
direct-USB driver that bypasses the GUI (theoretical ~33 Hz, not yet built).

Because the collaborator's deadline does not allow waiting on the direct-USB
work, the project is now switching primary instrument to the
**Keysight E5063A ENA Series Network Analyzer**, which already meets the 20 Hz
operating point on stock firmware and was the legacy production hardware.

### 1.2 Verified rates (source-of-truth)

From `code/LibreVNA-dev/markdown/20260205/part2-continuous-sweep-implementation.md`
and the data-sheet extract in `references/reports/20260504/E5063A_參考資料/`:

| Path | Achieved | Gap to 25 Hz |
|------|----------|--------------|
| LibreVNA — single-sweep, 0.1 s poll | 3.49 Hz | 21.51 Hz |
| LibreVNA — single-sweep, 0.01 s poll | 5.13 Hz | 19.87 Hz |
| LibreVNA — continuous + streaming (current best) | **16.95 Hz** | **8.05 Hz** |
| LibreVNA — single-sweep hot re-trigger (fragile) | 24.4 Hz | 0.6 Hz |
| LibreVNA — direct USB to firmware (not built) | ~33 Hz (est.) | — |
| **E5063A — data sheet @ 300 kHz IFBW, 1 GHz–1.2 GHz, 801 pt** | **~23 Hz** | 2 Hz |
| **E5063A — legacy DataFlux operating point (validated)** | **20 Hz** | 5 Hz |

### 1.3 Status: ✅ Background validated

---

## 2. Hardware & Connectivity

### 2.1 Instrument

| Field | Value |
|-------|-------|
| Model | Keysight E5063A ENA Series Network Analyzer |
| Serial | `MY54806798` |
| Firmware | `A.07.06` |
| OS | Windows Embedded (factory image) |

### 2.2 Host laptop

| Field | Value |
|-------|-------|
| OS | Windows 11 Pro |
| Shell | PowerShell 7+ |
| Python manager | `uv` (existing project convention) |

### 2.3 Physical connection

- **Cable:** USB Type-B (host laptop) → USB Type-B (E5063A rear panel)
- **Protocol:** USBTMC-USB488 (auto-detected, no GPIB adapter needed)
- **VISA resource string:** `USB0::0x2A8D::0x5D01::MY54806798::0::INSTR`
  - `0x2A8D` is Keysight's post-2014 USB VID. The Amp project README cites
    `0x0957` (pre-2014); both are valid Keysight VIDs and PyVISA passes the
    string through verbatim to the VISA backend.

### 2.4 VISA backend

- **Choice:** Keysight IO Libraries Suite (KIOLS) — installed on Windows 11.
- **Verification:** *IDN? round-trip through KIOLS Connection Expert returned
  `Keysight Technologies,E5063A,MY54806798,A.07.06`.

### 2.5 Status: ✅ Validated

---

## 3. Software Stack

### 3.1 Languages, frameworks, libraries

| Layer | Technology | Notes |
|-------|------------|-------|
| Language | Python 3.10+ (project floor 3.8 in existing `code/requirements.txt`; will bump to 3.10 to match Amp suite) | |
| GUI | PySide6 (Qt6) + pyqtgraph | Already used by LibreVNA script 7; reuse the binding to keep one Qt stack across the repo |
| Instrument I/O | PyVISA + pyvisa-py | PyVISA front-end is uniform; KIOLS is the active backend on Windows |
| Data | numpy, pandas, scipy, scikit-rf, matplotlib, plotly | Already in `code/requirements.txt` |
| Persistence | xlsx (LibreVNA-style multi-sheet) + Dataflux-compatible CSV (Monitor Mode parity) | |

### 3.2 Virtual environment

- **Location:** `code/.venv` (single shared venv across LibreVNA + ENA work).
- **Manager:** `uv`. Always invoke as `uv run python <script>` from `code/`.
- **State:** LibreVNA dependencies installed; **pyvisa + pyvisa-py not yet
  installed** (to add as part of §4.1).

### 3.3 Project layout

```
code/
├── LibreVNA-dev/                   ← existing LibreVNA scripts + GUI (unchanged)
├── LibreVNA-source/                ← upstream LibreVNA source (read-only)
├── ena_qt6_suite/                  ← Amp project (third-party, READ-MOSTLY)
│   ├── main.py
│   ├── core/   (visa_connection.py, base_widget.py, scpi_commands.py, simulator.py)
│   ├── apps/   (14 tools)
│   └── requirements.txt
├── ena-dev/                        ← project-owned ENA code (this is where we work)
│   ├── __init__.py
│   ├── ena_dev_paths.py            ← sys.path shim → makes core.* importable
│   ├── README.md                   ← reuse policy (must-read before adding code)
│   ├── scripts/                    (probe_e5063a, configure_e5063a, calibrate_e5063a,
│   │                                bench_e5063a_rates, bench_e5063a_realworld)
│   ├── gui/                        (qt_mcp_mockup.py; DataFlux-replacement GUI to be
│   │                                built — see gui-spec / gui-ux-spec / gui-design-system)
│   ├── notebook/                   (single-vs-continuous analysis; code/-rooted Jupyter)
│   └── data/                       (run outputs; may alias to LibreVNA-dev/data/)
└── .venv/                          ← shared uv environment
```

### 3.4 Reuse policy: BACKEND only, build our own GUI

Refined 2026-05-28. Two parts:

**Backend reuse — import, do not fork.**
`code/ena_qt6_suite/core/` is the canonical I/O layer. ena-dev imports from
it directly; we do not copy, rewrite, or fork the `core/` module. The thin
`ena_dev_paths.py` shim adds `code/ena_qt6_suite/` to `sys.path`, so any
ena-dev script can do:

```python
import ena_dev_paths  # noqa: F401  — side-effect: registers ena_qt6_suite
from core.visa_connection import ENAConnection
from core.scpi_commands import SCPI
```

**GUI: NOT reused.** The Amp suite's 14-tab Qt6 GUI (`main.py` + `apps/*`)
is **not** the user-facing tool for this migration. Reasons:

- The Amp GUI is a tool-tab "kitchen sink" inherited from 19 legacy Excel
  macros — it's structured around Keysight's sample-program taxonomy, not
  around the DataFlux/Monitor-Mode workflow we actually need.
- Building our own GUI in `code/ena-dev/gui/` lets us mirror the proven
  MVP pattern from `code/LibreVNA-dev/gui/mvp/` and ship a focused
  data-collector instead of a generic instrument-control panel.

Three resolution rules when `ena_qt6_suite/core/*.py` gets in the way:

1. **Prefer composition** — write an adapter/subclass in `ena-dev/` that
   wraps the Amp class.
2. **Patch only for real bugs** — modify `ena_qt6_suite/core/*.py` only when
   composition can't solve it.
3. **Always log patches in §13 Changelog** — so future re-syncs from the
   reference copy don't silently lose them.

This keeps the migration grounded on validated I/O code while letting us
ship a GUI shaped to the actual use case.

**Build-verify loop:** the `ena-dev/gui/` work is driven with **qt-mcp**
(agent-driven Qt inspection — "Playwright for PySide6"). The agent launches the
GUI with `QT_MCP_PROBE=1`, then reads the widget tree / clicks / screenshots /
introspects pyqtgraph scenes to confirm wiring without a manual click-through.
Validated 2026-06-02 against `code/ena-dev/gui/qt_mcp_mockup.py`. Give every
interactive widget a stable `setObjectName(...)` so the agent can find it by
name. Full guide: `docs/qt-mcp-gui-automation.md`.

### 3.5 Status: 🟦 In Progress

### 3.6 Windows VISA PATH fix (discovered 2026-05-28)

KIOLS installs `visa32.dll` / `visa64.dll` into `C:\Windows\System32`, but does
**not** add its dependent-DLL directories to the system `PATH`. Without the
fix, pyvisa's IVI backend reports:

```
pyvisa.errors.VisaIOError: VI_ERROR_LIBRARY_NFOUND (-1073807202):
    A code library required by VISA could not be located or loaded.
```

even though Connection Expert works fine (it carries its own PATH context).

**Fix (codified in `code/ena-dev/ena_dev_paths.py`):** at import time, prepend
these three directories (if they exist) to the process `PATH` and to
`os.add_dll_directory`:

```
C:\Program Files\Keysight\IO Libraries Suite\bin
C:\Program Files\IVI Foundation\IVI\Bin
C:\Program Files\IVI Foundation\VISA\VisaCom64
```

This is **transparent for callers** — any script that does
`import ena_dev_paths` gets the fix automatically; no user action required.
The fix is a no-op on non-Windows hosts.

---

## 4. Phase 1 — Amp Suite PoC Validation

### 4.1 Goal

Validate that the third-party
`references/reports/20260522/keysight-ena-e5063a-python-automation/` suite
("Amp project") works end-to-end against our E5063A. This is the cheapest
possible proof that the full PyVISA → USBTMC → SCPI chain is healthy in
Python before we invest in a custom GUI.

### 4.2 Tasks

| # | Task | Owner | Status |
|---|------|-------|--------|
| 4.2.1 | Install `pyvisa`, `pyvisa-py` into `code/.venv` via `uv pip install -r code/ena_qt6_suite/requirements.txt` | Claude | ⬜ |
| 4.2.2 | Add a `code/ena-dev/scripts/probe_e5063a.py` that lists VISA resources and queries `*IDN?` + a one-line measurement-config dump | Claude | ⬜ |
| 4.2.3 | Run the probe script, confirm `USB0::0x2A8D::0x5D01::MY54806798::0::INSTR` appears and `*IDN?` matches the §2.1 line | User + Claude | ⬜ |
| 4.2.4 | Launch `code/ena_qt6_suite/main.py`, paste the VISA address in any tool tab, connect, run one round-trip query | User | ⬜ |
| 4.2.5 | In the **Reading/Writing Data** tab, read one full S11 trace and verify point count matches `:SENS1:SWE:POIN?` | User | ⬜ |

### 4.3 Acceptance criteria

- ✅ Probe script lists the E5063A VISA address.
- ✅ `*IDN?` from Python returns `Keysight Technologies,E5063A,MY54806798,A.07.06`.
- ✅ `main.py` launches without import or Qt errors. *(launch-only — we do not
  use this GUI as a user tool, per §3.4. Reaching the main window confirms
  PySide6 + pyvisa are wired correctly in `code/.venv`.)*
- ✅ No `*ESR?` / `:SYST:ERR?` errors after the round trip.
- ⏸ Reading one S11 trace via the Amp GUI's Read/Write Data tab —
  **no longer required**. The probe already proved the SCPI roundtrip works
  via `ENAConnection`; an explicit trace read will land in Phase 2 inside our
  own GUI/script instead.

### 4.4 Non-goals (this phase)

- No custom GUI work — we are only validating the Amp suite.
- No calibration changes — accept the E5063A's current state.
- No long-run logging or rate measurement.

### 4.5 Phase 1 results (captured 2026-05-28 from live instrument)

The probe ran clean (4 OK, 0 FAIL). Captured baseline state of the instrument
**as the operator currently has it set** (not yet the migration target config):

| Field | Live value |
|-------|------------|
| `*IDN?` | `Keysight Technologies,E5063A,MY54806798,A.07.06` |
| Start freq | 50 kHz |
| Stop freq | 1.39995 GHz |
| Center freq | 700 MHz |
| Span | 1.39990 GHz |
| IF bandwidth | 70 kHz |
| Sweep points | 201 |
| Sweep type | LIN |
| Source power | -5 dBm |
| Trigger source | INT |
| Continuous trigger | ON |
| `:SYST:ERR?` | `0, "No error"` |

The 70 kHz IFBW / 201 pt setup the instrument currently has does NOT match the
migration's locked operating point (±10 MHz / 801 pt). That's expected — Phase 1
only verifies the SCPI pipe; configuration alignment happens in Phase 2/3.

### 4.6 Status: ✅ Validated. Phase 1 complete.

- S-1 … S-7b: ✅
- S-8 (Amp `main.py` launches): ✅ — user confirmed 2026-05-28, no errors.
- S-9 (read trace via Amp GUI): ⏸ Deferred — superseded by §3.4 backend-only
  reuse policy. The probe already validated the SCPI roundtrip; a real trace
  read will happen inside our own scripts/GUI in Phase 2/3.

---

## 4A. E5063A Workflow Primer (vs LibreVNA)

Captured 2026-05-28 to anchor Phase 2 design. Same conceptual workflow as
LibreVNA; the differences are where state lives and which SCPI verbs to use.

> 📖 **Full command reference:** `docs/E5063A_SCPI_Reference.md` is the
> exhaustive, categorized E5063A SCPI reference (syntax, parameters, ranges,
> query responses, workflow recipes, status/error maps). Use it as the
> authoritative working map for every SCPI verb below. (See also the source
> note in §6.7.6.)

### 4A.1 Required configuration before any measurement

Both instruments need the same four things set before SOLT calibration AND
before measurement:

| Setting | LibreVNA SCPI | E5063A SCPI | Notes |
|---------|---------------|-------------|-------|
| Start freq | `:SENSE:FREQUENCY:START <Hz>` | `:SENS1:FREQ:STAR <Hz>` | Or use center/span pair |
| Stop freq | `:SENSE:FREQUENCY:STOP <Hz>` | `:SENS1:FREQ:STOP <Hz>` | |
| Center freq | `:SENSE:FREQUENCY:CENTER <Hz>` | `:SENS1:FREQ:CENT <Hz>` | |
| Span | `:SENSE:FREQUENCY:SPAN <Hz>` | `:SENS1:FREQ:SPAN <Hz>` | |
| Sweep points | `:SENSE:SWEEP:POINTS <n>` | `:SENS1:SWE:POIN <n>` | E5063A max 1601 |
| IF bandwidth | `:SENSE:BAND <Hz>` | `:SENS1:BAND:RES <Hz>` | E5063A range 10 Hz – 300 kHz |
| Source power | `:SOURce:POWer <dBm>` | `:SOUR1:POW <dBm>` | E5063A range -45 to +10 dBm |

**Locked operating point for this migration** (per the 20260528 study):
- 801 points, 20 MHz span (±10 MHz), 300 kHz IFBW, 1-port S11.
- Frequency range is locked at **200–250 MHz** — see §4A.4.

### 4A.2 Calibration

Same SOLT concept on both instruments. Where the cal lives and how it is
loaded differs:

| | LibreVNA | E5063A |
|---|---|---|
| Cal data lives | Host-side JSON `.cal` file (e.g. `SOLT_1_2_43G-2_45G_300pt.cal`) | Onboard the instrument (Windows Embedded NVRAM) |
| Cal performed by | LibreVNA-GUI front panel, then exported to JSON | E5063A front panel **OR** SCPI sequence |
| Loaded each session via | `VNA:CAL:LOAD? <absolute_path>` SCPI query | `:MMEM:LOAD:STAT "<name>.sta"` (state file) or kept hot in active memory |
| Validity | Only for the exact Start/Stop + point count the cal was performed at | Same — only for the exact freq grid + IFBW + power used during cal |

**E5063A SCPI SOLT sequence (1-port on port 1):**
```scpi
:SENS1:CORR:COLL:CKIT 1                # select cal kit slot (front-panel-defined)
:SENS1:CORR:COLL:METH:SOLT1 1          # 1-port SOLT method on port 1
:SENS1:CORR:COLL:OPEN 1                # connect OPEN, then run this
*OPC?
:SENS1:CORR:COLL:SHORT 1               # connect SHORT, then run this
*OPC?
:SENS1:CORR:COLL:LOAD 1                # connect LOAD, then run this
*OPC?
:SENS1:CORR:COLL:SAVE                  # compute coefficients & apply
:MMEM:STOR:STYP CDST                   # save type = corrected data + state
:MMEM:STOR "myCal_233M5_801pt.sta"     # store as named state file
```

**For PoC: front-panel cal is simpler.** Operator does it once via the
E5063A's `Cal > Calibrate > 1-Port Cal` menu, saves as a state file (e.g.
`myCal_233M5_801pt.sta`), and our Python sessions just recall it:
```scpi
:MMEM:LOAD:STAT "myCal_233M5_801pt.sta"
```

This is the **default cal strategy** until §8 Phase 5 decides whether to
automate SOLT from Python.

### 4A.3 Acquisition (IFBW + points)

Identical concepts to LibreVNA. The E5063A's larger IFBW ceiling (300 kHz vs
LibreVNA's effective 50 kHz floor for max speed) is exactly the headroom
that closes the rate gap — see §6 for the full speed table and §1.2 for the
LibreVNA-vs-E5063A rate comparison.

```scpi
:SENS1:SWE:POIN 801             # 801 sweep points
:SENS1:BAND:RES 300E3           # 300 kHz IFBW
:SOUR1:POW -5                   # -5 dBm stimulus
:SENS1:SWE:TYPE LIN             # linear sweep
```

### 4A.4 Operating-point frequencies — resolved

**Decided 2026-05-28.** Matches the user's prior LibreVNA baseline at this
sensor (200–250 MHz), wider than the sensor's ±0.25 MHz resonance shifts
around 233.5 MHz so the calibration covers any sub-window we might use
later without re-cal.

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Calibration range** | **200 – 250 MHz** (50 MHz span) | Matches prior LibreVNA cal; covers any sub-window |
| Center frequency | 225 MHz | (200 + 250) / 2 |
| Default measurement window | same as cal (200–250 MHz) | Can be narrowed later without re-cal — see §4A.6 |
| Sensor of interest | resonant min S11 near 233.5 MHz, ±0.15–0.25 MHz shifts | per `docs/project-overview.md` §1 |
| Sweep points | 801 | 62.5 kHz/pt → ~4 points across the ±0.25 MHz shift |
| IF bandwidth | 300 kHz | from 20260528 study; -5 dB SNR margin at -40 dB S11 |
| Source power | -5 dBm | Matches operator's existing setup |
| Measurement | 1-port S11 | |
| Cal state file (on instrument) | `D:\State03.sta` (original ECal save, 55,894 B) **OR** `D:\MYCAL_200M_250M_801PT.STA` (canonical name, 55,879 B — uploaded from host by `configure_e5063a.py`) | Either works for `:MMEM:LOAD:STAT` |
| Cal state file (host-side reference copy) | `references/reports/20260528/myCal_200M_250M_801pt.sta` | 55,879 bytes, same content as the canonical file on instrument |

**Rate caveat:** the 20260528 study's ~33–35 Hz estimate was for a 20 MHz
span ("±10 MHz"). At 50 MHz span the LO retunes slightly more aggressively
per sweep, so realistic rate likely lands closer to **~30 Hz** instead of
35 Hz. Still well above the 20 Hz legacy DataFlux baseline. To be confirmed
empirically in Phase 3.

### 4A.5 Calibration via the Keysight **N7550A ECal module** (default)

The user has a **Keysight N7550A** USB ECal module (**DC – 4 GHz**, 2-port).
This easily covers 200–250 MHz and is now the **default calibration method**
for this migration — significantly faster and more repeatable than manual
SOLT.

#### Front-panel ECal workflow (recommended for PoC)

1. **Power on the E5063A** and let it boot fully.
2. **Set the measurement geometry FIRST** — the cal is only valid at the
   sweep settings present when it ran:
   - `[Stimulus]` → `[Start]` → `200 MHz`
   - `[Stimulus]` → `[Stop]` → `250 MHz`
   - `[Sweep Setup]` → `Points` → `801`
   - `[Avg]` → `[IF Bandwidth]` → `300 kHz`
   - `[Sweep Setup]` → `Power` → `-5 dBm`
   - `[Meas]` → `S11`
3. **Connect the N7550A**:
   - **USB:** N7550A `USB` port → any USB host on the E5063A (front or
     rear). The E5063A's status bar should show the module name after a
     few seconds (e.g. `ECal: N7550A, S/N <...>`).
   - **RF:** E5063A `Port 1` test-port cable → N7550A `Port A` (the port
     labelled `1` or `A` — check the silkscreen).
4. **Run the ECal**:
   - Press `[Cal]` on the front panel.
   - Select `ECal` → `1-Port Cal` → choose `Port 1`.
   - Confirm. The instrument cycles through Open / Short / Load states
     internally in ~10–15 seconds.
5. **Save the calibrated state**:
   - Press `[Save/Recall]` → `Save State` → choose a slot.
   - Filename: `myCal_200M_250M_801pt` (the `.sta` extension is added
     automatically).
6. **Sanity-check**: with the ECal still connected, the trace should read
   ~0 dB return loss across 200–250 MHz (the ECal's Load standard is a
   well-matched 50 Ω, so the corrected measurement reads near 0 dB).
   Disconnect the ECal and connect the DUT (biomedical sensor) for real
   measurements.

#### SCPI ECal workflow (for later automation)

Equivalent to front-panel, driven from Python. Requires the N7550A
plugged in via USB to the E5063A.

```scpi
# 1. Geometry FIRST (must match what you measure later)
:SENS1:FREQ:STAR 200E6
:SENS1:FREQ:STOP 250E6
:SENS1:SWE:POIN 801
:SENS1:BAND:RES 300E3
:SOUR1:POW -5
:CALC1:PAR:COUN 1
:CALC1:PAR1:DEF S11
:CALC1:PAR1:SEL

# 2. Run 1-port ECal on port 1 (instrument auto-detects N7550A)
:SENS1:CORR:COLL:ECAL:SOLT1 1
*OPC?                                    # blocks ~10–15 s

# 3. Save state file
:MMEM:STOR:STYP CDST                     # save type = state + corrected data
:MMEM:STOR "myCal_200M_250M_801pt.sta"

# 4. Sanity-check
:SYST:ERR?                               # expect 0,"No error"
```

Recall in any future session:
```scpi
:MMEM:LOAD:STAT "myCal_200M_250M_801pt.sta"
```

#### Manual SOLT (fallback only)

If the N7550A is unavailable, see §4A.2 for the open/short/load sequence.
Not the default path.

### 4A.6 What requires re-cal vs what can change freely

Calibration is performed at 200–250 MHz / 801 pts / 300 kHz IFBW / -5 dBm.
Changing some parameters afterwards invalidates the cal; others don't.

| Change | Re-cal needed? | Notes |
|--------|---------------|-------|
| Start / Stop / Span (frequency grid changes) | ✅ Yes — or enable interpolation | See §4A.6.1 |
| Sweep points | ✅ Yes (grid changes) | |
| Sweep type (LIN / LOG / SEG) | ✅ Yes | |
| Source power | ⚠ Small steps (≤ ±2 dB) usually fine | Larger changes affect source match |
| **IF bandwidth (IFBW)** | ❌ **No** | Affects noise floor only, not systematic errors. **Change freely at runtime.** |
| Trace format (MLOG / PHASE / SMITH / etc.) | ❌ No | Display-only |
| Display on/off | ❌ No | |
| Trigger source / mode | ❌ No | |
| Number of traces | ❌ No | |

**Practical takeaway:** IFBW is the runtime speed-vs-noise knob. The monitor
app may expose it as a user-changeable setting (e.g. 300 kHz for live
logging, 1 kHz for occasional precision sweeps) without invalidating cal.
The +10 dB-noise-floor / +5 dB-trace-noise per decade scaling from the
20260528 study still applies; cal-corrected mean values remain accurate.

#### 4A.6.1 Sub-window measurement via cal interpolation

To measure a narrower sub-window (e.g. zooming into 232–234 MHz for the
resonance neighbourhood) without re-calibrating, enable cal interpolation:

```scpi
:SENS1:CORR:INT ON                       # enable interpolation
:SENS1:FREQ:STAR 232E6                   # narrower window
:SENS1:FREQ:STOP 234E6
```

The E5063A interpolates the original cal coefficients onto the new
frequency grid. Trades a small amount of cal accuracy (typically a few dB
at the corners of the new window) for the convenience of switching
sub-windows. For high-precision work, prefer re-cal at the exact target.

### 4A.7 Trigger modes — E5063A vs LibreVNA

Same three logical modes on both instruments; the front-panel labels and
SCPI verbs differ. The user's prior LibreVNA "continuous" benchmark runs
(`code/LibreVNA-dev/markdown/20260205/part2-continuous-sweep-implementation.md`,
16.95 Hz figure) map exactly to E5063A "Continuous" mode.

| Concept | E5063A menu | E5063A SCPI | LibreVNA menu | LibreVNA SCPI |
|---------|-------------|-------------|---------------|---------------|
| **Continuous** — sweep, restart, repeat forever | `Continuous` | `:INIT1:CONT ON` + `:TRIG:SOUR INT` | `Continuous` | `:ACQ:SINGLE FALSE` (`Run`) |
| **Single** — one sweep then stop | `Single` (one-shot, returns to Hold) | `:INIT1:CONT OFF` + `:INIT1:IMM` per sweep | `Single` | `:ACQ:SINGLE TRUE` + `:ACQ:RUN` per sweep |
| **Hold** — stopped, no sweep in progress | `Hold` | `:ABOR` (or `:INIT1:CONT OFF` without `:INIT:IMM`) | implicit — "Stop" / pause | `:ACQ:STOP` |

The Phase 3 bench script (`bench_e5063a_rates.py`) uses BUS-triggered
single sweeps under the hood (Variants A–D), which on the E5063A is the
cleanest host-paced pattern. Continuous-mode benchmarking (Variant E) is
deferred — see §6.5.

The user's LibreVNA workflow that produced the 16.95 Hz figure
(`code/LibreVNA-dev/markdown/20260205/`) ran in LibreVNA "Continuous"
mode with the streaming TCP callback on port 19001. The equivalent
real-world test on E5063A would use `:INIT1:CONT ON` + `:TRIG:SOUR INT`
with a per-sweep sync (currently deferred, see §6.5). For the headline
rate validation the host-paced single-sweep path is cleaner and gives a
better-controlled benchmark.

## 5. Phase 2 — DataFlux / Monitor Mode Replacement

### 5.1 Goal

Replace the legacy DataFlux / DataAnalysis 2025 web app with a Qt6 desktop
application that runs on Windows. Feature parity is mandatory; UI improvements
(file prefix, progress bar, time-aware input) carry over from the LibreVNA
Monitor Mode work in `code/LibreVNA-dev/gui/`.

#### 5.1.1 Why the E5063A — the log-interval headroom (the *real* objective)

Source: `REPORT/20260226/20260205.pdf` (Jeffry's 2026-02-26 presentation on the
LibreVNA "Data Collector" GUI), parsed 2026-06-02. The end goal of this whole
migration is **Continuous / Monitor mode**: the tool logs, over time, the
**per-sweep minimum-S11 frequency** (Hz) and its magnitude (dB) — a Dataflux-style
scalar time series — to monitor a research-institute **blood-vessel prototype** for
continuous monitoring / early detection.

The monitoring sample rate is **hard-floored by the mean sweep time**:
`log_interval_ms` cannot be faster than one sweep (you can't log a fresh min-freq
before a new sweep completes). So **monitor-rate ceiling = 1 / mean sweep time.**
At the locked 200–250 MHz / 801-pt operating point this is exactly where the E5063A
pays off, because its sweep is ~4–6× faster than the LibreVNA's:

| Instrument / mode (200–250 MHz, 801 pt, S11) | Mean sweep | Min log-interval | Monitor ceiling | 60 s points |
|---|---|---|---|---|
| LibreVNA (report figure) | ~140 ms | ~140 ms | **~7 Hz** | ~400 |
| E5063A single, 50 kHz IFBW | 42.4 ms | 42 ms | ~23.6 Hz | ~1,415 |
| E5063A single, 300 kHz IFBW | 30.3 ms | 30 ms | ~33.0 Hz | ~1,980 |
| E5063A continuous, 50 kHz IFBW | 38.1 ms | 38 ms | ~26.2 Hz | ~1,575 |
| E5063A continuous, 300 kHz IFBW | 25.4 ms | 25 ms | **~39.3 Hz** | ~2,360 |

**Result: the E5063A lifts the Monitor-mode ceiling from ~7 Hz to ~26–39 Hz — a
~3.7–5.8× improvement at the same range/points/cal**, moving cardiovascular/pulse
monitoring from "barely Nyquist" to comfortable oversampling. The recommended Monitor
operating point is **IFBW ≥ 50 kHz** (keeps ≥20 Hz logging *and* ample dynamic range
for the resonant notch). Empirical sweep-time data: `code/ena-dev/data/20260602/`
(both `single_*` and `continuous_*` `..._124432.xlsx`); cross-mode analysis notebook:
`code/ena-dev/notebook/1_single_vs_continuous_sweep_e5063a.ipynb`.

### 5.2 Functional requirements (from collaborator handover §4.3–§4.4)

| ID | Requirement | Source |
|----|-------------|--------|
| F-1 | Configurable VNA address (USB/LAN/GPIB) | DataFlux v1 |
| F-2 | Editable file-name prefix | DataAnalysis 2025 |
| F-3 | Query interval (20–1000 ms) | DataAnalysis 2025 |
| F-4 | Query duration (hours) → auto-derive query number | DataAnalysis 2025 |
| F-5 | Query number (1–100000) | DataFlux v1 |
| F-6 | Scientific-notation toggle for CSV | DataAnalysis |
| F-7 | History list with multi-select delete + zip download | DataAnalysis 2025 |
| F-8 | Live progress bar + remaining-time estimate | SRD feedback |
| F-9 | Per-record metadata: Model, Serial, Date, Time, Log Points, Log Interval(ms), Start/Stop/Span/IF Bandwidth/Points | DataFlux v1 |
| F-10 | Output: CSV that loads in `code/LibreVNA-dev/scripts/8_plot_monitor_data.py` without conversion | Repo continuity |

### 5.3 Non-functional requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| NF-1 | Sustained ≥ 20 Hz logging at ±10 MHz / 801 pt | Legacy operating point |
| NF-2 | 60-min run stability without timing drift > 1 % | SRD feedback (delayed-vs-hung problem) |
| NF-3 | Windows-first; no Docker or Linux deployment | Aligns with current host |
| NF-4 | All SCPI runs on a QThread; GUI stays at 60 fps | Repo convention from script 7 |
| NF-5 | Output CSV header byte-identical to `vna_monitor_*.csv` format already produced by Monitor Mode | Cross-tool compatibility |

### 5.4 Architectural sketch

- Reuse `ena_qt6_suite/core/visa_connection.py` (`ENAConnection`) as the I/O
  primitive — wrap, do not rewrite. If patches are needed, push them upstream
  via PR or keep them as a small adapter in `ena-dev/`.
- Mirror the MVP pattern from `code/LibreVNA-dev/gui/mvp/` (Model, View,
  Presenter). The presenter owns one `VNAMonitorWorker(QThread)` and one
  optional `VNAPreviewWorker(QThread)`.
- Persist runs to `code/LibreVNA-dev/data/YYYYMMDD/` (single data root for the
  whole repo) under filenames `e5063a_monitor_YYYYMMDD_HHMMSS.csv`.

> **The detailed implementation plan for this phase lives in its own document:
> [`docs/e5063a-gui-spec.md`](./e5063a-gui-spec.md)** — port-vs-replace file map,
> backend-swap design, Monitor-mode UI, threading model, qt-mcp verify loop, and a
> phased build plan with its own status table. This migration spec remains the
> *validated foundation* (hardware, SCPI, sweep-rate, cal, data format) that the GUI
> spec builds on. Requirements F-1…F-10 / NF-1…NF-5 above are the contract the GUI
> spec implements.

### 5.5 Status: ✅ COMPLETE — **GUI built (G-0…G-15) + packaged (G-6 `.exe`)** in `code/ena-dev/gui/`, all live-validated against the instrument. Details + phase status in `docs/e5063a-gui-spec.md`; packaging in `docs/e5063a-packaging.md`. (Post-G-5 work 2026-06-04: G-12 monitor Y-axis toggle, G-13 live S11 trace preview + display modes, G-14 WTMH lab branding, G-15 cal file-listing bug fix, G-6 standalone `.exe`.)

---

## 6. Phase 3 — Sweep Rate Validation

### 6.1 Goal

Empirically confirm the E5063A's sweep-rate ceiling at the locked operating
point (±10 MHz / 801 pt, 1-port S11), and lock in the configuration that
sustains ≥ 20 Hz under USBTMC.

### 6.2 Target rate (revised 2026-05-28)

The internal study at
`references/reports/20260528/e5063a-speed-potential-and-ifbw-tradeoff.md`
re-derived the speed ceiling from the Keysight data-sheet throughput table
(interpolated to 801 pt, narrow span):

| IFBW | Instrument ceiling | Realistic end-to-end |
|------|--------------------|----------------------|
| **300 kHz** | **~42 Hz** | **~33–35 Hz** ✅ Recommended |
| 30 kHz | ~21 Hz | ~19–20 Hz (matches legacy DataFlux) |
| 1 kHz | ~1.27 Hz | ~1.3 Hz |

The "realistic" column is after the loss budget (display off, binary
`REAL32` + `SWAP`, no per-sweep `*OPC?` round trip). Key SCPI knobs that
deliver this performance:

```scpi
:SENS1:BAND:RES 300E3       # IFBW = 300 kHz (the speed lever)
:FORM:DATA REAL32           # binary IEEE-754 floats, not ASCII
:FORM:BORD SWAP             # little-endian (host PC byte order)
:DISP:ENAB OFF              # disable display rendering during logging
:CALC1:PAR:COUN 1           # single S11 trace
:TRIG:SOUR BUS              # host-paced single sweeps
:INIT1:CONT OFF             # no free-running sweeps
```

For the antenna-match use case (S11 -10 to -40 dB), 300 kHz IFBW gives ~45 dB
SNR margin and ~0.002 dB trace-noise rms — well below the 0.01 dB
"transparent" threshold. **The dynamic-range cost of running at 300 kHz IFBW
is acceptable** (per §4 of the 20260528 study). This validates 300 kHz as the
default target IFBW for the new monitor app.

### 6.3 Method

- Sweep configuration: 801 points, 20 MHz span centered at the antenna-match
  frequency (TBD per use case, e.g. 2.44 GHz), 300 kHz IFBW (variant B).
- Variants to run, in order:
  - **A. ASCII baseline** (`:FORM:DATA ASC`) — confirm binary helps.
  - **B. Binary 300 kHz** (above) — headline number, target ~33–35 Hz.
  - **C. Binary 30 kHz** — replicate legacy DataFlux 20 Hz baseline.
  - **D. Binary 1 kHz** — confirm deep-DR-mode floor.
  - **E. Continuous + paced reads** — see §3.7 of the 20260528 study.
- Measurement: ≥ 200 sweeps each, host-side timestamps in ns, discard the
  first sweep as cold-cache.
- Output: per-variant mean / median / p95 / p99 inter-sweep deltas.

### 6.4 Acceptance

- Variant B sustains ≥ 30 Hz mean over a 60-second window.
- Variant C lands within ±10 % of 20 Hz (legacy DataFlux verification).
- p99 inter-sweep delta ≤ 1.5 × mean (no severe stragglers).
- 60-min run at variant B completes with no SCPI errors and timing drift ≤ 1 %.

### 6.5 Phase 3 results (captured 2026-05-28 from live instrument)

`code/ena-dev/scripts/bench_e5063a_rates.py` ran 200 sweeps per variant at
200–250 MHz / 801 pt with cal active. Raw data:
`code/ena-dev/data/20260528/bench_e5063a_20260528_144325.{json,csv}`.

| Variant | IFBW | Format | Measured rate | Expected | ΔT mean / p99 | p99/mean | Verdict |
|---------|------|--------|---------------|----------|---------------|----------|---------|
| **A** | 300 kHz | ASCII | **21.68 Hz** | 12–28 Hz | 46.1 / 48.0 ms | 1.04 | ✅ |
| **B** | 300 kHz | REAL32 | **32.70 Hz** | 25–38 Hz | 30.6 / 35.7 ms | 1.17 | ✅ Headline |
| **C** | 30 kHz | REAL32 | **18.57 Hz** | 15–22 Hz | 53.9 / 60.6 ms | 1.13 | ✅ |
| **D** | 1 kHz | REAL32 | **1.26 Hz** | 1.0–1.6 Hz | 796 / 800 ms | 1.00 | ✅ |
| E | 300 kHz | REAL32 (continuous) | 2.48 Hz | n/a | 404 / 1475 ms | 3.65 | ⚠ Polling-bound — see below |

**Key findings:**

- **The migration target (≥ 20 Hz) is comfortably met** at 300 kHz IFBW with
  binary REAL32 transfer: **32.7 Hz mean**, p99 jitter only 17% above mean,
  zero SCPI errors. Almost double the legacy DataFlux 20 Hz baseline.
- The 30 kHz / DataFlux-style operating point (variant C, 18.6 Hz) confirms
  the legacy ~20 Hz figure is correct for that IFBW setting.
- ASCII (variant A) costs ~33% vs binary, not 3× as the 20260528 study
  worst-cased. Either acceptable in practice if binary support is hard.
- All single-sweep variants A–D show **very low jitter** (p99/mean ≤ 1.17)
  and clean error queues — no race conditions or stragglers at the trigger
  layer.

**Operational decision:** the new monitor app will run at **variant B**
(300 kHz IFBW, REAL32 binary, BUS-triggered single sweeps) by default.
IFBW is exposed as a runtime knob per §4A.6, allowing the user to drop to
30 kHz or 1 kHz for higher-precision occasional sweeps without re-cal.

**Variant E note (continuous + polling — deferred):**
The script uses `:STAT:OPER:COND?` polling to detect sweep-complete events.
Each `:STAT:OPER:COND?` is a USBTMC round trip (~1 ms); at the 200 µs
poll interval used, each measured sweep period accumulates 100+ polls
worth of round-trip overhead, dominating the timing. The instrument is
actually sweeping at its native ~42 Hz rate underneath — the bench just
can't measure it accurately with this method. The correct approach is
SRQ-based event signalling (`*SRE`/`*ESE` + `viWaitOnEvent`), which
pyvisa-py has limited support for; **deferred** until needed. Variant E
stays in the script (excluded from default suite) for future revisit.

**SCPI trigger pattern (gotcha worth recording):**
On the E5063A at this firmware (`A.07.06`), the only host-paced single-sweep
pattern that fires reliably is:

```scpi
:TRIG:SOUR BUS
:INIT1:CONT OFF
:ABOR

# per sweep:
:INIT1:IMM         # arm trigger system (transitions to wait-for-trigger)
:TRIG:SING         # software trigger (fires the sweep)
*OPC?              # blocks until sweep complete
:CALC1:DATA:FDAT?  # read trace
```

A first attempt with `:TRIG:SOUR INT + :INIT1:IMM + *OPC?` (the pattern
suggested in the 20260528 doc §3.4) produced impossibly high rates and
"Init ignored" errors — the cleaner BUS+SING pattern was needed. See the
benchmark script for the full implementation.

### 6.6 Status: ✅ Validated — all four single-sweep variants meet expected ranges; variant E deferred

#### 6.6.1 Phase 3 re-confirm run (2026-05-28 15:44)

A second Phase 3 run on the same day, post-context-clear, re-confirmed variants
A–D in the same expected ranges. No new information beyond §6.5, but recorded
here so future readers don't wonder about the extra
`code/ena-dev/data/20260528/bench_e5063a_20260528_154404.{json,csv}` files.

| Variant | 15:44 rate | 14:43 rate (canonical) | Notes |
|---------|-----------:|-----------------------:|-------|
| A (300 kHz, ASCII)  | 21.19 Hz | 21.68 Hz | 15:44 error queue **not** clean: "Query INTERRUPTED" — likely a residual from the preceding session, doesn't change the headline conclusion |
| B (300 kHz, REAL32) | 31.71 Hz | 32.70 Hz | both clean |
| C ( 30 kHz, REAL32) | 18.48 Hz | 18.57 Hz | both clean |
| D (  1 kHz, REAL32) |  1.26 Hz |  1.26 Hz | both clean |

The **14:43 numbers remain the canonical Phase 3 result** quoted in §6.5.

### 6.7 Phase 3 follow-up — real-world IFBW benchmark (S-12c, pending execution)

#### 6.7.1 Goal

Mirror the LibreVNA `REPORT/20260205/20260205.pdf` methodology on the E5063A
at the locked operating point (200–250 MHz / 801 pt). Produce two xlsx
workbooks (one per mode) that are **byte-compatible with the LibreVNA report
templates** so the user's existing report-generation pipeline works
unchanged.

#### 6.7.2 Methodology (decided 2026-05-28 via user-confirmed options)

| Decision | Value | Rationale |
|----------|-------|-----------|
| Frequency range | 200–250 MHz / 801 pt | Matches the active ECal — no re-cal needed |
| IFBW set | **8 values**: 300, 150, 125, 100, 75, 50, 10, 1 kHz | 7 LibreVNA-comparable values + 300 kHz (E5063A headline) |
| Modes | Both **Single** + **Continuous** | Matches LibreVNA REPORT side-by-side comparison |
| Sweeps per IFBW | 30 | Matches LibreVNA convention |
| Trace format | REAL32 + SWAP, MLOG | Phase 3-proven binary path |
| Continuous-mode sync | `:STAT:OPER:EVEN?` latched poll on bit 4 (Measuring), with `:STAT:OPER:NTR 16` + `:STAT:OPER:PTR 0` so end-of-sweep is the latch trigger | Avoids the missed-event problem of the `:STAT:OPER:COND?` polling that broke variant E in §6.5 |
| Single-mode trigger | BUS + INIT:IMM + TRIG:SING + *OPC? | Same proven Phase 3 pattern |

#### 6.7.3 Computed metrics (matching LibreVNA REPORT xlsx schema)

For each IFBW × mode the bench captures per-sweep wall-clock timing and the
full S11 trace, then derives:

| Metric | Formula |
|--------|---------|
| Mean Sweep Time (s, ms) | arithmetic mean of per-sweep wall-clock duration |
| Std Dev (s)             | population std-dev of per-sweep wall-clock |
| Min / Max (s)           | extremes across the 30 sweeps |
| Update Rate (Hz)        | 1 / mean_sweep_time |
| **Noise Floor (dB)**    | arithmetic mean of S11 across all (sweep, point) pairs |
| **Trace Jitter (dB)**   | mean over points of *population std-dev across sweeps* |

These two metric definitions were reverse-engineered from
`REPORT/20260205/continuous_sweep_test_20260205_230028.xlsx` and verified to
reproduce the LibreVNA Summary-sheet values (–50.4 dB / 1.57 dB at
IFBW=150 kHz).

#### 6.7.4 Output xlsx schema

Two workbooks per run: `single_sweep_test_e5063a_YYYYMMDD_HHMMSS.xlsx` and
`continuous_sweep_test_e5063a_YYYYMMDD_HHMMSS.xlsx` in
`code/ena-dev/data/YYYYMMDD/`.

Each workbook contains:

- **`Summary` sheet** — 10 cols: `Mode`, `IFBW (kHz)`, `Mean Time (s)`,
  `Mean Time (ms)`, `Std Dev (s)`, `Min Time (s)`, `Max Time (s)`,
  `Rate (Hz)`, `Noise Floor (dB)`, `Trace Jitter (dB)`. One row per IFBW.
- **`IFBW_<n>kHz` sheets** — 8 per workbook. Each has four labeled blocks:
  - **Configuration** (R1–9): Mode, IFBW, Start, Stop, Points, STIM Level,
    Avg Count, Num Sweeps.
  - **Timing** (R10–41 for N=30): Sweep #, Sweep Time (s), Sweep Time (ms),
    Update Rate (Hz).
  - **S11 Traces** (R43 onward): header `Frequency (Hz) | Sweep_1 S11 (dB)
    | ... | Sweep_N S11 (dB)`, then `Points` data rows.
  - **Metrics** (last 2 rows): Noise Floor (dB), Trace Jitter (dB).

The block structure exactly mirrors
`REPORT/20260205/{single,continuous}_sweep_test_20260205_*.xlsx`.

#### 6.7.5 Implementation

`code/ena-dev/scripts/bench_e5063a_realworld.py` (480 lines, syntax-checked
2026-05-28). CLI:

```bash
# Pre-req (recall cal + pin operating point):
uv run python ena-dev/scripts/configure_e5063a.py

# Full real-world bench (both modes × 8 IFBW × 30 sweeps, ~2 min):
uv run python ena-dev/scripts/bench_e5063a_realworld.py

# Smoke test first if any SCPI/format doubts:
uv run python ena-dev/scripts/bench_e5063a_realworld.py --ifbw 300 --n-sweeps 5 --modes continuous

# Other knobs:
uv run python ena-dev/scripts/bench_e5063a_realworld.py --modes continuous
uv run python ena-dev/scripts/bench_e5063a_realworld.py --ifbw 300,50,1
uv run python ena-dev/scripts/bench_e5063a_realworld.py --no-save
```

**Filename caveat:** the new script is `bench_e5063a_realworld.py`, not
`bench_e5063a_rates.py` (the older Phase 3 script). Tab-completion on
`bench_` will offer both — pick the right one.

#### 6.7.6 SCPI verbs requiring authoritative verification

> ⛔ **Reference correction (2026-06-02):** an earlier version of this section
> named `references/reports/20260528/9018-07931_E5063A_SCPI_Command_Reference.pdf`
> as the "authoritative reference." **That PDF is NOT an E5063A document — it is
> the Agilent 4155B/4156B Semiconductor Parameter Analyzer SCPI manual,
> mislabeled.** (Confirmed: its extracted pages `code/ena-dev/scpi_ch4_test.txt`
> are verbatim 4155B/4156B content.) **All copies were deleted 2026-06-02**
> (under `20260504/.../official_docs/`, `20260528/`, the extracted-page chunks,
> and `code/ena-dev/scpi_ch4_test.txt`); do not re-download. The current SCPI
> ground truth for the E5062A/E5063A family is:
> - `references/reports/20260602/E5062A_Programmers_Guide_E5061-90042_Part*.pdf` — E5062A/E5061 Programmer's Guide (sibling instrument, shared SCPI tree; Ch.13 full command reference).
> - `references/reports/20260522/keysight-ena-e5063a-python-automation/` — working PyVISA E5063A control suite (= `code/ena_qt6_suite/`).
> - `references/reports/20260504/E5063A_參考資料/` — E5063A cheat-sheet + DataFlux notes (**but ignore its `official_docs/9018-07931…pdf`** — same bogus 4155B file).
> - `docs/E5063A_SCPI_Reference.md` — the consolidated working map built from the three sources above.

The script is based on Keysight ENA conventions + patterns proven in
`bench_e5063a_rates.py`. Verification status against the corrected ground
truth above (`docs/E5063A_SCPI_Reference.md`, sourced from the E5062A
Programmer's Guide):

- `:CALC1:DATA:FDAT?` returning 2×N floats for MLOG (primary, secondary pairs) — **confirmed** (E5062A guide Ch.7 / `docs/E5063A_SCPI_Reference.md` §4).
- `:SENS1:FREQ:DATA?` returning N floats (Hz) for the stimulus axis — **confirmed** (guide / §4, §6).
- `:STAT:OPER:NTR` / `:PTR` transition filters + `:EVEN?`/`:COND?` edge-latched poll — **confirmed** as the documented free-run sweep-completion pattern (`docs/E5063A_SCPI_Reference.md` §8.19).
- `:STAT:OPER` **bit-4 = "Measuring"** (the exact bit weight) — **CONFIRMED 2026-06-02** against the now-complete consolidated reference (`docs/E5063A_SCPI_Reference.md` §8.19 / §7, sourced from the E5062A Programmer's Guide): bit 4 = Measuring (1 during sweep), end-of-sweep = bit-4 1→0; `:STAT:OPER:NTR` preset 0, `:PTR` preset 16432. The bench's `setup_mode_continuous` (`:STAT:OPER:NTR 16` + `:PTR 0` + poll `:STAT:OPER:EVEN?` for the 0x10 latch) exactly matches the documented end-of-sweep negative-transition latch, so the continuous-mode SCPI is correct. **All four §6.7.6 verbs are now verified.** Remaining work is purely a live continuous-mode *run* (the SCPI itself is no longer in doubt).

The documented SRQ-driven alternative is `:STAT:OPER:NTR 16` + `:STAT:OPER:ENAB 16`
+ `*SRE 128` then `viWaitOnEvent`; the bench's direct `:EVEN?` polling is a valid
simpler equivalent (ENAB/`*SRE` are only needed for true SRQ waits). If anything
still misbehaves on the first live continuous run, the fallback is the
`:STAT:OPER:COND?` edge-detection pattern from `bench_e5063a_rates.py` variant E.

#### 6.7.7 Status: ✅ Validated — **both single + continuous modes validated live 2026-06-02.**

Continuous-mode run executed on hardware (E5063A `MY54806798`, A.07.06, cal
active, 200–250 MHz / 801 pt / S11 / −5 dBm, REAL32). Full 8-value IFBW set ×
30 sweeps, clean error queue on every IFBW, latched `:STAT:OPER:EVEN?` bit-4
sync worked first time (no fallback to the variant-E `:COND?` pattern needed).
Output: `data/20260602/continuous_sweep_test_e5063a_real32_20260602_121928.xlsx`.

**Continuous-mode IFBW → rate curve** (mean of 30 sweeps each):

| IFBW (kHz) | 300 | 150 | 125 | 100 | 75 | 50 | 10 | 1 |
|------------|-----|-----|-----|-----|----|----|----|---|
| Rate (Hz)  | 39.54 | 35.75 | 35.78 | 32.81 | 29.66 | 26.24 | 10.04 | 1.26 |
| Mean (ms)  | 25.29 | 27.97 | 27.95 | 30.48 | 33.72 | 38.10 | 99.64 | 791.68 |

Noise floor −1.64 dB and trace jitter ≤ 0.004 dB across all IFBW (identical to
single mode — continuous polling does not degrade trace quality).

**Single vs continuous (apples-to-apples, REAL32, overlapping IFBW from S-12g):**

| IFBW (kHz) | Single (Hz) | Continuous (Hz) | Gain |
|------------|-------------|-----------------|------|
| 100 | 28.55 | 32.81 | +15% |
| 75  | 26.10 | 29.66 | +14% |
| 50  | 23.02 | 26.24 | +14% |

Continuous mode buys a **steady ~14–15% rate gain** in the overlap region
(~+25% at the 300 kHz head vs Phase-3 single Variant B's 31.71 Hz). This is the
expected **modest** improvement — nothing like LibreVNA's 3–5× single→continuous
jump, because the E5063A single path is already host-paced and efficient. The
≥30 Hz operating point is now reachable in continuous mode down to ~100 kHz IFBW
(32.8 Hz), vs single mode topping out at ~28.5 Hz @ 100 kHz.

### 6.8 Phase 3 follow-up — points × IFBW × span sweep-rate map (2026-06-04)

Extends the fixed-801pt benchmarks to a full **number-of-points (101→1001) × IFBW
(1→300 kHz)** grid plus a frequency-span comparison, collected from the GUI's
Device Sanity-Check mode. Dataset: `REPORT/20260604/20260604/` (11 sanity `.xlsx`
+ 2 `bloodvessel_monitor` CSVs). Full write-up + figures:
`docs/e5063a-20260604-sweep-rate-analysis.md`; notebook
`code/ena-dev/notebook/2_sweep_rate_vs_config_e5063a.ipynb`.

- **Sweep-time model** (fit, R²=0.99997): `t_sweep(N,IFBW) ≈ 4.64 + N·(0.0230 +
  0.959/IFBW_kHz)` ms; `rate = 1000/t_sweep`. Predicts the rate of ANY untested
  (points, IFBW); consistent at N=801 with the older `≈ 25 + 869/IFBW` model.
- **Span is a small secondary effect** (not first-order): at 801 pt the 20 MHz
  span ran ~7% faster on average than 50 MHz (confounded by ~10% host-VISA
  jitter). First-order rate is set by **points × IFBW** (~30× range).
- **Operating map** (200–250 MHz): 801pt/300kHz = 39.5 Hz (clears 30 Hz at the
  finest grid tested); 801pt/50kHz = 26.1 Hz (clears 25 Hz, more DR margin).
  Noise floor flat (~0.017 dB) across IFBW; jitter rises with IFBW.

**Accuracy trade-off + OPEN question (carry forward).** The frequency precision of
the logged min-S11 notch = point spacing **Δf = span/(N−1)** under the current raw
**argmin** min-search (all GUI paths). For a **localised** dip, narrowing the span
is the *free* accuracy lever (finer Δf + slightly faster) — adding points only
costs speed. Parabolic 3-point interpolation (decouples precision from N) was
prototyped this session then **deferred** (no code change adopted). **OPEN:** is
higher frequency accuracy actually needed? Decisive ratio = physiological min-freq
excursion ÷ Δf. **Next session:** deep-dive the two `bloodvessel_monitor` CSVs
(notebook 3) to answer it — plan in the dated doc §7 + memory
`project-e5063a-bloodvessel-accuracy-tradeoff`.

#### 6.8.1 Status: ✅ Analyzed (sweep-rate map + model); ⬜ accuracy question OPEN (next-session bloodvessel deep-dive)

---

## 7. Phase 4 — Data Format Compatibility

### 7.1 Goal

CSV produced by the new Monitor-Mode-equivalent on E5063A must be a drop-in
replacement for the LibreVNA Monitor Mode CSV consumed by
`code/LibreVNA-dev/scripts/8_plot_monitor_data.py`.

### 7.2 Schema (target)

12 metadata lines + 2 blank + 1 header line + N data rows. Metadata mirrors
LibreVNA `vna_monitor_*.csv` exactly:

```
Model, Serial, Date, Time, Log Points, Log Interval(ms), Start, Stop, Span,
IF Bandwidth, Points, (one reserved field)
```

(Exact byte layout to be captured by reading a current LibreVNA Monitor Mode
CSV and replicating the line ordering.)

### 7.3 Status: ⬜ Planned

---

## 8. Phase 5 — Calibration Strategy

### 8.1 Default strategy (decided 2026-05-28, revised same day)

**Default = ECal (Keysight N7550A) + state-file recall.** The operator runs
1-port ECal once via the E5063A's `Cal > ECal > 1-Port Cal` menu at the
locked operating point (200–250 MHz / 801 pt / 300 kHz IFBW / -5 dBm /
S11), then saves it as `myCal_200M_250M_801pt.sta`. Our Python sessions
recall it via `:MMEM:LOAD:STAT "myCal_200M_250M_801pt.sta"`.

Full workflow in §4A.5. Manual SOLT (§4A.2) is the fallback if the N7550A
is unavailable.

**✅ Host-driven ECal validated 2026-06-02 (S-18).** The front-panel step is
**no longer required** — `code/ena-dev/scripts/calibrate_e5063a.py` performs the
full 1-port S11 ECal from the host over USBTMC: set geometry → detect module
(`:SENS1:CORR:COLL:ECAL:PATH? 1` = `+1`) → `:SENS1:CORR:COLL:ECAL:SOLT1 1` +
`*OPC?` (module self-measures O/S/L, computes, auto-enables) → verify
`:CORR:STAT?`/`:CORR:TYPE1?` → confidence sweep → save a grid-named `.sta`
(`:MMEM:STOR:STYP CST`). Ran 14/14 OK on `MY54806798`, and the saved
`D:\cal_S11_200-250MHz_801pt.sta` round-trips through `configure_e5063a.py`
(16/16 OK). This makes the GUI a true **one-stop Configure + Calibrate + Sanity
Check + Continuous Measure** tool — the dynamic-experiment workflow the
collaborator asked for (change grid → re-cal from host, all in-app).

> **Re-cal trigger clarification (important for the dynamic workflow):** changing
> **IFBW does NOT require a re-cal** (§4A.6 — it only shifts the noise floor).
> Only **frequency-grid changes (start/stop/points/sweep-type)** force a re-cal.
> So during experimentation IFBW is a free runtime knob; ECal only needs to fire
> when start/stop/points change.

### 8.2 Future automation options (still on the table)

| Option | Pros | Cons | When to consider |
|--------|------|------|-------------------|
| **SCPI-automated SOLT** | Reproducible; no operator drift | Need operator to physically swap O/S/L between SCPI commands anyway | When the rig is dedicated and cal needs to be re-run from scripts |
| **ECal module** | Fully automated, repeatable, fast | Requires the physical ECal module | If we acquire one |
| **Software de-embedding via scikit-rf** | Cal data lives in repo (consistent with LibreVNA JSON flow) | Most work; needs scikit-rf integration + Touchstone management | If state-file management on the instrument becomes a pain point |

### 8.3 Status: ✅ Default decided; deeper options deferred

---

## 9. Non-Goals (intentional)

- **Maintain LibreVNA path in parallel after E5063A is production-validated.**
  LibreVNA work remains in the repo as a reference and may resume if the
  direct-USB driver is built later. No active development on the LibreVNA path
  during this migration.
- **Linux / Docker deployment.** The legacy host was Linux + Docker on a MSI
  Cubi NUC. The new host is Windows 11 (this laptop), so all tooling targets
  Windows first.
- **Web UI (Streamlit-style).** DataFlux was browser-based; we are replacing
  it with a Qt6 desktop GUI to match the rest of the repo.
- **Multi-vendor abstraction.** No attempt to make code instrument-agnostic.
  E5063A-specific SCPI is acceptable.

---

## 10. Open Questions / Risks

| ID | Question | Resolution path |
|----|----------|-----------------|
| Q-1 | At ±10 MHz / 801 pt, what IFBW gives the best rate-vs-noise tradeoff? | **Resolved 2026-05-28** — 300 kHz IFBW recommended (study at `references/reports/20260528/`). 0.002 dB trace noise, ~45 dB SNR margin against -40 dB return loss. |
| Q-2 | Should our DataFlux replacement extend the Amp suite (PR upstream) or be a fresh app under `ena-dev/`? | **Resolved 2026-05-28** — Fresh app in `code/ena-dev/gui/`. Reuse Amp `core/` as backend only (see §3.4). |
| Q-5 | Operating-point frequencies — what cal range? | **Resolved 2026-05-28** — 200–250 MHz (50 MHz span) matching prior LibreVNA baseline. Sensor of interest is the resonance near 233.5 MHz; the wider cal range gives flexibility to narrow the measurement window without re-cal. See §4A.4. |
| Q-6 | Calibration method: manual SOLT vs ECal? | **Resolved 2026-05-28** — Default is ECal using the user's Keysight N7550A USB module (DC–4 GHz, 2-port). Manual SOLT is a fallback. See §4A.5. |
| Q-3 | Does USBTMC sustain 30+ Hz for 60 min without bulk-transfer hiccups? | Phase 3 stability run (variant B) |
| Q-4 | Will ASCII `:CALC1:DATA:FDAT?` be fast enough? | **Resolved 2026-05-28** — No. Binary `:FORM:DATA REAL32` + `:FORM:BORD SWAP` is required from the start to reach 33–35 Hz; ASCII tops out at ~10–15 Hz. |
| R-1 | Risk: Amp suite has untested-on-real-hardware code paths (Amp is an AI agent's first pass). May need spot fixes. | Treat as expected; document fixes in changelog at §13 |
| R-2 | Risk: Windows USBTMC + KIOLS occasionally returns stale buffers after timeouts. | Always send `*CLS` before queries that follow a previous error |

---

## 11. References

### Internal (this repo)

- `docs/project-overview.md` — LibreVNA project narrative (canonical companion).
- `CLAUDE.md` — repo rules, sweep-rate table, libreVNA.py contract.
- `docs/e5063a-gui-spec.md` — GUI build plan (port LibreVNA MVP, swap backend; G-0…G-6).
- `docs/e5063a-gui-ux-spec.md` — deterministic two-screen UX (Setup → Acquire): widget objectNames, state machine, filename rule, wiring.
- `docs/e5063a-gui-design-system.md` — View-layer tokens + factories (`theme.py`); code-built views.
- `code/LibreVNA-dev/markdown/20260205/part2-continuous-sweep-implementation.md` — LibreVNA rate analysis.
- `code/LibreVNA-dev/gui/mvp/` — MVP architecture template (model dataclasses, presenter/worker pattern).
- `code/LibreVNA-dev/scripts/8_plot_monitor_data.py` — Monitor Mode CSV consumer (target format for §7).
- `code/ena-dev/scripts/` — project-owned scripts: `probe_e5063a.py`, `configure_e5063a.py`, `calibrate_e5063a.py` (host ECal, S-18), `bench_e5063a_rates.py`, `bench_e5063a_realworld.py`.

### External LibreVNA report artifacts (outside `code/`, in `REPORT/`)

These are the user's prior formal LibreVNA reports — to be parsed and mirrored
in the upcoming real-world continuous-mode IFBW benchmark on E5063A.

- `REPORT/20260205/20260205.pdf` — formal report of the 20260205 LibreVNA testing session (continuous + single mode workflow).
- `REPORT/20260205/20260205.pptx` — slide-deck version of the same.
- `REPORT/20260205/single_sweep_test_20260205_225940.xlsx` — single-mode sweep-rate data (format template).
- `REPORT/20260205/continuous_sweep_test_20260205_230028.xlsx` — continuous-mode sweep-rate data (format template).
- `REPORT/20260226/20260205.pdf` — follow-up report (note: filename inside 20260226/ also has 20260205 prefix — operator should confirm).
- `REPORT/20260226/*.mp4` — screen captures of the testing sessions.

### External / reference material (in `references/reports/`)

- `20260504/E5063A_參考資料/SUMMARY.md` — collaborator handover summary.
- `20260504/E5063A_參考資料/E5063A_參考資料.md` — connection methods, legacy DataFlux behaviour.
- `20260504/E5063A_參考資料/E5063A_SCPI常用命令整理.md` — SCPI cheat-sheet.
- ⛔ `9018-07931_E5063A_SCPI_Command_Reference.pdf` — **was NOT an E5063A reference; it is the Agilent 4155B/4156B Semiconductor Parameter Analyzer SCPI manual, mislabeled. All copies (in `20260504/.../official_docs/` and `20260528/`, plus extracted-page chunks and `code/ena-dev/scpi_ch4_test.txt`) deleted 2026-06-02.** Do not re-download. See §6.7.6.
- `20260602/E5062A_Programmers_Guide_E5061-90042_Part*.pdf` — **E5062A/E5061 Programmer's Guide** (P/N E5061-90042, 28 chunks). The real SCPI ground truth for the E5062A/E5063A family (shared SCPI tree; Ch.13 command reference). Consolidated into `docs/E5063A_SCPI_Reference.md`.
- `20260522/keysight-ena-e5063a-python-automation/` — Amp project (third-party PoC sandbox); working E5063A PyVISA SCPI constants.
- `20260522/keysight-ena-e5063a-python-automation/DEVELOPER_GUIDE.md` — Amp's own developer guide.
- `20260522/vna-e5063a/` — Keysight sample programs and IO Libraries Suite installers.
- `20260528/e5063a-speed-potential-and-ifbw-tradeoff.md` — **primary** speed-potential study (§6 of this SPEC is built on its findings: 300 kHz IFBW, binary REAL32, display off → ~33–35 Hz achievable). *(Speed numbers are sound; they derive from the E5063A data-sheet throughput table, not the bogus 9018-07931 PDF.)*

---

## 12. Status Table (Living — single source of truth)

| ID | Item | Phase | Status | Updated |
|----|------|-------|--------|---------|
| S-1 | KIOLS installed on Windows host | §2 | ✅ Validated | 2026-05-28 |
| S-2 | USBTMC `*IDN?` round-trip via Connection Expert | §2 | ✅ Validated | 2026-05-28 |
| S-3 | Amp suite copied into `code/ena_qt6_suite/` | §3 | ✅ Validated | 2026-05-28 |
| S-4 | `code/.venv` shared with LibreVNA work | §3 | ✅ Validated | 2026-05-28 |
| S-4a | `code/ena-dev/` skeleton + reuse shim (`ena_dev_paths.py`, README) | §3.3–§3.4 | ✅ Validated | 2026-05-28 |
| S-5 | `pyvisa` + `pyvisa-py` installed (1.16.2 / 0.8.1) | §3 / §4 | ✅ Validated | 2026-05-28 |
| S-5a | Windows VISA PATH fix codified in `ena_dev_paths.py` (§3.6) | §3.6 | ✅ Validated | 2026-05-28 |
| S-6 | `code/ena-dev/scripts/probe_e5063a.py` written | §4 | ✅ Validated | 2026-05-28 |
| S-7 | Probe script confirms VISA discovery + `*IDN?` + measurement-config dump + `:SYST:ERR?` clean | §4 | ✅ Validated | 2026-05-28 |
| S-7a | Q-1 resolved → 300 kHz IFBW recommended (study at `references/reports/20260528/`) | §6 / §10 | ✅ Validated | 2026-05-28 |
| S-7b | Q-4 resolved → binary `REAL32 + SWAP` required (ASCII too slow) | §6 / §10 | ✅ Validated | 2026-05-28 |
| S-8 | Amp `main.py` launches (launch-only check) | §4 | ✅ Validated | 2026-05-28 |
| S-9 | One full S11 trace read via Amp GUI | §4 | ⏸ Deferred | 2026-05-28 (superseded by §3.4 backend-only reuse) |
| S-9a | Q-2 resolved → own GUI in `code/ena-dev/gui/`, Amp `core/` reused as backend only | §3.4 / §10 | ✅ Validated | 2026-05-28 |
| S-9b | Calibration default strategy decided — **ECal via N7550A** + state-file recall (revised from manual SOLT) | §4A.5 / §8 | ✅ Validated | 2026-05-28 |
| S-9c | Q-5 resolved → cal range 200–250 MHz / 801 pt (matches prior LibreVNA baseline) | §4A.4 | ✅ Validated | 2026-05-28 |
| S-9d | Q-6 resolved → ECal method using Keysight N7550A (DC–4 GHz) | §4A.5 | ✅ Validated | 2026-05-28 |
| S-9e | Operator runs ECal on E5063A, saves cal as `D:\State03.sta` (host copy at `references/reports/20260528/myCal_200M_250M_801pt.sta`) | §4A.5 | ✅ Validated | 2026-05-28 |
| S-11a | `code/ena-dev/scripts/configure_e5063a.py` written and runs clean (16/16 OK) — recalls cal, pins locked operating point, sets binary REAL32 + SWAP | §4A | ✅ Validated | 2026-05-28 |
| S-11b | `configure_e5063a.py` accepts both host paths (auto-upload via `:MMEM:TRAN`) and instrument-side paths. Validated 17/17 OK end-to-end. | §4A | ✅ Validated | 2026-05-28 |
| S-10 | DataFlux-equivalent GUI scoped & wireframed (own GUI in `ena-dev/gui/`) — detailed plan + UX in `docs/e5063a-gui-spec.md` + `docs/e5063a-gui-ux-spec.md` | §5 / GUI-spec | ✅ Validated | 2026-06-02 |
| S-11 | **DataFlux-equivalent GUI implemented (`code/ena-dev/gui/`) — phases G-0…G-5 ✅ live-validated:** Configure + host ECal + Sanity Check + Continuous Monitor + History; Dataflux CSV byte-compatible with `8_plot_monitor_data.py`; Monitor sustained 39.1 Hz (drift +0.32% over 120 s). **ALL GUI phases now complete (2026-06-04): G-12 monitor Y-axis toggle, G-13 live S11 trace preview + display modes, G-14 WTMH lab branding, G-15 cal file-listing bug fix, G-6 standalone `.exe` — all live-validated.** Full status in `docs/e5063a-gui-spec.md`; packaging `docs/e5063a-packaging.md`. | §5 / GUI-spec | ✅ COMPLETE | 2026-06-04 |
| S-12 | ≥ 30 Hz mean validated on E5063A — measured **32.70 Hz** at variant B (300 kHz IFBW, REAL32 binary). All single-sweep variants A–D in expected range, zero SCPI errors. | §6.5 | ✅ Validated | 2026-05-28 |
| S-12a | 60-min stability run at variant B | §6 | ⬜ Planned | — |
| S-12b | Variant E (continuous + polling) deferred pending SRQ-based sync | §6.5 | ⏸ Deferred | 2026-05-28 |
| S-12c | Real-world continuous-mode IFBW benchmark mirroring LibreVNA REPORT/20260205/ + REPORT/20260226/ workflow → xlsx output for report. **Done: full 8-IFBW × 30-sweep continuous run executed live 2026-06-02, byte-compatible xlsx written (`data/20260602/continuous_sweep_test_e5063a_real32_20260602_121928.xlsx`), clean error queue all IFBW. Continuous = 39.54 Hz @ 300 kHz down to 1.26 Hz @ 1 kHz; ~+14–15% over single in the overlap region (§6.7.7).** | §6.7 / §11 | ✅ Validated | 2026-06-02 |
| S-12d | `code/ena-dev/scripts/bench_e5063a_realworld.py` — **both single + continuous paths validated live 2026-06-02.** Single-mode sub-100 kHz curve + continuous-mode full 8-IFBW × 30-sweep run both produced byte-compatible xlsx with clean error queues; latched `:STAT:OPER:EVEN?` bit-4 sync worked first time (no variant-E fallback needed). Carries a `--format {ascii,real32,real64}` flag (S-12h). | §6.7 | ✅ Validated | 2026-06-02 |
| S-12g | Sub-100 kHz single-mode IFBW→rate curve at locked cal (200–250 MHz/801 pt/S11, REAL32): 100/75/50/40/30 kHz = 28.36/26.03/22.67/21.42/18.54 Hz. **>20 Hz for IFBW ≳ 40 kHz; empirical 20 Hz crossover ≈ 35 kHz.** Recommended sub-100 kHz point: 50 kHz @ 22.7 Hz. Data: `data/20260602/single_sweep_test_e5063a_20260602_114115.xlsx`. | §6.7 | ✅ Validated | 2026-06-02 |
| S-12h | `--format {ascii,real32,real64}` flag added to `bench_e5063a_realworld.py` (default real32). Measured real32 vs real64 single-mode: **real64 costs ~2–5 ms/sweep (~4–13%, worst at high IFBW) for no usable S11 dB-mag accuracy gain** (USBTMC/host-overhead-bound, not USB-bandwidth-bound). real32 confirmed as the right default. Data: `single_sweep_test_e5063a_{real32,real64}_20260602_1151*.xlsx`. | §6.7 | ✅ Validated | 2026-06-02 |
| S-12e | LibreVNA `REPORT/20260205/` PDF + xlsx schema reverse-engineered (Single + Continuous modes, 7 IFBW values, 4 metrics, multi-sheet xlsx with Configuration/Timing/S11 Traces/Metrics blocks) | §6.7 | ✅ Validated | 2026-05-28 |
| S-12i | Single-vs-continuous analysis notebook `code/ena-dev/notebook/1_single_vs_continuous_sweep_e5063a.ipynb` built + executed (E5063A counterpart of LibreVNA `3_single_vs_continuous_sweep.ipynb`). Uses a **matched** same-session 8-IFBW × 30-sweep pair (`data/20260602/{single,continuous}_sweep_test_e5063a_real32_20260602_124432.xlsx`). Result: continuous beats single by only **+15–22%** in the 50–300 kHz band (vs LibreVNA's 3.7×) because the E5063A single path has no GUI mediator; **both modes ≥25 Hz for IFBW ≥ 75 kHz, ≥20 Hz for IFBW ≥ 50 kHz**; jitter & noise floor mode-independent. New `ena-dev/notebook/` folder + README (documents the `code/`-rooted Jupyter launch needed for MCP access). | §6.7 / §11 | ✅ Validated | 2026-06-02 |
| S-12f | Phase 3 re-confirm run 15:44 — variants A–D all in expected range, A had "Query INTERRUPTED" residual. 14:43 numbers remain canonical. | §6.6.1 | ✅ Validated | 2026-05-28 |
| S-13 | CSV format byte-compatible with `8_plot_monitor_data.py` | §7 | ⬜ Planned | — |
| S-14 | Calibration strategy beyond default — deferred until needed | §8 | ⏸ Deferred | 2026-05-28 |
| S-15 | SCPI verbs used by `bench_e5063a_realworld.py` verified against corrected ground truth (E5062A Programmer's Guide `20260602/` + complete `docs/E5063A_SCPI_Reference.md` §8; the old `9018-07931…pdf` is a mislabeled 4155B manual — see §6.7.6). **All four verbs confirmed:** FDAT 2×N MLOG, FREQ:DATA, NTR/PTR/EVEN syntax, and `:STAT:OPER` bit-4=Measuring (§8.19: bit 4 = Measuring, end-of-sweep = 1→0, NTR preset 0 / PTR preset 16432). | §6.7.6 | ✅ Validated | 2026-06-02 |
| S-16 | Monitor-mode **log-interval headroom** quantified from `REPORT/20260226/20260205.pdf` (parsed via netmind): monitor rate is floored by mean sweep time; E5063A lifts the ceiling from LibreVNA's ~7 Hz (140 ms) to **~26–39 Hz** (25–42 ms) at the matched 200–250 MHz/801 pt point = **~3.7–5.8×** more samples for the blood-vessel monitoring objective. Captured in §5.1.1 + memory `project-monitor-loginterval-e5063a`. | §5.1.1 | ✅ Validated | 2026-06-02 |
| S-17 | Dedicated GUI implementation spec `docs/e5063a-gui-spec.md` created + **executed** (G-0…G-5 built & validated; ux-spec `docs/e5063a-gui-ux-spec.md` + design-system `docs/e5063a-gui-design-system.md` also realized in code). | §5 / GUI-spec | ✅ Validated | 2026-06-02 |
| S-18 | **Host-driven 1-port (S11) ECal validated live.** `code/ena-dev/scripts/calibrate_e5063a.py` runs the full ECal from the host (`:SENS1:CORR:COLL:ECAL:SOLT1 1` + `*OPC?`, module self-measures O/S/L), verifies correction active + SOLT1, confidence-reads (binary REAL32), and auto-saves a grid-named `.sta` (`:MMEM:STOR:STYP CST`). 14/14 OK on `MY54806798`; saved `D:\cal_S11_200-250MHz_801pt.sta` round-trips through `configure_e5063a.py` (16/16 OK). Confirms configure + calibrate are both host-drivable → GUI can be a one-stop Configure/Calibrate/Sanity/Continuous tool. IFBW change ≠ re-cal (§4A.6); only grid change forces re-cal. | §8 / GUI-spec | ✅ Validated | 2026-06-02 |
| S-19 | **Timestamp-integrity fix implemented + headless-validated** (20260715 report: dt quantized to the 15.625 ms tick, 16–26% duplicate stamps, hour-scale gaps — timestamps only, S11 values fine). Root causes: `time.monotonic()`=GetTickCount64 on Py3.11/Windows; unbounded in-RAM record buffer; GUI-slot re-stamping. Fix: `perf_counter_ns` (QPC, 100 ns) stamped at acquisition in the controller thread; streaming `DatafluxWriter` (bounded RAM, header patched in place, byte-compatible); wall-vs-QPC drift audit. `verify_timestamp_fix.py` ALL PASS (0.000% dup, dt continuum, loads in `8_plot_monitor_data.py`). SPEC: `docs/e5063a-timestamp-fix-spec.md`. **RELEASED as v1.1.0 (2026-07-29, ahead of field validation — for the progress report; notes state this honestly). Remaining acceptance: MIRDC multi-hour recording vs §6 metrics.** SemVer adopted (`docs/versioning-and-releases.md`): both GitHub Releases published with exe zips (v1.0.0 binary recovered from the `REPORT/20260604` backup). | §5 / TS-fix-spec | 🟨 Released; field validation pending | 2026-07-29 |

---

## 13. Changelog

| Date | Change | By |
|------|--------|-----|
| 2026-05-28 | Initial SPEC created. Sections 1–12 drafted. S-1 through S-4 marked Validated based on Phase 1 setup work. | Claude (with Aunuun) |
| 2026-05-28 | §3.3 layout refreshed; §3.4 reuse policy added (import, do not fork). `code/ena-dev/` skeleton created with `ena_dev_paths.py` shim and README. New row S-4a added to Status Table. | Claude (with Aunuun) |
| 2026-05-28 | pyvisa 1.16.2 + pyvisa-py 0.8.1 installed into `code/.venv`. §3.6 added documenting the Windows VISA PATH fix (KIOLS install does not add its bin dirs to PATH; codified in `ena_dev_paths.py`). | Claude |
| 2026-05-28 | `code/ena-dev/scripts/probe_e5063a.py` written and run successfully against the live instrument (4 OK / 0 FAIL). §4.5 captures the live measurement-config baseline. S-5, S-5a, S-6, S-7 marked Validated. | Claude |
| 2026-05-28 | §6 (Phase 3 — sweep-rate validation) rewritten using the new `references/reports/20260528/e5063a-speed-potential-and-ifbw-tradeoff.md` findings: 300 kHz IFBW + binary REAL32 + display off → ~33–35 Hz realistic ceiling. Targets revised from "≥ 20 Hz" to "≥ 30 Hz (variant B)". Open questions Q-1 and Q-4 resolved. New rows S-7a, S-7b added. | Claude |
| 2026-05-28 | §3.4 refined to **backend-only reuse**: Amp GUI is not used as a user tool; ena-dev ships its own GUI in `code/ena-dev/gui/`. §4.3/§4.6 updated (Amp `main.py` launch is enough for S-8; S-9 superseded). New §4A added: E5063A workflow primer (calibration + acquisition concepts vs LibreVNA). Q-2 resolved; new Q-5 opened (operating-point center frequency). §8 default calibration strategy decided (front-panel SOLT + state-file recall). Rows S-8 (✅), S-9 (⏸), S-9a, S-9b, S-9c added; S-12 target updated to ≥30 Hz. | Claude (with Aunuun) |
| 2026-05-28 | Q-5 resolved: cal range = **200–250 MHz / 801 pt** (matches prior LibreVNA baseline; covers the 233.5 MHz sensor with wide flexibility). New Q-6 introduced and immediately resolved: cal method = **ECal via Keysight N7550A** (DC–4 GHz USB module). §4A.4 rewritten with locked operating point; §4A.5 added with front-panel + SCPI ECal workflows; §4A.6 added covering cal-interpolation for sub-window measurement. §8.1 default strategy revised from manual SOLT to ECal. Status rows S-9c (✅), S-9d (✅), S-9e (⬜) added. | Claude (with Aunuun) |
| 2026-05-28 | §4A.6 expanded with full re-cal-required vs not table. Clarified IFBW is independent of cal — can change at runtime without invalidating. Sub-window interpolation moved to §4A.6.1. | Claude (responding to user Q on IFBW independence) |
| 2026-05-28 | Operator completed ECal on E5063A. Cal lives at `D:\State03.sta` on the instrument (55,894 B); host-side reference copy at `references/reports/20260528/myCal_200M_250M_801pt.sta` (55,879 B). §4A.4 file-path row updated. S-9e ✅. | Claude (with Aunuun) |
| 2026-05-28 | `code/ena-dev/scripts/configure_e5063a.py` written and validated against live instrument (16 OK / 0 FAIL). Recalls cal state, pins all 8 operating-point parameters, switches to binary REAL32 + SWAP. New row S-11a added. | Claude |
| 2026-05-28 | `configure_e5063a.py` enhanced: `--cal-state` now accepts EITHER an instrument-side path (`D:\\State03.sta`, used as-is) OR a host file path (auto-uploaded via `:MMEM:TRAN` then recalled). New `--upload-to` flag for custom instrument-side destination. Validated end-to-end (17/17 OK with host-path form). Host-side `myCal_200M_250M_801pt.sta` is now also present on the instrument as `D:\\MYCAL_200M_250M_801PT.STA`. Doc-comment + usage examples updated. | Claude |
| 2026-05-28 | Phase 3 sweep-rate benchmark (`code/ena-dev/scripts/bench_e5063a_rates.py`) written and validated. Measured rates at 200–250 MHz / 801 pt: variant B (300 kHz IFBW, REAL32) = **32.70 Hz**, variant C (30 kHz) = 18.57 Hz, variant D (1 kHz) = 1.26 Hz, variant A (ASCII) = 21.68 Hz — all within expected ranges, zero SCPI errors, low jitter (p99/mean ≤ 1.17). §6.5 updated with the empirical table and the SCPI gotcha that the correct host-paced trigger pattern on this firmware is `TRIG:SOUR BUS + :INIT:IMM + :TRIG:SING + *OPC?` (not the `TRIG:SOUR INT + :INIT:IMM + *OPC?` from the 20260528 study). Variant E (continuous + polling) deferred due to polling-bound under-measurement. S-12 ✅, S-12a planned, S-12b deferred. | Claude |
| 2026-05-28 | §4A.7 added — trigger-mode comparison E5063A vs LibreVNA (Continuous / Single / Hold mapping with SCPI verbs on both sides). Pre-existing missing `## 5.` heading restored. §11 expanded with the external LibreVNA REPORT/ artifacts (PDFs + xlsx + mp4 captures) the upcoming real-world benchmark will mirror. New row S-12c added (Planned). | Claude (with Aunuun) |
| 2026-05-28 | LibreVNA `REPORT/20260205/{20260205.pdf, 20260226/20260205.pdf, continuous_sweep_test_*.xlsx, single_sweep_test_*.xlsx}` parsed. Methodology decoded: Single+Continuous modes, 7 IFBW values (150/125/100/75/50/10/1 kHz), 4 metrics (Mean Sweep Time, Update Rate, Noise Floor, Trace Jitter). xlsx schema decoded: Summary + per-IFBW sheets with Configuration/Timing/S11 Traces/Metrics blocks. S-12e ✅. | Claude |
| 2026-05-28 | Design decisions for the real-world IFBW bench locked in (via user-confirmed options): freq range 200–250 MHz / 801 pt (matches current ECal); IFBW set = 8 values (300/150/125/100/75/50/10/1 kHz — LibreVNA-comparable + 300 kHz headline); run both Single + Continuous; per-sweep sync = `:STAT:OPER:EVEN?` latched poll on bit 4 with NTR=16/PTR=0. 30 sweeps per IFBW. | Claude (with Aunuun) |
| 2026-05-28 | `code/ena-dev/scripts/bench_e5063a_realworld.py` written (480 lines, syntax-checked). Implements the design above. Writes two xlsx workbooks per run (`{mode}_sweep_test_e5063a_<stamp>.xlsx`) that are byte-compatible with the LibreVNA REPORT templates. New §6.7 added covering goal/methodology/metrics/schema/CLI/pending-SCPI-verification. S-12d 🟦 (script ready), S-15 ⬜ (SCPI reference cross-check, deferred). | Claude |
| 2026-05-28 | Phase 3 re-confirm run at 15:44 produced `bench_e5063a_20260528_154404.{json,csv}` with A=21.19, B=31.71, C=18.48, D=1.26 Hz — all variants in expected range, variant A error queue "Query INTERRUPTED" (residual, not a new failure). No new conclusion; 14:43 numbers remain canonical in §6.5. §6.6.1 added. S-12f ✅. | Claude |
| 2026-05-28 | Real-world benchmark NOT executed in this session — operator ran `bench_e5063a_rates.py` (old Phase 3 script) by mistake, then ran out of time and returned home before retrying with `bench_e5063a_realworld.py`. Live-hardware execution deferred to next session. S-12c remains Planned; SPEC + memories updated for clean handoff. | Claude (with Aunuun) |
| 2026-06-02 | **Reference-source correction.** Discovered that `9018-07931_E5063A_SCPI_Command_Reference.pdf` (referenced in §6.7.6, §11, S-15) is **not** an E5063A document — it is the Agilent 4155B/4156B Semiconductor Parameter Analyzer SCPI manual, mislabeled (its extract `code/ena-dev/scpi_ch4_test.txt` is verbatim 4155B content). Corrected §6.7.6, §11, and S-15 to point at the real ground truth: `20260602/` E5062A Programmer's Guide (E5061-90042), the `20260522/keysight-ena-e5063a-python-automation` suite, the `20260504/E5063A_參考資料` cheat-sheet (minus its bogus PDF), and `docs/E5063A_SCPI_Reference.md`. Re-assessed the four §6.7.6 verbs against the corrected sources: FDAT 2×N MLOG, FREQ:DATA, and NTR/PTR/EVEN syntax confirmed; `:STAT:OPER` bit-4=Measuring weight still needs hardware confirmation. Same correction applied to `docs/E5063A_SCPI_Reference.md` §0/§9. | Claude (with Aunuun) |
| 2026-06-02 | **First live run of `bench_e5063a_realworld.py` (single mode).** Sub-100 kHz IFBW sweep at the locked cal: 100/75/50/40/30 kHz = 28.36/26.03/22.67/21.42/18.54 Hz, clean error queue, byte-compatible xlsx written to `data/20260602/`. Confirms the prediction that single-mode clears 20 Hz for IFBW ≳ 40 kHz (empirical crossover ≈ 35 kHz; cycle model `25 + 869/IFBW(kHz)`). S-12d single-mode validated; new S-12g added. Continuous-mode path still pending bit-4 confirmation. Memory `project-e5063a-phase3-bench-results` updated. | Claude (with Aunuun) |
| 2026-06-02 | **Deleted the bogus 4155B files** (19 total): `code/ena-dev/scpi_ch4_test.txt`; `9018-07931_E5063A_SCPI_Command_Reference.pdf` in both `20260504/.../official_docs/` and `20260528/`; and the 16 `Extracted pages from 9018-07931…_*.pdf` chunks in `20260528/`. Genuine E5063A docs (data sheet, operation manual, brochure, config guide, PCB overview, help CHM, speed-screenshot PNG) left intact. Updated `20260504/.../official_docs/README_官方文件下載說明.md` to mark the entry removed (kept the download-provenance record + 4155B finding). Doc/memory warnings updated from "ignore copies" to "deleted." | Claude (with Aunuun) |
| 2026-06-02 | Added `--format {ascii,real32,real64}` flag to `bench_e5063a_realworld.py` (default real32, backward-compatible; real64 → `:FORM:DATA REAL` + datatype `"d"`; output filename now embeds the format). Measured real32 vs real64 single-mode at the locked cal: **real64 costs ~2–5 ms/sweep (~4–13% rate hit, largest at high IFBW) for no usable S11 dB-mag accuracy gain** — the extra bytes are USBTMC/host-overhead-bound (~1–2 MB/s effective), not USB-bandwidth-bound. real32 stays the recommended default; with real64 the 20 Hz crossover shifts to ~38–40 kHz. Data: `data/20260602/single_sweep_test_e5063a_{real32,real64}_*.xlsx`. Memory `project-e5063a-phase3-bench-results` updated. | Claude (with Aunuun) |
| 2026-06-02 | **Consolidated SCPI reference `docs/E5063A_SCPI_Reference.md` completed** (1162 lines; §8 per-subsystem detail filled from the E5062A Programmer's Guide). This **closes the last §6.7.6 open item:** §8.19 confirms `:STAT:OPER` **bit 4 = Measuring** (1 during sweep; end-of-sweep = bit-4 1→0; NTR preset 0 / PTR preset 16432) — the bench's `NTR 16 / PTR 0 / poll :EVEN?` continuous-sync exactly matches. All four §6.7.6 verbs now verified; S-15 → ✅ Validated; S-12d continuous-mode SCPI unblocked (only a live continuous run remains). Bogus-PDF ⛔ warnings confirmed intact in the completed reference. | Claude (with Aunuun) |
| 2026-06-02 | **Single-vs-continuous analysis notebook created (S-12i).** Ran a fresh matched both-mode bench (`bench_e5063a_realworld.py`, no `--modes` → single+continuous, 8 IFBW × 30, `..._124432.xlsx`) so both modes share one session/cal. Built + executed `code/ena-dev/notebook/1_single_vs_continuous_sweep_e5063a.ipynb` via Jupyter MCP (9 cells: timing panels, update-rate bars with 20/25 Hz lines, S11 overlays, jitter, PrettyTable summaries, conclusions) — mirrors LibreVNA `3_single_vs_continuous_sweep.ipynb`. Findings: continuous +15–22% over single (50–300 kHz), both modes ≥25 Hz for IFBW ≥75 kHz / ≥20 Hz for ≥50 kHz, jitter+NF mode-independent, one benign 125 kHz continuous polling outlier (min/max band only). New `ena-dev/notebook/` folder + README documenting the `code/`-rooted Jupyter launch (the documented `LibreVNA-dev/notebook` root can't see `ena-dev/notebook`). | Claude (with Aunuun) |
| 2026-06-02 | **Live continuous-mode benchmark run — S-12c/S-12d closed.** Ran `bench_e5063a_realworld.py --modes continuous` (full 8-IFBW × 30-sweep) on E5063A `MY54806798` at the locked cal. Latched `:STAT:OPER:EVEN?` bit-4 sync worked first try (no variant-E fallback). Continuous IFBW→rate: 300/150/125/100/75/50/10/1 kHz = 39.54/35.75/35.78/32.81/29.66/26.24/10.04/1.26 Hz; NF −1.64 dB, jitter ≤ 0.004 dB, clean error queue all IFBW. Apples-to-apples vs single (REAL32, overlap): 100/75/50 kHz = +15/+14/+14% — the expected **modest** gain (≈+25% at the 300 kHz head), not LibreVNA's 3–5× single→continuous jump. ≥30 Hz now reachable in continuous mode down to ~100 kHz IFBW. Data: `data/20260602/continuous_sweep_test_e5063a_real32_20260602_121928.xlsx`. §6.7.7 → ✅; S-12c/S-12d → ✅ Validated. Memory `project-e5063a-phase3-bench-results` updated. | Claude (with Aunuun) |
| 2026-06-02 | **Monitor-mode log-interval analysis + next-session handoff.** Parsed `REPORT/20260226/20260205.pdf` (netmind) → documented the *real objective*: Continuous/Monitor mode logs per-sweep min-S11 frequency for blood-vessel monitoring, and monitor rate is floored by mean sweep time. Added §5.1.1 with the LibreVNA ~7 Hz → E5063A ~26–39 Hz (~3.7–5.8×) table; new rows S-16 (✅) and S-17 (🟦). §5.4/§5.5 now point to the new **`docs/e5063a-gui-spec.md`** (created this session as the next-major-work kickoff: port `LibreVNA-dev/gui/mvp/` → `ena-dev/gui/`, swap SCPI backend for the E5063A `ENAConnection` path). S-10 → 🟦. Memories added/refreshed: `project-monitor-loginterval-e5063a` (new), `project-librevna-overview` (next-work pointer), MEMORY.md index. CLAUDE.md gained an ena-dev section for cold-start context. | Claude (with Aunuun) |
| 2026-06-02 | **Bugfix: single-sweep left the front-panel preview frozen.** The confidence/trace single sweep sets `:TRIG:SOUR BUS` + `:INIT1:CONT OFF` (Hold); on exit the E5063A stayed in Hold → front-panel live preview froze (user had to run `configure_e5063a.py` after `calibrate_e5063a.py` to recover). Fix: restore live free-run (`:ABOR`/`:TRIG:SOUR INT`/`:INIT1:CONT ON`) — in `calibrate_e5063a.py` BEFORE the `.sta` save (so the saved state is live too) and in `backend_e5063a.py` `restore_live()` (after ECal, on monitor/sanity stop, on close). Verified `:INIT1:CONT?`=1 / `:TRIG:SOUR?`=INT. Memory `project-e5063a-host-calibration` updated. | Claude (with Aunuun) |
| 2026-06-02 | **Host-driven ECal validated → one-stop GUI scope confirmed (S-18).** In response to collaborator feedback (experiments need fast dynamic re-config + re-cal), evaluated whether configure + calibrate can be driven from the host: **yes, both.** Configure was already proven (`configure_e5063a.py`, S-11a/b). Wrote `code/ena-dev/scripts/calibrate_e5063a.py` (1-port S11 ECal via N7550A: geometry → `:ECAL:SOLT1 1`+`*OPC?` → verify → confidence sweep → grid-named `.sta` save, hot+host copy). Live run 14/14 OK on `MY54806798`; cal `.sta` round-trips through `configure_e5063a.py` (16/16 OK). Fixed a confidence-read bug (ASCII `:CALC:DATA:FDAT?` → `-410 Query INTERRUPTED`; switched to binary REAL32 per the proven bench pattern). §8.1 host-driven note added; new row S-18 (✅). Surfaced the IFBW≠re-cal clarification for the dynamic workflow. Next: GUI now scoped as Configure/Calibrate/Sanity/Continuous one-stop tool. | Claude (with Aunuun) |
| 2026-06-02 | **GUI BUILT & live-validated — Phase 2 complete (S-10/S-11/S-17 → ✅).** Implemented the E5063A Data Collector under `code/ena-dev/gui/` (PySide6 MVP, two-screen Setup→Acquire + History page) across gui-spec phases **G-0…G-5**, all live-verified against `MY54806798` via qt-mcp: Configure + host ECal + recall, Verify preview, **Continuous Monitor → Dataflux CSV** (byte-compatible w/ `8_plot_monitor_data.py`, **39.1 Hz sustained, drift +0.32%/120 s**), Device Sanity Check → xlsx, History (list/delete/zip), filename composition, sci-notation toggle, stop-by Duration/Query-count/Manual + progress. Backend `E5063ABackend` on a dedicated QThread (NF-4). **Patterns learned (in gui-spec changelog + memory `project-e5063a-gui-ux` / `project-e5063a-host-calibration`):** (1) single-sweep trigger path is ~4× slower in-GUI than continuous → Monitor AND Sanity use the latched continuous read; (2) host kill mid-USBTMC-read → −420; resync on connect with `session.clear()`+`*CLS`+`:DISP:CCL`; the front-panel message is sticky (cleared by `:DISP:CCL`, separate from `:SYST:ERR?`); (3) restore live free-run on stop/close; (4) don't disable buttons on busy (controller serializes — clicks queue). Phase 5.5 → ✅; only gui-spec G-6 (`.exe`) remains. | Claude (with Aunuun) |
| 2026-06-04 | **GUI COMPLETE — all remaining phases done + packaged (S-11 → ✅ COMPLETE).** Five phases, all live-validated vs `MY54806798`: **G-12** monitor scroller Y-axis toggle (freq↔magnitude, idle-only); **G-13** live S11 trace preview that free-runs from Proceed (mimics the instrument screen) + a `displaySelector` (live trace ⇄ min-scalar) — state-machine change: preview armed once via `monitor_begin` on Proceed, torn down on Back/close (NOT Stop), recording flag on Start/Stop; live-verified real trace + ~38.8 Hz + Back/close leave `INT/CONT 1`; **G-14** WTMH (NCKU) lab branding (window/taskbar + `.exe` icon + 28 px header emblem via `theme.TopBar(show_logo)`; assets `mvp/assets/WTMH.ico`+`wtmh_logo.png`); **G-15** calibration file-listing bug fix — `list_cal_files` queried `:MMEM:CAT? "D:\"` (trailing backslash) which **times out** → silently fell back to 2 hardcoded defaults → new/diff-config cals never listed; fix = query `:MMEM:CAT? "D:"` + fail-loud + refresh dropdown after ECal/recall + recall no longer clobbers the grid (save+load were always fine); **G-6** standalone `.exe` (auto-py-to-exe/PyInstaller One-Directory; needed `--exclude-module PyQt5 PyQt6` for the dual-binding abort + `--paths`/`--hidden-import` + a `sys.frozen` guard in `ena_dev_paths.py`; ⚠ target needs Keysight IO Libraries — VISA driver not bundleable). New diagnostics `ena-dev/scripts/{check_instrument_state,investigate_cal_files,investigate_cal_load}.py`; new doc `docs/e5063a-packaging.md`. Patterns in gui-spec §6.1/§6.2 + memory `project-e5063a-gui-ux`. | Claude (with Aunuun) |
| 2026-07-24 | **Timestamp-integrity fix (SPEC written → implemented → headless-validated, same day) + SemVer versioning adopted.** Validated the 20260715 report (timestamps only; S11 fine), confirmed root causes (monotonic=GetTickCount64 15.625 ms; unbounded RAM buffer; GUI-slot re-stamping), wrote `docs/e5063a-timestamp-fix-spec.md` (Context7 Python/Qt docs + Microsoft QPC guidance + PEP 418), implemented F-1…F-5 (QPC stamps at acquisition, streaming `DatafluxWriter`, drift audit, `verify_timestamp_fix.py` ALL PASS incl. loader round-trip). Versioning: `docs/versioning-and-releases.md` (SemVer semantics + §6.1 command playbook), `CHANGELOG.md`, `mvp/version.py` in the window title; v1.0.0 retro-tagged `f1b0cf3` + GitHub Release published (notes-only); v1.1.0-dev exe rebuilt + zipped (135 MB). New row S-19 (🟨). Commits `cf46091`/`4203d78`/`5ea9f92`. Next: live pass + multi-hour re-validation → v1.1.0 release. | Claude (with Aunuun) |
| 2026-07-29 | **v1.1.0 RELEASED + v1.0.0 binary recovered + progress-report support.** Per user decision (needed for the progress report), released v1.1.0 ahead of the MIRDC field validation: version.py → 1.1.0, CHANGELOG finalized, commit `f6332fb`, annotated tag, exe rebuilt (title "v1.1.0" validated) + `E5063A-Data-Collector-v1.1.0-win64.zip` attached to the GitHub Release (notes state the validation status honestly). Recovered the original 2026-06-04 build from `REPORT/20260604/E5063A-Data-Collector/` backup → attached to the v1.0.0 release (that build predates in-app versioning — no version in its title). Learned + codified (versioning doc §7): GitHub release notes render single newlines as `<br>` (comment-style GFM) — write ONE source line per paragraph; both releases re-edited. S-19 → "Released; field validation pending". Parsed `REPORT/20260729/20260729.pdf` (progress deck) → `20260729_corrected.md` (spelling/grammar + factual fixes: perf_counter_ns name, MIRDC, software-not-firmware, IO-Libraries caveat). | Claude (with Aunuun) |
