#!/usr/bin/env python3
"""Stdio MCP harness for the Popit call bridge.

A general coding agent speaks MCP over stdin/stdout; the live call surface is the
loopback JSON-RPC server in `toast.py`. This proxy forwards each framed message to
`http://127.0.0.1:5207/mcp`, so `call.join`, `call.turns`, `call.say` and `call.leave`
are available to any MCP client without giving that client the desktop or the voice
queue directly.

Set `POPIT_MCP` to another loopback URL when the toast runs on a different port.
The proxy never invents a response: a transport failure is returned as a JSON-RPC
error with the real exception text.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = os.environ.get("POPIT_MCP", "http://127.0.0.1:5207/mcp")


def forward(message: dict) -> dict:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        return {"jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32000, "message": f"popit-mcp-transport: {error}"}}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            reply = {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": f"parse-error: {error}"}}
        else:
            reply = forward(message if isinstance(message, dict) else {"method": ""})
        sys.stdout.write(json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
