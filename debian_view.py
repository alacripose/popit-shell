"""Live LXDE frame and agent-command channel for the Popit toast.

The Debian desktop the owner watches is `:0` (1024x768, x11vnc backs it). `:99` is the
separate headless CUA display, so it is deliberately not the default here. Frames are
captured with ImageMagick's `import` over the existing WSL restore key and kept in memory;
the command runner uses the same key, as root, with a bounded timeout and a receipt row.
"""
from __future__ import annotations

import datetime
import hashlib
import pathlib
import shlex
import struct
import subprocess
import threading
import time

import hosts

ROOT = pathlib.Path(__file__).resolve().parent
DISTRO = "Debian"
HOST = hosts.debian_host()
KEY = "m0/id_ed25519"
DISPLAY = ":0"
XAUTHORITY = f"/home/{hosts.debian_user()}/.Xauthority"
SCHEMA = "popit.debian-view/1"


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Refused(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def _ssh(remote: str, *, timeout: float = 25.0, binary: bool = False) -> subprocess.CompletedProcess:
    script = (
        "cd /root; PATH=/usr/bin:/bin /usr/bin/ssh -o BatchMode=yes "
        f"-o ConnectTimeout=5 -i {KEY} root@{HOST} {shlex.quote(remote)}"
    )
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "--", "sh", "-c", script],
        capture_output=True, text=not binary, encoding=None if binary else "utf-8",
        errors=None if binary else "replace", timeout=timeout,
        creationflags=0x08000000,
    )


class DebianView:
    def __init__(self, interval: float = 2.0) -> None:
        self.interval = max(0.8, interval)
        self.lock = threading.RLock()
        self.state = "starting"
        self.detail = "opening the Debian desktop"
        self.png: bytes | None = None
        self.capture_ts = 0
        self.width = 0
        self.height = 0
        self.at = ""
        self.last: dict | None = None
        self.runs: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.capture()
            except Exception as error:  # a frame failure is a state, not a dead toast
                with self.lock:
                    self.state = "refused"
                    self.detail = f"capture-failed: {error}"[:300]
            self._stop.wait(self.interval)

    def capture(self) -> dict:
        remote = (
            f"DISPLAY={DISPLAY} XAUTHORITY={XAUTHORITY} "
            "import -window root png:-"
        )
        try:
            result = _ssh(remote, timeout=20, binary=True)
        except subprocess.TimeoutExpired as error:
            raise Refused("desktop-timeout", str(error)) from error
        body = result.stdout or b""
        if result.returncode != 0 or not body.startswith(b"\x89PNG\r\n\x1a\n"):
            detail = (result.stderr or b"").decode("utf-8", "replace").strip()
            detail = detail or f"import exited {result.returncode}"
            with self.lock:
                self.state, self.detail = "refused", detail[:300]
            raise Refused("desktop-capture-refused", detail[:300])
        width, height = struct.unpack(">II", body[16:24])
        digest = hashlib.sha256(body).hexdigest()[:12]
        with self.lock:
            self.png = body
            self.capture_ts = int(time.time() * 1000)
            self.width, self.height = width, height
            self.at, self.state, self.detail = iso(), "live", ""
            self.last = self.last or {}
        return {"ok": True, "width": width, "height": height, "digest": digest}

    def snapshot(self) -> bytes | None:
        with self.lock:
            return self.png

    def run(self, command: str, timeout: float = 30.0) -> dict:
        clean = " ".join(str(command or "").split())
        if not clean:
            raise Refused("command-empty", "a command needs words")
        if len(clean) > 2000:
            raise Refused("command-too-long", str(len(clean)))
        started = time.monotonic()
        try:
            result = _ssh(f"bash -lc {shlex.quote(clean)}", timeout=min(60.0, max(3.0, timeout)))
        except subprocess.TimeoutExpired as error:
            row = {
                "ok": False, "command": clean, "exit": None, "output": "timed out",
                "at": iso(), "seconds": round(time.monotonic() - started, 2),
                "refused": {"code": "command-timeout", "detail": str(error)},
            }
            self._remember(row)
            return row
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if len(output) > 4000:
            output = output[:3990] + "\n…"
        row = {
            "ok": result.returncode == 0,
            "command": clean,
            "exit": result.returncode,
            "output": output or "(no output)",
            "at": iso(),
            "seconds": round(time.monotonic() - started, 2),
        }
        self._remember(row)
        return row

    def _remember(self, row: dict) -> None:
        with self.lock:
            self.last = row
            self.runs = (self.runs + [row])[-8:]

    def state_dict(self) -> dict:
        with self.lock:
            return {
                "schema": SCHEMA,
                "state": self.state,
                "detail": self.detail,
                "display": DISPLAY,
                "capture_ts": self.capture_ts,
                "width": self.width,
                "height": self.height,
                "at": self.at,
                "last": dict(self.last) if self.last else None,
                "runs": list(self.runs),
            }
