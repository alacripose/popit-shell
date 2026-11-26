"""Keep the toast shell running, and record every exit it survives.

The window is the product; a shell that stops silently is not a state this application allows.
This supervisor runs `toast.py`, appends its output to `runlogs/toast/shell.log`, and when the
child exits it writes the exit code to `runlogs/toast/supervisor.jsonl` and starts it again with
a bounded backoff. It refuses to start a second shell while port 5207 already answers.

Usage:
    python tools/supervise_toast.py            # keep it up
    python tools/supervise_toast.py --once     # run one child, report its exit, stop
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "runlogs" / "toast" / "shell.log"
RECORD = ROOT / "runlogs" / "toast" / "supervisor.jsonl"
PORT = 5207
BACKOFF = (2, 5, 10, 20, 30)


def iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def port_answers() -> bool:
    """True only when something on the shell's port answers, not merely when it is bound."""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1.5):
            return True
    except OSError:
        return False


def record(row: dict) -> None:
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    with RECORD.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": iso(), **row}, ensure_ascii=False) + "\n")


def run_once() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\nsupervisor start {iso()}\n")
        log.flush()
        child = subprocess.Popen([sys.executable, "toast.py"], cwd=str(ROOT),
                                 stdout=log, stderr=subprocess.STDOUT)
        started = time.time()
        try:
            code = child.wait()
        except KeyboardInterrupt:
            child.terminate()
            code = child.wait()
        return code if code is not None else -1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if port_answers():
        print(f"supervisor refused · 127.0.0.1:{PORT} already answers", flush=True)
        record({"event": "refused", "reason": "port-answers"})
        return 2

    attempt = 0
    while True:
        started = time.time()
        record({"event": "start", "attempt": attempt})
        code = run_once()
        uptime = round(time.time() - started, 1)
        record({"event": "exit", "exit": code, "uptime_seconds": uptime})
        print(f"supervisor exit code={code} after {uptime}s", flush=True)
        if args.once:
            return code
        delay = BACKOFF[min(attempt, len(BACKOFF) - 1)]
        attempt += 1
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
