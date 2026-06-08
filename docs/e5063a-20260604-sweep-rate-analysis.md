# E5063A — Sweep-Rate vs Configuration Analysis (20260604 dataset)

**Document type:** Dated analysis report (point-in-time; not a living spec).
**Created:** 2026-06-04 (analysis), written up 2026-06-05.
**Owner:** Aunuun Jeffry Mahbuubi
**Companions:** `docs/e5063a-migration-spec.md` (living SoT), `docs/E5063A_SCPI_Reference.md`,
notebook `code/ena-dev/notebook/2_sweep_rate_vs_config_e5063a.ipynb` (executed, all figures).
**Instrument:** Keysight E5063A, SN MY54806798, FW A.07.06, S11, −5 dBm, 1-port ECal, REAL32 + SWAP,
continuous latched read.

> **Purpose of this doc.** Capture *what we measured* on 2026-06-04 about how the E5063A's sweep
> rate depends on configuration (points, IFBW, frequency span), AND — more importantly for future-self
> — the **mental model for the speed ↔ accuracy trade-off** in the context of the prototype
> blood-vessel resonance monitor. It closes with the **open question** and a concrete **next-session
> plan** (deep-dive on the `bloodvessel_monitor` CSVs to decide whether higher frequency accuracy is
> actually needed).

---

## 1. The objective this serves (why we care about config at all)

The custom E5063A tool exists to monitor a **prototype blood-vessel device** by tracking, over time,
the **frequency of the S11 resonant dip** (the notch) — a Dataflux-style scalar time series
(`min-freq [Hz]`, `min-mag [dB]` per sweep). Physiological dynamics (pulse, respiration, vessel
state) modulate the resonant frequency; we want to sample that modulation fast enough and resolve it
finely enough. See memory `project-monitor-loginterval-e5063a`.

So every configuration choice ultimately trades two things we care about:
- **Temporal resolution** — how fast we log min-freq points (monitoring rate, Hz).
- **Frequency accuracy** — how precisely each logged min-freq locates the true notch.

This dataset maps that trade-off across the instrument's knobs.

---

## 2. Dataset inventory (`REPORT/20260604/20260604/`)

**11 Device Sanity-Check workbooks** (`run_sanity_*.xlsx`) — per-IFBW summary rows
(`IFBW kHz | Mean Sweep ms | Update Rate Hz | Noise Floor dB | Trace Jitter dB`), 30 sweeps/IFBW:

| Swept dimension | Values | Held fixed |
|---|---|---|
| **Number of points** | 101, 201, 301, 401, 501, 601, 701, 801, 901, 1001 | span 200–250 MHz |
| **Start/stop (span)** | 200–250 MHz (50 MHz) vs **230–250 MHz** (20 MHz) | 801 pt |
| **IFBW** (inner sweep) | 300, 150, 125, 100, 75, 50, 1 kHz (+10 kHz on the 230–250/801 run) | — |

**2 Dataflux monitor CSVs** (`bloodvessel_monitor_*.csv`) — live min-S11 time-series at 801 pt /
300 kHz, one per span (200–250 and 230–250). Columns: `Time, Marker Stimulus (Hz), Marker Y Real Value (dB)`.

> ⚠ **Data-availability note for the deep-dive:** the monitor CSVs store only the *post-argmin scalar*
> per sweep (min-freq + min-mag), **not the full per-point S11 traces**. The sanity workbooks store
> only summary metrics, also **no full traces**. To inspect the *dip shape* (width / Q / depth) you
> must use a full-trace capture — the 20260602 dataset (`code/ena-dev/data/20260602/*.xlsx`, used by
> notebook 1) does store per-IFBW full traces, or capture a fresh short run.

---

## 3. What we measured (sweep rate vs configuration)

All numbers from notebook 2; figures saved in `code/ena-dev/notebook/figures_20260604_sweep_rate/`.

### 3.1 Rate vs number of points (fixed span 200–250 MHz)
Rate falls, mean sweep time rises ~linearly with N. Representative (300 / 100 / 50 kHz IFBW):

| Points | 300 kHz | 100 kHz | 50 kHz |
|---|---|---|---|
| 101 | 133.0 Hz | 116.0 | 97.6 |
| 401 | 66.4 | 51.6 | 45.3 |
| 801 | 39.5 | 31.5 | 26.1 |
| 1001 | 33.1 | 26.5 | 21.3 |

### 3.2 Rate vs IFBW (fixed 801 pt)
Rate rises with IFBW and saturates; the 1 kHz point is a ~1.3 Hz outlier (792 ms). At 801 pt:
300 kHz = 39.5 Hz, 100 kHz = 31.5, 50 kHz = 26.1, 10 kHz ≈ 10, 1 kHz ≈ 1.3.

### 3.3 Analytical sweep-time model (the reusable result)
Fit over the full points × IFBW grid (R² = 0.99997, median |resid| 0.7 ms):

```
t_sweep(N, IFBW) ≈ 4.64 ms  +  N · ( 0.0230 ms/pt  +  0.959 ms·kHz/pt / IFBW_kHz )
rate_hz = 1000 / t_sweep
```

- **4.64 ms** fixed host/trigger overhead · **0.023 ms/pt** per-point fixed (ADC/DSP) ·
  **0.959 ms·kHz/pt** per-point IF-settling dwell (∝ 1/IFBW).
- Reduces at N=801 to `≈ 23.0 + 768/IFBW` ms — consistent with the older fixed-801pt model
  `≈ 25 + 869/IFBW` (memory `project-e5063a-phase3-bench-results`).
- Use it to predict the rate of any untested (points, IFBW) before committing a run.

### 3.4 Frequency span is NOT perfectly neutral
At 801 pt, the narrower **20 MHz span ran ~7% faster on average** (mean signed −6.9%, up to −15% at
300 kHz) than the 50 MHz span — plausibly less LO retune per step. BUT the two spans are separate
acquisitions and host-VISA jitter is also ~10%, so this is suggestive, not conclusive (the 150 kHz
point even reversed sign). **First-order, rate is set by points × IFBW (~30× range); span is a small
secondary effect.** A clean span study needs interleaved repeats.

### 3.5 Quality (noise floor / jitter)
Noise floor is essentially flat (~0.017 dB across all IFBW at 801 pt). The speed↔quality cost shows up
as **trace jitter**, which rises with IFBW (2.6 → 18 mdB from 1 → 300 kHz). For S11-match work the
dynamic range is ample at any IFBW; jitter is the thing that degrades at high IFBW.

### 3.6 Monitor cross-check
The live monitor CSVs (801 pt/300 kHz) logged ~31.2–31.5 Hz (mean Δt ~32 ms) vs the 39.5 Hz bare
sanity sweep rate — the gap is the per-sample marker-search + CSV-logging overhead added on top of
each sweep. (CSV timestamps are quantised to ~15/16 ms host-clock; use the **mean** Δt, not median.)

---

## 4. The mental model: speed ↔ accuracy trade-off (read this first when revisiting)

Three **independent** knobs, each with a distinct role. Internalise which one moves which axis:

| Knob | Moves frequency accuracy via… | Moves speed via… |
|---|---|---|
| **Points N** (at fixed span) | point spacing **Δf = span/(N−1)** — the grid resolution of the dip | sweep time ∝ N (more points = slower) |
| **Span** (at fixed N) | Δf again — **narrower span = finer Δf for free** (+ ~7% faster) | mostly neutral (small secondary effect) |
| **IFBW** | **not** frequency resolution — sets noise floor / dip depth / SNR | per-point dwell ∝ 1/IFBW (higher IFBW = faster, noisier) |

**Point spacing for this dataset's configs:**

| Span | Points | Δf (frequency quantum of the logged min-freq) |
|---|---|---|
| 200–250 MHz (50 MHz) | 101 | 500 kHz |
| 200–250 MHz (50 MHz) | 801 | 62.5 kHz |
| 230–250 MHz (20 MHz) | 801 | **25 kHz** |
| (e.g.) 240–245 MHz (5 MHz) | 501 | **10 kHz** |

**Accuracy has two distinct facets:**
1. **Resolving small shifts of the dip over time** (the monitoring signal). Limited by Δf when using
   raw argmin (see §5): the min-freq(t) series is a *staircase* with step Δf; a physiological shift
   smaller than Δf is invisible until it crosses a whole bin.
2. **Characterising the dip shape** (depth / Q). Needs several points across the dip's −3 dB width
   (~5–10). A sharp/high-Q notch under-sampled gives biased depth *and* frequency. (Needs full traces
   to assess — see the data-availability note.)

**Speed budget:** monitoring needs ≥ ~20–30 Hz to oversample pulse/respiration dynamics — the whole
reason for migrating off the LibreVNA's ~7 Hz ceiling.

**The decision order that follows from this model:**
1. **Set the span** to tightly bracket the resonance + its drift range (don't waste points on flat
   baseline). This is the *free* accuracy lever for a localised dip.
2. **Choose N** so Δf is a few× finer than (a) the smallest shift you must detect and (b) the dip
   −3 dB width / ~5–10 samples — whichever is tighter.
3. **Then minimise N / maximise IFBW** to push the monitoring rate as high as the noise floor allows.

**Recommended operating points (from this dataset):** 801 pt / 300 kHz = 39.5 Hz (clears 30 Hz at the
finest grid tested); 801 pt / 50 kHz = 26.1 Hz (clears 25 Hz with more DR margin). But these assume
the wide 50 MHz span — see the open question.

---

## 5. Considered & deferred: argmin quantization vs parabolic interpolation

**Finding (verified in code, 2026-06-05):** every min-search path in the GUI is a **raw `argmin`** —
`backend_e5063a.py` (`monitor_min_freq`, `monitor_read`), `controller.py` (`_preview_tick`, the path
that feeds the logged Dataflux CSV), `stub_backend.py` (`argmin_freq`), `main_window.py` (on-screen
marker). So **the reported min-freq is hard-snapped to the grid; its precision = Δf.** This is *the*
reason facet-1 accuracy is tied to N/span today.

**Option prototyped then reverted (no code change adopted):** 3-point parabolic (quadratic-vertex)
interpolation around the deepest sample:
```
δ = 0.5*(y[i-1] − y[i+1]) / (y[i-1] − 2·y[i] + y[i+1])   # vertex offset in (−0.5, +0.5) bins
f_min = freqs[i] + δ·Δf ;  mag = y[i] − 0.25·(y[i-1] − y[i+1])·δ
```
On a synthetic Lorentzian notch (true f0 = 233.530 MHz, 200–250 MHz span) it cut the min-freq error
vs raw argmin dramatically — and, crucially, **decouples frequency precision from N** (lets you run
fewer points / faster at the same effective precision):

| Points | Δf | argmin error | parabolic error | gain |
|---|---|---|---|---|
| 101 | 500 kHz | 30.0 kHz | 4.4 kHz | ~7× |
| 401 | 125 kHz | 30.0 kHz | 0.25 kHz | ~120× |
| 801 | 62.5 kHz | 30.0 kHz | 0.006 kHz | huge |

(Real-world gain is SNR/curvature-limited, typically ~1/10–1/50 of a bin — not the noise-free numbers
above.) **Status: DEFERRED — code reverted, not adopted.** Two caveats: (a) it can't be applied
retroactively (the collected monitor CSVs store only the post-argmin scalar, no raw traces); (b)
whether it's worth adopting depends entirely on the open question below. If facet-1 accuracy turns out
to matter, parabolic interpolation is the cheapest lever (software-only, no speed cost) — preferred
over brute-forcing N.

---

## 6. Open question (for future-self to answer)

> **Given that the blood-vessel antenna's resonance dip lies in a SHORT frequency range, is high
> frequency accuracy actually needed — or is the current configuration already over- or
> under-resolved?**

The intuition: a wide 50 MHz / 801 pt sweep spends most of its points on flat baseline; if the dip is
localised and its physiological drift is small, you could narrow the span (free Δf + speed) and/or
drop points. But *whether* you need finer Δf at all depends on how the real min-freq(t) behaves
relative to the quantum:
- If the physiological min-freq excursion spans **many** Δf bins → coarse Δf is fine; **don't** add
  accuracy, buy speed instead.
- If the excursion is **comparable to or below** Δf (buried in the staircase) → you need finer Δf
  (narrow span first; then interpolation; N last).

---

## 7. Next-session plan — deep-dive on the `bloodvessel_monitor` CSVs

Goal: from the *real* monitor data, conclude whether higher accuracy is needed. Steps (build a
notebook `3_bloodvessel_monitor_analysis_e5063a.ipynb`, code/-rooted Jupyter):

1. **Load both CSVs** (200–250 and 230–250 MHz, both 801 pt/300 kHz → Δf = 62.5 kHz vs 25 kHz). Parse
   metadata + `min-freq(t)`, `min-mag(t)`; reconstruct the time base (mean Δt ≈ 32 ms ≈ 31 Hz).
2. **min-freq(t) trajectory stats** — range (max−min), mean, std. Express the excursion in **units of
   Δf**: excursion/Δf is the single most decisive number. ≫1 → resolution is fine; ≲ a few → resolution
   is limiting.
3. **Quantization fingerprint** — histogram of the *unique* min-freq values and of successive
   differences. Are they integer multiples of Δf (62.5 / 25 kHz)? Visualise the staircase. Compare the
   two spans: does the finer-Δf 230–250 run reveal structure the 62.5 kHz run flattens?
4. **Dynamics / physiology SNR** — detrend, then PSD/FFT of min-freq(t) at ~31 Hz sampling. Look for
   cardiac (~1–1.5 Hz) and respiration (~0.2–0.3 Hz) bands. **Key test: is the physiological
   modulation amplitude above the Δf quantization floor?** That answers the open question.
5. **Magnitude channel** — min-mag(t) stability + any freq↔mag correlation (sanity on dip quality).
6. **Dip shape (needs full traces)** — to judge facet-2 (width/Q) and a sensible narrowed span,
   pull a full-trace capture (reuse 20260602 traces or take a fresh short run) and measure the −3 dB
   width and how many points sit across it at each candidate (span, N).
7. **Conclusion + recommendation** — pick: (a) the span that tightly brackets the dip + drift, (b) the
   N/Δf that's *sufficient* (not maximal), (c) whether to adopt parabolic interpolation, (d) the IFBW
   for adequate DR at the highest rate. Update the migration spec operating point if it changes.

---

## 8. One-line takeaways

- Rate is governed by **points × IFBW** (model R²≈1.0); span is a small secondary effect.
- For a **localised dip, narrow the span first** — it buys frequency resolution *and* a little speed,
  unlike adding points (which only costs speed).
- Today's min-freq precision = **Δf** (raw argmin); parabolic interpolation can decouple precision
  from N but is **deferred** pending the accuracy question.
- **Whether higher accuracy is needed is unresolved** — answer it next session from the real
  `bloodvessel_monitor` min-freq(t): compare its physiological excursion against the Δf quantum.
