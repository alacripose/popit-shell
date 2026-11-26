"""The capacity audit: work cut down for context, capacity or session length is refused.

The owner's rule, verbatim: *"if you keep refusing to do work or cut down on work because
of context/capacity/session leght or assumed time then you will have to look for those
failurs so the cua driven harness development will refuse those behaviors"*.

An assistant that stops a unit because the conversation is long, because the context is
nearly full or because it assumes the work will not fit writes that reason into a decision
record: an authority row, a probe note, a doc. This audit reads those records and refuses
the reason by name (`capacity-excuse`) unless the record also names the unit the work was
cut from and the place it is owed — that is the acknowledgement, and it lives in
`logs/capacity/ack.jsonl`. Cutting work is allowed when it is handed to a driver as a wish
or a ticket; it is not allowed as a consequence of the session's own size.

The audit ships a Popit surface (`data-popit="capacity-audit"`) and its probe reads that
page over loopback, because a printed pass is not a reading.

    python tools/capacity_audit.py report    # write artifacts/receipts/capacity.json
    python tools/capacity_audit.py serve     # the Popit page on http://127.0.0.1:5220
    python tools/capacity_audit.py probe     # start, read / and /report.json, fail by name
    python tools/capacity_audit.py ack <digest> <unit>   # name the work a hit cut
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "artifacts" / "receipts" / "capacity.json"
ACK = ROOT / "logs" / "capacity" / "ack.jsonl"
UI = ROOT / "tools" / "capacity_ui" / "index.html"
PORT = int(os.environ.get("POPIT_CAPACITY_PORT") or "5220")
SCHEMA = "popit.capacity/1"

# The families of decision record this audit reads. Source code, the gate's own rules and
# the owner's instruction files are not scanned: the excuse is written where decisions are.
SOURCES = (
    ("authority", "logs/authority/*.jsonl"),
    ("probes", "data/probes/*.md"),
    ("docs", "docs/*.md"),
)

# A reason to stop, in the words a session writes it. Each pattern is a phrase, not a word:
# "time" alone is a timestamp, and "length" alone is a measurement.
EXCUSES = (
    r"context (?:length|window|limit)",
    r"out of context",
    r"session (?:length|limit|budget)",
    r"(?:remaining|available|my) capacity",
    r"capacity (?:budget|limit)",
    r"running (?:low|out) of (?:time|capacity|context)",
    r"out of (?:time|budget)",
    r"next (?:turn|session) I(?:'ll| will)",
    r"for now,? (?:I(?:'ll| will) )?stop",
    r"too (?:long|large) to",
    r"context (?:ran|is) (?:out|full)",
    r"token budget",
)
EXCUSE_RE = re.compile("|".join(f"(?:{pattern})" for pattern in EXCUSES), re.IGNORECASE)
# A line that quotes the rule rather than obeying the excuse is not a hit: the rule itself
# has to be readable in the records it governs.
QUOTE_RE = re.compile(r"verbatim|owner's rule|the rule\b", re.IGNORECASE)


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def digest(where: str, text: str) -> str:
    return "sha256:" + hashlib.sha256(f"{where}\n{text}".encode("utf-8")).hexdigest()


def acks() -> dict[str, str]:
    """Acknowledged hits: digest -> the unit that names where the cut work is owed."""
    rows: dict[str, str] = {}
    if not ACK.is_file():
        return rows
    for line in ACK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("digest") and row.get("unit"):
            rows[str(row["digest"])] = str(row["unit"])
    return rows


def scan() -> list[dict]:
    acknowledged = acks()
    rows: list[dict] = []
    for family, pattern in SOURCES:
        for path in sorted(ROOT.glob(pattern)):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, text in enumerate(lines, 1):
                if QUOTE_RE.search(text):
                    continue
                # A phrase inside backticks is the detector's own vocabulary, not a session
                # explaining why it stopped.
                spoken = re.sub(r"`[^`]*`", "", text)
                match = EXCUSE_RE.search(spoken)
                if not match:
                    continue
                key = digest(f"{relative}:{number}", text.strip())
                rows.append({
                    "family": family,
                    "file": relative,
                    "line": number,
                    "excerpt": text.strip()[:220],
                    "match": match.group(0),
                    "digest": key,
                    "state": "acknowledged" if key in acknowledged else "refused",
                    "unit": acknowledged.get(key, ""),
                })
    return rows


def report() -> dict:
    rows = scan()
    refused = [row for row in rows if row["state"] == "refused"]
    body = {
        "schema": SCHEMA,
        "at": iso(),
        "scanned": [family for family, _ in SOURCES],
        "acknowledged": len(rows) - len(refused),
        "refused": len(refused),
        "rows": rows,
        "act": ("name the unit the cut work belongs to (`python tools/capacity_audit.py ack "
                "<digest> <unit>`) or do the work"),
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return body


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Popit capacity audit</title>
<style>
  :root { --ground: #0c0e11; --ink: #e7e3d8; --muted: #8d8a80; --gold: #f0c454;
          --edge: #23262b; --bad: #e2765f; }
  body { margin: 0; background: var(--ground); color: var(--ink);
         font: 14px/1.5 "Archivo", "Segoe UI", sans-serif; }
  header { border-bottom: 1px solid var(--edge); padding: 18px 22px; }
  h1 { margin: 0; font-size: 15px; letter-spacing: .14em; text-transform: uppercase; }
  .mark { color: var(--gold); }
  main { padding: 18px 22px 40px; }
  .state { display: inline-block; padding: 2px 8px; border: 1px solid var(--edge);
           font-family: "IBM Plex Mono", monospace; font-size: 12px; }
  .state.refused { color: var(--bad); border-color: var(--bad); }
  .state.acknowledged { color: var(--gold); border-color: var(--gold); }
  table { border-collapse: collapse; width: 100%; margin-top: 14px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--edge);
           vertical-align: top; font-size: 13px; }
  th { color: var(--muted); font-weight: 500; text-transform: uppercase;
       letter-spacing: .1em; font-size: 11px; }
  code { font-family: "IBM Plex Mono", monospace; color: var(--muted); }
</style>
</head>
<body data-popit="capacity-audit">
<header>
  <h1><span class="mark">&#9671;</span> capacity audit &middot;
      <span id="capacity-state">reading</span></h1>
</header>
<main>
  <p>Work cut for context, capacity or session length is refused unless the record names
     the unit that still owes it. <code id="receipt-path">artifacts/receipts/capacity.json</code></p>
  <table id="excuse-table">
    <thead><tr><th>state</th><th>record</th><th>excerpt</th><th>unit</th></tr></thead>
    <tbody><tr><td colspan="4">reading&hellip;</td></tr></tbody>
  </table>
</main>
<script>
fetch("/report.json").then((reply) => reply.json()).then((body) => {
  const state = document.getElementById("capacity-state");
  state.textContent = body.refused ? `refused ${body.refused}` : "clean";
  state.className = "state " + (body.refused ? "refused" : "acknowledged");
  const rows = body.rows || [];
  const tbody = document.querySelector("#excuse-table tbody");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4">no capacity excuse in the decision records</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((row) =>
    `<tr><td><span class="state ${row.state}">${row.state}</span></td>` +
    `<td><code>${row.file}:${row.line}</code></td>` +
    `<td>${row.excerpt.replace(/[<>&]/g, (c) => ({"<": "&lt;", ">": "&gt;", "&": "&amp;"}[c]))}</td>` +
    `<td>${row.unit || "&mdash;"}</td></tr>`).join("");
});
</script>
</body>
</html>
"""


def serve(port: int = PORT) -> ThreadingHTTPServer:
    UI.parent.mkdir(parents=True, exist_ok=True)
    UI.write_text(PAGE, encoding="utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # noqa: D401 - quiet server
            return

        def send(self, body: bytes, kind: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server contract
            if self.path in ("/", "/index.html"):
                self.send(UI.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/report.json":
                if not RECEIPT.is_file():
                    report()
                self.send(RECEIPT.read_bytes(), "application/json; charset=utf-8")
            else:
                self.send_response(404)
                self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server


def probe() -> int:
    body = report()
    server = serve()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    rows: list[dict] = []
    try:
        base = f"http://127.0.0.1:{PORT}"
        for _ in range(40):
            try:
                page = urllib.request.urlopen(f"{base}/", timeout=2).read().decode("utf-8")
                served = json.loads(urllib.request.urlopen(f"{base}/report.json",
                                                          timeout=2).read())
                break
            except (OSError, ValueError, urllib.error.HTTPError):
                time.sleep(0.1)
        else:
            page, served = "", {}
    finally:
        server.shutdown()

    def check(name: str, passed: bool, detail: str) -> None:
        rows.append({"name": name, "passed": bool(passed), "detail": detail})

    markers = ('data-popit="capacity-audit"', 'id="capacity-state"', 'id="excuse-table"',
               'id="receipt-path"')
    check("capacity-page-is-a-popit-surface",
          all(marker in page for marker in markers),
          f"missing {[m for m in markers if m not in page]}")
    check("capacity-report-is-served",
          served.get("schema") == SCHEMA and served.get("scanned") == list(
              family for family, _ in SOURCES),
          f"schema {served.get('schema')}, scanned {served.get('scanned')}")
    check("capacity-receipt-matches-the-scan",
          served.get("refused") == body.get("refused") and served.get("rows") == body.get("rows"),
          f"refused {served.get('refused')} vs {body.get('refused')}")
    check("no-unacked-capacity-excuse",
          not [row for row in body.get("rows") or [] if row.get("state") == "refused"],
          "; ".join(f"{row['file']}:{row['line']}" for row in body.get("rows") or []
                    if row.get("state") == "refused") or "none")
    passed = sum(1 for row in rows if row["passed"])
    out = RECEIPT.with_suffix(".probe.json")
    out.write_text(json.dumps({"schema": "popit.capacity-probe/1", "rows": rows,
                               "passed": passed, "failed": len(rows) - passed},
                              indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(("PASS " if row["passed"] else "FAIL ") + row["name"] + " - " + str(row["detail"]))
    print(f"{passed} passed, {len(rows) - passed} failed -> {out}")
    return 0 if passed == len(rows) else 1


def acknowledge(key: str, unit: str) -> int:
    ACK.parent.mkdir(parents=True, exist_ok=True)
    with ACK.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": iso(), "digest": key.strip(), "unit": unit.strip()},
                                ensure_ascii=False) + "\n")
    print(f"acknowledged {key} -> {unit}")
    return 0


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "report"
    if command == "report":
        body = report()
        print(f"{body['refused']} refused, {body['acknowledged']} acknowledged -> {RECEIPT}")
        for row in body["rows"]:
            print(f"  {row['state']:12} {row['file']}:{row['line']}  {row['excerpt'][:90]}")
        return 0 if not body["refused"] else 1
    if command == "serve":
        server = serve()
        print(f"capacity audit on http://127.0.0.1:{PORT}")
        server.serve_forever()
        return 0
    if command == "probe":
        return probe()
    if command == "ack" and len(argv) > 3:
        return acknowledge(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
