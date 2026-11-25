"""Serve the Popit shell's view over loopback, with the archive application's own shape.

The session archive window (agent_god_files/tools/archive_window.py) is the pattern:
a loopback ThreadingHTTPServer over a folder, no framework, one JSON API. This server
adds the three things a shell needs: the installed applications, the running windows,
and the actions that start, raise or close them.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import archive
import desktop

ROOT = Path(__file__).resolve().parent
UI = ROOT / "ui"
REFUSALS = ROOT / "logs" / "authority" / "2026-11-22-contour-refusals.jsonl"
PORT = int(os.environ.get("POPIT_PORT", "5199"))
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}

START_MENUS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]


def installed_apps() -> list[dict]:
    """Every Start Menu shortcut, which is the list Windows itself offers."""
    rows: list[dict] = []
    for root in START_MENUS:
        if not root or not root.is_dir():
            continue
        for path in sorted(root.rglob("*.lnk")):
            folder = path.parent.relative_to(root).as_posix()
            rows.append(
                {
                    "label": path.stem,
                    "detail": "" if folder == "." else folder,
                    "target": str(path),
                    "kind": "Installed app",
                }
            )
    rows.sort(key=lambda row: (row["label"].lower(), row["detail"].lower()))
    return rows


def tools() -> list[dict]:
    """The shell's own rows, kept above the applications the way the launcher does."""
    return [
        # A family application started the way every other row starts its target: the Scout Port
        # application is a loopback surface of its own, and this row opens it.
        {
            "label": "Scout Port",
            "detail": "Deadlock Model Forge: the port, its build steps and what is refused",
            "target": os.environ.get(
                "SCOUT_PORT_APP",
                os.path.join(os.environ.get("USERPROFILE", ""), "Documents",
                             "deadlock-model-forge", "popit_apps", "scout_port", "start.cmd"),
            ),
            "kind": "Portal tool",
        },
        {
            "label": "Agent toast",
            "detail": "Pinned CUA drivers probing the Freebuff chat window",
            "target": r"F:\Documents\popit-shell\toast.cmd",
            "kind": "Portal tool",
        },
        {"label": "Session archive", "detail": "Files, evidence and cleanup across every project", "target": "archive", "kind": "Portal tool"},
        {"label": "Reload applications", "detail": "Reads the Start Menu again", "target": "reload", "kind": "Portal tool"},
        {"label": "Close the shell", "detail": "Ends this process", "target": "quit", "kind": "Portal tool"},
    ]


def state() -> dict:
    apps = installed_apps()
    return {"tools": tools(), "apps": apps, "count": len(apps)}


# The launcher's request queue: the view asks, the Qt process acts. One flag is enough
# because the launcher has one state, open or closed.
PENDING = {"launcher": 0, "tray": [], "tray_view": "all", "menu": [], "quit": False, "move": [0, 0], "archive": 0, "archive_move": [0, 0]}
PENDING_LOCK = threading.Lock()


def take_launcher_request() -> int:
    """Return how many launcher toggles were asked for, and clear them."""
    with PENDING_LOCK:
        count = PENDING["launcher"]
        PENDING["launcher"] = 0
        return count


def take_tray_request() -> list[str]:
    """Return the tray views the bar has asked for, in order, and clear them."""
    with PENDING_LOCK:
        views = PENDING["tray"]
        PENDING["tray"] = []
        return views


def take_menu() -> list[dict]:
    """Return the cell menus the bar has asked for, and clear them."""
    with PENDING_LOCK:
        menus = PENDING["menu"]
        PENDING["menu"] = []
        return menus


def take_move() -> tuple[int, int]:
    """Return the drag the view has asked for since the last frame, and clear it."""
    with PENDING_LOCK:
        dx, dy = PENDING["move"]
        PENDING["move"] = [0, 0]
        return int(dx), int(dy)


def request_archive() -> None:
    """Ask the shell to show or hide the session archive window."""
    with PENDING_LOCK:
        PENDING["archive"] += 1


def take_archive_request() -> int:
    with PENDING_LOCK:
        count = PENDING["archive"]
        PENDING["archive"] = 0
        return count


def take_archive_move() -> tuple[int, int]:
    with PENDING_LOCK:
        dx, dy = PENDING["archive_move"]
        PENDING["archive_move"] = [0, 0]
        return int(dx), int(dy)


def quit_requested() -> bool:
    with PENDING_LOCK:
        return bool(PENDING["quit"])


SHELL_READING = {"at": 0.0, "body": None}


def shell_state() -> dict:
    """The notification area's readings and the owner's pinned shortcuts.

    The volume read is a COM round trip, so the answer is reused for a second: the bar
    asks once a poll and nothing in the tray changes faster than that.
    """
    now = time.monotonic()
    if SHELL_READING["body"] is not None and now - SHELL_READING["at"] < 0.9:
        return SHELL_READING["body"]
    with PENDING_LOCK:
        view = PENDING["tray_view"]
    body = {"tray": desktop.tray_state(), "pinned": desktop.pinned_apps(6), "view": view}
    SHELL_READING.update({"at": now, "body": body})
    return body


def start(target: str) -> str:
    if target == "quit":
        with PENDING_LOCK:
            PENDING["quit"] = True
        return "quit"
    if target == "launcher":
        with PENDING_LOCK:
            PENDING["launcher"] += 1
        return "launcher"
    if target == "archive":
        request_archive()
        return "archive"
    if target == "reload":
        return "reload"
    # Windows' own settings pages are not files, and a tray view opens the one it owns.
    if target.startswith("ms-settings:"):
        os.startfile(target)  # noqa: S606 - the owner asked for this page
        return "started"
    if not os.path.exists(target):
        raise FileNotFoundError(target)
    os.startfile(target)  # noqa: S606 - the owner asked for this row to start its app
    return "started"


class Handler(BaseHTTPRequestHandler):
    server_version = "popit-shell/1"

    def log_message(self, fmt: str, *args) -> None:  # the shell's log is its own file
        sys.stderr.write("shell: " + fmt % args + "\n")

    def send_body(self, body: bytes, kind: str, code: int = 200,
                  cache: str = "no-store") -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's name
        path = urlparse(self.path).path
        if path == "/api/state":
            self.send_body(json.dumps(state()).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/windows":
            self.send_body(json.dumps({"windows": desktop.windows()}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/shell":
            self.send_body(json.dumps(shell_state()).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/archive":
            self.send_body(json.dumps(archive.state()).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/archive/files":
            query = parse_qs(urlparse(self.path).query)
            try:
                body = archive.files(query.get("slug", [""])[0])
            except (OSError, ValueError, archive.Refused) as error:
                self.send_body(json.dumps({"ok": False, "refused": str(error)}).encode("utf-8"), TYPES[".json"], 409)
                return
            self.send_body(json.dumps(body).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/icon":
            query = parse_qs(urlparse(self.path).query)
            try:
                hwnd = int(query.get("hwnd", ["0"])[0] or 0)
            except ValueError:
                hwnd = 0
            png = desktop.icon_png(hwnd=hwnd, path=query.get("path", [""])[0])
            if png:
                self.send_body(png, "image/png", cache="max-age=600")
            else:
                self.send_body(b"no icon", "text/plain; charset=utf-8", 404)
            return
        if path == "/contour.json":
            self.send_body((ROOT / "contour.json").read_bytes(), TYPES[".json"])
            return
        if path == "/":
            path = "/index.html"
        file = (UI / path.lstrip("/")).resolve()
        if not file.is_file() or UI not in file.parents:
            self.send_body(b"not found", "text/plain; charset=utf-8", 404)
            return
        self.send_body(file.read_bytes(), TYPES.get(file.suffix, "application/octet-stream"))

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/open":
            self.action(lambda request: start(str(request.get("target", ""))))
            return
        if path == "/api/activate":
            self.action(lambda request: "raised" if desktop.activate(int(request.get("hwnd", 0))) else "refused")
            return
        if path == "/api/minimize":
            desktop.minimize(int(self.read_json().get("hwnd", 0)))
            self.send_body(json.dumps({"ok": True, "result": "minimized"}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/close":
            desktop.close(int(self.read_json().get("hwnd", 0)))
            self.send_body(json.dumps({"ok": True, "result": "closed"}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/move":
            # A drag is a delta, not a position: the window may be off the view's own idea
            # of where it is, and a delta cannot jump it across the screen.
            request = self.read_json()
            with PENDING_LOCK:
                PENDING["move"][0] += int(request.get("dx", 0))
                PENDING["move"][1] += int(request.get("dy", 0))
            self.send_body(json.dumps({"ok": True}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/tray":
            view = str(self.read_json().get("view", "all"))
            with PENDING_LOCK:
                PENDING["tray"].append(view)
                PENDING["tray_view"] = view
            self.send_body(json.dumps({"ok": True, "result": view}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/menu":
            request = self.read_json()
            with PENDING_LOCK:
                PENDING["menu"].append({
                    "kind": str(request.get("kind", "bar")),
                    "hwnd": int(request.get("hwnd", 0)),
                    "target": str(request.get("target", "")),
                    "x": int(request.get("x", 0)),
                    "y": int(request.get("y", 0)),
                })
            self.send_body(json.dumps({"ok": True, "result": "menu"}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/volume":
            self.action(lambda request: "set" if desktop.set_volume(int(request.get("level", 50))) else "refused")
            return
        if path == "/api/mute":
            self.action(lambda request: "set" if desktop.set_mute(bool(request.get("muted", True))) else "refused")
            return
        if path == "/api/showdesktop":
            self.action(lambda request: desktop.show_desktop())
            return
        if path == "/api/taskview":
            self.action(lambda request: desktop.task_view())
            return
        if path == "/api/archive/backup":
            self.action(lambda request: archive.start_backup(
                [str(item) for item in (request.get("slugs") or ([request.get("slug")] if request.get("slug") else []))],
                all_projects=bool(request.get("all")),
                mode=str(request.get("mode") or "evidence"),
            ))
            return
        if path == "/api/archive/clean":
            self.action(lambda request: archive.clean(
                str(request.get("slug", "")), bool(request.get("apply"))
            ))
            return
        if path == "/api/archive/show":
            self.action(lambda request: archive.show(
                str(request.get("slug", "")),
                str(request.get("which") or "project"),
                str(request.get("path") or ""),
            ))
            return
        if path == "/api/archive/rescan":
            archive.ensure_index(force=True)
            self.send_body(json.dumps({"ok": True, "result": "indexing"}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/archive/toggle":
            request_archive()
            self.send_body(json.dumps({"ok": True, "result": "archive"}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/archive/move":
            request = self.read_json()
            with PENDING_LOCK:
                PENDING["archive_move"][0] += int(request.get("dx", 0))
                PENDING["archive_move"][1] += int(request.get("dy", 0))
            self.send_body(json.dumps({"ok": True}).encode("utf-8"), TYPES[".json"])
            return
        if path == "/api/refuse":
            # A surface that is not a nine-slice of the contour is refused by name, and the
            # refusal is recorded, so a rounded rectangle cannot pass as the contour.
            request = self.read_json()
            code = str(request.get("code", "surface-not-nine-slice"))
            row = {
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": "refusal",
                "code": code,
                "surface": str(request.get("surface", "")),
                "observed": "a painted surface was drawn without the contour nine-slice, so it was removed instead of shown",
            }
            REFUSALS.parent.mkdir(parents=True, exist_ok=True)
            with REFUSALS.open("a", encoding="utf-8") as log:
                log.write(json.dumps(row) + "\n")
            answer = {"ok": False, "refused": code}
            self.send_body(json.dumps(answer).encode("utf-8"), TYPES[".json"], 409)
            return
        self.send_body(b"not found", "text/plain; charset=utf-8", 404)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def action(self, run) -> None:
        try:
            result = run(self.read_json())
        except (FileNotFoundError, OSError, ValueError, archive.Refused) as error:
            message = json.dumps({"ok": False, "refused": str(error)}).encode("utf-8")
            self.send_body(message, TYPES[".json"], 409)
            return
        self.send_body(json.dumps({"ok": True, "result": result}).encode("utf-8"), TYPES[".json"])


def main() -> int:
    port = PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"popit-shell serving http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
