"""Put the driver's DialIn client and the tell lexicon on the Debian box.

The bridge carries one command per run, and a 60 KiB lexicon does not fit in one command line,
so the files travel as base64 in bounded chunks. Both ends are measured: the SHA-256 of what the
box now holds is printed next to the local digest, and a mismatch is a refusal rather than a
silent half-write.

    python tools/dialin_push.py --check     # compare digests only
    python tools/dialin_push.py             # write both files and compare digests
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAMILY = ROOT.parent / "portal-shell" / "tools" / "ui_prose.py"
BRIDGE = ROOT.parent / "mc3-client13" / "tools" / "bridge.py"
SHELL = ROOT.parent / "portal-shell" / "tools" / "prose-tells.json"
DRIVER = ROOT / "tools" / "dialin_driver.py"
RINGER = ROOT / "tools" / "dialin_ring.py"
REMOTE = {"driver": "~/.dialin/driver.py", "tells": "~/.dialin/tells.json",
          "ringer": "~/.dialin/ringer.py"}
CHUNK = 28000


def bridge(command: str, timeout: int = 120) -> str:
    run = subprocess.run([sys.executable, str(BRIDGE), "run", "--", command],
                         capture_output=True, text=True, timeout=timeout, cwd=str(BRIDGE.parents[1]))
    text = (run.stdout or "") + (run.stderr or "")
    if run.returncode != 0:
        raise SystemExit(f"bridge refused: {text.strip()[-400:]}")
    return text


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def remote_digest(path: str) -> str:
    try:
        text = bridge(f"sha256sum {path} 2>/dev/null | cut -d' ' -f1")
    except SystemExit:
        return ""
    return "".join(text.split()[:1])


def push(name: str, source: pathlib.Path) -> dict:
    data = source.read_bytes()
    local = digest(data)
    target = REMOTE[name]
    if remote_digest(target) == local:
        return {"file": name, "digest": local, "state": "present"}
    encoded = base64.b64encode(data).decode("ascii")
    carried = target + ".b64"
    bridge(f"mkdir -p ~/.dialin && : > {carried}")
    for start in range(0, len(encoded), CHUNK):
        piece = encoded[start:start + CHUNK]
        bridge(f"printf %s '{piece}' >> {carried}")
    bridge(f"base64 -d {carried} > {target} && rm -f {carried} && chmod 600 {target}")
    seen = remote_digest(target)
    return {"file": name, "digest": local, "remote": seen,
            "state": "written" if seen == local else "mismatch"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dialin_push", description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rows = []
    for name, source in (("driver", DRIVER), ("tells", SHELL), ("ringer", RINGER)):
        if args.check:
            rows.append({"file": name, "digest": digest(source.read_bytes()),
                         "remote": remote_digest(REMOTE[name])})
        else:
            rows.append(push(name, source))
    print(json.dumps({"files": rows, "bridge": str(BRIDGE), "family_checker": str(FAMILY)},
                     indent=2, ensure_ascii=False))
    return 0 if all(row.get("state", "present") == "present"
                    or row.get("state") == "written" for row in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
