"""The session archive and its evidence backup: the data layer two desk apps read.

The legacy shell shipped one loopback page, `ui/archive.html`, that polled a route the
server never answered, and the shell's own server pointed `/api/archive/*` at functions
that had been dropped. The rows below are that page's subject, rebuilt where the desk can
sign it: an index of the projects on every local drive, the evidence copy compared with
each project, and the family cache rule.

Three owner rules shape it:

* **The apps are the desk's.** `app_package.APPS` serves `archive` and `evidence` as windows
  built from the settings window's signed baseline; this module only answers their rows.
* **A row says what was measured.** A drive that could not be read, a project that does not
  fit the copy budget and an evidence root that is absent are named refusals, never an empty
  field. Every act appends a row to `runlogs/session-archive/ledger.jsonl`.
* **The family cache rule is the only thing a clean removes.** `__pycache__`,
  `.pytest_cache`, `.mypy_cache` and `.ruff_cache`, listed first and removed only when the
  window sends its second confirmation.

    python -m session_archive state        # what the two windows read
    python -m session_archive rescan       # walk every local drive and cache the index
"""
from __future__ import annotations

import ctypes
import datetime
import json
import os
import pathlib
import shutil
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent
LEDGER = ROOT / "runlogs" / "session-archive" / "ledger.jsonl"
INDEX = ROOT / "runlogs" / "session-archive" / "index.json"
SCHEMA = "popit.session-archive/1"
INDEX_SCHEMA = "popit.session-archive-index/1"
INDEX_MAX_AGE = 3600
# Per drive, not per walk: a shared budget stopped after 6060 directories inside C: and the
# window then reported 8 projects for a machine with six drives. The ceiling that matters is
# time, so a slow drive is named as timed out instead of silently cutting every later drive.
MAX_DIRECTORIES = 400000
WALK_SECONDS = 300.0
MAX_FILES_PER_PROJECT = 20000   # counted, not stored: a row is a summary
MAX_COPY_FILES = 400            # per project, per backup
MAX_COPY_BYTES = 40 * 1024 * 1024
MAX_ASSET_BYTES = 8 * 1024 * 1024
# The family cache rule, exactly four names.
CACHE_DIRS = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
# Trees that are not a project's own files: an OS, a package store, a build output, a VCS
# database or a cache. The index excludes them at any depth rather than counting them.
EXCLUDED = {
    "Windows", "Program Files", "Program Files (x86)", "ProgramData", "$Recycle.Bin",
    "System Volume Information", "Recovery", "PerfLogs", "node_modules", ".git", ".hg",
    ".svn", ".venv", "venv", "env", "site-packages", "dist", "build", "target",
    ".next", ".nuxt", ".cache", ".gradle", ".idea", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "AppData", "Application Data", "Packages",
    ".local", ".cargo", ".rustup", ".npm", ".bun", ".deno", ".conda", "wheels",
}
MARKERS = ("AGENTS.md", "CLAUDE.md", ".git", "pyproject.toml", "package.json",
           "Cargo.toml", "go.mod", "requirements.txt", "setup.py", "Makefile",
           "CMakeLists.txt", "*.sln", "*.csproj")
# The exact-name markers, for counting project roots a walk passes through. A wildcard marker
# cannot be counted without a second stat, and the whole point is that counting is nearly free.
MARKER_NAMES = frozenset(marker for marker in MARKERS if not marker.startswith("*"))
# A junction is the same bytes under a second name: a profile's `Templates` and `Start Menu` are
# reparse points, and reading them reported six PermissionErrors on the surface for nothing.
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
SOURCE_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css",
    ".scss", ".json", ".jsonl", ".md", ".txt", ".toml", ".yml", ".yaml", ".ini",
    ".cfg", ".sh", ".ps1", ".cmd", ".bat", ".sql", ".rs", ".go", ".c", ".h", ".cpp",
    ".hpp", ".cs", ".lua", ".gd", ".vue", ".svelte", ".svg", ".gradle", ".lock",
    ".csv", ".tsv", ".xml", ".ipynb", ".mjs", ".proto",
}
RECORD_SUFFIXES = {".md", ".json", ".jsonl", ".txt", ".csv", ".log", ".yml", ".yaml"}
EVIDENCE_ROOT = pathlib.Path(
    os.environ.get("POPIT_EVIDENCE_ROOT") or r"F:\Documents\_evidence-archive")

LOCK = threading.RLock()
_CACHE: dict = {}
_BUILD = {"running": False, "started": 0.0}
_INDEX_LOCK = threading.Lock()


class Refused(Exception):
    """A named refusal; an act that cannot be shown is named, never answered empty."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


# Codes an act writes about itself. They name what the program did, so the family failure
# sweep must not count them as refusals: a walk that started is not a walk that was refused.
ACT_CODES = frozenset({"archive-index-started", "archive-index-done"})


def ledger(kind: str, code: str = "", **fields) -> dict:
    """Append one row the program wrote about its own act."""
    row = {"schema": SCHEMA, "at": iso(), "kind": kind, "code": code,
           "app": "session-archive"}
    # A row that names a refusal says so in a field every family reader already knows, so
    # the failure sweep counts an app's refusal instead of passing it over as a plain act.
    # An act code is not a refusal: the index walk writes its own start and end here.
    row["result"] = "refused" if code and code not in ACT_CODES else "recorded"
    row.update({key: value for key, value in fields.items() if value is not None})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as log:
        log.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def ledger_tail(limit: int = 8) -> list[dict]:
    if not LEDGER.is_file():
        return []
    rows: list[dict] = []
    try:
        for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    except OSError:
        return []
    return rows[-limit:]


# -- roots and the walk ---------------------------------------------------------------
def _windows_drives() -> list[pathlib.Path]:
    """Every fixed or removable drive letter, read from the platform, never assumed."""
    kernel32 = ctypes.windll.kernel32
    mask = int(kernel32.GetLogicalDrives())
    roots: list[pathlib.Path] = []
    for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        if not mask & (1 << index):
            continue
        name = f"{letter}:\\"
        if int(kernel32.GetDriveTypeW(ctypes.c_wchar_p(name))) in (2, 3, 4):
            roots.append(pathlib.Path(name))
    return roots


def roots() -> list[pathlib.Path]:
    override = os.environ.get("POPIT_ARCHIVE_ROOTS")
    if override:
        return [pathlib.Path(part) for part in override.split(os.pathsep) if part.strip()]
    if os.name == "nt":
        try:
            return _windows_drives()
        except (AttributeError, OSError):
            pass
    return [pathlib.Path("/")]


def slug_for(path: pathlib.Path) -> str:
    text = str(path).replace("\\", "/").strip("/")
    return "".join(char if char.isalnum() else "-" for char in text).strip("-").lower()[:80]


def _is_marker(entry: os.DirEntry) -> bool:
    for marker in MARKERS:
        if marker.startswith("*"):
            if entry.name.lower().endswith(marker[1:].lower()):
                return True
        elif entry.name == marker:
            return True
    return False


def _marker_name(path: pathlib.Path) -> str:
    for marker in MARKERS:
        if marker.startswith("*"):
            if any(child.name.lower().endswith(marker[1:].lower()) for child in path.iterdir()):
                return marker
        elif (path / marker).exists():
            return marker
    return ""


def _is_reparse(entry: os.DirEntry) -> bool:
    try:
        return bool(entry.stat(follow_symlinks=False).st_file_attributes
                    & FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def _walk_project(path: pathlib.Path, budget: dict, deadline: float = 0.0) -> dict:
    """Count a folder's files, its family cache bytes, and the project roots inside it."""
    files = 0
    total = 0
    cache_bytes = 0
    cache_dirs = 0
    nested_projects = 0
    stack = [path]
    while stack:
        folder = stack.pop()
        budget["directories"] += 1
        if budget["directories"] > MAX_DIRECTORIES:
            budget["truncated"] = True
            break
        if deadline and time.time() > deadline:
            budget["timed_out"] = True
            break
        if folder.name in CACHE_DIRS and folder is not path:
            cache_dirs += 1
            for child in folder.rglob("*"):
                try:
                    if child.is_file():
                        cache_bytes += child.stat().st_size
                except OSError:
                    continue
            continue
        try:
            entries = list(os.scandir(folder))
        except OSError as error:
            budget["errors"].append(f"{folder}: {error.__class__.__name__}")
            continue
        if any(entry.name in MARKER_NAMES for entry in entries):
            nested_projects += 1
        for entry in entries:
            if entry.name in MARKER_NAMES:
                continue
            if entry.is_dir(follow_symlinks=False):
                if _is_reparse(entry):
                    continue
                if entry.name in EXCLUDED or entry.name in CACHE_DIRS:
                    if entry.name in CACHE_DIRS:
                        cache_dirs += 1
                        for child in pathlib.Path(entry.path).rglob("*"):
                            try:
                                if child.is_file():
                                    cache_bytes += child.stat().st_size
                            except OSError:
                                continue
                    continue
                stack.append(pathlib.Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                files += 1
                if files > MAX_FILES_PER_PROJECT:
                    # The cap bounds the count, never the bytes: the size is already in hand from
                    # the stat, and skipping it made C:\Users read 17 GB against a measured 197.
                    budget["file_capped"] = True
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
        if files > MAX_FILES_PER_PROJECT and not stack:
            break
    return {"files": files, "bytes": total, "cache_bytes": cache_bytes,
            "cache_dirs": cache_dirs, "nested_projects": nested_projects}


def _classify(path: pathlib.Path, budget: dict, deadline: float = 0.0) -> dict:
    """One row per top-level folder: a project when a marker exists, a folder otherwise."""
    markers: list[str] = []
    probe = path
    depth = 0
    while probe != probe.parent and depth < 6:
        try:
            found = _marker_name(probe)
        except OSError:
            found = ""
        if found:
            markers.append(found)
            break
        probe = probe.parent
        depth += 1
    if not markers:
        # The marker may be one level down (a repository holding a single project).
        try:
            for child in list(os.scandir(path))[:80]:
                if child.is_dir(follow_symlinks=False) and child.name not in EXCLUDED:
                    try:
                        found = _marker_name(pathlib.Path(child.path))
                    except OSError:
                        found = ""
                    if found:
                        markers.append(found)
                        path = pathlib.Path(child.path)
                        break
        except OSError:
            pass
    counted = _walk_project(path, budget, deadline)
    return {
        "slug": slug_for(path),
        "name": path.name or str(path),
        "root": str(path),
        "kind": "project" if markers else "folder",
        "marker": markers[0] if markers else "",
        **counted,
    }


def _build() -> dict:
    """One pass over every drive, each with its own directory budget and time ceiling.

    A shared budget is what made this index lie: it stopped inside C: after 6060 directories
    and every later drive was never walked at all. Each root now carries its own budget and
    its own deadline, and the row it leaves says whether that drive was read or cut short.
    """
    rows: list[dict] = []
    detail: list[dict] = []
    started = time.time()
    scanned: list[str] = []
    errors: list[str] = []
    for root in roots():
        scanned.append(str(root))
        budget = {"directories": 0, "truncated": False, "timed_out": False,
                  "file_capped": False, "errors": []}
        deadline = time.time() + WALK_SECONDS
        root_started = time.time()
        try:
            entries = list(os.scandir(root))
        except OSError as error:
            rows.append({"slug": slug_for(root), "name": str(root), "root": str(root),
                         "kind": "refused", "marker": "",
                         "refusal": {"code": "archive-root-unreadable",
                                     "detail": f"{root}: {error.__class__.__name__}"},
                         "files": 0, "bytes": 0, "cache_bytes": 0, "cache_dirs": 0})
            errors.append(f"{root}: {error.__class__.__name__}")
            detail.append({"root": str(root), "read": False, "directories": 0,
                           "projects": 0, "truncated": False, "timed_out": False,
                           "seconds": 0.0,
                           "refusal": "archive-root-unreadable"})
            continue
        loose = {"files": 0, "bytes": 0}
        projects = 0
        for entry in entries:
            if entry.name in EXCLUDED or entry.name in CACHE_DIRS or entry.name.startswith("$"):
                continue
            if _is_reparse(entry):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    row = _classify(pathlib.Path(entry.path), budget, deadline)
                    if row["kind"] == "project":
                        projects += 1
                    rows.append(row)
                elif entry.is_file(follow_symlinks=False):
                    loose["files"] += 1
                    loose["bytes"] += entry.stat().st_size
            except OSError:
                continue
        if loose["files"]:
            rows.append({"slug": slug_for(root / "loose"), "name": f"{root} files",
                         "root": str(root), "kind": "loose", "marker": "",
                         "files": loose["files"], "bytes": loose["bytes"],
                         "cache_bytes": 0, "cache_dirs": 0})
        errors.extend(budget["errors"])
        detail.append({"root": str(root), "read": True,
                       "directories": budget["directories"], "projects": projects,
                       "truncated": budget["truncated"],
                       "timed_out": budget["timed_out"],
                       "file_capped": budget["file_capped"],
                       "seconds": round(time.time() - root_started, 1),
                       "refusal": "archive-walk-truncated" if budget["truncated"]
                                  else "archive-walk-timed-out" if budget["timed_out"] else ""})
    rows.sort(key=lambda row: (row["kind"] != "project", row["name"].lower()))
    body = {
        "schema": INDEX_SCHEMA,
        "at": iso(),
        "seconds": round(time.time() - started, 1),
        "roots": scanned,
        "roots_detail": detail,
        "directories": sum(item["directories"] for item in detail),
        "projects": sum(1 for row in rows if row["kind"] == "project"),
        "rows": rows,
        "truncated": any(item["truncated"] for item in detail),
        "timed_out": any(item["timed_out"] for item in detail),
        "errors": errors[:20],
    }
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return body


def _background() -> None:
    try:
        body = _build()
        with LOCK:
            _CACHE.clear()
            _CACHE.update(body)
        # The walk says how it ended, so the window reads a finished pass rather than inferring
        # one from a row that only says it started.
        ledger("index", "archive-index-done", seconds=body["seconds"],
               projects=body["projects"], directories=body["directories"],
               truncated=body["truncated"], timed_out=body["timed_out"],
               roots=len(body["roots"]))
    except Exception as error:  # noqa: BLE001 - a walk that dies names itself, never silently
        ledger("index", "archive-index-failed", detail=error.__class__.__name__)
    finally:
        with LOCK:
            _BUILD["running"] = False


def _cached() -> dict | None:
    if _CACHE:
        return _CACHE
    try:
        body = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("rows"), list):
        return None
    _CACHE.update(body)
    return _CACHE


def ensure_index(force: bool = False) -> dict:
    """Read the cached walk, or start one; a full pass never runs inside the request."""
    with _INDEX_LOCK:
        if force:
            _CACHE.clear()
        cached = _cached()
        age = time.time() - INDEX.stat().st_mtime if INDEX.is_file() else 10**6
        if cached and not force and age < INDEX_MAX_AGE:
            with LOCK:
                cached["state"] = "ready"
                cached["age"] = round(age, 1)
                cached["building"] = _BUILD["running"]
            return cached
        if not _BUILD["running"]:
            _BUILD.update({"running": True, "started": time.time()})
            ledger("index", "archive-index-started", detail="a walk of every local drive")
            threading.Thread(target=_background, daemon=True).start()
        body = dict(cached or {"schema": INDEX_SCHEMA, "rows": [], "roots": [],
                               "directories": 0, "projects": 0, "truncated": False})
        body.update({"state": "indexing" if cached is None else "stale",
                     "age": round(age, 1) if cached else 0,
                     "building": True})
        return body


def _row(slug: str) -> dict:
    body = _cached() or {}
    for row in body.get("rows") or []:
        if row.get("slug") == slug:
            return row
    ledger("refusal", "archive-unknown-project", slug=slug or "no slug")
    raise Refused("archive-unknown-project", slug or "no slug")


# -- evidence -------------------------------------------------------------------------
def _evidence_rows() -> list[dict]:
    rows = []
    if not EVIDENCE_ROOT.is_dir():
        return rows
    try:
        for entry in EVIDENCE_ROOT.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            receipt = {}
            try:
                receipt = json.loads((entry / "_receipt.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                receipt = {}
            rows.append({"slug": entry.name, "root": str(entry),
                         "at": str(receipt.get("at") or ""),
                         "copied": int(receipt.get("copied") or 0),
                         "recorded": int(receipt.get("recorded") or 0),
                         "bytes": int(receipt.get("bytes") or 0),
                         "state": "current" if receipt else "unrecorded"})
    except OSError as error:
        return [{"slug": "", "root": str(EVIDENCE_ROOT), "state": "refused",
                 "refusal": {"code": "archive-evidence-unreadable",
                             "detail": error.__class__.__name__}}]
    return sorted(rows, key=lambda row: row["slug"])


def evidence_state() -> dict:
    free = 0
    exists = EVIDENCE_ROOT.is_dir()
    if exists:
        try:
            free = shutil.disk_usage(EVIDENCE_ROOT).free
        except OSError:
            free = 0
    return {"root": str(EVIDENCE_ROOT), "exists": exists, "free_bytes": free,
            "rows": _evidence_rows()}


def _copy_plan(folder: pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Source and record files to copy; assets recorded by size and time instead."""
    copy: list[pathlib.Path] = []
    assets: list[pathlib.Path] = []
    for current, folders, names in os.walk(folder):
        folders[:] = [name for name in folders
                      if name not in EXCLUDED and name not in CACHE_DIRS]
        for name in names:
            path = pathlib.Path(current) / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if path.suffix.lower() in SOURCE_SUFFIXES and size <= MAX_ASSET_BYTES:
                copy.append(path)
            elif path.suffix.lower() not in SOURCE_SUFFIXES and size > MAX_ASSET_BYTES:
                assets.append(path)
            elif path.suffix.lower() in RECORD_SUFFIXES:
                copy.append(path)
        if len(copy) > MAX_COPY_FILES:
            break
    return copy, assets


def start_backup(slugs: list[str], *, all_projects: bool = False,
                 mode: str = "evidence") -> dict:
    """Copy each project's source and record files beside it, and say what was copied."""
    if mode not in ("evidence", "full"):
        raise Refused("archive-backup-mode", mode)
    body = ensure_index()
    rows = body.get("rows") or []
    if all_projects:
        targets = [row for row in rows if row.get("kind") == "project"]
    else:
        targets = [_row(slug) for slug in slugs if slug]
    if not targets:
        ledger("backup", "archive-backup-none", detail="no project was selected")
        raise Refused("archive-backup-none", "no project was selected")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    receipts = []
    for row in targets:
        source = pathlib.Path(str(row.get("root") or ""))
        if not source.is_dir():
            receipts.append({"slug": row.get("slug"), "state": "refused",
                             "refusal": {"code": "archive-root-absent", "detail": str(source)}})
            continue
        copy, assets = _copy_plan(source)
        target = EVIDENCE_ROOT / str(row.get("slug") or slug_for(source))
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        size = 0
        for path in copy[:MAX_COPY_FILES]:
            try:
                relative = path.relative_to(source)
            except ValueError:
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, destination)
            except OSError:
                continue
            copied += 1
            try:
                size += path.stat().st_size
            except OSError:
                pass
            if size > MAX_COPY_BYTES:
                break
        recorded = [{"name": path.name, "bytes": path.stat().st_size,
                     "at": iso_for(path)} for path in assets[:200]
                    if path.exists()]
        receipt = {"schema": SCHEMA, "at": iso(), "project": source.name,
                   "slug": str(row.get("slug") or ""), "mode": mode,
                   "copied": copied, "recorded": len(recorded),
                   "bytes": size, "bounded": len(copy) > MAX_COPY_FILES,
                   "assets": recorded}
        (target / "_receipt.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ledger("backup", "", slug=str(row.get("slug") or ""), copied=copied,
               recorded=len(recorded), bytes=size)
        receipts.append({"slug": receipt["slug"], "state": "copied", "copied": copied,
                         "recorded": len(recorded), "bytes": size,
                         "bounded": receipt["bounded"]})
    return {"schema": SCHEMA, "at": iso(), "mode": mode,
            "root": str(EVIDENCE_ROOT), "rows": receipts}


def iso_for(path: pathlib.Path) -> str:
    try:
        stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime,
                                                datetime.timezone.utc)
    except OSError:
        return ""
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# -- cleaning -------------------------------------------------------------------------
def _cache_dirs(folder: pathlib.Path) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for current, folders, _names in os.walk(folder):
        keep = []
        for name in folders:
            path = pathlib.Path(current) / name
            if name in CACHE_DIRS:
                found.append(path)
            elif name not in EXCLUDED:
                keep.append(name)
        folders[:] = keep
    return found


def clean(slug: str, apply: bool = False) -> dict:
    """The family cache rule: list the four cache trees, remove them only when confirmed."""
    row = _row(slug)
    folder = pathlib.Path(str(row.get("root") or ""))
    if not folder.is_dir():
        raise Refused("archive-root-absent", str(folder))
    found = _cache_dirs(folder)
    files = 0
    size = 0
    for path in found:
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    files += 1
                    size += child.stat().st_size
            except OSError:
                continue
    removed = 0
    if apply:
        if not found:
            ledger("clean", "", slug=slug, removed=0, files=0, bytes=0)
            return {"slug": slug, "applied": True, "dirs": 0, "files": 0, "bytes": 0,
                    "removed": 0, "detail": "no cache tree was present"}
        for path in found[:400]:
            try:
                shutil.rmtree(path)
                removed += 1
            except OSError:
                continue
        ledger("clean", "", slug=slug, removed=removed, files=files, bytes=size)
    return {"slug": slug, "applied": bool(apply), "dirs": len(found), "files": files,
            "bytes": size, "removed": removed,
            "rule": list(CACHE_DIRS),
            "detail": "" if apply else "a second confirmation removes only these trees"}


def files(slug: str, limit: int = 400) -> dict:
    row = _row(slug)
    folder = pathlib.Path(str(row.get("root") or ""))
    if not folder.is_dir():
        raise Refused("archive-root-absent", str(folder))
    rows = []
    for current, folders, names in os.walk(folder):
        folders[:] = [name for name in folders
                      if name not in EXCLUDED and name not in CACHE_DIRS]
        for name in names:
            path = pathlib.Path(current) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            rows.append({"name": str(path.relative_to(folder)).replace("\\", "/"),
                         "bytes": stat.st_size, "at": iso_for(path)})
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    return {"schema": SCHEMA, "slug": slug, "project": row.get("name"),
            "root": str(folder), "files": rows, "limit": limit,
            "truncated": len(rows) >= limit}


def show(slug: str, which: str = "project", path: str = "") -> dict:
    """Open a folder in Explorer. Only the project's root, its copy, or the evidence root."""
    if not slug and which == "evidence":
        if not EVIDENCE_ROOT.is_dir():
            raise Refused("archive-evidence-absent", str(EVIDENCE_ROOT))
        os.startfile(str(EVIDENCE_ROOT))  # noqa: S606 - the window asked for this folder
        ledger("show", "", slug="", which="evidence", path=str(EVIDENCE_ROOT))
        return {"slug": "", "opened": str(EVIDENCE_ROOT), "which": "evidence"}
    row = _row(slug)
    project = pathlib.Path(str(row.get("root") or ""))
    root = project if which == "project" else EVIDENCE_ROOT / slug
    target = (root / path).resolve() if path else root
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise Refused("archive-path-outside", str(path)[:120]) from error
    if not target.exists():
        raise Refused("archive-path-absent", str(target))
    os.startfile(str(target))  # noqa: S606 - the window asked for this folder
    ledger("show", "", slug=slug, which=which, path=str(target))
    return {"slug": slug, "opened": str(target), "which": which}


# -- what the two windows read ---------------------------------------------------------
def state() -> dict:
    body = ensure_index()
    rows = []
    evidence = {row["slug"]: row for row in _evidence_rows()}
    for row in body.get("rows") or []:
        copy = evidence.get(str(row.get("slug")))
        rows.append({
            "slug": row.get("slug", ""),
            "name": row.get("name", ""),
            "root": row.get("root", ""),
            "kind": row.get("kind", ""),
            "marker": row.get("marker", ""),
            "files": int(row.get("files") or 0),
            "bytes": int(row.get("bytes") or 0),
            "cache_bytes": int(row.get("cache_bytes") or 0),
            "cache_dirs": int(row.get("cache_dirs") or 0),
            "nested_projects": int(row.get("nested_projects") or 0),
            "refusal": row.get("refusal") or None,
            "evidence": "backed" if copy and copy.get("state") == "current"
                        else "recorded" if copy else "none",
        })
    # A project is a row that is a project root, plus every project root a folder contains: C:\
    # reported 0 projects while holding most of the family, because its projects are nested.
    projects = sum(1 for row in rows if row["kind"] == "project") + sum(
        row["nested_projects"] for row in rows if row["kind"] != "project")
    return {
        "schema": SCHEMA,
        "at": iso(),
        "app": "session-archive",
        "index": {
            "state": body.get("state") or "ready",
            "building": bool(body.get("building")),
            "at": body.get("at", ""),
            "age": body.get("age", 0),
            "roots": body.get("roots") or [],
            "roots_detail": body.get("roots_detail") or [],
            "directories": int(body.get("directories") or 0),
            "projects": projects,
            "truncated": bool(body.get("truncated")),
            "timed_out": bool(body.get("timed_out")),
            "seconds": body.get("seconds", 0),
            "errors": body.get("errors") or [],
            "max_age": INDEX_MAX_AGE,
            "max_directories": MAX_DIRECTORIES,
            "walk_seconds": WALK_SECONDS,
        },
        "evidence": evidence_state(),
        "cache_rule": list(CACHE_DIRS),
        "rows": rows,
        "ledger": ledger_tail(),
    }


def main(argv: list[str]) -> int:
    action = argv[1] if len(argv) > 1 else "state"
    if action == "rescan":
        # A rescan from the command line is the walk itself. The request path starts a background
        # thread and answers "indexing"; a short-lived process that did the same printed a state
        # and exited before the walk it had just announced wrote anything.
        body = _build()
        with LOCK:
            _CACHE.clear()
            _CACHE.update(body)
        ledger("index", "archive-index-done", seconds=body["seconds"],
               projects=body["projects"], directories=body["directories"],
               truncated=body["truncated"], timed_out=body["timed_out"],
               roots=len(body["roots"]))
        print(json.dumps({key: value for key, value in body.items() if key != "rows"},
                         indent=2))
        return 0
    if action == "state":
        body = state()
        print(json.dumps({"index": body["index"], "evidence": {
            "root": body["evidence"]["root"], "exists": body["evidence"]["exists"]},
            "rows": len(body["rows"]), "projects": body["index"]["projects"]}, indent=2))
        return 0
    if action == "ledger":
        print(json.dumps(ledger_tail(20), indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
