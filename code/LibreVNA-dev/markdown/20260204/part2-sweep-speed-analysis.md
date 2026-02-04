# Part 2 — Sweep Speed Analysis & Root-Cause Summary

**Date:** 2026-02-04
**Device:** LibreVNA · Serial 206830535532 · Firmware v1.6.4
**Calibration:** SOLT_1 (2.43–2.45 GHz, 300 pts)
**Scripts:** `3_sweep_speed_baseline.py`, `4_ifbw_parameter_sweep.py`

---

## 1. Likely Cause & Current Solution

### 1.1 Root cause — two layers, one fixed, one remaining

The 25 Hz target (≤ 40 ms per sweep) was not met. Investigation and
forum research identified **two independent causes**, addressed in order.

#### Layer A — `time.sleep()` polling overhead (FIXED)

The original polling loop slept **0.1 s** between every `ACQ:FIN?`
query. Because the hardware sweep completes in tens of milliseconds, the
100 ms sleep was longer than the sweep itself. The result was a
**bimodal sweep-time distribution**: sweeps detected on the first poll
after a sleep landed at ~0.18 s; sweeps that missed that poll and waited
for the next one landed at ~0.32 s. The 0.14 s gap between clusters is
exactly one sleep interval plus TCP round-trip overhead.

**Solution applied:** `POLL_INTERVAL_S` reduced from `0.1` to `0.01` in
both scripts.

| Metric | Before (0.1 s poll) | After (0.01 s poll) |
|---|---|---|
| Mean sweep time | 0.3002 s | 0.1949 s |
| Std dev | 0.0536 s | 0.0012 s |
| Distribution | Bimodal | Unimodal |

The bimodal artifact disappeared entirely and std dropped **45×**.
Mean sweep time dropped **35 %** (from 0.30 s to 0.195 s).

#### Layer B — LibreVNA-GUI single-sweep preparation overhead (REMAINING)

With polling overhead removed, every sweep converges to a consistent
**~195 ms**. This is not host-side latency — it is the end-to-end
sweep-cycle time through LibreVNA-GUI in single-sweep mode.

The LibreVNA spec sheet states **10 k points/s** at 50 kHz IFBW. For
300 points that predicts a raw acquisition time of **30 ms**. The
measured 195 ms is 6.5× longer. The difference (~165 ms) is GUI
internal overhead.

**Jan Käberich (LibreVNA creator) confirmed this in the support forum**
(groups.io thread #111647361). He measured his own device and stated:

> "When I use continuous sweeps, a sweep takes about 100 ms.
> When I use single sweeps, the time it takes from issuing the command
> to a completed sweep is about 430 ms.
> This means **step 2 takes about 330 ms** and is responsible for much
> of the delay."

He identified "Step 2" as **sweep preparation inside the GUI**, which
runs once per sweep in single-sweep mode but is **skipped entirely in
continuous sweep mode**. Our code uses single-sweep mode (send
`:VNA:FREQuency:STOP` to re-trigger each sweep), so it pays this
overhead on every iteration. This is the bottleneck that `time.sleep()`
cannot fix.

### 1.2 Latency budget (current state)

| Layer | Time | Reducible by host? |
|---|---|---|
| Raw ADC acquisition (300 pts @ 10 k pts/s) | ~30 ms | No — hardware |
| GUI sweep-preparation overhead (Step 2) | ~165 ms | No — single-sweep mode |
| Poll detection latency (0.01 s interval) | 0–10 ms | Already minimised |
| **Total measured** | **~195 ms (5.1 Hz)** | — |

25 Hz requires ≤ 40 ms end-to-end. The GUI overhead alone (165 ms) is
4× that budget, so **25 Hz is not reachable in the current
single-sweep SCPI approach**, regardless of poll interval.

---

## 2. Current Results

### 2.1 Part 2(a) — Sweep Speed Baseline (30 sweeps, IFBW 50 kHz)

| Metric | Mean | Std Dev | Min | Max |
|---|---|---|---|---|
| Sweep Time (s) | 0.1949 | 0.0012 | 0.1937 | 0.1978 |
| Update Rate (Hz) | 5.13 | 0.03 | 5.05 | 5.16 |

- Distribution is unimodal and tight (std 1.2 ms).
- Update rate **5.13 Hz** — below the 25 Hz target.
- The remaining overhead is inside LibreVNA-GUI, not in the host script.

### 2.2 Part 2(b) — IFBW Parameter Sweep (10 sweeps per IFBW)

| IFBW | Mean Sweep Time (s) | Update Rate (Hz) | Noise Floor (dB) | Trace Jitter (dB) |
|---|---|---|---|---|
| 50 kHz | 0.1953 | 5.12 | −54.11 | 2.3598 |
| 10 kHz | 0.2460 | 4.07 | −53.83 | 1.5426 |
| 1 kHz  | 0.8094 | 1.24 | −53.73 | 0.3111 |

| Ratio (vs 50 kHz baseline) | 50 kHz → 10 kHz | 50 kHz → 1 kHz |
|---|---|---|
| Sweep Time | 1.26× | 4.14× |
| Jitter | 0.65× | 0.13× |

Key observations:
- **Sweep times are now correctly resolved across all three IFBWs.**
  The previous 0.1 s poll masked the 50 kHz vs 10 kHz difference
  entirely (both rounded to ~0.32 s). The 0.01 s poll reveals a clear
  1.26× difference.
- **Noise floor is IFBW-independent** (~−54 dB across all settings).
  With a calibrated 50 Ω load this is expected — the value is the
  calibration residual, not the receiver noise floor.
- **Trace jitter improves monotonically** with narrower IFBW:
  50 kHz → 10 kHz → 1 kHz reduces jitter by 0.65× then 0.20× per
  step. Narrower IFBW reduces the receiver noise bandwidth and produces
  more repeatable traces — textbook behaviour, confirms ADC/DSP chain
  integrity.
- **Speed vs quality trade-off:** 1 kHz IFBW gives 7.6× better jitter
  than 50 kHz at 4.14× the sweep time cost.

---

## 3. Future Improvements — Path to ≥ 25 Hz

### 3.1 Continuous sweep mode + streaming server (near-term)

Jan Käberich's forum post and the official LibreVNA example
`capture_live_data.py` describe the supported path:

1. Set the VNA into **continuous sweep mode** (the GUI free-runs
   sweeps back-to-back without Step 2 re-preparation).
2. Connect to the **streaming server** TCP port via
   `libreVNA.add_live_callback()` (already present in `libreVNA.py`)
   to receive completed trace data as a push callback — no
   `ACQ:FIN?` polling needed.
3. Time each callback arrival to measure the true continuous-sweep
   rate.

Jan measured **~100 ms per sweep** in continuous mode on his device
(512 pts, 10 kHz IFBW). Scaling to our config (300 pts, 50 kHz IFBW)
suggests a rate in the **50–100 ms** range, i.e. **10–20 Hz**. This
would be a 2–4× improvement over the current 5.1 Hz and would
eliminate the GUI Step 2 overhead entirely.

Reference: `https://github.com/jankae/LibreVNA/blob/master/Documentation/UserManual/SCPI_Examples/capture_live_data.py`

### 3.2 Direct USB interface (longer-term)

If continuous SCPI still falls short of 25 Hz, the remaining overhead
is inside the GUI application itself (TCP dispatch, sweep
orchestration). Bypassing the GUI entirely with a **direct USB
driver** that talks to the LibreVNA firmware would eliminate all GUI
latency and expose the raw 10 k points/s (30 ms for 300 pts = 33 Hz).
This would require firmware-level integration and is outside the
current scope.

### 3.3 Summary of expected rates by approach

| Approach | Estimated Rate | Notes |
|---|---|---|
| Current (single-sweep SCPI, 0.01 s poll) | ~5 Hz | Step 2 overhead dominates |
| Continuous sweep + streaming callback | 10–20 Hz | Eliminates Step 2; GUI TCP overhead remains |
| Direct USB to firmware | ~33 Hz | Eliminates GUI entirely; matches raw spec |
