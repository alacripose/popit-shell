"""The hang-up probe: a hang-up is a hang-up, and the lane dials back once.

The desk had no hang-up. Ending a line posted `/api/toast/call/close` with a proof path, so
the owner hanging up was archived as *work completed* and nothing rang back. This probe opens
a scratch line, hangs it up the way the desk now does, and reads the archive for the two rows
that must exist: `call-hangup` naming the line, and `call-callback` naming the new line.

A callback that is itself hung up must not dial again. The probe checks that too, because a
hang-up that chained would ring the owner for as long as he kept ending it.

    python tools/hangup_probe.py            # against the shell on 127.0.0.1:5207
    python tools/hangup_probe.py --port 5210
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "runlogs" / "toast" / "archive.jsonl"
RECEIPT = ROOT / "artifacts" / "receipts" / "hangup-probe.json"
PROOF = "data/probes/2026-11-26-hangup-callback.md"


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def post(base: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        base + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=40) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        try:
            return {"ok": False, "status": error.code, **json.loads(text)}
        except json.JSONDecodeError:
            return {"ok": False, "status": error.code, "text": text[:300]}


def get(base: str, path: str) -> dict:
    try:
        with urllib.request.urlopen(base + path, timeout=40) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as error:
        return {"ok": False, "error": str(error)}


def rows_since(moment: str) -> list[dict]:
    if not ARCHIVE.is_file():
        return []
    out = []
    for line in ARCHIVE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("at") or "") >= moment:
            out.append(row)
    return out


PAGE_ID = "hangup-probe"
POPIT_RECEIPT = ROOT / "artifacts" / "receipts" / "hangup-probe-popit.json"


def last_receipt() -> dict:
    if not RECEIPT.is_file():
        return {"schema": "popit.hangup-probe/1", "checks": [], "line": "", "callback": ""}
    try:
        return json.loads(RECEIPT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema": "popit.hangup-probe/1", "checks": [], "line": "", "callback": ""}


def page(receipt: dict) -> str:
    checks = receipt.get("checks") or []
    rows = "".join(
        "<tr><td class=mono>{check}</td><td class={cls}>{state}</td><td>{detail}</td></tr>".format(
            check=row.get("check", ""), cls="ok" if row.get("ok") else "bad",
            state="pass" if row.get("ok") else "refused",
            detail=(row.get("detail") or "").replace("<", "&lt;"))
        for row in checks)
    failures = len([row for row in checks if not row.get("ok")])
    return """<!doctype html><meta charset=utf-8>
<title>hang-up probe</title>
<style>
:root{{--ground:#0c0e11;--gold:#f0c454;--ink:#e8e6e1;--dim:#9aa0a6;--line:#23262b}}
body{{background:var(--ground);color:var(--ink);font:14px/1.5 Archivo,system-ui,sans-serif;margin:0;padding:24px}}
h1{{font:600 18px/1.3 "IBM Plex Mono",monospace;letter-spacing:.04em;margin:0 0 4px}}
.mono,td.mono{{font-family:"IBM Plex Mono",monospace}}
.meta{{color:var(--dim);margin:0 0 18px}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid var(--line);padding:6px 8px;text-align:left}}
th{{color:var(--dim);font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
.ok{{color:var(--ink)}} .bad{{color:var(--gold)}}
.sum{{margin-top:14px;font-family:"IBM Plex Mono",monospace;color:var(--gold)}}
</style>
<div data-popit="{pid}">
<h1>Hang-up probe</h1>
<p class=meta>line {line} · callback {callback} · last drill {at}</p>
<table id="hangup-checks"><thead><tr><th>check</th><th>state</th><th>detail</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class=sum id="hangup-summary">{passed} passed · {failed} refused</p>
</div>
""".format(pid=PAGE_ID, line=receipt.get("line") or "(none)",
           callback=receipt.get("callback") or "(none)", at=receipt.get("at") or "(never)",
           rows=rows or '<tr><td colspan=3>no drill recorded yet</td></tr>',
           passed=len(checks) - failures, failed=failures)


def serve(port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401 - quiet server
            return

        def do_GET(self):  # noqa: N802
            if self.path.startswith("/report.json"):
                body = json.dumps(last_receipt(), indent=2).encode("utf-8")
                kind = "application/json"
            elif self.path in ("/", "/index.html"):
                body = page(last_receipt()).encode("utf-8")
                kind = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    print(f"hang-up probe on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def probe(port: int) -> int:
    """Read the page and its report; a drill that ran but shows nothing is a refusal."""
    import threading
    import time
    import urllib.error
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'} {name} · {detail}")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):  # noqa: N802
            if self.path.startswith("/report.json"):
                body = json.dumps(last_receipt(), indent=2).encode("utf-8")
                kind = "application/json"
            else:
                body = page(last_receipt()).encode("utf-8")
                kind = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(20):
            try:
                html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.2)
        else:
            html = ""
        report = json.loads(urllib.request.urlopen(base + "/report.json", timeout=20).read())
    finally:
        server.shutdown()
    check("surface-serves", bool(html), f"{len(html)} byte(s) of page" if html
          else "surface-absent: no page answered")
    check("surface-is-marked", f'data-popit="{PAGE_ID}"' in html, "data-popit on the page")
    check("surface-has-the-checks", 'id="hangup-checks"' in html, "#hangup-checks present")
    check("report-schema", report.get("schema") == "popit.hangup-probe/1", str(report.get("schema")))
    rows = report.get("checks") or []
    check("report-carries-the-drill", bool(report.get("line")), f"line {report.get('line') or '(none)'}")
    check("drill-has-no-refusal", bool(rows) and all(row.get("ok") for row in rows),
          f"{len([r for r in rows if not r.get('ok')])} refused of {len(rows)}")
    receipt = {"schema": "popit.hangup-probe/popit", "at": datetime.datetime.now(
        datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "port": port, "checks": checks, "failed": [row for row in checks if not row["ok"]]}
    POPIT_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    POPIT_RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"{len(checks) - len(receipt['failed'])} passed, {len(receipt['failed'])} failed -> {POPIT_RECEIPT}")
    return 0 if not receipt["failed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5207)
    parser.add_argument("--agent", default="Whisper")
    parser.add_argument("--serve", type=int, default=0)
    parser.add_argument("--probe", type=int, default=0)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return 0
    if args.probe:
        return probe(args.probe)
    base = f"http://127.0.0.1:{args.port}"
    started = iso()
    checks = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'} {name} · {detail}")

    # A drill must not leave a line behind, and a leftover line would block the next run
    # (`call-open`). Clear the scratch agent's lines first, following one callback each time.
    cleared = 0
    for _ in range(4):
        state = get(base, "/api/toast")
        actives = ((state.get("calls") or {}).get("actives") or [])
        mine = [row for row in actives if row.get("agent") == args.agent]
        if not mine:
            break
        for row in mine:
            post(base, "/api/toast/call/close", {"id": row["id"], "hangup": True})
            cleared += 1

    opened = post(base, "/api/toast/call/open",
                  {"civilian": "Alacrity", "agent": args.agent,
                   "wish": "probe: hang-up drill", "proof": PROOF, "minutes": 1,
                   "allow_multiple": True})
    line = (opened.get("call") or {}).get("id") or ""
    check("probe-line-opened", bool(line), str(line or opened.get("refused")))
    if not line:
        RECEIPT.write_text(json.dumps({"schema": "popit.hangup-probe/1", "at": started,
                                       "checks": checks}, indent=2), encoding="utf-8")
        return 1

    ended = post(base, "/api/toast/call/close",
                 {"id": line, "evidence": PROOF, "hangup": True})
    refused = ended.get("refused") or {}
    check("hangup-is-accepted", not refused,
          f"hangup field {ended.get('hangup')!r}" if not refused
          else f"refused {refused.get('code')}: {str(refused.get('detail'))[:90]}")
    check("hangup-is-marked", ended.get("hangup") is True, f"hangup field {ended.get('hangup')!r}")
    back = ended.get("callback") or {}
    check("callback-dialled", bool(back.get("id")), str(back.get("id") or ended.get("refused_callback")))
    if back.get("id"):
        again = post(base, "/api/toast/call/close",
                     {"id": back["id"], "evidence": PROOF, "hangup": True})
        check("callback-does-not-chain", again.get("callback") is None,
              f"second hang-up returned {again.get('callback')!r}")

    rows = rows_since(started)
    kinds = [row for row in rows if row.get("kind") in ("call-hangup", "call-callback")]
    check("hangup-row-archived", any(row.get("kind") == "call-hangup" and row.get("call") == line
                                     for row in kinds),
          f"{len([r for r in kinds if r.get('kind') == 'call-hangup'])} hang-up row(s)")
    check("callback-row-archived", any(row.get("kind") == "call-callback"
                                       for row in kinds),
          f"{len([r for r in kinds if r.get('kind') == 'call-callback'])} callback row(s)")
    check("no-wish-close-on-hangup",
          not any(row.get("kind") == "event" and f"wish {line} closed with proof" in str(row.get("text"))
                  for row in rows),
          "the hang-up did not read as completed work")

    receipt = {"schema": "popit.hangup-probe/1", "at": started, "line": line,
               "cleared": cleared,
               "callback": back.get("id") or "", "checks": checks,
               "failures": [row for row in checks if not row["ok"]]}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"{len(checks) - len(receipt['failures'])} passed, {len(receipt['failures'])} failed"
          f" -> {RECEIPT}")
    return 0 if not receipt["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
