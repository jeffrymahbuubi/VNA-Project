# Project Design Summary
**Date:** 2026-02-25

---

## 1. Most Likely Project Objective

This project is building a **portable, low-cost replacement** for the Keysight E5063A Vector
Network Analyzer for a specific biomedical sensing application: **non-invasive monitoring of
resonant-frequency shift in an RF sensor placed near biological tissue or a pulsatile flow
phantom.**

The gold-standard instrument (Keysight E5063A) is laboratory-grade, large, and not portable.
The LibreVNA (USB-powered, palm-sized, ~$150) can serve as a field-deployable or bedside
alternative if its data output can be made equivalent.

---

## 2. What Is Being Monitored

- A **resonant RF sensor** (antenna, patch resonator, or loop) is placed near or on a target —
  either a living subject or a **pulsatile flow phantom** (a laboratory model that mimics blood
  vessel dynamics for testing post-surgical implants or vessel integrity).
- The sensor's resonant frequency (the frequency of minimum S11) **shifts slightly** as the
  nearby material deforms — chest-wall motion from breathing, pulse pressure expanding a vessel
  wall, or fluid volume changes.
- This shift is on the order of **±0.15–0.25 MHz** around a centre frequency of ~233.5 MHz.
- The **time-varying pattern** of this shift encodes physiological information:
  - Breathing rate (~0.2–0.4 Hz)
  - Heart rate (~1–2 Hz)
  - Pulsatile pressure waveform shape

---

## 3. What the Dataflux CSV Actually Represents

| Field | Meaning |
|-------|---------|
| `Time` | Timestamp of each marker log event (~20 ms apart) |
| `Marker Stimulus (Hz)` | Frequency of minimum S11 at that instant |
| `Marker Y Real Value (dB)` | Depth of the resonance dip at that frequency |

**Critical clarification:** The Dataflux CSV does **not** contain the full S11 trace (801 points
× magnitude). It contains only **one scalar per row** — the position of a minimum-tracking
marker. The Keysight sweeps continuously internally (223–243 MHz, 801 pts, 70 kHz IFBW → ~11
ms/sweep), and every ~20 ms logs where the minimum marker sits. The user manually configured the
marker to track the minimum before starting the session.

---

## 4. Corrected Understanding of the Current LibreVNA Tool

| Dimension | Current design (wrong for this use case) | Correct design for monitoring |
|-----------|------------------------------------------|-------------------------------|
| **Collection mode** | N discrete sweeps (30 repeats) | Continuous, indefinite sweep |
| **Stored per cycle** | Full S11 trace (300 pts × freq × mag × phase) | Single scalar: `min_freq_hz`, `min_dB` |
| **Session model** | Fixed N → stop → export | Run until user stops → export |
| **Time resolution** | ~5–16 Hz (one per complete sweep) | Same rate, but logged as time-series |
| **Real-time display** | Full S11 spectrum (freq vs magnitude) | Scrolling time-series (time vs min-freq) |
| **Output format** | Multi-sheet XLSX (one sheet per IFBW) | Single CSV matching Dataflux layout |
| **Purpose** | Benchmarking sweep speed / IFBW impact | Physiological signal capture |

---

## 5. Marker Configuration: Manual vs Automatic

On the Keysight E5063A the user must manually:
1. Add a marker to the S11 trace
2. Set it to "minimum tracking" mode
3. Configure the Data Flux panel (interval, count)
4. Press record

In the LibreVNA GUI this entire workflow collapses to a software operation:
`min_idx = np.argmin(s11_magnitudes_db)`. The user never needs to configure a marker — it is
always extracted automatically.

---

## 6. Temporal Resolution Trade-off

| IFBW | Approx sweep rate | Nyquist limit | Can capture heartbeat (~1.2 Hz)? |
|------|------------------|---------------|----------------------------------|
| 50 kHz | ~5–16 Hz | ~2.5–8 Hz | Yes (marginally) |
| 10 kHz | ~3 Hz | ~1.5 Hz | Borderline |
| 1 kHz | ~0.5 Hz | ~0.25 Hz | No |

For heartbeat detection: **50 kHz IFBW is the minimum viable setting**. For breathing only,
10 kHz is adequate.

To increase data rate further: **narrow the sweep span** to ±10–20 MHz around the resonance.
With 300 pts and 50 kHz IFBW this can push rates toward 20+ Hz.

---

## 7. BPM Calculation Caveat

The BPM figure from `plot_dataflux.py` (393 BPM) is acknowledged as inaccurate. Correct
approach:
1. Bandpass-filter the min-frequency time series:
   - 0.1–0.5 Hz window for breathing
   - 0.8–2.5 Hz window for heartbeat
2. Apply `scipy.signal.find_peaks` to the **filtered** signal
3. BPM = peak count / (total_time / 60)

---

## 8. Monitor Mode Feature Plan (Added 2026-02-25)

### What Was Built

A **"Monitor" mode** has been added to the existing LibreVNA GUI
(`gui/7_realtime_vna_plotter_mvp.py` and its MVP components) that:

- Runs continuous sweeps indefinitely (reuses the same streaming path as the preview worker)
- After each complete sweep, extracts `(timestamp, min_freq_hz, min_dB)` — the marker equivalent
- Emits each extracted row to the presenter for real-time GUI updates
- Displays a **scrolling time-series plot** of `min_freq_MHz` vs elapsed seconds (alongside
  the existing full S11 preview plot)
- On stop, exports to a **Dataflux-compatible CSV** that `plot_dataflux.py` can read without
  modification

### Files Modified

| File | Change |
|------|--------|
| `gui/mvp/model.py` | Added `MonitorRecord` dataclass + `monitor_records`, `is_monitoring`, `monitor_t0` fields to `VNADataModel` |
| `gui/mvp/presenter.py` | Added `VNAMonitorWorker` QThread + monitor slots in `VNAPresenter` |
| `gui/mvp/view.py` | Added "Monitor" button + second pyqtgraph PlotWidget (scrolling time-series) |

### Output Format (Dataflux-Compatible CSV)

```
Application,VNA-DATAFLUX
VNA Model,LibreVNA
VNA Serial,<from *IDN?>
File Name,<generated filename>
Start DateTime,<ISO timestamp>
Number of Data,<row count>
Log Interval(ms),<mean dt * 1000>
Freq Start(MHz),<from cal file>
Freq Stop(MHz),<from cal file>
Freq Span(MHz),<stop - start>
IF Bandwidth(KHz),<ifbw / 1000>
Points,<num_points from cal>


Time,Marker Stimulus (Hz),Marker Y Real Value (dB)
HH:MM:SS.ffffff,+X.XXXXXXXXXE+008,-X.XXXXXXXXXE+000
...
```

This allows `plot_dataflux.py` to run on LibreVNA data without any changes.

### Per-sweep Minimum Extraction (Core Logic)

```python
# Inside streaming callback, called once per complete sweep:
min_idx = np.argmin(s11_db)
min_freq_hz = freq_hz[min_idx]
min_db = s11_db[min_idx]
timestamp = datetime.now()
elapsed_s = (timestamp - t0).total_seconds()
records.append((timestamp, min_freq_hz, min_db))
monitor_point.emit(elapsed_s, min_freq_hz / 1e6, min_db)
```

### Verification Steps

After implementation:
```bash
cd code/LibreVNA-dev/gui
uv run python 7_realtime_vna_plotter_mvp.py
# 1. Click "Monitor" button (orange)
# 2. Let run for 30–60 seconds
# 3. Click "Stop Monitor" — CSV exported to data/YYYYMMDD/
# 4. Run: uv run python ../../markdown/20260211/plot_dataflux.py
#    (after updating CSV_PATH to point to the new file)
# 5. Verify two-panel figure generates correctly
```
