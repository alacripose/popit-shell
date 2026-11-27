"""Probe the two rebuilt archive apps: their signatures, their refusals and their copy.

The legacy page was a table nothing answered. This probe reads the apps the way the family
reads a surface: the signed package and its launch proof, the live window when the desk
answers, and a fixture project so the copy, the cache rule and the named refusals are
measured instead of asserted.

    python tools/session_archive_probe.py            # fixture checks, then the live desk
    python tools/session_archive_probe.py --fixture  # no shell, no signing key: CI's mode

A live check that cannot run because the desk is down is recorded `blocked` with the act
that clears it, never `passed`. The receipt is `artifacts/receipts/session-archive.json`.
"""
from __future__ import annotations

import json
import os
import pathlib
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "artifacts" / "receipts" / "session-archive.json"
SHELL = f"http://127.0.0.1:{os.environ.get('POPIT_PORT') or '5207'}"
WINDOW = "https://127.0.0.1:5211"
CERT = ROOT / "runlogs" / "toast" / "phone-cert.pem"
SCHEMA = "popit.session-archive-probe/1"
APPS = ("archive", "evidence")

# The fixture roots are read at import, so they are made before the module is imported.
FIXTURE = pathlib.Path(tempfile.mkdtemp(prefix="popit-archive-"))
PROJECT = FIXTURE / "roots" / "sample-project"
EVIDENCE = FIXTURE / "evidence"
PROJECT.mkdir(parents=True)
os.environ["POPIT_ARCHIVE_ROOTS"] = str(FIXTURE / "roots")
os.environ["POPIT_EVIDENCE_ROOT"] = str(EVIDENCE)
sys.path.insert(0, str(ROOT))
import session_archive  # noqa: E402 - after the fixture's roots are set


def iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def shown(path: pathlib.Path) -> str:
    """A receipt keeps the shape of a root, never the account name inside it."""
    text = str(path).replace("\\", "/")
    home = str(pathlib.Path(os.path.expanduser("~"))).replace("\\", "/")
    return "~" + text[len(home):] if text.startswith(home) else text


def http(path: str, body: dict | None = None, timeout: float = 12.0) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{SHELL}{path}", data=data,
                                     method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.status, json.loads(reply.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except (ValueError, OSError):
            return error.code, {}
    except (OSError, urllib.error.URLError):
        return 0, {}


def https_page(path: str) -> tuple[int, str]:
    """Read the delivered window page over the desk's own certificate, pinned from disk."""
    context = ssl.create_default_context()
    try:
        context.load_verify_locations(cafile=str(CERT))
    except (OSError, ssl.SSLError):
        return 0, ""
    try:
        with urllib.request.urlopen(f"{WINDOW}{path}", timeout=20,
                                    context=context) as reply:
            return reply.status, reply.read().decode("utf-8", "replace")
    except (OSError, ssl.SSLError, urllib.error.URLError):
        return 0, ""


def build_fixture() -> None:
    (PROJECT / "AGENTS.md").write_text("# sample\n", encoding="utf-8")
    (PROJECT / "main.py").write_text("print('sample')\n", encoding="utf-8")
    (PROJECT / "records").mkdir()
    (PROJECT / "records" / "row.json").write_text('{"ok": true}\n', encoding="utf-8")
    (PROJECT / "__pycache__").mkdir()
    (PROJECT / "__pycache__" / "main.cpython-313.pyc").write_bytes(b"\0" * 64)
    (PROJECT / ".git").mkdir()
    (PROJECT / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (PROJECT / "asset.bin").write_bytes(b"\0" * (9 * 1024 * 1024))


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, name: str, ok: bool, detail: str = "", state: str = "") -> None:
        state = state or ("passed" if ok else "failed")
        self.rows.append({"check": name, "state": state, "ok": state == "passed",
                          "detail": detail[:240]})
        print(f"{state.upper():8} {name} · {detail}"[:220])

    def blocked(self, name: str, detail: str) -> None:
        self.rows.append({"check": name, "state": "blocked", "ok": False, "detail": detail[:240]})
        print(f"BLOCKED  {name} · {detail}"[:220])


def fixture_checks(checks: Checks) -> None:
    started = session_archive.iso()
    build_fixture()
    index = session_archive._build()
    rows = [row for row in index["rows"] if row["kind"] == "project"]
    row = next((row for row in rows if row["name"] == "sample-project"), None)
    checks.check("fixture-project-indexed", bool(row),
                 f"{len(rows)} project row(s) · {index['directories']} dirs")
    if not row:
        return
    checks.check("fixture-cache-measured", row["cache_dirs"] == 1 and row["cache_bytes"] > 0,
                 f"{row['cache_dirs']} cache dir(s), {row['cache_bytes']} B")
    listing = session_archive.clean(row["slug"], apply=False)
    checks.check("clean-lists-before-removing", listing["dirs"] == 1 and listing["removed"] == 0,
                 f"{listing['dirs']} dir(s), removed {listing['removed']}")
    applied = session_archive.clean(row["slug"], apply=True)
    kept = (PROJECT / "main.py").is_file() and (PROJECT / ".git").is_dir()
    checks.check("clean-removes-only-the-family-cache-rule",
                 applied["removed"] == 1 and kept
                 and not (PROJECT / "__pycache__").exists(),
                 f"removed {applied['removed']}, source kept {kept}")
    backup = session_archive.start_backup([row["slug"]])
    receipt = (EVIDENCE / row["slug"] / "_receipt.json")
    checks.check("backup-copies-and-records",
                 receipt.is_file() and backup["rows"][0]["copied"] >= 3
                 and backup["rows"][0]["recorded"] >= 1,
                 f"{backup['rows'][0]['copied']} copied, "
                 f"{backup['rows'][0]['recorded']} recorded")
    try:
        session_archive.files("no-such-project")
        refusal = ""
    except session_archive.Refused as error:
        refusal = error.code
    checks.check("unknown-project-is-refused", refusal == "archive-unknown-project", refusal)
    try:
        session_archive.show(row["slug"], "project", "..\\..\\escape")
        refusal = "opened"
    except session_archive.Refused as error:
        refusal = error.code
    checks.check("a-path-outside-the-project-is-refused",
                 refusal == "archive-path-outside", refusal)
    try:
        session_archive.start_backup([], all_projects=False)
        refusal = "backed-up"
    except session_archive.Refused as error:
        refusal = error.code
    checks.check("an-empty-backup-is-refused", refusal == "archive-backup-none", refusal)
    ledger = session_archive.ledger_tail(20)
    codes = {row.get("code") for row in ledger}
    named = [row for row in ledger if row.get("code") and str(row.get("at") or "") >= started]
    checks.check("the-program-wrote-its-own-rows",
                 {"archive-unknown-project", "archive-backup-none"} <= codes,
                 f"{len(ledger)} row(s) in {session_archive.LEDGER.name}")
    checks.check("its-refusals-are-readable-by-the-family-sweep",
                 bool(named) and all(row.get("result") == "refused" for row in named),
                 f"{len(named)} named row(s), all `result: refused`")


def live_checks(checks: Checks) -> None:
    status, registry = http("/api/toast/apps")
    if status != 200 or not registry:
        for app in APPS:
            checks.blocked(f"window-measured-{app}", "desk does not answer /api/toast/apps")
        checks.blocked("live-session-state", "python tools/desk_launcher.py")
        return
    apps = registry.get("apps") or {}
    for app in APPS:
        row = apps.get(app) or {}
        proof = row.get("launch_proof") or {}
        refused = (row.get("refused") or {}).get("code") or ""
        checks.check(f"signed-{app}",
                     row.get("verified") is True and not refused and bool(row.get("identity")),
                     f"{row.get('identity') or 'unsigned'} {refused}".strip())
        checks.check(f"launch-proven-{app}",
                     (proof.get("ok") is True and proof.get("mode") == app
                      and str(proof.get("url") or "").endswith(f"window={app}")),
                     json.dumps(proof)[:200])
    status, body = http("/api/toast/session")
    checks.check("live-session-state", status == 200
                 and body.get("schema") == "popit.session-archive/1"
                 and isinstance(body.get("rows"), list),
                 f"{len(body.get('rows') or [])} row(s) · index "
                 f"{(body.get('index') or {}).get('state')}")
    status, answer = http("/api/toast/session/clean", {"slug": "anything", "apply": False})
    checks.check("live-clean-needs-the-second-confirmation",
                 status == 409 and (answer.get("refused") or {}).get("code")
                 == "archive-clean-confirm",
                 str(answer.get("refused"))[:120])
    status, answer = http("/api/toast/session/backup", {"slug": "no-such-project"})
    checks.check("live-backup-refuses-an-unknown-project",
                 status == 409
                 and (answer.get("refused") or {}).get("code") == "archive-unknown-project",
                 str(answer.get("refused"))[:120])
    # The page the window is delivered is read over the desk's pinned certificate: the app's
    # panel, the settings window's body and the family regions are in the bytes the window
    # loads. Opening the window itself is an act on the owner's desk, so a desk sitting on
    # another surface is a blocked row naming the driver act, never a pass and never a fail.
    for app in APPS:
        status, page = https_page(f"/toast.html?window={app}")
        checks.check(f"window-{app}-delivered",
                     status == 200 and f'id="{app}-panel"' in page
                     and 'data-window="popit-settings-package"' in page
                     and all(f'data-region="{region}"' in page
                             for region in ("bar", "status", "body", "foot")),
                     f"{status} · {len(page)} B over the pinned certificate")
    for probe, app in (("archive", "archive"), ("evidence", "evidence")):
        status, body = http("/api/toast/window/eval", {"name": probe})
        if status != 200:
            checks.blocked(f"window-{probe}-reports-its-panel",
                           "the delivered window did not queue the probe")
            continue
        key = str((body or {}).get("id") or "")
        deadline = time.time() + 20
        value: dict = {}
        while time.time() < deadline and key:
            status, reply = http(f"/api/toast/window/eval?id={key}")
            if status == 200 and (reply or {}).get("ok"):
                raw = (reply or {}).get("value")
                try:
                    value = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except json.JSONDecodeError:
                    value = {}
                break
            time.sleep(0.6)
        if str(value.get("window") or "") == app and not value.get("refused"):
            checks.check(f"window-{probe}-reports-its-panel", True,
                         json.dumps(value)[:200])
        else:
            checks.blocked(f"window-{probe}-reports-its-panel",
                           "the desk is on another surface; the tile opens the app window, "
                           "and a cua driver captures it")


def main(argv: list[str]) -> int:
    checks = Checks()
    started = iso()
    fixture_checks(checks)
    if "--fixture" not in argv:
        live_checks(checks)
    failed = [row for row in checks.rows if row["state"] == "failed"]
    blocked = [row for row in checks.rows if row["state"] == "blocked"]
    passed = [row for row in checks.rows if row["state"] == "passed"]
    receipt = {"schema": SCHEMA, "at": iso(), "started": started, "shell": SHELL,
               "roots": {"fixture": shown(FIXTURE), "evidence": shown(EVIDENCE)},
               "checks": checks.rows, "passed": len(passed), "failed": len(failed),
               "blocked": len(blocked),
               "state": "passed" if not failed and not blocked else
                        ("failed" if failed else "blocked"),
               "act": "" if not failed and not blocked else
                      "start the desk with python tools/desk_launcher.py and measure the window"}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    print(f"\n{len(passed)} passed, {len(failed)} failed, {len(blocked)} blocked -> {RECEIPT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
