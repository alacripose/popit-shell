#!/usr/bin/env python3
"""Drive the Windows CUA fleet through the toast bridge, from the Debian box.

    python3 tools/popit_bridge.py health
    python3 tools/popit_bridge.py capture --window Freebuff
    python3 tools/popit_bridge.py cua --action wait --ms 50
    python3 tools/popit_bridge.py cua --action click --x 400 --y 300
    python3 tools/popit_bridge.py drain

The URL and token come from `--target` (a `bridge-target.json` written by the toast), from
`--url/--token`, or from `POPIT_BRIDGE_URL`/`POPIT_BRIDGE_TOKEN`. Every act is spooled
before it is sent, so a tunnel that flaps mid-act is retried under the same key and the
toast answers with the first receipt instead of acting twice.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bridge  # noqa: E402


def build_client(args) -> bridge.BridgeClient:
    spool = pathlib.Path(args.spool) if args.spool else ROOT / "runlogs" / "toast" / "bridge-spool.json"
    if args.target:
        return bridge.BridgeClient.from_target(pathlib.Path(args.target), spool=spool,
                                               client=args.client)
    url = args.url or os.environ.get("POPIT_BRIDGE_URL", "")
    token = args.token or os.environ.get("POPIT_BRIDGE_TOKEN", "")
    if not url:
        raise bridge.Refused("bridge-url", "pass --target, --url or POPIT_BRIDGE_URL")
    return bridge.BridgeClient(url, token, spool=spool, client=args.client)


def actions_from(args) -> list[dict]:
    rows = []
    for kind in args.action or []:
        item = {"action": kind}
        if kind in ("capture", "focus", "probe_chat"):
            item["window"] = args.window or "Freebuff"
        elif kind in ("click", "move"):
            item["x"], item["y"] = int(args.x or 0), int(args.y or 0)
        elif kind == "type":
            item["text"] = args.text or ""
        elif kind == "key":
            item["key"] = args.key_name or "esc"
        elif kind == "wait":
            item["ms"] = int(args.ms or 50)
        rows.append(item)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("health", "cua", "capture", "receipt", "drain", "spool"))
    parser.add_argument("--target", default=str(ROOT / "runlogs" / "toast" / "bridge-target.json"))
    parser.add_argument("--url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--spool", default="")
    parser.add_argument("--client", default="debian")
    parser.add_argument("--driver", default="")
    parser.add_argument("--key", default="", help="idempotency key; one key names one act")
    parser.add_argument("--seq", type=int, default=None)
    parser.add_argument("--wait", type=float, default=12.0)
    parser.add_argument("--action", action="append", default=[])
    parser.add_argument("--window", default="")
    parser.add_argument("--x", type=int, default=0)
    parser.add_argument("--y", type=int, default=0)
    parser.add_argument("--text", default="")
    parser.add_argument("--key-name", default="")
    parser.add_argument("--ms", type=int, default=50)
    parser.add_argument("--task", default="")
    args = parser.parse_args()
    try:
        client = build_client(args)
        if args.command == "health":
            print(json.dumps(client.health(), indent=2, ensure_ascii=False))
        elif args.command == "spool":
            print(json.dumps(client.spooled(), indent=2, ensure_ascii=False))
        elif args.command == "drain":
            print(json.dumps(client.drain(), indent=2, ensure_ascii=False))
        elif args.command == "receipt":
            if not args.task:
                raise bridge.Refused("bridge-task", "pass --task")
            print(json.dumps(client.receipt(args.task), indent=2, ensure_ascii=False))
        else:
            if args.command == "capture" and not args.action:
                args.action = ["capture"]
            rows = actions_from(args)
            if not rows:
                raise bridge.Refused("bridge-actions", "pass at least one --action")
            value = client.cua(rows, driver=args.driver, key=args.key, seq=args.seq,
                               wait=args.wait)
            print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    except bridge.Refused as error:
        print(json.dumps({"ok": False, "refused": error.as_dict()}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
