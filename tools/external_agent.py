#!/usr/bin/env python3
"""Enroll and call a Popit external line without a second crypto/runtime dependency.

The enrollment and call tickets are Ed25519-signed canonical JSON. The signal is an
SDP offer/answer exchange; the caller supplies the offer from its own WebRTC runtime.
This CLI does not pretend to create media, and it does not store the host's secrets.

Examples:
    python tools/external_agent.py keygen --private caller.key --public caller.pem
    python tools/external_agent.py enroll --bridge http://127.0.0.1:5207 \
        --code CODE --name "Ada's agent" --endpoint https://agent.example/mcp \
        --key caller.key
    python tools/external_agent.py call --bridge http://127.0.0.1:5207 \
        --agent AGENT_ID --key caller.key --offer offer.sdp
    python tools/external_agent.py state --bridge http://127.0.0.1:5207 --call CALL_ID
    python tools/external_agent.py end --bridge http://127.0.0.1:5207 --call CALL_ID
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import secrets
import ssl
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import envelope  # noqa: E402

REGISTRATION_SCHEMA = "popit.agent-registration/1"
CALL_SCHEMA = "popit.agent-call/1"


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def request(method: str, url: str, body: dict | None = None, *, insecure: bool = False) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    context = ssl._create_unverified_context() if insecure else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"http {error.code}: {detail[:500]}")
    except OSError as error:
        raise SystemExit(f"bridge unavailable: {error}")


def base(bridge: str) -> str:
    return bridge.rstrip("/")


def keygen(args: argparse.Namespace) -> int:
    row = envelope.keygen(pathlib.Path(args.private), pathlib.Path(args.public))
    print(json.dumps(row, indent=2))
    return 0


def enroll(args: argparse.Namespace) -> int:
    public_key = pathlib.Path(args.public).read_text(encoding="utf-8").strip() if args.public else ""
    payload = {
        "schema": REGISTRATION_SCHEMA, "name": args.name, "endpoint": args.endpoint,
        "public_key": public_key, "issued_at": now(), "code": args.code,
    }
    payload["signature"] = envelope.sign_payload(payload, pathlib.Path(args.key))
    print(json.dumps(request("POST", base(args.bridge) + "/api/toast/external/enroll",
                              payload, insecure=args.insecure), indent=2))
    return 0


def call(args: argparse.Namespace) -> int:
    offer = pathlib.Path(args.offer).read_text(encoding="utf-8")
    nonce = secrets.token_hex(16)
    payload = {"schema": CALL_SCHEMA, "agent": args.agent, "nonce": nonce,
               "issued_at": now(), "offer": offer}
    payload["signature"] = envelope.sign_payload(payload, pathlib.Path(args.key))
    print(json.dumps(request("POST", base(args.bridge) + "/api/toast/external/call",
                              payload, insecure=args.insecure), indent=2))
    return 0


def state(args: argparse.Namespace) -> int:
    print(json.dumps(request("POST", base(args.bridge) + "/api/toast/external/call/state",
                              {"call_id": args.call, "agent": args.agent},
                              insecure=args.insecure), indent=2))
    return 0


def ice(args: argparse.Namespace) -> int:
    candidate = json.loads(args.candidate) if args.candidate else None
    print(json.dumps(request("POST", base(args.bridge) + "/api/toast/external/call/ice",
                              {"call_id": args.call, "side": args.side,
                               "candidate": candidate}, insecure=args.insecure), indent=2))
    return 0


def end(args: argparse.Namespace) -> int:
    print(json.dumps(request("POST", base(args.bridge) + "/api/toast/external/call/end",
                              {"call_id": args.call, "outcome": args.outcome},
                              insecure=args.insecure), indent=2))
    return 0


def contacts(args: argparse.Namespace) -> int:
    print(json.dumps(request("GET", base(args.bridge) + "/api/toast/external/contacts",
                              insecure=args.insecure), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    key = sub.add_parser("keygen")
    key.add_argument("--private", required=True)
    key.add_argument("--public", required=True)
    key.set_defaults(func=keygen)
    enroll_parser = sub.add_parser("enroll")
    enroll_parser.add_argument("--bridge", required=True)
    enroll_parser.add_argument("--code", required=True)
    enroll_parser.add_argument("--name", required=True)
    enroll_parser.add_argument("--endpoint", required=True)
    enroll_parser.add_argument("--key", required=True)
    enroll_parser.add_argument("--public", required=True)
    enroll_parser.add_argument("--insecure", action="store_true")
    enroll_parser.set_defaults(func=enroll)
    call_parser = sub.add_parser("call")
    call_parser.add_argument("--bridge", required=True)
    call_parser.add_argument("--agent", required=True)
    call_parser.add_argument("--key", required=True)
    call_parser.add_argument("--offer", required=True)
    call_parser.add_argument("--insecure", action="store_true")
    call_parser.set_defaults(func=call)
    state_parser = sub.add_parser("state")
    state_parser.add_argument("--bridge", required=True)
    state_parser.add_argument("--call", required=True)
    state_parser.add_argument("--agent", default="")
    state_parser.add_argument("--insecure", action="store_true")
    state_parser.set_defaults(func=state)
    ice_parser = sub.add_parser("ice")
    ice_parser.add_argument("--bridge", required=True)
    ice_parser.add_argument("--call", required=True)
    ice_parser.add_argument("--side", choices=["agent", "phone"], default="agent")
    ice_parser.add_argument("--candidate", default="")
    ice_parser.add_argument("--insecure", action="store_true")
    ice_parser.set_defaults(func=ice)
    end_parser = sub.add_parser("end")
    end_parser.add_argument("--bridge", required=True)
    end_parser.add_argument("--call", required=True)
    end_parser.add_argument("--outcome", choices=["ended", "declined"], default="ended")
    end_parser.add_argument("--insecure", action="store_true")
    end_parser.set_defaults(func=end)
    contacts_parser = sub.add_parser("contacts")
    contacts_parser.add_argument("--bridge", required=True)
    contacts_parser.add_argument("--insecure", action="store_true")
    contacts_parser.set_defaults(func=contacts)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
