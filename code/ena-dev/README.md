# ena-dev — Project-owned E5063A code

Companion to `LibreVNA-dev/`. Houses scripts, the **E5063A Data Collector GUI**
(the DataFlux replacement — built & live-validated, G-0…G-5), and run outputs
for the **Keysight E5063A ENA** migration documented in
`docs/e5063a-migration-spec.md`.

## Reuse policy (read this before adding code)

The third-party **Amp Qt6 suite** under `code/ena_qt6_suite/` is the canonical
I/O layer. **Reuse, do not fork.**

- Need to talk to the instrument? Use `core.visa_connection.ENAConnection`.
- Need a Qt6 widget with a built-in connection bar? Subclass
  `core.base_widget.ENABaseWidget`.
- Need SCPI strings/constants? Use `core.scpi_commands.SCPI`.

ena-dev imports those from `code/ena_qt6_suite/` via the small path shim in
`ena_dev_paths.py`. The shim adds `code/ena_qt6_suite/` to `sys.path` on
import. Always import it before `core.*`:

```python
import ena_dev_paths  # noqa: F401 — side-effect: registers ena_qt6_suite on sys.path
from core.visa_connection import ENAConnection
```

If a bug or genuine limitation in `ena_qt6_suite/` blocks ena-dev work, prefer
in-order:
1. Write a thin adapter / subclass in ena-dev/ that wraps the Amp class.
2. If adaptation isn't possible, patch `ena_qt6_suite/` and **record the patch
   in `docs/e5063a-migration-spec.md` §13 (Changelog)** so future re-syncs
   from the reference copy don't silently lose it.

## Layout

```
ena-dev/
├── __init__.py
├── ena_dev_paths.py        # sys.path shim (+ Windows VISA PATH fix) → makes core.* importable
├── README.md               (this file)
├── scripts/
│   ├── __init__.py
│   ├── probe_e5063a.py             # VISA discovery + *IDN? + config dump
│   ├── configure_e5063a.py         # recall a cal .sta + pin the locked operating point
│   ├── calibrate_e5063a.py         # host-driven 1-port S11 ECal (N7550A); saves grid-named .sta
│   ├── bench_e5063a_rates.py       # Phase-3 sweep-rate variants A–D
│   └── bench_e5063a_realworld.py   # single + continuous IFBW benchmark → LibreVNA-compatible xlsx
├── gui/                              # E5063A Data Collector (PySide6 MVP, built G-0…G-5)
│   ├── e5063a_data_collector.py      # entry point — launch this
│   ├── verify_backend_g2.py          # headless backend live-check (no GUI)
│   ├── qt_mcp_mockup.py              # qt-mcp smoke-test harness
│   └── mvp/
│       ├── __init__.py
│       ├── theme.py                  # design tokens + widget factories (paod_app pattern)
│       ├── model.py                  # dataclasses: DeviceInfo, CalibrationState, SweepConfig, MonitorConfig, MonitorRecord, AcquisitionMode, FilenameSpec, VNADataModel
│       ├── view_setup.py             # Screen 1: Connect/Configure/Calibrate/Filename/Verify
│       ├── view_acquire.py           # Screen 2: mode-adaptive Monitor / Sanity panels
│       ├── view_files.py             # Screen 3: History (list/delete/zip saved runs)
│       ├── backend_e5063a.py         # E5063ABackend — one ENAConnection session, all SCPI
│       ├── stub_backend.py           # StubE5063ABackend (offline dev, resource="STUB")
│       ├── controller.py             # BackendController — VISA on a dedicated QThread (NF-4)
│       ├── dataflux.py               # byte-exact Dataflux CSV writer (loads in 8_plot_monitor_data.py)
│       ├── sanity_xlsx.py            # Sanity-check multi-sheet xlsx writer (openpyxl)
│       └── main_window.py            # QStackedWidget shell + presenter
├── notebook/
│   ├── README.md           # code/-rooted Jupyter launch rules
│   └── 1_single_vs_continuous_sweep_e5063a.ipynb
└── data/
    └── YYYYMMDD/           # timestamped run outputs (xlsx/json/csv; cal/ holds host .sta copies)
```

## Running

Same convention as LibreVNA scripts: from the repo root,

```powershell
cd code
uv run python ena-dev/scripts/probe_e5063a.py        # check connection
uv run python ena-dev/scripts/calibrate_e5063a.py    # host-driven ECal (N7550A connected)
uv run python ena-dev/scripts/configure_e5063a.py    # recall a saved cal + pin operating point
```

The shared `code/.venv` already has PySide6, pyvisa (1.16.2), pyvisa-py (0.8.1),
pyqtgraph (0.14.0) and openpyxl (3.1.5) installed. KIOLS provides the actual VISA
backend on Windows — pyvisa-py is kept as a fallback. `ena_dev_paths.py` applies
the Windows VISA PATH fix automatically on import (migration-spec §3.6).

## Running the GUI (E5063A Data Collector)

```powershell
cd code\ena-dev\gui
../../.venv/Scripts/python.exe e5063a_data_collector.py          # against the instrument
# offline (no instrument): type resource "STUB" in the GUI's address box, then Connect
# agent-driven verify (qt-mcp): $env:QT_MCP_PROBE=1; ../../.venv/Scripts/python.exe e5063a_data_collector.py
```

Workflow: **Connect → Configure (grid/IFBW/power) → Calibrate (recall .sta or host ECal)
→ Verify → Proceed → [Monitor | Sanity Check] → save → History (Files…)**. Monitor logs
per-sweep min-S11 frequency to a Dataflux CSV at ~39 Hz; Sanity Check benchmarks per-IFBW
rates to xlsx. Headless backend check (no GUI): `uv run python ena-dev/gui/verify_backend_g2.py`.

> ⚠️ **Instrument hygiene:** the GUI restores live free-run + clears the front-panel
> message on connect/stop/close. **Stop any run (go idle) before closing — never kill the
> process mid-sweep** (a host killed mid-USBTMC-read makes the instrument log
> −420 "Query UNTERMINATED"; cleared by `:DISP:CCL`, auto-handled on next connect).

## References

- `docs/e5063a-migration-spec.md` — the living SPEC for this migration (status table §12).
- `docs/e5063a-gui-spec.md` — GUI build plan (port LibreVNA MVP, swap backend, G-0…G-6).
- `docs/e5063a-gui-ux-spec.md` — deterministic two-screen UX (Setup → Acquire): widget
  objectNames, state machine, filename rule, control→presenter→backend wiring.
- `docs/e5063a-gui-design-system.md` — View-layer tokens + factories (`theme.py`).
- `docs/qt-mcp-gui-automation.md` — agent-driven GUI build-verify loop (qt-mcp).
- `docs/E5063A_SCPI_Reference.md` — **consolidated SCPI command reference**
  (exhaustive, categorized, with syntax/params/usage). The working map when
  writing any E5063A SCPI. Built from the E5062A Programmer's Guide chunks,
  cross-checked vs the cheat-sheet + `ena_qt6_suite` constants. ⛔ Do **not**
  use `9018-07931…pdf` (it is a mislabeled 4155B manual — see that doc's §0).
- `code/ena_qt6_suite/DEVELOPER_GUIDE.md` — Amp suite's own dev guide
  (connection, SCPI cheat-sheet, new-app tutorial).
- `references/reports/20260504/E5063A_參考資料/` — collaborator handover
  (legacy DataFlux behaviour, SCPI cheat-sheet, official PDFs).
