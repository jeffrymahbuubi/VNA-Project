# Why a "Marker" Feature Is Not Relevant for This Use Case

**Date:** 2026-02-25

---

## Context

The Keysight E5063A Dataflux workflow requires the user to manually:
1. Add a marker to the S11 trace
2. Set it to "minimum tracking" mode
3. Configure the Data Flux panel (interval, count)
4. Press record

The question is whether the LibreVNA GUI needs to replicate a configurable marker UI to produce
equivalent output to `Dataflux.csv`.

---

## What the Dataflux CSV Actually Stores

Each row in `Dataflux.csv` contains exactly three scalars:

| Column | Meaning |
|--------|---------|
| `Time` | Timestamp of the log event |
| `Marker Stimulus (Hz)` | Frequency of minimum S11 at that instant |
| `Marker Y Real Value (dB)` | Depth of the resonance dip at that frequency |

There is no full S11 trace stored — only the position of the minimum per sweep.

---

## Why `np.argmin()` Is Already Sufficient

```python
min_idx = np.argmin(s11_db)
min_freq_hz = freq_hz[min_idx]
min_db = s11_db[min_idx]
```

This produces exactly the same output as a minimum-tracking marker on the Keysight. There is no
functional difference. The "marker" on the Keysight is a UI abstraction over the same mathematical
operation — find the index of the minimum of the S11 magnitude array.

The LibreVNA Monitor mode already implements this: after every complete sweep, `np.argmin` runs
automatically and the result is appended to the CSV. No user configuration is needed.

---

## Why a Configurable Marker Adds No Value Here

A manual marker feature would only be relevant in the following scenarios:

| Scenario | Relevant to this project? |
|----------|--------------------------|
| Multiple resonant dips in the sweep range, needing to select a specific one | **No** — sweep span is 223–243 MHz (20 MHz), narrow and centred on the ~233.5 MHz resonance; competing dips are improbable |
| Sensor moves significantly during measurement | **No** — sensor is fixed in place during each data collection session |
| Need to track a maximum, threshold crossing, or non-minimum feature | **No** — application requires minimum-frequency tracking only |
| Need a configurable sub-range to constrain the search window | **No** — fixed sensor and narrow span make this unnecessary |

---

## The One Case Where a Marker-Like Feature Would Matter

If `np.argmin()` were observed to occasionally "jump" to a spurious dip (cable resonance,
connector artifact, or a noise spike deeper than the true resonance), the correct mitigation is a
**frequency search window** — a single configuration value such as:

```yaml
search_window_mhz: 5.0   # only search within ±5 MHz of the last known minimum
```

This is far simpler than a full marker UI and handles the only realistic failure mode. It is a
configuration parameter, not a GUI feature.

---

## Conclusion

**The marker feature is not necessary.** `np.argmin()` already performs minimum-tracking
automatically on every sweep and produces Dataflux-compatible output. Given:

- Fixed sensor position during measurement
- Narrow sweep span (20 MHz) centred on the resonance of interest
- Low-artifact environment expected
- Output format already matches Dataflux CSV without any marker configuration step

Adding a marker UI would replicate instrument complexity that exists on the Keysight only because
its firmware requires explicit user setup. In the LibreVNA software implementation, the minimum is
always found algorithmically — the concept of "setting a marker" does not apply.

If spurious minimum jumps are observed in real data, add a search-window config parameter rather
than a full marker UI.
