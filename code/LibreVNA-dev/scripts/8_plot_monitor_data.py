"""
8_plot_monitor_data.py
======================
Analyze and visualize VNA monitor-mode frequency-over-time data produced by
the LibreVNA real-time GUI (Script 7, monitor mode).

CSV layout (VNA-DATAFLUX format, same as Dataflux.csv from Keysight/Agilent):
  Lines 1-12 : metadata key-value pairs  (Application, VNA Model, Serial, ...)
  Lines 13-14: blank
  Line  15   : column header  (Time, Marker Stimulus (Hz), Marker Y Real Value (dB))
  Lines 16+  : data rows

Outputs
-------
  stdout summary     -- loaded points, total time, peaks, BPM, max gap, mean gap
  <input_stem>_plot.png  -- two-panel figure saved next to the CSV  (--save-plot)

Usage
-----
  uv run python 8_plot_monitor_data.py --load-data path/to/vna_monitor.csv
  uv run python 8_plot_monitor_data.py --load-data path/to/vna_monitor.csv --save-plot
  uv run python 8_plot_monitor_data.py --load-data path/to/vna_monitor.csv --save-plot --no-show-plot
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

# ---------------------------------------------------------------------------
# Font configuration -- use a Windows font with CJK (Japanese) support.
# Meiryo or MS Gothic are present on standard Windows installs.
# Fallback to DejaVu Sans (no CJK) if neither is available.
# ---------------------------------------------------------------------------
import matplotlib.font_manager as fm

_JP_FONT_CANDIDATES = ["Meiryo", "Yu Gothic", "MS Gothic", "MS Mincho"]
_jp_font = "DejaVu Sans"
for _name in _JP_FONT_CANDIDATES:
    if any(f.name == _name for f in fm.fontManager.ttflist):
        _jp_font = _name
        break

matplotlib.rcParams["font.family"] = [_jp_font, "DejaVu Sans", "sans-serif"]


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Plot VNA monitor-mode frequency-over-time data from a "
            "VNA-DATAFLUX CSV file."
        )
    )
    parser.add_argument(
        "--load-data",
        metavar="PATH",
        required=True,
        help="Path to the VNA monitor CSV file to analyze.",
    )
    parser.add_argument(
        "--save-plot",
        action="store_true",
        default=False,
        help=(
            "Save the figure as <input_stem>_plot.png next to the input CSV. "
            "Default: OFF."
        ),
    )
    # --show-plot is ON by default; --no-show-plot suppresses plt.show().
    parser.add_argument(
        "--show-plot",
        dest="show_plot",
        action="store_true",
        default=True,
        help="Display the interactive plot window (default: ON).",
    )
    parser.add_argument(
        "--no-show-plot",
        dest="show_plot",
        action="store_false",
        help="Suppress the interactive plot window.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# 1. Parse header metadata (lines 1-12, comma-delimited key/value pairs)
# ---------------------------------------------------------------------------

HEADER_LINES = 12


def parse_metadata(csv_path: Path) -> dict[str, str]:
    """Read the first HEADER_LINES lines and return a key/value dict."""
    metadata: dict[str, str] = {}
    with open(csv_path, encoding="utf-8") as fh:
        for i, raw in enumerate(fh):
            if i >= HEADER_LINES:
                break
            line = raw.rstrip("\n").rstrip("\r")
            if "," in line:
                key, _, val = line.partition(",")
                metadata[key.strip()] = val.strip()
    return metadata


# ---------------------------------------------------------------------------
# 2. Load data
#    Layout: rows 1-12 = metadata, rows 13-14 = blank, row 15 = column header,
#    rows 16+ = data.  skiprows=14 advances past 12 metadata + 2 blank lines;
#    the first remaining row (position 0) is then used as the DataFrame header.
# ---------------------------------------------------------------------------

def load_data(csv_path: Path) -> pd.DataFrame:
    """
    Read the monitor CSV into a DataFrame with columns:
      Time (str), Freq_Hz (float), dB (float), t_s (float), Freq_MHz (float)
    """
    df = pd.read_csv(
        csv_path,
        skiprows=14,
        names=["Time", "Freq_Hz", "dB"],
        header=0,  # row at position 0 after skip is the true column header
    )

    # Coerce numeric columns (scientific notation strings -> float)
    df["Freq_Hz"] = pd.to_numeric(df["Freq_Hz"], errors="coerce")
    df["dB"] = pd.to_numeric(df["dB"], errors="coerce")
    df.dropna(subset=["Freq_Hz"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Convert time strings to elapsed seconds
    # Format: HH:MM:SS.microseconds  (e.g. 01:47:19.025237)
    df["_dt"] = pd.to_datetime(df["Time"], format="%H:%M:%S.%f", errors="coerce")
    t0 = df["_dt"].iloc[0]
    df["t_s"] = (df["_dt"] - t0).dt.total_seconds()

    # Frequency in MHz for plotting
    df["Freq_MHz"] = df["Freq_Hz"] / 1e6

    return df


# ---------------------------------------------------------------------------
# 3. Peak detection on frequency trace
# ---------------------------------------------------------------------------

def detect_peaks(
    freq_mhz: np.ndarray,
    prominence: float = 0.024,
    distance: int = 1,
) -> np.ndarray:
    """
    Detect local frequency excursion peaks.

    prominence=0.024 MHz sits just below one quantization step (0.025 MHz),
    capturing all genuine upward excursions while ignoring quantization noise.
    distance=1 allows back-to-back single-sample peaks on plateau tops.

    Returns an array of peak indices.
    """
    peaks, _ = find_peaks(freq_mhz, prominence=prominence, distance=distance)
    return peaks


# ---------------------------------------------------------------------------
# 4. Build the two-panel figure
# ---------------------------------------------------------------------------

def build_figure(
    df: pd.DataFrame,
    peaks: np.ndarray,
    metadata: dict[str, str],
) -> plt.Figure:
    """
    Construct and return the two-panel matplotlib figure.

    Top panel  : Frequency (MHz) over time with detected peaks marked.
    Bottom panel: Inter-sample time differences (vlines stem plot) with
                  max-gap annotation.
    """
    freq_mhz   = df["Freq_MHz"].to_numpy()
    t_arr      = df["t_s"].to_numpy()
    total_time = t_arr[-1]

    n_points = len(df)
    n_peaks  = len(peaks)
    bpm      = n_peaks / (total_time / 60.0) if total_time > 0 else 0.0

    dt         = np.diff(t_arr)
    dt_mean    = dt.mean()
    dt_max     = dt.max()
    dt_max_idx = int(np.argmax(dt))

    # Extract display metadata
    vna_model    = metadata.get("VNA Model", "VNA")
    vna_serial   = metadata.get("VNA Serial", "")
    ifbw_khz     = metadata.get("IF Bandwidth(KHz)", "")
    points_str   = metadata.get("Points", "")
    freq_start   = metadata.get("Freq Start(MHz)", "")
    freq_stop    = metadata.get("Freq Stop(MHz)", "")
    start_dt_str = metadata.get("Start DateTime", "")

    # Build a descriptive title
    title_parts = [vna_model]
    if vna_serial:
        title_parts.append(f"SN {vna_serial}")
    if freq_start and freq_stop:
        title_parts.append(f"{freq_start}–{freq_stop} MHz")
    if points_str:
        title_parts.append(f"{points_str} pts")
    if ifbw_khz:
        title_parts.append(f"IFBW {ifbw_khz} kHz")
    title_str = "   |   ".join(title_parts)

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1,
        figsize=(12, 8),
        gridspec_kw={"hspace": 0.42},
    )

    # ── Top subplot: frequency trace + detected peaks ─────────────────────
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

    # Robust y-axis limits: median + IQR-based inlier window.
    #
    # Simple percentile clipping (1st/99th) is insufficient when the outlier
    # fraction exceeds ~1% — in this dataset ~15% of points fall back to the
    # sweep-start frequency (200 MHz) when the marker loses lock, which pushes
    # even the 1st-percentile value into the outlier band.
    #
    # Strategy:
    #   1. Compute median and IQR of the full freq_mhz array.
    #   2. Define inliers as points within median ± 3*IQR
    #      (generous enough to keep all genuine resonance variation, yet the
    #      43 MHz gap to the 200 MHz outlier cluster is always >> 3*IQR).
    #   3. Set y-axis to [inlier_min - margin, inlier_max + margin] with a
    #      minimum ±0.5 MHz padding.
    _med = np.median(freq_mhz)
    _iqr = np.percentile(freq_mhz, 75) - np.percentile(freq_mhz, 25)
    _inlier_mask = np.abs(freq_mhz - _med) <= 3 * max(_iqr, 0.5)
    _inliers = freq_mhz[_inlier_mask] if _inlier_mask.any() else freq_mhz
    _y_lo = _inliers.min()
    _y_hi = _inliers.max()
    _margin = max((_y_hi - _y_lo) * 0.5, 0.5)  # at least ±0.5 MHz padding
    ax_top.set_ylim(_y_lo - _margin, _y_hi + _margin)

    ax_top.set_xlabel("Time (s)", fontsize=10)
    ax_top.set_ylabel("Freq (MHz)", fontsize=10)
    ax_top.set_title(title_str, fontsize=11, fontweight="bold")
    ax_top.tick_params(labelsize=9)
    ax_top.legend(fontsize=8, loc="upper left")

    # Annotation box -- upper-right corner, inside axes
    annotation_text = (
        f"\u7dcf\u6642\u9593 {total_time:.6f} s\n"   # 総時間
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

    # ── Bottom subplot: inter-sample time differences ─────────────────────
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
    arrow_y_text = dt_max * 1.30
    ax_bot.annotate(
        f"\u6700\u5927\u6642\u9593\u5dee {dt_max:.4f} s",   # 最大時間差
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

    # Legend / info box -- lower-right corner
    legend_text = (
        f"\u6642\u9593\u5dee\n"                     # 時間差
        f"\u5e73\u5747\u5024\uff1a{dt_mean:.4f} s"  # 平均値：
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

    return fig


# ---------------------------------------------------------------------------
# 5. stdout summary
# ---------------------------------------------------------------------------

def print_summary(
    df: pd.DataFrame,
    peaks: np.ndarray,
    out_png: Path | None,
) -> None:
    """Print analysis summary to stdout."""
    n_points   = len(df)
    t_arr      = df["t_s"].to_numpy()
    total_time = t_arr[-1]
    n_peaks    = len(peaks)
    bpm        = n_peaks / (total_time / 60.0) if total_time > 0 else 0.0

    dt         = np.diff(t_arr)
    dt_mean    = dt.mean()
    dt_max     = dt.max()
    dt_max_idx = int(np.argmax(dt))

    print(f"Loaded {n_points} data points")
    print(f"Total time: {total_time:.6f} s")
    print(f"Detected peaks: {n_peaks}")
    print(f"BPM: {bpm:.2f}")
    print(f"Max time gap: {dt_max:.4f} s at index {dt_max_idx}")
    print(f"Mean time gap: {dt_mean:.4f} s")
    if out_png is not None:
        print(f"Figure saved to: {out_png}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point: parse args, load data, detect peaks, plot, save/show."""
    args = parse_args()

    # Resolve input path to absolute so the script works from any cwd
    csv_path = Path(args.load_data).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {csv_path}")

    # Determine output PNG path (resolved next to input CSV)
    out_png: Path | None = None
    if args.save_plot:
        out_png = csv_path.parent / (csv_path.stem + "_plot.png")

    # 1. Parse metadata header
    metadata = parse_metadata(csv_path)

    # 2. Load data
    df = load_data(csv_path)

    # 3. Detect peaks
    freq_mhz = df["Freq_MHz"].to_numpy()
    peaks = detect_peaks(freq_mhz)

    # 4. Print summary (before blocking plt.show())
    print_summary(df, peaks, out_png)

    # 5. Build figure
    fig = build_figure(df, peaks, metadata)

    # 6. Save if requested
    if out_png is not None:
        fig.savefig(out_png, dpi=150, bbox_inches="tight")

    # 7. Show if requested
    if args.show_plot:
        plt.show()

    plt.close(fig)


if __name__ == "__main__":
    main()
