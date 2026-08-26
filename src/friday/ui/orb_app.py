"""
src/friday/ui/orb_app.py

WHAT THIS IS FOR:
Hosts the floating 3D WebGL orb visualizer inside a transparent, frameless,
always-on-top PySide6 window with drag-to-move support and WebSocket state sync.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is in sys.path
_src_root = Path(__file__).resolve().parent.parent.parent
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

from PySide6.QtCore import Qt, QUrl, QObject, Slot

from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtGui import QColor


class Bridge(QObject):
    """Exposes window controls to JavaScript inside the Three.js webview."""

    def __init__(self, window: OrbWindow):
        super().__init__()
        self._window = window

    @Slot(int, int)
    def moveBy(self, dx: int, dy: int) -> None:
        self._window.move(self._window.x() + dx, self._window.y() + dy)

    @Slot()
    def hideWindow(self) -> None:
        self._window.hide()

    @Slot()
    def showWindow(self) -> None:
        self._window.show()


class OrbWindow(QWebEngineView):
    """Frameless, transparent, always-on-top window displaying the 3D orb."""

    def __init__(self, html_path: Path):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.page().setBackgroundColor(QColor(0, 0, 0, 0))

        # Size (1.5x bigger: 270x270) and initial position (bottom right corner)
        self.resize(270, 270)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.width() - 310, screen.height() - 310)


        # Connect bridge via WebChannel
        self.channel = QWebChannel(self.page())
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)

        # Load Three.js scene
        self.load(QUrl.fromLocalFile(str(html_path.resolve())))


def main():
    app = QApplication(sys.argv)
    static_dir = Path(__file__).parent / "static" / "index.html"
    if not static_dir.exists():
        print(f"Error: index.html not found at {static_dir}", file=sys.stderr)
        sys.exit(1)

    window = OrbWindow(static_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
