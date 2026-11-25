#!/usr/bin/env python3
"""Keep the Popit toast, its microphone listener and its axis tunnel alive.

Run this with `pythonw.exe` at logon. It holds one per-user lock, reads the toast's loopback
state, and starts a fresh `toast.py` when the API stops answering. The parent keeps the
receipt in `runlogs/toast/watchdog.log`; it never replaces a live toast.
"""
from __future__ import annotations

import datetime
import json
import msvcrt
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
LOG = ROOT / "runlogs" / "toast" / "watchdog.log"
LOCK = ROOT / "runlogs" / "toast" / "watchdog.lock"
API = "http://127.0.0.1:5207/api/toast"
TOAST = ROOT / "toast.py"
INTERVAL = 15.0


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def log(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{iso()} {line}\n")


def state() -> dict | None:
    try:
        with urllib.request.urlopen(API, timeout=2.5) as reply:
            value = json.loads(reply.read().decode("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def post(path: str, body: dict) -> dict | None:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:5207{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


def pythonw() -> pathlib.Path:
    candidate = pathlib.Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.exists() else pathlib.Path(sys.executable)


def start() -> subprocess.Popen:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    output = (ROOT / "runlogs" / "toast" / "toast.log").open("a", encoding="utf-8")
    process = subprocess.Popen(
        [str(pythonw()), str(TOAST)],
        cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT,
        creationflags=0x08000000, close_fds=True,
    )
    log(f"started toast pid={process.pid}")
    output.close()
    return process


def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lock = LOCK.open("a+")
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        log("watchdog already running; exit")
        return 0
    log(f"watchdog up pid={pathlib.Path(sys.executable).name}")
    child: subprocess.Popen | None = None
    misses = 0
    while True:
        current = state()
        if current:
            misses = 0
            probe = (current.get("probe") or {}).get("state")
            axis = (current.get("axis") or {}).get("state")
            mic = (current.get("mic") or {}).get("state")
            if mic == "refused":
                post("/api/toast/mic", {"on": True})
                log(f"reopened microphone state={mic}")
            log(f"alive probe={probe} axis={axis} mic={mic}")
        else:
            misses += 1
            log(f"toast API absent ({misses})")
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
            child = start()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not state():
                time.sleep(1)
            if state():
                misses = 0
                log("toast API recovered")
            else:
                log("toast did not answer within 20 seconds; retrying")
        time.sleep(INTERVAL if state() else 5)


if __name__ == "__main__":
    raise SystemExit(main())
