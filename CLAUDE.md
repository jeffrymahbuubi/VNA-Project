# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment & Running Scripts

- Python is managed via `uv`. Always run scripts with `uv run python <script>`, never system Python directly.
- The virtual environment lives at `code/.venv`. Dependencies are in `code/requirements.txt`.
- LibreVNA-GUI binary: `code/LibreVNA-dev/tools/LibreVNA-GUI`. Scripts 3+ auto-start it in headless mode (`QT_QPA_PLATFORM=offscreen`) and poll TCP port 1234 for readiness.

## Repository Layout

```
code/
├── LibreVNA-dev/
│   ├── scripts/           # All automation scripts + libreVNA.py wrapper
│   ├── calibration/       # SOLT cal file (JSON, loaded via SCPI)
│   ├── data/              # Timestamped CSV outputs from script runs
│   ├── notebook/          # Jupyter notebooks for post-run analysis
│   ├── markdown/          # Written analysis docs, bug reports, latency breakdowns
│   └── tools/             # LibreVNA-GUI binary
├── requirements.txt
└── .venv/
.claude/agents/            # Custom agent specs (librevna-python-expert, rf-data-analyst)
```

## Script Numbering & Progression

Scripts build on each other. Each is self-contained but shares helpers via importlib (digit-prefixed filenames prevent normal `import`).

| Script | Purpose | Key technique |
|--------|---------|---------------|
| `1_librevna_cal_check.py` | Verify cal file + device identity | Cal JSON parse, `*IDN?` |
| `2_s11_cal_verification_sweep.py` | Single S11 sweep, save CSV | Trigger-and-poll, exports `connect_and_verify` and `load_calibration` |
| `3_sweep_speed_baseline.py` | 30-sweep single-sweep benchmark | Auto-starts GUI, imports `load_calibration` from script 2 |
| `4_ifbw_parameter_sweep.py` | IFBW impact on speed/jitter | 3 IFBWs × 10 sweeps each |
| `5_continuous_sweep_speed.py` | 30-sweep continuous benchmark | Enables streaming server, uses `add_live_callback` on port 19001 |
| `6_librevna_gui_mode_sweep_test.py` | Unified single/continuous benchmark | Config-driven via `sweep_config.yaml`; multi-sheet xlsx export; dispatches mode via `--mode` flag |

### Script 6 — class hierarchy & CLI

```
BaseVNASweep (ABC)          — GUI lifecycle, cal load, xlsx export
├── SingleModeSweep         — ACQ:RUN trigger + ACQ:FIN? poll; defensive ACQ:STOP + SINGLE TRUE on entry
├── ContinuousModeSweep     — streaming callback on port 19001; sweep boundary = pointNum == 0
└── VNAGUIModeSweepTest     — dispatches to SingleModeSweep or ContinuousModeSweep via --mode
```

```bash
uv run python 6_librevna_gui_mode_sweep_test.py                          # single mode, default config
uv run python 6_librevna_gui_mode_sweep_test.py --mode continuous        # continuous mode
uv run python 6_librevna_gui_mode_sweep_test.py --config other.yaml      # alternate config
uv run python 6_librevna_gui_mode_sweep_test.py --no-save                # skip xlsx write
```

### sweep_config.yaml

All sweep parameters for script 6 live here (`scripts/sweep_config.yaml`). Structure:

```yaml
configurations:
  start_frequency: 2430000000      # Hz
  stop_frequency:  2450000000      # Hz
  num_points:      300
  stim_lvl_dbm:   -10
  avg_count:       1
  num_sweeps:      30              # sweeps per IFBW value

target:
  ifbw_values:                     # single int OR list of ints (Hz)
    - 50000
    - 10000
    - 1000
```

Output is a multi-sheet `.xlsx` workbook in `data/<YYYYMMDD>/` — one sheet per IFBW value.

## libreVNA.py — SCPI Wrapper Contract

- `vna.cmd(cmd)` — fire-and-forget; auto-checks `*ESR?` and raises on error bits. Pass `check=False` for commands that spuriously set CME (e.g., `DEV:PREF` set).
- `vna.query(query)` — send + read response; does **not** check ESR.
- `VNA:CAL:LOAD?` is a **query** despite the `?`-less appearance in docs. Use `vna.query()`.
- `add_live_callback(port, fn)` — opens a TCP stream to the given streaming port; `fn` is called once per JSON line. Runs on a background thread.
- Known bug at line 148: `len(self.live_callbacks)` should be `len(self.live_callbacks[port])`. Thread cleanup still works; just the join guard is wrong.

## SCPI Gotchas (read before writing any new script)

1. **Trigger mechanism:** In single-sweep mode, use `ACQ:RUN` to trigger each sweep. Do **not** rely on re-sending `FREQuency:STOP` — after a single sweep completes the GUI sets `running=false`, and `SettingsChanged()` (called by every frequency/param write) returns early when `!running`, so no new sweep starts and `TRACE:DATA?` returns stale data. `ACQ:RUN` unconditionally calls `Run()` → `ConfigureDevice()`, which is the only reliable per-sweep trigger. (Confirmed in `vna.cpp:1092-1096` and `vna.cpp:1545-1546`.)
2. **Script 5 leaves the GUI in continuous mode** (`ACQ:SINGLE FALSE`). Any single-sweep script that runs after script 5 must open with `ACQ:STOP` then `ACQ:SINGLE TRUE`, or `ACQ:FIN?` will return TRUE immediately from background sweeps.
3. **Streaming servers are disabled by default.** Enable with `:DEV:PREF StreamingServers.VNACalibratedData.enabled true` then `:DEV:APPLYPREFERENCES`. APPLYPREFERENCES crashes/restarts the GUI — reconnect after. The pref persists on disk, so subsequent GUI starts have streaming enabled.
4. **`DEV:PREF` set commands** return CME in ESR even on success. Always use `check=False`.

## Streaming Ports

| Port | Stream |
|------|--------|
| 19000 | VNA Raw (uncalibrated) |
| 19001 | VNA Calibrated |
| 19002 | VNA De-embedded |

Each point arrives as a JSON object with `pointNum`, `frequency` (Hz), `Z0`, and `measurements` (e.g., `S11` as complex). A new sweep starts when `pointNum == 0`.

## Sweep Rate Reference

| Mode | Rate | Notes |
|------|------|-------|
| Single-sweep, 0.1 s poll | 3.49 Hz | Bimodal due to poll granularity |
| Single-sweep, 0.01 s poll | 5.13 Hz | GUI "Step 2" overhead dominates |
| Single-sweep, hot re-trigger | 24.4 Hz | Requires streaming enabled; first sweep is cold (~90 ms) |
| Continuous + streaming | 16.95 Hz | Best sustained rate via SCPI path |
| USB direct (theoretical) | ~33 Hz | Bypasses GUI entirely; not yet implemented |

## Calibration

Single cal file: `calibration/SOLT_1_2_43G-2_45G_300pt.cal`. Covers 2.43–2.45 GHz, 300 points. Load via:
```
vna.query("VNA:CAL:LOAD? <absolute_path_to_.cal>")
```
Returns `"TRUE"` or `"FALSE"`.

## Notebooks

- Use `NotebookEdit` tool for `.ipynb` files — the `Edit` tool will error on them.
- When running `nbconvert`, `cd` into the notebook directory first and pass only the filename to `--output`.

## Next: USB Direct Protocol

Docs (`USB_protocol_v12.pdf`, `Device_protocol_v13.pdf`) have been fully read and summarised in `markdown/20260205/part2-continuous-sweep-implementation.md` §7.11. Key facts:
- VID `0x1209`, PID `0x4121`; OUT `0x01`, IN data `0x81`
- Packet frame: `0x5A` + length (2B LE) + type (1B) + payload + CRC32 (4B LE). CRC is always `0x00000000` on VNADatapoint packets — do not validate.
- `SweepSettings` (type 2) with SO=0 auto-loops indefinitely (~33 Hz path).
- USB delivers raw receiver data; host must assemble S-params and apply calibration.
