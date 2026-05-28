# ena-dev — Project-owned E5063A code

Companion to `LibreVNA-dev/`. Houses scripts, the future DataFlux-replacement
GUI, and run outputs for the **Keysight E5063A ENA** migration documented in
`docs/e5063a-migration-spec.md`.

## Reuse policy (read this before adding code)

The third-party **Amp Qt6 suite** under `code/ena_qt6_suite/` is the canonical
I/O layer. **Reuse, do not fork.**

- Need to talk to the instrument? Use `core.visa_connection.ENAConnection`.
- Need a Qt6 widget with a built-in connection bar? Subclass
  `core.base_widget.ENABaseWidget`.
- Need SCPI strings/constants? Use `core.scpi_commands.SCPI`.

ena-dev imports those from `code/ena_qt6_suite/` via the small path shim in
`ena_dev_paths.py`. The shim adds `code/ena_qt6_suite/` to `sys.path` on
import. Always import it before `core.*`:

```python
import ena_dev_paths  # noqa: F401 — side-effect: registers ena_qt6_suite on sys.path
from core.visa_connection import ENAConnection
```

If a bug or genuine limitation in `ena_qt6_suite/` blocks ena-dev work, prefer
in-order:
1. Write a thin adapter / subclass in ena-dev/ that wraps the Amp class.
2. If adaptation isn't possible, patch `ena_qt6_suite/` and **record the patch
   in `docs/e5063a-migration-spec.md` §13 (Changelog)** so future re-syncs
   from the reference copy don't silently lose it.

## Layout

```
ena-dev/
├── __init__.py
├── ena_dev_paths.py        # sys.path shim → makes core.* / apps.* importable
├── README.md               (this file)
├── scripts/
│   ├── __init__.py
│   └── <to come: probe_e5063a.py, sweep_*.py, monitor_*.py>
├── gui/
│   └── <to come: DataFlux-replacement Qt6 app>
└── data/
    └── <to come: timestamped run outputs (or use ../LibreVNA-dev/data/)>
```

## Running

Same convention as LibreVNA scripts: from the repo root,

```powershell
cd code
uv run python ena-dev/scripts/probe_e5063a.py
```

The shared `code/.venv` already has PySide6; add `pyvisa` and `pyvisa-py`
once before running:

```powershell
uv pip install pyvisa pyvisa-py
```

(KIOLS provides the actual VISA backend — pyvisa-py is kept as a fallback.)

## References

- `docs/e5063a-migration-spec.md` — the living SPEC for this migration.
- `code/ena_qt6_suite/DEVELOPER_GUIDE.md` — Amp suite's own dev guide
  (connection, SCPI cheat-sheet, new-app tutorial).
- `references/reports/20260504/E5063A_參考資料/` — collaborator handover
  (legacy DataFlux behaviour, SCPI cheat-sheet, official PDFs).
