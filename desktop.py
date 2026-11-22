"""The Windows calls the shell makes directly, kept in one place.

Owning the strip is an AppBar reservation, which is what Explorer's own taskbar does:
the desktop work area shrinks so no window sits under the bar. The launcher and the
bar are Qt windows; this module is only the parts Windows has to answer.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
WM_CLOSE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABE_BOTTOM = 3


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT), ("uEdge", wintypes.UINT),
                ("rc", RECT), ("lParam", wintypes.LPARAM)]


def explorer_bar() -> int:
    return int(user32.FindWindowW("Shell_TrayWnd", None))


def hide_explorer_bar() -> int:
    """Hide Explorer's bar and return its handle so it can be restored."""
    hwnd = explorer_bar()
    if hwnd:
        user32.ShowWindow(hwnd, SW_HIDE)
    return hwnd


def show_explorer_bar(hwnd: int) -> None:
    if hwnd:
        user32.ShowWindow(hwnd, SW_SHOW)


class Strip:
    """The bottom strip, reserved the way a taskbar reserves it."""

    def __init__(self) -> None:
        self.hwnd = 0
        self.reserved = False

    def reserve(self, hwnd: int, height: int) -> tuple[int, int, int, int]:
        """Register the strip and return the rectangle Windows granted for it."""
        data = APPBARDATA()
        data.cbSize = ctypes.sizeof(APPBARDATA)
        data.hWnd = hwnd
        data.uCallbackMessage = 0x0400 + 55
        shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(data))
        self.hwnd = hwnd

        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        data.uEdge = ABE_BOTTOM
        data.rc = RECT(0, screen_h - height, screen_w, screen_h)
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(data))
        # The granted position is what the bar takes; asking twice with the same rect
        # is how an AppBar is told its own size after the query clamped it.
        data.rc = RECT(data.rc.left, data.rc.top, data.rc.right, data.rc.bottom)
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(data))
        self.reserved = True
        return data.rc.left, data.rc.top, data.rc.right, data.rc.bottom

    def release(self) -> None:
        if not self.reserved:
            return
        data = APPBARDATA()
        data.cbSize = ctypes.sizeof(APPBARDATA)
        data.hWnd = self.hwnd
        shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(data))
        self.reserved = False


def _style(hwnd: int) -> int:
    return int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE)) & 0xFFFFFFFF


def windows(exclude: set[int] | None = None) -> list[dict]:
    """Top-level windows a person can name: titled, unowned, not a tool window."""
    skip = exclude or set()
    found: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        handle = int(hwnd)
        if handle in skip or not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, 4) != 0:  # GW_OWNER
            return True
        if _style(handle) & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        found.append({
            "hwnd": handle,
            "title": title.value,
            "minimized": bool(user32.IsIconic(hwnd)),
            "active": handle == int(user32.GetForegroundWindow()),
        })
        return True

    user32.EnumWindows(visit, 0)
    return found


def activate(hwnd: int) -> bool:
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    return bool(user32.SetForegroundWindow(hwnd))


def minimize(hwnd: int) -> None:
    user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE


def close(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def work_area() -> tuple[int, int, int, int]:
    rect = RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


# DWMWA_BORDER_COLOR and its value for no colour. A frameless window still has the
# compositor's one pixel frame on Windows 11, which drew a rectangle around the
# contour; setting the border colour to none leaves the contour as the only frame.
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE


def remove_frame(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
    except OSError:
        return False
    value = ctypes.c_uint(DWMWA_COLOR_NONE)
    result = dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd), ctypes.c_uint(DWMWA_BORDER_COLOR),
        ctypes.byref(value), ctypes.sizeof(value),
    )
    return result == 0
