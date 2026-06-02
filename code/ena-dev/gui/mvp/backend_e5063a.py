"""backend_e5063a.py — real E5063A backend over a single ENAConnection session.

Wraps the validated SCPI sequences from the CLI scripts
(`configure_e5063a.py` S-11a/b, `calibrate_e5063a.py` S-18,
`bench_e5063a_realworld.py` S-12d) behind the method surface the GUI presenter
needs. One USBTMC session is opened and reused across all operations.

This is the G-2 deliverable (gui-spec §3 / ux-spec §6). Methods are SYNCHRONOUS
and must be called from a QThread worker (NF-4) — the presenter does that in G-3.

Trace reads use binary REAL32 (ASCII :CALC:DATA:FDAT? is flaky → -410, see
memory `project-e5063a-host-calibration`).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# ── Bootstrap: make `core.visa_connection` importable + apply Windows VISA PATH fix.
#    backend_e5063a.py is at ena-dev/gui/mvp/ → ena-dev/ is three parents up.
_ENA_DEV = Path(__file__).resolve().parent.parent.parent
if str(_ENA_DEV) not in sys.path:
    sys.path.insert(0, str(_ENA_DEV))
import ena_dev_paths  # noqa: F401, E402  (side effect: registers ena_qt6_suite + PATH fix)
from core.visa_connection import ENAConnection, ENAConnectionError  # noqa: E402

DEFAULT_RESOURCE = "USB0::0x2A8D::0x5D01::MY54806798::0::INSTR"
# General I/O timeout. Kept modest so a USBTMC desync (e.g. from an ungraceful
# host exit mid-transaction) surfaces in seconds instead of blocking ~60 s. ECal
# temporarily raises this (it blocks ~10-15 s) — see run_ecal().
DEFAULT_TIMEOUT_MS = 15_000
_ECAL_TIMEOUT_MS = 70_000
_ECAL_ERR_CODES = {31, 32}           # ECal config failed / module not in RF path
_OPER_MEASURING_BIT = 0x0010         # E5063A Operation Status bit 4 = Measuring


class BackendError(Exception):
    """Raised on an instrument operation failure (wraps ENAConnectionError + SCPI errors)."""


class E5063ABackend:
    """One USBTMC session; all GUI instrument operations go through here."""

    def __init__(self, resource: str = DEFAULT_RESOURCE, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self.resource = resource
        self.timeout_ms = timeout_ms
        self._ena: Optional[ENAConnection] = None
        self._freq_axis_hz: Optional[List[float]] = None   # cached per grid

    # ── lifecycle ───────────────────────────────────────────
    @property
    def is_open(self) -> bool:
        return self._ena is not None and self._ena.is_connected

    def connect(self) -> dict:
        """Open the session and return device info (probe)."""
        try:
            self._ena = ENAConnection(self.resource, timeout=self.timeout_ms)
            self._ena.connect()
            # Flush any stale USBTMC buffers from a prior ungraceful exit
            # (a host killed mid-read leaves the instrument addressed-to-talk →
            # -420 Query UNTERMINATED). viClear + *CLS resync the session.
            try:
                self._ena._session.clear()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            self._ena.write("*CLS")
            self._ena.write(":DISP:CCL")   # clear any sticky front-panel error message
            self._ena.write(":ABOR")
            return self.probe()
        except ENAConnectionError as exc:
            self._ena = None
            raise BackendError(f"connect failed: {exc}") from exc

    def close(self) -> None:
        if self._ena is not None:
            try:
                self.restore_live()   # leave the front-panel preview sweeping
            except Exception:  # noqa: BLE001
                pass
            try:
                self._ena.disconnect()
            finally:
                self._ena = None

    def _require(self) -> ENAConnection:
        if not self.is_open:
            raise BackendError("not connected")
        assert self._ena is not None
        return self._ena

    def _check(self, ctx: str) -> None:
        code, msg = self._require().error_check()
        if code != 0:
            raise BackendError(f"{ctx}: SCPI error {code}, '{msg}'")

    # ── probe ───────────────────────────────────────────────
    def probe(self) -> dict:
        ena = self._require()
        idn = ena.query("*IDN?")
        # "Keysight Technologies,E5063A,MY54806798,A.07.06"
        parts = [p.strip() for p in idn.split(",")]
        serial = parts[2] if len(parts) > 2 else ""
        fw = parts[3] if len(parts) > 3 else ""
        return {"idn": idn, "serial": serial, "fw": fw}

    # ── configure ───────────────────────────────────────────
    def apply_config(self, start_hz: float, stop_hz: float, points: int,
                     ifbw_hz: float, power_dbm: float) -> dict:
        """Pin the operating point + S11/MLOG + binary REAL32. Returns readback."""
        ena = self._require()
        ena.write(f":SENS1:FREQ:STAR {start_hz:.6E}")
        ena.write(f":SENS1:FREQ:STOP {stop_hz:.6E}")
        ena.write(f":SENS1:SWE:POIN {points}")
        ena.write(":SENS1:SWE:TYPE LIN")
        ena.write(f":SENS1:BAND:RES {ifbw_hz:.6E}")
        ena.write(f":SOUR1:POW {power_dbm:.3f}")
        ena.write(":CALC1:PAR:COUN 1")
        ena.write(":CALC1:PAR1:DEF S11")
        ena.write(":CALC1:PAR1:SEL")
        ena.write(":CALC1:FORM MLOG")
        ena.write(":FORM:DATA REAL32")
        ena.write(":FORM:BORD SWAP")
        ena.opc_wait()
        self._check("apply_config")
        self._freq_axis_hz = None  # grid changed → invalidate cached axis
        return {
            "start_hz": float(ena.query(":SENS1:FREQ:STAR?")),
            "stop_hz": float(ena.query(":SENS1:FREQ:STOP?")),
            "points": int(float(ena.query(":SENS1:SWE:POIN?"))),
            "ifbw_hz": float(ena.query(":SENS1:BAND:RES?")),
            "power_dbm": float(ena.query(":SOUR1:POW?")),
        }

    def set_ifbw(self, ifbw_hz: float) -> None:
        """Change IFBW only — does NOT invalidate the cal (migration-spec §4A.6)."""
        ena = self._require()
        ena.write(f":SENS1:BAND:RES {ifbw_hz:.6E}")
        ena.opc_wait()
        self._check("set_ifbw")

    # ── calibration: recall ─────────────────────────────────
    def list_cal_files(self, directory: str = r"D:\\") -> List[str]:
        """Best-effort enumeration of instrument-side .sta files."""
        ena = self._require()
        defaults = [r"D:\cal_S11_200-250MHz_801pt.sta", r"D:\State03.sta"]
        try:
            raw = ena.query(f':MMEM:CAT? "{directory}"')
        except ENAConnectionError:
            self._drain()
            return defaults
        import re
        found = re.findall(r'([^",\\]+\.sta)', raw, flags=re.IGNORECASE)
        files = [directory.rstrip("\\/") + "\\" + f for f in found]
        return files or defaults

    def recall_cal(self, sta_path: str) -> dict:
        ena = self._require()
        ena.write(f':MMEM:LOAD:STAT "{sta_path}"')
        ena.opc_wait()
        self._check(f"recall_cal({sta_path})")
        active = ena.query(":SENS1:CORR:STAT?").strip().lstrip("+") == "1"
        cal_type = ena.query(":SENS1:CORR:TYPE1?").strip()
        if not active:
            raise BackendError("cal recalled but correction is NOT active")
        return {"active": active, "cal_type": cal_type, "sta_path": sta_path}

    # ── calibration: ECal ───────────────────────────────────
    def detect_ecal(self, port: int = 1) -> str:
        ena = self._require()
        try:
            path = ena.query(f":SENS1:CORR:COLL:ECAL:PATH? {port}").strip()
        except ENAConnectionError:
            self._drain()
            return "0"
        self._drain()  # PATH? may set a benign error if no module
        return path

    def run_ecal(self, start_hz: float, stop_hz: float, points: int, ifbw_hz: float,
                 power_dbm: float, port: int = 1, save_dir: str = r"D:\\",
                 on_progress: Optional[Callable[[int], None]] = None) -> dict:
        """Host-driven 1-port S11 ECal via the N7550A; saves a grid-named .sta."""
        ena = self._require()
        if on_progress:
            on_progress(5)
        self.apply_config(start_hz, stop_hz, points, ifbw_hz, power_dbm)
        if on_progress:
            on_progress(15)
        # ECal blocks ~10-15 s — raise the session timeout for the *OPC? wait,
        # then restore the modest general timeout.
        try:
            ena._session.timeout = _ECAL_TIMEOUT_MS   # type: ignore[union-attr]
            ena.write(f":SENS1:CORR:COLL:ECAL:SOLT1 {port}")
            ena.opc_wait()  # blocks ~10-15 s
        finally:
            ena._session.timeout = self.timeout_ms     # type: ignore[union-attr]
        errs = self._drain_list()
        ecal_errs = [e for e in errs if e[0] in _ECAL_ERR_CODES]
        if ecal_errs:
            raise BackendError(
                f"ECal module/path error {ecal_errs} — check the N7550A is on port {port}")
        if errs:
            raise BackendError(f"ECal left errors: {errs}")
        if on_progress:
            on_progress(70)
        active = ena.query(":SENS1:CORR:STAT?").strip().lstrip("+") == "1"
        cal_type = ena.query(":SENS1:CORR:TYPE1?").strip()
        if not active:
            raise BackendError("ECal finished but correction is NOT active")
        # confidence sweep (binary REAL32)
        freqs, s11 = self.read_single_trace()
        conf = (min(s11), sum(s11) / len(s11), max(s11))
        # restore live free-run BEFORE the save so the .sta captures the
        # continuous state (else the front-panel preview freezes after recall).
        self.restore_live()
        # save grid-named .sta
        start_mhz, stop_mhz = start_hz / 1e6, stop_hz / 1e6
        cal_name = f"cal_S11_{start_mhz:g}-{stop_mhz:g}MHz_{points}pt.sta"
        sta_path = save_dir.rstrip("\\/") + "\\" + cal_name
        ena.write(":MMEM:STOR:STYP CST")
        ena.write(f':MMEM:STOR "{sta_path}"')
        ena.opc_wait()
        self._check("ecal save .sta")
        if on_progress:
            on_progress(100)
        return {"active": active, "cal_type": cal_type,
                "conf_min_mean_max": conf, "sta_path": sta_path}

    # ── acquisition ─────────────────────────────────────────
    def _freq_axis(self, points: int) -> List[float]:
        if self._freq_axis_hz is not None and len(self._freq_axis_hz) == points:
            return self._freq_axis_hz
        ena = self._require()
        axis = list(ena._session.query_binary_values(  # type: ignore[union-attr]
            ":SENS1:FREQ:DATA?", datatype="f", is_big_endian=False))
        self._freq_axis_hz = axis
        return axis

    def read_single_trace(self) -> Tuple[List[float], List[float]]:
        """One host-paced single sweep → (freqs_hz, s11_db). Binary REAL32."""
        ena = self._require()
        ena.write(":ABOR")
        ena.write(":TRIG:SOUR BUS")
        ena.write(":INIT1:CONT OFF")
        ena.opc_wait()
        ena.write(":INIT1:IMM")
        ena.write(":TRIG:SING")
        ena.opc_wait()
        raw = ena._session.query_binary_values(  # type: ignore[union-attr]
            ":CALC1:DATA:FDAT?", datatype="f", is_big_endian=False)
        s11 = list(raw[0::2])               # MLOG → (mag_dB, 0.0) pairs
        freqs = self._freq_axis(len(s11))
        return freqs, s11

    def monitor_min_freq(self) -> Tuple[float, float]:
        """One sweep → (min_freq_hz, mag_db) at the S11 minimum (Monitor core)."""
        freqs, s11 = self.read_single_trace()
        idx = min(range(len(s11)), key=lambda i: s11[i])
        return freqs[idx], s11[idx]

    def restore_live(self) -> None:
        """Return the instrument to internal free-run so the FRONT PANEL keeps
        sweeping. Single-sweep reads leave it in BUS + Hold, which freezes the
        front-panel preview. Call after any acquisition / before disconnect."""
        if not self.is_open:
            return
        ena = self._require()
        ena.write(":ABOR")
        ena.write(":TRIG:SOUR INT")
        ena.write(":INIT1:CONT ON")
        ena.opc_wait()
        self._drain()

    # ── continuous monitor (optimized — setup once, sweep many) ─────────────
    def monitor_begin(self) -> None:
        """Arm continuous free-run with the latched Measuring-bit sync (the
        validated bench pattern, ~30-39 Hz). Front panel stays live throughout."""
        ena = self._require()
        ena.write("*CLS")                    # clear any residual error/status state
        ena.write(":ABOR")
        ena.write(":FORM:DATA REAL32")
        ena.write(":FORM:BORD SWAP")
        ena.write(":STAT:OPER:PTR 0")        # ignore positive transitions
        ena.write(":STAT:OPER:NTR 16")       # latch bit-4 falling edge (sweep done)
        ena.query(":STAT:OPER:EVEN?")        # clear any stale latched event
        ena.write(":TRIG:SOUR INT")
        ena.write(":INIT1:CONT ON")
        ena.opc_wait()
        self._check("monitor_begin")

    def read_trace_continuous(self, timeout_s: float = 2.0) -> Tuple[List[float], List[float]]:
        """Block until the next free-run sweep completes (latched bit-4), then
        return the full (freqs_hz, s11_db). Assumes monitor_begin() armed
        continuous mode. This is the fast path (~26-39 Hz); the single-sweep
        trigger path (read_single_trace) is slower per sweep."""
        ena = self._require()
        t0 = time.monotonic()
        while True:
            ev = int(float(ena.query(":STAT:OPER:EVEN?")))
            if ev & _OPER_MEASURING_BIT:
                break
            if time.monotonic() - t0 > timeout_s:
                break  # fall through with the latest trace rather than hang
        raw = ena._session.query_binary_values(  # type: ignore[union-attr]
            ":CALC1:DATA:FDAT?", datatype="f", is_big_endian=False)
        s11 = list(raw[0::2])
        freqs = self._freq_axis(len(s11))
        return freqs, s11

    def monitor_read(self, timeout_s: float = 2.0) -> Tuple[float, float]:
        """Next sweep → (min_freq_hz, mag_db). Assumes monitor_begin() was called."""
        freqs, s11 = self.read_trace_continuous(timeout_s)
        idx = min(range(len(s11)), key=lambda i: s11[i])
        return freqs[idx], s11[idx]

    def monitor_end(self) -> None:
        """Stop monitoring; leave the instrument live (front panel free-running)."""
        self.restore_live()

    # ── single-sweep benchmark (setup once, sweep many) ─────────────────────
    def sweep_begin(self) -> None:
        """Arm host-paced single mode ONCE (BUS + CONT OFF). Per-sweep work is
        then just trigger+read (sweep_read) — no re-ABOR/re-trigger-source each
        sweep, so timing reflects the instrument, not host reconfig overhead."""
        ena = self._require()
        ena.write("*CLS")
        ena.write(":ABOR")
        ena.write(":FORM:DATA REAL32")
        ena.write(":FORM:BORD SWAP")
        ena.write(":TRIG:SOUR BUS")
        ena.write(":INIT1:CONT OFF")
        ena.opc_wait()
        self._check("sweep_begin")

    def sweep_read(self) -> Tuple[List[float], List[float]]:
        """One single sweep → (freqs_hz, s11_db). Assumes sweep_begin() ran."""
        ena = self._require()
        ena.write(":INIT1:IMM")
        ena.write(":TRIG:SING")
        ena.opc_wait()
        raw = ena._session.query_binary_values(  # type: ignore[union-attr]
            ":CALC1:DATA:FDAT?", datatype="f", is_big_endian=False)
        s11 = list(raw[0::2])
        freqs = self._freq_axis(len(s11))
        return freqs, s11

    def sweep_end(self) -> None:
        self.restore_live()

    # ── helpers ─────────────────────────────────────────────
    def _drain(self) -> None:
        self._drain_list()

    def _drain_list(self) -> List[Tuple[int, str]]:
        ena = self._require()
        seen: List[Tuple[int, str]] = []
        for _ in range(20):
            code, msg = ena.error_check()
            if code == 0:
                break
            seen.append((code, msg))
        return seen
