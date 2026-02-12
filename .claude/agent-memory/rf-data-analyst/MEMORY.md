# RF Data Analyst Agent Memory

## Jupyter MCP Server — Path Rules (CRITICAL)

The Jupyter MCP server requires **relative paths** (relative to the Jupyter server root), NOT absolute paths.

- **Server root**: `code/LibreVNA-dev/notebook` (the directory where JupyterLab was started)
- **Correct path**: `20260212/sweep_trace_analysis.ipynb`
- **WRONG path**: `D:/AUNUUN JEFFRY MAHBUUBI/.../notebook/20260212/sweep_trace_analysis.ipynb`

Using absolute paths causes a 404 error: `"is not a relative API path"`.

### Tools affected
- `mcp__jupyter-mcp-server__use_notebook` — `notebook_path` must be relative
- `mcp__jupyter-mcp-server__list_files` — `path` must be relative
- All other Jupyter MCP tools that accept file paths

### Correct workflow
1. Use `mcp__jupyter-mcp-server__list_files` with `path: ""` (empty = server root) to discover structure
2. Use relative paths like `20260212/notebook_name.ipynb` for `use_notebook`
3. If you need to create directories, use `mcp__filesystem__create_directory` with the **absolute** path first, then reference via **relative** path in Jupyter tools

### Reading/writing data files from within notebook cells
When writing Python code inside notebook cells that reads xlsx/csv files from `data/` directory, use **absolute paths** in the Python code itself (since the kernel's cwd may differ from the Jupyter server root). Example:
```python
data_path = r"D:\...\code\LibreVNA-dev\data\20260212\file.xlsx"
```

## XLSX Data Structure — Script 6 Output

Script `6_librevna_gui_mode_sweep_test.py` produces multi-sheet xlsx workbooks:
- **Summary** sheet: one row per IFBW with timing/metric columns
- **IFBW_{n}kHz** sheets: Configuration block (rows 1-9), Timing block (row 10+), S11 Trace blocks, Metrics block
- S11 Trace blocks have columns: **Time** (HH:MM:SS.ffffff), **Frequency (Hz)**, **Magnitude (dB)**
- Multiple sweep trace blocks per sheet: "S11 Sweep_1 Trace", "S11 Sweep_2 Trace", etc.

## Plotting Patterns — VNA Sweep Analysis

### Two-subplot pattern (matching example_plot.jpg style)
- **Top plot**: Frequency (MHz) vs Time (seconds) — shows sweep progression or resonant frequency tracking
- **Bottom plot**: Time differences between consecutive points vs point index — reveals timing jitter/gaps
- Mark max time difference with annotation arrow
- Show mean time difference as horizontal dashed line
- Save plot as PNG alongside the notebook
