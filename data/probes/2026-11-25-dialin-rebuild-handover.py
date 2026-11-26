#!/usr/bin/env python3
"""Hand the dialin rebuild to the CUA driver: dialin is not to be hand-rolled any more.

The owner, verbatim: *"the expectation was that the dialin would stop being handrolled in it's
entirety and the cua drivers would take ver the work to rebuild the application from the
settings app package"*.

This runs **on the driver box** (the shell's `tools/bridge.py run` path), not on the Windows
desk. It sends one `read` wish over the driver's own wire. The wish carries no body tool and no
authority: `receive_wish` adopts `status|read|question` as a peer task and never executes one,
so the rebuild is the driver's own work with its own tools, not an agent act behind a wish.

Why a wish and not an agent patch: the desk's palette table (`POPIT_THEMES`, `themePaint`,
`paintTheme`), its private keyframes and its own settings panel are the hand-rolled surface. The
settings app package is the baseline; a rebuild derives the window from it instead of copying it.
Patching the private copies again would deepen the thing the owner is retiring.

    echo <base64> | base64 -d > /tmp/popit_dialin_rebuild.py
    python3 /tmp/popit_dialin_rebuild.py

Receipt on the box: `/srv/scratch/popit-dialin-rebuild.json`.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import subprocess
import urllib.request

ENV = pathlib.Path("/etc/agent/driver.env")
NODE = "http://127.0.0.1:8765/v1/wishes"
# The desk's address on this network is a local fact of the box, not a constant in a record:
# it is read from the environment or from the box's own `/etc/agent/driver.env`.
ORIGIN = os.environ.get("POPIT_ORIGIN") or ""
RECEIPT = pathlib.Path("/srv/scratch/popit-dialin-rebuild.json")
SENDER = "popit-shell session (freebuff agent)"
SCOPE = "popit-shell/ui/toast.* · the dialin rebuild"

REQUEST = (
    "Rebuild the dialin window from the signed settings app package (popit-settings). The "
    "owner retired the hand-rolled desk: dialin must stop carrying its own palette table, its "
    "own motion keyframes, its own settings panel implementation and its own layout, and must "
    "paint only what the settings package publishes — frame, material, motion type, motion "
    "preference, the ten colour roles, per-app layout and DPI — through the shared sheets "
    "(contour-theme.css, package.js) and the window's declared regions (bar, status, body, "
    "foot). The desk stays a signed `window` package: app-dialin@<rev> with its files listed, "
    "served over the desk's own HTTPS origin and audited before it is signed. Name every finding "
    "with its code, deliver the rebuilt files with their digests, and write the receipt on this "
    "box naming what was replaced."
)

EXPECTED = ["dialin-handrolled", "dialin-private-palette", "dialin-private-motion",
            "dialin-private-settings-panel", "dialin-not-derived", "dialin-audit-pending"]


def origin() -> str:
    """The desk origin, refused by name when neither the environment nor the box names one."""
    if ORIGIN:
        return ORIGIN
    run = subprocess.run(["sudo", "-n", "sed", "-n", "s/^POPIT_ORIGIN=//p", str(ENV)],
                         capture_output=True, text=True, timeout=30, check=False)
    value = run.stdout.strip().strip('"')
    if not value:
        raise SystemExit("POPIT_ORIGIN is not set here and driver.env does not name it: "
                         + (run.stderr.strip()[:200] or "empty"))
    return value


def token() -> str:
    """The peer token, read on the box under sudo and never printed."""
    run = subprocess.run(["sudo", "-n", "sed", "-n", "s/^CUA_DRIVER_TOKEN=//p", str(ENV)],
                         capture_output=True, text=True, timeout=30, check=False)
    value = run.stdout.strip().strip('"')
    if not value:
        raise SystemExit("CUA_DRIVER_TOKEN could not be read on the box: "
                         + (run.stderr.strip()[:200] or "empty"))
    return value


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    base = origin()
    envelope = {
        "schema": "popit.wish/1",
        "sender": SENDER,
        "scope": SCOPE,
        "speech_act": "request",
        "content": {
            "intent": "read",
            "request": REQUEST,
            "origin": base,
            "certificate": base + "/popit-cert.cer",
            "app": "dialin",
            "derives_from": "popit-settings",
            "files": ["toast.html", "toast.js", "toast.css", "package.js",
                      "contour-theme.css", "ui-audit.js"],
            "regions": ["bar", "status", "body", "foot"],
            "expected_codes": EXPECTED,
            "boundary": "the settings app package is the baseline; a desk that keeps a private "
                        "copy of it is the refusal, not a resemblance score.",
        },
        "expiry": (now + datetime.timedelta(hours=8)).isoformat(),
        "provenance": {"source": "agent", "project": "popit-shell",
                       "session": "freebuff-2026-11-25", "authority": "none"},
    }
    body = json.dumps(envelope).encode("utf-8")
    opened = urllib.request.Request(NODE, data=body, headers={
        "Authorization": "Bearer " + token(),
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(opened, timeout=15) as reply:
        answer = json.loads(reply.read().decode("utf-8"))
    receipt = {"schema": "popit.driver-wishes/1", "at": now.isoformat(), "origin": base,
               "wish": {"sent": envelope, "answer": answer}}
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{answer.get('status', '?')} {answer.get('code', '')} "
          f"{answer.get('task_id', answer.get('missing', ''))}")
    print(f"receipt {RECEIPT}")
    return 0 if answer.get("status") == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
