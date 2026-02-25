"""
plot_dataflux.py
================
Analyze and visualize VNA marker frequency-over-time data from Dataflux.csv.

CSV layout (Keysight/Agilent E5063A export format):
  Lines 1-12 : metadata key-value pairs
  Lines 13-14: blank
  Line  15   : column header  (Time, Marker Stimulus (Hz), Marker Y Real Value (dB))
  Lines 16+  : data rows (1800 points, ~20 ms apart)

Outputs
-------
  dataflux_plot.png  -- two-panel figure (same directory as this script)
  stdout summary     -- loaded points, total time, peaks, BPM, max gap, mean gap

Usage
-----
  uv run python plot_dataflux.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATH   = SCRIPT_DIR / "Dataflux.csv"
OUT_PNG    = SCRIPT_DIR / "dataflux_plot.png"

# ---------------------------------------------------------------------------
# Font configuration — use a Windows font with CJK (Japanese) support
# ---------------------------------------------------------------------------
# Meiryo or MS Gothic are present on standard Windows installs.
# Fallback to DejaVu Sans (no CJK) if neither is available.
import matplotlib.font_manager as fm

_JP_FONT_CANDIDATES = ["Meiryo", "Yu Gothic", "MS Gothic", "MS Mincho"]
_jp_font = "DejaVu Sans"
for _name in _JP_FONT_CANDIDATES:
    if any(f.name == _name for f in fm.fontManager.ttflist):
        _jp_font = _name
        break

matplotlib.rcParams["font.family"] = [_jp_font, "DejaVu Sans", "sans-serif"]

# ---------------------------------------------------------------------------
# 1. Parse header metadata (lines 1–12, comma-delimited key/value pairs)
# ---------------------------------------------------------------------------
HEADER_LINES = 12

metadata: dict[str, str] = {}
with open(CSV_PATH, encoding="utf-8") as fh:
    for i, raw in enumerate(fh):
        if i >= HEADER_LINES:
            break
        line = raw.rstrip("\n").rstrip("\r")
        if "," in line:
            key, _, val = line.partition(",")
            metadata[key.strip()] = val.strip()

vna_model = metadata.get("VNA Model", "VNA")

# ---------------------------------------------------------------------------
# 2. Load data
#    Layout: rows 1-12 = metadata, rows 13-14 = blank, row 15 = column header,
#    rows 16+ = data.  skiprows=14 advances past 12 metadata + 2 blank lines;
#    the first remaining row (index 0) is then used as the DataFrame header.
# ---------------------------------------------------------------------------
df = pd.read_csv(
    CSV_PATH,
    skiprows=14,
    names=["Time", "Freq_Hz", "dB"],
    header=0,          # row at position 0 after skip is the true column header
)

# Coerce numeric columns (scientific notation strings -> float)
df["Freq_Hz"] = pd.to_numeric(df["Freq_Hz"], errors="coerce")
df["dB"]      = pd.to_numeric(df["dB"],      errors="coerce")
df.dropna(subset=["Freq_Hz"], inplace=True)
df.reset_index(drop=True, inplace=True)

n_points = len(df)

# ---------------------------------------------------------------------------
# 3. Convert time strings to elapsed seconds
#    Format: HH:MM:SS.microseconds  (e.g. 14:36:10.013396)
# ---------------------------------------------------------------------------
df["_dt"] = pd.to_datetime(df["Time"], format="%H:%M:%S.%f", errors="coerce")
t0 = df["_dt"].iloc[0]
df["t_s"] = (df["_dt"] - t0).dt.total_seconds()

total_time = df["t_s"].iloc[-1]   # elapsed seconds at last sample

# ---------------------------------------------------------------------------
# 4. Convert frequency to MHz
# ---------------------------------------------------------------------------
df["Freq_MHz"] = df["Freq_Hz"] / 1e6

# ---------------------------------------------------------------------------
# 5. Peak detection on frequency trace
#    The signal is quantized to 0.025 MHz steps.  Baseline hovers near
#    233.475–233.500 MHz; genuine excursions reach up to ~233.80 MHz.
#    prominence=0.024 MHz (just below one quantization step) captures all
#    local maxima that represent real upward excursions, yielding ~274 peaks.
#    distance=1 allows back-to-back single-sample peaks on the plateau tops.
# ---------------------------------------------------------------------------
freq_mhz = df["Freq_MHz"].to_numpy()

peak_prominence = 0.024   # MHz — just below one quantization step (0.025 MHz)
peak_distance   = 1       # minimum samples between peaks

peaks, _ = find_peaks(
    freq_mhz,
    prominence=peak_prominence,
    distance=peak_distance,
)
n_peaks = len(peaks)

bpm = n_peaks / (total_time / 60.0) if total_time > 0 else 0.0

# ---------------------------------------------------------------------------
# 6. Inter-sample time differences
# ---------------------------------------------------------------------------
t_arr      = df["t_s"].to_numpy()
dt         = np.diff(t_arr)     # length N-1
dt_mean    = dt.mean()
dt_max     = dt.max()
dt_max_idx = int(np.argmax(dt))

# ---------------------------------------------------------------------------
# 7. Summary to stdout
# ---------------------------------------------------------------------------
print(f"Loaded {n_points} data points")
print(f"Total time: {total_time:.6f} s")
print(f"Detected peaks: {n_peaks}")
print(f"BPM: {bpm:.2f}")
print(f"Max time gap: {dt_max:.4f} s at index {dt_max_idx}")
print(f"Mean time gap: {dt_mean:.4f} s")
print(f"Figure saved to: {OUT_PNG}")

# ---------------------------------------------------------------------------
# 8. Build two-panel figure
# ---------------------------------------------------------------------------
fig, (ax_top, ax_bot) = plt.subplots(
    2, 1,
    figsize=(12, 8),
    gridspec_kw={"hspace": 0.42},
)

# ── Top subplot: frequency trace + detected peaks ─────────────────────────
ax_top.plot(
    df["t_s"], df["Freq_MHz"],
    color="#7EC8E3",
    linewidth=0.8,
    label="Frequency",
    zorder=2,
)
ax_top.scatter(
    df["t_s"].iloc[peaks],
    freq_mhz[peaks],
    color="red",
    s=20,
    zorder=3,
    label=f"Peaks ({n_peaks})",
)

ax_top.set_xlabel("Time (s)", fontsize=10)
ax_top.set_ylabel("Freq (MHz)", fontsize=10)
ax_top.set_title(vna_model, fontsize=12, fontweight="bold")
ax_top.tick_params(labelsize=9)
ax_top.legend(fontsize=8, loc="upper left")

# Annotation box — upper-right corner, inside axes
annotation_text = (
    f"\u7dcf\u6642\u9593 {total_time:.6f}\n"   # 総時間
    f"peak : {n_peaks}\n"
    f"bpm  : {bpm:.2f}"
)
ax_top.text(
    0.98, 0.97,
    annotation_text,
    transform=ax_top.transAxes,
    fontsize=9,
    verticalalignment="top",
    horizontalalignment="right",
    bbox=dict(
        boxstyle="round,pad=0.4",
        facecolor="lightyellow",
        edgecolor="gray",
        alpha=0.85,
    ),
    fontfamily=[_jp_font, "DejaVu Sans", "sans-serif"],
)

# ── Bottom subplot: inter-sample time differences ─────────────────────────
x_idx = np.arange(len(dt))

# Thin vertical lines from 0 to dt value (stem-like, no marker heads)
ax_bot.vlines(
    x_idx,
    ymin=0,
    ymax=dt,
    colors="#7EC8E3",
    linewidth=0.6,
)

ax_bot.set_xlabel("Data point index", fontsize=10)
ax_bot.set_ylabel("\u6642\u9593\u5dee (s)", fontsize=10)   # 時間差
ax_bot.tick_params(labelsize=9)

# Downward-pointing arrow annotation at the maximum gap
# Position the text above the bar, with arrowhead pointing down to the bar top
arrow_y_text = dt_max * 1.30
ax_bot.annotate(
    f"\u6700\u5927\u6642\u9593\u5dee {dt_max:.4f}",   # 最大時間差
    xy=(dt_max_idx, dt_max),
    xytext=(dt_max_idx, arrow_y_text),
    fontsize=8,
    ha="center",
    arrowprops=dict(
        arrowstyle="-|>",
        color="black",
        lw=0.8,
    ),
    bbox=dict(
        boxstyle="round,pad=0.3",
        facecolor="white",
        edgecolor="gray",
        alpha=0.85,
    ),
)

# Legend / info box — lower-right corner
legend_text = (
    f"\u6642\u9593\u5dee\n"                    # 時間差
    f"\u5e73\u5747\u5024\uff1a{dt_mean:.4f}"   # 平均値：
)
ax_bot.text(
    0.98, 0.05,
    legend_text,
    transform=ax_bot.transAxes,
    fontsize=9,
    verticalalignment="bottom",
    horizontalalignment="right",
    bbox=dict(
        boxstyle="round,pad=0.4",
        facecolor="lightyellow",
        edgecolor="gray",
        alpha=0.85,
    ),
    fontfamily=[_jp_font, "DejaVu Sans", "sans-serif"],
)

# ---------------------------------------------------------------------------
# 9. Save and display
# ---------------------------------------------------------------------------
fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
plt.show()
