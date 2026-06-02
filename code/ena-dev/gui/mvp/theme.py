"""theme.py — E5063A Data Collector design system (PySide6).

Token + factory design system ported from `references/reports/20260602/paod_app`
(PyQt5) and translated to PySide6 per docs/e5063a-gui-design-system.md (D-1…D-5).

Rules:
- No raw hex / rgb() / px literal in any *view* file — everything comes from a
  token (CLR/FONT/TOUCH) or a factory here.
- Apply STYLESHEET ONCE at app root: `app.setStyleSheet(theme.STYLESHEET)`.
- Card factories take a `name` so QSS is objectName-scoped AND the widget is
  uniquely findable by qt-mcp (docs/qt-mcp-gui-automation.md).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QGraphicsDropShadowEffect,
    QWidget, QHBoxLayout, QProgressBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPainter, QBrush
import pyqtgraph as pg

# ═══════════════════════════════════════════════════════════
# COLOR PALETTE  (paod_app dark-instrument palette, D-5)
# ═══════════════════════════════════════════════════════════
CLR = {
    "bg":            "#080e1c",
    "panel":         "#0d1628",
    "card":          "#101e36",
    "card_raised":   "#142342",
    "card_glow":     "#162848",
    "input":         "#0f1e38",
    "plot":          "#090f1e",

    "border":        "#1e3460",
    "border_light":  "#2a4880",
    "border_accent": "#3b6fd4",
    "divider":       "#152a50",
    "grid":          "#162040",

    "accent":        "#3b82f6",
    "accent_hover":  "#5096ff",
    "accent_dim":    "#1d4ed8",
    "accent_glow":   "#3b82f640",

    "green":         "#10b981",
    "green_hover":   "#34d399",
    "green_dim":     "#065f46",
    "green_glow":    "#10b98130",
    "red":           "#ef4444",
    "red_hover":     "#f87171",
    "red_dim":       "#7f1d1d",
    "red_glow":      "#ef444430",
    "amber":         "#f59e0b",
    "amber_hover":   "#fbbf24",
    "amber_dim":     "#78350f",
    "amber_glow":    "#f59e0b30",
    "cyan":          "#06b6d4",

    "t1":            "#f0f6ff",   # primary text
    "t2":            "#8fb4dc",   # secondary
    "t3":            "#4f7099",   # muted
    "t4":            "#2d4a6e",   # faint

    # E5063A trace colors (replace PAOD's PPG/ECG set)
    "trace_s11":     "#3b82f6",   # live S11 magnitude  (= accent)
    "trace_phase":   "#f59e0b",   # S11 phase           (= amber)
    "trace_monitor": "#06b6d4",   # min-freq scroller   (= cyan)
}

# ═══════════════════════════════════════════════════════════
# TYPOGRAPHY SCALE  (role → px)
# ═══════════════════════════════════════════════════════════
FONT = {
    "display":  30,
    "title":    24,
    "section":  17,
    "label":    14,
    "body":     13,
    "small":    12,
    "tiny":     10,
    "btn":      14,
    "btn_sm":   12,
    "timer":    24,
    "verdict":  26,
    "plot_lbl": 11,
    "mono":     12,
}

# ═══════════════════════════════════════════════════════════
# SIZING TOKENS  (desktop-retuned from paod_app's 800×480 RPi values, §2.3)
# ═══════════════════════════════════════════════════════════
TOUCH = {
    "btn_h":     40,
    "btn_sm_h":  32,
    "input_h":   36,
    "combo_h":   34,
    "min_touch": 36,
}

# ═══════════════════════════════════════════════════════════
# GLOBAL STYLESHEET  (built once from tokens, applied at app root)
# ═══════════════════════════════════════════════════════════
STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Noto Sans', 'Roboto', sans-serif;
    outline: none;
}}
QWidget {{
    background-color: {CLR['bg']};
    color: {CLR['t1']};
    font-size: {FONT['body']}px;
}}
QLabel {{
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
}}
QFrame QLabel {{ border: none; background: transparent; }}

QLineEdit, QDoubleSpinBox, QSpinBox {{
    background-color: {CLR['input']};
    border: 1.5px solid {CLR['border']};
    border-radius: 8px;
    padding: 6px 12px;
    color: {CLR['t1']};
    font-size: {FONT['label']}px;
    selection-background-color: {CLR['accent']};
    min-height: {TOUCH['input_h'] - 14}px;
}}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 2px solid {CLR['accent']};
    background-color: #111f3a;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 18px; border: none; }}

QComboBox {{
    background-color: {CLR['input']};
    border: 1.5px solid {CLR['border']};
    border-radius: 8px;
    padding: 5px 12px;
    color: {CLR['t1']};
    font-size: {FONT['label']}px;
    min-height: {TOUCH['combo_h'] - 12}px;
}}
QComboBox:focus {{ border: 2px solid {CLR['accent']}; }}
QComboBox::drop-down {{ border: none; width: 26px; border-left: 1px solid {CLR['border']}; }}
QComboBox QAbstractItemView {{
    background-color: {CLR['card_raised']};
    border: 1px solid {CLR['border_light']};
    color: {CLR['t1']};
    selection-background-color: {CLR['accent_dim']};
    padding: 4px;
}}

QCheckBox {{ color: {CLR['t2']}; spacing: 8px; font-size: {FONT['label']}px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1.5px solid {CLR['border_light']}; background: {CLR['input']};
}}
QCheckBox::indicator:checked {{ background: {CLR['accent']}; border-color: {CLR['accent']}; }}
QCheckBox::indicator:disabled {{ border-color: {CLR['border']}; background: {CLR['card']}; }}

QRadioButton {{ color: {CLR['t2']}; spacing: 8px; font-size: {FONT['label']}px; }}
QRadioButton::indicator {{
    width: 16px; height: 16px; border-radius: 8px;
    border: 1.5px solid {CLR['border_light']}; background: {CLR['input']};
}}
QRadioButton::indicator:checked {{ background: {CLR['accent']}; border-color: {CLR['accent']}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {CLR['bg']}; width: 8px; border-radius: 4px; }}
QScrollBar::handle:vertical {{ background: {CLR['border_light']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QTableWidget {{
    background-color: {CLR['card']};
    border: 1px solid {CLR['border']};
    border-radius: 8px;
    gridline-color: {CLR['divider']};
    color: {CLR['t1']};
    font-size: {FONT['small']}px;
}}
QHeaderView::section {{
    background-color: {CLR['card_raised']};
    color: {CLR['t2']};
    border: none;
    border-bottom: 1px solid {CLR['border']};
    padding: 5px;
    font-weight: 600;
}}

QProgressBar {{
    background-color: {CLR['card']};
    border: 1px solid {CLR['border']};
    border-radius: 4px;
    text-align: center;
    color: transparent;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {CLR['accent_dim']}, stop:1 {CLR['accent']});
    border-radius: 3px;
}}

QMessageBox {{ background-color: {CLR['card_raised']}; }}
QMessageBox QLabel {{ color: {CLR['t1']}; font-size: {FONT['label']}px; }}
QMessageBox QPushButton {{
    background-color: {CLR['accent']}; color: white; border-radius: 8px;
    padding: 8px 24px; font-weight: bold; min-height: 32px; min-width: 80px;
}}
QMessageBox QPushButton:hover {{ background-color: {CLR['accent_hover']}; }}
"""


# ═══════════════════════════════════════════════════════════
# FONT / LABEL FACTORIES
# ═══════════════════════════════════════════════════════════
def font(size_key="label", bold=False, italic=False) -> QFont:
    sz = FONT.get(size_key, size_key) if isinstance(size_key, str) else size_key
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    f = QFont("Segoe UI", sz, weight)
    if italic:
        f.setItalic(True)
    return f


def label(text, size_key="label", bold=False, color=None, italic=False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(font(size_key, bold, italic))
    c = color or CLR['t1']
    lbl.setStyleSheet(f"color:{c};background:transparent;border:none;padding:0;")
    return lbl


# ═══════════════════════════════════════════════════════════
# BUTTON FACTORIES
# ═══════════════════════════════════════════════════════════
def _btn_style(bg, hover, text_color="white", radius=8, font_size=None) -> str:
    fs = font_size or FONT['btn']
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {text_color};
            border: none;
            border-radius: {radius}px;
            font-weight: 700;
            font-size: {fs}px;
            padding: 0 18px;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
        QPushButton:pressed {{ padding-top: 2px; background-color: {bg}; }}
        QPushButton:disabled {{ background-color: {CLR['card']}; color: {CLR['t4']}; }}
    """


def button(text, bg=None, hover=None, min_w=110, h=None, size_key="btn") -> QPushButton:
    bg = bg or CLR['accent']
    hover = hover or CLR['accent_hover']
    h = h or TOUCH['btn_h']
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setMinimumWidth(min_w)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(font(size_key, bold=True))
    b.setStyleSheet(_btn_style(bg, hover, font_size=FONT.get(size_key, 14)))
    sh = QGraphicsDropShadowEffect()
    sh.setColor(QColor(0, 0, 0, 110))
    sh.setBlurRadius(16)
    sh.setOffset(0, 3)
    b.setGraphicsEffect(sh)
    return b


def button_sm(text, bg=None, hover=None, min_w=72, h=None) -> QPushButton:
    bg = bg or CLR['card_raised']
    hover = hover or CLR['border_light']
    h = h or TOUCH['btn_sm_h']
    b = QPushButton(text)
    b.setFixedHeight(h)
    b.setMinimumWidth(min_w)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(font("btn_sm", bold=True))
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: {bg};
            color: {CLR['t2']};
            border: 1.5px solid {CLR['border_light']};
            border-radius: 7px;
            font-weight: 600;
            font-size: {FONT['btn_sm']}px;
            padding: 0 12px;
        }}
        QPushButton:hover {{ background-color: {hover}; color: {CLR['t1']}; border-color: {CLR['accent']}; }}
        QPushButton:pressed {{ padding-top: 1px; }}
        QPushButton:disabled {{ color: {CLR['t4']}; border-color: {CLR['border']}; }}
    """)
    return b


def button_danger(text, min_w=110, h=None) -> QPushButton:
    return button(text, CLR['red'], CLR['red_hover'], min_w, h)


def button_success(text, min_w=110, h=None) -> QPushButton:
    return button(text, CLR['green'], CLR['green_hover'], min_w, h)


# ═══════════════════════════════════════════════════════════
# CARD / PANEL FACTORIES  (name-scoped QSS → unique objectName for qt-mcp)
# ═══════════════════════════════════════════════════════════
def card(name="card", radius=12, glow=False) -> QFrame:
    f = QFrame()
    f.setObjectName(name)
    border_color = CLR['border_accent'] if glow else CLR['border']
    bg_color = CLR['card_glow'] if glow else CLR['card']
    f.setStyleSheet(f"""
        QFrame#{name} {{
            background-color: {bg_color};
            border: 1.5px solid {border_color};
            border-radius: {radius}px;
        }}
        QFrame#{name} QLabel {{ border: none; background: transparent; }}
    """)
    if glow:
        sh = QGraphicsDropShadowEffect()
        sh.setColor(QColor(CLR['accent']))
        sh.setBlurRadius(22)
        sh.setOffset(0, 2)
        f.setGraphicsEffect(sh)
    return f


def card_raised(name="cardR", radius=12) -> QFrame:
    f = QFrame()
    f.setObjectName(name)
    f.setStyleSheet(f"""
        QFrame#{name} {{
            background-color: {CLR['card_raised']};
            border: 1.5px solid {CLR['border_light']};
            border-radius: {radius}px;
        }}
        QFrame#{name} QLabel {{ border: none; background: transparent; }}
    """)
    sh = QGraphicsDropShadowEffect()
    sh.setColor(QColor(0, 0, 0, 160))
    sh.setBlurRadius(18)
    sh.setOffset(0, 4)
    f.setGraphicsEffect(sh)
    return f


def card_status(name="cardS", color_key="accent", radius=12) -> QFrame:
    bg_map = {
        "green":  ("#0d2119", CLR['green']),
        "red":    ("#200d10", CLR['red']),
        "accent": ("#0e1e38", CLR['accent']),
        "amber":  ("#201508", CLR['amber']),
    }
    bg, border = bg_map.get(color_key, bg_map["accent"])
    f = QFrame()
    f.setObjectName(name)
    f.setStyleSheet(f"""
        QFrame#{name} {{
            background-color: {bg};
            border: 2px solid {border}60;
            border-radius: {radius}px;
        }}
        QFrame#{name} QLabel {{ border: none; background: transparent; }}
    """)
    return f


# ═══════════════════════════════════════════════════════════
# SEPARATORS / SECTION HEADER / PROGRESS
# ═══════════════════════════════════════════════════════════
def separator_h(opacity="80") -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(
        f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 transparent,stop:0.3 {CLR['divider']}{opacity},"
        f"stop:0.7 {CLR['divider']}{opacity},stop:1 transparent);border:none;"
    )
    return line


def separator_v(h=24) -> QFrame:
    line = QFrame()
    line.setFixedWidth(1)
    line.setFixedHeight(h)
    line.setStyleSheet(f"background:{CLR['divider']};border:none;")
    return line


def section_header(text, color=None) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background:transparent;border:none;")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    bar = QFrame()
    bar.setFixedWidth(3)
    bar.setFixedHeight(15)
    bar.setStyleSheet(f"background:{color or CLR['accent']};border-radius:2px;border:none;")
    row.addWidget(bar)
    row.addWidget(label(text, "section", bold=True, color=CLR['t2']))
    row.addStretch()
    return w


def progress_bar() -> QProgressBar:
    pb = QProgressBar()
    pb.setRange(0, 100)
    pb.setValue(0)
    pb.setFixedHeight(6)
    pb.setTextVisible(False)
    return pb


# ═══════════════════════════════════════════════════════════
# PYQTGRAPH PLOT SETUP  (single source for both plots — design-system §3)
# ═══════════════════════════════════════════════════════════
def setup_plot(pw, y_range=(-60.0, 5.0)):
    pw.setBackground(CLR['plot'])
    pi = pw.getPlotItem()
    for axis_name in ('bottom', 'left'):
        ax = pi.getAxis(axis_name)
        ax.setPen(pg.mkPen(CLR['border'], width=0.8))
        ax.setTextPen(pg.mkPen(CLR['t3']))
        ax.setStyle(tickFont=font("tiny"), tickLength=-5)
    pw.showGrid(x=True, y=True, alpha=0.15)
    pw.setMenuEnabled(False)
    pw.hideButtons()
    vb = pw.getViewBox()
    vb.setBackgroundColor(CLR['plot'])
    vb.setBorder(pg.mkPen(CLR['border'], width=0.8))
    if y_range is not None:
        pw.setYRange(*y_range)
        pw.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
    pw.setClipToView(True)
    pw.setDownsampling(auto=True, mode='peak')
    return pw


# ═══════════════════════════════════════════════════════════
# CUSTOM PAINTED COMPONENTS
# ═══════════════════════════════════════════════════════════
class StatusDot(QWidget):
    """Glowing status indicator. green=ok, amber=busy, red=error, grey=idle."""

    def __init__(self, color=None, size=10, parent=None):
        super().__init__(parent)
        self._color = QColor(color or CLR['t3'])
        self._size = size
        self.setFixedSize(size + 8, size + 8)

    def set_color(self, c):
        self._color = QColor(c)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        g = QColor(self._color); g.setAlpha(35)
        p.setBrush(QBrush(g)); p.drawEllipse(0, 0, self._size + 8, self._size + 8)
        g2 = QColor(self._color); g2.setAlpha(70)
        p.setBrush(QBrush(g2)); p.drawEllipse(2, 2, self._size + 4, self._size + 4)
        p.setBrush(QBrush(self._color)); p.drawEllipse(4, 4, self._size, self._size)
        p.end()


class MetricBadge(QWidget):
    """name → value → ref row, for live readouts."""

    def __init__(self, name, value="—", ref="", val_color=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._name_lbl = label(name, "body", color=CLR['t3'])
        self._value_lbl = label(value, "body", bold=True, color=val_color or CLR['t1'])
        self._ref_lbl = label(ref, "small", color=CLR['t4'])
        row.addWidget(self._name_lbl)
        row.addStretch()
        row.addWidget(self._value_lbl)
        row.addWidget(self._ref_lbl)

    def set_value(self, value, color=None):
        self._value_lbl.setText(str(value))
        if color:
            self._value_lbl.setStyleSheet(f"color:{color};background:transparent;border:none;")

    def set_ref(self, ref):
        self._ref_lbl.setText(str(ref))


class TopBar(QWidget):
    """Gradient header: status dot + title + optional right widget."""

    def __init__(self, title, dot_color=None, right_widget=None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {CLR['panel']},stop:1 {CLR['bg']});border:none;"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)
        self.dot = StatusDot(dot_color or CLR['t3'], size=9)
        row.addWidget(self.dot)
        self.title_lbl = label(title, "section", bold=True)
        row.addWidget(self.title_lbl)
        row.addStretch()
        if right_widget:
            row.addWidget(right_widget)

    def set_dot_color(self, c):
        self.dot.set_color(c)

    def set_title(self, t):
        self.title_lbl.setText(t)


def pill_badge(text, bg, text_color="white") -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(font("small", bold=True))
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(f"background:{bg};color:{text_color};border-radius:10px;padding:2px 10px;border:none;")
    lbl.setFixedHeight(20)
    return lbl
