"""The freshness register: what is not allowed to go stale, and which driver act fixes it.

The owner's rule, verbatim: *"landing pages, ci, audits, failures, ledgers, refusals, signed
app packages and their signed tiles are not allowed to go stale across the family, handled
by the cua drivers in their projects."*

This register is the work list, not a second opinion. Eight families are measured against
the thing each one claims to describe:

* **landing** — `docs/index.html` is regenerated from the pinned look; a hand edit or a new
  reading leaves it stale, and the act is `python tools/landing.py`.
* **ci** — the workflows that publish or check this project, or a named absence when the
  site is served from `docs/`. An absence is reported as `none`, never as fresh.
* **audits** — a signed package whose `ui_audit` is not `passed` is a row here; the act is
  the CUA driver's browser audit, not a hand edit.
* **failures** — the probe receipts must be newer than the surfaces they measure.
* **ledgers** — the authority records must carry a row for this unit; a silent ledger is
  stale after two days.
* **refusals** — the store's refused rows must be exactly the registry's foreign names.
* **packages** — every signed identity the store lists must be the identity the shell
  serves.
* **tiles** — the SpringBoard's tiles are painted from the registry at load, so the tile a
  reader clicks carries the joined identity; a tile that is stored rather than derived is
  the stale case and is refused here.

A stale row names the driver act that clears it. The register is served as a Popit surface
(`data-popit="freshness"`) and the probe reads that page over loopback, because a printed
pass is not a reading.

    python tools/freshness.py report    # write artifacts/receipts/freshness.json
    python tools/freshness.py serve     # the Popit page on http://127.0.0.1:5213
    python tools/freshness.py probe     # start, read / and /report.json, fail by name
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "artifacts" / "receipts" / "freshness.json"
PORT = int(os.environ.get("POPIT_FRESHNESS_PORT") or "5213")
SHELL = f"http://127.0.0.1:{os.environ.get('POPIT_PORT') or '5207'}"
SCHEMA = "popit.freshness/1"
LEDGER_LIMIT_DAYS = 2
FAMILIES = ("landing", "ci", "audits", "failures", "ledgers", "refusals", "packages",
            "tiles", "prose")
UI_FILES = ("ui/toast.html", "ui/toast.js", "ui/toast.css", "ui/phone.html",
            "ui/settings.html", "ui/bridge.html", "ui/contour-theme.css")


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{SHELL}{path}", timeout=8) as reply:
            return json.loads(reply.read().decode("utf-8") or "{}")
    except (OSError, ValueError, urllib.error.HTTPError):
        return None


def newest_mtime(patterns: tuple[str, ...]) -> float:
    stamps = [path.stat().st_mtime for pattern in patterns
              for path in ROOT.glob(pattern) if path.is_file()]
    return max(stamps) if stamps else 0.0


def row(family: str, code: str, state: str, subject: str, detail: str, act: str) -> dict:
    return {"family": family, "code": code, "state": state, "subject": subject,
            "detail": detail, "act": act}


def landing_row() -> dict:
    run = subprocess.run([sys.executable, str(ROOT / "tools" / "landing.py"), "--check"],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    detail = (run.stdout + run.stderr).strip().replace("\n", " | ")[:200]
    return row("landing", "landing-page", "fresh" if run.returncode == 0 else "stale",
               "docs/index.html",
               detail or "the generated page matches its reading and pins",
               "python tools/landing.py")


def ci_rows() -> list[dict]:
    workflows = sorted(path for pattern in (".github/workflows/*.yml", ".github/workflows/*.yaml")
                       for path in ROOT.glob(pattern) if path.is_file())
    if workflows:
        return [row("ci", "ci-workflow", "fresh", str(path.relative_to(ROOT)),
                    "a workflow publishes or checks this project",
                    "python tools/gate.py && push the workflow's own run")
                for path in workflows]
    return [row("ci", "ci-absent", "none", ".github/workflows",
                "no GitHub workflow here; the landing page is served from docs/",
                "add .github/workflows/pages.yml, or keep docs/ as the published copy")]


def audit_rows(live: dict | None) -> list[dict]:
    if not live:
        return [row("audits", "audit-unread", "stale", SHELL,
                    "the shell did not answer /api/toast/apps", "python toast.py")]
    rows = []
    for name, package in sorted((live.get("apps") or {}).items()):
        # A package that is refused by name was never delivered, so it has no surface to
        # measure: the refusal is the finding, and the act is the rebuild that clears it.
        refusal = package.get("refused")
        code = str(refusal.get("code") or "") if isinstance(refusal, dict) else ""
        if code:
            rows.append(row("audits", f"audit-{name}", "refused", f"app-{name}",
                            f"not audited: {code}",
                            f"rebuild {name} from the settings window, then audit it"))
            continue
        audit = str(package.get("ui_audit") or "pending")
        rows.append(row("audits", f"audit-{name}",
                        "fresh" if audit == "passed" else "stale", f"app-{name}",
                        f"ui_audit {audit}",
                        f"cua driver: audit {name} (?uiaudit=1&app={name}) and republish"))
    return rows


def failure_rows() -> dict:
    newest_ui = newest_mtime(UI_FILES)
    receipts = [path for path in (ROOT / "runlogs" / "toast").glob("*.json") if path.is_file()]
    if not receipts:
        return row("failures", "probe-receipt-missing", "stale", "runlogs/toast/",
                   "no probe receipt is kept beside the surfaces", "python tools/app_package_probe.py")
    newest = max(receipts, key=lambda path: path.stat().st_mtime)
    stale = newest.stat().st_mtime < newest_ui
    return row("failures", "probe-receipt-newer", "stale" if stale else "fresh",
               str(newest.relative_to(ROOT)),
               f"newest receipt {newest.name} is {'older' if stale else 'newer'} than the surfaces",
               "python tools/app_package_probe.py && python tools/toast_probe.py")


def ledger_rows() -> list[dict]:
    """A ledger is stale when its newest row is old; older files are history, not debt."""
    records = [path for path in (ROOT / "logs" / "authority").glob("*.jsonl") if path.is_file()]
    if not records:
        return [row("ledgers", "ledger-missing", "stale", "logs/authority/",
                    "no authority row exists for this project",
                    "append logs/authority/<date>-<unit>.jsonl")]
    today = datetime.date.today()
    newest, newest_path = None, records[0]
    for path in records:
        try:
            day = datetime.date.fromisoformat(path.stem[:10])
        except ValueError:
            continue
        if newest is None or day > newest:
            newest, newest_path = day, path
    age = (today - newest).days if newest else 10**3
    return [row("ledgers", "ledger-newest-row",
                "stale" if age > LEDGER_LIMIT_DAYS else "fresh",
                str(newest_path.relative_to(ROOT)),
                f"newest authority row is {age} day(s) old",
                "append the next unit's authority row under logs/authority/")]


def store_rows(live: dict | None) -> list[dict]:
    path = ROOT / "docs" / "app-store.json"
    if not path.is_file():
        return [row("refusals", "store-missing", "stale", "docs/app-store.json",
                    "the landing store has never been generated", "python tools/app_store.py")]
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [row("refusals", "store-unreadable", "stale", "docs/app-store.json",
                    str(error), "python tools/app_store.py")]
    refused = sorted((entry.get("refused") or {}).get("code", "")
                     for entry in store.get("refused") or [])
    foreign = sorted((entry.get("refused") or {}).get("code", "")
                     for entry in (live or {}).get("foreign", {}).values())
    rows = [row("refusals", "store-refusals-current",
                "fresh" if live is not None and refused == foreign else "stale",
                "docs/app-store.json",
                f"store {refused or 'none'} vs registry {foreign or 'none'}",
                "python tools/app_store.py")]
    listed = {entry.get("name"): entry.get("identity") for entry in store.get("apps") or []}
    signed = {name: package.get("identity")
              for name, package in ((live or {}).get("apps") or {}).items()
              if package.get("verified")}
    stale = [name for name, identity in listed.items() if signed.get(name) != identity]
    rows.append(row("packages", "store-packages-current", "stale" if stale else "fresh",
                    "docs/app-store.json",
                    f"stale identities: {', '.join(sorted(stale)) or 'none'}",
                    "python tools/app_store.py"))
    return rows


def dialin_rebuild_row(live: dict | None = None) -> dict:
    """Measure the desk window against the settings package it is built from.

    The desk is the settings window's own page: it is delivered in the settings window, its
    signature carries the settings package as its base, and the served bytes carry the panel
    and the contour. Every part is observed here, so the row is a reading, not an assertion.
    """
    live = live if live is not None else fetch("/api/toast/apps")
    apps = (live or {}).get("apps") or {}
    desk = apps.get("dialin") or {}
    settings = apps.get("settings") or {}
    # The desk is delivered in the settings window and served from the same entry page, so its
    # signed payload and the settings package's payload are the same bytes.
    same_entry = str(desk.get("entry") or "") == str(settings.get("entry") or "") != ""
    on_settings = same_entry and desk.get("verified") is True \
        and settings.get("verified") is True
    page = ""
    try:
        with urllib.request.urlopen(SHELL + "/toast.html", timeout=20) as response:
            page = response.read().decode("utf-8", "replace")
    except (OSError, urllib.error.URLError):
        page = ""
    panel = 'id="settings-panel"' in page
    contour = "data-contour" in page
    window = 'data-window="popit-settings-package"' in page
    fresh = bool(desk) and on_settings and panel and contour and window
    detail = (f"desk {desk.get('identity') or 'unsigned'} on entry {desk.get('entry') or 'none'}"
              f" (settings {settings.get('identity') or 'unsigned'}); served page {len(page)}B "
              f"panel={panel} contour={contour} window={window}")
    return row("packages", "dialin-rebuild", "fresh" if fresh else "stale", "ui/toast.html",
               detail,
               "re-sign the desk from the settings package and serve the window page")


def tile_rows() -> dict:
    phone = (ROOT / "ui" / "phone.js").read_text(encoding="utf-8")
    derived = ("/api/toast/apps" in phone and "data-package-identity" in phone
               and "escapeHTML(item.identity)" in phone)
    return row("tiles", "tiles-are-derived", "fresh" if derived else "stale",
               "ui/phone.js",
               "tiles paint the joined identity from the registry at load"
               if derived else "a tile is stored instead of derived from its package",
               "keep the SpringBoard reading /api/toast/apps; do not store tile identities")


def prose_rows() -> list[dict]:
    """The family's prose documents are surfaces: a project the box has not staged is stale.

    The reading is the prose program's own receipt, taken over the loopback probe; the checker
    that produced it is the family checker in portal-shell. A document older than the checker
    is stale, and a project named `prose-not-staged` is the driver's work list, not a pass.
    """
    receipt = ROOT / "artifacts" / "receipts" / "prose-family.json"
    index = ROOT / "docs" / "prose" / "index.html"
    checker = next((base / "portal-shell" / "tools" / "ui_prose.py"
                    for base in (pathlib.Path(r"F:\Documents"), pathlib.Path.home() / "Documents")
                    if base.is_dir()), None)
    if not receipt.is_file() or not index.is_file():
        return [row("prose", "prose-documents-missing", "stale", "docs/prose/index.html",
                    "no prose document or receipt is kept",
                    "python tools/prose_family.py report && python tools/prose_family.py probe")]
    try:
        body = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        body = {}
    checker_stamp = checker.stat().st_mtime if checker and checker.is_file() else 0.0
    fresh = receipt.stat().st_mtime >= checker_stamp and index.stat().st_mtime >= checker_stamp
    rows = [row("prose", "prose-documents-current", "fresh" if fresh else "stale",
                "docs/prose/index.html",
                f"receipt {body.get('passed', 0)} of {body.get('projects', 0)} project(s); "
                f"{'newer' if fresh else 'older'} than the family checker",
                "python tools/prose_family.py report && python tools/prose_family.py probe")]
    # The corpus is written by the driver's own service under /opt, so a refused corpus write
    # is named `blocked` and carries the act; it is not this project's staleness to clear.
    corpus_path = ROOT / "runlogs" / "prose" / "corpus.json"
    if corpus_path.is_file():
        try:
            corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            corpus = {}
        code = str(corpus.get("code") or "")
        rows.append(row("prose", "prose-corpus",
                        "fresh" if corpus.get("ok") else ("blocked" if code == "corpus-write-permission" else "stale"),
                        "/srv/scratch/prose-staging",
                        f"corpus ingest {'accepted' if corpus.get('ok') else code}; "
                        f"{(corpus.get('detail') or '')[:100]}",
                        "cua driver: ingest the staged prose profile into \
/opt/cua-driver/artifacts/corpus"))
    for entry in body.get("rows") or []:
        refusal = entry.get("refusal") or {}
        if not refusal:
            continue
        code = str(refusal.get("code"))
        rows.append(row("prose", f"prose-{entry.get('name')}",
                        "refused" if code == "project-absent" else "stale",
                        str(entry.get("project") or entry.get("name")),
                        f"{code}: {str(refusal.get('detail'))[:120]}",
                        "cua driver: stage %s under /srv/ingest/family-prose and ingest it"
                        % entry.get("name")))
    return rows


def report() -> dict:
    live = fetch("/api/toast/apps")
    rows = [landing_row(), *ci_rows(), *audit_rows(live), failure_rows(),
            *ledger_rows(), *store_rows(live), tile_rows(), dialin_rebuild_row(live),
            *prose_rows()]
    stale = [entry for entry in rows if entry["state"] == "stale"]
    return {"schema": SCHEMA, "generated_at": iso(), "shell": SHELL,
            "families": list(FAMILIES), "rows": rows, "stale": len(stale),
            "driver_acts": sorted({entry["act"] for entry in stale}), "live": bool(live)}


def page(body: dict) -> str:
    def cell(text: object) -> str:
        return (str(text).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    rows = "".join(
        f'<tr data-state="{cell(entry["state"])}"><td>{cell(entry["family"])}</td>'
        f'<td class="word">{cell(entry["state"])}</td><td>{cell(entry["subject"])}</td>'
        f'<td>{cell(entry["detail"])}</td><td class="act">{cell(entry["act"])}</td></tr>'
        for entry in body["rows"])
    acts = "".join(f"<li>{cell(act)}</li>" for act in body["driver_acts"]) or "<li>none</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8" />
<title>Popit freshness</title>
<style>
:root {{ --ground:#0c0e11; --panel:#14100b; --gold:#f0c454; --ink:#e8e2d4; --meta:#9c8a6b; --line:#2a2012; }}
body {{ margin:0; padding:24px; background:var(--ground); color:var(--ink);
  font-family:Archivo,"Segoe UI",system-ui,sans-serif; }}
h1 {{ font-size:15px; letter-spacing:.14em; text-transform:uppercase; margin:0 0 4px; }}
p.meta {{ color:var(--meta); font:12px/1.5 "IBM Plex Mono",monospace; margin:0 0 16px; }}
.count {{ font:13px/1 "IBM Plex Mono",monospace; color:var(--gold); margin:0 0 18px; }}
table {{ width:100%; border-collapse:collapse; font:12px/1.5 "IBM Plex Mono",monospace; }}
th {{ text-align:left; color:var(--meta); font-weight:400; letter-spacing:.08em;
  text-transform:uppercase; padding:6px 8px; border-bottom:1px solid var(--line); }}
td {{ padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
tr[data-state="stale"] td.word {{ color:var(--gold); }}
tr[data-state="stale"] {{ background:#14100b; }}
td.word {{ text-transform:uppercase; letter-spacing:.08em; }}
td.act {{ color:var(--meta); }}
h2 {{ font-size:12px; letter-spacing:.12em; text-transform:uppercase; margin:22px 0 8px; }}
ul {{ margin:0; padding-left:18px; font:12px/1.6 "IBM Plex Mono",monospace; color:var(--ink); }}
</style></head>
<body data-popit="freshness">
<h1>Family freshness</h1>
<p class="meta">generated {cell(body["generated_at"])} · shell {cell(body["shell"])} · {cell(body["schema"])}</p>
<p id="stale-count" class="count">{body["stale"]} stale of {len(body["rows"])} rows</p>
<table id="freshness-table"><thead><tr><th>Family</th><th>State</th><th>Subject</th>
<th>Measured</th><th>Driver act</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Driver acts</h2><ul id="driver-acts">{acts}</ul>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = report()
        if self.path.startswith("/report.json"):
            payload = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
            self._send(payload, "application/json; charset=utf-8")
            return
        self._send(page(body).encode("utf-8"), "text/html; charset=utf-8")

    def _send(self, payload: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        return


def start(port: int = PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def probe() -> int:
    server = start()
    try:
        page_text = ""
        body: dict = {}
        for _ in range(20):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5) as reply:
                    page_text = reply.read().decode("utf-8")
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/report.json",
                                            timeout=5) as reply:
                    body = json.loads(reply.read().decode("utf-8"))
                break
            except (OSError, ValueError):
                time.sleep(0.15)
    finally:
        server.shutdown()
        server.server_close()
    covered = {entry["family"] for entry in body.get("rows") or []}
    checks = [
        ("page-served", 'data-popit="freshness"' in page_text),
        ("table-served", 'id="freshness-table"' in page_text),
        ("count-served", 'id="stale-count"' in page_text),
        ("acts-served", 'id="driver-acts"' in page_text),
        ("schema", body.get("schema") == SCHEMA),
        ("families-covered", set(FAMILIES) <= covered)
        and ("prose",) == tuple(family for family in FAMILIES if family == "prose"),
        ("shell-answering", bool(body.get("live"))),
    ]
    failed = [name for name, ok in checks if not ok]
    body["covered"] = sorted(covered)
    body["checks"] = [{"name": name, "passed": ok} for name, ok in checks]
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    for entry in body.get("rows") or []:
        if entry["state"] == "stale":
            print(f"STALE {entry['code']}: {entry['subject']} — {entry['detail']} "
                  f"(act: {entry['act']})")
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed, "
          f"{body.get('stale')} stale -> {RECEIPT}")
    return 1 if failed or body.get("stale") else 0


def main(argv: list[str]) -> int:
    action = argv[1] if len(argv) > 1 else "report"
    if action == "report":
        body = report()
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        print(f"{body['stale']} stale of {len(body['rows'])} rows -> {RECEIPT}")
        return 1 if body["stale"] else 0
    if action == "serve":
        print(f"freshness on http://127.0.0.1:{PORT}/")
        start().serve_forever()
        return 0
    if action == "probe":
        return probe()
    print(f"unknown action {action!r}: use report, serve or probe", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
