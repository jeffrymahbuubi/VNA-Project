# LibreVNA Real-Time Plotter GUI

PyQt6-based graphical interface for real-time S-parameter visualization during VNA data collection.

## Architecture

**MVP (Model-View-Presenter) Pattern**

```
mvp/
├── model.py           - Pure Python business logic (device, calibration, sweep config)
├── view.py            - PyQt6 UI (loads main_window.ui, display methods only)
├── presenter.py       - Mediator (wires Model ↔ View, manages worker thread)
└── backend_wrapper.py - Adapter for script 6 (ContinuousModeSweep integration)
```

**Key Features:**
- ✅ Real-time S11 trace plotting (pyqtgraph)
- ✅ Thread-safe GUI updates (all SCPI/backend runs in QThread)
- ✅ Auto-detection of calibration and config files on startup
- ✅ Multi-IFBW sweep support with live progress updates
- ✅ Automatic Excel export (multi-sheet workbook)
- ✅ Fully integrated with validated script 6 backend

## Prerequisites

### Hardware
- LibreVNA device connected via USB
- 50-ohm matched load on port 1 (for S11 measurement)

### Software
```bash
# Install GUI dependencies
cd code
uv pip install PyQt6 pyqtgraph

# All script 6 dependencies should already be installed:
# numpy, yaml, openpyxl, prettytable
```

### Required Files

**Calibration file** (place in `gui/` directory):
```
gui/SOLT_1_2_43G-2_45G_300pt.cal
```

**Configuration file** (place in `gui/` directory):
```
gui/sweep_config.yaml
```

Example `sweep_config.yaml`:
```yaml
configurations:
  start_frequency: 2430000000      # Hz (2.43 GHz)
  stop_frequency:  2450000000      # Hz (2.45 GHz)
  num_points:      300
  stim_lvl_dbm:   -10
  avg_count:       1
  num_sweeps:      30              # sweeps per IFBW value

target:
  ifbw_values:                     # List of IFBW values to sweep
    - 150000                       # 150 kHz
    - 145000                       # 145 kHz
    - 125000                       # 125 kHz
```

## Usage

### Launch GUI

```bash
cd code/LibreVNA-dev/gui
uv run python 7_realtime_vna_plotter_mvp.py
```

### Workflow

1. **Startup**
   - GUI auto-detects `.cal` and `.yaml` files in `gui/` directory
   - Status bar shows: `✓ Auto-loaded: SOLT_1_2_43G-2_45G_300pt.cal`
   - Configuration widgets populated from YAML
   - "Collect Data" button turns GREEN when ready

2. **Configuration** (optional)
   - Edit any parameter in the GUI widgets
   - Start/Stop frequency (Hz)
   - Number of points
   - IFBW values (comma-separated list)
   - Stimulus level (dBm)
   - Number of sweeps per IFBW

3. **Data Collection**
   - Click green "Collect Data" button
   - Button turns RED with blinking animation ("Collecting Data...")
   - Status bar shows: `"IFBW 150 kHz - Sweep 1/30"`
   - Real-time S11 plot updates with each sweep
   - Process repeats for all IFBW values

4. **Completion**
   - Button returns to GREEN
   - Dialog shows: `"Collection complete! Saved to: data/YYYYMMDD/gui_sweep_collection_YYYYMMDD_HHMMSS.xlsx"`
   - Excel file contains:
     - Summary sheet (all IFBW metrics)
     - Per-IFBW detail sheets (timing, S11 traces)

## GUI Components

### Main Window (`main_window.ui`)

**Configuration Panel:**
- Start Frequency (Hz)
- Stop Frequency (Hz)
- Number of Points
- Stimulus Level (dBm)
- Average Count
- Number of Sweeps
- IFBW Values (comma-separated)

**Plot Widget:**
- Real-time S11 magnitude (dB) vs Frequency (Hz)
- Yellow trace with grid
- Fixed Y-range: -60 to 0 dB (during collection)

**Control Button:**
- GREEN: "Collect Data" (ready to start)
- RED (blinking): "Collecting Data..." (running)
- GRAY: "Not Ready" (calibration or config missing)

**Status Bar:**
- Shows current operation status
- Progress updates during collection

**Menu Bar:**
- Device → Serial: `<device_serial>` (updated after connection)
- File → Load Calibration
- File → Load Config

## Data Output

### Excel Workbook Structure

**File location:** `data/YYYYMMDD/gui_sweep_collection_YYYYMMDD_HHMMSS.xlsx`

**Summary Sheet:**
| Mode       | IFBW (kHz) | Mean Time (s) | Std Dev (s) | Rate (Hz) | Noise Floor (dB) | Trace Jitter (dB) |
|------------|------------|---------------|-------------|-----------|------------------|-------------------|
| continuous | 150        | 0.0589        | 0.0012      | 16.98     | -45.23           | 0.0034            |
| continuous | 145        | 0.0591        | 0.0011      | 16.92     | -45.18           | 0.0036            |
| continuous | 125        | 0.0595        | 0.0013      | 16.81     | -45.31           | 0.0032            |

**Per-IFBW Sheets** (`IFBW_150kHz`, `IFBW_145kHz`, etc.):
- Configuration block (frequency, points, stimulus, etc.)
- Timing data (per-sweep times, update rates)
- S11 trace data (frequency, magnitude columns for each sweep)
- Metrics block (noise floor, trace jitter)

## Threading Model

**Main Thread (GUI):**
- All PyQt6 widgets and plot updates
- User interactions (button clicks, menu selections)
- Presenter signal handlers

**Worker Thread (QThread):**
- LibreVNA-GUI subprocess lifecycle
- SCPI communication
- Sweep execution (continuous mode streaming)
- Excel export

**Communication:**
- Worker emits Qt signals → Presenter slots (on main thread)
- Thread-safe via Qt's queued connection mechanism

## Troubleshooting

### Button stays GRAY ("Not Ready")

**Cause:** Calibration not loaded or config invalid

**Fix:**
```bash
# Check calibration file exists
ls gui/SOLT_1_2_43G-2_45G_300pt.cal

# Check config file exists
ls gui/sweep_config.yaml

# Verify config is valid YAML
uv run python -c "import yaml; yaml.safe_load(open('gui/sweep_config.yaml'))"
```

### "Device connection lost" during collection

**Cause:** LibreVNA device disconnected or GUI subprocess crashed

**Fix:**
- Check USB cable connection
- Restart GUI application
- Check LibreVNA-GUI binary path in `backend_wrapper.py`

### Plot not updating

**Cause:** Thread communication issue or Qt event loop blocked

**Fix:**
- Check console for Python exceptions
- Ensure worker signals are connected in `presenter.py`
- Verify `QApplication.exec()` is running

### Excel file not saved

**Cause:** Data directory permissions or disk space

**Fix:**
```bash
# Check data directory exists and is writable
mkdir -p ../data/$(date +%Y%m%d)
ls -ld ../data/$(date +%Y%m%d)
```

## Development Notes

### Adding New Configuration Parameters

1. Add field to `SweepConfig` dataclass (`mvp/model.py`)
2. Add widget to `main_window.ui` (Qt Designer)
3. Wire widget in `view.py` (`populate_sweep_config` and `read_sweep_config`)
4. Update `backend_wrapper.py` to pass parameter to script 6

### Modifying Plot Appearance

Edit `view.py` → `_setup_plot_widget()`:
```python
self.plot_widget.setYRange(-60, 0)          # Y-axis range
self.plot_data_item = self.plot_widget.plot(
    [], [],
    pen=pg.mkPen(color='y', width=2),       # Pen color/width
    name='S11'
)
```

### Changing Button Colors

Edit `view.py` → `set_collecting_state()`:
```python
# Green (ready)
self.pushButton.setStyleSheet("background-color: rgb(74, 222, 128);")

# Red (collecting)
self.pushButton.setStyleSheet("background-color: rgb(239, 68, 68);")

# Gray (not ready)
self.pushButton.setStyleSheet("background-color: rgb(156, 163, 175);")
```

## Testing

### Unit Test - Model Layer
```bash
cd gui
uv run python -c "
from mvp.model import VNADataModel, SweepConfig
import yaml

model = VNADataModel()
print('Model created:', model.is_ready_to_collect())

with open('sweep_config.yaml') as f:
    config = SweepConfig.from_dict(yaml.safe_load(f))
print('Config valid:', config.is_valid())
"
```

### Integration Test - Full GUI (requires device)
```bash
cd gui
uv run python 7_realtime_vna_plotter_mvp.py

# Expected behavior:
# 1. Window opens (1280x720)
# 2. Status shows "✓ Auto-loaded: SOLT_1_2_43G-2_45G_300pt.cal"
# 3. Config widgets populated
# 4. Button is GREEN and enabled
# 5. Click button → RED blinking animation
# 6. Plot updates in real-time
# 7. Excel file saved after completion
```

## Performance

**Typical sweep rates** (2.43-2.45 GHz, 300 points, 50-ohm load):

| Mode              | IFBW    | Rate (Hz) | Notes                          |
|-------------------|---------|-----------|--------------------------------|
| Continuous (GUI)  | 150 kHz | ~17 Hz    | Best SCPI path                |
| Continuous (GUI)  | 145 kHz | ~17 Hz    | Minimal IFBW impact            |
| Continuous (GUI)  | 125 kHz | ~17 Hz    | Stable performance             |
| USB Direct (TBD)  | Any     | ~33 Hz    | Theoretical max (not implemented) |

**GUI responsiveness:**
- Plot updates: ~30 FPS (pyqtgraph handles buffering)
- Button clicks: Immediate (main thread always responsive)
- Window resize/minimize: No lag (worker thread isolation)

## References

- **Script 6:** `scripts/6_librevna_gui_mode_sweep_test.py` - Backend sweep logic
- **SCPI Wrapper:** `scripts/libreVNA.py` - TCP socket abstraction
- **Plan Document:** Root directory plan file - Full architecture details
- **LibreVNA Docs:** `Programming_Guide.pdf` - SCPI command reference
