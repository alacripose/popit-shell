"""Delegated CUA drivers for the Popit toast.

A driver is a named worker with a bounded, declared vocabulary: find a window, capture
it, focus it, move/click, press a key, type text, wait. The toast never calls the
desktop directly; it submits a task to a driver and reads the receipt. The Freebuff chat
window is probed the same way, by a `probe_chat` task assigned to the `cua-chat` driver.

No shell, no file writes outside `runlogs/toast/`, no unbounded loops.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime
import hashlib
import io
import json
import pathlib
import re
import threading
import time
import uuid
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageFilter, ImageGrab, ImageStat

ROOT = pathlib.Path(__file__).resolve().parent
CAPTURES = ROOT / "runlogs" / "toast"
CAPTURES.mkdir(parents=True, exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
PW_RENDERFULLCONTENT = 2
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
DECLARED_ACTIONS = {"capture", "probe_chat", "focus", "move", "click", "key", "type", "wait"}
# A key names one act. The fleet keeps the first task a key produced, so a bridge retry
# after a tunnel flap reads that receipt instead of clicking a second time.
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{7,95}$")


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Refused(Exception):
    def __init__(self, code: str, detail: str = "", **extra) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.extra = extra

    def as_dict(self) -> dict:
        body = {"code": self.code, "detail": self.detail}
        body.update(self.extra)
        return body


def windows() -> list[dict]:
    rows: list[dict] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        if not title.value:
            return True
        rect = wt.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        rows.append({
            "hwnd": int(hwnd),
            "title": title.value,
            "class": _class_name(hwnd),
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
        })
        return True

    user32.EnumWindows(callback, 0)
    return rows


def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_window(title_part: str, *, exact: bool = False) -> dict:
    wanted = title_part.lower()
    for row in windows():
        title = row["title"].lower()
        if (title == wanted) if exact else (wanted in title):
            return row
    raise Refused("window-not-found", title_part, windows=[row["title"] for row in windows()[:12]])


def capture_window(title_part: str, *, exact: bool = False) -> dict:
    row = find_window(title_part, exact=exact)
    hwnd = row["hwnd"]
    left, top, right, bottom = row["rect"]
    width, height = max(1, right - left), max(1, bottom - top)
    image = _print_window(hwnd, width, height)
    if image is None:
        image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    slug = "".join(ch if ch.isalnum() else "-" for ch in title_part.lower())[:32].strip("-")
    path = CAPTURES / f"{slug}-{stamp}.png"
    image.save(path, "PNG")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    _trim(slug, keep=4)
    return {
        "window": row,
        "path": str(path),
        "name": path.name,
        "width": image.width,
        "height": image.height,
        "digest": digest,
        "at": iso(),
    }


def _harness_regions(shot: dict) -> dict:
    """Detect the harness history, working area and textbox from the driver's capture.

    Chromium does not expose this editor through UI Automation here, so the driver reads
    the rendered surface it already captures. The composer is anchored by its bottom-most
    green control (the send button), not by a fixed percentage, so shrinking the Freebuff
    window moves all three regions with it. Crops are kept artifacts; their deltas make a
    new keystroke visible without pretending the inaccessible renderer tree was read.
    """
    source = pathlib.Path(shot["path"])
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    pixels = image.load()
    green_rows: list[int] = []
    for y in range(int(height * 0.82), height):
        count = 0
        for x in range(int(width * 0.35), width, 2):
            r, g, b = pixels[x, y]
            if g > 95 and g > r * 1.18 and g > b * 1.12:
                count += 1
        if count >= 2:
            green_rows.append(y)
    if green_rows:
        anchor = max(green_rows)
        composer_bottom = min(height - 1, anchor + max(8, int(height * 0.035)))
        composer_top = max(int(height * 0.45), anchor - max(64, int(height * 0.13)))
    else:
        # No green control: use the strongest horizontal edge in the lower fifth.
        central = image.crop((int(width * 0.15), 0, int(width * 0.85), height)).convert("L")
        edge = central.filter(ImageFilter.FIND_EDGES)
        rows = []
        for y in range(int(height * 0.78), int(height * 0.96)):
            rows.append((ImageStat.Stat(edge.crop((0, y, edge.width, y + 1))).mean[0], y))
        anchor = max(rows, default=(0, int(height * 0.88)))[1]
        composer_bottom = min(height - 1, anchor + max(8, int(height * 0.035)))
        composer_top = max(int(height * 0.45), anchor - max(64, int(height * 0.13)))
    boxes = {
        "history": (0, max(0, int(height * 0.035)), width, max(1, composer_top - 4)),
        "working": (0, composer_top, width, max(composer_top + 1, height)),
        "textbox": (0, composer_top, width, max(composer_top + 1, composer_bottom)),
    }
    regions = {}
    for name, box in boxes.items():
        crop = image.crop(box)
        target = CAPTURES / f"harness-{name}.png"
        previous = None
        if target.exists():
            try:
                with Image.open(target) as prior:
                    previous = prior.convert("L")
            except OSError:
                previous = None
        crop.save(target, "PNG")
        digest = hashlib.sha256(crop.tobytes()).hexdigest()[:24]
        delta = None
        changed = False
        if previous is not None and previous.size == crop.size:
            difference = ImageChops.difference(previous, crop.convert("L"))
            delta = round(float(ImageStat.Stat(difference).mean[0]), 3)
            # A blinking caret or a repaint is below this; a typed character is not.
            changed = delta >= 0.12
        regions[name] = {"path": str(target), "width": crop.width, "height": crop.height,
                         "box": list(box), "digest": digest, "delta": delta,
                         "changed": changed, "at": shot["at"]}
    return regions


def _trim(slug: str, keep: int) -> None:
    old = sorted(CAPTURES.glob(f"{slug}-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in old[keep:]:
        try:
            path.unlink()
        except OSError:
            pass


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def _print_window(hwnd: int, width: int, height: int) -> Image.Image | None:
    hdc = user32.GetWindowDC(hwnd)
    if not hdc:
        return None
    mem = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    old = gdi32.SelectObject(mem, bitmap)
    try:
        if not user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT):
            return None
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        if not gdi32.GetDIBits(mem, bitmap, 0, height, buffer, ctypes.byref(info), 0):
            return None
        image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1)
        image = image.convert("RGB")
        # A fully black PrintWindow is a refusal, not a probe.
        if image.getbbox() is None:
            return None
        return image
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(hwnd, hdc)


# -- input ------------------------------------------------------------------

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def _send(*inputs: INPUT) -> None:
    array = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT)) != len(inputs):
        raise Refused("input-refused", "SendInput did not consume the event")


def move(x: int, y: int) -> dict:
    if not user32.SetCursorPos(int(x), int(y)):
        raise Refused("move-refused", f"{x},{y}")
    point = wt.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return {"cursor": [point.x, point.y]}


def click(x: int, y: int, *, button: str = "left") -> dict:
    move(x, y)
    down, up = ((MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP) if button == "left"
                else (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP))
    _send(INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, down, 0, None)),
          INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, up, 0, None)))
    return {"clicked": [x, y], "button": button}


KEYS = {
    "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12,
}


def key(name: str) -> dict:
    code = KEYS.get(name.lower())
    if code is None:
        raise Refused("key-not-declared", name, allowed=sorted(KEYS))
    _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(code, 0, 0, 0, None)),
          INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(code, 0, KEYEVENTF_KEYUP, 0, None)))
    return {"key": name}


def type_text(text: str) -> dict:
    if len(text) > 500:
        raise Refused("text-too-long", str(len(text)))
    units = text.encode("utf-16-le")
    for index in range(0, len(units), 2):
        scan = int.from_bytes(units[index:index + 2], "little")
        _send(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE, 0, None)),
              INPUT(type=INPUT_KEYBOARD,
                    ki=KEYBDINPUT(0, scan, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)))
    return {"typed": len(text)}


def focus(title_part: str) -> dict:
    row = find_window(title_part)
    hwnd = row["hwnd"]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return {"focused": row["title"], "hwnd": hwnd}


# -- drivers ----------------------------------------------------------------

@dataclass
class Driver:
    id: str
    role: str
    capabilities: tuple[str, ...] = ("capture", "focus", "move", "click", "key", "type", "wait")
    tasks: int = 0
    last: str = ""


@dataclass
class Task:
    id: str
    driver: str
    actions: list[dict]
    status: str = "queued"
    at: str = field(default_factory=iso)
    finished: str = ""
    results: list[dict] = field(default_factory=list)
    refusal: dict | None = None
    announce: bool = False
    key: str = ""
    _abort: threading.Event = field(default_factory=threading.Event, repr=False)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "driver": self.driver, "status": self.status, "at": self.at,
            "finished": self.finished, "results": self.results, "refusal": self.refusal,
            "actions": len(self.actions), "key": self.key,
        }


class Fleet:
    """Named drivers, each a worker thread; the toast submits tasks and reads receipts."""

    def __init__(self, drivers: int = 4) -> None:
        self.lock = threading.RLock()
        self.tasks: list[Task] = []
        self.by_key: dict[str, str] = {}
        self.on_task = None
        self.drivers = [Driver("cua-chat", "freebuff chat probe")]
        for index in range(1, max(1, drivers)):
            self.drivers.append(Driver(f"cua-{index + 1}", "desktop"))

    def state(self) -> dict:
        with self.lock:
            return {
                "drivers": [
                    {"id": d.id, "role": d.role, "tasks": d.tasks, "last": d.last,
                     "capabilities": list(d.capabilities)}
                    for d in self.drivers
                ],
                "tasks": [t.as_dict() for t in self.tasks[-8:]][::-1],
                "keys": len(self.by_key),
            }

    def submit(self, actions: list[dict], driver_id: str = "", *, announce: bool = False,
               key: str = "") -> dict:
        if not isinstance(actions, list) or not actions:
            raise Refused("actions-empty", "a task needs at least one action")
        if len(actions) > 32:
            raise Refused("actions-too-many", str(len(actions)))
        if key and not KEY_RE.fullmatch(key):
            raise Refused("key-invalid", str(key)[:96])
        unknown = {
            str(item.get("action")) for item in actions
            if not isinstance(item, dict) or item.get("action") not in DECLARED_ACTIONS
        }
        if unknown:
            raise Refused("action-not-declared", ", ".join(sorted(unknown)),
                          allowed=sorted(DECLARED_ACTIONS))
        with self.lock:
            if key and key in self.by_key:
                existing = next((t for t in self.tasks if t.id == self.by_key[key]), None)
                if existing is not None:
                    return {**existing.as_dict(), "replayed": True}
            if driver_id:
                driver = next((d for d in self.drivers if d.id == driver_id), None)
                if driver is None:
                    raise Refused("driver-unknown", driver_id,
                                  drivers=[d.id for d in self.drivers])
            else:
                driver = min(self.drivers, key=lambda d: d.tasks)
            task = Task(id="task-" + uuid.uuid4().hex[:8], driver=driver.id,
                        actions=actions, announce=announce, key=key)
            self.tasks.append(task)
            if key:
                self.by_key[key] = task.id
            driver.tasks += 1
        threading.Thread(target=self._run, args=(task,), daemon=True).start()
        return {**task.as_dict(), "replayed": False}

    def wait(self, task_id: str, timeout: float = 8.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                task = next((t for t in self.tasks if t.id == task_id), None)
                if task and task.status in ("done", "refused"):
                    return task.as_dict()
            time.sleep(0.05)
        raise Refused("task-timeout", task_id)

    def _run(self, task: Task) -> None:
        task.status = "running"
        try:
            for action in task.actions:
                if task._abort.is_set():
                    raise Refused("task-aborted", task.id)
                task.results.append(self._act(action))
            task.status = "done"
        except Refused as error:
            task.status = "refused"
            task.refusal = error.as_dict()
        except Exception as error:  # one bad action cannot kill the fleet
            task.status = "refused"
            task.refusal = {"code": "task-failed", "detail": str(error)}
        finally:
            task.finished = iso()
            with self.lock:
                driver = next((d for d in self.drivers if d.id == task.driver), None)
                if driver:
                    driver.last = task.status + " " + (task.actions[0].get("action", "") if task.actions else "")
                if task.announce and self.on_task:
                    try:
                        self.on_task(task)
                    except Exception:
                        pass  # an announcement cannot fail a completed task

    def _act(self, action: dict) -> dict:
        kind = str(action.get("action") or "")
        if kind == "capture":
            return capture_window(str(action.get("window") or "Freebuff"),
                                  exact=bool(action.get("exact")))
        if kind == "probe_chat":
            shot = capture_window(str(action.get("window") or "Freebuff"),
                                  exact=bool(action.get("exact")))
            shot["kind"] = "chat-probe"
            shot["changed"] = True
            shot["regions"] = _harness_regions(shot)
            shot["textbox"] = shot["regions"]["textbox"]
            return shot
        if kind == "focus":
            return focus(str(action.get("window") or "Freebuff"))
        if kind == "move":
            return move(int(action.get("x", 0)), int(action.get("y", 0)))
        if kind == "click":
            return click(int(action.get("x", 0)), int(action.get("y", 0)),
                         button=str(action.get("button") or "left"))
        if kind == "key":
            return key(str(action.get("key") or "esc"))
        if kind == "type":
            return type_text(str(action.get("text") or ""))
        if kind == "wait":
            ms = max(0, min(5000, int(action.get("ms", 250))))
            time.sleep(ms / 1000)
            return {"waited": ms}
        raise Refused("action-not-declared", kind)

    def probe_freebuff(self, window: str = "Freebuff: The free coding agent") -> dict:
        task = self.submit([{"action": "probe_chat", "window": window}], "cua-chat")
        receipt = self.wait(task["id"], timeout=10)
        if receipt["status"] != "done":
            raise Refused("probe-refused", json.dumps(receipt.get("refusal") or {}))
        return receipt["results"][0]
