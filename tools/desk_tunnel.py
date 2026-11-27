#!/usr/bin/env python3
"""Put the desk's remote listener on the internet, behind its own sign-in.

The desk already serves its app over TLS on the machine; this only carries that listener out.
It opens a Cloudflare quick tunnel to ``https://127.0.0.1:<remote-port>`` — the listener that
answers a signed-in browser and nothing else — and prints the public origin the tunnel was
given. The public leg is Cloudflare's own certificate; the leg from the tunnel to this machine
is the desk's TLS listener, which is self-signed, so the tunnel is told not to verify it.

    python tools/desk_tunnel.py                 # 5222, stays in the foreground
    python tools/desk_tunnel.py --port 5222 --print-url-only

Nothing here weakens the desk: the tunnel points at the sign-in gate. The loopback desk, the
LAN origin and the phone's certificate are untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "tools" / "bin"
BINARY = BIN_DIR / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
RELEASES = {
    "nt": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "posix": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
}
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
LOG = ROOT / "runlogs" / "toast" / "desk-tunnel.log"
RECEIPT = ROOT / "runlogs" / "toast" / "desk-tunnel.json"


def ensure_binary() -> pathlib.Path:
    if BINARY.exists() and BINARY.stat().st_size > 1_000_000:
        return BINARY
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    source = RELEASES["nt"] if os.name == "nt" else RELEASES["posix"]
    print(f"desk-tunnel · fetching {source}", flush=True)
    with urllib.request.urlopen(source, timeout=180) as response, \
            BINARY.open("wb") as handle:
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            handle.write(chunk)
    if os.name != "nt":
        BINARY.chmod(0o755)
    print(f"desk-tunnel · {BINARY} · {BINARY.stat().st_size / 1e6:.1f} MB", flush=True)
    return BINARY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=5222)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--print-url-only", action="store_true")
    args = parser.parse_args()

    origin = f"https://{args.host}:{args.port}"
    binary = ensure_binary()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    command = [str(binary), "tunnel", "--url", origin, "--no-tls-verify",
               "--no-autoupdate"]
    print(f"desk-tunnel · {' '.join(command)}", flush=True)
    log = LOG.open("a", encoding="utf-8", errors="replace")
    log.write(f"\n=== desk-tunnel {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} · {origin}\n")
    log.flush()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace",
                               creationflags=0x08000000 if os.name == "nt" else 0)
    public = ""
    started = time.time()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            if not args.print_url_only:
                sys.stdout.write(line)
                sys.stdout.flush()
            found = URL_RE.search(line)
            if found and not public:
                public = found.group(0)
                RECEIPT.write_text(json.dumps({
                    "schema": "popit.desk-tunnel/1",
                    "origin": origin,
                    "public": public,
                    "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }, indent=2) + "\n", encoding="utf-8")
                print(f"desk-tunnel · public {public}", flush=True)
                if args.print_url_only:
                    print(public, flush=True)
            if time.time() - started > 180 and not public:
                print("desk-tunnel · no public origin after 180 s · see " + str(LOG),
                      flush=True)
                break
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log.close()
    return 0 if public else 1


if __name__ == "__main__":
    raise SystemExit(main())
