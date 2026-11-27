"""The window audit: the delivered window measures its own surface, and this reads it back.

Owner rule: *"no more doing tests in the browser harness you us the cua drivers s and their
development and actually use the harness probe feature instead of hardcoding a lie into it"*.

So the measurement is not typed here. The shell owns one window; `POST /api/toast/window/audit`
loads a page into that window with the audit flag, the page measures its own surface, and it
posts the report to `/api/toast/ui-audit` — the same route the family's audits already use.
This tool asks the window for each app and then reads the numbers the window produced: the
registry's audit state, the package revision, the measured size and the report's timestamp.

Its probe reads this page and `/report.json` over loopback, because a printed pass is not a
reading; a row that is not `passed` is a refusal with its code and the act that clears it.

    python tools/window_audit.py report   # visit every app's surface once
    python tools/window_audit.py serve    # the Popit page on http://127.0.0.1:5214
    python tools/window_audit.py probe    # start, read /, read /report.json, fail by name
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHELL = "http://127.0.0.1:5207"
# Every mutable app, audited in its own window: the prose app included, since a window signed
# without a measured surface is a claim rather than a delivery.
APPS = ("dialin", "settings", "springboard", "prose", "archive", "evidence")
# A window page is hosted by the shell, never signed as a package: the store lists it refused,
# the same rejection the retired IDE app got.
FOREIGN = {"bridge": "app-kind-foreign"}
RECEIPT = ROOT / "artifacts" / "receipts" / "window-audit.json"
PAGE_REPORT = ROOT / "artifacts" / "receipts" / "window-audit-report.json"
SCHEMA = "popit.window-audit/1"
PORT = 5214


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def http(path: str, body: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(SHELL + path, data=data, method="POST" if body else "GET",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except (ValueError, OSError):
            return error.code, {}


def registry() -> dict:
    _, body = http("/api/toast/apps")
    return ((body or {}).get("apps") or {})


def row_for(app: str, apps: dict) -> dict:
    # The list carries the state; the per-app record carries the measured size and timestamp.
    status, facts = http(f"/api/toast/apps/{app}")
    record = dict(facts) if status == 200 and isinstance(facts, dict) else {}
    if not record:
        record = apps.get(app) or {}
    record.setdefault("revision", (apps.get(app) or {}).get("revision"))
    refused = record.get("refused") or None
    audit = str(record.get("ui_audit") or "none")
    audit_row = record.get("ui_audit_report") or {}
    size = audit_row.get("size") or {}
    passed = audit == "passed" and not refused
    return {
        "app": app,
        "state": "passed" if passed else "refused",
        "detail": (f"{audit} · app-{app}@{record.get('revision') or '0'} · "
                   f"{size.get('width') or '?'}x{size.get('height') or '?'} · "
                   f"{(refused or {}).get('code') or 'no refusal'}"),
        "audit": audit,
        "revision": record.get("revision"),
        "at": audit_row.get("at") or "",
        "findings": len(audit_row.get("findings") or []),
        "refusal": (refused or {}).get("code") or "",
        "act": f"open /{app} in the delivered window with ?uiaudit=1&app={app}",
    }


def report() -> dict:
    apps = registry()
    rows = [row_for(app, apps) for app in APPS]
    return {
        "schema": SCHEMA,
        "generated_at": iso(),
        "shell": SHELL,
        "rows": rows,
        "refused": [row["app"] for row in rows if row["state"] != "passed"],
        "live": bool(apps),
    }


def measure(app: str, seconds: float = 40.0) -> dict:
    """Ask the delivered window to audit `app`, then read the numbers it produced."""
    asked = iso()
    if app == "springboard":
        # The home is measured inside the frame the settings window delivers, never as a page
        # of its own: the window is back on its own page, and the frame it delivers is loaded
        # with the audit flag and reports its own size.
        http("/api/toast/window/audit", {"app": "desk"})
        time.sleep(5)
        status, body = http("/api/toast/window/eval", {"name": "springboardAudit"})
    else:
        status, body = http("/api/toast/window/audit", {"app": app})
    if status != 200 or not (body or {}).get("ok"):
        return {"app": app, "state": "refused", "detail": str((body or {}).get("refused")),
                "act": "start the shell window", "at": "", "findings": 0}
    deadline = time.time() + seconds
    while time.time() < deadline:
        row = row_for(app, registry())
        # A refused package is a result, not something to wait out: the name is the finding.
        if row.get("refusal"):
            row["asked"] = asked
            return row
        if row["state"] == "passed" and row["at"] and row["at"] >= asked:
            row["asked"] = asked
            # The window is left on its own page, never on the page it just measured.
            http("/api/toast/window/audit", {"app": "desk"})
            time.sleep(2)
            return row
        time.sleep(1.5)
    row = row_for(app, registry())
    row["asked"] = asked
    return row


def window_probe(name: str, seconds: float = 25.0) -> dict | None:
    """Ask the delivered window to perform a named act and read the state it reports."""
    status, body = http("/api/toast/window/eval", {"name": name})
    if status != 200 or not (body or {}).get("ok"):
        return None
    key = str(body.get("id") or "")
    deadline = time.time() + seconds
    while time.time() < deadline:
        status, reply = http(f"/api/toast/window/eval?id={key}")
        if status == 200 and (reply or {}).get("ok"):
            value = (reply or {}).get("value")
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {"value": value}
            return value if isinstance(value, dict) else None
        time.sleep(0.8)
    return None


def report_page(body: dict) -> str:
    def cell(text: object) -> str:
        return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    rows = "".join(
        f'<tr data-state="{cell(row["state"])}"><td>{cell(row["app"])}</td>'
        f'<td class="word">{cell(row["state"])}</td><td>{cell(row["detail"])}</td>'
        f'<td class="mono">{cell(row["at"] or "—")}</td><td class="act">{cell(row["act"])}</td></tr>'
        for row in body["rows"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<title>Popit window audit</title>
<style>
:root {{ --ground:#0c0e11; --panel:#14100b; --gold:#f0c454; --ink:#e8e2d4; --meta:#9c8a6b; --line:#2a2012; }}
body {{ margin:0; padding:22px 24px; background:var(--ground); color:var(--ink);
  font-family:Archivo,"Segoe UI",system-ui,sans-serif; }}
h1 {{ font-size:14px; letter-spacing:.14em; text-transform:uppercase; margin:0 0 4px; }}
p.meta {{ color:var(--meta); font:12px/1.5 "IBM Plex Mono",monospace; margin:0 0 14px; }}
.count {{ font:13px/1 "IBM Plex Mono",monospace; color:var(--gold); margin:0 0 16px; }}
table {{ width:100%; border-collapse:collapse; font:12px/1.5 "IBM Plex Mono",monospace; }}
th {{ text-align:left; color:var(--meta); font-weight:400; letter-spacing:.08em;
  text-transform:uppercase; padding:6px 8px; border-bottom:1px solid var(--line); }}
td {{ padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
tr[data-state="refused"] td.word {{ color:var(--gold); }}
td.word {{ text-transform:uppercase; letter-spacing:.08em; }}
td.act {{ color:var(--meta); }}
</style></head>
<body data-popit="window-audit">
<h1>Window audit</h1>
<p class="meta">the delivered window measures its own surface · {cell(body["shell"])} · read {cell(body["generated_at"])}</p>
<p class="count" id="refused-count">{len(body["refused"])} refused of {len(body["rows"])} rows</p>
<table id="audit-table"><thead><tr><th>app</th><th>state</th><th>measured</th><th>at</th><th>act</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # keep the probe's output readable
        return

    def send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path)
        if path.path in ("/", "/index.html"):
            body = report()
            PAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
            PAGE_REPORT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
            return self.send(200, report_page(body).encode("utf-8"), "text/html; charset=utf-8")
        if path.path == "/report.json":
            return self.send(200, json.dumps(report()).encode("utf-8"), "application/json")
        if path.path == "/measure":
            app = (parse_qs(path.query).get("app") or [""])[0]
            if app not in APPS:
                return self.send(400, b'{"ok":false,"refused":"unknown-app"}', "application/json")
            return self.send(200, json.dumps(measure(app)).encode("utf-8"), "application/json")
        return self.send(404, b'{"ok":false,"refused":"not-found"}', "application/json")


def serve(port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def post(path: str) -> dict:
    with urllib.request.urlopen(SHELL + path, timeout=60) as response:
        return json.loads(response.read() or b"{}")


def probe() -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + ((" — " + detail) if detail else ""))

    server = serve(0)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30) as response:
            page = response.read().decode("utf-8")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/report.json", timeout=30) as response:
            body = json.loads(response.read())
        check("popit-surface", 'data-popit="window-audit"' in page
              and 'id="audit-table"' in page and 'id="refused-count"' in page, f"port {port}")
        check("report-schema", body.get("schema") == SCHEMA
              and len(body.get("rows") or []) == len(APPS),
              f"{len(body.get('rows') or [])} rows")
        for app in APPS:
            row = measure(app)
            check(f"window-measured-{app}", row.get("state") == "passed",
                  f"{row.get('detail', '')} · at {row.get('at') or '—'}")
        _, ledger = http("/api/toast/apps")
        foreign = (ledger or {}).get("foreign") or {}
        for name, code in FOREIGN.items():
            refused = ((foreign.get(name) or {}).get("refused") or {}).get("code")
            check(f"store-rejects-{name}", refused == code,
                  f"foreign {name}: {refused or 'listed as a package'}")
        # The SpringBoard is a package inside this window: it is hidden while it loads and
        # shown only after it reports its own paint, and it loads from this window's origin.
        # The window is reloaded first so it runs the package's current script.
        http("/api/toast/window/audit", {"app": "desk"})
        time.sleep(5)
        first = window_probe("springboardAudit")
        check("springboard-hidden-until-painted",
              bool(first) and first.get("pending") == "true" and first.get("painted") is False,
              json.dumps(first)[:140])
        time.sleep(4)
        second = window_probe("springboardState")
        # The measurement reloads the frame as the plain signed page once it has reported; the
        # integrity reading is taken from that page, not from a frame mid-reload.
        time.sleep(7)
        integrity = {}
        for _attempt in range(3):
            integrity = window_probe("frameIntegrity") or {}
            if "frames" in integrity:
                break
            time.sleep(3)
        spring = registry().get("springboard") or {}

        def revision(text: object) -> str:
            found = re.search(r"app-springboard@(\d+)", str(text or ""))
            return found.group(1) if found else ""

        check("springboard-frame-is-the-signed-package",
              str(integrity.get("path") or "") == "/phone.html"
              and bool(revision(integrity.get("identity")))
              and revision(integrity.get("identity")) == revision(spring.get("identity")),
              f"frame {integrity.get('identity') or '—'} vs package {spring.get('identity') or '—'}")
        check("springboard-is-the-only-launcher",
              integrity.get("frames") == 1 and integrity.get("launchers") == 0,
              f"{integrity.get('frames')} frame(s), {integrity.get('launchers')} extra launcher(s)")
        check("springboard-revealed-after-paint",
              bool(second) and second.get("ready") == "true" and second.get("painted") is True
              and str(second.get("src") or "").startswith(str(second.get("origin") or "")),
              json.dumps(second)[:140])
        http("/api/toast/window/audit", {"app": "desk"})
        receipt = {"schema": SCHEMA, "at": iso(), "checks": checks,
                   "passed": sum(1 for row in checks if row["ok"]),
                   "failed": sum(1 for row in checks if not row["ok"])}
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(f"\n{receipt['passed']} passed, {receipt['failed']} failed -> {RECEIPT}")
        return 0 if receipt["failed"] == 0 else 1
    finally:
        server.shutdown()


def main(argv: list[str]) -> int:
    action = argv[1] if len(argv) > 1 else "probe"
    if action == "report":
        body = report()
        PAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        PAGE_REPORT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(body["rows"], indent=2))
        return 0
    if action == "serve":
        server = serve()
        print(f"popit window audit http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()
        return 0
    return probe()


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
