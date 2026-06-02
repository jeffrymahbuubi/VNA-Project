"""model.py — E5063A Data Collector model layer (pure logic, no Qt).

Ported from `LibreVNA-dev/gui/mvp/model.py` with the E5063A deltas from
docs/e5063a-gui-ux-spec.md §4:
  - CalibrationState repurposed for the E5063A `.sta` / host-ECal world.
  - SweepConfig grid (start/stop/points) is user-editable (no .cal JSON parse);
    adds is_grid_stale_vs() to drive the "re-cal needed" hint.
  - New AcquisitionMode enum and FilenameSpec (filename composition, ux-spec §5).

Unit-testable without a GUI or an instrument.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple


# ═══════════════════════════════════════════════════════════
# Device / calibration / config
# ═══════════════════════════════════════════════════════════
@dataclass
class DeviceInfo:
    """E5063A connection state."""
    serial_number: str = ""
    firmware: str = ""
    idn_string: str = ""
    connected: bool = False


@dataclass
class CalibrationState:
    """E5063A calibration state (host-ECal or recalled .sta).

    `grid` is the (start_hz, stop_hz, points) the cal is valid for — used to
    detect when the user edits the grid and a re-cal becomes necessary.
    """
    source: str = "existing"            # "existing" (recall .sta) | "ecal" (run ECal)
    sta_path: str = ""                  # instrument-side .sta path
    active: bool = False                # mirrors :SENS1:CORR:STAT?
    cal_type: str = ""                  # e.g. "SOLT1"
    grid: Optional[Tuple[int, int, int]] = None   # (start_hz, stop_hz, points)
    ecal_port: int = 1
    conf_min_mean_max: Optional[Tuple[float, float, float]] = None


@dataclass
class SweepConfig:
    """E5063A sweep configuration. Grid is user-editable (ux-spec OQ-2 revised)."""
    start_frequency: int = 200_000_000   # Hz
    stop_frequency: int = 250_000_000    # Hz
    num_points: int = 801
    stim_lvl_dbm: float = -5.0
    # Sanity-check mode sweeps a set of IFBW values; monitor uses one (MonitorConfig).
    ifbw_values: List[int] = field(default_factory=lambda: [300_000, 100_000, 50_000])  # Hz
    num_sweeps: int = 30                 # sweeps per IFBW (sanity mode)

    @property
    def center_frequency(self) -> int:
        return (self.start_frequency + self.stop_frequency) // 2

    @property
    def span_frequency(self) -> int:
        return self.stop_frequency - self.start_frequency

    @property
    def grid(self) -> Tuple[int, int, int]:
        return (self.start_frequency, self.stop_frequency, self.num_points)

    def is_valid(self) -> bool:
        if self.start_frequency >= self.stop_frequency:
            return False
        if not (1 < self.num_points <= 1601):
            return False
        if self.num_sweeps <= 0:
            return False
        if not self.ifbw_values or any(v <= 0 for v in self.ifbw_values):
            return False
        return True

    def is_grid_stale_vs(self, cal_grid: Optional[Tuple[int, int, int]]) -> bool:
        """True if the current grid differs from the grid the cal was made at.

        IFBW/power are NOT part of this — they don't invalidate the cal
        (migration-spec §4A.6). Only start/stop/points do.
        """
        if cal_grid is None:
            return False
        return self.grid != cal_grid


@dataclass
class MonitorConfig:
    """Continuous-monitor configuration (single IFBW)."""
    ifbw_hz: int = 300_000
    log_interval_ms: str = "auto"        # "auto" or int-as-str ms
    duration_s: float = 0.0              # 0 = indefinite
    warmup_sweeps: int = 5
    stop_mode: str = "duration"          # "duration" | "count" | "manual"
    query_number: int = 1000             # target point count when stop_mode == "count"


@dataclass
class MonitorRecord:
    """One logged monitor point (Dataflux scalar time-series)."""
    timestamp: datetime
    freq_hz: float        # frequency of the S11 minimum (Hz)
    s11_db: float         # S11 magnitude at that frequency (dB)


# ═══════════════════════════════════════════════════════════
# Acquisition mode + filename
# ═══════════════════════════════════════════════════════════
class AcquisitionMode(Enum):
    MONITOR = "monitor"     # Continuous min-S11-frequency logging (the objective)
    SANITY = "sanity"       # Device sanity-check IFBW benchmark

    @property
    def label(self) -> str:
        return {"monitor": "Continuous Monitor", "sanity": "Device Sanity Check"}[self.value]


@dataclass
class FilenameSpec:
    """Composes the output filename (ux-spec §5). Full metadata lives in-file."""
    label: str = ""
    include_mode: bool = True
    include_grid: bool = True
    # timestamp is ALWAYS included.

    @staticmethod
    def _sanitize(s: str) -> str:
        s = s.strip().replace(" ", "-")
        return re.sub(r"[^A-Za-z0-9._-]", "", s)

    def compose(
        self,
        mode: AcquisitionMode,
        config: SweepConfig,
        monitor_config: MonitorConfig,
        stamp: str,
        ext: str,
    ) -> str:
        parts: List[str] = []
        lbl = self._sanitize(self.label) or "run"
        parts.append(lbl)
        if self.include_mode:
            parts.append(f"{mode.value}_S11")
        if self.include_grid:
            start_mhz = config.start_frequency / 1e6
            stop_mhz = config.stop_frequency / 1e6
            if mode is AcquisitionMode.MONITOR:
                ifbw_khz = monitor_config.ifbw_hz / 1e3
                parts.append(f"{start_mhz:g}-{stop_mhz:g}MHz_{config.num_points}pt_{ifbw_khz:g}kHz")
            else:
                parts.append(f"{start_mhz:g}-{stop_mhz:g}MHz_{config.num_points}pt_multiIFBW")
        parts.append(stamp)  # always
        return "_".join(parts) + "." + ext


# ═══════════════════════════════════════════════════════════
# Central model
# ═══════════════════════════════════════════════════════════
class VNADataModel:
    """Central data model for the E5063A Data Collector GUI."""

    def __init__(self):
        self.device = DeviceInfo()
        self.calibration = CalibrationState()
        self.config = SweepConfig()
        self.monitor_config = MonitorConfig()
        self.mode: AcquisitionMode = AcquisitionMode.MONITOR
        self.filename = FilenameSpec()
        self.save_data_folder: Optional[str] = None
        self.scientific_notation: bool = True   # F-6 CSV number format

    def is_ready_to_collect(self) -> bool:
        """Gate for the Proceed button (ux-spec §1)."""
        return (
            self.device.connected
            and self.calibration.active
            and self.config.is_valid()
        )

    def cal_is_stale(self) -> bool:
        """True when the grid was edited after calibration → re-cal recommended."""
        return self.config.is_grid_stale_vs(self.calibration.grid)

    def __repr__(self) -> str:
        return (
            f"VNADataModel(connected={self.device.connected}, "
            f"cal_active={self.calibration.active}, "
            f"mode={self.mode.value}, "
            f"config_valid={self.config.is_valid()}, "
            f"ready={self.is_ready_to_collect()})"
        )
