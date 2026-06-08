"""Path shim: makes `code/ena_qt6_suite/` importable from `code/ena-dev/` scripts.

Import this module BEFORE importing from `core.*` or `apps.*` (the Amp suite's
top-level packages). One-line usage:

    import ena_dev_paths  # noqa: F401 — side-effect: adds ena_qt6_suite to sys.path
    from core.visa_connection import ENAConnection
    from core.scpi_commands import SCPI

Rationale
---------
The Amp suite (under code/ena_qt6_suite/) is read-mostly third-party code. We
do NOT fork or copy its `core/` module into ena-dev/. Instead, ena-dev scripts
import from it directly. This keeps a single source of truth for ENAConnection
and lets any upstream improvements flow through with a simple re-copy.

If you find yourself wanting to PATCH ena_qt6_suite/core/*.py, first consider
writing an adapter in ena-dev/ that wraps the Amp class. Only patch
ena_qt6_suite/core/ for actual bugs, and record the patch in
docs/e5063a-migration-spec.md §13 (Changelog).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ENA_DEV_DIR = Path(__file__).resolve().parent          # code/ena-dev/
_CODE_DIR = _ENA_DEV_DIR.parent                          # code/
_ENA_QT6_SUITE_DIR = _CODE_DIR / "ena_qt6_suite"         # code/ena_qt6_suite/

# In a frozen build (PyInstaller / auto-py-to-exe, G-6) the `core` package is
# collected INTO the bundle and is importable directly, while this dev-tree dir
# does NOT exist relative to the unpacked module — so skip the dir check + the
# sys.path insert when frozen (they'd raise / point at a nonexistent dir). The
# Windows VISA PATH fix below still runs (it's needed in the frozen app too).
if not getattr(sys, "frozen", False):
    if not _ENA_QT6_SUITE_DIR.is_dir():
        raise ImportError(
            f"ena_qt6_suite not found at {_ENA_QT6_SUITE_DIR}. "
            "Was the Amp suite copied into code/ena_qt6_suite/?"
        )
    _path_str = str(_ENA_QT6_SUITE_DIR)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)


# -- Windows VISA PATH augmentation ----------------------------------------
#
# Keysight IO Libraries Suite installs visa32.dll / visa64.dll into
# C:\Windows\System32 but does NOT add its dependent-DLL folders
# (`C:\Program Files\Keysight\IO Libraries Suite\bin`,
# `C:\Program Files\IVI Foundation\IVI\Bin`,
# `C:\Program Files\IVI Foundation\VISA\VisaCom64`) to the system PATH on
# a stock install. As a result, when pyvisa's IVI backend tries to
# `viOpenDefaultRM`, the dependent DLL load fails with
# `VI_ERROR_LIBRARY_NFOUND (-1073807202)`.
#
# Diagnosed and fixed 2026-05-28 — see docs/e5063a-migration-spec.md §3.6.
# We prepend the missing folders here so every ena-dev script gets the fix
# automatically. Has no effect on non-Windows hosts.
if sys.platform == "win32":
    _KEYSIGHT_VISA_DIRS = [
        r"C:\Program Files\Keysight\IO Libraries Suite\bin",
        r"C:\Program Files\IVI Foundation\IVI\Bin",
        r"C:\Program Files\IVI Foundation\VISA\VisaCom64",
    ]
    _existing = os.environ.get("PATH", "")
    _to_prepend = [p for p in _KEYSIGHT_VISA_DIRS if Path(p).is_dir() and p not in _existing]
    if _to_prepend:
        os.environ["PATH"] = os.pathsep.join(_to_prepend) + os.pathsep + _existing
        # Python 3.8+: also register with os.add_dll_directory so ctypes
        # respects the new dirs even under Safe DLL Search Mode.
        if hasattr(os, "add_dll_directory"):
            for _d in _to_prepend:
                try:
                    os.add_dll_directory(_d)
                except (OSError, FileNotFoundError):
                    pass


def amp_suite_root() -> Path:
    """Absolute path to the third-party Amp suite root."""
    return _ENA_QT6_SUITE_DIR


def code_root() -> Path:
    """Absolute path to code/ (parent of ena-dev/ and ena_qt6_suite/)."""
    return _CODE_DIR


def ena_dev_root() -> Path:
    """Absolute path to ena-dev/ itself."""
    return _ENA_DEV_DIR
