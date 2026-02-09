"""
View layer for LibreVNA GUI (MVP architecture).

PySide6-based UI - uses compiled Ui_MainWindow class and provides display-only
methods. NO business logic - all state changes are handled by Presenter.

Uses the auto-generated main_window.py (from pyside6-uic) via multiple
inheritance so that all widget attributes are directly accessible as self.xxx.
"""

from PySide6.QtWidgets import QMainWindow, QMessageBox
from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QIcon
import pyqtgraph as pg
import numpy as np
from pathlib import Path
from typing import Optional

from .main_window import Ui_MainWindow


class VNAMainWindow(QMainWindow, Ui_MainWindow):
    """
    Main window for LibreVNA real-time plotter.

    Inherits from both QMainWindow and the auto-generated Ui_MainWindow class.
    Replaces the s11TracePlot QLabel placeholder with a pyqtgraph PlotWidget.
    Emits signals for user actions, provides display methods for Presenter.
    """

    # Signals for user actions (emitted TO presenter)
    collect_data_requested = Signal()
    load_calibration_requested = Signal()
    load_config_requested = Signal()
    config_changed = Signal()  # Emitted when user edits any config widget

    def __init__(self):
        """
        Initialize main window using compiled Ui_MainWindow class.

        The multiple inheritance pattern calls setupUi(self) which sets
        all widget attributes directly on this instance, so they are
        accessible as self.pushButton, self.startFrequencyLineEdit, etc.
        """
        super().__init__()

        # Set up the auto-generated UI (sets all widget attributes on self)
        self.setupUi(self)

        # Set window title and icon
        self.setWindowTitle("LibreVNA Real-Time Plotter")
        icon_path = Path(__file__).parent.parent / "resources" / "WTMH.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Replace plot placeholder with pyqtgraph widget
        self._setup_plot_widget()

        # Button blink animation timer
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self._toggle_button_blink)
        self._blink_state = False

        # Connect widget signals to user action signals
        self._connect_widget_signals()

        # Initialize button state
        self.set_collect_button_enabled(False)

    def _setup_plot_widget(self):
        """
        Replace s11TracePlot QLabel placeholder with pyqtgraph PlotWidget.

        The .ui file has a QLabel named 's11TracePlot' inside the 'tracesBox'
        QGroupBox with a verticalLayout_2. We remove it and insert a
        pyqtgraph PlotWidget in its place.
        """
        # Find the parent layout (verticalLayout_2 inside tracesBox)
        placeholder = self.s11TracePlot  # QLabel from compiled UI
        parent_layout = self.verticalLayout_2  # QVBoxLayout inside tracesBox

        # Remove and delete placeholder
        parent_layout.removeWidget(placeholder)
        placeholder.deleteLater()

        # Create pyqtgraph PlotWidget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setObjectName("s11TracePlot")  # Preserve name
        self.plot_widget.setLabel('left', 'S11 Magnitude', units='dB')
        self.plot_widget.setLabel('bottom', 'Frequency', units='Hz')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setYRange(-60, 0)  # Fixed range during collection

        # Create plot data item (yellow pen for S11 trace)
        self.plot_data_item = self.plot_widget.plot(
            [], [],
            pen=pg.mkPen(color='y', width=2),
            name='S11'
        )

        # Add to layout
        parent_layout.addWidget(self.plot_widget)

    def _connect_widget_signals(self):
        """
        Connect UI widget signals to custom signals.

        Widget names come from the .ui file (compiled into main_window.py):
          Sweep box:       startFrequencyLineEdit, centerFrequencyLineEdit,
                           stopFrequencyLineEdit, spanFrequencyLineEdit,
                           numberOfSweepLineEdit
          Acquisitions box: levelLineEdit, pointsLineEdit, ifbwFrequencyLineEdit
          Actions:         actionLoad (.cal), actionLoad_yaml_config,
                           actionSerial_LibreVNA_USB
          Button:          pushButton (Collect Data)
        """
        # Collect data button
        self.pushButton.clicked.connect(self.collect_data_requested.emit)

        # Menu actions (these exist in the .ui file)
        self.actionLoad.triggered.connect(
            self.load_calibration_requested.emit
        )
        self.actionLoad_yaml_config.triggered.connect(
            self.load_config_requested.emit
        )

        # Config widget changes (for validation feedback)
        config_widgets = [
            self.startFrequencyLineEdit,
            self.centerFrequencyLineEdit,
            self.stopFrequencyLineEdit,
            self.spanFrequencyLineEdit,
            self.numberOfSweepLineEdit,
            self.levelLineEdit,
            self.pointsLineEdit,
            self.ifbwFrequencyLineEdit,
        ]

        for widget in config_widgets:
            widget.textChanged.connect(lambda _text: self.config_changed.emit())

    # -----------------------------------------------------------------------
    # Display methods (called by Presenter)
    # -----------------------------------------------------------------------

    def set_collect_button_enabled(self, enabled: bool):
        """
        Enable or disable the collect data button.

        Args:
            enabled: True to enable, False to disable (gray out)
        """
        self.pushButton.setEnabled(enabled)

        if not enabled:
            self.pushButton.setText("Not Ready")
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(156, 163, 175); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(156, 163, 175); }"
            )

    def set_collecting_state(self, collecting: bool):
        """
        Toggle button appearance between ready and collecting states.

        Args:
            collecting: True = red blinking "Collecting Data..."
                       False = green "Collect Data"
        """
        if collecting:
            self.pushButton.setText("Collecting Data...")
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(239, 68, 68); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(239, 68, 68); }"
            )
            self.pushButton.setEnabled(False)
            self.blink_timer.start(500)  # Blink every 500ms
        else:
            self.pushButton.setText("Collect Data")
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(74, 222, 128); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(74, 222, 128); }\n"
                "QPushButton:hover { border-color: #38bdf8; }"
            )
            self.pushButton.setEnabled(True)
            self.blink_timer.stop()
            self.pushButton.setVisible(True)  # Ensure visible after blink

    def _toggle_button_blink(self):
        """Internal: Toggle button visibility for blink animation."""
        self._blink_state = not self._blink_state
        self.pushButton.setVisible(self._blink_state)

    def update_plot(self, freq_hz: np.ndarray, s11_db: np.ndarray):
        """
        Update plot with new sweep data (overwrites previous trace).

        Args:
            freq_hz: Frequency array in Hz
            s11_db: S11 magnitude in dB
        """
        self.plot_data_item.setData(freq_hz, s11_db)

    def clear_plot(self):
        """Clear plot data (empty trace)."""
        self.plot_data_item.setData([], [])

    def populate_sweep_config(self, config: dict):
        """
        Populate configuration widgets from config dictionary.

        Maps model fields to the actual widget names from the .ui file:
          start_frequency  -> startFrequencyLineEdit
          stop_frequency   -> stopFrequencyLineEdit
          num_points       -> pointsLineEdit
          stim_lvl_dbm     -> levelLineEdit
          num_sweeps       -> numberOfSweepLineEdit
          ifbw_values      -> ifbwFrequencyLineEdit (comma-separated)

        Also computes and displays center and span frequencies.

        Args:
            config: Dictionary with keys matching SweepConfig fields
        """
        # Frequency settings
        if 'start_frequency' in config:
            self.startFrequencyLineEdit.setText(str(config['start_frequency']))

        if 'stop_frequency' in config:
            self.stopFrequencyLineEdit.setText(str(config['stop_frequency']))

        # Compute and populate center and span
        start = config.get('start_frequency', 0)
        stop = config.get('stop_frequency', 0)
        if start and stop:
            center = (start + stop) // 2
            span = stop - start
            self.centerFrequencyLineEdit.setText(str(center))
            self.spanFrequencyLineEdit.setText(str(span))

        # Acquisition settings
        if 'num_points' in config:
            self.pointsLineEdit.setText(str(config['num_points']))

        if 'stim_lvl_dbm' in config:
            self.levelLineEdit.setText(str(config['stim_lvl_dbm']))

        if 'num_sweeps' in config:
            self.numberOfSweepLineEdit.setText(str(config['num_sweeps']))

        # IFBW values (list -> comma-separated string)
        if 'ifbw_values' in config:
            ifbw_str = ', '.join(str(v) for v in config['ifbw_values'])
            self.ifbwFrequencyLineEdit.setText(ifbw_str)

    def read_sweep_config(self) -> dict:
        """
        Read configuration values from widgets.

        Returns:
            Dictionary with config values (strings converted to appropriate types).
            Uses default of 1 for avg_count since there is no widget for it.
        """
        # Parse IFBW values (comma-separated string -> list of ints)
        ifbw_text = self.ifbwFrequencyLineEdit.text().strip()
        ifbw_values = []
        if ifbw_text:
            try:
                ifbw_values = [int(v.strip()) for v in ifbw_text.split(',')]
            except ValueError:
                ifbw_values = []

        try:
            start_freq = int(self.startFrequencyLineEdit.text() or 0)
        except ValueError:
            start_freq = 0

        try:
            stop_freq = int(self.stopFrequencyLineEdit.text() or 0)
        except ValueError:
            stop_freq = 0

        try:
            num_points = int(self.pointsLineEdit.text() or 0)
        except ValueError:
            num_points = 0

        try:
            stim_lvl = int(self.levelLineEdit.text() or 0)
        except ValueError:
            stim_lvl = -10

        try:
            num_sweeps = int(self.numberOfSweepLineEdit.text() or 0)
        except ValueError:
            num_sweeps = 0

        return {
            'start_frequency': start_freq,
            'stop_frequency': stop_freq,
            'num_points': num_points,
            'stim_lvl_dbm': stim_lvl,
            'avg_count': 1,  # No widget in UI, use default
            'num_sweeps': num_sweeps,
            'ifbw_values': ifbw_values,
        }

    def set_device_serial(self, serial: str):
        """
        Update device serial display in the Device > Connect to menu.

        Args:
            serial: Device serial number string
        """
        self.actionSerial_LibreVNA_USB.setText(f"Serial: {serial}")

    def set_calibration_status(self, loaded: bool, file_name: str = ""):
        """
        Update calibration status display in status bar.

        Args:
            loaded: True if calibration loaded successfully
            file_name: Name of loaded calibration file
        """
        if loaded:
            status = f"Cal: {file_name}" if file_name else "Cal: Loaded"
            self.statusbar.showMessage(status, 0)
        else:
            self.statusbar.showMessage("Cal: Not loaded", 0)

    def show_status_message(self, message: str, timeout: int = 5000):
        """
        Display message in status bar.

        Args:
            message: Message text
            timeout: Display duration in milliseconds (0 = permanent)
        """
        self.statusbar.showMessage(message, timeout)

    def show_error_dialog(self, title: str, message: str):
        """
        Display error dialog to user.

        Args:
            title: Dialog title
            message: Error message
        """
        QMessageBox.critical(self, title, message)

    def show_info_dialog(self, title: str, message: str):
        """
        Display info dialog to user.

        Args:
            title: Dialog title
            message: Info message
        """
        QMessageBox.information(self, title, message)

    def show_success_dialog(self, title: str, message: str):
        """
        Display success dialog to user.

        Args:
            title: Dialog title
            message: Success message
        """
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()

    def update_progress_label(self, text: str):
        """
        Update progress display via status bar.

        Args:
            text: Progress text (e.g., "IFBW 150 kHz - Sweep 5/30")
        """
        self.statusbar.showMessage(text, 0)
