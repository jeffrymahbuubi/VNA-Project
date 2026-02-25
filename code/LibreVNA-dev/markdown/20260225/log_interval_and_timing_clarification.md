# Log Interval & VNA Timing Units — Clarification Notes
**Date:** 2026-02-25

---

## 1. Is `Log Interval(ms)` User-Configured or Instrument-Determined?

The `Log Interval(ms)` field in the Keysight E5063A Dataflux CSV is a **user-configured
parameter** entered in the Data Flux panel before pressing Record. It is not automatically
derived from sweep speed after the fact.

**Evidence from `Dataflux.csv`:**
- Header declares `Log Interval(ms),20` — a round number, hallmark of user entry.
- Actual inter-row timestamp gaps in the data are **~21–26 ms**, slightly above the declared
  20 ms due to sweep-boundary quantization (the instrument logs on sweep completion, not on a
  free-running timer).

**What the user configures on the Keysight Data Flux panel:**
1. Which marker to log (set to minimum-tracking mode separately)
2. Log Interval (ms) — minimum time between successive log entries
3. Number of data points to record (count)

---

## 2. Log Interval vs. Sweep Time — Physical Constraint

The Log Interval is **not purely arbitrary**. It is user-set but subject to a hard physical
lower bound:

> **You cannot log faster than one completed sweep.**

Each CSV row requires one complete S11 sweep to extract the minimum-tracking marker value.
Therefore:

```
Effective log interval = max(user_set_log_interval, actual_sweep_time)
```

### Two scenarios

| Scenario | User sets Log Interval | Actual sweep time | Effective behaviour |
|----------|----------------------|-------------------|---------------------|
| Interval > sweep time | 20 ms | ~11 ms | ~50 rows/s — deliberate decimation (skips some sweeps) |
| Interval < sweep time | 5 ms | ~200 ms | ~5 rows/s — instrument ignores 5 ms; logs every completed sweep |

In the second case the instrument silently clamps the effective interval to the sweep time.
The declared `Log Interval` in the header reflects what the user typed, not what was achieved.

### Practical example — 200–250 MHz, 50 kHz IFBW, 801 points

```
Approx sweep time ≈ (1 / IFBW) × points × overhead_factor
                  ≈ (1 / 50 000) × 801 × ~3
                  ≈ ~48 ms  →  ~21 Hz maximum log rate
```

Setting `Log Interval = 20 ms` at this configuration would be silently rounded up to ~48 ms.
Setting it to 100 ms would achieve true decimation (logs roughly every other sweep).

---

## 3. Understanding the "ms" Unit in VNA Context

**ms = milliseconds = 1/1000 of a second**

> **Higher ms → more time elapsed → SLOWER**
> **Lower ms → less time elapsed → FASTER**

### Examples

| Parameter | Value | Meaning |
|-----------|-------|---------|
| Sweep time | 11 ms | Fast — ~91 sweeps/sec theoretical max |
| Sweep time | 200 ms | Slow — ~5 sweeps/sec |
| Log Interval | 20 ms | Frequent logging — 50 rows/sec |
| Log Interval | 1000 ms | Infrequent logging — 1 row/sec |

---

## 4. Hz ↔ ms Conversion

Sweep **rate** (Hz) and sweep **time** (ms) are inverses:

```
sweep_rate_Hz  = 1000 / sweep_time_ms
sweep_time_ms  = 1000 / sweep_rate_Hz
```

| Sweep rate | Sweep time |
|-----------|------------|
| 5 Hz | 200 ms |
| 16 Hz | 62.5 ms |
| 50 Hz | 20 ms |

---

## 5. IFBW Impact on Sweep Time

IFBW is in **Hz** and directly controls per-point measurement time:

> **Higher IFBW (Hz) → shorter per-point time → lower sweep time (ms) → faster**

| IFBW | Approx sweep time (801 pts) | Sweep rate |
|------|---------------------------|------------|
| 1 kHz | ~800 ms | ~1.25 Hz |
| 10 kHz | ~80 ms | ~12 Hz |
| 50 kHz | ~48 ms | ~21 Hz |
| 70 kHz | ~11 ms | ~90 Hz |

**Trade-off:** Higher IFBW = faster sweep = noisier measurement (less averaging per point).
Lower IFBW = slower sweep = cleaner measurement.

---

## 6. Rule of Thumb

> In **time** measurements (ms): **smaller = faster**.
> In **rate** measurements (Hz): **larger = faster**.

---

## 7. Implication for LibreVNA Monitor Mode

The LibreVNA has no Log Interval user-setting. It logs every completed sweep and reports the
`Log Interval(ms)` field in the Dataflux-compatible CSV as the **retroactively computed mean
inter-row gap** (`mean_dt * 1000`). This fills the header field correctly without requiring
user input, and accurately reflects the achieved logging cadence rather than an aspirational
target value.
