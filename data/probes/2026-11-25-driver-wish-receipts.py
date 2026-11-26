#!/usr/bin/env python3
"""Read back what the CUA driver adopted: `/v1/tasks`, `/v1/state` and the wish receipt.

Runs on the driver box. The peer token is read under sudo from the unit's environment and is
never printed or included in the output; only the driver's own task rows and the receipt the
wish script wrote are returned.

    echo <base64> | base64 -d > /tmp/popit_wish_receipts.py
    python3 /tmp/popit_wish_receipts.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import urllib.request

ENV = "/etc/agent/driver.env"
BASE = "http://127.0.0.1:8765"
RECEIPT = pathlib.Path("/srv/scratch/popit-look-wishes.json")


def token() -> str:
    run = subprocess.run(["sudo", "-n", "sed", "-n", "s/^CUA_DRIVER_TOKEN=//p", ENV],
                         capture_output=True, text=True, timeout=30, check=False)
    value = run.stdout.strip().strip('"')
    if not value:
        raise SystemExit("peer token unreadable: " + (run.stderr.strip()[:160] or "empty"))
    return value


def get(path: str) -> dict:
    opened = urllib.request.Request(BASE + path,
                                    headers={"Authorization": "Bearer " + token()})
    with urllib.request.urlopen(opened, timeout=12) as reply:
        return json.loads(reply.read().decode("utf-8"))


def main() -> int:
    payload: dict = {"schema": "popit.driver-wish-readback/1"}
    for name, path in (("tasks", "/v1/tasks"), ("state", "/v1/state")):
        try:
            payload[name] = get(path)
        except Exception as error:  # a refused read is a named fact, not a traceback
            payload[name] = {"error": type(error).__name__, "detail": str(error)[:240]}
    if RECEIPT.exists():
        try:
            payload["receipt"] = json.loads(RECEIPT.read_text(encoding="utf-8"))
        except ValueError as error:
            payload["receipt"] = {"error": "unreadable", "detail": str(error)[:200]}
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
