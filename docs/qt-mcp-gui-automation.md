# qt-mcp — Agent-Driven GUI Automation (for E5063A GUI work)

> **Status:** Installed & security-audited 2026-06-02. **✅ VALIDATED 2026-06-02** against
> `code/ena-dev/gui/qt_mcp_mockup.py` — all core tools work, incl. `qt_scene_snapshot` on a
> pyqtgraph plot (after a one-line probe patch — see §10).
> **Companion memory:** `project_qt_mcp_setup.md`.

---

## 1. What this tool is and why we picked it

**qt-mcp** (repo: [0xCarbon/qt-mcp](https://github.com/0xCarbon/qt-mcp)) is an MCP server that is, in
its own words, *"like Playwright MCP, but for desktop Qt apps."* It lets an AI agent **see and drive a
running PySide6/PyQt application** — read the widget tree, inspect properties, click, type, press keys,
invoke slots, and capture screenshots.

We evaluated the field (2026-06-02 session):

| Option | Verdict for us |
|--------|----------------|
| **qt-mcp** ✅ | PySide6-native, **cross-platform → works on Windows**, widget-tree model, active. **Chosen.** |
| qt-pilot | PySide6 but **Linux-only** (needs Xvfb). Rejected. |
| kwin-mcp | Powerful AT-SPI tree but **KDE/Wayland Linux-only**. Rejected. |
| Squish MCP | Commercial license. Rejected. |
| pytest-qt | Great for *automated testing*, but it's a test library, not an agent-drivable MCP. (Keep in mind for CI later.) |

**Why it matters for E5063A:** the E5063A GUI will mirror script 7's PySide6 MVP. Building a GUI is a slow
edit→launch→click→eyeball loop. qt-mcp collapses that: the agent launches the app, reads the widget tree,
clicks the new button, screenshots the result, and confirms wiring — all without the human driving the mouse.

---

## 2. Current install state (already done — do NOT re-run)

- **Clone:** `references/reports/20260602/qt-mcp/` (this is the audited copy; install is editable against it).
- **Python conflict resolved:** qt-mcp shipped `requires-python>=3.12`, but `code/.venv` is **Python 3.11.9**
  (pinned via `code/.python-version`). The clone's `pyproject.toml` was relaxed to `>=3.11` (code audited —
  no 3.12-only syntax; verified import works on 3.11).
- **Installed editable into `code/.venv`:**
  ```bash
  uv pip install --python "code/.venv/Scripts/python.exe" -e "references/reports/20260602/qt-mcp"
  ```
- **Smoke-tested:** `from qt_mcp.probe import install` ✅, `import qt_mcp.server.mcp_server` ✅, `mcp` dep present ✅.
- **MCP server registered** in `.mcp.json` as `qt-mcp`, command = `code/.venv/Scripts/qt-mcp.exe`
  (NOT `uvx qt-mcp` — we use the local clone, not PyPI), env `QT_MCP_PORT=9142`.

> ⚠️ Because this is editable against the clone, **do not delete or move
> `references/reports/20260602/qt-mcp/`** — that would break the install.

---

## 3. Architecture (mental model)

```
┌─ Target PySide6 app (runs in code/.venv, Python 3.11) ─────────┐
│   in-process PROBE  →  listens on 127.0.0.1:9142 (JSON-RPC/TCP) │
│   (activated only when QT_MCP_PROBE=1)                          │
└───────────────────────────────┬────────────────────────────────┘
                                 │ JSON-RPC over TCP (localhost only)
┌────────────────────────────────┴───────────────────────────────┐
│   qt-mcp SERVER  (qt-mcp.exe)  ── MCP stdio ──►  Claude Code     │
└─────────────────────────────────────────────────────────────────┘
```

Two halves: (1) a **probe** that must run *inside* the target app's process, and (2) a **server** that
Claude talks to, which forwards calls to the probe over localhost TCP. The server is launched automatically
by Claude (it's in `.mcp.json`); **you only have to launch the app with the probe enabled.**

---

## 4. How to activate (every test/dev session)

**Step 1 — launch the target GUI with the probe on** (PowerShell, from the GUI dir):
```powershell
cd "code\LibreVNA-dev\gui"            # or code\ena-dev\gui once it exists
$env:QT_MCP_PROBE=1; uv run python <your_gui_script>.py
```
The `.pth` auto-loader sees `QT_MCP_PROBE=1`, monkey-patches `QApplication.__init__`, and auto-installs the
probe the moment the app's `QApplication` is created. No code change needed in the GUI.

**Alternative (explicit, no env var):** add right after the `QApplication(...)` line:
```python
from qt_mcp.probe import install
install()  # idempotent; no-op if already installed
```

**Step 2 — drive it from Claude.** With the app running, ask things like:
- "List the open windows" → `qt_list_windows`
- "Snapshot the widget tree" → `qt_snapshot`
- "Click the widget named `collect_button`" → `qt_click`
- "Screenshot the plot" → `qt_screenshot`

---

## 5. MCP tool reference (what the agent can call)

| Tool | Purpose |
|------|---------|
| `qt_snapshot` | Full widget tree as a structured (accessibility-like) snapshot — the primary "see the UI" call |
| `qt_screenshot` | PNG of a widget or whole window (returned base64) |
| `qt_widget_details` | All Qt properties of one widget |
| `qt_click` | Click a widget (left/right/middle, modifiers) |
| `qt_type` | Type text into a widget |
| `qt_key_press` | Key event (Return, Escape, Ctrl+S, …) |
| `qt_set_property` | Set a Qt property on a widget |
| `qt_invoke_slot` | Call a slot/method on a QObject |
| `qt_list_windows` | All top-level windows |
| `qt_object_tree` | Full QObject parent-child tree |
| `qt_scene_snapshot` | Items in a `QGraphicsScene` — **use this for pyqtgraph plots** (PlotWidget is a QGraphicsView) |
| `qt_vtk_scene_info` / `qt_vtk_screenshot` | 3D/VTK scenes (not needed here) |

Underlying probe methods also include `find_widget`, `get_text`, `trigger_action`, `wait_for`, `menu_items`,
`active_popup`, `qt_messages` (captured Qt warnings), `thread_check`, `layout_check`, `signals`, and `batch`
(multiple steps in one round trip). Most are surfaced through the tools above.

---

## 6. The E5063A GUI build-verify loop (the actual use case)

Target: build `code/ena-dev/gui/` (empty today) as a PySide6 MVP, likely mirroring script 7
(`gui/mvp/{model,view,presenter,backend_wrapper}.py`). qt-mcp accelerates each iteration:

1. **Implement** a view change (e.g., add a "Start Sweep" button, a freq-range input, an S11 plot).
2. **Launch** with `QT_MCP_PROBE=1`.
3. **Verify via agent**, not by hand:
   - `qt_snapshot` → confirm the widget exists, correct parent, correct `objectName`.
   - `qt_widget_details` → confirm properties (enabled, text, range).
   - `qt_click` / `qt_type` → exercise the control.
   - `qt_messages` → catch Qt warnings (e.g., layout/thread issues) the human would miss.
   - `qt_screenshot` / `qt_scene_snapshot` → confirm the plot renders / updates.
4. **Iterate** — the agent reports back what it saw and fixes wiring without a manual click-through.

**Make this work better:** give every interactive widget a stable `setObjectName("...")` in the view
(buttons, inputs, plot widgets). qt-mcp can traverse the tree regardless, but click/find **by name** is far
more reliable than by index — exactly like Playwright relies on selectors. This is a cheap habit to enforce
from the first commit of the E5063A GUI.

---

## 7. Security posture (audited 2026-06-02 — LOW RISK)

Full source (17 files) was read. **Clean:** no outbound network/telemetry, no `subprocess`/`os.system`/`eval`,
no disk writes (screenshots go to in-memory `QBuffer`), 1 runtime dep (`mcp`). Ships `SECURITY.md`,
`.gitleaks.toml`, security CI, `pip-audit`. **Two awareness items, not blockers:**

1. **Gated `.pth` auto-loader** (`code/.venv/.../qt_mcp_probe.pth`) runs at *every* Python startup in the
   venv but is a **no-op unless `QT_MCP_PROBE=1`**. → Never set that env var globally/persistently; scope it
   to the single GUI launch.
2. **Probe port 9142 is unauthenticated** (binds 127.0.0.1 only, so not network-exposed). While an
   instrumented GUI is live, any *local* process could drive it — same model as Playwright CDP / tokenless
   Jupyter. → Don't run an instrumented GUI unattended on a shared machine.

**Right pre-install vetting tool for MCPs in this repo:** `cisco-ai-mcp-scanner` (already in
`code/pyproject.toml`) — *not* claude-flow's `aidefence_*` tools (those scan text for prompt-injection/PII,
not package malware).

---

## 8. Smoke-test procedure (✅ executed 2026-06-02 — see §10 for results)

> **This is no longer a TODO.** qt-mcp was validated 2026-06-02 against
> `code/ena-dev/gui/qt_mcp_mockup.py` (results in §10). The procedure below is kept as the
> **reusable smoke test** — re-run it (against the mockup, or any instrumented GUI) whenever you
> want to confirm qt-mcp still works after an env change, a clone re-sync, or a Claude Code restart.

**Pre-flight**
1. Restart Claude Code so it loads the new `qt-mcp` MCP server; **approve** it when prompted (project-scoped
   `.mcp.json` servers require approval).
2. Confirm the server is connected (qt_* tools become available).

**Smoke test (use script 7 as a known-good target before touching E5063A)**
```powershell
cd "code\LibreVNA-dev\gui"
$env:QT_MCP_PROBE=1; uv run python 7_realtime_vna_plotter_mvp.py
```
Then, from Claude:
- `qt_list_windows` → expect the script-7 main window. **(Acceptance: ≥1 window returned.)**
- `qt_snapshot` → expect a widget tree incl. the Collect Data + Monitor buttons.
- `qt_widget_details` on a button → expect correct text/enabled state.
- `qt_screenshot` of the main window → expect a non-empty PNG.
- `qt_scene_snapshot` on the pyqtgraph PlotWidget → expect scene items (validates plot introspection).
- `qt_click` the Collect Data button → expect the app to react (button blinks / sweep starts).

**Acceptance criteria for "qt-mcp works":** snapshot returns a tree that matches the real UI, a screenshot
comes back non-empty, and a click produces a visible state change reported back by a follow-up snapshot.

**Troubleshooting**
- *No qt_* tools:* server not loaded → restart/approve; check `.mcp.json` path to `qt-mcp.exe` is valid.
- *Tools present but "probe not connected":* the app wasn't launched with `QT_MCP_PROBE=1`, or it's not on
  3.11/`code/.venv`, or port 9142 is taken (`QT_MCP_PORT` to change). Verify probe is live:
  `QApplication.instance().findChild(QObject, "qt_mcp_probe")` should be non-None inside the app.
- *Editable install broke:* don't move `references/reports/20260602/qt-mcp/`.

---

## 9. Key facts to carry forward (cheat sheet)

- Install = **editable against the clone**; clone path must persist.
- Activation = **`QT_MCP_PROBE=1` on the GUI launch only** (never global).
- App must run on **`code/.venv` / Python 3.11** (where qt-mcp is installed).
- Server in `.mcp.json` → `code/.venv/Scripts/qt-mcp.exe` (local clone, not PyPI).
- For pyqtgraph plots use **`qt_scene_snapshot`**, not just screenshots.
- Enforce **`setObjectName(...)`** on E5063A GUI widgets for reliable agent control.
- Vet future MCPs with **`cisco-ai-mcp-scanner`**, not aidefence.

---

## 10. Validation run + applied patch (2026-06-02)

**Validated against** `code/ena-dev/gui/qt_mcp_mockup.py` — a **keeper** PySide6 smoke-test GUI
(not throwaway): button / line-edit / apply-button / checkbox / status-label + a pyqtgraph
`PlotWidget` showing a mock S11 resonance dip; every widget has a stable `setObjectName`. It is the
canonical "is qt-mcp working?" harness — re-run §8 against it after any env change or clone re-sync.
Launched with `QT_MCP_PROBE=1 QT_MCP_PORT=9142 ../../.venv/Scripts/python.exe qt_mcp_mockup.py`
(background). Stop it after testing:
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? CommandLine -like '*qt_mcp_mockup*' | Stop-Process -Force`.

**Tools confirmed working:** `qt_list_windows`, `qt_snapshot` (tree matched source exactly),
`qt_find_widget`, `qt_get_text`, `qt_click` (fired slots — label updated), `qt_type` (text
round-tripped), `qt_widget_details`, `qt_messages` (no Qt warnings), `qt_screenshot` (non-empty
PNGs of window and of the plot), and — after the patch below — `qt_scene_snapshot` (20 scene items
incl. `PlotCurveItem`, axis labels, title, `ViewBox`, `PlotItem`).

**pyqtgraph install:** was missing from `code/.venv`; installed `pyqtgraph==0.14.0` via
`uv pip install --python .venv/Scripts/python.exe pyqtgraph`. (Required for `qt_scene_snapshot`
testing and for the real E5063A plot view.)

### ⚠️ Patch applied to the qt-mcp clone — DO NOT lose on re-sync

`qt_scene_snapshot` crashed on any pyqtgraph item with `'numpy.ndarray' object is not callable`.
**Root cause:** `src/qt_mcp/probe/scene_inspector.py` called `item.data(0)` assuming
`QGraphicsItem.data(int)`, but pyqtgraph's `PlotCurveItem`/`ScatterPlotItem` **shadow `.data` with a
non-callable numpy-array attribute**. **Fix** (guard that `data` is callable first):

```python
# scene_inspector.py, in scene_snapshot(), replacing `data = item.data(0)`:
item_data = getattr(item, "data", None)
if callable(item_data):
    try:
        data = item_data(0)
    except (RuntimeError, TypeError):
        data = None
    if data is not None:
        info["data"] = repr(data)
```

The install is **editable** against `references/reports/20260602/qt-mcp/`, so the patch lives in that
clone (`src/qt_mcp/probe/scene_inspector.py`). The probe runs **in-process** in the target GUI →
**restart the GUI to reload the patched module** (no server restart needed). If the clone is ever
re-synced from upstream, re-apply this patch (or upstream it).
