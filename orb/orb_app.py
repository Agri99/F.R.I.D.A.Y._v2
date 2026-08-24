import json
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QObject, Slot, QPoint, QUrl, QTimer
from PySide6.QtGui import QIcon, QPixmap, QColor, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebSockets import QWebSocket

HTML_PATH = Path(__file__).parent / "index.html"


class Bridge(QObject):
    def __init__(self, window):
        super().__init__()
        self._window = window

    @Slot(int, int)
    def moveBy(self, dx, dy):
        self._window.move(self._window.pos() + QPoint(dx, dy))

    @Slot()
    def hideWindow(self):
        self._window.hide()

    @Slot()
    def showWindow(self):
        self._window.show()


class OrbCommandClient(QObject):
    """Listen for hide/show commands from the voice process."""

    def __init__(self, orb, toggle_action: QAction):
        super().__init__()
        self._orb = orb
        self._toggle_action = toggle_action
        self._socket = QWebSocket()
        self._socket.textMessageReceived.connect(self._on_message)
        self._socket.disconnected.connect(self._schedule_reconnect)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._connect)
        self._connect()

    def _connect(self):
        self._socket.open(QUrl("ws://127.0.0.1:8765"))

    def _schedule_reconnect(self):
        self._reconnect_timer.start(1000)

    def _on_message(self, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        visibility = data.get("visibility")
        if visibility == "hide":
            self._orb.hide()
            self._toggle_action.setText("Show Orb")
        elif visibility == "show":
            self._orb.show()
            self._orb.raise_()
            self._toggle_action.setText("Hide Orb")


class OrbView(QWebEngineView):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.page().setBackgroundColor(Qt.transparent)
        self.resize(300, 300)

        self.channel = QWebChannel()
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.page().setWebChannel(self.channel)

        self.load(f"file:///{HTML_PATH.as_posix()}")


def _make_tray_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(34, 102, 255))
    return QIcon(pixmap)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    orb = OrbView()
    orb.show()

    tray = QSystemTrayIcon(_make_tray_icon())
    tray.setToolTip("FRIDAY")
    menu = QMenu()

    toggle_action = QAction("Hide Orb")
    def toggle_orb():
        if orb.isVisible():
            orb.hide()
            toggle_action.setText("Show Orb")
        else:
            orb.show()
            toggle_action.setText("Hide Orb")
    toggle_action.triggered.connect(toggle_orb)
    menu.addAction(toggle_action)

    quit_action = QAction("Quit Orb")
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    _command_client = OrbCommandClient(orb, toggle_action)  # keep a reference so it isn't garbage-collected

    sys.exit(app.exec())


if __name__ == "__main__":
    main()