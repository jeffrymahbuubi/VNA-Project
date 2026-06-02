"""qt-mcp smoke-test mockup GUI.

A deliberately tiny PySide6 window whose only purpose is to validate that the
qt-mcp MCP server can see and drive an ena-dev GUI. It is NOT the real E5063A
app — it just exercises the qt-mcp tool surface (snapshot / find_widget /
get_text / click / type / screenshot).

Every interactive widget gets a stable ``setObjectName(...)`` so the agent can
find/click it by name (Playwright-selector style) — the habit the E5063A GUI
should follow from its first commit.

Run (from ``code/``):

    cd ena-dev/gui
    $env:QT_MCP_PROBE=1; uv run python qt_mcp_mockup.py

The ``QT_MCP_PROBE=1`` env var makes the .pth auto-loader install the probe on
127.0.0.1:9142 the moment QApplication is created — no code change needed. The
explicit ``install()`` fallback below is a belt-and-suspenders no-op if the
auto-loader already ran.
"""

from __future__ import annotations

import math
import sys

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MockupWindow(QWidget):
    """Minimal window: a counter button, a text input, an apply button,
    a checkbox, and a status label that reflects every interaction."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MockupMainWindow")
        self.setWindowTitle("qt-mcp Mockup — ena-dev")
        self.resize(420, 480)

        self._click_count = 0

        layout = QVBoxLayout(self)
        layout.setObjectName("main_layout")

        self.title_label = QLabel("qt-mcp smoke test")
        self.title_label.setObjectName("title_label")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        self.click_button = QPushButton("Click me")
        self.click_button.setObjectName("click_button")
        self.click_button.clicked.connect(self._on_click)
        layout.addWidget(self.click_button)

        self.freq_input = QLineEdit()
        self.freq_input.setObjectName("freq_input")
        self.freq_input.setPlaceholderText("Enter a value, e.g. 2.44 GHz")
        layout.addWidget(self.freq_input)

        self.apply_button = QPushButton("Apply value")
        self.apply_button.setObjectName("apply_button")
        self.apply_button.clicked.connect(self._on_apply)
        layout.addWidget(self.apply_button)

        self.enable_checkbox = QCheckBox("Enable feature")
        self.enable_checkbox.setObjectName("enable_checkbox")
        self.enable_checkbox.toggled.connect(self._on_toggle)
        layout.addWidget(self.enable_checkbox)

        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("status_label")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # pyqtgraph PlotWidget — a QGraphicsView. Introspect its scene items
        # with qt_scene_snapshot (a screenshot only proves it rendered; the
        # scene snapshot proves the curve is actually in the scene graph).
        self.s11_plot = pg.PlotWidget()
        self.s11_plot.setObjectName("s11_plot")
        self.s11_plot.setTitle("S11 (mock)")
        self.s11_plot.setLabel("bottom", "Frequency", units="GHz")
        self.s11_plot.setLabel("left", "Magnitude", units="dB")
        # Mock resonance-dip trace so the scene has a real PlotCurveItem.
        freqs = [2.43 + 0.02 * i / 100 for i in range(101)]
        mags = [
            -3.0 - 22.0 * math.exp(-((f - 2.44) ** 2) / (2 * 0.0018 ** 2))
            for f in freqs
        ]
        self.s11_curve = self.s11_plot.plot(freqs, mags, pen=pg.mkPen("y", width=2))
        self.s11_curve.setObjectName("s11_curve")
        layout.addWidget(self.s11_plot)

    def _on_click(self) -> None:
        self._click_count += 1
        self.status_label.setText(f"Button clicked {self._click_count} time(s)")

    def _on_apply(self) -> None:
        value = self.freq_input.text().strip()
        self.status_label.setText(
            f"Applied: {value}" if value else "Applied: (empty)"
        )

    def _on_toggle(self, checked: bool) -> None:
        self.status_label.setText(
            f"Feature {'enabled' if checked else 'disabled'}"
        )


def main() -> int:
    app = QApplication(sys.argv)

    # Belt-and-suspenders: explicitly install the probe in case QT_MCP_PROBE
    # wasn't set. Idempotent no-op if the .pth auto-loader already installed it.
    try:
        from qt_mcp.probe import install

        install()
    except Exception as exc:  # pragma: no cover - probe is optional
        print(f"[qt-mcp] probe not installed ({exc}); GUI runs normally.")

    window = MockupWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
