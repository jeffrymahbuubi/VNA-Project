"""stub_backend.py — no-instrument stub adapters for G-0.

Lets the GUI launch, navigate, and render plots WITHOUT a connected E5063A so
the structure / objectName coverage can be verified via qt-mcp. These implement
the same method signatures as the real adapters (gui-spec §3 contract); G-2/G-2c
will swap in the `ENAConnection`-backed versions wrapping `configure_e5063a.py`
and `calibrate_e5063a.py`.

Fake S11: a resonant dip near 233.5 MHz so the verify/preview plots look real.
"""

from __future__ import annotations

import math
from typing import Callable, List, Tuple


def fake_s11_trace(start_hz: float, stop_hz: float, points: int,
                   t: float = 0.0) -> Tuple[List[float], List[float]]:
    """Return (freqs_hz, s11_db): a Lorentzian notch near 233.5 MHz.

    `t` slowly shifts the notch so a live view visibly animates.
    """
    f0 = 233.5e6 + 0.20e6 * math.sin(t * 0.7)   # resonance wanders ±0.2 MHz
    bw = 1.2e6
    depth = 32.0
    freqs, s11 = [], []
    for i in range(points):
        f = start_hz + (stop_hz - start_hz) * i / max(1, points - 1)
        x = (f - f0) / bw
        mag = -depth / (1.0 + x * x) - 0.5     # floor ~ -0.5 dB off-resonance
        freqs.append(f)
        s11.append(mag)
    return freqs, s11


def argmin_freq(freqs: List[float], s11_db: List[float]) -> Tuple[float, float]:
    """(min_freq_hz, mag_db) at the S11 minimum — Monitor-mode core."""
    idx = min(range(len(s11_db)), key=lambda i: s11_db[i])
    return freqs[idx], s11_db[idx]


class StubConfigureAdapter:
    """Stub of GUIVNAConfigureAdapter."""

    def __init__(self, resource: str = "STUB"):
        self.resource = resource

    def apply_config(self, start_hz, stop_hz, points, ifbw_hz, power_dbm) -> dict:
        return {
            "start_hz": start_hz, "stop_hz": stop_hz, "points": points,
            "ifbw_hz": ifbw_hz, "power_dbm": power_dbm, "accepted": True,
        }

    def recall_cal(self, sta_path: str) -> dict:
        return {"active": True, "cal_type": "SOLT1", "sta_path": sta_path}

    def list_cal_files(self) -> List[str]:
        return [
            r"D:\cal_S11_200-250MHz_801pt.sta",
            r"D:\State03.sta",
        ]


class StubCalibrateAdapter:
    """Stub of GUIVNACalibrateAdapter."""

    def __init__(self, resource: str = "STUB"):
        self.resource = resource

    def detect_ecal(self, port: int = 1) -> str:
        return "+1"  # module present on port 1 (0 = none)

    def run_ecal(self, start_hz, stop_hz, points, ifbw_hz, power_dbm,
                 port=1, on_progress: Callable[[int], None] | None = None) -> dict:
        if on_progress:
            for pct in (10, 40, 70, 100):
                on_progress(pct)
        start_mhz, stop_mhz = start_hz / 1e6, stop_hz / 1e6
        return {
            "active": True,
            "cal_type": "SOLT1",
            "conf_min_mean_max": (-11.30, -11.25, -11.19),
            "sta_path": rf"D:\cal_S11_{start_mhz:g}-{stop_mhz:g}MHz_{points}pt.sta",
        }


class StubSweepAdapter:
    """Stub of GUIVNASweepAdapter (Device Sanity Check)."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def probe_device_serial(self) -> dict:
        return {"serial": "MY54806798", "fw": "A.07.06",
                "idn": "Keysight Technologies,E5063A,MY54806798,A.07.06"}

    def single_trace(self, start_hz, stop_hz, points, t=0.0):
        return fake_s11_trace(start_hz, stop_hz, points, t)


class StubMonitorAdapter:
    """Stub of GUIVNAMonitorAdapter (Continuous Monitor)."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def next_point(self, start_hz, stop_hz, points, t):
        freqs, s11 = fake_s11_trace(start_hz, stop_hz, points, t)
        return argmin_freq(freqs, s11)


class StubE5063ABackend:
    """Stub mirror of E5063ABackend (same method surface) for offline dev / qt-mcp.

    Lets controller.py drive a working GUI with no instrument: connect the GUI
    with resource == 'STUB'.
    """

    def __init__(self, resource: str = "STUB", timeout_ms: int = 0):
        self.resource = resource
        self._open = False
        self._t = 0.0
        self._grid = (200_000_000, 250_000_000, 801)

    @property
    def is_open(self) -> bool:
        return self._open

    def connect(self) -> dict:
        self._open = True
        return self.probe()

    def close(self) -> None:
        self._open = False

    def probe(self) -> dict:
        return {"idn": "Keysight Technologies,E5063A,MY54806798,A.07.06 (STUB)",
                "serial": "MY54806798", "fw": "A.07.06"}

    def apply_config(self, start_hz, stop_hz, points, ifbw_hz, power_dbm) -> dict:
        self._grid = (int(start_hz), int(stop_hz), int(points))
        return {"start_hz": start_hz, "stop_hz": stop_hz, "points": points,
                "ifbw_hz": ifbw_hz, "power_dbm": power_dbm}

    def set_ifbw(self, ifbw_hz: float) -> None:
        pass

    def restore_live(self) -> None:
        pass

    def list_cal_files(self, directory: str = r"D:\\") -> list:
        return [r"D:\cal_S11_200-250MHz_801pt.sta", r"D:\State03.sta"]

    def recall_cal(self, sta_path: str) -> dict:
        return {"active": True, "cal_type": "SOLT1", "sta_path": sta_path}

    def detect_ecal(self, port: int = 1) -> str:
        return "+1"

    def run_ecal(self, start_hz, stop_hz, points, ifbw_hz, power_dbm,
                 port=1, save_dir=r"D:\\", on_progress=None) -> dict:
        self.apply_config(start_hz, stop_hz, points, ifbw_hz, power_dbm)
        if on_progress:
            for pct in (5, 15, 70, 100):
                on_progress(pct)
        start_mhz, stop_mhz = start_hz / 1e6, stop_hz / 1e6
        return {"active": True, "cal_type": "SOLT1",
                "conf_min_mean_max": (-11.30, -11.25, -11.19),
                "sta_path": rf"D:\cal_S11_{start_mhz:g}-{stop_mhz:g}MHz_{points}pt.sta"}

    def read_single_trace(self):
        self._t += 0.15
        s, e, n = self._grid
        return fake_s11_trace(s, e, n, self._t)

    def monitor_min_freq(self):
        freqs, s11 = self.read_single_trace()
        return argmin_freq(freqs, s11)

    def monitor_begin(self) -> None:
        pass

    def read_trace_continuous(self, timeout_s: float = 2.0):
        return self.read_single_trace()

    def monitor_read(self, timeout_s: float = 2.0):
        return self.monitor_min_freq()

    def monitor_end(self) -> None:
        pass

    def sweep_begin(self) -> None:
        pass

    def sweep_read(self):
        return self.read_single_trace()

    def sweep_end(self) -> None:
        pass
