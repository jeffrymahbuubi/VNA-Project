"""
Backend adapter for GUI integration with script 6 (BaseVNASweep).

This module wraps the monolithic run() method from ContinuousModeSweep into
discrete lifecycle steps suitable for GUI threading:
  - start_lifecycle() → start GUI, connect, load calibration
  - run_single_ifbw_sweep() → configure + run sweeps for ONE IFBW value
  - save_results() → write xlsx workbook
  - stop_lifecycle() → terminate GUI subprocess

Threading contract: All methods except callbacks are called from QThread worker.
Callbacks are passed by caller and should emit Qt signals for thread-safe GUI updates.
"""

import sys
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional
import numpy as np

# Add scripts directory to path for importing backend
SCRIPT_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from importlib import import_module

# Dynamically import script 6 to avoid naming conflicts (starts with digit)
script6_module = import_module("6_librevna_gui_mode_sweep_test")
ContinuousModeSweep = script6_module.ContinuousModeSweep
SweepResult = script6_module.SweepResult


class GUIVNASweepAdapter:
    """
    Adapter that breaks ContinuousModeSweep into discrete GUI-friendly steps.

    Usage pattern (from QThread worker):
        adapter = GUIVNASweepAdapter(config_dict, cal_file_path)
        adapter.start_lifecycle()

        for ifbw in ifbw_values:
            def callback(sweep_idx, freq_hz, s11_db):
                # Emit Qt signal here for GUI update
                pass

            result = adapter.run_single_ifbw_sweep(ifbw, callback)

        xlsx_path = adapter.save_results(all_results)
        adapter.stop_lifecycle()
    """

    def __init__(self, config_dict: dict, calibration_file_path: str):
        """
        Initialize adapter with configuration.

        Args:
            config_dict: Sweep configuration matching SweepConfig.to_dict() format
            calibration_file_path: Absolute path to .cal file
        """
        self.config = config_dict
        self.cal_file_path = calibration_file_path

        # Create temporary YAML config file for BaseVNASweep
        self.temp_config_path = self._create_temp_config()

        # Initialize sweep instance (continuous mode only)
        self.sweep = ContinuousModeSweep(
            config_path=self.temp_config_path,
            mode="continuous",
            summary=False,  # No console output in GUI
            save_data=False  # We'll handle saving separately
        )

        # Lifecycle state
        self.gui_process = None
        self.vna = None
        self.all_results: List[SweepResult] = []

    def _create_temp_config(self) -> str:
        """
        Create a temporary sweep_config.yaml for BaseVNASweep consumption.

        Returns:
            Absolute path to temporary config file
        """
        import tempfile
        import yaml

        # Convert config_dict to YAML structure expected by script 6
        yaml_config = {
            'configurations': {
                'start_frequency': self.config['start_frequency'],
                'stop_frequency': self.config['stop_frequency'],
                'num_points': self.config['num_points'],
                'stim_lvl_dbm': self.config['stim_lvl_dbm'],
                'avg_count': self.config['avg_count'],
                'num_sweeps': self.config['num_sweeps'],
            },
            'target': {
                'ifbw_values': self.config['ifbw_values']
            }
        }

        # Write to temp file
        fd, path = tempfile.mkstemp(suffix='.yaml', prefix='gui_sweep_')
        with os.fdopen(fd, 'w') as f:
            yaml.dump(yaml_config, f)

        return path

    def start_lifecycle(self) -> Dict[str, str]:
        """
        Start GUI subprocess, connect to SCPI, load calibration.

        Returns:
            Dictionary with device info: {'serial': ..., 'idn': ...}

        Raises:
            RuntimeError: If GUI start, connection, or calibration fails
        """
        # Step 1: Start GUI subprocess
        self.gui_process = self.sweep.start_gui()

        # Step 2: Connect to SCPI server and verify device
        self.vna = self.sweep.connect_and_verify()

        # Extract device info for GUI display
        idn_raw = self.vna.query("*IDN?")
        parts = [p.strip() for p in idn_raw.split(",")]
        serial = parts[2] if len(parts) > 2 else "Unknown"

        # Step 3: Load calibration file
        success = self.sweep.load_calibration(self.vna, self.cal_file_path)
        if not success:
            raise RuntimeError(f"Failed to load calibration: {self.cal_file_path}")

        # Step 4: Enable streaming server (required for continuous mode)
        self.sweep.enable_streaming_server(self.vna)

        return {
            'serial': serial,
            'idn': idn_raw,
        }

    def run_single_ifbw_sweep(
        self,
        ifbw_hz: int,
        callback: Optional[Callable[[int, np.ndarray, np.ndarray], None]] = None
    ) -> SweepResult:
        """
        Configure and run sweeps for a single IFBW value.

        Args:
            ifbw_hz: IF bandwidth in Hz
            callback: Called after each sweep with (sweep_idx, freq_hz, s11_db)
                      This should emit Qt signals for thread-safe GUI updates

        Returns:
            SweepResult object with timing metrics and trace data
        """
        # Configure SCPI parameters for this IFBW
        self.sweep.configure_sweep(self.vna, ifbw_hz)

        # Inject callback wrapper into sweep instance
        if callback:
            self._install_callback_hook(callback)

        # Run the sweep loop (blocking until all sweeps complete)
        result = self.sweep.run_sweeps(self.vna, ifbw_hz)

        # Store result for later xlsx export
        self.all_results.append(result)

        return result

    def _install_callback_hook(self, callback: Callable):
        """
        Monkey-patch the sweep instance to call our callback.

        This intercepts the internal streaming callback to inject GUI updates.
        """
        original_make_callback = self.sweep._make_callback

        def wrapped_make_callback(state_holder):
            # Get the original streaming callback
            original_callback = original_make_callback(state_holder)

            # Wrap it to extract data for GUI
            def gui_callback(datapoint):
                # Call original callback first (accumulates data)
                original_callback(datapoint)

                # After sweep completes, extract data for GUI
                state = state_holder[0]
                if state and datapoint['pointNum'] == state.num_points - 1:
                    # Last point of sweep → full sweep ready
                    with state.lock:
                        if state.all_s11_complex:
                            sweep_idx = len(state.all_s11_complex) - 1
                            s11_complex = state.all_s11_complex[-1]

                            # Convert to dB
                            s11_db = 20 * np.log10(np.abs(s11_complex))

                            # Build frequency array
                            freq_hz = np.linspace(
                                self.sweep.start_freq_hz,
                                self.sweep.stop_freq_hz,
                                self.sweep.num_points
                            )

                            # Call user callback (should emit Qt signal)
                            callback(sweep_idx, freq_hz, s11_db)

            return gui_callback

        # Install monkey patch
        self.sweep._make_callback = wrapped_make_callback

    def save_results(self, custom_filename: Optional[str] = None) -> str:
        """
        Export all accumulated results to multi-sheet xlsx workbook.

        Args:
            custom_filename: Optional custom filename (without extension)

        Returns:
            Absolute path to saved xlsx file
        """
        if not self.all_results:
            raise ValueError("No sweep results to save")

        # Temporarily restore save_data flag
        original_save_data = self.sweep.save_data
        self.sweep.save_data = True

        # Override filename if provided
        if custom_filename:
            import datetime
            today = datetime.datetime.now().strftime("%Y%m%d")
            out_dir = Path(SCRIPT_DIR).parent / "data" / today
            out_dir.mkdir(parents=True, exist_ok=True)
            xlsx_path = out_dir / f"{custom_filename}.xlsx"

            # Temporarily patch the save_xlsx method to use custom path
            original_save = self.sweep.save_xlsx

            def custom_save(results):
                path = original_save(results)
                # Move to custom location
                import shutil
                shutil.move(path, xlsx_path)
                return str(xlsx_path)

            self.sweep.save_xlsx = custom_save

        # Call save method
        xlsx_path = self.sweep.save_xlsx(self.all_results)

        # Restore original state
        self.sweep.save_data = original_save_data

        return xlsx_path

    def stop_lifecycle(self):
        """
        Terminate GUI subprocess gracefully.
        """
        if self.gui_process:
            self.sweep.stop_gui(self.gui_process)

        # Clean up temp config file
        if hasattr(self, 'temp_config_path') and os.path.exists(self.temp_config_path):
            os.unlink(self.temp_config_path)

    def get_device_serial(self) -> str:
        """Query device serial number (DEV:CONN?)."""
        if not self.vna:
            return "Not connected"

        try:
            serial = self.vna.query(":DEV:CONN?")
            return serial.strip()
        except Exception:
            return "Query failed"
