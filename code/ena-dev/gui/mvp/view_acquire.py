"""view_acquire.py — Screen 2 (Acquire) for the E5063A Data Collector.

Display-only (MVP View). Common shell + a mode-specific panel (monitor / sanity)
swapped via a QStackedWidget. Every widget has a stable objectName per
docs/e5063a-gui-ux-spec.md §3. Both plots use theme.setup_plot().
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QDoubleSpinBox, QSpinBox, QComboBox, QTableWidget, QHeaderView,
)
import pyqtgraph as pg

from . import theme as T


class AcquirePage(QWidget):
    """Screen 2 — mode-adaptive live data collection."""

    backClicked = Signal()
    startClicked = Signal()
    stopClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("acquirePage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── TopBar with Back ──
        self.backButton = T.button_sm("←  Back to Setup", min_w=140)
        self.backButton.setObjectName("backButton")
        self.backButton.clicked.connect(self.backClicked)
        self.topBar = T.TopBar("Acquiring", right_widget=self.backButton)
        self.topBar.setObjectName("acquireTopBar")
        self.acqDot = self.topBar.dot
        self.acqDot.setObjectName("acqDot")
        root.addWidget(self.topBar)

        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(14)
        root.addWidget(body, 1)

        # ── Mode-specific panel (stacked) ──
        self.modeStack = QStackedWidget()
        self.modeStack.setObjectName("modeStack")
        self.monitorPanel = self._build_monitor_panel()
        self.sanityPanel = self._build_sanity_panel()
        self.modeStack.addWidget(self.monitorPanel)   # index 0
        self.modeStack.addWidget(self.sanityPanel)    # index 1
        col.addWidget(self.modeStack, 1)

        # ── Control bar ──
        col.addWidget(self._build_control_bar())

        # ElidedLabel (design-system D-8): a long "Saved → <path>" must NOT widen the
        # window — it elides to the available width with the full path in the tooltip.
        self.saveStatusLabel = T.ElidedLabel("—", "small", color=T.CLR['t3'])
        self.saveStatusLabel.setObjectName("saveStatusLabel")
        col.addWidget(self.saveStatusLabel)

    # ── Monitor panel ───────────────────────────────────────
    def _build_monitor_panel(self) -> QWidget:
        c = T.card("monitorPanel")
        v = QVBoxLayout(c)
        v.setContentsMargins(T.SIZE['card_pad'], T.SIZE['card_pad_v'],
                             T.SIZE['card_pad'], T.SIZE['card_pad_v']); v.setSpacing(10)
        v.addWidget(T.section_header("Continuous Monitor — min-S11 frequency", T.CLR['cyan']))

        self.monitorPlot = pg.PlotWidget()
        self.monitorPlot.setObjectName("monitorPlot")
        T.setup_plot(self.monitorPlot, y_range=None)
        self.monitorPlot.setLabel('left', 'Min-S11 freq (MHz)')
        self.monitorPlot.setLabel('bottom', 'Time (s)')
        self._monitorCurve = self.monitorPlot.plot(
            [], [], pen=pg.mkPen(T.CLR['trace_monitor'], width=2))
        v.addWidget(self.monitorPlot, 1)

        opts = QWidget(); oh = QHBoxLayout(opts)
        oh.setContentsMargins(0, 0, 0, 0); oh.setSpacing(12)
        self.stopModeSelector = QComboBox(); self.stopModeSelector.setObjectName("stopModeSelector")
        self.stopModeSelector.addItems(["Duration (s)", "Query count", "Manual (until Stop)"])
        self.stopModeSelector.currentIndexChanged.connect(self._apply_stop_mode_visibility)
        self.durationInput = QDoubleSpinBox(); self.durationInput.setObjectName("durationInput")
        self.durationInput.setRange(0, 86400); self.durationInput.setSuffix(" s"); self.durationInput.setValue(60)
        self.queryNumberInput = QSpinBox(); self.queryNumberInput.setObjectName("queryNumberInput")
        self.queryNumberInput.setRange(1, 100000); self.queryNumberInput.setValue(1000)
        self.logIntervalInput = QComboBox(); self.logIntervalInput.setObjectName("logIntervalInput")
        self.logIntervalInput.setEditable(True)
        self.logIntervalInput.addItems(["auto", "50", "100", "200", "500", "1000"])
        oh.addWidget(T.label("Stop by", "label", color=T.CLR['t2']))
        oh.addWidget(self.stopModeSelector)
        self._lblDuration = T.label("Duration", "label", color=T.CLR['t2'])
        oh.addWidget(self._lblDuration); oh.addWidget(self.durationInput)
        self._lblCount = T.label("Queries", "label", color=T.CLR['t2'])
        oh.addWidget(self._lblCount); oh.addWidget(self.queryNumberInput)
        oh.addWidget(T.label("Interval (ms)", "label", color=T.CLR['t2']))
        oh.addWidget(self.logIntervalInput)
        oh.addStretch()
        # responsive: min width + combo min-contents so "auto" et al. never clip (§8.2)
        for _w in (self.stopModeSelector, self.durationInput,
                   self.queryNumberInput, self.logIntervalInput):
            T.field(_w)
        v.addWidget(opts)

        prog = QWidget(); ph = QHBoxLayout(prog)
        ph.setContentsMargins(0, 0, 0, 0); ph.setSpacing(12)
        self.monitorProgress = T.progress_bar(); self.monitorProgress.setObjectName("monitorProgress")
        self.remainingLabel = T.label("—", "small", color=T.CLR['t3'])
        self.remainingLabel.setObjectName("remainingLabel")
        ph.addWidget(self.monitorProgress, 1)
        ph.addWidget(self.remainingLabel)
        v.addWidget(prog)
        self._apply_stop_mode_visibility()

        badges = QWidget(); bg = QHBoxLayout(badges)
        bg.setContentsMargins(0, 0, 0, 0); bg.setSpacing(24)
        self.effIntervalBadge = T.MetricBadge("Eff. interval", "—", "ms")
        self.effIntervalBadge.setObjectName("effIntervalBadge")
        self.minFreqBadge = T.MetricBadge("Min-S11 freq", "—", "MHz")
        self.minFreqBadge.setObjectName("minFreqBadge")
        self.magBadge = T.MetricBadge("Magnitude", "—", "dB")
        self.magBadge.setObjectName("magBadge")
        bg.addWidget(self.effIntervalBadge); bg.addWidget(self.minFreqBadge)
        bg.addWidget(self.magBadge); bg.addStretch()
        v.addWidget(badges)
        return c

    # ── Sanity panel ────────────────────────────────────────
    def _build_sanity_panel(self) -> QWidget:
        c = T.card("sanityPanel")
        v = QVBoxLayout(c)
        v.setContentsMargins(T.SIZE['card_pad'], T.SIZE['card_pad_v'],
                             T.SIZE['card_pad'], T.SIZE['card_pad_v']); v.setSpacing(10)
        v.addWidget(T.section_header("Device Sanity Check — per-IFBW benchmark", T.CLR['accent']))

        self.s11LivePlot = pg.PlotWidget()
        self.s11LivePlot.setObjectName("s11LivePlot")
        T.setup_plot(self.s11LivePlot, y_range=(-40, 5))
        self.s11LivePlot.setLabel('left', 'S11 (dB)')
        self.s11LivePlot.setLabel('bottom', 'Freq (MHz)')
        self._sanityCurve = self.s11LivePlot.plot(
            [], [], pen=pg.mkPen(T.CLR['trace_s11'], width=2))
        v.addWidget(self.s11LivePlot, 1)

        self.currentIfbwLabel = T.label("Current IFBW: —", "small", color=T.CLR['t2'])
        self.currentIfbwLabel.setObjectName("currentIfbwLabel")
        v.addWidget(self.currentIfbwLabel)

        self.overallProgress = T.progress_bar()
        self.overallProgress.setObjectName("overallProgress")
        v.addWidget(self.overallProgress)

        self.metricsTable = QTableWidget(0, 5)
        self.metricsTable.setObjectName("metricsTable")
        self.metricsTable.setHorizontalHeaderLabels(
            ["IFBW (kHz)", "Mean (ms)", "Rate (Hz)", "NF (dB)", "Jitter (dB)"])
        self.metricsTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.metricsTable.verticalHeader().setVisible(False)
        self.metricsTable.setFixedHeight(150)
        v.addWidget(self.metricsTable)
        return c

    # ── Control bar ─────────────────────────────────────────
    def _build_control_bar(self) -> QWidget:
        c = T.card("controlCard")
        h = QHBoxLayout(c)
        h.setContentsMargins(T.SIZE['card_pad'], 12, T.SIZE['card_pad'], 12); h.setSpacing(16)
        self.startButton = T.button("Start Record", min_w=150)
        self.startButton.setObjectName("startButton")
        self.startButton.clicked.connect(self.startClicked)
        self.stopButton = T.button_danger("Stop", min_w=110)
        self.stopButton.setObjectName("stopButton")
        self.stopButton.setEnabled(False)
        self.stopButton.clicked.connect(self.stopClicked)
        h.addWidget(self.startButton)
        h.addWidget(self.stopButton)
        h.addWidget(T.separator_v(26))
        self.elapsedLabel = T.label("00:00:00", "timer", bold=True, color=T.CLR['t1'])
        self.elapsedLabel.setObjectName("elapsedLabel")
        h.addWidget(self.elapsedLabel)
        self.countLabel = T.label("points: 0", "label", color=T.CLR['t2'])
        self.countLabel.setObjectName("countLabel")
        h.addWidget(self.countLabel)
        h.addStretch()
        self.rateBadge = T.MetricBadge("Rate", "—", "Hz")
        self.rateBadge.setObjectName("rateBadge")
        h.addWidget(self.rateBadge)
        return c

    # ── presenter helpers ───────────────────────────────────
    def show_mode(self, is_monitor: bool):
        self.modeStack.setCurrentIndex(0 if is_monitor else 1)
        self.topBar.set_title("Acquiring — " + ("Continuous Monitor" if is_monitor else "Device Sanity Check"))
        self.startButton.setText("Start Record" if is_monitor else "Start Benchmark")

    def set_running(self, running: bool):
        self.startButton.setEnabled(not running)
        self.stopButton.setEnabled(running)
        self.backButton.setEnabled(not running)
        self.acqDot.set_color(T.CLR['amber'] if running else T.CLR['green'])

    def set_monitor_curve(self, ts, freqs_mhz):
        self._monitorCurve.setData(ts, freqs_mhz)

    def set_sanity_curve(self, freqs_mhz, s11_db):
        self._sanityCurve.setData(freqs_mhz, s11_db)

    def _apply_stop_mode_visibility(self, *_):
        mode = self.stopModeSelector.currentIndex()   # 0=duration, 1=count, 2=manual
        self._lblDuration.setVisible(mode == 0)
        self.durationInput.setVisible(mode == 0)
        self._lblCount.setVisible(mode == 1)
        self.queryNumberInput.setVisible(mode == 1)

    def monitor_stop_mode(self) -> str:
        return ("duration", "count", "manual")[self.stopModeSelector.currentIndex()]

    def set_monitor_progress(self, pct: float, remaining_text: str = ""):
        self.monitorProgress.setValue(max(0, min(100, int(pct))))
        self.remainingLabel.setText(remaining_text)
