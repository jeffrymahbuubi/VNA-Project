# Planned Features — LibreVNA Monitor Mode
**Created:** 2026-02-25
**Status:** Draft — actively updated

---

## Feature Index

| # | Feature | Status |
|---|---------|--------|
| F-01 | Log Interval Mode (Auto / Manual) | Planned |

---

## F-01 — Log Interval Mode (Auto / Manual)

### Overview

When running Monitor Mode, the user needs a `Log Interval (ms)` value that is compatible
with the actual sweep speed of the connected device under the current configuration. Setting
it too short is physically impossible (clamped to sweep time); setting it uninformed leads
to misleading metadata in the exported Dataflux CSV.

This feature adds two modes:

- **Auto** — device runs a short warm-up sweep sequence before data collection; algorithm
  estimates mean sweep time and recommends a log interval automatically.
- **Manual** — user enters a value directly; system validates it against the estimated sweep
  time and warns if the value is below the physical minimum.

---

### Background / Constraints

- Log Interval cannot be shorter than one sweep time (physical lower bound).
- Sweep time is determined by: IFBW, point count, frequency span, and OS/USB jitter.
- The **first sweep is always a cold-start outlier** (GUI subprocess warm-up, calibration
  load, streaming registration) and must be discarded from any estimate.
- Sweep time has real variance (~5–15% CV) from OS scheduling and USB latency.

Reference: `log_interval_and_timing_clarification.md` for full derivation.

---

### Warm-Up Algorithm

#### Minimum repetitions

| N total sweeps | Usable (N − 1) | Reliability | Decision |
|----------------|----------------|-------------|----------|
| 3 | 2 | Poor | Rejected |
| 5 | 4 | Marginal | Absolute floor |
| **10** | **9** | **Good** | **Default** |
| 15 | 14 | Better | Recommended for noisy environments |
| 30 | 29 | Excellent | Conservative / benchmark use |

**Default warm-up sweeps: 10** (configurable, minimum 5).

#### Recommended log interval calculation

```python
def estimate_log_interval(sweep_times_ms: list) -> dict:
    """
    Args:
        sweep_times_ms: raw per-sweep durations from warm-up phase
                        (index 0 = cold-start sweep, always discarded)
    Returns:
        dict with estimated mean, std, and recommended log interval
    """
    usable = sweep_times_ms[1:]          # discard cold-start

    mean_ms = np.mean(usable)
    std_ms  = np.std(usable)

    # mean + 1σ gives ~84% of sweeps within window — good engineering margin
    raw_recommended = mean_ms + std_ms

    # Round UP to nearest 10 ms for clean presentation
    recommended_ms = np.ceil(raw_recommended / 10) * 10

    return {
        "mean_sweep_ms":     round(mean_ms, 1),
        "std_sweep_ms":      round(std_ms, 1),
        "sweep_rate_hz":     round(1000 / mean_ms, 2),
        "recommended_ms":    recommended_ms,
    }
```

**Why `mean + 1σ` and not just `mean`:**
Using only the mean means ~50% of sweeps arrive late, risking occasional skipped log rows.
Adding 1σ provides a jitter-tolerance margin without over-padding the interval.

---

### Validation Rule (Manual Mode)

If the user manually enters a log interval, the system should:

1. Run the warm-up phase (same as Auto) to obtain `mean_sweep_ms`.
2. Compare user value against the physical minimum:

```python
if user_log_interval_ms < mean_sweep_ms:
    show_warning(
        f"Log interval {user_log_interval_ms} ms is below estimated sweep time "
        f"({mean_sweep_ms:.0f} ms). Effective interval will be ~{mean_sweep_ms:.0f} ms."
    )
```

3. Allow the user to proceed — it is not a hard block, just an informed warning.

---

### UI Sketch

```
┌─────────────────────────────────────────────────────┐
│  Log Interval                                       │
│  ○ Auto   ● Manual                                  │
│                                                     │
│  [Auto selected]                                    │
│  Warm-up sweeps:       [ 10 ]  (min: 5)            │
│  Estimated sweep time: 135 ms  (7.4 Hz)            │
│  Recommended interval: 150 ms                      │
│                                                     │
│  [Manual selected]                                  │
│  Log Interval (ms):    [ 150 ]                     │
│  ⚠ shown if value < estimated sweep time           │
└─────────────────────────────────────────────────────┘
```

- Auto mode runs warm-up silently, then shows estimated sweep time to the user before
  starting the monitor session proper.
- Manual mode still runs the warm-up for validation purposes only.
- Warm-up progress can be shown in the status bar (e.g. "Warm-up: 6 / 10 sweeps…").

---

### Implementation Touch Points (MVP Architecture)

| File | Change needed |
|------|---------------|
| `gui/mvp/model.py` | Add `log_interval_mode: str = "auto"`, `warmup_sweeps: int = 10`, `log_interval_ms: Optional[float]` to `VNADataModel` or `SweepConfig`. Add `estimate_log_interval()` as a model method. |
| `gui/mvp/presenter.py` | Add warm-up phase inside `VNAMonitorWorker.run()` before the main recording loop. Emit warm-up progress signal. After warm-up, call `estimate_log_interval()` and either apply result (Auto) or validate against it (Manual). |
| `gui/mvp/view.py` | Add Log Interval mode radio buttons + warm-up sweep count field + estimated sweep time read-only label to the configuration panel. Show/hide fields based on Auto/Manual toggle. |
| `gui/sweep_config.yaml` | Add `log_interval_mode`, `warmup_sweeps`, `log_interval_ms` fields under `configurations`. |

---

### Open Questions

- [ ] Should the warm-up sweeps be counted separately from the monitor recording, or should the
      first N sweeps of the recording session serve double duty (warm-up + data)?
      **Recommendation:** Keep them separate — warm-up data is discarded; recording starts clean.
- [ ] Should the warm-up result (mean sweep time, std) be written into the exported CSV metadata
      as an additional header field for traceability?
- [ ] What is the UI behaviour if warm-up variance is very high (std > 30% of mean)? Consider
      showing a caution indicator suggesting the user check IFBW/configuration.

---

*Add new features below this line as separate H2 sections following the same template.*
