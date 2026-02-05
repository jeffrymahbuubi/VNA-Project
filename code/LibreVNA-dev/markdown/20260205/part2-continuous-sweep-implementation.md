# Part 2 — Continuous Sweep Implementation & Full Results Summary

**Date:** 2026-02-05
**Device:** LibreVNA · Serial 206830535532 · Firmware v1.6.4
**Calibration:** SOLT_1 (2.43–2.45 GHz, 300 pts)
**Scripts:** `3_sweep_speed_baseline.py`, `4_ifbw_parameter_sweep.py`,
`5_continuous_sweep_speed.py`
**Previous summary:** `../20260204/part2-sweep-speed-analysis.md`

---

## 1. Previous Work Recap (2026-02-04)

### 1.1 Scripts 3 & 4 — single-sweep SCPI baseline

Script 3 ran 30 consecutive S11 sweeps in single-sweep mode: each sweep
was re-triggered by re-sending `:VNA:FREQuency:STOP`, then polled with
`:VNA:ACQ:FIN?` until TRUE.  Script 4 repeated that pattern at three
IFBW settings (50 kHz / 10 kHz / 1 kHz), 10 sweeps each.

Two successive iterations of these scripts were run during the first
session.  The root-cause investigation identified two independent
bottlenecks (full detail in `../20260204/part2-sweep-speed-analysis.md`):

| Layer | Cause | Status |
|---|---|---|
| A | `time.sleep(0.1)` in the poll loop created a bimodal distribution | **Fixed** — interval reduced to 0.01 s |
| B | LibreVNA-GUI "Step 2" sweep-preparation overhead (~165 ms) paid on every single-sweep trigger | **Remains in single-sweep mode** |

### 1.2 Script 3 final results (single-sweep, 0.01 s poll)

| Metric | Mean | Std Dev | Min | Max |
|---|---|---|---|---|
| Sweep Time (s) | 0.1949 | 0.0012 | 0.1937 | 0.1978 |
| Update Rate (Hz) | 5.13 | 0.03 | 5.05 | 5.16 |

### 1.3 Script 4 final results (IFBW sweep)

| IFBW | Mean Sweep Time (s) | Update Rate (Hz) | Noise Floor (dB) | Trace Jitter (dB) |
|---|---|---|---|---|
| 50 kHz | 0.1953 | 5.12 | −54.11 | 2.3598 |
| 10 kHz | 0.2460 | 4.07 | −53.83 | 1.5426 |
| 1 kHz  | 0.8094 | 1.24 | −53.73 | 0.3111 |

---

## 2. Future Work 3.1 — Continuous Sweep + Streaming (Implemented)

### 2.1 What was done

`5_continuous_sweep_speed.py` implements the path described in the
previous summary's Section 3.1 and confirmed by LibreVNA creator Jan
Käberich (groups.io thread #111647361).  It replaces the single-sweep
trigger-and-poll loop with two architectural changes:

1. **Continuous sweep mode.**  `:VNA:ACQ:SINGLE FALSE` followed by
   `:VNA:ACQ:RUN` puts the GUI into a free-running loop.  Sweeps execute
   back-to-back with no per-sweep "Step 2" re-preparation.

2. **Push-based streaming callback.**  The GUI's VNA-Calibrated-Data
   streaming server (TCP port 19001) pushes one JSON line per frequency
   point as each sweep progresses.  `libreVNA.add_live_callback()` opens
   that connection and dispatches each line to a user-supplied callback
   on a dedicated reader thread.  The callback timestamps sweep start
   (`pointNum == 0`) and sweep end (`pointNum == 299`).  No
   `:VNA:ACQ:FIN?` polling exists anywhere in the script.

### 2.2 Enabling the streaming server

All LibreVNA streaming servers are **disabled by default** (confirmed in
`preferences.h` source).  The calibrated-data server was enabled via
SCPI before the first run:

```
:DEV:PREF StreamingServers.VNACalibratedData.enabled true
:DEV:APPLYPREFERENCES
```

`:DEV:APPLYPREFERENCES` saves the preference to disk but **crashes /
restarts the GUI process**.  After the crash the GUI was restarted with:

```bash
QT_QPA_PLATFORM=offscreen /path/to/LibreVNA-GUI --port 1234 &
```

On restart it read the saved preference and opened port 19001
automatically.  SCPI remained on the user's custom port 1234.

### 2.3 Streaming data format

Each JSON line pushed by the server contains (confirmed in
`streamingserver.cpp`):

| Field | Type | Notes |
|---|---|---|
| `pointNum` | int | 0-based index within sweep |
| `frequency` | float | Hz (present for non-zerospan sweeps) |
| `Z0` | float | Reference impedance; presence confirms VNA data |
| `measurements` | dict | `S11_real` / `S11_imag` split; wrapper reassembles to `complex` before callback |

The wrapper's `__live_thread` performs the JSON decode and
real/imag → complex conversion before invoking the callback, so the
callback receives a fully-parsed Python dict.

### 2.4 Callback design

The callback is intentionally minimal to avoid slowing the reader
thread:

- `pointNum == 0`  →  record `sweep_start_time`, reset the per-sweep
  S11 accumulator.
- Every point  →  append the raw `complex` S11 value.
- `pointNum == 299`  →  record `sweep_end_time`, snapshot the
  accumulator, increment the counter, set a `threading.Event` when 30
  sweeps are collected.

All shared state is guarded by a single `threading.Lock`.  The main
thread blocks on `event.wait(timeout=300)` — no busy loop.

dB conversion and the frequency axis (via `numpy.linspace`) are
deferred to after the callback loop ends.

---

## 3. Script 5 Results (continuous sweep, 30 sweeps, IFBW 50 kHz)

Two timing metrics are reported.  **Sweep Duration** measures the time
from the first streamed point to the last streamed point within a single
sweep — pure acquisition time as seen by the host.  **Inter-Sweep
Interval** measures the time between consecutive sweep completions — the
true repetition rate, including any back-to-back gap the GUI inserts.
Inter-Sweep Interval is the apples-to-apples equivalent of Script 3's
per-cycle wall time.

| Metric | Mean | Std Dev | Min | Max |
|---|---|---|---|---|
| Sweep Duration (s) | 0.0520 | 0.0004 | 0.0505 | 0.0522 |
| Duration Rate (Hz) | 19.25 | 0.15 | 19.17 | 19.79 |
| Inter-Sweep Interval (s) | 0.0590 | <0.0001 | 0.0589 | 0.0591 |
| Inter-Sweep Rate (Hz) | **16.95** | 0.01 | 16.93 | 16.97 |

- The inter-sweep interval is **rock-steady**: 29 values span only
  0.0589–0.0591 s (< 0.2 ms peak-to-peak).
- S11 trace range on the last sweep: −81.2 dB to −48.1 dB — confirms
  calibration was correctly applied via the calibrated streaming channel.

---

## 4. Three-Way Comparison — All Approaches

| Metric | Script 3 (single-sweep, 0.1 s poll) | Script 3 (single-sweep, 0.01 s poll) | Script 5 (continuous + streaming) |
|---|---|---|---|
| Mean cycle time (s) | 0.3002 | 0.1949 | **0.0590** |
| Mean rate (Hz) | 3.49 | 5.13 | **16.95** |
| Std Dev (s) | 0.0536 | 0.0012 | <0.0001 |
| Distribution | Bimodal | Unimodal | Unimodal |
| Step 2 overhead | Paid | Paid | **Eliminated** |
| Speedup vs 0.01 s poll | — | 1× | **3.30×** |

---

## 5. Latency Budget — Continuous Mode

The 59 ms inter-sweep interval decomposes as follows.  All values are
derived from the measured data and the hardware spec sheet (10 k
points/s at 50 kHz IFBW).

| Layer | Time | Notes |
|---|---|---|
| Raw ADC acquisition (300 pts @ 10 k pts/s) | ~30 ms | Hardware floor; unchanged across all modes |
| GUI continuous-mode internal overhead | ~22 ms | Sweep orchestration, calibration application, TCP buffering |
| Back-to-back gap (end of sweep N → start of sweep N+1) | ~7 ms | `59 ms − 52 ms`; gap between last point of one sweep and first point of next |
| **Total measured inter-sweep interval** | **~59 ms (16.95 Hz)** | |

For comparison, the single-sweep latency budget was:

| Layer | Time |
|---|---|
| Raw ADC acquisition | ~30 ms |
| GUI "Step 2" sweep-preparation | ~165 ms |
| Poll detection latency (0.01 s interval) | 0–10 ms |
| **Total** | **~195 ms (5.13 Hz)** |

Continuous mode eliminates the 165 ms Step 2 entirely.  The remaining
~29 ms of non-ADC overhead (22 ms internal + 7 ms gap) is the GUI TCP
dispatch path and is not reducible by host-side changes.

---

## 6. 25 Hz Target Assessment

| Approach | Achieved Rate | Gap to 25 Hz | Bottleneck |
|---|---|---|---|
| Single-sweep (0.01 s poll) | 5.13 Hz | 19.87 Hz | GUI Step 2 (165 ms) |
| Continuous + streaming | 16.95 Hz | 8.05 Hz | GUI TCP dispatch (~29 ms) |
| Direct USB to firmware (not implemented) | ~33 Hz (est.) | — | None; bypasses GUI entirely |

25 Hz requires ≤ 40 ms end-to-end.  The continuous-sweep approach
delivers 59 ms — the remaining 19 ms excess is inside the GUI process
and cannot be removed without bypassing it.  The only path to ≥ 25 Hz
within the current hardware is a **direct USB driver** that speaks the
LibreVNA firmware protocol (documented in `USB_protocol_v12.pdf` and
`Device_protocol_v13.pdf`), which would expose the raw 30 ms
acquisition time with no GUI in the loop.

---

## 7. Future Work — Direct USB Driver Implementation

This section consolidates all protocol-level detail needed to implement
a Python USB driver that bypasses the GUI entirely.  Source documents:
`USB_protocol_v12.pdf` (v12), `Device_protocol_v13.pdf` (v13).  The
existing C++ driver in the GUI source
(`LibreVNA-GUI/Device/LibreVNA/librevnausbdriver.cpp/.h`) serves as a
working reference implementation.

### 7.1 Architecture shift

```
Current (Script 5, 16.95 Hz):
  Python ──TCP:1234──► LibreVNA-GUI ──USB──► Firmware
                        │                      │
                        ◄──────USB─────────────┘
                        │  (GUI applies calibration)
                        ──TCP:19001──► Python callback

Target (direct USB, ~33 Hz est.):
  Python ──USB ep 0x01──► Firmware
           ◄──USB ep 0x81── (raw VNADatapoint stream)
  Python assembles S-parameters + applies calibration
```

The GUI disappears entirely.  All overhead it introduced (Step 2
sweep-preparation, TCP streaming dispatch, calibration application) is
removed.  The trade-off is that the host must perform S-parameter
assembly and calibration correction itself.

### 7.2 USB device identity and endpoints

| Parameter | Value | Notes |
|---|---|---|
| VID | `0x0483` (v12) / `0x1209` (v13) | v13 doc uses VIDPID.org VID |
| PID | `0x4121` | Unchanged across docs |
| Endpoint OUT | `0x01` | Host → Device (commands) |
| Endpoint IN (data) | `0x81` | Device → Host (responses + data stream) |
| Endpoint IN (debug) | `0x82` | Device → Host (ASCII debug log; optional) |

Python library: `pyusb` (`usb.core.find`, `usb.core.Device`).

### 7.3 Packet framing

Every message in both directions uses the same binary frame:

```
┌──────────┬────────────┬──────────┬─────────────┬────────────┐
│ Header   │ Length     │ Type     │ Payload     │ CRC32      │
│ 1 byte   │ 2 bytes LE │ 1 byte   │ variable    │ 4 bytes LE │
│ 0x5A     │ total size │          │             │            │
└──────────┴────────────┴──────────┴─────────────┴────────────┘
```

- **Length** = total frame size (1 + 2 + 1 + payload_len + 4).
- **CRC32** is validated on most packets.  **Exception:** `VNADatapoint`
  (type 27) always carries CRC = `0x00000000` — firmware skips the
  calculation at high IFBW to avoid missing points.  The host must
  **not** validate CRC on type 27.

### 7.4 Connection handshake

The first packet the host must send after USB enumeration is
`RequestDeviceInfo` (type 15, no payload).  The firmware responds with
`DeviceInfo` (type 5), which contains the protocol version, firmware
version, and a hardware-capability bitmap.  The host should parse the
protocol version to confirm compatibility before sending any sweep
commands.

### 7.5 Sweep configuration — `SweepSettings` (type 2)

A single outbound packet configures and starts a sweep.  Payload layout
(all little-endian):

| Offset | Size | Field | Unit / Notes |
|---|---|---|---|
| 0 | 8 | `f_start` | UINT64, Hz |
| 8 | 8 | `f_stop` | UINT64, Hz |
| 16 | 2 | `points` | UINT16 |
| 18 | 4 | `IF_bandwidth` | UINT32, Hz |
| 22 | 2 | `cdbm_excitation_start` | INT16, power in 1/100 dBm |
| 24 | 2 | `Configuration` | Bitmap; bit 0 = SO flag (see §7.6) |
| 26 | 2 | `Stages` | Bitmap; port/stage assignments |
| 28 | 2 | `cdbm_excitation_stop` | INT16 |

The firmware replies with `Ack` (type 7, no payload) and immediately
begins sweeping.

### 7.6 SO flag — auto-loop vs standby

The **SO (Standby Operation)** flag is the single most important bit for
achieving maximum sweep rate:

| SO | Firmware behaviour | Re-trigger required? |
|---|---|---|
| `0` | **Auto-loop.** After the first sweep completes, firmware loops
back to the start frequency and sweeps again — indefinitely, with no
host intervention. | No.  One `SweepSettings` starts an infinite stream. |
| `1` | **Standby.** Firmware stops after each sweep and waits for an
`InitiateSweep` packet (type 32, no payload) before starting the next. | Yes, once per sweep. |

**SO = 0 is the path to ~33 Hz.**  The loop runs entirely inside the
firmware.  The host simply reads `VNADatapoint` packets from endpoint
`0x81` as fast as they arrive.  There is no per-sweep round-trip
latency.

SO = 1 is useful for on-demand single sweeps with minimum latency (e.g.
triggered measurements), but adds one host→device→host round-trip per
sweep.

### 7.7 Receiving sweep data — `VNADatapoint` (type 27)

One packet per frequency point arrives on endpoint `0x81` during every
sweep.  Payload layout:

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 8 | `Frequency` | UINT64, Hz |
| 8 | 2 | `PowerLevel` | INT16 |
| 10 | 2 | `PointNumber` | UINT16, 0-based; resets each sweep |
| 12 | N×4 | Real values | FLOAT[], one per receiver |
| 12+N×4 | N×4 | Imag values | FLOAT[], same order |
| 12+2N×4 | N | Bitmasks | UINT8[], one per receiver |

Array length N is derived from the packet size:

```
N = (total_packet_size − 12) / 9      # 4 (real) + 4 (imag) + 1 (mask)
```

(The 12 accounts for Frequency + PowerLevel + PointNumber; CRC is
outside the payload.)

**CRC is always `0x00000000`** on this packet type — do not reject it.

### 7.8 Data-description bitmask and S-parameter assembly

Each bitmask byte identifies one receiver value:

| Bits | Meaning |
|---|---|
| 7–5 | Stage number (0-based) |
| 4–0 | Receiver source: 0 = Reference, 1 = Port1, 2 = Port2, … |

S-parameter assembly is a **host-side** operation.  The firmware
streams raw receiver amplitudes; the GUI normally performs this math.
For S11:

```
S11 = Port1_receiver / Reference_receiver
```

Both complex values must come from the **same stage**.  Steps:

1. Parse the bitmask array.  Group values by stage.
2. Within each stage, locate the Reference (source = 0) and Port1
   (source = 1) complex values: `complex(Real[i], Imag[i])`.
3. Divide: `S11 = Port1 / Reference`.

For S21 the divisor is the same Reference; the numerator is Port2
(source = 2).  The v13 protocol document (pages 19–21) contains a
worked example for S21 assembly.

### 7.9 Calibration — scikit-rf SOLT workflow

The streaming server path (Script 5) used port 19001 (VNA Calibrated
Data) and received calibration-corrected S11 directly.  The USB path
delivers **uncalibrated** raw receiver data.  Calibration correction
must be applied by the host.  The chosen library is
**scikit-rf** (`skrf`), which provides a full 12-term SOLT
calibration class — no need to implement the error-correction math
from scratch.

#### 7.9.1 Two-stage pipeline

scikit-rf's `SOLT` class and `apply_cal()` operate on assembled
S-parameter `skrf.Network` objects.  It does not accept raw receiver
voltages directly.  The USB data path therefore has two sequential
stages:

```
Stage 1 — S-parameter assembly (§7.8, host-side)
  Raw receivers from VNADatapoint
      Port1_complex / Reference_complex  →  uncorrected S11 (per point)
  Wrap into skrf.Network(s11_uncorrected, frequency)

Stage 2 — Error correction (scikit-rf)
  cal = skrf.calibration.SOLT(ideals=..., measured=...)
  cal.run()
  s11_corrected = cal.apply_cal(s11_uncorrected_network)
```

Stage 1 is the bitmask decode + complex division already specified in
§7.8.  Stage 2 is a single `apply_cal()` call once the error model has
been built.

#### 7.9.2 Building the SOLT error model — calibration standards

`skrf.calibration.SOLT` requires two parallel lists of
`skrf.Network` objects:

| Parameter | Content |
|---|---|
| `ideals` | Known (ideal) S-parameter responses of Short, Open, Load, Through |
| `measured` | Actual VNA measurements of the same standards |

The ideal responses are fixed constants (short = −1, open = +1, load = 0,
through = identity) and can be generated with `skrf.media.DefinedAEpTandZ0`.
The measured responses must come from the instrument.  Two options:

| Option | How | Trade-off |
|---|---|---|
| **Re-measure via USB** (recommended) | Connect each standard to the ports, run a sweep via the USB driver, assemble S-params (Stage 1), feed into `SOLT` as `measured` | Cleanest integration.  No file-format reverse-engineering.  Same physical standards already used to create the existing `.cal` file. |
| Extract from existing `.cal` file | Reverse-engineer the `.cal` binary format from GUI source in `LibreVNA-GUI/Device/LibreVNA/`, parse error coefficients or raw standard measurements out | Skips remeasurement but requires source archaeology; file format is undocumented. |

Re-measuring via USB is recommended.  It uses the same workflow as the
DUT sweeps (no new code path) and is exactly how the scikit-rf SOLT
tutorial is designed to operate.

#### 7.9.3 Sequencing recommendation

The sweep rate target (33 Hz) is independent of calibration.  The
recommended iteration order is:

1. **Iteration A — speed benchmark (uncalibrated):** Confirm the
   auto-loop USB driver delivers 30 sweeps at ~33 Hz.  Log timing CSV
   in the same format as `continuous_sweep_speed_*.csv`.  Stage 1
   (S-parameter assembly) is exercised here; Stage 2 is skipped.
2. **Iteration B — calibration integration:** Re-measure SOLT
   standards via USB.  Build the `skrf.calibration.SOLT` error model.
   Apply `cal.apply_cal()` to the DUT sweeps.  Compare the corrected
   S11 trace against the Script 5 baseline
   (`continuous_sweep_last_trace_20260205_143650.csv`) to confirm
   correctness.

### 7.10 Existing reference implementation

The GUI's own USB driver is in:

```
LibreVNA-GUI/Device/LibreVNA/librevnausbdriver.cpp
LibreVNA-GUI/Device/LibreVNA/librevnausbdriver.h
```

This C++ code performs enumeration, handshake, `SweepSettings`
construction, and `VNADatapoint` parsing against the same firmware.  It
is the closest thing to a working reference.  Key functions to study
before writing the Python equivalent:

- Sweep packet construction (field layout and endianness)
- The read loop on endpoint `0x81` (buffering, frame boundary detection)
- `VNADatapoint` parsing (array length calculation, bitmask decode)

### 7.11 Implementation checklist (next iteration)

#### Iteration A — USB driver + speed benchmark (uncalibrated)

| # | Task | Depends on |
|---|---|---|
| 1 | Enumerate device with `pyusb`; confirm VID/PID and endpoints | — |
| 2 | Implement packet framer (header + length + type + payload + CRC32) | — |
| 3 | Send `RequestDeviceInfo`; parse `DeviceInfo`; verify protocol version | 1, 2 |
| 4 | Send `SweepSettings` with SO = 0 (auto-loop, 300 pts, 50 kHz IFBW, 2.43–2.45 GHz) | 3 |
| 5 | Read loop: bulk-read endpoint `0x81`, frame-align, parse `VNADatapoint` | 4 |
| 6 | Assemble S11 from raw receivers using bitmask decode (§7.8) | 5 |
| 7 | Timestamp `PointNumber == 0` and `PointNumber == 299`; compute inter-sweep interval | 5 |
| 8 | Run 30 sweeps; log timing CSV in same format as `continuous_sweep_speed_*.csv` | 7 |
| 9 | Compare achieved rate against the 33 Hz estimate | 8 |

#### Iteration B — scikit-rf SOLT calibration integration

| # | Task | Depends on |
|---|---|---|
| 10 | Install / confirm `scikit-rf` (`pip install scikit-rf`) in the project environment | — |
| 11 | Re-measure SOLT standards via USB: connect Short, Open, Load, Through one at a time; run a sweep for each; assemble S-params using the same Stage 1 code from task 6 | 6 |
| 12 | Build ideal standard networks using `skrf.media.DefinedAEpTandZ0` (short = −1, open = +1, load = 0, through = identity) at the same frequency axis as task 11 | 10 |
| 13 | Construct `skrf.calibration.SOLT(ideals=..., measured=...)`; call `cal.run()`; inspect `cal.coefs_12term` to confirm error coefficients are populated | 11, 12 |
| 14 | Apply calibration to DUT sweeps: wrap uncorrected S11 arrays from task 6 into `skrf.Network`; call `cal.apply_cal(network)` | 13 |
| 15 | Compare corrected S11 trace against Script 5 baseline (`continuous_sweep_last_trace_20260205_143650.csv`); confirm agreement within expected noise floor | 14 |

---

## 8. Outstanding Notes

- **Streaming server enable procedure:** All VNA streaming servers are
  disabled by default.  Enable via `:DEV:PREF` + `:DEV:APPLYPREFERENCES`.
  The latter saves to disk and restarts the GUI; reconnect the SCPI
  socket after.  Restart command:
  `QT_QPA_PLATFORM=offscreen ./LibreVNA-GUI --port 1234 &`

- **Port mapping:**
  VNA Raw = 19000, VNA Calibrated = **19001**, VNA De-embedded = 19002.
  Script 5 uses 19001 because calibration was loaded; this gives
  calibrated S11 data directly from the stream with no post-processing
  needed.

- **`libreVNA.py` line 148 bug:** `remove_live_callback` checks
  `len(self.live_callbacks)` (the dict) instead of
  `len(self.live_callbacks[port])` (the port's list).  The reader thread
  still self-exits when the list empties (line 154 checks it correctly),
  so the bug is cosmetic — the thread is not joined/cleaned up but does
  terminate.

- **Output files produced by Script 5:**
  `data/continuous_sweep_speed_20260205_143650.csv` (30-row timing
  record) and
  `data/continuous_sweep_last_trace_20260205_143650.csv` (300-point
  calibrated S11 trace).
