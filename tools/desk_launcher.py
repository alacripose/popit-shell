#!/usr/bin/env python3
"""The desk's one launch: open the window, or raise the one that is already open.

Owner rule: launches are the launcher's, not a watchdog's. This process is what a pinned
shortcut starts. It never keeps a child on a timer and never replaces a working desk; it
answers "already open" by raising the same window. When nothing answers, it starts exactly
one `toast.py`, waits for the API to answer, and records the receipt in
`runlogs/launcher/launch.json`.

    python tools/desk_launcher.py          # open or raise the desk
    python tools/desk_launcher.py --status # print the receipt and exit
"""
from __future__ import annotations

import ctypes
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECEIPT = ROOT / "runlogs" / "launcher" / "launch.json"
LOG = ROOT / "runlogs" / "launcher" / "launcher.log"
TOAST = ROOT / "toast.py"
API = "http://127.0.0.1:5207/api/toast"
TITLE = "Popit toast"
MUTEX = "PopitDeskLauncher"
# A cold desk signs every package before it answers; the shell log's own runs take about
# ninety seconds. Waiting is the launcher's job, not the owner's.
READY_SECONDS = 120.0
TITLES = ("Popit toast", "Popit agent toast")


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def note(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{iso()} {line}\n")


def answers(timeout: float = 15.0) -> bool:
    """True only when the desk's own route answers, not merely when the port is bound."""
    try:
        with urllib.request.urlopen(API, timeout=timeout) as reply:
            return reply.status == 200
    except (OSError, ValueError, urllib.error.URLError):
        return False


def window_handle() -> int:
    user32 = ctypes.windll.user32
    for title in TITLES:
        handle = int(user32.FindWindowW(None, title) or 0)
        if handle:
            return handle
    return 0


def raise_window() -> int:
    handle = window_handle()
    if not handle:
        return 0
    user32 = ctypes.windll.user32
    user32.ShowWindow(handle, 9)  # SW_RESTORE
    user32.SetForegroundWindow(handle)
    return handle


def pythonw() -> pathlib.Path:
    candidate = pathlib.Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.exists() else pathlib.Path(sys.executable)


def start_desk() -> subprocess.Popen:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    output = (ROOT / "runlogs" / "toast" / "toast.log").open("a", encoding="utf-8")
    process = subprocess.Popen(
        [str(pythonw()), str(TOAST)],
        cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT,
        # DETACHED so the desk outlives this launcher; the launcher is a door, not a leash.
        creationflags=0x08000000 | 0x00000008, close_fds=True,
    )
    output.close()
    return process


def write_receipt(row: dict) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if "--status" in argv:
        try:
            print(RECEIPT.read_text(encoding="utf-8").strip())
            return 0
        except OSError:
            print(json.dumps({"ok": False, "refused": "launcher-never-ran"}))
            return 1

    lock = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX)
    already = ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
    started_at = time.monotonic()
    row = {"schema": "popit.desk-launch/1", "at": iso(), "started": False, "pid": 0,
           "answers": False, "handle": 0, "seconds": 0.0, "refused": ""}
    try:
        if answers():
            row.update({"answers": True, "handle": raise_window()})
        elif already:
            # A second double-click while the first is still starting: wait for its desk.
            row["refused"] = "launcher-already-starting"
            deadline = time.monotonic() + READY_SECONDS
            while time.monotonic() < deadline:
                if answers():
                    row.update({"answers": True, "handle": raise_window(), "refused": ""})
                    break
                time.sleep(1.0)
        else:
            process = start_desk()
            row.update({"started": True, "pid": process.pid})
            note(f"started toast pid={process.pid}")
            deadline = time.monotonic() + READY_SECONDS
            while time.monotonic() < deadline:
                if answers():
                    row.update({"answers": True, "handle": raise_window()})
                    break
                if process.poll() is not None:
                    row["refused"] = f"desk-exited-{process.returncode}"
                    break
                time.sleep(1.0)
            if not row["answers"] and not row["refused"]:
                row["refused"] = "desk-did-not-answer"
            if row["answers"]:
                note(f"desk answered pid={process.pid} in {time.monotonic() - started_at:.1f}s")
            else:
                note(f"desk refused {row['refused']}")
    finally:
        if lock:
            ctypes.windll.kernel32.CloseHandle(lock)
        row["seconds"] = round(time.monotonic() - started_at, 1)
        row["ok"] = bool(row["answers"])
        write_receipt(row)
    print(json.dumps(row, ensure_ascii=False))
    return 0 if row["answers"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
