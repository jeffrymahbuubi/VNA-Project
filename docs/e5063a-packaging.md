# E5063A Data Collector — packaging to a standalone `.exe` (G-6)

**Status:** ✅ Built & validated 2026-06-04 (PyInstaller 6.19.0 via auto-py-to-exe 2.48.1,
One-Directory). The packaged `.exe` launches, resolves the bundled `mvp`/`core` modules and
`mvp/assets`, shows the WTMH window icon + header emblem, and renders the full Setup UI — no
Python install required on the target.
**Owner:** Aunuun + Claude · **Parent:** [`e5063a-gui-spec.md`](./e5063a-gui-spec.md) §6 (G-6).

---

## 0. TL;DR

```
Entry script : code/ena-dev/gui/e5063a_data_collector.py
Mode         : One Directory   (folder with the .exe + _internal/)
Window       : windowed (no console)
Icon         : code/ena-dev/gui/mvp/assets/WTMH.ico
Output       : dist/E5063A-Data-Collector/E5063A-Data-Collector.exe   (~ run this)
```

Two non-obvious things make or break the build (both handled below):
1. **Exclude `PyQt5` + `PyQt6`** — both PyQt6 and PySide6 are in the venv; PyInstaller
   **aborts** if it tries to bundle two Qt bindings. We use PySide6, so exclude the others.
2. **The `sys.path` hack** — the app reaches `core.visa_connection` via
   `ena_dev_paths` (adds `code/ena_qt6_suite/` to `sys.path`). PyInstaller can't follow a
   runtime `sys.path.insert`, so we pass `--paths` for the three source roots + hidden-imports,
   and `ena_dev_paths.py` got a **`sys.frozen` guard** (commit: skip the dev-tree dir check when
   frozen — else the packaged app raises `ImportError` on startup).

---

## 1. ⚠ Target-machine prerequisite (not bundleable)

The GUI talks to the E5063A through the **Keysight IO Libraries Suite** VISA driver (the
default IVI `pyvisa.ResourceManager()` backend; `ena_dev_paths` even PATH-patches its DLL
folders). PyInstaller **cannot** bundle that native driver — it's a system component.

➡ **Every PC that runs the `.exe` must have Keysight IO Libraries Suite (or NI-VISA)
installed** for USB-TMC to the instrument. The `.exe` removes the *Python* requirement, not the
*VISA-runtime* requirement. (The pure-Python `pyvisa-py` backend isn't a drop-in: `pyusb` isn't
installed and its USB-TMC support is weaker.)

The GUI still **launches and renders fully** without IO Libraries — only Connect/acquire need it.

---

## 2. auto-py-to-exe settings (field by field)

Open auto-py-to-exe (`code/.venv/Scripts/auto-py-to-exe.exe`) and set:

| auto-py-to-exe field | Value |
|---|---|
| **Script Location** | `…/code/ena-dev/gui/e5063a_data_collector.py` |
| **Onefile** | **One Directory** |
| **Console Window** | **Window Based (hide the console)** |
| **Icon** | `…/code/ena-dev/gui/mvp/assets/WTMH.ico` |
| **Additional Files → Add Folder** | source `…/code/ena-dev/gui/mvp/assets` → dest `mvp/assets` |
| **Advanced → `--name`** | `E5063A-Data-Collector` |
| **Advanced → `--paths`** (add 3) | `…/code/ena-dev/gui` · `…/code/ena-dev` · `…/code/ena_qt6_suite` |
| **Advanced → `--hidden-import`** (add 4) | `ena_dev_paths` · `core.visa_connection` · `core.scpi_commands` · `core.simulator` |
| **Advanced → `--exclude-module`** (add 2) | `PyQt5` · `PyQt6`  ← **required, else the build aborts** |
| **Settings → Output Directory** | wherever you like (default `output/`) |

Then **CONVERT .PY TO .EXE**. The result is `…/E5063A-Data-Collector/` (a folder); run
`E5063A-Data-Collector.exe` inside it. Zip the **whole folder** to share.

> auto-py-to-exe just drives PyInstaller, so the field set above is exactly the validated
> command in §3. If you tweak in the GUI, keep the two excludes + three `--paths` + four
> hidden-imports.

---

## 3. Equivalent CLI / `.spec` (the validated recipe)

Run from `code/ena-dev/gui/`:

```powershell
../../.venv/Scripts/pyinstaller.exe --noconfirm `
  --name "E5063A-Data-Collector" --windowed `
  --icon "mvp/assets/WTMH.ico" `
  --paths "." --paths ".." --paths "../../ena_qt6_suite" `
  --add-data "mvp/assets;mvp/assets" `
  --hidden-import ena_dev_paths `
  --hidden-import core.visa_connection `
  --hidden-import core.scpi_commands `
  --hidden-import core.simulator `
  --exclude-module PyQt5 --exclude-module PyQt6 `
  e5063a_data_collector.py
```

This generates `E5063A-Data-Collector.spec` (committed — the canonical recipe). To rebuild
from it later: `pyinstaller --noconfirm E5063A-Data-Collector.spec`.

> `--add-data` uses `;` (Windows path separator). On the spec, `datas=[('mvp/assets','mvp/assets')]`.

---

## 4. What's in the bundle (verified)

```
dist/E5063A-Data-Collector/
  E5063A-Data-Collector.exe          ← launcher
  _internal/
    mvp/assets/{WTMH.ico, wtmh_logo.png, *_arrow.svg}   ← icons/emblem/carets
    PySide6/, pyqtgraph/, numpy/, …                     ← deps
    base_library.zip / PYZ           ← mvp, core, ena_dev_paths (pure-Python modules)
```
- No missing-module warnings for `ena_dev_paths` / `core.*` (warn-file clean).
- `core` + `ena_dev_paths` live in the PYZ (not loose `.py`) — that's normal.

## 5. Validation done (2026-06-04)

- Build exit 0; launched `E5063A-Data-Collector.exe` → process stable (~203 MB), window
  title "E5063A Data Collector".
- Screenshot: **WTMH icon in the titlebar + WTMH emblem in the header**, full Setup UI
  renders (cards, slate palette, combo/spin SVG carets, default resource) — identical to dev.
- Not driven against the instrument from the frozen exe (qt-mcp probe isn't bundled); the
  Connect/acquire code is identical to the dev build (already live-validated) and uses the
  IO-Libraries VISA + the `ena_dev_paths` PATH fix, which **also runs when frozen** (it's
  outside the `sys.frozen` guard).

## 6. Distribution checklist
1. Build (§2 or §3) → `dist/E5063A-Data-Collector/`.
2. On the **target PC**: install **Keysight IO Libraries Suite** (§1).
3. Copy/zip the whole `E5063A-Data-Collector/` folder to the target; run the `.exe`.
4. (Optional) make a desktop shortcut to the `.exe`.

## 7. Notes / future
- **One-File** alternative: add `--onefile` (drop `COLLECT`); single portable `.exe` but slower
  start (unpacks to `%TEMP%\_MEIxxxx`). One-Directory chosen for speed + debuggability.
- The `.gitignore` in `code/ena-dev/gui/` excludes `build/`, `dist/`, `output/`, `_build_log.txt`;
  the `.spec` is committed.
- If a future dep adds a third Qt binding or a dynamically-imported module that PyInstaller
  misses, add it to `--hidden-import` (or `--collect-submodules <pkg>` — but **not**
  `--collect-submodules pyqtgraph`, which re-pulls PyQt6 and re-triggers the dual-binding abort).

## 8. Changelog
| Date | Change | By |
|------|--------|-----|
| 2026-07-24 | **Rebuild with the timestamp fix + versioning (v1.1.0-dev).** `pyinstaller --noconfirm E5063A-Data-Collector.spec` rebuilt cleanly (~2.5 min) with the QPC-timestamp/streaming-CSV code and `mvp/version.py`; launched → stable 204 MB, title "E5063A Data Collector v1.1.0-dev", graceful close. Zip naming convention adopted: `Compress-Archive dist/E5063A-Data-Collector → dist/E5063A-Data-Collector-v<X.Y.Z>-win64.zip` (135.4 MB) — the artifact attached to GitHub Releases (`docs/versioning-and-releases.md` §6.1 has the full command playbook). | Claude (with Aunuun) |
| 2026-06-04 | G-6 built + validated. `sys.frozen` guard added to `ena_dev_paths.py`; PyInstaller One-Directory build with `--paths`×3 + hidden-imports×4 + `--exclude-module PyQt5/PyQt6` + `--add-data mvp/assets` + WTMH `.ico`. Launched the `.exe`: window + WTMH branding + full UI render. auto-py-to-exe field guide (§2) + validated CLI/.spec (§3). IO-Libraries prerequisite documented (§1). | Claude (with Aunuun) |
