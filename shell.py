"""Run the Popit shell: the bar that owns the bottom strip, and its launcher.

The server is started in this process, so the view's requests and the Qt windows share
one state. Explorer's own bar is hidden and the strip is reserved as an AppBar, which
is the same reservation Explorer's bar makes, so the work area ends above the bar and
no window hides under it.
"""

from __future__ import annotations

import hashlib
import json
import ssl
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
TRAY_W = 380
TRAY_H = 340
ARCHIVE_W = 1180
ARCHIVE_H = 760


def main() -> int:
    from PySide6.QtCore import QPoint, Qt, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication, QMainWindow, QMenu

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
    # The strip is the physical screen's bottom row. availableGeometry can already be
    # short by another bar's reservation (Explorer's, or a previous shell still exiting),
    # and reading the bar's edge from it left the strip floating above the screen.
    full = QGuiApplication.primaryScreen().geometry()

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
    bar.move(full.left(), full.top() + full.height() - BAR_HEIGHT)
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
    # Another bar's stale reservation can clamp the answer upward (Explorer's hidden bar
    # kept its edge). The strip is the screen edge itself, so it takes the full bottom
    # row whatever rectangle the reservation was granted, and it says so after the
    # AppBar has had its say, since the granted rectangle can arrive late.
    left, top = full.left(), full.top() + full.height() - BAR_HEIGHT
    right, bottom = full.left() + full.width(), full.top() + full.height()

    def place_bar() -> None:
        bar.setGeometry(left, top, right - left, bottom - top)

    place_bar()
    QTimer.singleShot(300, place_bar)

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

    # The quick settings panel is its own window above the tray: the strip is 48 px tall,
    # so a flyout cannot live inside it.
    tray_panel = make_window(
        "Popit quick settings", TRAY_W, TRAY_H,
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint,
    )
    tray_panel.centralWidget().load(QUrl(f"http://127.0.0.1:{port}/tray.html"))

    # The panel is one window with a view per control, so the bar's cell decides what it
    # shows rather than every control landing on the same plate.
    tray_shown = {"view": "all", "ready": False}

    def apply_tray_view() -> None:
        if not tray_shown["ready"]:
            return
        tray_panel.centralWidget().page().runJavaScript(
            f"window.setView && window.setView({json.dumps(tray_shown['view'])})")

    def tray_loaded(ok: bool) -> None:
        tray_shown["ready"] = bool(ok)
        apply_tray_view()

    tray_panel.centralWidget().loadFinished.connect(tray_loaded)

    def place_tray() -> None:
        tray_panel.setGeometry(
            screen.right() - TRAY_W - 8,
            max(screen.top(), screen.top() + screen.height() - BAR_HEIGHT - TRAY_H - 8),
            TRAY_W, TRAY_H,
        )

    # Placed before it is shown, so the first frame never flashes at the screen's corner.
    place_tray()
    tray_panel.show()
    desktop.remove_frame(int(tray_panel.winId()))
    tray_panel.hide()

    # The session archive is a desk app window: the desk delivers it as
    # `/toast.html?window=archive` over its pinned TLS origin, and this window is the client
    # that shows it. The legacy loopback page is retired, and a window that cannot reach the
    # desk names that refusal instead of drawing a page beside the app.
    desk_window = "https://127.0.0.1:5211/toast.html?window=archive"
    archive_panel = make_window(
        "Popit session archive", ARCHIVE_W, ARCHIVE_H,
        Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint,
    )
    archive_loaded = {"ok": False}
    desk_cert = ROOT / "runlogs" / "toast" / "phone-cert.pem"
    try:
        der = ssl.PEM_cert_to_DER_cert(desk_cert.read_text(encoding="ascii"))
        pinned_desk = hashlib.sha256(bytes(der)).hexdigest() if isinstance(der, bytes) \
            else hashlib.sha256(der.encode("latin-1")).hexdigest()
    except (OSError, ValueError):
        pinned_desk = ""

    def pin_desk_certificate(error) -> None:
        # The desk's window origin is self-signed: the certificate this machine generated is
        # accepted and any other is refused, which is narrower than the platform trust, never
        # wider. No window is loaded over bare http as a fallback.
        digest = ""
        try:
            chain = error.certificateChain()
            digest = hashlib.sha256(bytes(chain[0].toDer())).hexdigest() if chain else ""
        except (AttributeError, TypeError, ValueError):
            digest = ""
        if pinned_desk and digest == pinned_desk:
            try:
                error.acceptCertificate()
            except (AttributeError, RuntimeError):
                pass
            return
        try:
            error.rejectCertificate()
        except (AttributeError, RuntimeError):
            pass

    try:
        archive_panel.centralWidget().page().certificateError.connect(pin_desk_certificate)
    except (AttributeError, TypeError):
        pass

    def archive_finished(ok: bool) -> None:
        archive_loaded["ok"] = bool(ok)
        if not ok:
            archive_panel.centralWidget().setHtml(
                "<!doctype html><meta charset='utf-8'><body style='background:#0c0e11;"
                "color:#e9e2d0;font:14px/1.5 monospace;padding:24px'>"
                "<p>session-archive-unreachable</p>"
                "<p>The desk does not answer on the secure window origin.</p>"
                "<p>python tools/desk_launcher.py</p></body>")

    archive_panel.centralWidget().loadFinished.connect(archive_finished)

    def place_archive() -> None:
        archive_panel.setGeometry(
            max(0, full.left() + (full.width() - ARCHIVE_W) // 2),
            max(0, full.top() + (full.height() - BAR_HEIGHT - ARCHIVE_H) // 2),
            ARCHIVE_W, ARCHIVE_H,
        )

    place_archive()
    archive_panel.centralWidget().load(QUrl(desk_window))
    archive_panel.show()
    desktop.remove_frame(int(archive_panel.winId()))
    archive_panel.hide()

    # A menu is the cell's own: the same window, the same pin and the strip itself each
    # get the actions that belong to them, popped above the strip without blocking the loop.
    # A popped menu is kept here until it hides: Qt does not own a Python QMenu, and one
    # that is only a local is collected before it is ever painted.
    open_menus: list[QMenu] = []

    def show_menu(request: dict) -> None:
        # One cell menu at a time: a second request replaces whatever is still open.
        for previous in list(open_menus):
            previous.close()
        menu = QMenu(bar)
        # The menu is the strip's own palette: ink body, paper text, brass for the row the
        # pointer is on, so it reads as the same family as the cells it came from.
        menu.setStyleSheet(
            "QMenu { background: #0f1113; color: #e6dbc2; border: 1px solid #b08d57; padding: 4px; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: rgba(176, 141, 87, 0.28); color: #d9b779; }"
            "QMenu::separator { height: 1px; background: rgba(176, 141, 87, 0.4); margin: 4px 8px; }"
        )
        kind = str(request.get("kind", "bar"))
        hwnd = int(request.get("hwnd", 0))
        target = str(request.get("target", ""))
        actions: dict[str, object] = {}
        if kind == "window":
            actions["activate"] = menu.addAction("Activate")
            actions["minimize"] = menu.addAction("Minimize")
            menu.addSeparator()
            actions["close"] = menu.addAction("Close")
        elif kind == "pin":
            actions["open"] = menu.addAction("Open")
            actions["reveal"] = menu.addAction("Open containing folder")
        else:
            actions["archive"] = menu.addAction("Session archive")
            actions["taskview"] = menu.addAction("Task view")
            actions["showdesktop"] = menu.addAction("Show desktop")
            menu.addSeparator()
            actions["quit"] = menu.addAction("Close the shell")

        def run(name: str) -> None:
            if name == "activate":
                desktop.activate(hwnd)
            elif name == "minimize":
                desktop.minimize(hwnd)
            elif name == "close":
                desktop.close(hwnd)
            elif name == "open":
                try:
                    desktop.start(target)
                except OSError:
                    pass
            elif name == "reveal":
                try:
                    desktop.reveal(target)
                except OSError:
                    pass
            elif name == "archive":
                server.request_archive()
            elif name == "taskview":
                desktop.task_view()
            elif name == "showdesktop":
                desktop.show_desktop()
            elif name == "quit":
                app.quit()

        for name, action in actions.items():
            action.triggered.connect(lambda _checked=False, chosen=name: run(chosen))

        open_menus.append(menu)

        def forget() -> None:
            if menu in open_menus:
                open_menus.remove(menu)
            menu.deleteLater()

        menu.aboutToHide.connect(forget)
        menu.popup(bar.mapToGlobal(QPoint(int(request.get("x", 0)), int(request.get("y", 0)))))

    def keep_strip() -> None:
        # Explorer re-shows its bar after a display change or a restart; ours owns the
        # edge, so the real one is hidden again and the reservation is re-stated.
        if desktop.explorer_bar() and desktop.user32.IsWindowVisible(desktop.explorer_bar()):
            desktop.hide_explorer_bar()
        strip.reserve(int(bar.winId()), BAR_HEIGHT)
        place_bar()

    def pump() -> None:
        dx, dy = server.take_move()
        if (dx or dy) and launcher.isVisible():
            # A drag may not carry the window off the screen: the header stays reachable.
            here = launcher.pos()
            x = max(80 - LAUNCHER_W, min(here.x() + dx, screen.width() - 80))
            y = max(0, min(here.y() + dy, screen.height() - BAR_HEIGHT - 64))
            launcher.move(x, y)
        adx, ady = server.take_archive_move()
        if (adx or ady) and archive_panel.isVisible():
            # The archive is never parked under the strip: the whole plate stays visible.
            here = archive_panel.pos()
            x = max(full.left(), min(here.x() + adx, full.width() - ARCHIVE_W))
            y = max(full.top(), min(here.y() + ady, full.height() - BAR_HEIGHT - ARCHIVE_H))
            archive_panel.move(x, y)
        for _ in range(server.take_archive_request()):
            if archive_panel.isVisible():
                archive_panel.hide()
            else:
                place_archive()
                archive_panel.show()
                archive_panel.raise_()
                if not archive_loaded["ok"]:
                    archive_panel.centralWidget().load(QUrl(desk_window))
                archive_panel.centralWidget().setFocus()
        for view in server.take_tray_request():
            if tray_panel.isVisible() and tray_shown["view"] == view:
                tray_panel.hide()
            else:
                tray_shown["view"] = view
                place_tray()
                tray_panel.show()
                tray_panel.raise_()
                apply_tray_view()
        for request in server.take_menu():
            show_menu(request)
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
