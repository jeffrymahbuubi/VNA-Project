"""main_window.py — E5063A Data Collector shell + presenter (G-3).

QStackedWidget (Setup → Acquire) + a presenter that drives a threaded
BackendController (one VISA session on a dedicated QThread, NF-4). All instrument
work is async: the presenter emits request signals; the controller emits results
back to GUI-thread slots. Backend is real (E5063ABackend) for a normal USB
resource, or stub (StubE5063ABackend) when the resource is "STUB".
"""

from __future__ import annotations

import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal, QMetaObject, Qt
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QTableWidgetItem, QFileDialog

from . import theme as T
from . import dataflux
from . import sanity_xlsx
from .model import VNADataModel, AcquisitionMode, MonitorRecord
from .view_setup import SetupPage
from .view_acquire import AcquirePage
from .view_files import FilesPage
from .controller import BackendController
from .backend_e5063a import E5063ABackend, _ENA_DEV
from .stub_backend import StubE5063ABackend

_PREVIEW_STAMP = "<timestamp>"


def make_backend(resource: str):
    if resource.strip().upper() == "STUB":
        return StubE5063ABackend()
    return E5063ABackend(resource)


class MainWindow(QMainWindow):
    # request signals (GUI → controller, auto-queued onto the controller thread)
    reqConnect = Signal(str)
    reqApplyConfig = Signal(float, float, int, float, float)
    reqListCal = Signal()
    reqRecall = Signal(str)
    reqRunEcal = Signal(float, float, int, float, float, int)
    reqVerify = Signal()
    reqStartMonitor = Signal(float, float)
    reqStopMonitor = Signal()
    reqStartSanity = Signal(object, int)
    reqStopSanity = Signal()
    reqClose = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("E5063A Data Collector")
        self.resize(1080, 800)
        # Responsive floor (design-system §8.5): a usable minimum, NOT the content
        # sizeHint — long labels elide (ElidedLabel) instead of forcing the window wider.
        self.setMinimumSize(T.SIZE['win_min_w'], T.SIZE['win_min_h'])

        self.model = VNADataModel()

        # pages / stack
        self.stack = QStackedWidget(); self.stack.setObjectName("rootStack")
        self.setup_page = SetupPage()
        self.acquire_page = AcquirePage()
        self.files_page = FilesPage()
        self.stack.addWidget(self.setup_page)     # 0
        self.stack.addWidget(self.acquire_page)   # 1
        self.stack.addWidget(self.files_page)     # 2
        self.setCentralWidget(self.stack)

        # backend controller on its own thread
        self._thread = QThread(self)
        self.controller = BackendController(make_backend)
        self.controller.moveToThread(self._thread)
        self._thread.start()

        # run state + elapsed clock (GUI thread, display only)
        self._running = False
        self._t0 = 0.0
        self._mon_ts: list[float] = []
        self._mon_freqs: list[float] = []
        self._mon_records: list[MonitorRecord] = []
        self._mon_start_dt = datetime.now()
        self._mon_target_dur = 0.0
        self._mon_target_count = 0
        self._sanity_rows: list[dict] = []
        self._clock = QTimer(self); self._clock.setInterval(250)
        self._clock.timeout.connect(self._tick_clock)

        self._wire_requests()
        self._wire_results()
        self._wire_view()

        self._refresh_derived(); self._refresh_preview(); self._refresh_gate()

    # ── signal wiring ───────────────────────────────────────
    def _wire_requests(self):
        c = self.controller
        self.reqConnect.connect(c.doConnect)
        self.reqApplyConfig.connect(c.doApplyConfig)
        self.reqListCal.connect(c.doListCal)
        self.reqRecall.connect(c.doRecall)
        self.reqRunEcal.connect(c.doRunEcal)
        self.reqVerify.connect(c.doVerify)
        self.reqStartMonitor.connect(c.doStartMonitor)
        self.reqStopMonitor.connect(c.doStopMonitor)
        self.reqStartSanity.connect(c.doStartSanity)
        self.reqStopSanity.connect(c.doStopSanity)
        self.reqClose.connect(c.doClose)

    def _wire_results(self):
        c = self.controller
        c.sigConnected.connect(self._on_connected)
        c.sigConfig.connect(self._on_config)
        c.sigCalFiles.connect(self._on_cal_files)
        c.sigRecalled.connect(self._on_recalled)
        c.sigEcalProgress.connect(self._on_ecal_progress)
        c.sigEcalDone.connect(self._on_ecal_done)
        c.sigTrace.connect(self._on_trace)
        c.sigMonitorPoint.connect(self._on_monitor_point)
        c.sigMonitorStopped.connect(self._on_monitor_stopped)
        c.sigSanityTrace.connect(self._on_sanity_trace)
        c.sigSanityRow.connect(self._on_sanity_row)
        c.sigSanityProgress.connect(self._on_sanity_progress)
        c.sigSanityStopped.connect(self._on_sanity_stopped)
        c.sigError.connect(self._on_error)
        c.sigBusy.connect(self._on_busy)

    def _wire_view(self):
        s = self.setup_page
        s.connectButton.clicked.connect(self._on_connect)
        s.modeSelector.currentIndexChanged.connect(self._on_view_changed)
        for sb in (s.startFreqInput, s.stopFreqInput, s.pointsInput, s.powerInput):
            sb.valueChanged.connect(self._on_view_changed)
        s.ifbwMonitorInput.currentTextChanged.connect(self._on_view_changed)
        s.ifbwListInput.textChanged.connect(self._on_view_changed)
        s.experimentLabelInput.textChanged.connect(self._refresh_preview)
        s.incModeCheck.toggled.connect(self._refresh_preview)
        s.incGridCheck.toggled.connect(self._refresh_preview)
        s.filesButton.clicked.connect(self._on_open_files)
        s.saveDirButton.clicked.connect(self._on_browse_savedir)   # G-9: wire folder picker
        s.recallButton.clicked.connect(self._on_recall)
        s.runEcalButton.clicked.connect(self._on_run_ecal)
        s.verifyButton.clicked.connect(self._on_verify)
        s.proceedClicked.connect(self._on_proceed)
        a = self.acquire_page
        a.backClicked.connect(self._on_back)
        a.startClicked.connect(self._on_start)
        a.stopClicked.connect(self._on_stop)

        f = self.files_page
        f.backClicked.connect(lambda: self.stack.setCurrentIndex(0))
        f.refreshClicked.connect(self._on_refresh_files)
        f.deleteClicked.connect(self._on_delete_files)
        f.zipClicked.connect(self._on_zip_files)

    # ── model sync / local refreshes ────────────────────────
    def _sync_model(self):
        s, m = self.setup_page, self.model
        m.mode = AcquisitionMode.MONITOR if s.is_monitor_mode() else AcquisitionMode.SANITY
        m.config.start_frequency = int(round(s.startFreqInput.value() * 1e6))
        m.config.stop_frequency = int(round(s.stopFreqInput.value() * 1e6))
        m.config.num_points = s.pointsInput.value()
        m.config.stim_lvl_dbm = s.powerInput.value()
        try:
            m.monitor_config.ifbw_hz = int(float(s.ifbwMonitorInput.currentText()) * 1e3)
        except ValueError:
            pass
        try:
            m.config.ifbw_values = [int(float(x) * 1e3) for x in s.ifbwListInput.text().split(",") if x.strip()]
        except ValueError:
            pass
        m.filename.label = s.experimentLabelInput.text()
        m.filename.include_mode = s.incModeCheck.isChecked()
        m.filename.include_grid = s.incGridCheck.isChecked()
        m.scientific_notation = s.sciNotationCheck.isChecked()

    def _acq_ifbw_hz(self) -> float:
        m = self.model
        if m.mode is AcquisitionMode.MONITOR:
            return float(m.monitor_config.ifbw_hz)
        return float(m.config.ifbw_values[0]) if m.config.ifbw_values else 300e3

    def _emit_apply_config(self, ifbw_hz: float):
        c = self.model.config
        self.reqApplyConfig.emit(float(c.start_frequency), float(c.stop_frequency),
                                 int(c.num_points), float(ifbw_hz), float(c.stim_lvl_dbm))

    def _on_view_changed(self, *_):
        self._sync_model(); self._refresh_derived(); self._refresh_preview()
        self.setup_page.calStaleHint.setVisible(self.model.cal_is_stale() and self.model.calibration.active)
        self._refresh_gate()

    def _refresh_derived(self):
        s = self.setup_page
        center = (s.startFreqInput.value() + s.stopFreqInput.value()) / 2
        span = s.stopFreqInput.value() - s.startFreqInput.value()
        s.centerLabel.setText(f"Center: {center:g} MHz")
        s.spanLabel.setText(f"Span: {span:g} MHz")

    def _refresh_preview(self, *_):
        self._sync_model(); m = self.model
        ext = "csv" if m.mode is AcquisitionMode.MONITOR else "xlsx"
        self.setup_page.set_preview(
            m.filename.compose(m.mode, m.config, m.monitor_config, _PREVIEW_STAMP, ext))

    def _on_browse_savedir(self):
        """G-9: folder picker for the save directory (the button was previously dead).
        Sets saveDirInput, which `_resolve_data_dir()` reads as the source of truth."""
        start = self.setup_page.saveDirInput.text().strip() or str(_ENA_DEV)
        chosen = QFileDialog.getExistingDirectory(self, "Select save directory", start)
        if chosen:
            self.setup_page.saveDirInput.setText(chosen)
            self._refresh_preview()

    def _refresh_gate(self):
        self._sync_model(); m = self.model
        if not m.device.connected:
            self.setup_page.set_proceed_enabled(False, "Connect to the instrument first.")
        elif not m.calibration.active:
            self.setup_page.set_proceed_enabled(False, "Run or recall a calibration first.")
        elif not m.config.is_valid():
            self.setup_page.set_proceed_enabled(False, "Configuration is invalid (check start < stop, points).")
        else:
            self.setup_page.set_proceed_enabled(True, "Ready — proceed to acquisition.")

    # ── setup actions (emit requests) ───────────────────────
    def _on_connect(self):
        self._sync_model()
        self.setup_page.gateLabel.setText("Connecting…")
        self.reqConnect.emit(self.setup_page.resourceInput.text())

    def _on_recall(self):
        self._sync_model()
        self.reqRecall.emit(self.setup_page.calFileInput.currentText())
        self._emit_apply_config(self._acq_ifbw_hz())

    def _on_run_ecal(self):
        self._sync_model()
        self.setup_page.calProgressBar.setVisible(True)
        c = self.model.config
        self.reqRunEcal.emit(float(c.start_frequency), float(c.stop_frequency),
                             int(c.num_points), self._acq_ifbw_hz(),
                             float(c.stim_lvl_dbm), self.setup_page.ecalPortInput.value())

    def _on_verify(self):
        self._sync_model()
        self._emit_apply_config(self._acq_ifbw_hz())
        self.setup_page.verifyStatusLabel.setText("Sweeping…")
        self.reqVerify.emit()

    def _on_proceed(self):
        self._sync_model()
        is_mon = self.model.mode is AcquisitionMode.MONITOR
        self._emit_apply_config(self._acq_ifbw_hz())
        self.acquire_page.show_mode(is_mon)
        self.acquire_page.set_running(False)
        self.acquire_page.acqDot.set_color(T.CLR['green'])
        self.acquire_page.saveStatusLabel.setText("Armed — press Start.")
        self.stack.setCurrentIndex(1)

    # ── controller results (GUI thread) ─────────────────────
    def _on_connected(self, info: dict):
        d = self.model.device
        d.idn_string, d.serial_number, d.firmware, d.connected = (
            info["idn"], info["serial"], info["fw"], True)
        s = self.setup_page
        s.idnLabel.setText(info["idn"]); s.serialLabel.setText(info["serial"])
        s.fwLabel.setText(info["fw"]); s.connDot.set_color(T.CLR['green'])
        s.connectButton.setText("Connected")
        self.reqListCal.emit()
        # Config is applied just-in-time before recall / verify / proceed, so we
        # don't apply it here (keeps the post-connect window short so the next
        # user action isn't queued behind a config write).
        self._refresh_gate()

    def _on_config(self, rb: dict):
        pass  # readback accepted; could reconcile widgets here

    def _on_cal_files(self, files: list):
        s = self.setup_page
        cur = s.calFileInput.currentText()
        s.calFileInput.clear(); s.calFileInput.addItems(files)
        if cur:
            s.calFileInput.setCurrentText(cur)

    def _on_recalled(self, res: dict):
        cal = self.model.calibration
        cal.source = "existing"; cal.sta_path = res["sta_path"]
        cal.active = res["active"]; cal.cal_type = res["cal_type"]; cal.grid = self.model.config.grid
        s = self.setup_page
        s.calActiveDot.set_color(T.CLR['green'])
        s.calTypeLabel.setText(f"Correction ON · {res['cal_type']}")
        s.calSourceLabel.setText(f"recalled {res['sta_path']}")
        s.calStaleHint.setVisible(False)
        self._refresh_gate()

    def _on_ecal_progress(self, pct: int):
        self.setup_page.calProgressBar.setValue(pct)

    def _on_ecal_done(self, res: dict):
        cal = self.model.calibration
        cal.source = "ecal"; cal.sta_path = res["sta_path"]
        cal.active = res["active"]; cal.cal_type = res["cal_type"]
        cal.grid = self.model.config.grid; cal.conf_min_mean_max = res["conf_min_mean_max"]
        s = self.setup_page
        s.calActiveDot.set_color(T.CLR['green'])
        s.calTypeLabel.setText(f"Correction ON · {res['cal_type']}")
        s.calSourceLabel.setText(f"fresh ECal → {res['sta_path']}")
        lo, mid, hi = res["conf_min_mean_max"]
        s.calConfLabel.setText(f"S11 min {lo:.2f} / mean {mid:.2f} / max {hi:.2f} dB")
        s.calStaleHint.setVisible(False)
        QTimer.singleShot(800, lambda: s.calProgressBar.setVisible(False))
        self._refresh_gate()

    def _on_trace(self, freqs, s11):
        fmhz = [f / 1e6 for f in freqs]
        self.setup_page.set_preview_curve(fmhz, s11)
        idx = min(range(len(s11)), key=lambda i: s11[i])
        self.setup_page.verifyStatusLabel.setText(f"min S11 {s11[idx]:.2f} dB @ {fmhz[idx]:.3f} MHz")

    # ── acquire actions ─────────────────────────────────────
    def _on_back(self):
        if not self._running:
            self.stack.setCurrentIndex(0)

    def _on_start(self):
        self._sync_model()
        self._running = True
        self._t0 = time.monotonic()
        self._mon_ts.clear(); self._mon_freqs.clear(); self._mon_records.clear()
        self._mon_start_dt = datetime.now()
        self.acquire_page.set_running(True)
        self.acquire_page.saveStatusLabel.setText("Recording…")
        self._clock.start()
        if self.model.mode is AcquisitionMode.MONITOR:
            a = self.acquire_page
            txt = a.logIntervalInput.currentText().strip().lower()
            if txt == "auto":
                interval_ms = 0.0
            else:
                try:                       # F-3: clamp query interval to 20–1000 ms
                    interval_ms = min(1000.0, max(20.0, float(txt)))
                except ValueError:
                    interval_ms = 0.0
            mode = a.monitor_stop_mode()   # duration | count | manual
            self._mon_target_dur = a.durationInput.value() if mode == "duration" else 0.0
            self._mon_target_count = a.queryNumberInput.value() if mode == "count" else 0
            a.set_monitor_progress(0, "")
            self._emit_apply_config(self._acq_ifbw_hz())
            self.reqStartMonitor.emit(interval_ms, float(self._mon_target_dur))
        else:
            self.acquire_page.metricsTable.setRowCount(0)
            self._sanity_rows = []
            self.reqStartSanity.emit(self.model.config.ifbw_values, self.model.config.num_sweeps)

    def _on_stop(self):
        if self.model.mode is AcquisitionMode.MONITOR:
            self.reqStopMonitor.emit()
        else:
            self.reqStopSanity.emit()

    def _tick_clock(self):
        elapsed = time.monotonic() - self._t0
        self.acquire_page.elapsedLabel.setText(time.strftime("%H:%M:%S", time.gmtime(elapsed)))

    def _on_monitor_point(self, elapsed, f0, mag):
        self._mon_records.append(MonitorRecord(
            self._mon_start_dt + timedelta(seconds=elapsed), f0, mag))
        self._mon_ts.append(elapsed); self._mon_freqs.append(f0 / 1e6)
        if len(self._mon_ts) > 600:   # plot window only; _mon_records keeps all
            self._mon_ts = self._mon_ts[-600:]; self._mon_freqs = self._mon_freqs[-600:]
        n = len(self._mon_records)
        a = self.acquire_page
        a.set_monitor_curve(self._mon_ts, self._mon_freqs)
        a.minFreqBadge.set_value(f"{f0/1e6:.3f}")
        a.magBadge.set_value(f"{mag:.2f}")
        a.countLabel.setText(f"points: {n}")
        if elapsed > 0:
            a.rateBadge.set_value(f"{n/elapsed:.1f}")
            a.effIntervalBadge.set_value(f"{1000*elapsed/n:.0f}")
        # progress + remaining (F-8)
        if self._mon_target_dur > 0:
            a.set_monitor_progress(100 * elapsed / self._mon_target_dur,
                                   f"{max(0, self._mon_target_dur - elapsed):.0f} s left")
        elif self._mon_target_count > 0:
            a.set_monitor_progress(100 * n / self._mon_target_count,
                                   f"{max(0, self._mon_target_count - n)} pts left")
            if n >= self._mon_target_count:
                self.reqStopMonitor.emit()
        else:
            a.set_monitor_progress(0, "manual — press Stop")

    def _on_monitor_stopped(self, count):
        self._finish_acquisition(f"points: {count}")

    def _on_sanity_trace(self, freqs, s11):
        self.acquire_page.set_sanity_curve([f / 1e6 for f in freqs], s11)

    def _on_sanity_row(self, row: dict):
        self._sanity_rows.append(row)
        t = self.acquire_page.metricsTable
        r = t.rowCount(); t.insertRow(r)
        vals = [f"{row['ifbw_khz']:g}", f"{row['mean_ms']:.1f}",
                f"{row['rate_hz']:.1f}", f"{row['nf_db']:.2f}", f"{row['jitter_db']:.3f}"]
        for col, v in enumerate(vals):
            t.setItem(r, col, QTableWidgetItem(v))
        self.acquire_page.currentIfbwLabel.setText(f"Last IFBW: {row['ifbw_khz']:g} kHz @ {row['rate_hz']:.1f} Hz")

    def _on_sanity_progress(self, pct):
        self.acquire_page.overallProgress.setValue(pct)
        self.acquire_page.countLabel.setText(f"progress: {pct}%")

    def _on_sanity_stopped(self):
        self._finish_acquisition("benchmark complete")

    def _finish_acquisition(self, note: str):
        self._running = False
        self._clock.stop()
        self.acquire_page.set_running(False)
        m = self.model
        if m.mode is AcquisitionMode.MONITOR and self._mon_records:
            self._write_monitor_csv(note)
        elif m.mode is AcquisitionMode.SANITY and self._sanity_rows:
            self._write_sanity_xlsx(note)
        else:
            self.acquire_page.saveStatusLabel.setText(f"Stopped ({note}). No data to save.")

    def _resolve_data_dir(self) -> Path:
        raw = self.setup_page.saveDirInput.text().strip()
        base = Path(raw)
        if not base.is_absolute():
            base = Path(_ENA_DEV) / "data"   # canonical ena-dev/data (ux-spec OQ-3)
        return base / datetime.now().strftime("%Y%m%d")

    def _write_monitor_csv(self, note: str):
        m = self.model
        recs = self._mon_records
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = m.filename.compose(m.mode, m.config, m.monitor_config, stamp, "csv")
        if len(recs) > 1:
            span = (recs[-1].timestamp - recs[0].timestamp).total_seconds()
            eff_ms = 1000.0 * span / (len(recs) - 1)
        else:
            eff_ms = 0.0
        try:
            path = dataflux.write_dataflux_csv(
                recs,
                vna_model="E5063A",
                vna_serial=m.device.serial_number or "MY54806798",
                ifbw_hz=m.monitor_config.ifbw_hz,
                eff_log_interval_ms=eff_ms,
                start_hz=m.config.start_frequency,
                stop_hz=m.config.stop_frequency,
                num_points=m.config.num_points,
                out_dir=str(self._resolve_data_dir()),
                filename=name,
                scientific=m.scientific_notation,
            )
            rate = 1000.0 / eff_ms if eff_ms else 0.0
            self.acquire_page.saveStatusLabel.setText(
                f"Saved {len(recs)} pts ({eff_ms:.0f} ms/pt ≈ {rate:.1f} Hz) → {path}")
        except Exception as exc:  # noqa: BLE001
            self.acquire_page.saveStatusLabel.setText(f"CSV write failed: {exc}")

    def _write_sanity_xlsx(self, note: str):
        m = self.model
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = m.filename.compose(m.mode, m.config, m.monitor_config, stamp, "xlsx")
        meta = {
            "model": "E5063A", "serial": m.device.serial_number or "MY54806798",
            "start_mhz": m.config.start_frequency / 1e6,
            "stop_mhz": m.config.stop_frequency / 1e6,
            "points": m.config.num_points, "power_dbm": m.config.stim_lvl_dbm,
            "num_sweeps": m.config.num_sweeps,
        }
        try:
            path = sanity_xlsx.write_sanity_xlsx(
                self._sanity_rows, meta=meta,
                out_dir=str(self._resolve_data_dir()), filename=name)
            self.acquire_page.saveStatusLabel.setText(
                f"Saved {len(self._sanity_rows)} IFBW rows → {path}")
        except Exception as exc:  # noqa: BLE001
            self.acquire_page.saveStatusLabel.setText(f"xlsx write failed: {exc}")

    # ── Files / history page (F-7) ──────────────────────────
    def _scan_files(self):
        base = self._resolve_data_dir().parent   # the data root (drop the <date>)
        if not base.exists():
            return []
        files = list(base.glob("**/*.csv")) + list(base.glob("**/*.xlsx"))
        files = [p for p in files if not p.name.startswith("~$")]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def _on_open_files(self):
        self._on_refresh_files()
        self.stack.setCurrentIndex(2)

    def _on_refresh_files(self):
        self.files_page.set_files([str(p) for p in self._scan_files()])

    def _on_delete_files(self):
        sel = self.files_page.selected_files()
        if not sel:
            self.files_page.set_status("Nothing selected.")
            return
        deleted = 0
        for p in sel:
            try:
                Path(p).unlink(); deleted += 1
            except OSError:
                pass
        self._on_refresh_files()
        self.files_page.set_status(f"Deleted {deleted} file(s).")

    def _on_zip_files(self):
        sel = self.files_page.selected_files()
        if not sel:
            self.files_page.set_status("Nothing selected.")
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = self._resolve_data_dir().parent / f"runs_export_{stamp}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in sel:
                    zf.write(p, arcname=Path(p).name)
            self._on_refresh_files()
            self.files_page.set_status(f"Zipped {len(sel)} file(s) → {zip_path}")
        except Exception as exc:  # noqa: BLE001
            self.files_page.set_status(f"Zip failed: {exc}")

    # ── errors / busy ───────────────────────────────────────
    def _on_error(self, ctx: str, msg: str):
        if ctx == "connect":
            self.setup_page.connDot.set_color(T.CLR['red'])
        if self._running:
            self._finish_acquisition(f"error: {ctx}")
        self.setup_page.gateLabel.setText(f"Error [{ctx}]: {msg}")
        self.setup_page.calProgressBar.setVisible(False)

    def _on_busy(self, busy: bool):
        # Do NOT disable the action buttons — the controller serializes requests
        # on its thread, so a click during a busy op just queues and runs after
        # (it is never lost). Disabling them silently swallowed clicks. We only
        # gate Proceed, which is driven by readiness anyway.
        if busy:
            self.setup_page.proceedButton.setEnabled(False)
        else:
            self._refresh_gate()

    # ── shutdown ────────────────────────────────────────────
    def closeEvent(self, event):
        # Run teardown (stop timers + restore live free-run + close session)
        # SYNCHRONOUSLY on the controller thread BEFORE quitting it. The old code
        # emitted reqClose (queued, cross-thread) then immediately quit the thread,
        # racing the queued doClose → restore_live() was skipped and the instrument
        # was left in BUS+Hold (frozen front panel). BlockingQueuedConnection waits
        # for doClose to finish on the controller thread first.
        try:
            QMetaObject.invokeMethod(
                self.controller, "doClose", Qt.ConnectionType.BlockingQueuedConnection)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._thread.quit()
            self._thread.wait(3000)
            super().closeEvent(event)
