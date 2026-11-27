#!/usr/bin/env python3
"""Kept probe: a model's act goes to the Debian body, and a click is refused by name.

The owner's complaint was a Steam installer clicked on the Windows machine while the model
ran on the box. This drives the exact function the model calls (`Toast.delegate_debian`) and
records what each act did: capture and move must land on the Debian loop, and a click must
refuse rather than reach the Windows fleet or be simulated.

    python tools/debian_route_probe.py
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECEIPT = ROOT / "runlogs" / "probes" / "debian-route.json"


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def attempt(desk, name: str, action: dict) -> dict:
    try:
        value = desk.delegate_debian({"actions": [action]})
        return {"act": name, "ok": True, "value": value}
    except Exception as error:  # a refusal is the measurement
        return {"act": name, "ok": False, "code": getattr(error, "code", type(error).__name__),
                "detail": getattr(error, "detail", str(error))[:300]}


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import toast

    desk = toast.Toast()
    rows = [
        attempt(desk, "click", {"action": "click", "x": 40, "y": 40}),
        attempt(desk, "capture", {"action": "capture"}),
        attempt(desk, "move", {"action": "move", "x": 300, "y": 200}),
        attempt(desk, "type", {"action": "type", "text": "steam"}),
    ]
    row = {"schema": "popit.debian-route/1", "at": iso(), "rows": rows}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    for entry in rows:
        print(json.dumps(entry)[:400], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
