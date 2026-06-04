# E5063A GUI Design System SPEC — adopt the `paod_app` token+factory pattern

**Status:** ✅ Implemented (2026-06-02) in `code/ena-dev/gui/mvp/theme.py` — the
token+factory pattern (CLR/FONT/TOUCH/STYLESHEET + factories + `setup_plot` + StatusDot/
MetricBadge/TopBar) is realized; code-built views (no `.ui`); objectName on every widget.
One refinement to D-? : `card(name)` takes a name so its QSS is objectName-scoped AND the
widget is uniquely findable by qt-mcp.
**Update 2026-06-04 (live testing):** the token/factory core is done, but live testing
surfaced sizing/glyph gaps — invisible combo/spin arrows, clipped combo text, and a long
save-path that grew the window. These are addressed by a new **responsive sizing +
control-glyph** layer (decisions D-6/D-7/D-8, §8), tracked as gui-spec **G-7**
(**✅ implemented + live-validated 2026-06-04**; combo "auto" fits, long path no longer
widens the window, locked timestamp legible, crisp ▼/▲ via SVG carets — see §8.3).
A further **visual refresh (G-8)** is **✅ implemented + live-validated 2026-06-04** (§9,
D-9…D-12): two-column config grid (no maximized dead zone), medium-slate palette (visible
panels + recessed input wells), semibold/brighter labels, combo caret flips ▲ on open.
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
| D-6 | **Responsive ("flexbox-for-Qt") sizing convention** — a `SIZE` token group + `QSizePolicy` rules so widgets flex with the window between sensible min/max bounds, and **no single label can dictate the window's minimum width**. (Added 2026-06-04 after live testing; see §8.) | The current views mix `setFixedWidth`/`setFixedHeight` with unbounded `QLabel`s, so a long save-path string grew the window 1080→1632 px (live-observed #6), and squeezed combos clip text ("auto"→"uto", #5). A min/max + elide policy is the durable fix. |
| D-7 | **Draw combo/spin glyphs via small SVG carets** referenced by absolute-path `image: url(...)` in `STYLESHEET` (`QComboBox::down-arrow`, `QSpinBox::up/down-arrow`). *(Originally specced as asset-free CSS border-triangles, but Qt renders those as a dash; revised 2026-06-04 to SVG assets — see §8.3.)* | Styling `::drop-down`/spin-buttons with `border:none` removed the native arrow, leaving an invisible drop indicator on the dark theme (live-observed #1). SVG is the only way to guarantee a crisp ▼/▲. |
| D-8 | **`ElidedLabel` component** for any label that shows arbitrary-length content (save path, filename preview, cal source). Elides (middle, for paths) to the available width, full text in tooltip, `minimumWidth = 0`. | A label that must never propagate its content width to the layout minimum — root fix for #6. |
| D-9 | **Two-column Configuration grid** (`QGridLayout`) instead of full-width single-column rows. | Live testing (2026-06-04, gui-spec G-8): the `field_max_w` cap from G-7 left a large empty card area when maximized; a 2-column grid uses the width and reads as an instrument panel. User choice. See §9. |
| D-10 | **"Bigger palette refresh" — near-black → medium slate.** Raise surface tokens so panels are clearly visible and inputs read as recessed wells; strengthen borders; brighten secondary text. | "Text on black" feel (#2): the near-black palette + flat rows made labels float on black. A medium-slate palette with surface hierarchy fixes it. User chose the *bigger* refresh over incremental elevation. See §9. |
| D-11 | **Field labels = semibold + brighter** (weight 600 / DemiBold, `t1`-tier color) in `_labeled()`. | Labels looked "dry" (#3) at normal weight / muted `t2`. User choice. |
| D-12 | **Combo open-state feedback** — `QComboBox::down-arrow:on` flips to `up_arrow.svg`; `::drop-down:pressed` tints the drop-down zone. **Restyle sub-controls ONLY** (a whole-combo `QComboBox:on{}` rule causes an accent-fill bug — §9.4). | The dropdown gave no pressed/open feedback (#4). User choice; reuses existing `up_arrow.svg`. |
| D-13 | **Increase card inner padding** — `_card_with_header` (and the Acquire cards) contentsMargins 16 → `SIZE['card_pad']` (≈22 h / 18 v) so readout/label text isn't tight against the rounded border. | Live feedback (2026-06-04, G-9): text in Configuration/Calibration/Filename/Acquire cards looked like it touched the card border. See §9.6. |
| D-14 | **Round spin-button outer corners** — `QSpinBox/QDoubleSpinBox::up-button` gets `border-top-right-radius`, `::down-button` gets `border-bottom-right-radius` = input radius (8 px). | The square spin buttons + full-height `border-left` didn't follow the input's rounded corners → a corner artifact (#1b). See §9.6. |
| D-15 | **Clean IFBW-row structure + grid spacing** — replace the overlapping shared-cell mode widgets with a per-mode **container** swapped by visibility; bump config grid `verticalSpacing` 10 → 14. | The overlapping widgets in the IFBW grid cells collapsed that row's spacing to **0 px** (Points touched IFBW, #1a). See §9.6. |
| D-17 | **IFBW cell must mirror the config grid columns** — the monitor IFBW field should be the same width as Start/Stop (col1). The G-9 `ifbwCell` page used `[label][combo,1][stretch,1]` → combo width `(W−130)/2`, wider than col1's `(W−260)/2`. Fix: give each `ifbwCell` page a `QGridLayout` with the same 4-column structure + stretches as the parent grid. | Live feedback (2026-06-04, G-11): IFBW combo measured 424 px vs Start 345 px — looked "longer"/out of place. See §9.8. |
| D-18 | **Spin buttons get `:hover`/`:pressed` feedback** — add `QSpinBox/QDoubleSpinBox::up/down-button:hover` (lighten) + `:pressed` (accent_dim), mirroring the combo's `::drop-down:pressed`, so clicking a spin arrow feels responsive. | Live feedback (2026-06-04, G-11): spin arrows gave no click feedback unlike the combo drop-down. See §9.8. |
| D-16 | **Layout containers must be transparent** — the global `QWidget { background-color: bg }` paints every layout-only sub-container (`ifbwCell`+pages, `derived` Center/Span, connection `wrap`, cal `sel`/`status`, filename rows, Acquire sub-rows) with the *darker window* colour, creating "dead-zone" bands inside the lighter cards. Fix: **drop `background-color` from the universal `QWidget` rule** and set it on `QMainWindow` instead, so containers default to transparent and the card colour shows through. | Live feedback (2026-06-04, G-10): the IFBW row and the info-text rows (Center/Span, etc.) showed a darker band and the text looked tight to the border. The slate palette (D-10) made the bg/card contrast visible enough to notice. One global change fixes every section. See §9.7. |

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

## 8. Responsive sizing & control-glyph rendering (added 2026-06-04 — gui-spec G-7)

The "flexbox for Qt" layer. Qt has no flexbox, but the same goal — widgets that **flex
between a minimum and maximum** as the window resizes, and a layout whose minimum width
is **not** hostage to one long string — is achieved with three tools: (a) `QSizePolicy`,
(b) explicit `minimum*`/`maximum*` sizes, and (c) **eliding** for arbitrary-length text.
This section is the spec; implementation lands in `theme.py` + the view files under G-7.

> **Why this exists (live testing 2026-06-04):** a finished-run save path
> (`Saved … → D:/…/bloodvessel-t3_monitor_S11_200-250MHz_801pt_300kHz_….csv`) set on the
> plain `saveStatusLabel` grew the window **1080 → 1632 px** (the unbroken string raised
> the layout's minimum width). The `logIntervalInput` combo rendered **"uto"** (the "a" of
> "auto" clipped) because the editable combo had `minimumContentsLength = 0` and the 26 px
> drop-down ate the text region. And every combo/spin showed **no arrow glyph** because the
> QSS styled the drop-down/buttons with `border:none` but never supplied an arrow image.

### 8.1 `SIZE` token group (new in `theme.py`)

```python
SIZE = {
    "label_col_w":    130,   # fixed label column in _labeled() rows (unchanged)
    "input_min_w":     90,   # spin/line-edit never narrower than this
    "combo_min_w":     96,   # combo box minimum width
    "combo_min_chars":  7,   # QComboBox.setMinimumContentsLength(7) → "auto"/"1000" fit
    "field_max_w":    560,   # cap a single input so it can't sprawl on a wide window
    "win_min_w":      880,   # QMainWindow.setMinimumSize — usable floor, not the sizeHint
    "win_min_h":      600,
    "glyph":            6,   # caret triangle half-extent (px) for combo/spin arrows
}
```

### 8.2 `QSizePolicy` convention (per widget role)

| Widget role | Horizontal policy | Vertical | Extra constraints |
|---|---|---|---|
| Spin / line-edit (value field) | `Preferred` | `Fixed` | `setMinimumWidth(SIZE['input_min_w'])`; optional `setMaximumWidth(SIZE['field_max_w'])` so it grows but doesn't sprawl |
| Editable / list combo | `Preferred` | `Fixed` | `setMinimumContentsLength(SIZE['combo_min_chars'])` + `setMinimumWidth(SIZE['combo_min_w'])`; `setSizeAdjustPolicy(AdjustToContents)` |
| Fixed-width label column (`_labeled`) | `Fixed` | `Fixed` | keep `setFixedWidth(SIZE['label_col_w'])` |
| **Arbitrary-length text label** (save status, filename preview, cal source, IDN) | `Ignored` or `Preferred` with `setMinimumWidth(0)` | `Fixed`/`Preferred` | **use `ElidedLabel` (§8.4)** — must shrink, never raise the layout minimum |
| Plot widget | `Expanding` | `Expanding` | already stretches (`addWidget(plot, 1)`) |
| Card / panel `QFrame` | `Preferred`/`Expanding` | `Preferred` | `setMinimumWidth(0)` so a card never forces window growth from a child |

**The cardinal rule (fixes #6):** any widget that can hold content of unbounded length
**must** have `minimumWidth == 0` and elide/wrap. A widget's content width may influence
its *preferred* size but must never become the layout's *minimum*.

### 8.3 Control-glyph QSS (fixes #1 — append to `STYLESHEET`)

Token-colored CSS border-triangles; no image assets, no resource files:

```css
/* combo drop-down caret */
QComboBox::down-arrow {
    image: none; width: 0; height: 0;
    border-left:  {glyph}px solid transparent;
    border-right: {glyph}px solid transparent;
    border-top:   {glyph}px solid {CLR['t2']};
    margin-right: 8px;
}
QComboBox::down-arrow:disabled { border-top-color: {CLR['t4']}; }

/* spin up/down carets (also give the buttons a visible width) */
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 18px; background: {CLR['input']}; border-left: 1px solid {CLR['border']};
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width:0;height:0; border-left:4px solid transparent; border-right:4px solid transparent;
    border-bottom:5px solid {CLR['t2']};
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width:0;height:0; border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {CLR['t2']};
}
```

> **RESOLVED (2026-06-04) — SVG arrows shipped.** Qt's QSS engine does **not** honor
> `transparent` on sub-control borders, so the border-triangle above rendered as a visible
> **dash, not a crisp triangle**. Per user decision we replaced it with tiny **SVG carets**
> (`mvp/assets/{down_arrow,down_arrow_dim,up_arrow}.svg`), referenced by **absolute path**
> computed at import (`_ARROW_DOWN = (Path(__file__).parent/"assets"/"down_arrow.svg").as_posix()`)
> in QSS `image: url("…")` (the path is quoted because the repo path contains spaces). PySide6's
> bundled QtSvg renders them; qt-mcp verified crisp ▼ on every combo and ▲/▼ on every spin box.
> **This supersedes D-7's "asset-free" wording** — the carets are now image assets. The legacy
> `SIZE['glyph']` token is retained but unused.

### 8.4 New factory / component (D-8)

```python
class ElidedLabel(QLabel):
    """QLabel that elides (default Qt.ElideMiddle, ideal for paths) to its current
    width and shows the full text as a tooltip. minimumWidth == 0 so it never widens
    the layout. Use for saveStatusLabel, filenamePreviewLabel, calSourceLabel, idnLabel."""
    def __init__(self, text="", mode=Qt.TextElideMode.ElideMiddle, ...):
        ...
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    def setText(self, text): self._full = text; self.setToolTip(text); self._relayout()
    def resizeEvent(self, e): self._relayout(); super().resizeEvent(e)
    def _relayout(self):
        fm = self.fontMetrics()
        super().setText(fm.elidedText(self._full, self._mode, self.width()))
```

A `field(widget, min_w=None, max_w=None)` helper may also be added to apply the §8.2
policy/min/max to spin/line/combo widgets in one call, keeping the view files declarative.

### 8.5 Window + scroll

`MainWindow`: `setMinimumSize(SIZE['win_min_w'], SIZE['win_min_h'])` — a *usable floor*,
**not** the content `sizeHint` (currently 728×934). The Setup page already wraps its body
in a `QScrollArea` (handles vertical overflow); the responsibility of §8.2/§8.4 is to keep
the **horizontal** minimum bounded so the window obeys the user's width. Acquire page has no
scroll area — its long-text labels (`saveStatusLabel`) are the offenders and become
`ElidedLabel`.

### 8.6 Acceptance (qt-mcp, under G-7)

- `qt_layout_check` reports **no `text_truncated`** on any combo/label at the default size.
- Setting a 200-char path on `saveStatusLabel` does **not** change `qt_list_windows` width.
- `qt_screenshot` shows a visible caret on every combo and spin box.
- Window can be resized down to `win_min_w` without clipping controls; fields flex.

---

## 9. Visual refresh (G-8 — planned, specced 2026-06-04)

User aesthetic feedback after G-7, with locked directions (D-9…D-12). **Spec only — not
implemented.** Four coordinated changes; all in `theme.py` + `view_setup.py` (View layer
only — Model/Presenter/backend untouched).

### 9.1 Two-column Configuration grid (D-9)
Rebuild `view_setup._build_config_card` with a `QGridLayout` (2 columns):

```
row0:  Mode    [ Continuous Monitor                       ▾ ]   ← spans both columns
row1:  Start   [ 200.000 MHz ]        Stop    [ 250.000 MHz ]
row2:  Points  [ 801         ]        Power   [ −5.0 dBm    ]
row3:  IFBW    [ 300 ▾       ]        Center 225 MHz · Span 50 MHz   (monitor mode)
       └ Sanity mode: right column swaps to IFBW-set + Sweeps/IFBW ┘
```
- Wrap each value field in `field()` for the min width + combo min-contents, but **drop the
  `max_w` cap inside the grid** — the two columns already split the width, so fields fill
  their column (balanced, no dead zone). Capping at `field_max_w` here re-introduces a
  ~400 px right gap on a maximized window (as-built finding). Label column stays
  `SIZE['label_col_w']`. (The `max_w` cap is still correct for single-column rows elsewhere.)
- Preserve `_apply_mode_visibility()` — it now toggles the monitor-only vs sanity-only
  *cells* (`ifbwMonitorInput` vs `ifbwListInput`+`numSweepsInput`).
- Apply the same 2-col treatment to Calibration/Filename rows where it reduces dead space.
- This removes the maximized empty-card zone (the G-7 `field_max_w` side effect).

### 9.2 Palette refresh — near-black → medium slate (D-10)
Edit `CLR` in `theme.py`. Candidate values (tune on first render):

| Token | Now | Proposed | Role |
|---|---|---|---|
| `bg` | `#080e1c` | `#121a2b` | window base |
| `panel` | `#0d1628` | `#18223a` | top bars |
| `card` | `#101e36` | `#1e2940` | panels (clearly visible vs bg) |
| `card_raised` | `#142342` | `#25324d` | elevated |
| `card_glow` | `#162848` | `#283a5c` | glow card |
| `input` | `#0f1e38` | `#161f33` | **inset well — darker than card** |
| `border` | `#1e3460` | `#34507e` | stronger definition |
| `border_light` | `#2a4880` | `#44608f` | — |
| `divider` | `#152a50` | `#2a3a5c` | hairlines |
| `t2` | `#8fb4dc` | `#b3cae6` | brighter secondary/labels |
| `t3` | `#4f7099` | `#6b8bb5` | brighter muted |

Accent/green/red/amber + `t1`/`t4` unchanged. Key relationship: **`card` lighter than
`bg`, `input` darker than `card`** → controls read as recessed wells on visible panels.
The `plot` token (`#090f1e`) may lift slightly (`#0e1525`) to match. Because everything is
token-driven (no raw hex in views, D-2), this is a single-file edit.

### 9.3 Field labels — semibold + brighter (D-11)
In `view_setup._labeled()`: `T.label(text, "label", bold=True, color=T.CLR['t1'])` — but
bold (700) reads heavy; prefer a **DemiBold (600)** weight. Add a `font()` option for
weight 600 (`QFont.Weight.DemiBold`) and a `label(..., weight=600)` passthrough, or a
dedicated `field_label()` factory. Color → `t1` (or the new brighter `t2`).

### 9.4 Combo open-state (D-12) — append to `STYLESHEET`  ⚠ sub-controls only
```css
/* DO NOT add `QComboBox:on { border: ... }` — see gotcha below. Restyle sub-controls only. */
QComboBox::drop-down:pressed { background: {CLR['accent_dim']}; }   /* press feedback on the zone */
QComboBox::down-arrow:on     { image: url("{_ARROW_UP}"); }        /* caret flips ▲ when popup open */
```
(`_ARROW_UP` already exists from G-7.) Verify with qt-mcp: open a combo → `qt_screenshot`
shows ▲.

> **Gotcha (hit during G-8 build):** a whole-combo state rule like
> `QComboBox:on { border: 2px solid accent; }` makes **non-editable** combos render with a
> bright **accent fill** at rest — Qt matches `:on` and, with the *background left
> unspecified*, fills it from the palette **Highlight** role (accent). Fix = never restyle
> the whole `QComboBox` for `:on`/`:pressed`; restyle only sub-controls (`::down-arrow:on`,
> `::drop-down:pressed`). The arrow flip is the primary open cue; the existing `:focus`
> border already gives an outline. (No `QComboBox:on::drop-down` either — same fallback risk.)

### 9.6 G-9 micro-polish (follow-up feedback 2026-06-04 — ✅ implemented + qt-mcp-validated)

Four small fixes from a second hands-on pass (all View-layer). **As-built result:** Points↔IFBW
gap restored to 14 px (was 0 px — `pointsInput` bottom 188, `ifbwCell` top ≈ 202); spin-button
corners rounded; Browse-host removed (cal row = dropdown + Recall); cards have ~22 px padding;
save-dir Browse wired (folder picker — `_on_browse_savedir`, not interactively triggered as it's
a native modal dialog). Details:

**(a) Card padding (D-13) — #3 "text touches the border".** `_card_with_header` uses
`contentsMargins(16,14,16,16)`. Add `SIZE['card_pad']` (≈22) and `SIZE['card_pad_v']` (≈18)
and apply `setContentsMargins(card_pad, card_pad_v, card_pad, card_pad)` there **and** in the
Acquire-page cards (`view_acquire`: monitorPanel/sanityPanel/controlCard). Net: readout text
(IDN/Serial/Firmware, Center/Span, Source/Confidence, save status, badges) gets breathing room
from the rounded border.

**(b) Spin-button corner radius (D-14) — #1b.** Validated: the up/down buttons are square with a
full-height `border-left`, while `QSpinBox { border-radius: 8px }` rounds the field — so the
separator/corner doesn't follow the rounding. Append to `STYLESHEET`:
```css
QSpinBox::up-button, QDoubleSpinBox::up-button     { border-top-right-radius: 8px; }
QSpinBox::down-button, QDoubleSpinBox::down-button { border-bottom-right-radius: 8px; }
```
(8 px = the input `border-radius`.) Optionally add `margin: 1px;` so the button sits just inside
the field border.

**(c) IFBW-row spacing (D-15) — #1a.** Validated by geometry: Start→Points gap = 10 px (correct),
but **Points→IFBW = 0 px** — `pointsInput` y=138 h=38 (bottom 176), `ifbwMonitorInput` y=176. Root
cause: row 3 of the config grid stacks the monitor combo, the sanity line-edit, the sweeps spin
and 3 labels in **overlapping shared cells** (toggled by visibility), which collapses the row's
spacing. Fix: build **one `ifbwCell` container** (a `QStackedWidget` or a `QWidget` with a
swapped inner layout) placed in a single grid cell, holding the monitor-vs-sanity controls; toggle
the *container's* inner page in `_apply_mode_visibility`. Then no two widgets share a cell and the
row sits at the normal pitch. Also bump `grid.setVerticalSpacing(10 → 14)`.

**(d) Browse buttons (user decision 2026-06-04).** **Remove** `calBrowseButton` ("Browse host…")
from the Calibration card (redundant — the `calFileInput` dropdown already lists instrument-side
`.sta`; the cal workflow saves `.sta` on the instrument). **Wire** `saveDirButton` ("Browse…") in
the Filename card to a `QFileDialog.getExistingDirectory(...)` that sets `saveDirInput` /
`model.save_data_folder` (presenter slot `_on_browse_savedir`; see ux-spec §6).

### 9.7 G-10 — kill the container "dead zones" (feedback 2026-06-04 — ✅ implemented + qt-mcp-validated)

**As-built:** the global QSS change shipped; qt-mcp confirmed the Setup cards now read as one
uniform surface (no dark band on the IFBW row, Center/Span, connection info, or cal status),
inputs keep their recessed wells, and the Files page + window base render correctly (no
transparency/black regression). Acquire uses the same factories (covered by construction).

**Symptom (both user points share one cause).** Validated via qt-mcp: inside every card, the
plain `QWidget` layout-containers render with the **darker window colour** (`bg #121a2b`) instead
of the card colour (`card #1e2940`), making darker bands — most visible on the **IFBW row**
(`ifbwCell`, #1) and the **Center/Span** row (`derived`), and also the connection **IDN/Serial/
Firmware** block (`wrap`) and the Calibration **radio row** (`sel`) + **Source/Confidence** status
(`status`). The info text then sits on a dark strip near the border (#2).

**Root cause.** The global stylesheet has `QWidget {{ background-color: {{bg}} }}`, which paints
*every* QWidget — including layout-only containers — with `bg`. Cards override via `QFrame#card`,
and inputs via their type rules, but bare containers don't, so they show the darker colour.

**Fix (one change — covers all sections).** In `theme.STYLESHEET`:
```css
/* was: QWidget { background-color: <bg>; color: <t1>; font-size: ... } */
QWidget        { color: <t1>; font-size: <body>; }      /* no universal background */
QMainWindow    { background-color: <bg>; }              /* window paints the base; */
                                                        /* transparent children show it */
```
Now layout containers default to transparent → the **card colour shows through** (no dark
bands), and the existing card padding (`SIZE['card_pad']` = 22, G-9 D-13) gives the space between
the card border and the info text (#2). If a specific info row still feels tight after this,
nudge `card_pad`/that row's margin — but validate first; transparency alone is expected to suffice.

**Why not a card-scoped `QFrame#card > QWidget {{ background: transparent }}`?** The grid's
inputs (spinboxes/combos) are *also* direct children of the card frame, and an id-scoped
`> QWidget` rule outranks their type rules → it would blank the inputs. The global tweak is the
safe, surgical option.

**Verify (qt-mcp, under G-10):** screenshot all three pages (Setup/Acquire/Files) — no darker
rectangle behind the IFBW row, Center/Span, connection info, cal status, filename rows, or the
Acquire badges/option rows; cards read as one uniform surface; inputs, combo popup, message box,
and the save-dir file dialog still have their correct backgrounds (regression check for the global
change).

### 9.8 G-11 — IFBW width alignment + spin-button click feedback (feedback 2026-06-04 — ✅ implemented + qt-mcp-validated)

**As-built:** IFBW combo 424→**352 px** vs Start 345 px — right edges visually aligned (the
residual 7 px is imperceptible; a sub-grid can't reproduce the parent column math to the exact
pixel when col3 is empty vs a field — a `QWidget` spacer in col2 closed all but ~7 px). Spin
hover/pressed QSS applied (no parse warnings; transient state, not screenshot-captured but mirrors
the validated combo `::drop-down:pressed`).

**(a) IFBW combo too wide (D-17) — validated:** `ifbwMonitorInput` = 424 px vs `startFreqInput`
= 345 px. The G-9 monitor page used `[_flabel][combo, stretch1][stretch1]` so the combo got
`(W−130)/2`, while a col1 field gets `(W−260)/2`. **Fix:** rebuild each `ifbwCell` page with a
`QGridLayout` that mirrors the parent config grid — 4 columns, `setColumnStretch(1,1)` +
`setColumnStretch(3,1)`, label column fixed at `SIZE['label_col_w']`:
- monitor page: col0 = "IFBW (kHz)" label, col1 = `ifbwMonitorInput` (cols 2–3 empty).
- sanity page: col0 = "IFBW set (kHz)", col1 = `ifbwListInput`, col2 = "Sweeps / IFBW", col3 = `numSweepsInput`.

Because the page spans the full grid width (cols 0–3) and uses identical column stretches, the
monitor combo in col1 lands at exactly the Start/Stop width. (Still apply `field()` to the inputs.)

**(b) Spin-button click feedback (D-18) — append to `STYLESHEET`:**
```css
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover     {{ background: {CLR['border_light']}; }}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{ background: {CLR['accent_dim']}; }}
```
Mirrors the combo's `::drop-down:pressed` → clicking a spin arrow now lightens (hover) / accents
(press). Applies to every spin box (config + the Acquire duration/query inputs) via the type rules.

**Verify (qt-mcp, under G-11):** `ifbwMonitorInput.width == startFreqInput.width`; hovering/pressing
a spin up/down button changes its background (screenshot during a held press).

### 9.5 Acceptance (qt-mcp, under G-8)
- Maximized: Configuration fills the width with no large empty card zone.
- Labels render semibold + brighter; inputs visibly recessed against lighter panels.
- Opening any combo flips the caret to ▲ and highlights the drop-down zone.
- No raw hex in any view file (palette change is entirely in `theme.py` `CLR`).
- All G-7 acceptance (§8.6) still holds (no truncation, long path doesn't widen window).

---

## 10. References
- Inspected reference: `references/reports/20260602/paod_app/theme.py` (mature system),
  `…/ui.py` (the "before" inline style), `…/patient_page.py`, `…/monitor_page.py` (factory
  consumers), `…/main.py` (apply-once + `QStackedLayout`).
- Port target / seam: `docs/e5063a-gui-spec.md` (§2 port-vs-replace map, §5 phases G-0/G-5).
- Source view being replaced: `code/LibreVNA-dev/gui/mvp/view.py` (PySide6, compiled
  `Ui_MainWindow`, inline QSS — the "old design system" being retired for this port).
- Build-verify loop: `docs/qt-mcp-gui-automation.md`; memory `project-qt-mcp-setup`.

## 11. Changelog
| Date | Change | By |
|------|--------|-----|
| 2026-06-04 | **G-11 implemented + qt-mcp-validated — §9.8, D-17/D-18.** `view_setup.py`: `ifbwCell` pages rebuilt as `QGridLayout`s mirroring the config columns (+ a `QWidget` spacer in monitor col2) → IFBW combo 424→352 px, right edge aligned with Start (345 px). `theme.py`: spin `::up/down-button:hover`/`:pressed` QSS (no parse warnings). | Claude (with Aunuun) |
| 2026-06-04 | **G-11 specced (not implemented) — §9.8, D-17/D-18.** Validated: (a) IFBW combo 424 px > Start 345 px (the G-9 `ifbwCell` monitor page over-widened the combo) → rebuild each page with a `QGridLayout` mirroring the config grid's 4 cols/stretches so the monitor combo == col1 width; (b) spin up/down buttons have no click feedback → add `:hover`/`:pressed` QSS mirroring the combo's `::drop-down:pressed`. | Claude (with Aunuun) |
| 2026-06-04 | **G-10 container dead-zone fix implemented + qt-mcp-validated — §9.7, D-16.** Dropped the universal `QWidget {{background-color}}`; set it on `QMainWindow`. Verified: Setup cards uniform (no dark bands on IFBW/Center-Span/connection-info/cal-status), inputs keep recessed wells, Files page + window base correct (no transparency regression); Acquire covered by shared factories. | Claude (with Aunuun) |
| 2026-06-04 | **G-10 container dead-zone fix specced (not implemented) — §9.7, D-16.** Validated: plain `QWidget` layout-containers inside cards render with the darker window `bg` (global `QWidget{background-color}`), making dark bands on the IFBW row (#1), the Center/Span row, connection info, and cal status (#2). Fix = drop the universal `QWidget` background, set it on `QMainWindow`, so containers go transparent and the card colour shows through; existing 22 px card padding gives the border spacing. One global change covers all sections + both pages. | Claude (with Aunuun) |
| 2026-06-04 | **G-9 micro-polish implemented + qt-mcp-validated — §9.6, D-13…D-15.** `theme.py`: `SIZE` card_pad/card_pad_v/input_radius, spin-button `border-top/bottom-right-radius`. `view_setup.py`: `_card_with_header` padding, config grid verticalSpacing 14, **`ifbwCell` `QStackedWidget`** (replaces the overlapping shared cells → Points↔IFBW gap 0→14 px verified), `calBrowseButton` removed. `view_acquire.py`: panel/control-card padding. `main_window.py`: `saveDirButton`→`_on_browse_savedir` folder picker. Validated: gap 14 px, rounded spin corners, Browse-host gone, more card padding.| Claude (with Aunuun) |
| 2026-06-04 | **G-9 micro-polish specced (not implemented) — §9.6, D-13…D-15.** Second hands-on pass: (a) card padding 16→~22/18 so readout text isn't tight against the rounded border (#3); (b) round spin-button outer corners to the input radius (#1b, validated structurally); (c) fix the **0 px Points↔IFBW gap** (validated by geometry: pointsInput bottom 176 = ifbwMonitorInput top 176) by replacing the overlapping shared-cell mode widgets with one `ifbwCell` container + grid verticalSpacing 10→14 (#1a); (d) per user decision, **remove** the dead `calBrowseButton`, **wire** `saveDirButton` to a folder picker (#2). | Claude (with Aunuun) |
| 2026-06-04 | **Visual refresh G-8 implemented + live-validated (qt-mcp, maximized).** `theme.py`: slate `CLR` palette (D-10), `font()`/`label()` `weight=` param + `field_label()` DemiBold factory (D-11), combo `::down-arrow:on`→▲ + `::drop-down:pressed` (D-12). `view_setup.py`: two-column `QGridLayout` config (D-9) with `_apply_mode_visibility` toggling cell widgets; `_labeled()` uses `field_label`. **Two gotchas fixed (see §9.1/§9.4):** (a) a whole-combo `QComboBox:on {border}` rule made non-editable combos render accent-filled (palette-Highlight fallback) → restyle sub-controls only; (b) keeping the `field_max_w` cap inside the 2-col grid left a ~400 px right gap → dropped the cap in the grid (fields fill their column). Result: balanced two-column form, visible panels, semibold labels, ▲ on open. | Claude (with Aunuun) |
| 2026-06-04 | **Visual refresh specced (G-8 — not implemented).** Post-G-7 aesthetic feedback; user locked four directions → decisions D-9 (two-column Configuration `QGridLayout`, kills the maximized empty-card zone), D-10 ("bigger" palette refresh: near-black → medium slate with visible panels + recessed input wells + stronger borders + brighter `t2`/`t3` — full token before→after in §9.2), D-11 (field labels semibold/DemiBold + brighter), D-12 (combo open-state: `::down-arrow:on` flips to ▲ + `:on`/`::drop-down:pressed` accent highlight). Full §9 with grid layout, palette table, label spec, arrow QSS, qt-mcp acceptance. View-layer only. | Claude (with Aunuun) |
| 2026-06-02 | Doc created. Inspected `paod_app` design pattern (token module + widget factories + objectName-scoped QSS + `setup_plot` + custom painted components). Locked D-1 code-built views, D-2 `theme.py`, D-3 objectName rule, D-4 PyQt5→PySide6 translation, D-5 keep palette. Token tables, factory inventory, port checklist mapped to gui-spec G-0/G-5. | Claude (with Aunuun) |
| 2026-06-04 | **Responsive sizing + control-glyph layer (spec — gui-spec G-7).** Added after live qt-mcp testing surfaced three View-layer gaps: (#1) invisible combo/spin arrows, (#5) clipped combo text ("auto"→"uto"), (#6) a long save-path grew the window 1080→1632 px. New decisions D-6 ("flexbox-for-Qt" `SIZE` tokens + `QSizePolicy` convention), D-7 (token-colored CSS border-triangle carets, asset-free), D-8 (`ElidedLabel` for arbitrary-length text). Full §8: `SIZE` token group, per-role size-policy table, the cardinal "minimumWidth==0 + elide for unbounded text" rule, glyph QSS, `ElidedLabel`/`field()` factories, window min-size, qt-mcp acceptance. | Claude (with Aunuun) |
| 2026-06-04 | **Implemented + live-validated (G-7).** `theme.py`: `SIZE` tokens, glyph QSS (`::down-arrow`, spin `::up/down-arrow`), `ElidedLabel`, `field()` helper, locked-checked checkbox QSS. Applied in `view_setup.py` (config/cal `field()`, `ElidedLabel` for idn/calSource/filenamePreview, "timestamp (always)"+tooltip) and `view_acquire.py` (monitor-control `field()`, `saveStatusLabel`→`ElidedLabel`); `main_window.py` `setMinimumSize(880,600)`. qt-mcp vs `MY54806798`: combo "auto" fits (85→113 px), long path holds window at 1080 px (was 1632). | Claude (with Aunuun) |
| 2026-06-04 | **Arrow glyph → SVG (D-7 revised, §8.3).** The asset-free CSS border-triangle rendered as a dash (Qt ignores `transparent` sub-control borders), so per user decision shipped `mvp/assets/{down_arrow,down_arrow_dim,up_arrow}.svg` and referenced them by absolute-path `image: url("…")` (quoted — repo path has spaces). qt-mcp confirmed crisp ▼ on combos and ▲/▼ on spin boxes. Supersedes the "asset-free" wording in D-7. | Claude (with Aunuun) |
