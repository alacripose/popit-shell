#!/usr/bin/env python3
"""Fix the Debian driver's json.dumps(flush=...) crash and restart it with a receipt.

Measured on the box (2026-11-26): `$HOME/.dialin/driver.log` ends in

    File "$HOME/.dialin/driver.py", line 288, in main
        print(json.dumps({"poll": "unreadable", "detail": str(error)[:160]}, flush=True))
    TypeError: JSONEncoder.__init__() got an unexpected keyword argument 'flush'

`flush` belongs to `print`, not to `json.dumps`, so the driver died on the first poll the
desk reset. The edit is one line per occurrence and is reported as a before/after pair.

This runs **on the driver box** through `tools/bridge.py run`, because the file is there.
It keeps a timestamped copy beside the original, refuses to write anything when the pattern
does not match, and prints one JSON receipt naming the lines it changed.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import py_compile
import re

TARGET = pathlib.Path.home() / ".dialin" / "driver.py"
PATTERN = re.compile(r"print\(json\.dumps\((.*), flush=True\)\)")


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    if not TARGET.is_file():
        print(json.dumps({"ok": False, "code": "driver-absent", "path": str(TARGET)}))
        return 1
    source = TARGET.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    changed: list[dict] = []
    for index, line in enumerate(lines):
        match = PATTERN.search(line)
        if not match:
            continue
        fixed = line[:match.start()] + f"print(json.dumps({match.group(1)}), flush=True)" + line[match.end():]
        changed.append({"line": index + 1, "before": line.strip(), "after": fixed.strip()})
        lines[index] = fixed
    if not changed:
        print(json.dumps({"ok": False, "code": "pattern-absent",
                          "note": "no json.dumps(..., flush=True) print left to fix"}))
        return 1
    backup = TARGET.with_suffix(f".py.bak-{now.strftime('%Y%m%dT%H%M%SZ')}")
    backup.write_text(source, encoding="utf-8")
    TARGET.write_text("".join(lines), encoding="utf-8")
    try:
        py_compile.compile(str(TARGET), doraise=True)
    except py_compile.PyCompileError as error:
        TARGET.write_text(source, encoding="utf-8")
        print(json.dumps({"ok": False, "code": "compile-failed",
                          "detail": str(error)[:300], "restored": str(backup)}))
        return 1
    remaining = [index + 1 for index, line in enumerate(TARGET.read_text(encoding="utf-8").splitlines())
                 if "json.dumps(" in line and ", flush=True))" in line]
    receipt = {"schema": "popit.driver-fix/1", "at": now.isoformat(), "path": str(TARGET),
               "backup": str(backup), "changed": changed, "remaining": remaining,
               "compiled": True}
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
