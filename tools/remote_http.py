#!/usr/bin/env python3
"""One loopback HTTP exchange on the Debian box, on the box's behalf.

Reads `{"url", "token", "body", "method"}` as JSON on stdin and prints
`{"ok", "status", "body"}` on stdout. The desk reaches this over ssh, so the request never
depends on a WSL local-forward, and the bearer token stays in this process's memory instead
of appearing in a command line or a Windows-side state file.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    request = json.load(sys.stdin)
    url = str(request.get("url") or "")
    token = str(request.get("token") or "")
    method = str(request.get("method") or "POST").upper()
    payload = request.get("body")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    opened = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(opened, timeout=60) as reply:
            raw = reply.read().decode("utf-8", "replace")
            answer = {"ok": True, "status": reply.status}
            try:
                answer["body"] = json.loads(raw)
            except ValueError:
                answer["body"] = raw[:2000]
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        answer = {"ok": False, "status": error.code}
        try:
            answer["body"] = json.loads(raw)
        except ValueError:
            answer["body"] = raw[:2000]
    except (OSError, ValueError) as error:
        answer = {"ok": False, "status": 0, "body": str(error)[:300]}
    print(json.dumps(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
