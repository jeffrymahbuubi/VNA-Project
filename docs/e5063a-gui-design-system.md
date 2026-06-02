# E5063A GUI Design System SPEC — adopt the `paod_app` token+factory pattern

**Status:** ✅ Implemented (2026-06-02) in `code/ena-dev/gui/mvp/theme.py` — the
token+factory pattern (CLR/FONT/TOUCH/STYLESHEET + factories + `setup_plot` + StatusDot/
MetricBadge/TopBar) is realized; code-built views (no `.ui`); objectName on every widget.
One refinement to D-? : `card(name)` takes a name so its QSS is objectName-scoped AND the
widget is uniquely findable by qt-mcp.
**Owner:** Aunuun + Claude
**Parent spec:** [`docs/e5063a-gui-spec.md`](./e5063a-gui-spec.md) — this document supplies the
**View-layer design system** for that spec's port. It touches **only** Phase **G-0**
(scaffold the theme module) and **G-5** (parity/polish); Model, Presenter, and the
`ENAConnection` backend are out of scope here.

> ## Why this doc exists
> Feedback (2026-06-02): the current LibreVNA "Data Collector" GUI uses an **old,
> ad-hoc styling system** — inline `setStyleSheet("... rgb(251,146,60) ...")` repeated
> per widget/per state across `LibreVNA-dev/gui/mvp/view.py` (≈1228 lines, hard-coded
> hex/`rgb()` literals, no shared palette, compiled `.ui`). A sibling project,
> **`references/reports/20260602/paod_app`**, already solved this with a clean
> **design-token + widget-factory** pattern. We adopt that *pattern* (not its PAOD/PPG
> functionality) as the reference for the E5063A GUI port.

---

## 0. Decisions (locked 2026-06-02)

| # | Decision | Rationale |
|---|----------|-----------|
| D-1 | **Code-built views consuming `theme.py`** — drop the compiled `main_window.ui` / `Ui_MainWindow` for the E5063A port. | Matches `paod_app` exactly; lets the view use factory components and stay a single source of truth. The current `.ui` carries no logic worth preserving. |
| D-2 | **New `theme.py` design-system module** under `code/ena-dev/gui/mvp/`. | One place for palette, typography, sizing, global QSS, factories, custom widgets. |
| D-3 | **objectName on every interactive/styled widget** as a hard rule from commit 1. | objectName-scoped QSS (`QFrame#card{}`) prevents style leak **and** is required for the qt-mcp build-verify loop (memory `project-qt-mcp-setup`). Current view has only **1** `setObjectName`. |
| D-4 | **Translate, don't copy.** `paod_app` is **PyQt5**; this project is **PySide6**. Reproduce the structure in PySide6 idioms (see §6). | Avoid importing PyQt5 quirks. |
| D-5 | Keep `paod_app`'s **dark-instrument palette** as the starting point. | Its accent/green/red/amber hexes already match what `view.py` uses inline today → low-risk, near drop-in. |

---

## 1. The pattern, in one picture

```
theme.py  ── design tokens ────────────────────────────────────────
  CLR   {}   semantic colors      (bg, panel, card, accent, green…, t1–t4)
  FONT  {}   typography scale      (display/title/section/label/body/small…)
  TOUCH {}   sizing tokens         (btn_h, input_h, min_touch)
  STYLESHEET (one f-string built from tokens) ── applied ONCE at app root
          │
          ├── font(), label()                     text factories
          ├── button(), button_sm/_danger/_success  button factories
          ├── card(), card_raised(), card_status()   QFrame factories (objectName-scoped QSS)
          ├── separator_h/v(), section_header(), pill_badge(), progress_bar()
          ├── setup_plot(pw)                        ← pyqtgraph theming (CRITICAL: 2 plots)
          └── StatusDot, MetricBadge, TopBar        custom-painted QWidget components
                          │
   view.py / pages ───────┘  build UI from factories, never inline hex
   main entry ── app.setStyleSheet(STYLESHEET) once; QStackedLayout for navigation
```

Mantra: **no raw hex/`rgb()`/px literal in a view file** — everything comes from a token
or a factory. A restyle = edit `theme.py` only.

> `paod_app` even contains both stages of its own evolution, which is exactly the
> before/after for this port:
> - `paod_app/ui.py` — *old* inline style (local `C={}` + one `SS` string + private
>   `_btn/_lbl/_card`). **This is where `LibreVNA-dev/gui/mvp/view.py` is today.**
> - `paod_app/theme.py` + page modules — *mature* token+factory system. **This is the target.**

---

## 2. Design tokens (port these into `ena-dev/gui/mvp/theme.py`)

Values below are `paod_app`'s, kept as the starting palette (D-5). Tune only after the
app runs.

### 2.1 `CLR` — semantic color palette
| Group | Keys | Sample values |
|-------|------|---------------|
| Surfaces | `bg, panel, card, card_raised, card_glow, input, plot` | `#080e1c … #090f1e` |
| Borders | `border, border_light, border_accent, divider, grid` | `#1e3460 … #162040` |
| Accent | `accent, accent_hover, accent_dim, accent_glow` | `#3b82f6 …` |
| Status | `green/red/amber` each + `_hover/_dim/_glow`, `cyan` | `#10b981 / #ef4444 / #f59e0b` |
| Text tiers | `t1` (primary) `t2` (secondary) `t3` (muted) `t4` (faint) | `#f0f6ff … #2d4a6e` |

**E5063A additions** (replace PAOD's PPG/ECG trace colors): keep `accent` for the **live
S11 magnitude** trace; add `trace_phase` (e.g. `amber`) for S11 phase; `trace_monitor`
(e.g. `cyan`) for the min-freq time-series; reuse `green/amber/red` for the
connection/quality `StatusDot`.

### 2.2 `FONT` — typography scale (role → px)
`display 34 · title 26 · section 18 · label 15 · body 14 · small 12 · tiny 10 · btn 15 ·
btn_sm 13 · timer 28 · verdict 30 · plot_lbl 11 · mono 13`. Views call `font("section",
bold=True)`, never `QFont("…", 18)`.

### 2.3 `TOUCH` — sizing tokens
`btn_h 52 · btn_sm_h 40 · input_h 46 · combo_h 42 · min_touch 48`.
**Re-tune for desktop:** `paod_app` targets an 800×480 RPi touchscreen; the E5063A GUI is
a Windows desktop app. Keep the token *structure*; you may shrink heights (e.g. `btn_h
36–40`) so it doesn't look oversized on a mouse-driven window.

---

## 3. Factory + component inventory (what to reproduce)

| Factory / component | Purpose | E5063A relevance |
|---|---|---|
| `font(size_key, bold, italic)` | role-based `QFont` | everywhere |
| `label(text, size_key, bold, color)` | pre-styled `QLabel` | everywhere |
| `button()` / `button_sm()` / `button_danger()` / `button_success()` | consistent buttons w/ hover/pressed/disabled + drop-shadow | Collect / Monitor / Stop / Save |
| `card()` / `card_raised()` / `card_status(color_key)` | `QFrame` panels, objectName-scoped QSS, optional glow | device-info panel, config panel, status banner |
| `separator_h/v()`, `section_header(text)`, `pill_badge()`, `progress_bar()` | layout/labeling primitives | section dividers, "Sweeping…" progress |
| **`setup_plot(pw, y_range)`** | one-call pyqtgraph theming: background, axis pens/fonts, grid, `setMenuEnabled(False)`, `hideButtons()`, viewbox border, `setClipToView(True)`, `setDownsampling(auto, 'peak')` | **both** plots: live S11 preview **and** monitor min-freq scroller. Single source guarantees visual + perf parity. |
| `StatusDot(color, size)` | glowing painted indicator (`paintEvent`) | VNA connection / sweep state (green=idle, amber=armed, red=error) |
| `MetricBadge(name, value, ref)` | name → value → ref row | live readouts: min-freq Hz, mag dB, sweep rate |
| `TopBar(title, dot_color, right_widget)` | gradient header w/ status dot + title | app/page header |

`SignalQualityDot` (SNR-based) is PAOD-specific — **skip or repurpose** as an S11 sweep
freshness/health indicator only if useful.

---

## 4. objectName convention (styling × qt-mcp, one rule)

Every widget that is styled or interacted with gets a stable, descriptive
`setObjectName(...)` at creation:

```python
btn = button("Collect Data");  btn.setObjectName("collectButton")
panel = card();                panel.setObjectName("deviceInfoCard")
self.s11_plot.setObjectName("s11PreviewPlot")
self.monitor_plot.setObjectName("monitorPlot")
```

This serves **two** masters simultaneously:
1. **Styling** — QSS targets `QFrame#deviceInfoCard {}` so rules don't leak to children.
2. **Automation** — qt-mcp finds/clicks/asserts by name (`qt_find_widget`, `qt_click`),
   the Playwright-selector workflow in `docs/qt-mcp-gui-automation.md`. The current view
   has only 1 objectName — this is the single biggest verify-loop blocker to fix on port.

---

## 5. Apply-once wiring

```python
# entry (ena-dev/gui main):
from .mvp.theme import STYLESHEET
app = QApplication(sys.argv)
app.setStyleSheet(STYLESHEET)          # global, once — not per widget
win = VNAMainWindow(); win.show()
```

Per-widget `setStyleSheet` is reserved for **dynamic state changes only** (e.g. Collect
button green→red while recording), and even then it should interpolate `CLR[...]` tokens,
never raw hex — mirroring `paod_app/monitor_page.py:toggle_recording`.

---

## 6. PyQt5 → PySide6 translation notes (D-4)

`paod_app` is **PyQt5**; copy the structure, fix these idioms:

| PyQt5 (paod_app) | PySide6 (this project) |
|---|---|
| `from PyQt5.QtWidgets import …` | `from PySide6.QtWidgets import …` |
| `QFont.Bold`, `QFont.Normal` | `QFont.Weight.Bold`, `QFont.Weight.Normal` |
| `Qt.AlignCenter`, `Qt.AlignRight` | `Qt.AlignmentFlag.AlignCenter` (or keep `Qt.AlignCenter` — PySide6 still accepts it; prefer scoped) |
| `Qt.PointingHandCursor` | `Qt.CursorShape.PointingHandCursor` |
| `mb.exec_()` | `mb.exec()` *(view.py already uses `.exec()`)* |
| `QMessageBox.Warning` | `QMessageBox.Icon.Warning` |
| signals: PyQt `pyqtSignal` | PySide6 `Signal` *(view.py already imports `Signal`)* |

`pyqtgraph` is binding-agnostic (already validated in `code/.venv` under PySide6 per
`project-qt-mcp-setup`), so `setup_plot()` ports verbatim. `QGraphicsDropShadowEffect`
exists in both.

---

## 7. Port checklist (folds into gui-spec G-0 and G-5) — ✅ DONE

- [x] **G-0** `ena-dev/gui/mvp/theme.py`: `CLR`, `FONT`, `TOUCH`, `STYLESHEET`,
      `font/label/button*/card*/separator*/section_header/progress_bar/setup_plot`,
      `StatusDot`, `MetricBadge`, `TopBar`, `pill_badge` — PySide6, desktop-retuned `TOUCH`.
- [x] **G-0** Entry (`e5063a_data_collector.py`) applies `STYLESHEET` once; `QStackedWidget` shell.
- [x] **G-0** Every widget has `setObjectName(...)`; 126+ resolve via `qt_find_widget`.
- [x] **G-0/G-3** Views built in code from factories (D-1) — no `.ui`.
- [x] **G-4** `monitorPlot` + `s11PreviewPlot` + `s11LivePlot` all themed via `setup_plot()`.
- [x] **G-5** No raw hex/`rgb()`/px literal in any view file — all via tokens/factories.
- [x] **G-5** Dynamic restyles (StatusDot colour, button states) use `CLR[...]` tokens.

**Acceptance:** no raw color/px literal in any `ena-dev/gui` view file; one global
stylesheet; `qt_find_widget` resolves every interactive widget by name; both plots share
`setup_plot()`.

---

## 8. References
- Inspected reference: `references/reports/20260602/paod_app/theme.py` (mature system),
  `…/ui.py` (the "before" inline style), `…/patient_page.py`, `…/monitor_page.py` (factory
  consumers), `…/main.py` (apply-once + `QStackedLayout`).
- Port target / seam: `docs/e5063a-gui-spec.md` (§2 port-vs-replace map, §5 phases G-0/G-5).
- Source view being replaced: `code/LibreVNA-dev/gui/mvp/view.py` (PySide6, compiled
  `Ui_MainWindow`, inline QSS — the "old design system" being retired for this port).
- Build-verify loop: `docs/qt-mcp-gui-automation.md`; memory `project-qt-mcp-setup`.

## 9. Changelog
| Date | Change | By |
|------|--------|-----|
| 2026-06-02 | Doc created. Inspected `paod_app` design pattern (token module + widget factories + objectName-scoped QSS + `setup_plot` + custom painted components). Locked D-1 code-built views, D-2 `theme.py`, D-3 objectName rule, D-4 PyQt5→PySide6 translation, D-5 keep palette. Token tables, factory inventory, port checklist mapped to gui-spec G-0/G-5. | Claude (with Aunuun) |
