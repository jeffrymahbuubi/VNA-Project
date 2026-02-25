# How to Effectively Increase VNA Sampling Rate
**Date:** 2026-02-25

---

## Core Formula

Sweep time on a step-frequency VNA (such as LibreVNA) is determined by:

```
sweep_time_ms = num_points × time_per_point_ms

time_per_point_ms ≈ 1000 / IFBW_Hz   (× overhead factor ~1.5–3×)

sweep_rate_Hz = 1000 / sweep_time_ms
```

Three levers directly reduce sweep time:

1. **Increase IFBW** — reduces time per point
2. **Reduce number of sweep points** — fewer points to measure
3. **Narrow the frequency span + reduce points** — focus only on the region of interest

---

## Lever 1 — Increase IFBW

IFBW (Intermediate Frequency Bandwidth) controls how long the VNA settles at each frequency
point before measuring. A wider filter settles faster.

> **Higher IFBW → shorter time per point → faster sweep, but higher noise floor**

### IFBW vs sweep speed (LibreVNA, 300 points, 2.43–2.45 GHz)

| IFBW | Approx sweep time | Sweep rate | Noise |
|------|------------------|------------|-------|
| 1 kHz | ~600 ms | ~1.7 Hz | Lowest |
| 10 kHz | ~60 ms | ~16 Hz | Low |
| **50 kHz** | **~18 ms** | **~55 Hz** | Moderate |
| 100 kHz | ~9 ms | ~110 Hz | Higher |

### IFBW vs sweep speed (Keysight reference, 801 points, 223–243 MHz)

| IFBW | Approx sweep time | Sweep rate |
|------|------------------|------------|
| 1 kHz | ~800 ms | ~1.25 Hz |
| 10 kHz | ~80 ms | ~12 Hz |
| 50 kHz | ~48 ms | ~21 Hz |
| 70 kHz | ~11 ms | ~90 Hz |

### Trade-off

| Increasing IFBW gains | Increasing IFBW costs |
|----------------------|-----------------------|
| Faster sweep rate | Higher noise floor |
| More sweeps per second | Reduced dynamic range |
| Lower sweep time | May blur closely spaced resonances |

**Rule:** Use the highest IFBW that keeps the S11 resonance dip clearly distinguishable from
noise. For the ~233.5 MHz biomedical resonance, 50 kHz is the validated minimum viable setting
for heartbeat capture (Nyquist requires >2.4 Hz sweep rate for ~1.2 Hz heart rate).

---

## Lever 2 — Reduce Number of Sweep Points

Fewer frequency points = fewer measurements = shorter sweep time. This lever is **directly
proportional** — halving the point count halves the sweep time.

```
sweep_rate_new = sweep_rate_old × (old_points / new_points)
```

### Example

| Points | Sweep time (50 kHz IFBW) | Sweep rate |
|--------|--------------------------|------------|
| 801 | ~48 ms | ~21 Hz |
| 300 | ~18 ms | ~55 Hz |
| 100 | ~6 ms | ~167 Hz |
| 50 | ~3 ms | ~333 Hz |

### Trade-off

| Fewer points gains | Fewer points costs |
|-------------------|--------------------|
| Proportionally faster sweep | Lower frequency resolution (wider steps) |
| Less data per sweep | May miss a narrow resonance dip |

**Rule:** The minimum number of points needed is set by the resonance linewidth. If the
resonance spans ~2 MHz (Q ~120 at 233.5 MHz), you need at minimum:

```
min_points ≈ span_MHz / step_size_MHz
           = 20 MHz / 0.1 MHz = 200 points   (at 0.1 MHz step, adequate)
           = 20 MHz / 0.5 MHz = 40 points    (at 0.5 MHz step, may lose peak accuracy)
```

For a 20 MHz span centred on the resonance, **100–150 points** is a practical minimum that
retains adequate resonance shape while improving sweep rate.

---

## Lever 3 — Narrow the Frequency Span

Reducing the sweep span **alone does not increase sweep rate** — because sweep time depends on
point count, not span width. However, narrowing the span allows you to **reduce the point count
while maintaining the same frequency resolution** (step size).

### Logic

```
step_size_MHz = span_MHz / num_points

# To keep step_size constant while narrowing span:
new_points = new_span_MHz / step_size_MHz
```

### Example — 233.5 MHz resonance application

| Scenario | Span | Points | Step size | Sweep rate (50 kHz IFBW) |
|----------|------|--------|-----------|--------------------------|
| Full range (original) | 200–250 MHz (50 MHz) | 300 | 0.167 MHz | ~16 Hz |
| Wide range | 223–243 MHz (20 MHz) | 120 | 0.167 MHz | ~40 Hz |
| Focused range | 228–240 MHz (12 MHz) | 72 | 0.167 MHz | ~67 Hz |
| Tight range | 230–237 MHz (7 MHz) | 42 | 0.167 MHz | ~114 Hz |

All scenarios maintain the same frequency resolution. The gain comes from needing fewer points
to cover the narrower span.

### When narrowing span is safe

- The resonance does **not** drift outside the narrowed window during measurement.
- No other significant features (competing dips, cable resonances) fall within the window.
- The window is at least 3–5× the resonance linewidth to avoid edge-clipping the dip.

**For the biomedical phantom application:** the resonance shifts ±0.25 MHz around 233.5 MHz.
A span of 230–237 MHz (7 MHz) provides a ±3.25 MHz margin — adequate for the observed drift.

---

## Combined Strategy — Maximum Practical Rate

Apply all three levers together:

| Parameter | Original | Optimised |
|-----------|----------|-----------|
| IFBW | 10 kHz | 50 kHz |
| Span | 200–250 MHz (50 MHz) | 230–237 MHz (7 MHz) |
| Points | 300 | 42 |
| **Sweep rate** | **~3 Hz** | **~114 Hz** |

This ~38× improvement uses the same instrument hardware — only configuration changes.

---

## Nyquist Constraint — Minimum Viable Rate

The physiological signals of interest set a hard lower bound on sweep rate:

| Signal | Frequency | Required min sweep rate (×2 Nyquist) |
|--------|-----------|--------------------------------------|
| Breathing | 0.2–0.4 Hz | >0.8 Hz |
| Heart rate | 0.8–2.5 Hz | **>5 Hz** |
| Pulse waveform shape | up to ~10 Hz | >20 Hz |

For heartbeat detection only: **≥5 Hz sweep rate required**.
For pulse waveform fidelity: **≥20 Hz sweep rate recommended**.

---

## Summary — Decision Tree

```
Goal: increase sweep rate
│
├─ Is noise acceptable at higher IFBW?
│   ├─ YES → Increase IFBW first (biggest single gain)
│   └─ NO  → Keep IFBW, focus on points/span reduction
│
├─ Is the current frequency span wider than needed?
│   ├─ YES → Narrow span to ±3–5× the resonance linewidth
│   │         and reduce points proportionally
│   └─ NO  → Skip span reduction
│
└─ Is point count higher than resonance resolution requires?
    ├─ YES → Reduce points until step_size ≈ resonance_width / 10
    └─ NO  → Current point count is already optimal
```

---

## Key Rules

| Rule | Explanation |
|------|-------------|
| Higher IFBW = faster + noisier | Each point settles in less time; wider filter passes more noise |
| Fewer points = proportionally faster | Sweep time scales linearly with point count |
| Narrowing span alone = no gain | Must also reduce points to benefit from narrower span |
| Nyquist sets the floor | Cannot sample physiological signal at less than 2× its frequency |
| First sweep is always a cold-start outlier | Discard index 0 from any sweep-time estimation |
