"""view_setup.py — Screen 1 (Setup) for the E5063A Data Collector.

Display-only (MVP View). Builds every widget from theme.py factories, gives each
a stable objectName per docs/e5063a-gui-ux-spec.md §2, and exposes them as
attributes for the presenter to wire. Mode/cal-source visibility toggling is
pure display logic and handled here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QRadioButton,
    QButtonGroup,
)
import pyqtgraph as pg

from . import theme as T


def _labeled(text: str, w: QWidget, label_w: int = 130) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)
    lbl = T.label(text, "label", color=T.CLR['t2'])
    lbl.setFixedWidth(label_w)
    h.addWidget(lbl)
    h.addWidget(w, 1)
    return row


def _card_with_header(name: str, header: str):
    """Return (card_frame, inner_vbox) with a section header already added."""
    c = T.card(name)
    v = QVBoxLayout(c)
    v.setContentsMargins(16, 14, 16, 16)
    v.setSpacing(10)
    v.addWidget(T.section_header(header))
    return c, v


class SetupPage(QWidget):
    """Screen 1 — configure + calibrate + filename + verify."""

    proceedClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("setupPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── TopBar ──
        self.filesButton = T.button_sm("Files…", min_w=80)
        self.filesButton.setObjectName("filesButton")
        self.topBar = T.TopBar("E5063A Data Collector — Setup", right_widget=self.filesButton)
        self.topBar.setObjectName("setupTopBar")
        self.connDot = self.topBar.dot
        self.connDot.setObjectName("connDot")
        root.addWidget(self.topBar)

        # ── Scroll body ──
        scroll = QScrollArea()
        scroll.setObjectName("setupScroll")
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("setupBody")
        col = QVBoxLayout(body)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        col.addWidget(self._build_connection_card())
        col.addWidget(self._build_config_card())
        col.addWidget(self._build_cal_card())
        col.addWidget(self._build_filename_card())
        col.addWidget(self._build_verify_card())
        col.addStretch()

        # ── Footer nav ──
        footer = QWidget()
        footer.setObjectName("setupFooter")
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(16, 8, 16, 12)
        self.gateLabel = T.label("Connect, configure and calibrate to continue.",
                                 "small", color=T.CLR['t3'])
        self.gateLabel.setObjectName("gateLabel")
        fh.addWidget(self.gateLabel)
        fh.addStretch()
        self.proceedButton = T.button_success("Proceed to Acquire  →", min_w=200)
        self.proceedButton.setObjectName("proceedButton")
        self.proceedButton.setEnabled(False)
        self.proceedButton.clicked.connect(self.proceedClicked)
        fh.addWidget(self.proceedButton)
        root.addWidget(footer)

        # initial visibility
        self._apply_mode_visibility()
        self._apply_cal_source_visibility()

    # ── Connection ──────────────────────────────────────────
    def _build_connection_card(self) -> QWidget:
        c, v = _card_with_header("connectionCard", "Connection")
        self.resourceInput = QLineEdit("USB0::0x2A8D::0x5D01::MY54806798::0::INSTR")
        self.resourceInput.setObjectName("resourceInput")
        self.connectButton = T.button("Connect", min_w=120)
        self.connectButton.setObjectName("connectButton")
        rowtop = QWidget(); h = QHBoxLayout(rowtop)
        h.setContentsMargins(0, 0, 0, 0); h.setSpacing(10)
        h.addWidget(self.resourceInput, 1)
        h.addWidget(self.connectButton)
        v.addWidget(rowtop)

        info = QGridLayout()
        info.setHorizontalSpacing(10); info.setVerticalSpacing(4)
        self.idnLabel = T.label("—", "small", color=T.CLR['t2'])
        self.idnLabel.setObjectName("idnLabel")
        self.serialLabel = T.label("—", "small", color=T.CLR['t2'])
        self.serialLabel.setObjectName("serialLabel")
        self.fwLabel = T.label("—", "small", color=T.CLR['t2'])
        self.fwLabel.setObjectName("fwLabel")
        info.addWidget(T.label("IDN", "small", color=T.CLR['t3']), 0, 0)
        info.addWidget(self.idnLabel, 0, 1)
        info.addWidget(T.label("Serial", "small", color=T.CLR['t3']), 1, 0)
        info.addWidget(self.serialLabel, 1, 1)
        info.addWidget(T.label("Firmware", "small", color=T.CLR['t3']), 2, 0)
        info.addWidget(self.fwLabel, 2, 1)
        info.setColumnStretch(1, 1)
        wrap = QWidget(); wrap.setLayout(info)
        v.addWidget(wrap)
        return c

    # ── Configuration ───────────────────────────────────────
    def _build_config_card(self) -> QWidget:
        c, v = _card_with_header("configCard", "Configuration")

        self.modeSelector = QComboBox()
        self.modeSelector.setObjectName("modeSelector")
        self.modeSelector.addItems(["Continuous Monitor", "Device Sanity Check"])
        self.modeSelector.currentIndexChanged.connect(self._apply_mode_visibility)
        v.addWidget(_labeled("Mode", self.modeSelector))

        self.startFreqInput = QDoubleSpinBox()
        self.startFreqInput.setObjectName("startFreqInput")
        self.startFreqInput.setRange(0.1, 18000.0); self.startFreqInput.setDecimals(3)
        self.startFreqInput.setSuffix(" MHz"); self.startFreqInput.setValue(200.0)
        v.addWidget(_labeled("Start", self.startFreqInput))

        self.stopFreqInput = QDoubleSpinBox()
        self.stopFreqInput.setObjectName("stopFreqInput")
        self.stopFreqInput.setRange(0.1, 18000.0); self.stopFreqInput.setDecimals(3)
        self.stopFreqInput.setSuffix(" MHz"); self.stopFreqInput.setValue(250.0)
        v.addWidget(_labeled("Stop", self.stopFreqInput))

        self.pointsInput = QSpinBox()
        self.pointsInput.setObjectName("pointsInput")
        self.pointsInput.setRange(2, 1601); self.pointsInput.setValue(801)
        v.addWidget(_labeled("Points", self.pointsInput))

        self.powerInput = QDoubleSpinBox()
        self.powerInput.setObjectName("powerInput")
        self.powerInput.setRange(-45.0, 10.0); self.powerInput.setDecimals(1)
        self.powerInput.setSuffix(" dBm"); self.powerInput.setValue(-5.0)
        v.addWidget(_labeled("Power", self.powerInput))

        # Monitor-only IFBW
        self.ifbwMonitorInput = QComboBox()
        self.ifbwMonitorInput.setObjectName("ifbwMonitorInput")
        self.ifbwMonitorInput.setEditable(True)
        self.ifbwMonitorInput.addItems(["300", "150", "100", "75", "50", "30", "10", "1"])
        self.ifbwMonitorInput.setCurrentText("300")
        self._rowIfbwMonitor = _labeled("IFBW (kHz)", self.ifbwMonitorInput)
        v.addWidget(self._rowIfbwMonitor)

        # Sanity-only IFBW list + sweeps
        self.ifbwListInput = QLineEdit("300,150,100,50")
        self.ifbwListInput.setObjectName("ifbwListInput")
        self._rowIfbwList = _labeled("IFBW set (kHz)", self.ifbwListInput)
        v.addWidget(self._rowIfbwList)

        self.numSweepsInput = QSpinBox()
        self.numSweepsInput.setObjectName("numSweepsInput")
        self.numSweepsInput.setRange(1, 100000); self.numSweepsInput.setValue(30)
        self._rowNumSweeps = _labeled("Sweeps / IFBW", self.numSweepsInput)
        v.addWidget(self._rowNumSweeps)

        # Derived
        derived = QWidget(); dh = QHBoxLayout(derived)
        dh.setContentsMargins(0, 0, 0, 0); dh.setSpacing(16)
        self.centerLabel = T.label("Center: 225 MHz", "small", color=T.CLR['t3'])
        self.centerLabel.setObjectName("centerLabel")
        self.spanLabel = T.label("Span: 50 MHz", "small", color=T.CLR['t3'])
        self.spanLabel.setObjectName("spanLabel")
        dh.addWidget(self.centerLabel); dh.addWidget(self.spanLabel); dh.addStretch()
        v.addWidget(derived)

        self.calStaleHint = T.label(
            "Grid changed → re-cal needed. (IFBW changes do not.)",
            "small", color=T.CLR['amber'])
        self.calStaleHint.setObjectName("calStaleHint")
        self.calStaleHint.setVisible(False)
        v.addWidget(self.calStaleHint)
        return c

    # ── Calibration ─────────────────────────────────────────
    def _build_cal_card(self) -> QWidget:
        c, v = _card_with_header("calCard", "Calibration")

        sel = QWidget(); sel.setObjectName("calSourceSelector")
        sh = QHBoxLayout(sel); sh.setContentsMargins(0, 0, 0, 0); sh.setSpacing(20)
        self.calSourceExistingRadio = QRadioButton("Use existing .sta")
        self.calSourceExistingRadio.setObjectName("calSourceExistingRadio")
        self.calSourceExistingRadio.setChecked(True)
        self.calSourceEcalRadio = QRadioButton("Run new ECal")
        self.calSourceEcalRadio.setObjectName("calSourceEcalRadio")
        self._calSourceGroup = QButtonGroup(self)
        self._calSourceGroup.addButton(self.calSourceExistingRadio, 0)
        self._calSourceGroup.addButton(self.calSourceEcalRadio, 1)
        self._calSourceGroup.idClicked.connect(self._apply_cal_source_visibility)
        sh.addWidget(self.calSourceExistingRadio)
        sh.addWidget(self.calSourceEcalRadio)
        sh.addStretch()
        v.addWidget(sel)

        # Branch A — existing
        self.calExistingPanel = QWidget(); self.calExistingPanel.setObjectName("calExistingPanel")
        ah = QHBoxLayout(self.calExistingPanel); ah.setContentsMargins(0, 0, 0, 0); ah.setSpacing(10)
        self.calFileInput = QComboBox(); self.calFileInput.setObjectName("calFileInput")
        self.calFileInput.setEditable(True)
        self.calFileInput.addItems([r"D:\cal_S11_200-250MHz_801pt.sta", r"D:\State03.sta"])
        self.calBrowseButton = T.button_sm("Browse host…")
        self.calBrowseButton.setObjectName("calBrowseButton")
        self.recallButton = T.button("Recall", min_w=110)
        self.recallButton.setObjectName("recallButton")
        ah.addWidget(self.calFileInput, 1)
        ah.addWidget(self.calBrowseButton)
        ah.addWidget(self.recallButton)
        v.addWidget(self.calExistingPanel)

        # Branch B — ECal
        self.calEcalPanel = QWidget(); self.calEcalPanel.setObjectName("calEcalPanel")
        bh = QHBoxLayout(self.calEcalPanel); bh.setContentsMargins(0, 0, 0, 0); bh.setSpacing(10)
        self.ecalPortInput = QSpinBox(); self.ecalPortInput.setObjectName("ecalPortInput")
        self.ecalPortInput.setRange(1, 2); self.ecalPortInput.setValue(1)
        self.ecalPortInput.setPrefix("Port ")
        self.runEcalButton = T.button("Run ECal", min_w=140)
        self.runEcalButton.setObjectName("runEcalButton")
        bh.addWidget(self.ecalPortInput)
        bh.addWidget(self.runEcalButton)
        bh.addStretch()
        v.addWidget(self.calEcalPanel)

        self.calProgressBar = T.progress_bar()
        self.calProgressBar.setObjectName("calProgressBar")
        self.calProgressBar.setVisible(False)
        v.addWidget(self.calProgressBar)

        # Shared status
        status = QWidget(); status.setObjectName("calStatusPanel")
        sg = QGridLayout(status); sg.setContentsMargins(0, 4, 0, 0)
        sg.setHorizontalSpacing(10); sg.setVerticalSpacing(4)
        self.calActiveDot = T.StatusDot(T.CLR['t3'], size=10)
        self.calActiveDot.setObjectName("calActiveDot")
        self.calTypeLabel = T.label("not calibrated", "small", color=T.CLR['t2'])
        self.calTypeLabel.setObjectName("calTypeLabel")
        self.calSourceLabel = T.label("—", "small", color=T.CLR['t3'])
        self.calSourceLabel.setObjectName("calSourceLabel")
        self.calConfLabel = T.label("—", "small", color=T.CLR['t3'])
        self.calConfLabel.setObjectName("calConfLabel")
        sg.addWidget(self.calActiveDot, 0, 0)
        sg.addWidget(self.calTypeLabel, 0, 1)
        sg.addWidget(T.label("Source", "small", color=T.CLR['t3']), 1, 0)
        sg.addWidget(self.calSourceLabel, 1, 1)
        sg.addWidget(T.label("Confidence", "small", color=T.CLR['t3']), 2, 0)
        sg.addWidget(self.calConfLabel, 2, 1)
        sg.setColumnStretch(1, 1)
        v.addWidget(status)
        return c

    # ── Filename ────────────────────────────────────────────
    def _build_filename_card(self) -> QWidget:
        c, v = _card_with_header("filenameCard", "Filename & output")
        self.experimentLabelInput = QLineEdit()
        self.experimentLabelInput.setObjectName("experimentLabelInput")
        self.experimentLabelInput.setPlaceholderText("experiment / sample label, e.g. bloodvessel-t3")
        v.addWidget(_labeled("Label", self.experimentLabelInput))

        checks = QWidget(); ch = QHBoxLayout(checks)
        ch.setContentsMargins(130, 0, 0, 0); ch.setSpacing(18)
        self.incModeCheck = QCheckBox("mode+param"); self.incModeCheck.setObjectName("incModeCheck")
        self.incModeCheck.setChecked(True)
        self.incGridCheck = QCheckBox("freq grid"); self.incGridCheck.setObjectName("incGridCheck")
        self.incGridCheck.setChecked(True)
        self.incTimestampCheck = QCheckBox("timestamp"); self.incTimestampCheck.setObjectName("incTimestampCheck")
        self.incTimestampCheck.setChecked(True); self.incTimestampCheck.setEnabled(False)
        ch.addWidget(self.incModeCheck); ch.addWidget(self.incGridCheck)
        ch.addWidget(self.incTimestampCheck); ch.addStretch()
        v.addWidget(checks)

        self.filenamePreviewLabel = T.label("—", "mono", color=T.CLR['cyan'])
        self.filenamePreviewLabel.setObjectName("filenamePreviewLabel")
        self.filenamePreviewLabel.setWordWrap(True)
        v.addWidget(_labeled("Preview", self.filenamePreviewLabel))

        self.saveDirInput = QLineEdit("code/ena-dev/data")
        self.saveDirInput.setObjectName("saveDirInput")
        self.saveDirButton = T.button_sm("Browse…")
        self.saveDirButton.setObjectName("saveDirButton")
        rowd = QWidget(); dh = QHBoxLayout(rowd)
        dh.setContentsMargins(0, 0, 0, 0); dh.setSpacing(10)
        dh.addWidget(self.saveDirInput, 1); dh.addWidget(self.saveDirButton)
        v.addWidget(_labeled("Save dir", rowd))

        self.sciNotationCheck = QCheckBox("Scientific notation in CSV (uncheck for fixed decimal)")
        self.sciNotationCheck.setObjectName("sciNotationCheck")
        self.sciNotationCheck.setChecked(True)
        v.addWidget(self.sciNotationCheck)
        return c

    # ── Verify ──────────────────────────────────────────────
    def _build_verify_card(self) -> QWidget:
        c, v = _card_with_header("verifyCard", "Verify")
        top = QWidget(); th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0); th.setSpacing(10)
        self.verifyButton = T.button("Verify trace", min_w=140)
        self.verifyButton.setObjectName("verifyButton")
        self.verifyStatusLabel = T.label("Run a sweep to confirm DUT + cal.",
                                         "small", color=T.CLR['t3'])
        self.verifyStatusLabel.setObjectName("verifyStatusLabel")
        th.addWidget(self.verifyButton)
        th.addWidget(self.verifyStatusLabel, 1)
        v.addWidget(top)

        self.s11PreviewPlot = pg.PlotWidget()
        self.s11PreviewPlot.setObjectName("s11PreviewPlot")
        self.s11PreviewPlot.setFixedHeight(170)
        T.setup_plot(self.s11PreviewPlot, y_range=(-40, 5))
        self.s11PreviewPlot.setLabel('left', 'S11 (dB)')
        self.s11PreviewPlot.setLabel('bottom', 'Freq (MHz)')
        self._previewCurve = self.s11PreviewPlot.plot(
            [], [], pen=pg.mkPen(T.CLR['trace_s11'], width=2))
        v.addWidget(self.s11PreviewPlot)
        return c

    # ── display logic ───────────────────────────────────────
    def is_monitor_mode(self) -> bool:
        return self.modeSelector.currentIndex() == 0

    def _apply_mode_visibility(self):
        mon = self.is_monitor_mode()
        self._rowIfbwMonitor.setVisible(mon)
        self._rowIfbwList.setVisible(not mon)
        self._rowNumSweeps.setVisible(not mon)

    def _apply_cal_source_visibility(self, *_):
        existing = self.calSourceExistingRadio.isChecked()
        self.calExistingPanel.setVisible(existing)
        self.calEcalPanel.setVisible(not existing)

    # ── presenter helpers ───────────────────────────────────
    def set_preview(self, text: str):
        self.filenamePreviewLabel.setText(text)

    def set_preview_curve(self, freqs_mhz, s11_db):
        self._previewCurve.setData(freqs_mhz, s11_db)

    def set_proceed_enabled(self, on: bool, reason: str = ""):
        self.proceedButton.setEnabled(on)
        if reason:
            self.gateLabel.setText(reason)
