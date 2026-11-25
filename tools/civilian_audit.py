#!/usr/bin/env python3
"""Full family civilian-architecture audit with a Popit surface.

The roster is no longer five handpicked names. This tool treats the family as an
inventory: every code, document and PDF under the family Documents roots is indexed,
searched for civilian/agent/voice/call architecture terms, and assigned to a working
lane. The terminal is not the surface; the page served on loopback is, and its probe
reads the page and the served report together.

Usage:
  python tools/civilian_audit.py scan [--root DIR ...] [--max-files N]
  python tools/civilian_audit.py serve [--port 5311]
  python tools/civilian_audit.py probe [--port 5311]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "runlogs" / "civilian-audit"
INDEX = OUT / "index.jsonl"
REPORT = OUT / "report.json"
PAGE = ROOT / "tools" / "civilian_audit_ui.html"
SCHEMA = "popit.civilian-audit/1"
DEFAULT_ROOTS = [
    pathlib.Path("C:/Users/ala/Documents"),
    pathlib.Path("F:/Documents/popit-shell"),
    pathlib.Path("F:/Documents/laya-cua-agent"),
    pathlib.Path("F:/Documents/portal-shell"),
    pathlib.Path("F:/Documents/brass-meridian"),
    pathlib.Path("F:/Documents/income-engine"),
    pathlib.Path("F:/Documents/AWA3D"),
    pathlib.Path("F:/Documents/openlock_modern"),
    pathlib.Path("C:/Users/ala/Documents/ala-system"),
    pathlib.Path("C:/Users/ala/Documents/agent_god_files"),
    pathlib.Path("C:/Users/ala/Documents/openlock_modern"),
    pathlib.Path("C:/Users/ala/Documents/income-engine"),
]
ROOT_NAMES = {
    "C:/Users/ala/Documents": "family Documents",
    "F:/Documents/popit-shell": "popit-shell",
    "F:/Documents/laya-cua-agent": "laya-cua-agent",
    "F:/Documents/portal-shell": "portal-shell",
    "F:/Documents/brass-meridian": "brass-meridian",
    "F:/Documents/income-engine": "income-engine",
    "F:/Documents/AWA3D": "AWA3D",
    "F:/Documents/openlock_modern": "openlock_modern",
    "C:/Users/ala/Documents/ala-system": "ala-system",
    "C:/Users/ala/Documents/agent_god_files": "agent_god_files",
    "C:/Users/ala/Documents/openlock_modern": "openlock-modern-c",
    "C:/Users/ala/Documents/income-engine": "income-engine-c",
}
EXCLUDE_DIRS = {
    ".git", "node_modules", ".tools", ".toolchain", "__pycache__", ".venv", "venv",
    "target", "dist", "build", ".cache", "site-packages", "Models", "Saved",
    ".next", ".nuxt", ".parcel-cache", ".pytest_cache", ".mypy_cache",
    "runlogs/civilian-audit", ".cloud-attachments",
}
EXTENSIONS = {
    ".py": "code", ".js": "code", ".mjs": "code", ".cjs": "code", ".ts": "code",
    ".tsx": "code", ".jsx": "code", ".rs": "code", ".go": "code", ".c": "code",
    ".h": "code", ".cpp": "code", ".hpp": "code", ".sql": "code", ".sh": "code",
    ".ps1": "code",
    ".md": "doc", ".txt": "doc", ".rst": "doc", ".pdf": "pdf", ".html": "doc",
    ".htm": "doc", ".css": "doc",
    ".json": "data", ".yaml": "data", ".yml": "data", ".toml": "data",
    ".ini": "data", ".cfg": "data", ".xml": "data", ".csv": "data",
}
TERMS = (
    "civilian", "agent", "family", "persona", "voice", "roster", "call",
    "resident", "soul", "identity", "audit", "name", "cua", "debian", "memory",
)
TERM_RE = {term: re.compile(rf"\b{re.escape(term)}s?\b", re.I) for term in TERMS}
LANES = {
    "Buffy": "orchestration, UI, receipts and gates",
    "Qwen": "Debian host, CUA runtime and tool bridges",
    "Whisper": "listening, transcription and audio evidence",
    "Ash": "resident behaviour, voices and lived state",
    "Bram": "storage, supply, call ledger and name roster",
}
SNIPPET = re.compile(r"\S(?:.*?\S)?")
MAX_TEXT = 240_000


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:24]


def is_excluded(path: pathlib.Path, roots: list[pathlib.Path]) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    folded = str(path).replace("\\", "/")
    return "runlogs/civilian-audit" in folded or ".cloud-attachments" in folded


def collect(roots: list[pathlib.Path], max_files: int = 0) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    seen: set[str] = set()
    # A single broad root (the user's Documents) can fill a global cap before the later
    # project roots are reached. Give each root a fair share so the inventory covers
    # the family projects rather than only whichever path was walked first.
    per_root = max(200, max_files // max(1, len(roots))) if max_files else 0
    for root in roots:
        if not root.exists():
            continue
        root_found = 0
        # rglob walks excluded trees before the filter sees them (toolchains, node_modules,
        # game caches), which made the full family scan look hung. Prune directories while
        # walking so every eligible family code/doc/PDF is still reached.
        for here, dirs, files in os.walk(root, topdown=True):
            dirs[:] = [name for name in dirs
                       if name not in EXCLUDE_DIRS and name != ".cloud-attachments"]
            for name in files:
                path = pathlib.Path(here) / name
                if path.suffix.lower() not in EXTENSIONS or is_excluded(path, roots):
                    continue
                key = str(path).lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(path)
                root_found += 1
                if per_root and root_found >= per_root:
                    break
            if per_root and root_found >= per_root:
                break
    return found


def extract_pdf(path: pathlib.Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages[:80]:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(pages)[:MAX_TEXT], ""
    except Exception as error:
        return "", f"pdf:{error.__class__.__name__}:{str(error)[:140]}"


def extract_text(path: pathlib.Path, kind: str) -> tuple[str, str]:
    if kind == "pdf":
        return extract_pdf(path)
    try:
        # Read only the audit window. read_bytes() on a large artifact loads the whole
        # file before slicing and can stall the full scan on a data blob.
        with path.open("rb") as handle:
            data = handle.read(MAX_TEXT * 4)
        for encoding in ("utf-8", "utf-16", "cp1252"):
            try:
                return data.decode(encoding, "replace")[:MAX_TEXT], ""
            except UnicodeError:
                continue
        return data.decode("utf-8", "replace")[:MAX_TEXT], ""
    except OSError as error:
        return "", f"read:{error.__class__.__name__}:{str(error)[:120]}"


def row_for(path: pathlib.Path, roots: list[pathlib.Path]) -> dict:
    kind = EXTENSIONS[path.suffix.lower()]
    text, error = extract_text(path, kind)
    counts = {term: len(TERM_RE[term].findall(text)) for term in TERMS}
    matched = sum(counts.values())
    snippets = []
    if matched:
        for term in TERMS:
            for match in list(TERM_RE[term].finditer(text))[:2]:
                start = max(0, match.start() - 90)
                end = min(len(text), match.end() + 150)
                snippets.append({
                    "term": term,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "text": " ".join(text[start:end].split()),
                })
                if len(snippets) >= 4:
                    break
            if len(snippets) >= 4:
                break
    return {
        "path": str(path),
        "root": next((ROOT_NAMES.get(str(root), root.name)
                      for root in roots if str(path).startswith(str(root))), "other"),
        "kind": kind,
        "bytes": path.stat().st_size,
        "chars": len(text),
        "digest": sha(text),
        "terms": {term: count for term, count in counts.items() if count},
        "matches": matched,
        "snippets": snippets,
        "error": error,
    }


def scan(roots: list[pathlib.Path], max_files: int = 0) -> dict:
    started = time.monotonic()
    paths = collect(roots, max_files=max_files)
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    errors: list[dict] = []
    print(f"audit collecting {len(paths)} files", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(row_for, path, roots): path for path in paths}
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            path = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {"path": str(path), "kind": EXTENSIONS.get(path.suffix.lower(), "other"),
                       "matches": 0, "terms": {}, "snippets": [],
                       "error": f"row:{error.__class__.__name__}:{str(error)[:120]}"}
            rows.append(row)
            if row.get("error"):
                errors.append({"path": row["path"], "error": row["error"]})
            if done % 1000 == 0:
                print(f"audit {done}/{len(paths)} files", flush=True)
    rows.sort(key=lambda row: row["path"].lower())
    with INDEX.open("w", encoding="utf-8") as log:
        for row in rows:
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
    totals = {
        "files": len(rows),
        "code": sum(1 for row in rows if row["kind"] == "code"),
        "docs": sum(1 for row in rows if row["kind"] == "doc"),
        "pdfs": sum(1 for row in rows if row["kind"] == "pdf"),
        "data": sum(1 for row in rows if row["kind"] == "data"),
        "bytes": sum(int(row.get("bytes") or 0) for row in rows),
        "chars": sum(int(row.get("chars") or 0) for row in rows),
        "matching_files": sum(1 for row in rows if row.get("matches")),
        "errors": len(errors),
        "seconds": round(time.monotonic() - started, 2),
    }
    terms = {term: 0 for term in TERMS}
    for row in rows:
        for term, count in (row.get("terms") or {}).items():
            if term in terms:
                terms[term] += int(count)
    projects: dict[str, dict] = {}
    for row in rows:
        root = row.get("root") or "other"
        item = projects.setdefault(root, {"root": root, "files": 0, "matches": 0})
        item["files"] += 1
        item["matches"] += int(row.get("matches") or 0)
    findings = sorted(
        (row for row in rows if row.get("matches")),
        key=lambda row: (-int(row["matches"]), row["path"]),
    )[:36]
    report = {
        "schema": SCHEMA,
        "scanned_at": iso(),
        "roots": [str(root) for root in roots],
        "index": str(INDEX),
        "totals": totals,
        "terms": terms,
        "projects": sorted(projects.values(), key=lambda item: -item["files"]),
        "findings": [{
            "path": row["path"], "kind": row["kind"], "matches": row["matches"],
            "terms": row["terms"], "snippets": row["snippets"],
        } for row in findings],
        "errors": errors[:80],
        "lanes": [{"name": name, "work": work} for name, work in LANES.items()],
        "coverage": "code, docs, PDFs and structured data under the family Documents roots",
        "civilian": feature_inventory(),
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def feature_inventory() -> dict:
    """Read the running civilian register without starting the Toast server."""
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import civilian_features
        import civilian_scope
        rows = [
            {"id": feature, "source": source, "evidence": evidence, "detail": detail}
            for feature, source, evidence, detail in civilian_features.FEATURES
        ]
        scope = civilian_scope.state()
        return {
            "features": rows, "count": len(rows),
            "operation": {
                "schema": civilian_features.OPERATION_SCHEMA,
                "preflight": hasattr(civilian_features.CivilianDesk, "operation"),
                "record": hasattr(civilian_features.CivilianDesk, "record_operation"),
            },
            "scope": {
                "schema": scope["schema"], "counts": scope["counts"],
                "errors": scope["errors"],
                "blocked": [row["id"] for row in scope["blocked"]],
                "partial": [row["id"] for row in scope["partial"]],
            },
        }
    except Exception as error:
        return {"features": [], "count": 0, "scope": {"counts": {}, "errors": [str(error)]},
                "error": f"{error.__class__.__name__}:{str(error)[:160]}"}


def report() -> dict:
    if not REPORT.exists():
        return {"schema": SCHEMA, "scanned_at": "", "totals": {"files": 0}, "terms": {},
                "projects": [], "findings": [], "errors": [], "lanes": [],
                "coverage": "no scan yet", "civilian": feature_inventory()}
    return json.loads(REPORT.read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "popit-civilian-audit/1"

    def log_message(self, fmt, *args):
        return

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] in {"/", "/index.html"}:
            body = PAGE.read_text(encoding="utf-8").encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if self.path.split("?")[0] == "/report.json":
            body = json.dumps(report(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return
        self._send(404, b'{"ok":false,"refused":{"code":"audit-route"}}',
                   "application/json; charset=utf-8")

    def do_POST(self):
        if self.path.split("?")[0] != "/scan":
            self._send(404, b'{"ok":false,"refused":{"code":"audit-route"}}',
                       "application/json; charset=utf-8")
            return
        threading.Thread(target=scan, args=(DEFAULT_ROOTS,), daemon=True).start()
        self._send(202, b'{"ok":true,"state":"scanning"}', "application/json; charset=utf-8")


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"civilian audit on http://127.0.0.1:{port}/", flush=True)
    server.serve_forever()


def probe(port: int) -> int:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    checks: list[dict] = []
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=8).read().decode("utf-8")
        served = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/report.json",
                                                   timeout=8).read().decode("utf-8"))
        checks = [
            {"name": "popit-surface", "ok": 'data-popit="civilian-audit"' in page},
            {"name": "summary", "ok": 'id="audit-summary"' in page},
            {"name": "lanes", "ok": 'id="audit-lanes"' in page},
            {"name": "findings", "ok": 'id="audit-findings"' in page},
            {"name": "report-schema", "ok": served.get("schema") == SCHEMA},
            {"name": "report-has-files", "ok": int((served.get("totals") or {}).get("files") or 0) > 0},
            {"name": "feature-register", "ok": int((served.get("civilian") or {}).get("count") or 0) >= 17},
            {"name": "scope-complete", "ok": int((((served.get("civilian") or {}).get("scope") or {}).get("counts") or {}).get("total") or 0) >= 40},
            {"name": "scope-evidence", "ok": not ((((served.get("civilian") or {}).get("scope") or {}).get("errors") or []))},
            {"name": "scope-blocked-named", "ok": bool((((served.get("civilian") or {}).get("scope") or {}).get("blocked")))},
            {"name": "operation-preflight", "ok": all(
                (((served.get("civilian") or {}).get("operation") or {}).get(key))
                for key in ("preflight", "record"))},
        ]
    finally:
        server.shutdown()
        server.server_close()
    receipt = {"schema": SCHEMA + "/probe", "at": iso(), "port": port,
               "ok": all(check["ok"] for check in checks), "checks": checks}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "popit-probe.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("scan", "serve", "probe"))
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--port", type=int, default=5311)
    args = parser.parse_args()
    roots = [pathlib.Path(value) for value in args.root] if args.root else DEFAULT_ROOTS
    if args.command == "scan":
        result = scan(roots, max_files=args.max_files)
        print(json.dumps(result["totals"], indent=2))
        return 0
    if args.command == "serve":
        serve(args.port)
        return 0
    return probe(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
