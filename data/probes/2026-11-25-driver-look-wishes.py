#!/usr/bin/env python3
"""Two read wishes to the CUA driver: the surface look audit, and the tile drive.

This runs **on the driver box**, not here. The shell's modern origin is HTTPS, named by
`POPIT_ORIGIN` or by the box's own `/etc/agent/driver.env`, certificate at `/popit-cert.cer`;
the loopback port 5207 is the desk's convenience view and is not the app.

The driver's own answer is the receipt: `accepted` stores the wish as its task, `clarify`
names a missing slot, `declined` is its own bound. Nothing here executes a body tool; the
wish carries no capability and no authority.

    echo <base64> | base64 -d > /tmp/popit_look_wishes.py
    python3 /tmp/popit_look_wishes.py

Receipt on the box: `/srv/scratch/popit-look-wishes.json`.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import urllib.request

ENV = pathlib.Path("/etc/agent/driver.env")
NODE = "http://127.0.0.1:8765/v1/wishes"
# The desk's address on this network is a local fact of the box, not a constant in a record:
# it is read from the environment or from the box's own `/etc/agent/driver.env`.
ORIGIN = os.environ.get("POPIT_ORIGIN") or ""
RECEIPT = pathlib.Path("/srv/scratch/popit-look-wishes.json")
SENDER = "popit-shell session (freebuff agent)"
SCOPE = "popit-shell/ui · the look check and the SpringBoard tile"


def token() -> str:
    """The peer token, read on the box under sudo and never printed.

    The bridge reaches the box as the family's unprivileged user; the unit keeps the token in
    root-only `/etc/agent/driver.env`. `alacrity` holds NOPASSWD sudo, so the read is a local
    act, not a secret in a command line.
    """
    run = subprocess.run(["sudo", "-n", "sed", "-n", "s/^CUA_DRIVER_TOKEN=//p", str(ENV)],
                         capture_output=True, text=True, timeout=30, check=False)
    value = run.stdout.strip().strip('"')
    if not value:
        raise SystemExit("CUA_DRIVER_TOKEN could not be read on the box: "
                         + (run.stderr.strip()[:200] or "empty"))
    return value


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


def wish(intent: str, request: str, extra: dict) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    content = {"intent": intent, "request": request}
    content.update(extra)
    envelope = {
        "schema": "popit.wish/1",
        "sender": SENDER,
        "scope": SCOPE,
        "speech_act": "request",
        "content": content,
        "expiry": (now + datetime.timedelta(hours=4)).isoformat(),
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
    return {"sent": envelope, "answer": answer}


def main() -> int:
    base = origin()
    look = wish(
        "read",
        "Audit every signed Popit app surface on its HTTPS origin and refuse a surface that "
        "furnishes its own look: a stylesheet the family did not publish for its kind, a style "
        "block, an inline paint, a control without the chrome's contour, window furniture that is "
        "not a declared region, or motion of its own. Read the code the server signs and the "
        "rendered window; name each finding with its code; write the receipt on this box and name "
        "it in the answer.",
        {
            "origin": base,
            "certificate": base + "/popit-cert.cer",
            "surfaces": ["bridge", "springboard", "settings", "dialin"],
            "derives_from": "popit-settings",
            "expected_codes": ["look-stylesheet", "look-style-block", "look-inline-paint",
                               "look-motion", "look-button", "look-chrome", "look-not-derived"],
            "boundary": "the look, buttons, chrome and motion belong to the settings package and "
                        "the shared sheets (contour-theme.css, toast.css/phone.css, package.js); a "
                        "page that paints its own is the refusal, not a resemblance score.",
        },
    )
    drive = wish(
        "read",
        "Drive the SpringBoard tile that launches the bridge and the bridge page itself on the "
        "HTTPS origin: focus the SpringBoard, capture the signed Bridge tile, activate it, capture "
        "the bridge page, and record both captures with their digests and the app identity each "
        "window names.",
        {
            "origin": base,
            "tile": {"app": "bridge", "label": "Bridge", "identity_prefix": "app-bridge@"},
            "pages": ["/phone.html", "/bridge.html"],
            "record": ["capture path", "sha256", "window title", "identity", "at"],
            "boundary": "the Windows CUA fleet is driven through the toast bridge "
                        "(tools/popit_bridge.py, spooled acts, one key per act); the witness "
                        "window is 'Popit toast', not a second launcher.",
        },
    )
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    receipt = {"schema": "popit.driver-wishes/1", "at": now.isoformat(),
               "origin": base, "wishes": [look, drive]}
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for row in (look, drive):
        answer = row["answer"]
        print(f"{answer.get('status', '?')} {answer.get('code', '')} "
              f"{answer.get('task_id', answer.get('missing', ''))}")
    print(f"receipt {RECEIPT}")
    return 0 if all(row["answer"].get("status") == "accepted" for row in (look, drive)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
