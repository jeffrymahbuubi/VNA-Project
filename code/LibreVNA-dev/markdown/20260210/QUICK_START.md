# Quick Start Guide - LibreVNA Real-Time Plotter

## 1-Minute Setup

### Prerequisites
```bash
# Ensure dependencies installed
cd code
uv pip install PyQt6 pyqtgraph

# Check files exist
cd LibreVNA-dev/gui
ls SOLT_1_2_43G-2_45G_300pt.cal    # Calibration file ✓
ls sweep_config.yaml                # Config file ✓
```

### Launch GUI
```bash
cd code/LibreVNA-dev/gui
uv run python 7_realtime_vna_plotter_mvp.py
```

**That's it!** GUI will auto-detect files and populate configuration.

---

## First Run Checklist

### Hardware
- [ ] LibreVNA device connected via USB
- [ ] 50-ohm matched load on port 1

### Software
- [ ] Python virtual environment activated (`uv`)
- [ ] PyQt6 installed
- [ ] pyqtgraph installed

### Files
- [ ] `gui/SOLT_1_2_43G-2_45G_300pt.cal` exists
- [ ] `gui/sweep_config.yaml` exists

---

## Expected Workflow

1. **Window opens** (1280×720)
2. **Status bar shows:**
   ```
   ✓ Auto-loaded: SOLT_1_2_43G-2_45G_300pt.cal
   ```
3. **Configuration panel populated** with values from YAML
4. **Green "Collect Data" button** enabled
5. **Click button** → red blinking animation starts
6. **Real-time plot** updates with yellow S11 trace
7. **Status updates:**
   ```
   Starting LibreVNA-GUI...
   ✓ Device connected - Starting sweeps...
   IFBW 150 kHz - Sweep 1/30
   IFBW 150 kHz - Sweep 2/30
   ...
   IFBW 150 kHz - Sweep 30/30
   IFBW 145 kHz - Sweep 1/30
   ...
   ```
8. **Success dialog appears:**
   ```
   Collection complete!

   Total sweeps: 90
   Mean sweep time: 0.059 s
   Sweep rate: 16.95 Hz

   Saved to:
   data/20260210/gui_sweep_collection_20260210_010523.xlsx
   ```

---

## Troubleshooting

### Button is gray ("Not Ready")
**Check:**
```bash
# Calibration file exists?
ls SOLT_1_2_43G-2_45G_300pt.cal

# Config file exists and is valid YAML?
uv run python -c "import yaml; yaml.safe_load(open('sweep_config.yaml'))"
```

### "Device connection lost"
**Fix:**
- Check USB cable
- Restart GUI
- Check device appears in system (Windows Device Manager / Linux lsusb)

### Window doesn't open
**Windows specific:**
- Ensure you have active desktop session (RDP/console)
- Qt on Windows requires windowing system (no offscreen mode)

---

## Configuration

### Edit Settings (in GUI)
- Start Frequency (Hz): `2430000000`
- Stop Frequency (Hz): `2450000000`
- Number of Points: `300`
- IFBW Values: `150000, 145000, 125000` (comma-separated)
- Stimulus Level (dBm): `-10`
- Number of Sweeps: `30`

### Or Edit YAML Directly
```yaml
# sweep_config.yaml
configurations:
  start_frequency: 2430000000
  stop_frequency:  2450000000
  num_points:      300
  stim_lvl_dbm:   -10
  avg_count:       1
  num_sweeps:      30

target:
  ifbw_values:
    - 150000
    - 145000
    - 125000
```

---

## Output Files

**Location:** `data/YYYYMMDD/`

**Filename:** `gui_sweep_collection_YYYYMMDD_HHMMSS.xlsx`

**Structure:**
- Summary sheet (metrics for all IFBW values)
- IFBW_150kHz sheet (detailed timing + S11 traces)
- IFBW_145kHz sheet
- IFBW_125kHz sheet

---

## Performance

**Typical Results** (2.43-2.45 GHz, 300 points):
- Sweep rate: **~17 Hz** (continuous mode)
- Collection time: **~16 seconds** (90 sweeps total)
- Plot update rate: **30 FPS** (pyqtgraph)

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│         7_realtime_vna_plotter_mvp.py           │  Entry Point
│  (Creates Model + View + Presenter, starts Qt)  │
└─────────────────┬───────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼──────┐   ┌────────▼────────┐
│    Model     │   │      View       │   (Main Thread)
│  (Pure Data) │   │  (PyQt6 Widgets)│
└──────────────┘   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │   Presenter     │   (State Machine)
                   │   + Worker      │
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │ Backend Wrapper │   (Worker Thread)
                   │  (Script 6)     │
                   └─────────────────┘
```

---

## Next Steps

1. **Test with device:** Follow checklist above
2. **Customize config:** Edit YAML or GUI widgets
3. **Analyze data:** Open Excel file, plot S11 traces
4. **Read full docs:** See `README.md` for details

---

**Questions?** Check `README.md` or `IMPLEMENTATION_SUMMARY.md`
