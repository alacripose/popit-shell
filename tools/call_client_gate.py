#!/usr/bin/env python3
"""Gate the standalone Popit Call client.

The gate reads the surface the owner would read: it serves its own report page and
fails by name when the page, the report, the contour, the prose or the signed
envelope behavior is missing. It also starts the call client's companion and reads
its page over loopback, so a printed pass cannot stand in for a rendered one.

Run:
    python tools/call_client_gate.py
    python tools/call_client_gate.py serve --port 5312
    python tools/call_client_gate.py probe --port 5312
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import pathlib
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLIENT = ROOT / "call-client"
UI = ROOT / "tools" / "call_client_gate_ui.html"
RECEIPT = ROOT / "artifacts" / "receipts" / "call-client-gate-probe.json"
SCHEMA = "popit.call-client-gate/1"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(name: str, ok: bool, detail: str = "", **extra) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, **extra}


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style", "noscript", "pre", "code"):
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "pre", "code") and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip and data.strip():
            self.parts.append(" ".join(data.split()))


def prose_texts() -> list[str]:
    parser = VisibleText()
    source = _text(CLIENT / "index.html")
    body = re.search(r"<body[^>]*>(.*)</body>", source, re.S)
    parser.feed(body.group(1) if body else source)
    texts: list[str] = []
    for part in parser.parts:
        for sentence in re.split(r"(?<=[.!?])\s+|\s*·\s*|\s{2,}", part):
            value = html.unescape(sentence).strip(" ·\n\t")
            if len(value.split()) >= 3:
                texts.append(value)
    return texts


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch(url: str, timeout: float = 6.0) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type", "")


def check_static() -> list[dict]:
    rows: list[dict] = []
    required = ["index.html", "app.js", "styles.css", "serve.py", "envelope.py",
                "contour.js", "contour.json", "manifest.webmanifest", "sw.js",
                "README.md", "ENVELOPE.md"]
    missing = [name for name in required if not (CLIENT / name).is_file()]
    rows.append(_row("files-present", not missing, ", ".join(missing) or "all present"))
    index = _text(CLIENT / "index.html")
    css = _text(CLIENT / "styles.css")
    app = _text(CLIENT / "app.js")
    rows.append(_row("popit-surface", 'data-popit="call-client"' in index,
                     "the page names its Popit surface"))
    contours = re.findall(r'<[^>]+data-contour="[^"]+"', index)
    rows.append(_row("contour-surfaces", len(contours) >= 4,
                     f"{len(contours)} contour surfaces"))
    rows.append(_row("no-rounded-rectangle", "border-radius" not in css,
                     "the CSS has no rounded-rectangle declaration"))
    rows.append(_row("contour-paint", "clip-path: var(--clip" in css,
                     "the paint layer takes the contour clip"))
    rows.append(_row("contour-loader", "fillContours" in app and "loadContour" in app,
                     "the page loads and fills the contour"))
    serve = _text(CLIENT / "serve.py")
    rows.append(_row("companion-routes", "/api/bridge" in serve and "/health" in serve,
                     "the companion exposes its bridge and health"))
    rows.append(_row("remote-section", "REMOTE LINE" in index and "--public-origin" in index,
                     "the landing page names the cross-machine TLS path"))
    rows.append(_row("bridge-allowlist", "BRIDGE_ALLOW" in serve and "bridge-route" in serve,
                     "the public companion refuses unlisted bridge routes"))
    rows.append(_row("cors-exact-origin", "PUBLIC_ORIGIN" in serve and
                     "Access-Control-Allow-Origin" in serve,
                     "CORS is tied to the exact published origin"))
    client_envelope = _text(CLIENT / "envelope.py")
    rows.append(_row("envelope-authority",
                     "SIGNED_FIELDS" in client_envelope and "envelope-replay" in client_envelope,
                     "signing, trust and replay are in the package"))
    private = [path.name for path in CLIENT.iterdir()
               if path.is_file() and "BEGIN PRIVATE KEY" in _text(path)]
    rows.append(_row("no-private-key", not private,
                     ", ".join(private) or "no private key in the published tree"))
    return rows


def check_prose() -> list[dict]:
    texts = prose_texts()
    try:
        landing = _load(ROOT / "tools" / "landing.py", "popit_landing_gate")
        landing.prose_check(texts)
    except SystemExit as error:
        return [_row("family-prose", False, str(error)[:300])]
    except Exception as error:  # noqa: BLE001 - the refusal is the report
        return [_row("family-prose", False, f"{type(error).__name__}: {error}"[:300])]
    return [_row("family-prose", True, f"{len(texts)} visible sentences checked")]


def check_envelope() -> list[dict]:
    rows: list[dict] = []
    try:
        envelope = _load(CLIENT / "envelope.py", "popit_call_envelope")
    except Exception as error:  # noqa: BLE001
        return [_row("envelope-import", False, f"{type(error).__name__}: {error}"[:240])]
    with tempfile.TemporaryDirectory(prefix="popit-call-gate-") as folder:
        root = pathlib.Path(folder)
        key = root / "caller.key"
        public = root / "caller.pem"
        trust = root / "trust.json"
        nonces = root / "nonces.json"
        info = envelope.keygen(key, public)
        envelope.trust_key(_text(public), "Gate Caller", trust)
        payload = {
            "schema": "popit.call-envelope/1",
            "name": "Gate Caller", "agent": "Buffy",
            "endpoint": "https://caller.example.test/mcp",
            "mcp": "https://caller.example.test/mcp",
            "capabilities": ["call.join", "call.turns", "call.say", "call.leave"],
            "nonce": secrets.token_hex(16),
        }
        signed = envelope.sign(payload, key)
        rows.append(_row("envelope-signature", bool(signed.get("signature")),
                         info["fingerprint"]))
        admission = envelope.admit(signed, trust_path=trust, nonce_path=nonces)
        rows.append(_row("envelope-admit", admission.get("admitted") is True,
                         f"caller {admission.get('caller')}"))
        try:
            envelope.admit(signed, trust_path=trust, nonce_path=nonces)
        except envelope.Refused as error:
            rows.append(_row("envelope-replay", error.code == "envelope-replay", error.code))
        else:
            rows.append(_row("envelope-replay", False, "a replay was admitted"))
        tampered = dict(signed)
        tampered["name"] = "Gate Caller altered"
        try:
            envelope.admit(tampered, trust_path=trust, nonce_path=nonces)
        except envelope.Refused as error:
            rows.append(_row("envelope-tamper", error.code == "envelope-signature", error.code))
        else:
            rows.append(_row("envelope-tamper", False, "a tampered name was admitted"))
        try:
            envelope.admit(signed, trust_path=root / "absent-trust.json", nonce_path=nonces)
        except envelope.Refused as error:
            rows.append(_row("envelope-trust-absent", error.code == "envelope-trust-absent",
                             error.code))
        else:
            rows.append(_row("envelope-trust-absent", False, "an absent registry was accepted"))
    return rows


def check_client_http() -> list[dict]:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(CLIENT / "serve.py"), "--port", str(port)],
        cwd=str(CLIENT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )
    try:
        deadline = time.monotonic() + 8
        status, body, _ = 0, b"", ""
        while time.monotonic() < deadline:
            try:
                status, body, _ = fetch(f"http://127.0.0.1:{port}/", 1.0)
                if status == 200:
                    break
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.15)
        page_ok = status == 200 and b'data-popit="call-client"' in body
        health_status, health_body, _ = fetch(f"http://127.0.0.1:{port}/health")
        try:
            health = json.loads(health_body)
        except json.JSONDecodeError:
            health = {}
        health_ok = health_status == 200 and health.get("service") == "popit-call-companion"
        app_status, app_body, app_type = fetch(f"http://127.0.0.1:{port}/app.js")
        app_ok = app_status == 200 and b"loadContour" in app_body and "javascript" in app_type
        return [
            _row("call-client-http", page_ok, f"GET / {status}"),
            _row("call-client-health", health_ok, f"GET /health {health_status}"),
            _row("call-client-js", app_ok, f"GET /app.js {app_status}"),
        ]
    finally:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()


def build_report() -> dict:
    checks = check_static() + check_client_http()
    prose = check_prose()
    envelope = check_envelope()
    rows = checks + prose + envelope
    refused = [row for row in rows if not row["ok"]]
    return {
        "schema": SCHEMA, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(rows), "passed": len(rows) - len(refused), "refused": len(refused),
        "checks": checks, "prose": prose, "envelope": envelope,
        "refusals": [row["name"] for row in refused],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PopitCallGate/1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/report.json":
            body = json.dumps(build_report(), ensure_ascii=False).encode("utf-8")
            return self._send(200, body, "application/json; charset=utf-8")
        if self.path in ("/", "/index.html"):
            return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
        return self._send(404, b'{"ok":false,"refused":"call-client-gate-route"}',
                          "application/json; charset=utf-8")


def serve(port: int) -> int:
    threading.Thread(target=lambda: ThreadingHTTPServer(
        ("127.0.0.1", port), Handler).serve_forever(), daemon=True).start()
    print(json.dumps({"ok": True, "url": f"http://127.0.0.1:{port}/"}), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def probe(port: int) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, page, _ = fetch(f"http://127.0.0.1:{port}/")
        report_status, report_body, _ = fetch(f"http://127.0.0.1:{port}/report.json")
        report = json.loads(report_body)
        page_ok = status == 200 and b'data-popit="call-client-gate"' in page \
            and b'id="gate-checks"' in page and b'id="gate-summary"' in page
        report_ok = report_status == 200 and report.get("schema") == SCHEMA \
            and report.get("total", 0) >= 10 and all(
                row.get("name") for group in ("checks", "prose", "envelope")
                for row in report.get(group, []))
        receipt = {
            "schema": "popit.call-client-gate-probe/1", "at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "page": page_ok, "report": report_ok, "summary": {
                "total": report.get("total"), "passed": report.get("passed"),
                "refused": report.get("refused"),
            },
            "refusals": report.get("refusals", []),
        }
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False))
        return 0 if page_ok and report_ok and not report.get("refused") else 1
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="run", choices=("run", "serve", "probe"))
    parser.add_argument("--port", type=int, default=5312)
    args = parser.parse_args()
    if args.command == "serve":
        return serve(args.port)
    if args.command == "probe":
        return probe(args.port)
    report = build_report()
    for row in report["checks"] + report["prose"] + report["envelope"]:
        print(f"[{'ok' if row['ok'] else 'FAIL'}] {row['name']}: {row['detail']}")
    print(f"{report['total']} checks, {report['refused']} refusals")
    return 0 if not report["refused"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
