"""The Windows calls the shell makes directly, kept in one place.

Owning the strip is an AppBar reservation, which is what Explorer's own taskbar does:
the desktop work area shrinks so no window sits under the bar. The launcher and the
bar are Qt windows; this module is only the parts Windows has to answer.
"""

from __future__ import annotations

import ctypes
import os
import re
import tempfile
import threading
from ctypes import wintypes
from pathlib import Path

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
    """Restore Explorer's bar on the work area's bottom edge.

    The strip reservation moved the work area, and Explorer leaves its bar where the
    old edge was, hanging below the screen. Showing it alone is not enough: its
    geometry is put back on the bottom of the work area Windows reports now.
    """
    if not hwnd:
        return
    user32.ShowWindow(hwnd, SW_SHOW)
    work = wintypes.RECT()
    if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0):  # SPI_GETWORKAREA
        return
    here = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(here)):
        return
    height = here.bottom - here.top
    user32.SetWindowPos(hwnd, 0, work.left, work.bottom - height,
                        work.right - work.left, height, 0x0014)  # NOZORDER | NOACTIVATE


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


# ---------------------------------------------------------------------------
# Program pictures: the icon a window's executable owns, streamed to the bar as a
# PNG frame. Windows answers with the same icon the taskbar would draw, so the bar
# carries the program's own mark instead of a name spelled in its cell.

WM_GETICON = 0x007F
ICON_SMALL = 0
ICON_SMALL2 = 2
GCLP_HICONSM = -34
SHGFI_ICON = 0x00000100
SHGFI_SMALLICON = 0x00000001

user32.GetClassLongPtrW.restype = ctypes.c_void_p
shell32.SHGetFileInfoW.restype = ctypes.c_size_t


class SHFILEINFO(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)]


_ICON_PNG: dict[str, bytes] = {}
_ICON_LOCK = threading.Lock()
_GDIPLUS: dict[str, object] = {}
_PNG_CLSID: dict[str, GUID] = {}


def _gdiplus():
    if "token" not in _GDIPLUS:
        library = ctypes.windll.gdiplus
        startup = ctypes.create_string_buffer(24)
        ctypes.memmove(startup, ctypes.byref(ctypes.c_uint32(1)), 4)
        token = ctypes.c_void_p()
        if library.GdiplusStartup(ctypes.byref(token), startup, None) != 0:
            raise OSError("GDI+ did not start")
        _GDIPLUS.update({"token": token, "library": library})
    return _GDIPLUS["library"]


def _png_encoder() -> GUID:
    if "clsid" not in _PNG_CLSID:
        value = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p("{557CF406-1A04-11D3-9A73-0000F81EF32E}"),
                              ctypes.byref(value))
        _PNG_CLSID["clsid"] = value
    return _PNG_CLSID["clsid"]


def _icon_png(hicon: int, key: str) -> bytes | None:
    library = _gdiplus()
    image = ctypes.c_void_p()
    if library.GdipCreateBitmapFromHICON(hicon, ctypes.byref(image)) != 0 or not image:
        return None
    frame = Path(tempfile.gettempdir()) / f"popit-icon-{os.getpid()}-{abs(hash(key))}.png"
    try:
        status = library.GdipSaveImageToFile(image, ctypes.c_wchar_p(str(frame)),
                                             ctypes.byref(_png_encoder()), None)
        if status != 0 or not frame.is_file():
            return None
        return frame.read_bytes()
    finally:
        library.GdipDisposeImage(image)
        try:
            frame.unlink()
        except OSError:
            pass


def process_image(hwnd: int) -> str:
    """The executable behind a window, for the icon fallback."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    buffer = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(len(buffer))
    try:
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def icon_png(hwnd: int = 0, path: str = "") -> bytes | None:
    """One PNG frame of the icon a window or file carries."""
    key = f"h{hwnd}" if hwnd else f"p{path.lower()}"
    with _ICON_LOCK:
        if key in _ICON_PNG:
            return _ICON_PNG[key]
        hicon = 0
        owned = False
        if hwnd:
            hicon = int(user32.SendMessageW(hwnd, WM_GETICON, ICON_SMALL2, 0) or 0)
            if not hicon:
                hicon = int(user32.SendMessageW(hwnd, WM_GETICON, ICON_SMALL, 0) or 0)
            if not hicon:
                hicon = int(user32.GetClassLongPtrW(hwnd, GCLP_HICONSM) or 0)
            if not hicon:
                path = path or process_image(hwnd)
        if not hicon and path and os.path.exists(path):
            info = SHFILEINFO()
            flags = SHGFI_ICON | SHGFI_SMALLICON
            if shell32.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info), flags):
                hicon = int(info.hIcon or 0)
                owned = bool(hicon)
        if not hicon:
            return None
        try:
            data = _icon_png(hicon, key)
        finally:
            if owned:
                user32.DestroyIcon(hicon)
        if data:
            if len(_ICON_PNG) > 128:
                _ICON_PNG.clear()
            _ICON_PNG[key] = data
        return data


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


# ---------------------------------------------------------------------------
# The notification area: what Windows answers about sound, power, the network and
# the shortcuts the owner pinned to its own bar.


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> GUID:
    parts = text.strip("{}").split("-")
    value = GUID()
    value.Data1 = int(parts[0], 16)
    value.Data2 = int(parts[1], 16)
    value.Data3 = int(parts[2], 16)
    for index, byte in enumerate(bytes.fromhex(parts[3] + parts[4])):
        value.Data4[index] = byte
    return value


_CLSID_MMDEVICE = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
_IID_MMDEVICE_ENUM = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
_IID_ENDPOINT_VOLUME = _guid("5CDF2C82-841E-4546-9722-0CF74078229A")
ole32 = ctypes.windll.ole32
kernel32 = ctypes.windll.kernel32


def _com_call(pointer, index: int, restype, *argtypes):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[index])


def _release(pointer) -> None:
    if pointer:
        _com_call(pointer, 2, ctypes.c_ulong)(pointer)


def _endpoint_volume():
    """The default render endpoint's volume interface, or None when COM refuses."""
    try:
        ole32.CoInitializeEx(None, 0x2)  # STA; the bar polls from one thread
    except OSError:
        return None
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        if ole32.CoCreateInstance(ctypes.byref(_CLSID_MMDEVICE), None, 1,
                                  ctypes.byref(_IID_MMDEVICE_ENUM),
                                  ctypes.byref(enumerator)) != 0:
            return None
        if _com_call(enumerator, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int,
                     ctypes.POINTER(ctypes.c_void_p))(
                enumerator, 0, 0, ctypes.byref(device)) != 0:
            return None
        if _com_call(device, 3, ctypes.c_long, ctypes.POINTER(GUID), ctypes.c_uint,
                     ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
                device, ctypes.byref(_IID_ENDPOINT_VOLUME), 0x17, None,
                ctypes.byref(endpoint)) != 0:
            return None
        return endpoint
    finally:
        _release(device)
        _release(enumerator)


def audio() -> dict:
    endpoint = _endpoint_volume()
    if not endpoint:
        return {"volume": None, "muted": False}
    try:
        level = ctypes.c_float(0.0)
        muted = ctypes.c_int(0)
        read = _com_call(endpoint, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_float))(
            endpoint, ctypes.byref(level)) == 0
        _com_call(endpoint, 15, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(
            endpoint, ctypes.byref(muted))
        return {"volume": round(level.value * 100) if read else None, "muted": bool(muted.value)}
    finally:
        _release(endpoint)


def set_volume(level: int) -> bool:
    endpoint = _endpoint_volume()
    if not endpoint:
        return False
    try:
        value = max(0, min(100, int(level))) / 100.0
        return _com_call(endpoint, 7, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)(
            endpoint, ctypes.c_float(value), None) == 0
    finally:
        _release(endpoint)


def set_mute(muted: bool) -> bool:
    endpoint = _endpoint_volume()
    if not endpoint:
        return False
    try:
        return _com_call(endpoint, 14, ctypes.c_long, ctypes.c_int, ctypes.c_void_p)(
            endpoint, ctypes.c_int(1 if muted else 0), None) == 0
    finally:
        _release(endpoint)


class POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


def battery():
    """A desktop has no pack: the cell stays absent instead of showing a zero."""
    status = POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return None
    if status.BatteryLifePercent == 255 or status.BatteryFlag == 128:
        return None
    return {"percent": int(status.BatteryLifePercent), "charging": status.ACLineStatus == 1}


def online() -> bool:
    state = wintypes.DWORD()
    return bool(ctypes.windll.wininet.InternetGetConnectedState(ctypes.byref(state), 0))


def pinned_apps(limit: int = 6) -> list[dict]:
    """The shortcuts the owner pinned to Windows' own bar, read where Windows keeps them."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband",
        ) as key:
            raw, _ = winreg.QueryValueEx(key, "Favorites")
    except OSError:
        return []
    # The value is a shell item list, not plain UTF-16 text: odd-length records shift the
    # alignment, so both offsets are read and the paths are taken from either.
    blob = bytes(raw)
    text = "\n".join(blob[shift:].decode("utf-16-le", "ignore") for shift in (0, 1))
    rows: list[dict] = []
    seen: set[str] = set()
    # A pin is stored as the shortcut's own target (an exe) as often as a .lnk, and only
    # a target that still exists is a pin worth a cell.
    for match in re.finditer(r"[A-Za-z]:\\[^\x00\r\n]{2,}?\.(?:exe|lnk)", text, re.IGNORECASE):
        path = Path(match.group(0))
        if not path.is_file():
            continue
        label = _pin_label(path)
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"label": label, "target": str(path)})
        if len(rows) >= limit:
            break
    return rows


def _pin_label(path: Path) -> str:
    """A pin's name without the version tail a download folder leaves on it."""
    stem = path.stem
    if path.suffix.lower() == ".lnk":
        return stem
    head = re.split(r"-\d|_\d", stem, maxsplit=1)[0]
    return head if len(head) >= 3 else stem


_MINIMIZED: set[int] = set()


def reveal(target: str) -> str:
    """The folder a shortcut lives in, opened where the owner keeps it."""
    path = Path(target)
    folder = path.parent if path.parent.is_dir() else path
    os.startfile(str(folder))  # noqa: S606 - the owner asked for this row's folder
    return str(folder)


def show_desktop() -> str:
    """Toggle the desktop: the first call clears the screen, the next brings it back."""
    global _MINIMIZED
    if _MINIMIZED:
        restored = 0
        for hwnd in list(_MINIMIZED):
            if user32.IsWindow(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE, so a cleared window comes back un-minimized
                restored += 1
        _MINIMIZED = set()
        return f"restored {restored}"
    for row in windows():
        hwnd = row["hwnd"]
        if not row["minimized"]:
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            _MINIMIZED.add(hwnd)
    return f"cleared {len(_MINIMIZED)}"


def task_view() -> str:
    """Win+Tab, which is the Task View Windows itself provides."""
    VK_LWIN, VK_TAB, KEYUP = 0x5B, 0x09, 0x0002
    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(VK_TAB, 0, 0, 0)
    user32.keybd_event(VK_TAB, 0, KEYUP, 0)
    user32.keybd_event(VK_LWIN, 0, KEYUP, 0)
    return "task view"


def tray_state() -> dict:
    sound = audio()
    return {
        "volume": sound["volume"],
        "muted": sound["muted"],
        "online": online(),
        "battery": battery(),
    }
