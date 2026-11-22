"""Host the Popit shell's view in a frameless window masked to the contour.

The archive application hosts its view the same way (PySide6 QtWebEngine over a
loopback server). The difference is the mask: the window's shape is the measured page
9 contour, so the outline is the framing authority at the window level as well as in
the view's own clip path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 5199

# The corner blend the measured path turns through, in the drawing's own units.
LOOP = (
    (461.43, 634.0), (510.57, 634.0), (525.0, 612.17), (525.0, 537.83),
    (510.57, 516.0), (461.43, 516.0), (447.0, 537.83), (447.0, 612.17),
)

CORNER_BAND_X = 16.38
CORNER_BAND_Y = 23.48
CORNER_LEFT = 445.05
CORNER_RIGHT = 526.95
# The corner's depth along the long rail at the bar's height: one number for the whole
# family, so the window's corner is cut the same as a bar cell whatever its size.
CORNER_UNITS = 21.83
BAR_HEIGHT = 48
CORNER_PX = CORNER_UNITS * BAR_HEIGHT / 121.348


def contour(port: int) -> dict:
    """The contour is read from the window's own server, so there is one source."""
    from urllib.request import urlopen

    with urlopen(f"http://127.0.0.1:{port}/contour.json", timeout=5) as reply:
        return json.loads(reply.read().decode("utf-8"))


PROFILE_END = (
    (461.43, 634.0, 510.57, 634.0),
    (510.57, 634.0, 525.0, 612.17),
    (525.0, 612.17, 525.0, 537.83),
    (525.0, 537.83, 510.57, 516.0),
    (510.57, 516.0, 461.43, 516.0),
    (461.43, 516.0, 447.0, 537.83),
    (447.0, 537.83, 447.0, 612.17),
    (447.0, 612.17, 461.43, 634.0),
)

LOOP = (
    (461.43, 634.0), (510.57, 634.0), (525.0, 612.17), (525.0, 537.83),
    (510.57, 516.0), (461.43, 516.0), (447.0, 537.83), (447.0, 612.17),
)

CORNER_BAND_X = 16.38
CORNER_BAND_Y = 23.48
CORNER_PX = (27.8 * 48) / 121.348
# A window frame uses the accepted family corner, the same numbers a bar button uses.


# The mask sits at the window box itself, never inside the drawn outline: a window's visible edge
# is the antialiased path clip and the frame just inside it, exactly as on a button. A mask that
# followed the drawn curve would replace it with pixel rows and the crown would read flatter.
def contour_region(width: int, height: int, shape: dict, pad: float = 0.0):
    """The same faithful slice the view draws, as a window mask.

    A window frame is the page 9 profile cut at the button's own corner size: the corners
    are scaled by one factor and the rails are extended with their control offsets kept, so
    the mask, the drawn frame and a taskbar cell are one outline at three sizes.
    """
    from PySide6.QtCore import QPointF, QRect
    from PySide6.QtGui import QPainterPath, QRegion

    w, h = float(width), float(height)
    inset = min(pad, w / 6, h / 6)
    box_w = max(2.0, w - 2 * inset)
    box_h = max(2.0, h - 2 * inset)
    scale = min(CORNER_PX / CORNER_BAND_Y,
                box_h / 3 / CORNER_BAND_Y, box_w / 3 / CORNER_BAND_X)
    right = inset + box_w
    bottom = inset + box_h
    corners = {
        "BL": (inset - shape["left"] * scale, bottom - shape["bottom"] * scale),
        "BR": (right - shape["right"] * scale, bottom - shape["bottom"] * scale),
        "TR": (right - shape["right"] * scale, inset - shape["top"] * scale),
        "TL": (inset - shape["left"] * scale, inset - shape["top"] * scale),
    }
    owner = ("BL", "BR", "BR", "TR", "TR", "TL", "TL", "BL")
    loop = []
    for index, point in enumerate(LOOP):
        tx, ty = corners[owner[index]]
        loop.append((point[0] * scale + tx, point[1] * scale + ty))

    path = QPainterPath()
    path.moveTo(*loop[0])
    for i, seg in enumerate(shape["segments"]):
        sx, sy, ex, ey = PROFILE_END[i]
        dsx, dsy = loop[i]
        dex, dey = loop[(i + 1) % len(loop)]
        c1 = (dsx + (seg[0] - sx) * scale, dsy + (seg[1] - sy) * scale)
        c2 = (dex + (seg[2] - ex) * scale, dey + (seg[3] - ey) * scale)
        path.cubicTo(c1[0], c1[1], c2[0], c2[1], dex, dey)
    path.closeSubpath()

    region = QRegion()
    for y in range(int(h)):
        row = y + 0.5

        def filled(x: int) -> bool:
            return path.contains(QPointF(x + 0.5, row))

        if not any(filled(x) for x in (0, int(w) // 2, int(w) - 1)):
            continue
        lo, hi = 0, int(w) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if filled(mid):
                hi = mid
            else:
                lo = mid + 1
        first = lo
        lo, hi = 0, int(w) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if filled(mid):
                lo = mid
            else:
                hi = mid - 1
        last = lo
        if last >= first:
            region = region.united(QRegion(QRect(first, y, last - first + 1, 1)))
    return region


def main() -> int:
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication, QMainWindow

    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    app = QApplication(sys.argv[:1])
    shape = contour(port)

    window = QMainWindow()
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    window.setAttribute(Qt.WA_TranslucentBackground, True)
    window.setWindowTitle("Popit shell")
    view = QWebEngineView(window)
    view.page().setBackgroundColor(Qt.transparent)
    window.setCentralWidget(view)
    width, height = 620, 660
    window.resize(width, height)
    window.setMask(contour_region(width, height, shape))

    screen = QGuiApplication.primaryScreen().availableGeometry()
    window.move(screen.right() - width - 16, max(screen.top() + 16, screen.bottom() - height - 24))
    view.load(QUrl(f"http://127.0.0.1:{port}/"))
    window.show()
    view.setFocus()

    def remask() -> None:
        window.setMask(contour_region(window.width(), window.height(), shape))

    window.resizeEvent = lambda event: (QMainWindow.resizeEvent(window, event), remask())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
