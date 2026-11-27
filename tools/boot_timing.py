#!/usr/bin/env python3
"""Kept probe: which step of `Toast.start()` is the desk standing in?

The desk stopped answering with 5207 and 5211 bound but silent, and it never printed its
own `popit toast http://…` line, so the wait is inside `Toast.start()` between the servers
and the window. This runs the same steps in the same order, times each one and writes a
receipt, so the answer is a measurement rather than a guess.

    python tools/boot_timing.py            # times each step, prints the receipt
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECEIPT = ROOT / "runlogs" / "probes" / "boot-timing.json"


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def timed(step: str, call, rows: list[dict]) -> None:
    started = time.monotonic()
    detail = ""
    try:
        value = call()
        if isinstance(value, (list, tuple, dict)):
            detail = f"{len(value)} rows"
    except Exception as error:  # a refusal is the measurement, not a crash
        detail = f"{type(error).__name__}: {str(error)[:160]}"
    rows.append({"step": step, "seconds": round(time.monotonic() - started, 2),
                 "detail": detail})
    print(f"{step} · {rows[-1]['seconds']}s · {detail}", flush=True)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import toast

    rows: list[dict] = []
    started = time.monotonic()
    desk = toast.Toast()
    rows.append({"step": "construct", "seconds": round(time.monotonic() - started, 2),
                 "detail": ""})
    print(f"construct · {rows[-1]['seconds']}s", flush=True)
    timed("calls.clear_queues", desk.calls.clear_queues, rows)
    timed("archive.repair_hallucinations", desk.archive.repair_hallucinations, rows)
    timed("settings._read_state", desk.settings._read_state, rows)
    timed("settings._subscriptions", desk.settings._subscriptions, rows)
    timed("settings.current", desk.settings.current, rows)
    timed("device_report", toast.settings_package.device_report, rows)
    timed("settings.state", desk.settings.state, rows)
    timed("apps.ensure_all", desk.apps.ensure_all, rows)
    timed("dialin.bootstrap", desk.dialin.bootstrap, rows)
    row = {"schema": "popit.boot-timing/1", "at": iso(), "steps": rows,
           "seconds": round(time.monotonic() - started, 2)}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(row, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
