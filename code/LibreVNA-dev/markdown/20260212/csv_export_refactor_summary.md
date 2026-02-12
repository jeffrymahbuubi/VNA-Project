# Script 6 Data Export Refactor — CSV Bundle

**Date:** 2026-02-12  
**Scope:** `6_librevna_gui_mode_sweep_test.py` + `gui/mvp/vna_backend.py`  
**Change:** Replace `.xlsx` multi-sheet workbook export with directory-based CSV bundle

---

## Motivation

- **Smaller file sizes** — CSV files are text-based and compress better than binary `.xlsx`
- **Easier per-sweep loading** — Each sweep is a standalone file; downstream analysis (notebooks) can load individual sweeps or ranges without parsing entire workbook
- **Simpler dependencies** — Remove `openpyxl` from requirements; use only Python stdlib `csv` module

---

## Changes Summary

### Files Modified

1. **`code/LibreVNA-dev/scripts/6_librevna_gui_mode_sweep_test.py`**
   - Renamed `save_xlsx()` → `save_csv_bundle()`
   - Replaced multi-sheet xlsx generation with:
     - One CSV file per sweep (`s11_sweep_N.csv`)
     - One summary text file (`summary.txt` with PrettyTable-formatted sections)
   - Updated CLI help text: `--no-save` now says "Skip CSV bundle export"
   - Updated docstrings to reflect new output structure

2. **`code/LibreVNA-dev/gui/mvp/vna_backend.py`**
   - Applied same refactor to standalone GUI backend copy
   - Simplified `summary.txt` formatting (no PrettyTable dependency in GUI backend; uses plain text columns)

3. **`code/requirements.txt`**
   - Removed `openpyxl>=3.1.0`
   - Updated comment: "Excel export" → "CSV export"

---

## New Output Structure

### Directory Layout

```
data/YYYYMMDD/{mode}_sweep_test_{YYYYMMDD}_{HHMMSS}/
    s11_sweep_1.csv
    s11_sweep_2.csv
    ...
    s11_sweep_N.csv
    summary.txt
```

Where `{mode}` is `single` or `continuous`.

### CSV File Format

**Script 6 (scripts/)** — includes timestamps:
```csv
Time,Frequency (Hz),Magnitude (dB)
14:23:45.123456,2430000000,-35.1234
14:23:45.234567,2431000000,-34.5678
...
```

**GUI Backend (gui/mvp/)** — no timestamps (streaming callback doesn't track them):
```csv
Frequency (Hz),Magnitude (dB)
2430000000,-35.1234
2431000000,-34.5678
...
```

### summary.txt Format

Three PrettyTable-formatted sections (script 6) or plain text tables (GUI backend):

1. **Sweep Configuration**
   - Mode, IFBW, Start/Stop Freq, Points, STIM Level, Avg Count, Num Sweeps

2. **Per-Sweep Timing**
   - Sweep #, Sweep Time (s), Sweep Time (ms), Update Rate (Hz)

3. **Summary Metrics** (one row per IFBW value)
   - Mode, IFBW (kHz), Mean Time (s), Std Dev (s), Min Time (s), Max Time (s), Rate (Hz), Noise Floor (dB), Trace Jitter (dB)

---

## Backward Compatibility

**Breaking change** — Old scripts/notebooks expecting `.xlsx` files will need to be updated to:
- Read CSV files instead of Excel sheets
- Parse `summary.txt` if needed (or ignore it and compute metrics directly from CSVs)

**Migration path:**
- Use `pandas.read_csv()` to load individual sweeps:
  ```python
  import pandas as pd
  sweep_1 = pd.read_csv("s11_sweep_1.csv")
  ```
- To replicate old multi-sweep structure:
  ```python
  import glob
  sweep_files = sorted(glob.glob("s11_sweep_*.csv"))
  sweeps = [pd.read_csv(f) for f in sweep_files]
  ```

---

## Testing

✓ **Syntax validation:** Both scripts parse without errors  
✓ **Import validation:** Script 6 imports load successfully  

**Next steps for full validation:**
1. Run script 6 in single mode with a short sweep (`--num-sweeps 3`)
2. Verify CSV bundle is created in `data/YYYYMMDD/{mode}_sweep_test_{timestamp}/`
3. Verify `summary.txt` formatting is correct
4. Load CSV files in a notebook and compare data to previous xlsx output

---

## Code Metrics

**Lines removed:** ~300 (xlsx generation logic + openpyxl style definitions)  
**Lines added:** ~150 (CSV writing + summary.txt text formatting)  
**Net reduction:** ~150 lines  

**Dependencies removed:** `openpyxl` (binary Excel library)  
**Dependencies added:** None (stdlib `csv` only)  

---

## Future Enhancements

1. **Compression** — Optionally write `.csv.gz` for even smaller file sizes
2. **Metadata JSON** — Add `metadata.json` with structured sweep config (easier programmatic parsing than `summary.txt`)
3. **Parquet export** — For very large datasets, offer parquet format (column-oriented, highly compressed)
