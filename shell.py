"""Run the Popit shell: the bar that owns the bottom strip, and its launcher.

The server is started in this process, so the view's requests and the Qt windows share
one state. Explorer's own bar is hidden and the strip is reserved as an AppBar, which
is the same reservation Explorer's bar makes, so the work area ends above the bar and
no window hides under it.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import desktop
import server
from window import contour_region

ROOT = Path(__file__).resolve().parent
BAR_HEIGHT = 48
# The launcher's own size is a constant so its placement does not read a height the contour mask
# may change after the window is created.
LAUNCHER_W = 620
LAUNCHER_H = 660


def main() -> int:
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication, QMainWindow

    httpd = ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_port
    shape = json.loads((ROOT / "contour.json").read_text(encoding="utf-8"))

    app = QApplication(sys.argv[:1])
    # The view is edited while the shell runs, so its files are never served from a
    # disk cache: a stale stylesheet reads as a broken frame.
    from PySide6.QtWebEngineCore import QWebEngineProfile

    QWebEngineProfile.defaultProfile().setHttpCacheType(QWebEngineProfile.NoCache)
    screen = QGuiApplication.primaryScreen().availableGeometry()

    def make_window(title: str, width: int, height: int, flags, mask: bool = True) -> QMainWindow:
        window = QMainWindow()
        window.setWindowFlags(flags)
        window.setAttribute(Qt.WA_TranslucentBackground, True)
        window.setWindowTitle(title)
        view = QWebEngineView(window)
        view.page().setBackgroundColor(Qt.transparent)

        # The view's own console goes to the shell's log, so a script that fails inside
        # QtWebEngine is readable instead of an empty frame.
        def console(level, message, line, source) -> None:
            print(f"view[{title}] {source}:{line} {message}", flush=True)

        view.page().javaScriptConsoleMessage = console
        window.setCentralWidget(view)
        window.resize(width, height)
        if mask:
            window.setMask(contour_region(width, height, shape))
        if mask:
            window.resizeEvent = lambda event, w=window: (
                QMainWindow.resizeEvent(w, event),
                w.setMask(contour_region(w.width(), w.height(), shape)),
            )
        return window

    # The strip is the desktop edge itself: one rectangle holding contoured cells, so it
    # is not itself cut to the contour.
    bar = make_window(
        "Popit bar", screen.width(), BAR_HEIGHT,
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint,
        mask=False,
    )
    bar.move(screen.left(), screen.top() + screen.height() - BAR_HEIGHT)
    bar.show()
    desktop.remove_frame(int(bar.winId()))

    launcher = make_window(
        "Popit launcher", LAUNCHER_W, LAUNCHER_H,
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint,
    )
    launcher.move(
        screen.right() - 636,
        max(screen.top() + 16, screen.top() + screen.height() - BAR_HEIGHT - 668),
    )

    # Explorer recreates its bar after it is hidden, so the handle is waited for and
    # the hide is repeated while the shell runs. The strip is reserved only after the
    # real bar is out of the way, because two bars cannot own the same edge.
    tray = 0
    for _ in range(50):
        tray = desktop.explorer_bar()
        if tray:
            break
        time.sleep(0.1)
    desktop.hide_explorer_bar()
    time.sleep(0.4)

    strip = desktop.Strip()
    left, top, right, bottom = strip.reserve(int(bar.winId()), BAR_HEIGHT)
    if bottom - top > 0:
        bar.setGeometry(left, top, right - left, bottom - top)

    # A view that loads before the loopback server answers stays blank forever under the
    # no-cache profile, so the launcher's own load result is remembered and retried.
    loaded = {"launcher": False}

    def launcher_finished(ok: bool) -> None:
        loaded["launcher"] = ok

    launcher.centralWidget().loadFinished.connect(launcher_finished)
    # The launcher opens above the Start button, where the strip's own control is, so it
    # lands where the owner looks for it.
    launcher.setGeometry(left if bottom - top == 0 else 8,
                         max(0, top - LAUNCHER_H - 8),
                         LAUNCHER_W, LAUNCHER_H)
    bar.centralWidget().load(QUrl(f"http://127.0.0.1:{port}/bar.html"))
    launcher.centralWidget().load(QUrl(f"http://127.0.0.1:{port}/?view=launcher"))
    launcher.show()
    desktop.remove_frame(int(launcher.winId()))
    launcher.hide()

    def keep_strip() -> None:
        # Explorer re-shows its bar after a display change or a restart; ours owns the
        # edge, so the real one is hidden again and the reservation is re-stated.
        if desktop.explorer_bar() and desktop.user32.IsWindowVisible(desktop.explorer_bar()):
            desktop.hide_explorer_bar()
        strip.reserve(int(bar.winId()), BAR_HEIGHT)

    def pump() -> None:
        dx, dy = server.take_move()
        if (dx or dy) and launcher.isVisible():
            # A drag may not carry the window off the screen: the header stays reachable.
            here = launcher.pos()
            x = max(80 - LAUNCHER_W, min(here.x() + dx, screen.width() - 80))
            y = max(0, min(here.y() + dy, screen.height() - BAR_HEIGHT - 64))
            launcher.move(x, y)
        for _ in range(server.take_launcher_request()):
            if launcher.isVisible():
                launcher.hide()
            else:
                launcher.show()
                launcher.raise_()
                # A first load can land before the loopback server answers, and a view
                # with no page shows as a black frame: reloading on show is the fix.
                if not loaded["launcher"]:
                    launcher.centralWidget().load(QUrl(f"http://127.0.0.1:{port}/?view=launcher"))
                launcher.centralWidget().setFocus()
        if server.quit_requested():
            app.quit()

    timer = QTimer()
    timer.timeout.connect(pump)
    timer.start(120)

    guard = QTimer()
    guard.timeout.connect(keep_strip)
    guard.start(2500)

    def shutdown() -> None:
        strip.release()
        desktop.show_explorer_bar(tray)
        httpd.shutdown()

    app.aboutToQuit.connect(shutdown)
    print(f"popit-shell bar {screen.width()}x{BAR_HEIGHT}, view on http://127.0.0.1:{port}/", flush=True)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
