"""controller.py — threaded backend controller (NF-4).

Owns the single E5063A VISA session and runs EVERY instrument operation on one
dedicated QThread (pyvisa sessions are not thread-safe, so all calls must stay on
the thread that opened the session). The presenter talks to it only via signals:
request signals (GUI → controller, auto-queued) and result signals
(controller → GUI, auto-queued). The GUI thread never blocks on VISA.

Backend is injected (E5063ABackend for hardware, StubE5063ABackend offline), so
this controller is backend-agnostic.
"""

from __future__ import annotations

import time
from typing import List

from PySide6.QtCore import QObject, QTimer, Signal, Slot


class BackendController(QObject):
    # ── result signals (→ GUI thread) ──
    sigConnected = Signal(dict)
    sigConfig = Signal(dict)
    sigCalFiles = Signal(list)
    sigRecalled = Signal(dict)
    sigEcalProgress = Signal(int)
    sigEcalDone = Signal(dict)
    sigTrace = Signal(object, object)            # freqs_hz, s11_db
    sigMonitorPoint = Signal(float, float, float)  # elapsed_s, freq_hz, mag_db
    sigMonitorStopped = Signal(int)              # total points
    sigSanityTrace = Signal(object, object)      # freqs_hz, s11_db
    sigSanityRow = Signal(dict)                  # one IFBW's metrics
    sigSanityProgress = Signal(int)
    sigSanityStopped = Signal()
    sigError = Signal(str, str)                  # context, message
    sigBusy = Signal(bool)

    def __init__(self, backend_factory, parent=None):
        """backend_factory(resource) -> backend, called on the controller thread
        in doConnect so the VISA session is created on this thread."""
        super().__init__(parent)
        self._factory = backend_factory
        self._be = None
        # monitor state
        self._mon_timer: QTimer | None = None
        self._mon_t0 = 0.0
        self._mon_duration = 0.0
        self._mon_count = 0
        # sanity state
        self._san_timer: QTimer | None = None
        self._san_ifbws: List[int] = []
        self._san_nsweeps = 0
        self._san_i = 0
        self._san_j = 0
        self._san_times: List[float] = []
        self._san_last = 0.0
        self._san_mins: List[float] = []

    # ── one-shot ops ────────────────────────────────────────
    @Slot(str)
    def doConnect(self, resource: str):
        self.sigBusy.emit(True)
        try:
            if self._be is not None:
                self._be.close()
            self._be = self._factory(resource)   # built on THIS (controller) thread
            info = self._be.connect()
            self.sigConnected.emit(info)
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("connect", str(exc))
        finally:
            self.sigBusy.emit(False)

    @Slot(float, float, int, float, float)
    def doApplyConfig(self, start_hz, stop_hz, points, ifbw_hz, power_dbm):
        self.sigBusy.emit(True)
        try:
            rb = self._be.apply_config(start_hz, stop_hz, points, ifbw_hz, power_dbm)
            self.sigConfig.emit(rb)
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("apply_config", str(exc))
        finally:
            self.sigBusy.emit(False)

    @Slot()
    def doListCal(self):
        try:
            self.sigCalFiles.emit(self._be.list_cal_files())
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("list_cal_files", str(exc))

    @Slot(str)
    def doRecall(self, path: str):
        self.sigBusy.emit(True)
        try:
            self.sigRecalled.emit(self._be.recall_cal(path))
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("recall_cal", str(exc))
        finally:
            self.sigBusy.emit(False)

    @Slot(float, float, int, float, float, int)
    def doRunEcal(self, start_hz, stop_hz, points, ifbw_hz, power_dbm, port):
        self.sigBusy.emit(True)
        try:
            res = self._be.run_ecal(start_hz, stop_hz, points, ifbw_hz, power_dbm,
                                    port=port, on_progress=self.sigEcalProgress.emit)
            self.sigEcalDone.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("run_ecal", str(exc))
        finally:
            self.sigBusy.emit(False)

    @Slot()
    def doVerify(self):
        self.sigBusy.emit(True)
        try:
            freqs, s11 = self._be.read_single_trace()
            self.sigTrace.emit(freqs, s11)
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("verify", str(exc))
        finally:
            # read_single_trace leaves the instrument in BUS + Hold (single-sweep
            # trigger), which freezes the front-panel free-run preview. Always
            # restore live free-run after a verify sweep — even on error.
            self._restore_live_safe()
            self.sigBusy.emit(False)

    # ── monitor loop ────────────────────────────────────────
    @Slot(float, float)
    def doStartMonitor(self, interval_ms: float, duration_s: float):
        if self._mon_timer is None:
            self._mon_timer = QTimer(self)
            self._mon_timer.timeout.connect(self._mon_tick)
        self._mon_t0 = time.monotonic()
        self._mon_duration = duration_s
        self._mon_count = 0
        try:
            self._be.monitor_begin()   # arm continuous latched free-run (full rate)
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("monitor_begin", str(exc))
            return
        # Floor at 5 ms so the event loop can service Stop between ticks. On real
        # hardware monitor_read blocks until the next sweep (~30 ms), so this floor
        # adds no rate penalty; it only tames the instant stub. "auto" → the floor.
        self._mon_timer.setInterval(max(5, int(interval_ms)))
        self._mon_timer.start()

    @Slot()
    def doStopMonitor(self):
        if self._mon_timer is not None:
            self._mon_timer.stop()
        self._monitor_end_safe()
        self.sigMonitorStopped.emit(self._mon_count)

    def _monitor_end_safe(self):
        try:
            if self._be is not None:
                self._be.monitor_end()   # stop + restore live front-panel sweep
        except Exception:  # noqa: BLE001
            self._restore_live_safe()

    def _mon_tick(self):
        try:
            f0, mag = self._be.monitor_read()
        except Exception as exc:  # noqa: BLE001
            if self._mon_timer:
                self._mon_timer.stop()
            self.sigError.emit("monitor", str(exc))
            return
        elapsed = time.monotonic() - self._mon_t0
        self._mon_count += 1
        self.sigMonitorPoint.emit(elapsed, f0, mag)
        if self._mon_duration > 0 and elapsed >= self._mon_duration:
            self._mon_timer.stop()
            self._monitor_end_safe()
            self.sigMonitorStopped.emit(self._mon_count)

    # ── sanity loop ─────────────────────────────────────────
    @Slot(object, int)
    def doStartSanity(self, ifbw_hz_list, num_sweeps: int):
        self._san_ifbws = [int(x) for x in ifbw_hz_list]
        self._san_nsweeps = max(1, num_sweeps)
        self._san_i = 0
        self._san_j = 0
        self._san_times = []
        self._san_mins = []
        self._san_last = 0.0
        if self._san_timer is None:
            self._san_timer = QTimer(self)
            self._san_timer.timeout.connect(self._san_tick)
        if not self._san_ifbws:
            self.sigSanityStopped.emit()
            return
        try:
            self._be.monitor_begin()           # arm continuous free-run (fast path)
            self._be.set_ifbw(self._san_ifbws[0])
        except Exception as exc:  # noqa: BLE001
            self.sigError.emit("sanity set_ifbw", str(exc))
            return
        self._san_last = time.monotonic()
        self._san_timer.setInterval(0)
        self._san_timer.start()

    @Slot()
    def doStopSanity(self):
        if self._san_timer is not None:
            self._san_timer.stop()
        self._restore_live_safe()
        self.sigSanityStopped.emit()

    def _san_tick(self):
        t0 = time.monotonic()
        try:
            freqs, s11 = self._be.read_trace_continuous()
        except Exception as exc:  # noqa: BLE001
            self._san_timer.stop()
            self.sigError.emit("sanity", str(exc))
            return
        # Time the SWEEP itself, not the inter-tick gap (which includes event-loop
        # scheduling idle) — else the benchmark over-reports the sweep time.
        self._san_times.append(time.monotonic() - t0)
        self._san_mins.append(min(s11))
        # Emit the full 801-pt trace only occasionally — plotting it on the GUI
        # thread every sweep contends with the controller thread for the GIL and
        # inflates the measured sweep time. Every 5th keeps live feedback cheap.
        if self._san_j % 5 == 0:
            self.sigSanityTrace.emit(freqs, s11)
        self._san_j += 1
        total = len(self._san_ifbws) * self._san_nsweeps
        done = self._san_i * self._san_nsweeps + self._san_j
        self.sigSanityProgress.emit(int(100 * done / total))

        if self._san_j >= self._san_nsweeps:
            # finalize this IFBW (discard the first dt as cold)
            times = self._san_times[1:] or self._san_times
            mean_ms = 1000.0 * sum(times) / len(times)
            nf = sum(self._san_mins) / len(self._san_mins)
            mins = self._san_mins
            jitter = (max(mins) - min(mins)) if len(mins) > 1 else 0.0
            self.sigSanityRow.emit({
                "ifbw_khz": self._san_ifbws[self._san_i] / 1e3,
                "mean_ms": mean_ms,
                "rate_hz": 1000.0 / mean_ms if mean_ms > 0 else 0.0,
                "nf_db": nf,
                "jitter_db": jitter,
            })
            self._san_i += 1
            self._san_j = 0
            self._san_times = []
            self._san_mins = []
            if self._san_i >= len(self._san_ifbws):
                self._san_timer.stop()
                self._restore_live_safe()
                self.sigSanityStopped.emit()
                return
            try:
                self._be.set_ifbw(self._san_ifbws[self._san_i])
            except Exception as exc:  # noqa: BLE001
                self._san_timer.stop()
                self.sigError.emit("sanity set_ifbw", str(exc))
            self._san_last = time.monotonic()

    @Slot()
    def doClose(self):
        if self._mon_timer:
            self._mon_timer.stop()
        if self._san_timer:
            self._san_timer.stop()
        try:
            self._be.close()   # close() restores live free-run before disconnect
        except Exception:  # noqa: BLE001
            pass

    def _restore_live_safe(self):
        """Restore front-panel free-run; never raise (post-acquisition cleanup)."""
        try:
            if self._be is not None:
                self._be.restore_live()
        except Exception:  # noqa: BLE001
            pass
