"""prose-family — the family's prose, read and rendered, for the prose app window.

Owner instruction, verbatim: *"you just invented an html surface document, not a popit shell app
mutated from the settings app baseline in the windows toast client"*, after the first pass served a
page of its own on a port. The surface is the **prose app package**: `?window=prose` on the settings
window's own page, signed by the settings publisher, tiled on the SpringBoard, measured by the
window audit. This file is the worker behind that window:

1. **Inventory.** Every project in the family register is read by the family checker
   (`../portal-shell/tools/ui_prose.py`, imported, never copied) across its own trees, so a
   sentence inside `ui/phone.js`, a doc under `docs/`, a landing page and a Python tool are one
   reading with one rule set.
2. **External visible documents.** Each project gets a rustdoc-shaped document at
   `docs/prose/<project>/index.html`, served by the shell at `/api/toast/prose/doc/<project>` and
   linked from the prose window. `docs/prose/index.html` is the family index.
3. **Live progress.** Every phase change republishes `runlogs/prose/progress.json`, which the shell
   serves at `/api/toast/prose/progress.json`; the window polls it and shows a spinner per project
   while it is queued or running, and a bar for its phase.
4. **The driver owns what only it can read.** Which projects the Debian box has staged is asked over
   the bridge; a missing one is staged by publishing a bundle on the shell's origin for the box to
   pull. The corpus write is the driver's own service and a refused write is named.

    python tools/prose_family.py run       # read, render, report
    python tools/prose_family.py report    # run and print the receipt
    python tools/prose_family.py ingest    # run the box's corpus ingest on the staged profile
    python tools/prose_family.py probe     # sign, audit and read the prose app window
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import hosts  # noqa: E402

HOME = pathlib.Path.home()
SCHEMA = "popit.prose-family/1"
DOC_SCHEMA = "popit.prose-doc/1"
PROBE_SCHEMA = "popit.prose-probe/1"
DOCS = ROOT / "docs" / "prose"
RECEIPT = ROOT / "artifacts" / "receipts" / "prose-family.json"
PROBE_RECEIPT = ROOT / "artifacts" / "receipts" / "prose-probe.json"
CORPUS_RECEIPT = ROOT / "runlogs" / "prose" / "corpus.json"
PROGRESS = ROOT / "runlogs" / "prose" / "progress.json"
SHELL = f"http://127.0.0.1:{os.environ.get('POPIT_PORT') or '5207'}"

# The family lives beside this checkout. Both roots are read; a project is resolved from
# whichever carries it, and absent is named rather than assumed.
PROJECTS_ROOTS = tuple(
    candidate for candidate in (pathlib.Path(r"F:\Documents"), HOME / "Documents") if candidate.is_dir()
) or (HOME / "Documents",)
PROJECTS_ROOT = PROJECTS_ROOTS[0]
FAMILY_CHECKER = PROJECTS_ROOT / "portal-shell" / "tools" / "ui_prose.py"
BRIDGE = PROJECTS_ROOT / "mc3-client13" / "tools" / "bridge.py"

# Two roots, one fact: root staged the corpus tree, the program stages what it can read into the
# driver's scratch tree, and the ingest profile names the program's root.
STAGED_ROOTS = ("/srv/ingest/family-prose", "/srv/scratch/prose-staging")
STAGED_ROOT = STAGED_ROOTS[0]
SCRATCH_ROOT = STAGED_ROOTS[1]
PROFILE_NAME = "prose-profile"
# The staging origin is this machine's own address on its network, asked of the routing table
# at run time. A private address written into the source is a stale fact and the owner's
# network in a repository, which is the one thing the family will not commit.
STAGE_BASE = (os.environ.get("POPIT_STAGE_BASE")
              or f"https://{hosts.lan_host()}:5210/api/toast/prose/stage")
STAGE_URL = STAGE_BASE + "/{name}.tar.gz"
PROFILE_URL = STAGE_BASE + "/{name}.json"
CORPUS_INGEST = "/opt/cua-driver/tools/cua_ingest_profile.py"

ROSTER = (
    "deadlock-model-forge",
    "popit-shell",
    "portal-shell",
    "brass-meridian",
    "mc3-client13",
    "db-mc-indev",
    "ala-system",
    "alacripose-landing",
    "AWA3D",
    "income-engine",
    "laya-cua-agent",
)

PHASES = ("inventory", "driver", "stage", "docs", "verify")
PHASE_WEIGHT = {"inventory": 52, "driver": 10, "stage": 18, "docs": 15, "verify": 5}

# A document a person can read: files and strings beyond this are in inventory.json, named.
MAX_DOC_FILES = 250
MAX_DOC_STRINGS = 60
MAX_FILES = 6000
MAX_FILE_BYTES = 512 * 1024
MAX_BUNDLE_BYTES = 40 * 1024 * 1024

# Where prose is written in this family. Discovery is by presence, so a project that adds one of
# these trees is read and a project with none still has its root documents read.
PROSE_TREES = ("ui", "src", "app", "apps", "client", "lib", "internal", "cmd", "core",
               "tools", "public", "docs", "scripts", "web", "static", "addon", "companion",
               "business-mind", ".agents", "tests", "cua")


def iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_checker():
    """Import the family checker by path. No rule is copied into this project."""
    if not FAMILY_CHECKER.is_file():
        raise SystemExit(f"prose-family: family checker absent at {display(FAMILY_CHECKER)}")
    spec = importlib.util.spec_from_file_location("family_ui_prose", FAMILY_CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def display(path: pathlib.Path) -> str:
    """A path a document can carry: the home folder is `~`, never an absolute user folder."""
    text = str(path)
    home = str(HOME)
    return "~" + text[len(home):] if text.lower().startswith(home.lower()) else text


def project_root(name: str) -> pathlib.Path:
    for base in PROJECTS_ROOTS:
        candidate = base / name
        if candidate.is_dir():
            return candidate
    return PROJECTS_ROOT / name


def prose_trees(root: pathlib.Path) -> tuple[str, ...]:
    trees = [name for name in PROSE_TREES if (root / name).is_dir()]
    for entry in sorted(root.glob("*")):
        if entry.is_file() and entry.suffix.lower() in (".md", ".html", ".txt"):
            trees.append(entry.name)
    return tuple(trees) or (".",)


class Job:
    """One project's progress, published for the window as it moves."""

    def __init__(self, name: str, root: pathlib.Path) -> None:
        self.name = name
        self.root = root
        self.phase = "queued"
        self.percent = 0
        self.busy = False
        self.visible = 0
        self.hits = 0
        self.files = 0
        self.extractors: dict[str, int] = {}
        self.rules: dict[str, int] = {}
        self.driver = "pending"
        self.driver_detail = ""
        self.stage = ""
        self.doc = ""
        self.trees: list[str] = []
        self.started = iso()
        self.finished = ""
        self.refusal: dict | None = None
        self.present = root.is_dir()

    def move(self, phase: str) -> None:
        self.phase = phase
        done = sum(PHASE_WEIGHT[p] for p in PHASES[:PHASES.index(phase)])
        self.percent = min(99, done)
        self.busy = True

    def settle(self, refusal: dict | None = None) -> None:
        self.busy = False
        self.percent = 100 if refusal is None else self.percent
        self.finished = iso()
        if refusal:
            self.refusal = refusal
            self.phase = "refused"
        else:
            self.phase = "passed"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "project": display(self.root),
            "present": self.present,
            "phase": self.phase,
            "percent": self.percent,
            "busy": self.busy,
            "visible": self.visible,
            "hits": self.hits,
            "files": self.files,
            "trees": self.trees,
            "extractors": self.extractors,
            "rules": self.rules,
            "driver": self.driver,
            "driver_detail": self.driver_detail,
            "stage": self.stage,
            "doc": self.doc,
            # The document is served by the shell, inside the signed origin, not by a port.
            "doc_url": f"/api/toast/prose/doc/{self.name}" if self.doc else "",
            "started": self.started,
            "finished": self.finished,
            "refusal": self.refusal,
        }


JOBS: dict[str, Job] = {}
RAW: dict[str, dict] = {}
STAGED: dict[str, object] = {"state": "unread", "projects": [], "detail": ""}
CHECKER = None



def publish() -> None:
    """Republish the progress file the prose window reads. Called on every phase change."""
    rows = [job.as_dict() for job in JOBS.values()]
    body = {
        "schema": "popit.prose-progress/1",
        "at": iso(),
        "rows": rows,
        "total": len(rows),
        "busy": sum(1 for row in rows if row["busy"]),
        "finished": sum(1 for row in rows if not row["busy"] and row["phase"] in ("passed", "refused")),
        "driver": dict(STAGED),
    }
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def trace(job: Job, note: str) -> None:
    """A progress line per step, kept beside the window so a pass can be read afterwards."""
    path = ROOT / "runlogs" / "prose" / "run.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": iso(), "project": job.name, "phase": job.phase,
                                 "percent": job.percent, "note": note}) + "\n")
    publish()



def run_on_box(command: str, timeout: float = 240.0) -> dict:
    """One bounded command on the box, through the family's own bridge."""
    if not BRIDGE.is_file():
        return {"ok": False, "code": "driver-unreachable", "detail": f"bridge absent at {display(BRIDGE)}",
                "output": ""}
    try:
        completed = subprocess.run(
            [sys.executable, str(BRIDGE), "run", "--", command],
            cwd=str(BRIDGE.parent.parent), capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "driver-timeout", "detail": command[:120], "output": ""}
    output = (completed.stdout or "") + (completed.stderr or "")
    # The bridge prints its own summary line last; what the box said is the lines before it.
    lines = [line for line in output.strip().splitlines() if line.strip()]
    if lines and lines[-1].startswith("BRIDGE "):
        lines = lines[:-1]
    return {"ok": completed.returncode == 0,
            "code": "" if completed.returncode == 0 else "driver-refused",
            "detail": (lines[-1][:240] if lines else ""),
            "output": " | ".join(lines)[-800:]}


def read_staged() -> dict:
    """Ask the box which projects it has staged. The box's answer, not a guess."""
    # Two roots, and a root that does not exist yet is empty, not a failure.
    listing = " ; ".join(f"ls -1 {root} 2>/dev/null" for root in STAGED_ROOTS) + " ; true"
    answer = run_on_box(listing, timeout=90)
    if not answer["ok"] and not answer["output"]:
        return {"state": "blocked", "projects": [], "detail": answer["detail"] or answer["code"]}
    staged = []
    for line in (answer["output"] or "").split(" | "):
        for name in line.split():
            if name and "/" not in name and name not in staged:
                staged.append(name)
    return {"state": "read", "projects": sorted(staged),
            "detail": f"{len(staged)} project(s) staged"}



def collect_strings(checker, path: pathlib.Path) -> list[dict]:
    """Every drawn string in one file, with its budgets and the rules it breaks."""
    kind = checker.extractor_for(path)
    if kind is None or kind == "md":
        return []
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return []
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if "\x00" in source[:4096]:
        return []
    if kind in ("go", "js"):
        stream = checker.literals(source)
    elif kind == "html":
        stream = checker.html_strings(source)
    elif kind == "py":
        stream = checker.py_strings(source)
    else:
        stream = checker.json_strings(source)
    rows = []
    for line, text, context in stream:
        drawn = bool(checker.DRAWN_CTX.search(context))
        text = " ".join(text.split())
        if not checker.readable(text, drawn):
            continue
        rules = list(checker.bans(text, True))
        words, chars = checker.count_words(text), len(text)
        if words > checker.MAX_UI_WORDS or chars > checker.MAX_UI_CHARS:
            rules.insert(0, f"ui-budget {words}w/{chars}c")
        for sentence in checker.sentences_of(text):
            if checker.count_words(sentence) > checker.MAX_SENTENCE_WORDS:
                rules.append(f"sentence {checker.count_words(sentence)}w")
        if checker.SEMICOLON_RE.search(text):
            rules.append("semicolon")
        rows.append({"line": line, "text": text, "words": words, "chars": chars,
                     "rules": sorted(set(rules))})
    return rows


def inventory(job: Job) -> None:
    checker = CHECKER
    assert checker is not None
    job.move("inventory")
    if not job.present:
        job.settle({"code": "project-absent", "detail": display(job.root)})
        return
    exts = tuple(checker.EXTRACTORS)
    trees = prose_trees(job.root)
    paths = checker.sources(job.root, trees, exts, set(checker.SKIP_FILES))
    if len(paths) > MAX_FILES:
        paths = paths[:MAX_FILES]
    docs = ("*.md", "docs/*.md", "docs/**/*.md", "tickets/*.md", ".agents/skills/*/SKILL.md")
    hits, visible = checker.scan(paths, extended=True, skip_names=set(checker.SKIP_FILES))
    hits.extend(checker.doc_scan(job.root, docs, extended=True))
    failures: list[str] = []
    if not paths and not checker.doc_paths(job.root, docs):
        failures.append(f"nothing read under {display(job.root)}")
    job.files = len(paths) + len(checker.doc_paths(job.root, docs))
    job.trees = list(trees)
    job.visible = visible
    job.hits = len(hits)
    per: dict[str, int] = {}
    for path in paths:
        key = checker.extractor_for(path) or "other"
        per[key] = per.get(key, 0) + 1
    job.extractors = per
    rules: dict[str, int] = {}
    for entry in hits:
        name = entry["rule"].split(":")[0]
        rules[name] = rules.get(name, 0) + 1
    job.rules = dict(sorted(rules.items(), key=lambda item: (-item[1], item[0])))
    strings: dict[str, list[dict]] = {}
    for path in paths:
        rows = collect_strings(checker, path)
        if rows:
            strings[str(path)] = rows
    RAW[job.name] = {"hits": hits, "docs": [str(p) for p in checker.doc_paths(job.root, docs)],
                     "paths": [str(p) for p in paths], "failures": failures,
                     "strings": strings}


def driver_phase(job: Job) -> None:
    """Record what the box says about this project. A miss is a named work item."""
    job.move("driver")
    if STAGED.get("state") != "read":
        job.driver = "blocked"
        job.driver_detail = str(STAGED.get("detail") or "")[:200]
        job.refusal = {"code": "driver-unreachable", "detail": job.driver_detail}
        job.percent += PHASE_WEIGHT["driver"]
        job.busy = True
        publish()
        return
    if job.name in (STAGED.get("projects") or []):
        job.driver = "staged"
        job.driver_detail = f"{STAGED_ROOT}/{job.name}"
    else:
        job.driver = "not-staged"
        job.driver_detail = f"{SCRATCH_ROOT}/{job.name} absent; the driver stages it"
        job.refusal = {"code": "prose-not-staged", "detail": job.driver_detail}
    job.percent += PHASE_WEIGHT["driver"]
    job.busy = True
    publish()



STAGE_DIR = ROOT / "runlogs" / "prose" / "stage"


def write_profile() -> pathlib.Path:
    """The ingest profile for what this program stages: the box's own profile shape."""
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = STAGE_DIR / f"{PROFILE_NAME}.json"
    target.write_text(json.dumps({
        "schema": "cua.corpus.ingest-profile/2",
        "name": "family-prose-staged-by-popit-2026-11-25",
        "roots": [SCRATCH_ROOT],
        "root_project": "family-prose",
        "include_suffixes": [".md", ".txt", ".json", ".jsonl", ".py", ".rs", ".js", ".mjs",
                             ".ts", ".tsx", ".html", ".css", ".toml", ".yaml", ".yml"],
        "skip_dirs": [".git", "node_modules", "target", "build", "dist", "obj", "bin",
                      "__pycache__", ".cache", ".venv", "venv", "coverage", ".next"],
        "max_body_bytes": 32000000,
        "note": "Prose staged by tools/prose_family.py in popit-shell: one archive per project, "
                "pulled over the shell's own HTTPS origin. Claim rules and source quotes stay verbatim.",
    }, indent=2) + "\n", encoding="utf-8")
    return target


def bundle(job: Job) -> pathlib.Path:
    """The project's prose as one archive, written where the shell serves it."""
    import tarfile
    checker = CHECKER
    assert checker is not None
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = STAGE_DIR / f"{job.name}.tar.gz"
    exts = tuple(checker.EXTRACTORS)
    paths = checker.sources(job.root, prose_trees(job.root), exts, set(checker.SKIP_FILES))
    total = 0
    with tarfile.open(target, "w:gz") as archive:
        for path in paths[:MAX_FILES]:
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            rel = str(path.relative_to(job.root)).replace("\\", "/")
            archive.add(str(path), arcname=rel)
            total += path.stat().st_size
            if total > MAX_BUNDLE_BYTES:
                break
    return target


def stage_phase(job: Job) -> None:
    """Hand the project's prose to the box: it pulls the bundle and keeps it staged."""
    job.move("stage")
    staged = list(STAGED.get("projects") or [])
    if job.name in staged:
        job.stage = "already-staged"
        job.percent += PHASE_WEIGHT["stage"]
        job.busy = True
        publish()
        return
    if job.driver != "not-staged":
        job.stage = "skipped"
        job.percent += PHASE_WEIGHT["stage"]
        job.busy = True
        publish()
        return
    archive = bundle(job)
    write_profile()
    mb = round(archive.stat().st_size / (1024 * 1024), 1)
    command = (
        f"curl -sk -m 120 -o /tmp/{job.name}.tar.gz '{STAGE_URL.format(name=job.name)}' && "
        f"mkdir -p {SCRATCH_ROOT}/{job.name} && tar -xzf /tmp/{job.name}.tar.gz -C {SCRATCH_ROOT}/{job.name} && "
        f"ls {SCRATCH_ROOT}/{job.name} | head -1"
    )
    answer = run_on_box(command)
    job.percent += PHASE_WEIGHT["stage"]
    job.busy = True
    if not answer["ok"]:
        job.stage = "refused"
        job.refusal = {"code": "prose-stage-refused", "detail": f"{mb} MB bundle; {answer['detail']}"}
        publish()
        return
    job.stage = f"staged {mb} MB"
    # The refusal named the box not having this project. It has it now, so the name goes.
    if job.refusal and job.refusal.get("code") == "prose-not-staged":
        job.refusal = None
    if job.name not in (STAGED.get("projects") or []):
        STAGED["projects"] = sorted(set((STAGED.get("projects") or []) + [job.name]))
    publish()



DOC_CSS = """
:root{--ground:#0c0e11;--ink:#e7e3d8;--muted:#8d8a80;--gold:#f0c454;--edge:#23262b;--bad:#e2765f;--ok:#8dc98a}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font:14px/1.55 "Archivo","Segoe UI",sans-serif}
header{border-bottom:1px solid var(--edge);padding:20px 26px}
h1{margin:0;font-size:15px;letter-spacing:.14em;text-transform:uppercase}
h2{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:26px 0 8px}
.mark{color:var(--gold)}
main{padding:20px 26px 60px;max-width:1100px}
code,.mono{font-family:"IBM Plex Mono",monospace;font-size:12px}
a{color:var(--gold);text-decoration:none}
table{border-collapse:collapse;width:100%;margin-top:10px}
th,td{text-align:left;padding:6px 9px;border-bottom:1px solid var(--edge);vertical-align:top;font-size:13px}
th{color:var(--muted);font-weight:500;text-transform:uppercase;letter-spacing:.1em;font-size:11px}
.rule{color:var(--bad)}
.ok{color:var(--ok)}
.badge{display:inline-block;border:1px solid var(--edge);padding:1px 7px;font-family:"IBM Plex Mono",monospace;font-size:11px}
.badge.bad{color:var(--bad);border-color:var(--bad)}
.badge.ok{color:var(--ok);border-color:var(--ok)}
nav a{margin-right:14px}
"""


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def doc_head(title: str, body_attrs: str) -> str:
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\" />\n"
            f"<title>{esc(title)}</title>\n<style>{DOC_CSS}</style>\n</head>\n"
            f"<body {body_attrs}>\n")


def render_project(job: Job) -> pathlib.Path:
    """A rustdoc-shaped page: what was read, what was refused, and where it is."""
    job.move("docs")
    raw = RAW.get(job.name) or {"hits": [], "docs": [], "paths": [], "failures": [], "strings": {}}
    checker = CHECKER
    assert checker is not None
    out_dir = DOCS / job.name
    out_dir.mkdir(parents=True, exist_ok=True)
    strings_by_file: dict[str, list[dict]] = raw.get("strings") or {}

    parts = [doc_head(f"prose · {job.name}",
                      f'data-doc="prose" data-project="{esc(job.name)}" data-schema="{DOC_SCHEMA}"')]
    parts.append('<header><h1><span class="mark">&#9671;</span> prose &middot; '
                 f'{esc(job.name)}</h1></header><main>')
    parts.append('<nav><a href="/api/toast/prose/doc/../index.html">family index</a>'
                 f'<span class="mono">{esc(display(job.root))}</span></nav>')
    state = "refused" if job.refusal else "passed"
    parts.append(f'<p><span class="badge {"bad" if job.refusal else "ok"}">{esc(state)}</span> '
                 f'<span class="mono">{esc(job.visible)} drawn string(s) &middot; {esc(job.hits)} hit(s) &middot; '
                 f'{esc(job.files)} file(s)</span></p>')
    if job.refusal:
        parts.append(f'<p class="rule">{esc(job.refusal["code"])} &middot; {esc(job.refusal["detail"])}</p>')
    parts.append('<h2>extractors</h2><table><thead><tr><th>extractor</th><th>files</th></tr></thead><tbody>')
    for name, count in sorted(job.extractors.items()):
        parts.append(f"<tr><td>{esc(name)}</td><td>{count}</td></tr>")
    parts.append("</tbody></table>")
    parts.append('<h2>the family rules, and what this project draws against each</h2>')
    catalogue = [
        ("sentence budget", f"a sentence is at most {checker.MAX_SENTENCE_WORDS} words"),
        ("drawn string budget", f"at most {checker.MAX_UI_WORDS} words and {checker.MAX_UI_CHARS} characters"),
        ("word bans", ", ".join(sorted(set(checker.WORDS) | set(checker.WORDS_EXTENDED)))),
        ("phrase bans", "; ".join(sorted(set(checker.PHRASES) | set(checker.PHRASES_EXTENDED)))),
        ("punctuation", "no semicolon in copy, no trailing period on a label, no em dash"),
        ("voice", "no assistant voice: you can, lets you, use this to, this will, so you"),
    ]
    parts.append('<table><thead><tr><th>rule</th><th>holds</th><th>hits here</th></tr></thead><tbody>')
    for name, holds in catalogue:
        count = job.rules.get(name.split()[0], "") if name.split()[0] in job.rules else ""
        parts.append(f"<tr><td>{esc(name)}</td><td>{esc(holds)}</td><td>{esc(count)}</td></tr>")
    for name, count in job.rules.items():
        parts.append(f"<tr><td>{esc(name)}</td><td>counted by the family checker</td><td>{count}</td></tr>")
    parts.append("</tbody></table>")
    parts.append('<h2>every string, by file</h2>')
    printed = 0
    for path_text, rows in sorted(strings_by_file.items()):
        if printed >= MAX_DOC_FILES:
            break
        printed += 1
        rel = pathlib.Path(path_text).resolve()
        try:
            rel_text = str(rel.relative_to(job.root)).replace("\\", "/")
        except ValueError:
            rel_text = display(rel)
        parts.append(f'<h3 class="mono">{esc(rel_text)} <span class="mono">({len(rows)} string(s))</span></h3>')
        if not rows:
            parts.append('<p class="mono ok">nothing drawn here</p>')
            continue
        if len(rows) > MAX_DOC_STRINGS:
            parts.append(f'<p class="mono">{len(rows) - MAX_DOC_STRINGS} more string(s) in this file are in '
                         f'inventory.json and not printed here</p>')
        parts.append('<table><thead><tr><th>line</th><th>string</th><th>budget</th><th>rules</th></tr></thead><tbody>')
        for row in rows[:MAX_DOC_STRINGS]:
            flagged = bool(row["rules"])
            parts.append(
                f'<tr><td class="mono">{row["line"]}</td><td>{esc(row["text"][:220])}</td>'
                f'<td class="mono">{row["words"]}w/{row["chars"]}c</td>'
                f'<td class="{"rule" if flagged else "ok"}">{esc(", ".join(row["rules"]) or "ok")}</td></tr>')
        parts.append("</tbody></table>")
    if len(strings_by_file) > printed:
        parts.append(f'<p class="mono">{len(strings_by_file) - printed} more file(s) are in '
                     f'inventory.json and not printed here</p>')
    parts.append("<h2>documents</h2><ul>")
    for doc in raw["docs"]:
        parts.append(f'<li class="mono">{esc(display(pathlib.Path(doc)))}</li>')
    parts.append("</ul>")
    parts.append(f'<p class="mono">read by {esc(display(FAMILY_CHECKER))} &middot; rendered {esc(iso())}</p>')
    parts.append("</main></body></html>\n")
    target = out_dir / "index.html"
    target.write_text("".join(parts), encoding="utf-8")
    (out_dir / "inventory.json").write_text(json.dumps(
        {"schema": DOC_SCHEMA, "project": job.name, "root": display(job.root),
         "visible": job.visible, "hits": len(raw["hits"]), "rules": job.rules,
         "extractors": job.extractors,
         "strings": {key: rows[:MAX_DOC_STRINGS] for key, rows in strings_by_file.items()},
         "strings_total": {key: len(rows) for key, rows in strings_by_file.items()},
         "hits_detail": raw["hits"][:2000], "documents": raw["docs"],
         "driver": {"state": job.driver, "detail": job.driver_detail}, "at": iso()},
        indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    job.doc = display(target)
    job.percent += PHASE_WEIGHT["docs"]
    job.busy = True
    publish()
    return target


def render_index(jobs: list[Job]) -> pathlib.Path:
    DOCS.mkdir(parents=True, exist_ok=True)
    parts = [doc_head("prose · the family",
                      f'data-doc="prose" data-project="family" data-schema="{DOC_SCHEMA}"')]
    parts.append('<header><h1><span class="mark">&#9671;</span> prose &middot; the family</h1></header><main>')
    parts.append('<p>One rule set, read from <span class="mono">portal-shell/tools/ui_prose.py</span>. '
                 'A sentence carries one idea and at most twenty-four words. A drawn string is at most '
                 'eighteen words and ninety-two characters.</p>')
    parts.append('<table id="family-index"><thead><tr><th>project</th><th>state</th><th>extractors</th>'
                 '<th>drawn</th><th>hits</th><th>driver</th><th>document</th></tr></thead><tbody>')
    for row in jobs:
        state = "refused" if row.refusal else ("absent" if not row.present else "passed")
        parts.append(
            f'<tr id="project-{esc(row.name)}"><td>{esc(row.name)}</td>'
            f'<td><span class="badge {"bad" if state != "passed" else "ok"}">{esc(state)}</span></td>'
            f'<td class="mono">{esc(", ".join(f"{k}:{v}" for k, v in sorted(row.extractors.items())))}</td>'
            f'<td class="mono">{row.visible}</td><td class="mono">{row.hits}</td>'
            f'<td class="mono">{esc(row.driver)}{" · " + esc(row.refusal["code"]) if row.refusal else ""}</td>'
            f'<td><a href="/api/toast/prose/doc/{esc(row.name)}">read</a></td></tr>')
    parts.append("</tbody></table>")
    parts.append(f'<p class="mono">rendered {esc(iso())} by tools/prose_family.py</p>')
    parts.append("</main></body></html>\n")
    target = DOCS / "index.html"
    target.write_text("".join(parts), encoding="utf-8")
    return target


def verify(job: Job) -> None:
    """The document is re-read from disk. A page that was written but is empty is a refusal."""
    job.move("verify")
    if not job.doc:
        job.settle({"code": "prose-doc-missing", "detail": "no document was written"})
        publish()
        return
    path = DOCS / job.name / "index.html"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        job.settle({"code": "prose-doc-missing", "detail": str(error)})
        publish()
        return
    if 'data-doc="prose"' not in text or f'data-project="{job.name}"' not in text or len(text) < 900:
        job.settle({"code": "prose-doc-incomplete", "detail": f"{len(text)} bytes"})
        publish()
        return
    job.settle(job.refusal)
    publish()


def work(job: Job) -> None:
    try:
        trace(job, "inventory started")
        inventory(job)
        trace(job, f"read {job.files} file(s), {job.visible} string(s), {job.hits} hit(s)")
        if job.phase == "refused":
            trace(job, f"refused: {job.refusal['code']}")
            return
        driver_phase(job)
        trace(job, f"driver: {job.driver}")
        stage_phase(job)
        trace(job, f"stage: {job.stage}")
        render_project(job)
        trace(job, f"document written: {job.doc}")
        verify(job)
        trace(job, f"settled: {job.phase}")
    except Exception as error:  # one project cannot stop the family pass
        job.settle({"code": "prose-pass-failed", "detail": f"{type(error).__name__}: {error}",
                    "trace": traceback.format_exc()[-800:]})
        publish()


def ingest() -> dict:
    """Run the box's own corpus ingest against the profile for what this program staged."""
    profile = write_profile()
    remote = f"/tmp/{PROFILE_NAME}-{int(time.time())}.json"
    answer = run_on_box(
        f"rm -f {remote} && "
        f"curl -sk -m 60 -o {remote} '{PROFILE_URL.format(name=PROFILE_NAME)}' && "
        f"python3 -c \"import json;d=json.load(open('{remote}',encoding='utf-8'));"
        f"print('profile-schema-read', d.get('schema'))\" && "
        f"python3 {CORPUS_INGEST} --profile {remote} 2>&1 | tail -4",
        timeout=420,
    )
    # The bridge's exit status says the command ran; the box's words say what happened. A corpus
    # under /opt is written by the driver's service, so a write refusal is a driver act, named.
    output = answer.get("output", "") or ""
    code = answer["code"]
    if "PermissionError" in output:
        code = "corpus-write-permission"
    elif "profile-schema" in output:
        code = "profile-schema"
    elif any(word in output for word in ("Traceback", "Error", "refused")):
        code = "corpus-ingest-refused"
    ok = answer["ok"] and not code
    body = {"schema": "popit.prose-corpus/1", "at": iso(),
            "profile": display(profile), "stage_root": SCRATCH_ROOT,
            "ok": ok, "code": code, "detail": answer["detail"], "output": output}
    CORPUS_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_RECEIPT.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return body


def run(projects: tuple[str, ...] = ROSTER) -> list[Job]:
    global CHECKER
    CHECKER = load_checker()
    JOBS.clear()
    RAW.clear()
    STAGED.update(read_staged())
    jobs = []
    for name in projects:
        job = Job(name, project_root(name))
        JOBS[name] = job
        jobs.append(job)
    publish()
    # Four at a time: the family pass is a read, and a read bounded to four keeps the box and
    # this machine responsive while the window shows the queue.
    pending = list(jobs)
    while pending:
        batch, pending = pending[:4], pending[4:]
        threads = [__import__("threading").Thread(target=work, args=(job,), daemon=True) for job in batch]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        publish()
    if any(job.stage.startswith("staged ") for job in jobs):
        # What this program staged is ingested by the box's own tool, against this program's
        # profile, and the outcome is kept as its own receipt.
        ingest()
    render_index(jobs)
    publish()
    return jobs


def report(projects: tuple[str, ...] = ROSTER) -> dict:
    jobs = run(projects)
    rows = [job.as_dict() for job in jobs]
    refused = [row["name"] for row in rows if row["refusal"]]
    body = {
        "schema": SCHEMA,
        "at": iso(),
        "checker": display(FAMILY_CHECKER),
        "rules": {
            "sentence_words": CHECKER.MAX_SENTENCE_WORDS if CHECKER else None,
            "ui_words": CHECKER.MAX_UI_WORDS if CHECKER else None,
            "ui_chars": CHECKER.MAX_UI_CHARS if CHECKER else None,
            "extractors": sorted(CHECKER.EXTRACTORS) if CHECKER else [],
        },
        "driver": {"staged_root": STAGED_ROOT, "stage_roots": list(STAGED_ROOTS),
                   "state": STAGED.get("state"), "projects": STAGED.get("projects"),
                   "detail": STAGED.get("detail")},
        "corpus": (json.loads(CORPUS_RECEIPT.read_text(encoding="utf-8"))
                   if CORPUS_RECEIPT.is_file() else {"state": "not-run"}),
        # The window links these through the shell's own route, not a port of this program's.
        "rows": rows,
        "projects": len(rows),
        "passed": sum(1 for row in rows if not row["refusal"]),
        "refused": refused,
        "index": "/api/toast/prose/doc/../index.html",
    }
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return body



def http(path: str, *, body: bytes | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    request = urllib.request.Request(SHELL + path, data=body, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"} if body is not None else {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return reply.status, json.loads(reply.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(raw or "{}")
        except ValueError:
            return error.code, {"body": raw[:200]}


def window_probe(name: str, seconds: float = 40.0) -> dict | None:
    """Ask the delivered window to run one named act and return what it measured."""
    status, queued = http("/api/toast/window/eval", body=json.dumps({"name": name}).encode("utf-8"))
    if status != 200 or not queued.get("id"):
        return None
    key = str(queued["id"])
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.6)
        status, reply = http(f"/api/toast/window/eval?id={key}")
        if status == 200 and reply.get("ok"):
            value = reply.get("value")
            try:
                return json.loads(value) if isinstance(value, str) else value
            except ValueError:
                return {"raw": value}
    return None


def probe() -> int:
    """Sign the app, audit its window, and read what the delivered window shows."""
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    status, apps = http("/api/toast/apps")
    app = (apps.get("apps") or {}).get("prose") or {}
    if not app or app.get("refused") or app.get("verified") is not True:
        if not RECEIPT.is_file():
            report()
        status, ensured = http("/api/toast/apps/ensure", body=b"{}", timeout=300)
        app = ((ensured.get("apps") or {}).get("prose")) if status == 200 else {}
        if not app:
            status, apps = http("/api/toast/apps")
            app = (apps.get("apps") or {}).get("prose") or {}
    refusal = app.get("refused") or {}
    check("prose-app-is-signed", bool(app.get("identity")) and app.get("verified") is True
          and not refusal,
          f"{app.get('identity') or 'unsigned'}" + (f" refused {refusal.get('code')}"
                                                    if isinstance(refusal, dict) else ""))
    check("prose-app-is-the-settings-window", str(app.get("entry") or "") == "toast.html"
          and str(app.get("kind") or "") == "window",
          f"entry {app.get('entry')} kind {app.get('kind')}")
    if not RECEIPT.is_file():
        report()
    # The audit is measured in a fresh delivery of the window: an earlier refusal page has no
    # probe object at all, and a stale service worker would serve the old script.
    http("/api/toast/window/audit", body=json.dumps({"app": "desk"}).encode("utf-8"))
    time.sleep(2)
    audit = None
    for _attempt in range(3):
        status, started = http("/api/toast/window/audit", body=json.dumps({"app": "prose"}).encode("utf-8"))
        if status != 200:
            break
        deadline = time.time() + 90
        while time.time() < deadline:
            time.sleep(2)
            status, apps = http("/api/toast/apps")
            app = (apps.get("apps") or {}).get("prose") or {}
            audit = app.get("ui_audit") or {}
            if isinstance(audit, str):
                audit = {"state": audit}
            if str(audit.get("state") or "") in ("passed", "refused", "failed"):
                break
        if audit and str(audit.get("state")) == "passed":
            break
    audit = audit or {}
    check("prose-window-audit-is-measured", str(audit.get("state") or "") == "passed",
          f"{audit.get('state')} {audit.get('detail') or audit.get('size') or ''}")
    state = None
    for _attempt in range(4):
        state = window_probe("prose")
        if state and "rows" in state:
            break
        time.sleep(3)
    state = state or {}
    check("prose-window-shows-every-project", int(state.get("rows") or 0) == len(ROSTER),
          f"{state.get('rows')} row(s) for {len(ROSTER)} project(s)")
    check("prose-window-is-in-its-own-mode", state.get("window") == "prose"
          and state.get("package") == "prose",
          f"window {state.get('window')} package {state.get('package')}")
    check("prose-window-links-every-document", int(state.get("documents") or 0) == len(ROSTER),
          f"{state.get('documents')} document link(s) for {len(ROSTER)} project(s)")
    check("prose-window-carries-the-spinner", bool(state.get("spinnerCss")),
          "the spinner's keyframes are in the signed sheet")
    check("prose-window-knows-the-driver", state.get("driver") in ("read", "blocked"),
          f"driver {state.get('driver')} · {state.get('staged')} staged")
    # The document route is the shell's, over its own origin: read one end to end.
    status, doc = (0, {})
    try:
        with urllib.request.urlopen(SHELL + "/api/toast/prose/doc/popit-shell", timeout=20) as reply:
            text = reply.read().decode("utf-8", "replace")
            status = reply.status
    except (OSError, urllib.error.URLError):
        text = ""
    check("prose-document-is-served-by-the-shell", status == 200
          and 'data-doc="prose"' in text and 'data-project="popit-shell"' in text,
          f"{status}, {len(text)} bytes")
    passed = sum(1 for entry in checks if entry["ok"])
    body = {"schema": PROBE_SCHEMA, "at": iso(), "checks": checks,
            "passed": passed, "failed": len(checks) - passed,
            "window": {"app": app.get("identity"), "audit": audit, "state": state},
            "receipt": display(PROBE_RECEIPT)}
    PROBE_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    PROBE_RECEIPT.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for entry in checks:
        print(("PASS " if entry["ok"] else "FAIL ") + entry["check"] + " · " + str(entry["detail"]))
    print(f"{passed} passed, {len(checks) - passed} failed -> {display(PROBE_RECEIPT)}")
    return 0 if passed == len(checks) else 1


def family_ratchet() -> int:
    """Read every family project with the shared checker and keep its ratchet receipt.

    The checker owns the rules and the baselines; this only runs it and records what it said, so
    the gate reads a receipt instead of running a three-minute pass on every check.
    """
    import subprocess
    # Its own receipt: the document pass owns `prose-family.json`, and one file naming two
    # readings is how a freshness row goes stale for the wrong reason.
    receipt = ROOT / "artifacts" / "receipts" / "prose-ratchet.json"
    if not FAMILY_CHECKER.is_file():
        print(f"family-checker-absent {FAMILY_CHECKER}")
        return 1
    result = subprocess.run([sys.executable, str(FAMILY_CHECKER), "--family", "--json"],
                            capture_output=True, text=True, timeout=900)
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"family-checker-output {result.stdout[:200]} {result.stderr[:200]}")
        return 1
    body["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body["checker"] = str(FAMILY_CHECKER)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"family {body.get('passed')} passed, {body.get('held')} held, "
          f"{body.get('regressed')} regressed of {body.get('checked')} -> {receipt}")
    return 0 if int(body.get("regressed") or 0) == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("run", "report", "ingest", "probe", "family"),
                        nargs="?", default="run")
    parser.add_argument("--project", action="append", default=None)
    args = parser.parse_args(argv)
    if args.command == "probe":
        return probe()
    if args.command == "family":
        return family_ratchet()
    if args.command == "ingest":
        body = ingest()
        print(json.dumps(body, indent=2)[:1200])
        return 0 if body["ok"] else 1
    body = report(tuple(args.project) if args.project else ROSTER)
    if args.command == "report":
        print(json.dumps({key: body[key] for key in ("schema", "projects", "passed", "refused",
                                                     "driver", "index")}, indent=2)[:2000])
        return 0
    for row in body["rows"]:
        state = "passed" if not row["refusal"] else f"refused {row['refusal']['code']}"
        print(f"{row['name']:<20} {state:<28} {row['visible']:>5} string(s) {row['hits']:>4} hit(s) "
              f"driver={row['driver']} doc={row['doc']}")
    print(f"{body['passed']} of {body['projects']} project(s) documented -> {body['index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
