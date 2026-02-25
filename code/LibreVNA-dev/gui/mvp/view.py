"""
View layer for LibreVNA GUI (MVP architecture).

PySide6-based UI - uses compiled Ui_MainWindow class and provides display-only
methods. NO business logic - all state changes are handled by Presenter.

Uses the auto-generated main_window.py (from pyside6-uic) via multiple
inheritance so that all widget attributes are directly accessible as self.xxx.
"""

import math

from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QMenu,
)
from PySide6.QtCore import Signal, QTimer
from PySide6.QtGui import QIcon, QCloseEvent
import pyqtgraph as pg
import numpy as np
from pathlib import Path
from typing import Optional

from .main_window import Ui_MainWindow


class _MHzAxisItem(pg.AxisItem):
    """X-axis: formats Hz values as '200MHz', '210MHz', etc.

    Disables the painter clip during paint() so that tick labels at the
    axis edges (e.g. '200MHz' at left, '250MHz' at right) are not
    scissored by the item boundary when viewport X-padding is zero.
    """

    def tickStrings(self, values, scale, spacing):
        return [f"{v / 1e6:.0f}MHz" for v in values]

    def paint(self, p, opt, widget):
        p.save()
        p.setClipping(False)
        super().paint(p, opt, widget)
        p.restore()


class _dBAxisItem(pg.AxisItem):
    """Y-axis: formats dB values as '20dB', '-10dB', etc."""

    def tickStrings(self, values, scale, spacing):
        return [f"{v:.0f}dB" for v in values]


def _nice_step(max_val: float, min_val: float, target_divisions: int = 7) -> float:
    """Return a 'nice' round tick step for the given range.

    Selects from preferred multipliers (1, 2, 5, 10) at the appropriate
    order of magnitude so that the number of divisions stays close to
    *target_divisions*.
    """
    span = abs(max_val - min_val)
    if span == 0:
        return 1.0
    raw_step = span / target_divisions
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for multiplier in (1, 2, 5, 10):
        step = magnitude * multiplier
        if span / step <= target_divisions * 1.5:
            return step
    return magnitude * 10


def _frange(start: float, stop: float, step: float):
    """Generate float range from *start* to *stop* (inclusive) with *step*.

    Works for both positive and negative step values.
    """
    values = []
    v = start
    if step < 0:
        while v >= stop - 1e-9:
            values.append(round(v, 10))
            v += step
    else:
        while v <= stop + 1e-9:
            values.append(round(v, 10))
            v += step
    return values


class _VNAPlotWidget(pg.PlotWidget):
    """PlotWidget subclass that replaces pyqtgraph's built-in right-click
    menu with a single "Axis Setup" action.

    The ``_on_axis_setup`` callback is assigned after construction by
    ``VNAMainWindow._setup_plot_widget``.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Disable pyqtgraph's default context menu
        self.getViewBox().setMenuEnabled(False)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("Axis Setup", self._on_axis_setup)
        menu.exec(event.globalPos())

    def _on_axis_setup(self):
        """Placeholder -- monkey-patched by VNAMainWindow after creation."""
        pass


# ---------------------------------------------------------------------------
# AxisSetupDialog
# ---------------------------------------------------------------------------


class AxisSetupDialog(QDialog):
    """Modal dialog for configuring Y-axis and X-axis range and tick divisions.

    Layout mirrors the official LibreVNA-GUI "Axis Setup" dialog but omits
    the secondary Y-axis column (not needed for single-trace S11 plotting).
    """

    def __init__(
        self,
        y_max: float,
        y_min: float,
        y_divisions: int,
        y_auto_div: bool,
        x_max_hz: float,
        x_min_hz: float,
        x_divisions: int,
        x_auto_div: bool,
        x_auto_range: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Axis Setup")
        self.setMinimumWidth(550)

        # --- Primary Y Axis group box ---
        y_group = QGroupBox("Primary Y Axis")
        y_layout = QGridLayout()

        y_layout.addWidget(QLabel("Type:"), 0, 0)
        y_layout.addWidget(QLabel("Magnitude"), 0, 1)

        y_layout.addWidget(QLabel("Range:"), 1, 0)

        y_layout.addWidget(QLabel("Maximum:"), 2, 0)
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-200.0, 200.0)
        self.y_max_spin.setDecimals(1)
        self.y_max_spin.setSuffix(" dB")
        self.y_max_spin.setValue(y_max)
        y_layout.addWidget(self.y_max_spin, 2, 1)

        y_layout.addWidget(QLabel("Minimum:"), 3, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-200.0, 200.0)
        self.y_min_spin.setDecimals(1)
        self.y_min_spin.setSuffix(" dB")
        self.y_min_spin.setValue(y_min)
        y_layout.addWidget(self.y_min_spin, 3, 1)

        y_div_row = QHBoxLayout()
        y_layout.addWidget(QLabel("# Divisions:"), 4, 0)
        self.y_div_spin = QSpinBox()
        self.y_div_spin.setRange(1, 100)
        self.y_div_spin.setValue(y_divisions)
        y_div_row.addWidget(self.y_div_spin)
        self.y_auto_div_cb = QCheckBox("Auto")
        self.y_auto_div_cb.setChecked(y_auto_div)
        y_div_row.addWidget(self.y_auto_div_cb)
        y_layout.addLayout(y_div_row, 4, 1)

        # Wire auto-div checkbox to disable/enable the spinbox
        self.y_auto_div_cb.toggled.connect(
            lambda checked: self.y_div_spin.setEnabled(not checked)
        )
        self.y_div_spin.setEnabled(not y_auto_div)

        y_group.setLayout(y_layout)

        # --- X Axis group box ---
        x_group = QGroupBox("X Axis")
        x_layout = QGridLayout()

        x_layout.addWidget(QLabel("Type:"), 0, 0)
        x_layout.addWidget(QLabel("Frequency"), 0, 1)

        # Range row with Auto checkbox and "Use Span" label
        x_range_row = QHBoxLayout()
        x_layout.addWidget(QLabel("Range:"), 1, 0)
        self.x_auto_range_cb = QCheckBox("Auto")
        self.x_auto_range_cb.setChecked(x_auto_range)
        x_range_row.addWidget(self.x_auto_range_cb)
        self._use_span_label = QLabel("Use Span")
        self._use_span_label.setEnabled(False)  # Always greyed, informational
        x_range_row.addWidget(self._use_span_label)
        x_range_row.addStretch()
        x_layout.addLayout(x_range_row, 1, 1)

        x_layout.addWidget(QLabel("Maximum:"), 2, 0)
        self.x_max_spin = QDoubleSpinBox()
        self.x_max_spin.setRange(0.0, 100000.0)
        self.x_max_spin.setDecimals(3)
        self.x_max_spin.setSuffix(" MHz")
        self.x_max_spin.setValue(x_max_hz / 1e6)
        x_layout.addWidget(self.x_max_spin, 2, 1)

        x_layout.addWidget(QLabel("Minimum:"), 3, 0)
        self.x_min_spin = QDoubleSpinBox()
        self.x_min_spin.setRange(0.0, 100000.0)
        self.x_min_spin.setDecimals(3)
        self.x_min_spin.setSuffix(" MHz")
        self.x_min_spin.setValue(x_min_hz / 1e6)
        x_layout.addWidget(self.x_min_spin, 3, 1)

        x_div_row = QHBoxLayout()
        x_layout.addWidget(QLabel("# Divisions:"), 4, 0)
        self.x_div_spin = QSpinBox()
        self.x_div_spin.setRange(1, 100)
        self.x_div_spin.setValue(x_divisions)
        x_div_row.addWidget(self.x_div_spin)
        self.x_auto_div_cb = QCheckBox("Auto")
        self.x_auto_div_cb.setChecked(x_auto_div)
        x_div_row.addWidget(self.x_auto_div_cb)
        x_layout.addLayout(x_div_row, 4, 1)

        # Wire X auto-div checkbox
        self.x_auto_div_cb.toggled.connect(
            lambda checked: self.x_div_spin.setEnabled(not checked)
        )
        self.x_div_spin.setEnabled(not x_auto_div)

        # Wire X auto-range checkbox to disable/enable Max/Min spinboxes
        def _toggle_x_range(checked):
            self.x_max_spin.setEnabled(not checked)
            self.x_min_spin.setEnabled(not checked)

        self.x_auto_range_cb.toggled.connect(_toggle_x_range)
        _toggle_x_range(x_auto_range)

        x_group.setLayout(x_layout)

        # --- Button box (OK / Cancel) ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # --- Top-level layout ---
        columns = QHBoxLayout()
        columns.addWidget(y_group)
        columns.addWidget(x_group)

        main_layout = QVBoxLayout()
        main_layout.addLayout(columns)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

    def get_values(self) -> dict:
        """Return the current dialog values as a dict.

        X-axis values are converted from MHz (display) back to Hz (internal).
        """
        return {
            "y_max": self.y_max_spin.value(),
            "y_min": self.y_min_spin.value(),
            "y_divisions": self.y_div_spin.value(),
            "y_auto_div": self.y_auto_div_cb.isChecked(),
            "x_max_hz": self.x_max_spin.value() * 1e6,
            "x_min_hz": self.x_min_spin.value() * 1e6,
            "x_divisions": self.x_div_spin.value(),
            "x_auto_div": self.x_auto_div_cb.isChecked(),
            "x_auto_range": self.x_auto_range_cb.isChecked(),
        }


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
    connect_device_requested = (
        Signal()
    )  # Emitted when user clicks Device > Connect to > serial action
    config_changed = Signal()  # Emitted when user edits any config widget
    mode_changed = Signal(str)  # Emits "sanity_check" or "continuous_monitoring"
    window_closing = (
        Signal()
    )  # Emitted when user closes the window (X button, Alt+F4, etc.)

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

        # Initialize mode configuration widgets
        self._setup_mode_widgets()

        # Connect widget signals to user action signals
        self._connect_widget_signals()

        # Initialize button state
        self.set_collect_button_enabled(False)

    def _setup_plot_widget(self):
        """
        Replace s11TracePlot QLabel placeholder with pyqtgraph PlotWidget.

        The .ui file has a QLabel named 's11TracePlot' inside the 'tracesBox'
        QGroupBox with a verticalLayout_2. We remove it and insert a
        _VNAPlotWidget (custom subclass) in its place.  The subclass replaces
        pyqtgraph's built-in right-click menu with a single "Axis Setup"
        action that opens the AxisSetupDialog.
        """
        # Find the parent layout (verticalLayout_2 inside tracesBox)
        placeholder = self.s11TracePlot  # QLabel from compiled UI
        parent_layout = self.verticalLayout_2  # QVBoxLayout inside tracesBox

        # Remove and delete placeholder
        parent_layout.removeWidget(placeholder)
        placeholder.deleteLater()

        # Create custom PlotWidget with right-click "Axis Setup" menu.
        self.plot_widget = _VNAPlotWidget(
            axisItems={
                "bottom": _MHzAxisItem(orientation="bottom"),
                "left": _dBAxisItem(orientation="left"),
            }
        )
        self.plot_widget.setObjectName("s11TracePlot")  # Preserve name
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # Wire the right-click callback to our dialog opener
        self.plot_widget._on_axis_setup = self._open_axis_setup_dialog

        # Disable auto-range on Y so _apply_axis_settings() controls it
        view_box = self.plot_widget.getViewBox()
        view_box.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        view_box.setDefaultPadding(0.0)

        # Create plot data item (yellow pen for S11 trace)
        self.plot_data_item = self.plot_widget.plot(
            [], [], pen=pg.mkPen(color="y", width=2), name="S11"
        )

        # Add to layout
        parent_layout.addWidget(self.plot_widget)

        # Initialise default axis state and apply to the plot
        self._axis_state = {
            "y_max": 20.0,
            "y_min": -50.0,
            "y_divisions": 7,
            "y_auto_div": True,
            "x_max_hz": 250_000_000.0,
            "x_min_hz": 200_000_000.0,
            "x_divisions": 10,
            "x_auto_div": True,
            "x_auto_range": True,
        }
        self._apply_axis_settings()

    def _setup_mode_widgets(self):
        """
        Initialize mode configuration widgets with default values.

        Sets Continuous Monitoring as the default mode, populates the
        monitor duration combo box, and enables the monitor-specific
        controls (since continuous monitoring is the default).
        """
        # Set Continuous Monitoring as the default
        self.continuousMonitoring.setChecked(True)

        # Populate monitor duration combo box
        self.monitorDurationcomboBox.clear()
        for item in ("10", "30", "60", "Indefinitely"):
            self.monitorDurationcomboBox.addItem(item)
        # Default to "Indefinitely" (index 3)
        self.monitorDurationcomboBox.setCurrentIndex(3)

        # Set default placeholder text for log interval
        self.logIntervallineEdit.setPlaceholderText("auto")

        # Monitor controls enabled by default (continuous monitoring is selected)
        self.set_monitor_controls_enabled(True)

    def _connect_widget_signals(self):
        """
        Connect UI widget signals to custom signals.

        Widget names come from the .ui file (compiled into main_window.py):
          Sweep box:       startFrequencyLineEdit, centerFrequencyLineEdit,
                           stopFrequencyLineEdit, spanFrequencyLineEdit,
                           numberOfSweepLineEdit
          Acquisitions box: levelLineEdit, pointsLineEdit, ifbwFrequencyLineEdit
          Mode box:        deviceSanityCheck, continuousMonitoring,
                           monitorDurationcomboBox, logIntervallineEdit
          Actions:         actionLoad (.cal), actionLoad_yaml_config,
                           actionSerial_LibreVNA_USB (device connect)
          Button:          pushButton (Collect Data)
        """
        # Collect data button
        self.pushButton.clicked.connect(self.collect_data_requested.emit)

        # Menu actions (these exist in the .ui file)
        self.actionLoad.triggered.connect(self.load_calibration_requested.emit)
        self.actionLoad_yaml_config.triggered.connect(self.load_config_requested.emit)
        self.actionSerial_LibreVNA_USB.triggered.connect(
            self.connect_device_requested.emit
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

        # Mode configuration widgets
        self.deviceSanityCheck.toggled.connect(self._on_mode_toggled)
        self.continuousMonitoring.toggled.connect(self._on_mode_toggled)
        self.monitorDurationcomboBox.currentIndexChanged.connect(
            lambda _idx: self.config_changed.emit()
        )
        self.logIntervallineEdit.textChanged.connect(
            lambda _text: self.config_changed.emit()
        )

    # -----------------------------------------------------------------------
    # Mode configuration helpers
    # -----------------------------------------------------------------------

    def _on_mode_toggled(self, checked: bool):
        """
        Handle radio button toggle for mode selection.

        Only emits when a button becomes checked (ignores the unchecked
        event from the other radio button) to avoid double-firing.

        Args:
            checked: True if the sender radio button is now checked
        """
        if not checked:
            return  # Ignore the unchecked signal from the other button

        mode = self.get_selected_mode()
        self.set_monitor_controls_enabled(mode == "continuous_monitoring")
        self.mode_changed.emit(mode)
        self.config_changed.emit()

    def set_monitor_controls_enabled(self, enabled: bool):
        """
        Enable or disable monitor-specific controls.

        When Device Sanity Check is selected, the monitor duration combo box
        and log interval line edit are grayed out. When Continuous Monitoring
        is selected, they are re-enabled.

        Args:
            enabled: True to enable monitor controls, False to disable
        """
        self.monitorDurationcomboBox.setEnabled(enabled)
        self.logIntervallineEdit.setEnabled(enabled)
        self.monitorDurationsLabel.setEnabled(enabled)
        self.logIntervalLabel.setEnabled(enabled)

    def get_selected_mode(self) -> str:
        """
        Return the currently selected mode as a string.

        Returns:
            "sanity_check" if Device Sanity Check radio is checked,
            "continuous_monitoring" if Continuous Monitoring radio is checked.
        """
        if self.deviceSanityCheck.isChecked():
            return "sanity_check"
        return "continuous_monitoring"

    def set_log_interval_value(self, value_ms: float):
        """
        Set the log interval line edit to the given value in milliseconds.

        Called by the Presenter after warmup completes to auto-populate
        the effective log interval (mean sweep time in ms).

        Args:
            value_ms: Log interval in milliseconds (displayed as integer)
        """
        self.logIntervallineEdit.setText(str(int(round(value_ms))))

    def get_monitor_duration_s(self) -> float:
        """
        Read the monitor duration from the combo box.

        Returns:
            Duration in seconds. 0.0 means "Indefinitely".
        """
        text = self.monitorDurationcomboBox.currentText()
        if text == "Indefinitely":
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    def get_log_interval_ms(self) -> str:
        """
        Read the log interval from the line edit.

        Returns:
            "auto" if the field is empty, contains "auto", or is invalid.
            Otherwise, the numeric string value in milliseconds.
        """
        text = self.logIntervallineEdit.text().strip()
        if not text or text.lower() == "auto":
            return "auto"
        return text

    def set_monitoring_state(self, monitoring: bool):
        """
        Toggle button appearance between ready and monitoring states.

        Args:
            monitoring: True = orange pulsing "Monitoring..." (button stays
                        enabled so user can click to stop)
                        False = green "Collect Data" (enabled, ready)
        """
        if monitoring:
            self.pushButton.setText("Stop\nMonitoring")
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(251, 146, 60); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(251, 146, 60); "
                "color: white; }\n"
                "QPushButton:hover { border-color: #ef4444; }"
            )
            self.pushButton.setEnabled(True)
            self._blink_state = False
            self.blink_timer.start(800)  # Pulse every 800ms
        else:
            self.set_collecting_state(False)

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
            collecting: True = red pulsing "Collecting Data..." (disabled)
                       False = green "Collect Data" (enabled)

        The pulsing animation alternates between bright red and dark red
        via stylesheet changes rather than visibility toggling, which avoids
        layout shifts and the button "disappearing" during collection.
        """
        if collecting:
            self.pushButton.setText("Collecting \nData...")
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(239, 68, 68); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(239, 68, 68); "
                "color: white; }"
            )
            self.pushButton.setEnabled(False)
            self._blink_state = False
            self.blink_timer.start(600)  # Pulse every 600ms
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

    def set_preview_state(self, previewing: bool):
        """
        Toggle button appearance for live preview mode.

        When previewing, the button shows "Collect Data" with a blue border
        hint to indicate that live data is streaming. When not previewing,
        the button reverts to the standard green ready state.

        Args:
            previewing: True = live preview active (blue-accent button)
                       False = standard ready state (green button)
        """
        if previewing:
            self.pushButton.setText("Collect Data")
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(74, 222, 128); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(56, 189, 248); }\n"
                "QPushButton:hover { border-color: #2563eb; }"
            )
            self.pushButton.setEnabled(True)
        else:
            # Revert to standard green ready state
            self.set_collecting_state(False)

    def _toggle_button_blink(self):
        """
        Internal: Alternate button color for pulse animation.

        Uses color alternation (bright red / dark red) instead of visibility
        toggling to prevent layout shifts and button flickering.
        """
        self._blink_state = not self._blink_state
        if self._blink_state:
            # Dark red phase
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(185, 28, 28); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(185, 28, 28); "
                "color: white; }"
            )
        else:
            # Bright red phase
            self.pushButton.setStyleSheet(
                "QPushButton { background-color: rgb(239, 68, 68); "
                "border-style: solid; border-width: 2px; border-radius: 10px; "
                "border-color: rgb(239, 68, 68); "
                "color: white; }"
            )

    def update_plot(self, freq_hz: np.ndarray, s11_db: np.ndarray):
        """
        Update plot with new sweep data (overwrites previous trace).

        If the X-axis is in auto-range mode (the default), re-enables
        auto-range so the view stretches horizontally to the current
        frequency span.  When the user has set a manual X range via the
        Axis Setup dialog, auto-range is left disabled and the fixed
        range is preserved.

        The Y-axis range is always controlled by ``_axis_state`` and is
        not auto-ranged.

        Args:
            freq_hz: Frequency array in Hz
            s11_db: S11 magnitude in dB
        """
        self.plot_data_item.setData(freq_hz, s11_db)

        # Only re-enable X auto-range when the user has not set a manual range
        if self._axis_state.get("x_auto_range", True):
            self.plot_widget.getViewBox().enableAutoRange(
                axis=pg.ViewBox.XAxis, enable=True
            )

    # -----------------------------------------------------------------------
    # Axis Setup dialog and helpers
    # -----------------------------------------------------------------------

    def _open_axis_setup_dialog(self):
        """Open the Axis Setup dialog pre-populated with current state.

        Called by the right-click context menu on the plot widget.  If the
        user accepts (OK), the new values are stored in ``_axis_state`` and
        immediately applied to the live plot.
        """
        s = self._axis_state
        dlg = AxisSetupDialog(
            y_max=s["y_max"],
            y_min=s["y_min"],
            y_divisions=s["y_divisions"],
            y_auto_div=s["y_auto_div"],
            x_max_hz=s["x_max_hz"],
            x_min_hz=s["x_min_hz"],
            x_divisions=s["x_divisions"],
            x_auto_div=s["x_auto_div"],
            x_auto_range=s["x_auto_range"],
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.get_values()
            self._axis_state.update(vals)
            self._apply_axis_settings()

    def _apply_axis_settings(self):
        """Apply the current ``_axis_state`` to the live plot.

        Configures Y-axis range and tick labels, X-axis range (fixed or
        auto), and tick divisions for both axes.
        """
        s = self._axis_state

        # --- Y axis ---
        self.plot_widget.setYRange(s["y_min"], s["y_max"], padding=0)

        y_axis = self.plot_widget.getAxis("left")
        if s["y_auto_div"]:
            step = _nice_step(s["y_max"], s["y_min"])
            ticks = [
                (v, f"{v:.0f}dB")
                for v in _frange(s["y_max"], s["y_min"], -step)
            ]
        else:
            n = s["y_divisions"]
            span = s["y_max"] - s["y_min"]
            step = span / n if n else span
            ticks = [
                (s["y_max"] - i * step, f"{s['y_max'] - i * step:.0f}dB")
                for i in range(n + 1)
            ]
        y_axis.setTicks([ticks, []])

        # --- X axis ---
        if not s["x_auto_range"]:
            self.plot_widget.setXRange(
                s["x_min_hz"], s["x_max_hz"], padding=0
            )
            self.plot_widget.getViewBox().enableAutoRange(
                axis=pg.ViewBox.XAxis, enable=False
            )
        else:
            self.plot_widget.getViewBox().enableAutoRange(
                axis=pg.ViewBox.XAxis, enable=True
            )

        x_axis = self.plot_widget.getAxis("bottom")
        if not s["x_auto_div"]:
            x_min = s["x_min_hz"]
            x_max = s["x_max_hz"]
            n = s["x_divisions"]
            span = x_max - x_min
            step = span / n if n else span
            x_ticks = [
                (x_min + i * step, f"{(x_min + i * step) / 1e6:.0f}MHz")
                for i in range(n + 1)
            ]
            x_axis.setTicks([x_ticks, []])
        else:
            x_axis.setTicks(None)  # Let pyqtgraph auto-generate ticks

    def clear_plot(self):
        """Clear plot data (empty trace)."""
        self.plot_data_item.setData([], [])

    def populate_sweep_config(self, config: dict, monitor_config: Optional[dict] = None):
        """
        Populate configuration widgets from config dictionary.

        Maps model fields to the actual widget names from the .ui file:
          start_frequency  -> startFrequencyLineEdit  (displayed as MHz)
          stop_frequency   -> stopFrequencyLineEdit   (displayed as MHz)
          num_points       -> pointsLineEdit
          stim_lvl_dbm     -> levelLineEdit
          num_sweeps       -> numberOfSweepLineEdit
          ifbw_values      -> ifbwFrequencyLineEdit (comma-separated)

        Frequency values are stored in Hz internally but displayed as MHz
        in the UI for readability. The read_sweep_config() method converts
        MHz back to Hz when reading.

        Also computes and displays center and span frequencies (in MHz).

        Args:
            config: Dictionary with keys matching SweepConfig fields (Hz)
            monitor_config: Optional dict with monitor config fields.
                If provided, populates logIntervallineEdit from
                'log_interval_ms' (unless it is "auto").
        """
        # Frequency settings -- display as MHz (model uses Hz)
        if "start_frequency" in config:
            start_hz = config["start_frequency"]
            self.startFrequencyLineEdit.setText(f"{start_hz / 1e6:.3f}")

        if "stop_frequency" in config:
            stop_hz = config["stop_frequency"]
            self.stopFrequencyLineEdit.setText(f"{stop_hz / 1e6:.3f}")

        # Compute and populate center and span (displayed as MHz)
        start = config.get("start_frequency", 0)
        stop = config.get("stop_frequency", 0)
        if start and stop:
            center = (start + stop) / 2.0
            span = stop - start
            self.centerFrequencyLineEdit.setText(f"{center / 1e6:.3f}")
            self.spanFrequencyLineEdit.setText(f"{span / 1e6:.3f}")

        # Acquisition settings
        if "num_points" in config:
            self.pointsLineEdit.setText(str(config["num_points"]))

        if "stim_lvl_dbm" in config:
            self.levelLineEdit.setText(str(config["stim_lvl_dbm"]))

        if "num_sweeps" in config:
            self.numberOfSweepLineEdit.setText(str(config["num_sweeps"]))

        # IFBW values (list -> comma-separated string)
        if "ifbw_values" in config:
            ifbw_str = ", ".join(str(v) for v in config["ifbw_values"])
            self.ifbwFrequencyLineEdit.setText(ifbw_str)

        # Monitor config fields (optional)
        if monitor_config is not None:
            log_ms = monitor_config.get("log_interval_ms", "auto")
            if log_ms != "auto":
                self.logIntervallineEdit.setText(str(log_ms))

    def read_sweep_config(self) -> dict:
        """
        Read configuration values from widgets.

        Frequency values are displayed in MHz but stored internally in Hz.
        This method converts the MHz display values back to Hz.

        Returns:
            Dictionary with config values (strings converted to appropriate types).
            Uses default of 1 for avg_count since there is no widget for it.
            Also includes mode selection and monitor fields:
              mode: "sanity_check" or "continuous_monitoring"
              monitor_duration_s: float (0.0 = indefinite)
              log_interval_ms: "auto" or numeric string
        """
        # Parse IFBW values (comma-separated string -> list of ints)
        ifbw_text = self.ifbwFrequencyLineEdit.text().strip()
        ifbw_values = []
        if ifbw_text:
            try:
                ifbw_values = [int(v.strip()) for v in ifbw_text.split(",")]
            except ValueError:
                ifbw_values = []

        # Frequency values: displayed as MHz, convert to Hz (int)
        try:
            start_freq = int(float(self.startFrequencyLineEdit.text() or 0) * 1e6)
        except ValueError:
            start_freq = 0

        try:
            stop_freq = int(float(self.stopFrequencyLineEdit.text() or 0) * 1e6)
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
            "start_frequency": start_freq,
            "stop_frequency": stop_freq,
            "num_points": num_points,
            "stim_lvl_dbm": stim_lvl,
            "avg_count": 1,  # No widget in UI, use default
            "num_sweeps": num_sweeps,
            "ifbw_values": ifbw_values,
            # Mode configuration
            "mode": self.get_selected_mode(),
            "monitor_duration_s": self.get_monitor_duration_s(),
            "log_interval_ms": self.get_log_interval_ms(),
        }

    def set_device_serial(self, serial: str):
        """
        Update device serial display in the Device > Connect to menu.

        Displays the serial number followed by the device type, matching
        the LibreVNA-GUI convention: "206830535532 (LibreVNA/USB)".
        Re-enables the action (it was disabled during search).

        Args:
            serial: Device serial number string (e.g. "206830535532")
        """
        self.actionSerial_LibreVNA_USB.setText(f"{serial} (LibreVNA/USB)")
        self.actionSerial_LibreVNA_USB.setEnabled(True)

    def set_device_searching(self):
        """
        Show searching state in the Device > Connect to menu.

        Displayed while the background device probe thread is running.
        """
        self.actionSerial_LibreVNA_USB.setText("Searching... (LibreVNA/USB)")
        self.actionSerial_LibreVNA_USB.setEnabled(False)

    def set_device_cleaning(self):
        """
        Show port-cleanup state in the Device > Connect to menu.

        Displayed while the background PortCleanupWorker is killing stale
        processes that hold LibreVNA ports, before retrying device probe.
        """
        self.actionSerial_LibreVNA_USB.setText("Cleaning ports... (LibreVNA/USB)")
        self.actionSerial_LibreVNA_USB.setEnabled(False)

    def set_device_not_found(self):
        """
        Show not-found state in the Device > Connect to menu.

        Displayed when the device probe fails (no device connected, GUI
        not running, or SCPI connection refused).
        """
        self.actionSerial_LibreVNA_USB.setText("Not found (LibreVNA/USB)")
        self.actionSerial_LibreVNA_USB.setEnabled(True)

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

    # -----------------------------------------------------------------------
    # Window close event
    # -----------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent):
        """
        Override to emit window_closing signal before accepting close.

        The Presenter subscribes to window_closing and performs all cleanup
        (stopping worker threads, terminating subprocesses, closing sockets).
        The View remains passive -- it only signals intent to close.

        Args:
            event: The close event from Qt (X button, Alt+F4, programmatic close)
        """
        # Stop the blink timer (owned by View, so cleaned up here)
        self.blink_timer.stop()

        # Notify Presenter to run cleanup logic
        self.window_closing.emit()

        # Show cleanup in status bar (may not render if cleanup is fast)
        self.statusbar.showMessage("Shutting down...", 0)

        # Accept the close event
        event.accept()
