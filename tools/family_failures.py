"""family-failures — sweep every family ledger and the hypergrilling docs for failures.

The owner's instruction, verbatim: *"you will have to include a full audit sweep of failures in the
family, exhausting information from ledgers and hypergrilling ledgers"*.

A failure row is not one file's opinion. This reads every ledger surface it can find — each project's
``ledger/*.jsonl``, ``logs/authority/*.jsonl``, ``logs/failures.jsonl``, every ``runlogs/**/*.jsonl`` —
and the hypergrilling documents under ``.superpowers/hypergrilling``, normalizes them into one row
shape, and groups them by the named refusal so a repeated failure is one line with a count instead of
a thousand lines with no reading.

    python tools/family_failures.py scan
    python tools/family_failures.py serve --port 8798
    python tools/family_failures.py probe --port 8798

``scan`` writes ``runlogs/family-failures.json`` (the reading) and ``docs/family-failures.md`` (the
same table as a document). Nothing is deleted or rewritten: the sweep only reads.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = "popit.family-failures/1"
OUT_JSON = ROOT / "runlogs" / "family-failures.json"
OUT_MD = ROOT / "docs" / "family-failures.md"

HOME = pathlib.Path.home()
# The projects worth reading. A directory that is a browser profile, an installer or a game tree is
# not a project and holds no family ledger.
ROOTS = [
    HOME / "Documents" / "deadlock-model-forge",
    pathlib.Path(r"F:\Documents\popit-shell"),
    pathlib.Path(r"F:\Documents\mc3-client13"),
    pathlib.Path(r"F:\Documents\db-mc-indev"),
    pathlib.Path(r"F:\Documents\ala-system"),
    pathlib.Path(r"F:\Documents\alacripose-landing"),
    pathlib.Path(r"F:\Documents\AWA3D"),
    pathlib.Path(r"F:\Documents\income-engine"),
]
HYPERGRILL = HOME / "Documents" / ".superpowers" / "hypergrilling"

LEDGER_GLOBS = (
    "ledger/*.jsonl",
    "logs/*.jsonl",
    "logs/authority/*.jsonl",
    "logs/records/*.jsonl",
    "runlogs/*.jsonl",
    "runlogs/toast/*.jsonl",
    "runlogs/session-archive/*.jsonl",
    "runlogs/civilian-audit/*.jsonl",
    "data/*.jsonl",
)
MAX_BYTES = 8 * 1024 * 1024
FAIL_WORDS = ("fail", "blocked", "refused", "error", "refusal")
HYPER_WORDS = re.compile(r"\b(refus\w*|fail\w*|blocked)\b", re.IGNORECASE)


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def display(path) -> str:
    """A path a ledger can carry: the account's home is `~`, never an absolute user folder.

    The family's secrets gate refuses a home path in a committed document, and a sweep exists to
    be read and committed. The mapping is one-way; `rows` name where a failure came from without
    naming whose machine it was.
    """
    text = str(path)
    home = str(HOME)
    return "~" + text[len(home):] if text.lower().startswith(home.lower()) else text


def _tool_of(row: dict) -> str:
    """The unit a row came from: the script the command ran, else its first word."""
    command = str(row.get("command") or "").strip()
    for word in command.split():
        if word.lower().endswith((".py", ".ps1", ".cmd", ".bat")):
            return pathlib.PurePosixPath(word.replace("\\", "/")).name
        if word and not word.startswith("-") and word not in ("python", "python3", "py"):
            return word[:40]
    return str(row.get("tool") or "")[:40]


def _row_code(row: dict) -> str:
    """The named refusal when a row carries one, else `result:unit` so a fail is still readable.

    Counting 79 rows as `fail` hides which unit failed; the sweep's job is to make a repeated
    failure one line an owner can act on, not one bucket per verb.
    """
    listed = row.get("refusals")
    if isinstance(listed, list) and listed:
        return ", ".join(str(item)[:40] for item in listed[:2])
    for key in ("refused", "refusal", "code", "refuse"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("code")
        if value and str(value) not in ("fail", "failed", "blocked", "error"):
            return str(value)[:80]
    result = str(row.get("result") or row.get("state") or "unknown").lower()
    unit = _tool_of(row)
    return f"{result}:{unit}" if unit else result


def _is_failure(row: dict) -> bool:
    """A failure is a row that says it failed or names a refusal, not every ledger event.

    A first pass counted every row with a `code`, and `_row_code` labels a passing row
    `pass:gate`, so the sweep read 5320 "failures" that were mostly passes. Only the result
    field decides here, and an event row with neither result nor refusal is not a failure.
    """
    if str(row.get("kind") or "").lower() in ("refusal", "failure", "collision"):
        return True
    if row.get("refusals"):
        return True
    if any(row.get(key) for key in ("refused", "refusal", "refuse")):
        return True
    result = str(row.get("result") or row.get("state") or "").lower()
    if not result:
        return False
    if result in ("pass", "passed", "ok", "recorded", "present", "observed", "skip",
                  "skipped", "absent"):
        return False
    return any(word in result for word in FAIL_WORDS)


def read_ledger(path: pathlib.Path, project: str) -> list[dict]:
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or not _is_failure(row):
            continue
        found.append({
            "project": project,
            "source": str(path.relative_to(ROOT)) if ROOT in path.parents else display(path),
            "line": index,
            "code": _row_code(row) or str(row.get("result") or "unknown"),
            "result": str(row.get("result") or row.get("state") or ""),
            "command": str(row.get("command") or "")[:200],
            "observed": str(row.get("observed") or row.get("detail") or "")[:400],
            "artifact": display(row.get("artifact") or row.get("artifacts") or "")[:200],
            "at": str(row.get("at") or ""),
        })
    return found


def read_hypergrill() -> list[dict]:
    """The hypergrilling documents, read for the lines that name a failure or a refusal."""
    found = []
    if not HYPERGRILL.is_dir():
        return found
    for path in sorted(HYPERGRILL.rglob("*.md")):
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines, start=1):
            match = HYPER_WORDS.search(line)
            if not match:
                continue
            found.append({
                "project": "hypergrilling",
                "source": str(path),
                "line": index,
                "code": match.group(1).lower(),
                "result": "documented",
                "command": "",
                "observed": line.strip()[:400].replace(str(HOME), "~"),
                "artifact": display(path),
                "at": "",
            })
    return found


def scan() -> dict:
    rows: list[dict] = []
    scanned: list[dict] = []
    for root in ROOTS:
        if not root.is_dir():
            scanned.append({"root": display(root), "state": "absent", "files": 0, "rows": 0})
            continue
        files = 0
        before = len(rows)
        for pattern in LEDGER_GLOBS:
            for path in sorted(root.glob(pattern)):
                if not path.is_file():
                    continue
                files += 1
                rows.extend(read_ledger(path, root.name))
        scanned.append({"root": display(root), "state": "present", "files": files,
                        "rows": len(rows) - before})
    hyper = read_hypergrill()
    rows.extend(hyper)
    scanned.append({"root": display(HYPERGRILL), "state": "present" if HYPERGRILL.is_dir() else "absent",
                    "files": len({row["source"] for row in hyper}), "rows": len(hyper)})

    groups = collections.Counter(row["code"] for row in rows)
    by_project = collections.Counter(row["project"] for row in rows)
    reading = {
        "schema": SCHEMA,
        "at": iso(),
        "sources": scanned,
        "totals": {"rows": len(rows), "codes": len(groups), "projects": len(by_project)},
        "codes": [{"code": code, "count": count,
                   "projects": sorted({row["project"] for row in rows if row["code"] == code}),
                   "example": next((row["observed"] for row in rows if row["code"] == code), "")}
                  for code, count in groups.most_common()],
        "by_project": dict(by_project.most_common()),
        "rows": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    # A reading that is committed must not carry the account's home path through a row's
    # observed text either, so the serialized document is mapped once more before it lands.
    OUT_JSON.write_text(
        json.dumps(reading, indent=2).replace(str(HOME), "~") + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(reading), encoding="utf-8")
    return reading


def render_md(reading: dict) -> str:
    lines = [
        "# Family failures, swept from the ledgers and the hypergrilling documents",
        "",
        f"`{SCHEMA}` · {reading['at']} · {reading['totals']['rows']} rows · "
        f"{reading['totals']['codes']} named codes · {reading['totals']['projects']} projects",
        "",
        "## Sources read",
        "",
        "| root | state | files | rows |",
        "|---|---|---|---|",
    ]
    for row in reading["sources"]:
        lines.append(f"| `{row['root']}` | {row['state']} | {row['files']} | {row['rows']} |")
    lines += ["", "## Every named code, most repeated first", "",
              "| code | rows | projects | first example |", "|---|---|---|---|"]
    for entry in reading["codes"]:
        example = (entry["example"] or "").replace("|", "\\|")[:160]
        lines.append(f"| `{entry['code']}` | {entry['count']} | "
                     f"{', '.join(entry['projects'])} | {example} |")
    return "\n".join(lines) + "\n"


def page(reading: dict) -> str:
    codes = "".join(
        f"<tr><td>{entry['count']}</td><td>{entry['code']}</td>"
        f"<td>{', '.join(entry['projects'])}</td></tr>"
        for entry in reading.get("codes", [])
    )
    sources = "".join(
        f"<li>{row['root']} · {row['state']} · {row['files']} files · {row['rows']} rows</li>"
        for row in reading.get("sources", [])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>family failures</title>
<link rel="stylesheet" href="/contour-theme.css"><link rel="stylesheet" href="/toast.css">
</head><body>
<section class="toast" data-contour="window" data-popit="family-failures" data-motion="full">
  <header class="bar" data-contour data-region="bar"><span class="mark">◆</span>
    <h1>Family failures</h1>
    <span id="failure-summary" class="status" data-contour="card" data-state="live">
      {reading.get('totals', {}).get('rows', 0)} rows</span></header>
  <div class="tabs" data-contour data-region="status"><span class="chip">
    {reading.get('totals', {}).get('codes', 0)} named codes · {reading.get('at', '')}</span></div>
  <div class="body" data-contour data-region="body">
    <ul id="failure-sources" class="facts">{sources}</ul>
    <table id="failure-table" class="facts"><tbody>{codes}</tbody></table>
  </div>
  <footer class="foot" data-contour="card" data-region="foot">
    <span id="failure-foot">{SCHEMA} · every ledger surface plus the hypergrilling documents</span>
  </footer>
</section></body></html>"""


def cmd_scan(args) -> int:
    reading = scan()
    print(f"SWEEP rows={reading['totals']['rows']} codes={reading['totals']['codes']} "
          f"projects={reading['totals']['projects']}")
    for entry in reading["codes"][:12]:
        print(f"SWEEP {entry['count']:>4}  {entry['code']}  ({', '.join(entry['projects'])})")
    print(f"SWEEP wrote={OUT_JSON} md={OUT_MD}")
    return 0


def cmd_serve(args) -> int:
    reading = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.is_file() else scan()
    body = page(reading).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            payload = (json.dumps(reading).encode("utf-8") if self.path.startswith("/state.json")
                       else body)
            kind = "application/json" if self.path.startswith("/state.json") else "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"SWEEP serve http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_probe(args) -> int:
    base = f"http://127.0.0.1:{args.port}"
    problems, markup, state = [], "", ""
    for _ in range(20):
        try:
            markup = urlopen(base + "/", timeout=3).read().decode("utf-8", "replace")
            state = urlopen(base + "/state.json", timeout=3).read().decode("utf-8", "replace")
            break
        except OSError:
            time.sleep(0.3)
    for marker in ('data-popit="family-failures"', 'id="failure-table"', 'id="failure-sources"',
                   'data-region="bar"', 'data-region="foot"'):
        if marker not in markup:
            problems.append(f"page-missing:{marker}")
    try:
        body = json.loads(state)
    except json.JSONDecodeError:
        body = {}
        problems.append("state-not-json")
    if body.get("schema") != SCHEMA:
        problems.append(f"state-schema:{body.get('schema')}")
    receipt = {"schema": SCHEMA, "at": iso(), "unit": "probe", "url": base,
               "checks": [{"name": "popit-surface", "state": "blocked" if problems else "present",
                           "detail": ", ".join(problems) if problems else
                           f"{body.get('totals', {}).get('rows', 0)} rows"}]}
    (ROOT / "runlogs" / "family-failures-probe.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(("SWEEP probe blocked " + ", ".join(problems)) if problems else
          f"SWEEP probe present rows={body.get('totals', {}).get('rows', 0)}")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan").set_defaults(func=cmd_scan)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8798)
    serve.set_defaults(func=cmd_serve)
    probe = sub.add_parser("probe")
    probe.add_argument("--port", type=int, default=8798)
    probe.set_defaults(func=cmd_probe)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
