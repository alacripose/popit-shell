"""Build the landing pages' app package store from the signed registry.

The store is not a second copy of the shell. It lists only packages signed in the reference
forms — dialin and settings as `window`, the springboard as `phone` — names the CUA driver
that developed each revision, and carries the refusal of any name that is not a signable
kind instead of inventing a row for it.

    python tools/app_store.py            # writes docs/app-store.json

Exit 0 when the store was written; a store that cannot name its driver or that meets an
unverified package refuses by name rather than publishing a shelf with holes in it.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "app-store.json"
KINDS = ("window", "phone")
NAMES = ("dialin", "settings", "prose", "springboard", "archive", "evidence")


def fetch(path: str, port: int) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as reply:
            return reply.status, json.loads(reply.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode("utf-8") or "{}")
        except (ValueError, json.JSONDecodeError):
            return error.code, {}
    except OSError as error:
        print(f"store-offline: {error}", file=sys.stderr)
        return 0, {}


def main() -> int:
    port = int(os.environ.get("POPIT_PORT") or "5207")
    status, registry = fetch("/api/toast/apps", port)
    if status != 200:
        print(f"store-offline: /api/toast/apps answered {status}", file=sys.stderr)
        return 1
    _, live = fetch("/api/toast", port)
    fleet = (live or {}).get("fleet") or {}
    drivers = [row for row in fleet.get("drivers") or [] if row.get("id")]
    tasks = [row for row in fleet.get("tasks") or [] if row.get("driver")]
    # The driver that most recently carried work, else the one the fleet would dispatch to.
    driver = (tasks[0]["driver"] if tasks else "") or (drivers[0]["id"] if drivers else "")
    if not driver:
        print("store-no-driver: no CUA driver is attached to develop or sign packages",
              file=sys.stderr)
        return 1
    apps = registry.get("apps") or {}
    rows, refusals = [], []
    for name in NAMES:
        row = apps.get(name) or {}
        kind = str(row.get("kind") or "")
        if kind not in KINDS:
            print(f"store-foreign-package: {name} is {kind or 'untyped'}, not {' or '.join(KINDS)}",
                  file=sys.stderr)
            return 1
        if not row.get("verified"):
            refused = (row.get("refused") or {}).get("code") or "unverified"
            print(f"store-unverified: {name} is refused {refused}", file=sys.stderr)
            return 1
        rows.append({
            "name": name,
            "kind": kind,
            "entry": row.get("entry", ""),
            "pages": row.get("pages", 0),
            "regions": row.get("regions", 0),
            "identity": row.get("identity", ""),
            "revision": row.get("revision", 0),
            "ui_audit": row.get("ui_audit", ""),
            "verified": True,
            "driver": row.get("driver", ""),
            "added_to_the_family": {
                "dialin": ["call desk", "lane selection", "voice document", "probe log",
                           "the bridge surface"],
                "settings": ["appearance", "motion", "layout", "apps", "functions", "device",
                             "package"],
                "prose": ["prose inventory", "per-project progress", "external document links"],
                "springboard": ["signed tiles", "app launch", "offline shell"],
                "archive": ["project index", "per-project files", "evidence state",
                            "cache clean"],
                "evidence": ["evidence root state", "copy receipts", "recorded assets",
                             "backup act"],
            }[name],
        })
    for name, row in (registry.get("foreign") or {}).items():
        refusal = row.get("refused") or {}
        refusals.append({"name": name, "kind": row.get("kind", ""),
                         "refused": {"code": refusal.get("code", ""),
                                     "detail": refusal.get("detail", "")}})
    store = {
        "schema": "popit.app-store/1",
        "store": "popit shelf · github landing pages",
        "publisher": registry.get("publisher", ""),
        "kinds": list(KINDS),
        "driver": {"id": driver, "role": next(
            (row.get("role", "") for row in drivers if row.get("id") == driver), "")},
        "generated_by": "tools/app_store.py",
        "apps": rows,
        "refused": refusals,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"store written: {len(rows)} packages, {len(refusals)} refused -> {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
