"""
Model layer for LibreVNA GUI (MVP architecture).

Pure Python - NO PyQt dependencies. This module contains all business logic,
data structures, and validation rules. It is unit-testable without GUI.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class DeviceInfo:
    """VNA device connection state."""

    serial_number: str = ""
    connected: bool = False
    idn_string: str = ""


@dataclass
class CalibrationState:
    """Calibration file state."""

    file_path: str = ""
    loaded: bool = False
    active_cal_type: str = "SOLT"  # Default calibration type


@dataclass
class SweepConfig:
    """VNA sweep configuration parameters."""

    start_frequency: int = 200000000  # Hz
    stop_frequency: int = 250000000  # Hz
    num_points: int = 801
    stim_lvl_dbm: int = -10
    avg_count: int = 1
    num_sweeps: int = 30
    ifbw_values: List[int] = field(default_factory=lambda: [50000, 10000, 1000])  # Hz

    @property
    def center_frequency(self) -> int:
        """Calculate center frequency in Hz."""
        return (self.start_frequency + self.stop_frequency) // 2

    @property
    def span_frequency(self) -> int:
        """Calculate frequency span in Hz."""
        return self.stop_frequency - self.start_frequency

    def is_valid(self) -> bool:
        """Validate configuration parameters."""
        if self.start_frequency >= self.stop_frequency:
            return False
        if self.num_points <= 0:
            return False
        if self.num_sweeps <= 0:
            return False
        if not self.ifbw_values:
            return False
        if any(ifbw <= 0 for ifbw in self.ifbw_values):
            return False
        return True

    def to_dict(self) -> dict:
        """Convert to dictionary for backend consumption."""
        return {
            "start_frequency": self.start_frequency,
            "stop_frequency": self.stop_frequency,
            "num_points": self.num_points,
            "stim_lvl_dbm": self.stim_lvl_dbm,
            "avg_count": self.avg_count,
            "num_sweeps": self.num_sweeps,
            "ifbw_values": self.ifbw_values,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SweepConfig":
        """Create from dictionary (YAML config).

        Note: start_frequency, stop_frequency, and num_points are NOT
        read from YAML. They are always populated from the .cal file by
        calling update_from_cal_file() after instantiation. The zero
        placeholders ensure is_valid() returns False until the cal file
        has been applied, enforcing the architectural invariant that the
        calibration file is the single source of truth for sweep range
        and point count.
        """
        config = data.get("configurations", {})
        target = data.get("target", {})

        # Handle both single IFBW value and list
        ifbw_values = target.get("ifbw_values", [50000])
        if isinstance(ifbw_values, int):
            ifbw_values = [ifbw_values]

        return cls(
            start_frequency=0,  # Populated by update_from_cal_file()
            stop_frequency=0,   # Populated by update_from_cal_file()
            num_points=0,       # Populated by update_from_cal_file()
            stim_lvl_dbm=config.get("stim_lvl_dbm", -10),
            avg_count=config.get("avg_count", 1),
            num_sweeps=config.get("num_sweeps", 30),
            ifbw_values=ifbw_values,
        )

    def update_from_cal_file(self, cal_file_path: str) -> None:
        """Populate start_frequency, stop_frequency, num_points from a .cal file.

        The calibration file is the single source of truth for the sweep
        frequency range and point count.  This method parses the JSON .cal
        file and updates the corresponding fields in-place.

        Parameters
        ----------
        cal_file_path : str
            Absolute or relative path to the .cal file.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the file is malformed or missing required data.
        """
        from .vna_backend import BaseVNASweep

        cal_params = BaseVNASweep.parse_calibration_file(cal_file_path)
        self.start_frequency = cal_params["start_frequency"]
        self.stop_frequency = cal_params["stop_frequency"]
        self.num_points = cal_params["num_points"]


@dataclass
class SweepData:
    """Single sweep measurement data."""

    sweep_index: int
    ifbw_hz: int
    frequencies_hz: np.ndarray
    s11_db: np.ndarray
    timestamp: float = field(default_factory=lambda: 0.0)


class VNADataModel:
    """
    Central data model for VNA GUI application.

    Stores device state, calibration, configuration, and measurement data.
    Provides business logic for validation and data processing.
    """

    def __init__(self):
        self.device = DeviceInfo()
        self.calibration = CalibrationState()
        self.config = SweepConfig()

        # Storage for sweep measurements
        self.sweep_data: List[SweepData] = []
        self.sweep_times: List[float] = []

        # Current active sweep tracking
        self._current_ifbw: Optional[int] = None
        self._latest_freq: Optional[np.ndarray] = None
        self._latest_s11: Optional[np.ndarray] = None

    def is_ready_to_collect(self) -> bool:
        """
        Check if system is ready to start data collection.

        Returns:
            True if device connected AND calibration loaded AND config valid
        """
        return (
            self.device.connected and self.calibration.loaded and self.config.is_valid()
        )

    def add_sweep_data(
        self,
        sweep_index: int,
        ifbw_hz: int,
        frequencies_hz: np.ndarray,
        s11_db: np.ndarray,
        sweep_time: float = 0.0,
    ) -> None:
        """
        Add a completed sweep to the model.

        Args:
            sweep_index: Sequential sweep number (0-based)
            ifbw_hz: IF bandwidth used for this sweep
            frequencies_hz: Frequency array in Hz
            s11_db: S11 magnitude in dB
            sweep_time: Time taken for this sweep (seconds)
        """
        sweep = SweepData(
            sweep_index=sweep_index,
            ifbw_hz=ifbw_hz,
            frequencies_hz=frequencies_hz,
            s11_db=s11_db,
            timestamp=sweep_time,
        )
        self.sweep_data.append(sweep)

        if sweep_time > 0:
            self.sweep_times.append(sweep_time)

        # Update latest data cache
        self._current_ifbw = ifbw_hz
        self._latest_freq = frequencies_hz
        self._latest_s11 = s11_db

    def get_latest_sweep(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Get the most recent sweep data for real-time plotting.

        Returns:
            Tuple of (frequencies_hz, s11_db) or (None, None) if no data
        """
        return (self._latest_freq, self._latest_s11)

    def get_current_ifbw(self) -> Optional[int]:
        """Get the IFBW value currently being measured."""
        return self._current_ifbw

    def clear_sweep_data(self) -> None:
        """Clear all accumulated sweep data (for new collection run)."""
        self.sweep_data.clear()
        self.sweep_times.clear()
        self._current_ifbw = None
        self._latest_freq = None
        self._latest_s11 = None

    def get_sweep_statistics(self) -> dict:
        """
        Calculate statistics from accumulated sweep data.

        Returns:
            Dictionary with mean sweep time, std dev, min, max, rate
        """
        if not self.sweep_times:
            return {
                "mean_time": 0.0,
                "std_time": 0.0,
                "min_time": 0.0,
                "max_time": 0.0,
                "sweep_rate_hz": 0.0,
                "total_sweeps": 0,
            }

        times = np.array(self.sweep_times)
        return {
            "mean_time": float(np.mean(times)),
            "std_time": float(np.std(times)),
            "min_time": float(np.min(times)),
            "max_time": float(np.max(times)),
            "sweep_rate_hz": 1.0 / np.mean(times) if np.mean(times) > 0 else 0.0,
            "total_sweeps": len(self.sweep_times),
        }

    def convert_s11_complex_to_db(self, s11_complex: np.ndarray) -> np.ndarray:
        """
        Convert complex S11 to magnitude in dB.

        Args:
            s11_complex: Complex S11 values

        Returns:
            S11 magnitude in dB (20*log10(|S11|))
        """
        magnitude = np.abs(s11_complex)
        # Avoid log(0) by clamping to small value
        magnitude = np.maximum(magnitude, 1e-10)
        return 20 * np.log10(magnitude)

    def get_sweeps_by_ifbw(self, ifbw_hz: int) -> List[SweepData]:
        """
        Retrieve all sweeps for a specific IFBW value.

        Args:
            ifbw_hz: IF bandwidth to filter by

        Returns:
            List of SweepData objects matching the IFBW
        """
        return [sweep for sweep in self.sweep_data if sweep.ifbw_hz == ifbw_hz]

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"VNADataModel(\n"
            f"  device_connected={self.device.connected},\n"
            f"  cal_loaded={self.calibration.loaded},\n"
            f"  config_valid={self.config.is_valid()},\n"
            f"  total_sweeps={len(self.sweep_data)},\n"
            f"  ready={self.is_ready_to_collect()}\n"
            f")"
        )
