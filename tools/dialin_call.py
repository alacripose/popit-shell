"""Talk to a family agent over DialIn, with the signed envelope the join route requires.

`/api/toast/call/join` admits a signed package, `/api/toast/call/say` carries a turn onto the
call, `/api/toast/call/turns` reads what came back and `/api/toast/call/leave` drops the
harness. A driver reached by a bare command is not on a call, so its reply is not on the
record; this is the channel that puts both sides on one.

    python tools/dialin_call.py keygen                 # once, per caller
    python tools/dialin_call.py join --agent Qwen
    python tools/dialin_call.py say --session <id> --text "one turn"
    python tools/dialin_call.py turns --session <id> --since 0
    python tools/dialin_call.py leave --session <id>

The key lives under `runlogs/toast/callers/`, is enrolled with `python envelope.py trust`,
and never enters the repository: `runlogs/` is ignored.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import secrets
import ssl
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import envelope  # noqa: E402

# The desk's HTTPS listener. The loopback port 5207 is the convenience view of the same
# ledger; the call routes answer on both, and the address here is never a LAN literal.
BASE = os.environ.get("POPIT_DESK_ORIGIN") or "https://127.0.0.1:5211"
KEY = ROOT / "runlogs" / "toast" / "callers" / "buffy.key"
PUBLIC = ROOT / "runlogs" / "toast" / "callers" / "buffy.pem"
TRUST = ROOT / "runlogs" / "toast" / "envelope-trust.json"


def post(path: str, body: dict, timeout: float = 60.0) -> dict:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout, context=context) as answer:
        return json.loads(answer.read().decode("utf-8"))


def keygen() -> dict:
    KEY.parent.mkdir(parents=True, exist_ok=True)
    made = envelope.keygen(KEY, PUBLIC)
    return {"made": made, "trusted": envelope.trusted(PUBLIC.read_text(encoding="utf-8"),
                                                       trust_path=TRUST),
            "enrol": f"python envelope.py trust --public {PUBLIC} --name \"Buffy harness\""}


def join(agent: str, profile: str, minutes: int) -> dict:
    if not KEY.is_file():
        raise SystemExit(f"dialin-call: no caller key at {KEY}; run `keygen` first")
    public = envelope._public_from_private(KEY)
    if not envelope.trusted(public, trust_path=TRUST):
        raise SystemExit("dialin-call: this caller key is not in envelope-trust.json; "
                         "enrol it with `python envelope.py trust` before placing a call")
    payload = {
        "schema": envelope.SCHEMA,
        "name": profile,
        "agent": agent,
        "endpoint": BASE + "/api/toast/call/join",
        "mcp": "",
        "capabilities": ["call.join", "call.turns", "call.say", "call.leave"],
        "issued_at": envelope.iso(),
        "expires_at": "",
        "nonce": secrets.token_hex(16),
    }
    signed = envelope.sign(payload, KEY)
    return post("/api/toast/call/join", {"envelope": signed, "agent": agent,
                                         "profile": profile})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dialin_call", description=__doc__.splitlines()[0])
    parser.add_argument("action",
                        choices=("keygen", "join", "say", "turns", "leave", "ask"))
    parser.add_argument("--agent", default="Qwen")
    parser.add_argument("--profile", default="Buffy")
    parser.add_argument("--minutes", type=int, default=0)
    parser.add_argument("--session", default="")
    parser.add_argument("--text", default="")
    parser.add_argument("--since", type=int, default=-1)
    parser.add_argument("--wait", type=float, default=25.0)
    args = parser.parse_args(argv)

    if args.action == "keygen":
        print(json.dumps(keygen(), indent=2, ensure_ascii=False))
        return 0

    session = args.session
    if args.action in ("join", "ask"):
        opened = join(args.agent, args.profile, args.minutes)
        session = str(opened.get("session") or "")
        print(json.dumps({"ok": opened.get("ok"), "session": session,
                          "call": (opened.get("call") or {}).get("id", ""),
                          "agent": opened.get("agent", ""),
                          "fingerprint": opened.get("fingerprint", "")},
                         ensure_ascii=False))
        if args.action == "join":
            return 0 if session else 2

    if not session:
        raise SystemExit("dialin-call: this action needs --session from `join`")

    if args.action in ("say", "ask"):
        said = post("/api/toast/call/say", {"session": session, "text": args.text})
        print(json.dumps({"ok": said.get("ok"), "archive":
                          (said.get("archive") or {}).get("id", "")}, ensure_ascii=False))

    if args.action in ("turns", "ask"):
        seen = args.since
        deadline = time.time() + args.wait
        while time.time() < deadline:
            answer = post("/api/toast/call/turns",
                          {"session": session, "since": seen, "wait": 5})
            rows = answer.get("turns") or []
            for turn in rows:
                print(json.dumps({key: turn.get(key) for key in
                                  ("id", "kind", "role", "text", "at")}, ensure_ascii=False))
                seen = max(seen, int(turn.get("id") or 0))
            if rows and not answer.get("waiting"):
                break
        if seen < 0:
            print(json.dumps({"turns": 0, "refused": "no turn came back on the call"}))
    if args.action == "leave":
        print(json.dumps(post("/api/toast/call/leave", {"session": session}),
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
