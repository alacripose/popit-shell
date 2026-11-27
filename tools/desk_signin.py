#!/usr/bin/env python3
"""Mint what the remote desk sign-in asks for.

A remote browser signs in with the same Ed25519 envelope a call uses; this tool is the
machine's side of it. It generates the caller key, puts the public half in the envelope trust
registry, and mints a short-lived package carrying ``desk.access``. A browser that cannot
hold a key enrols once with a one-time desk code.

    python tools/desk_signin.py keygen --private runlogs/toast/desk.key --public runlogs/toast/desk.pem
    python tools/desk_signin.py trust  --public runlogs/toast/desk.pem --name "Owner phone"
    python tools/desk_signin.py mint   --key runlogs/toast/desk.key --name "Owner phone" --out runlogs/toast/desk-package.json
    python tools/desk_signin.py code   --minutes 10
    python tools/desk_signin.py sessions
    python tools/desk_signin.py revoke --all
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import desk_auth  # noqa: E402
import envelope  # noqa: E402

STORE = desk_auth.Store(ROOT / "runlogs" / "toast")
TRUST = ROOT / "runlogs" / "toast" / "envelope-trust.json"


def payload(name: str, endpoint: str, minutes: int) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return {
        "schema": envelope.SCHEMA,
        "name": name,
        "agent": "desk",
        "endpoint": endpoint,
        "mcp": "",
        "capabilities": ["desk.access"],
        "nonce": secrets.token_hex(16),
        "issued_at": envelope.iso(now),
        "expires_at": envelope.iso(now + datetime.timedelta(minutes=max(1, minutes))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    key = sub.add_parser("keygen", help="generate the caller's Ed25519 key")
    key.add_argument("--private", default=str(ROOT / "runlogs" / "toast" / "desk.key"))
    key.add_argument("--public", default=str(ROOT / "runlogs" / "toast" / "desk.pem"))

    trust = sub.add_parser("trust", help="add the public key to the envelope trust registry")
    trust.add_argument("--public", required=True)
    trust.add_argument("--name", default="desk caller")
    trust.add_argument("--trust", default=str(TRUST))

    mint = sub.add_parser("mint", help="sign a desk package for the sign-in page")
    mint.add_argument("--key", default=str(ROOT / "runlogs" / "toast" / "desk.key"))
    mint.add_argument("--name", default="desk caller")
    mint.add_argument("--endpoint", default="https://popit.local/desk")
    mint.add_argument("--minutes", type=int, default=15)
    mint.add_argument("--out", default="")

    code = sub.add_parser("code", help="mint a one-time desk code")
    code.add_argument("--minutes", type=int, default=desk_auth.CODE_MINUTES)
    code.add_argument("--caller", default="remote")

    sub.add_parser("sessions", help="list live desk sessions")

    revoke = sub.add_parser("revoke", help="revoke one session, a caller's sessions, or all")
    revoke.add_argument("--id", default="")
    revoke.add_argument("--caller", default="")
    revoke.add_argument("--all", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "keygen":
            print(json.dumps(envelope.keygen(pathlib.Path(args.private),
                                             pathlib.Path(args.public)), indent=2))
        elif args.command == "trust":
            public = pathlib.Path(args.public).read_text(encoding="utf-8")
            print(json.dumps(envelope.trust_key(public, args.name, pathlib.Path(args.trust)),
                             indent=2))
        elif args.command == "mint":
            signed = envelope.sign(payload(args.name, args.endpoint, args.minutes),
                                   pathlib.Path(args.key))
            text = json.dumps(signed, indent=2, ensure_ascii=False) + "\n"
            if args.out:
                target = pathlib.Path(args.out)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                print(json.dumps({"package": str(target),
                                  "fingerprint": envelope.fingerprint(signed["public_key"]),
                                  "expires_at": signed["expires_at"]}, indent=2))
            else:
                print(text, end="")
        elif args.command == "code":
            STORE.code_minutes = max(1, args.minutes)
            print(json.dumps(STORE.mint_code(args.caller), indent=2))
        elif args.command == "sessions":
            rows = [{"id": row["id"], "caller": row["caller"], "mode": row["mode"],
                     "created": row["created"], "expires": row["expires"], "last": row["last"]}
                    for row in STORE.sessions()]
            print(json.dumps({"sessions": rows, "count": len(rows)}, indent=2))
        elif args.command == "revoke":
            ident = args.id or args.caller
            removed = STORE.revoke("" if args.all else ident)
            print(json.dumps({"revoked": removed, "scope": "all" if args.all else ident},
                             indent=2))
    except (envelope.Refused, desk_auth.Refused, OSError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "desk-signin")
        print(json.dumps({"ok": False, "refused": {"code": code, "detail": str(error)}},
                         ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
