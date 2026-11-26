"""The tone probe: what digits are actually in a line's dial tone, and whose number are they.

`dialin.call_tone` writes one WAV per roster row and call direction. This decodes those files
back to digits with a Goertzel read of the DTMF pairs, then compares them with the number the
roster holds for that row and with the number the call itself carried.

The owner's question is the reason it exists: the desk plays a set of digits at the start of a
line, and the reading must say whether those digits are the number that called in or a
sequence the roster happened to hold.

    python tools/tone_probe.py                    # every tone in runlogs/toast/tones
    python tools/tone_probe.py --row alacrity     # one row
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import pathlib
import struct
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
TONES = ROOT / "runlogs" / "toast" / "tones"
TONE_REV = 3          # kept beside the generator so the page can say which revision it read
STATE = ROOT / "runlogs" / "toast" / "civilians.json"
RECEIPT = ROOT / "artifacts" / "receipts" / "tone-probe.json"

LOW = (697, 770, 852, 941)
HIGH = (1209, 1336, 1477, 1633)
DIGITS = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("*", "0", "#"))
FRAME = 0.01          # a DTMF tone is 40ms or longer; 10ms frames find its edges
# A dial tone leaks a little energy into the 697/1209 pair; a real DTMF tone is an order of
# magnitude stronger and lasts 120ms. Both bounds together keep the dial tone out of the read.
FLOOR = 0.0016        # a frame quieter than this is silence, not a digit
STRENGTH = 0.01       # a digit's weaker tone is at least this strong
MIN_FRAMES = 6        # 60ms: the shortest real DTMF run in a generated tone is 12 frames


def read_wav(path: pathlib.Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise SystemExit(f"{path.name}: expected 16-bit audio, found {width * 8}-bit")
    count = len(frames) // 2
    samples = [value / 32768.0 for value in struct.unpack("<" + "h" * count, frames)]
    return rate, samples


def energy(samples: list[float], rate: int, hz: float) -> float:
    """Goertzel: the energy at one frequency inside a frame."""
    omega = 2.0 * math.pi * hz / rate
    coeff = 2.0 * math.cos(omega)
    first = second = 0.0
    for value in samples:
        first, second = value + coeff * first - second, first
    return math.sqrt(max(0.0, first * first + second * second - coeff * first * second)) / max(1, len(samples))


def decode(rate: int, samples: list[float]) -> list[dict]:
    """Every frame's best low/high pair, grouped into runs, as the digits they are."""
    size = max(1, int(rate * FRAME))
    runs: list[dict] = []
    for start in range(0, len(samples) - size + 1, size):
        frame = samples[start:start + size]
        if max(abs(value) for value in frame) < FLOOR:
            runs.append({"digit": "", "frames": 1, "energy": 0.0})
            continue
        low = sorted(((energy(frame, rate, hz), hz) for hz in LOW), reverse=True)[0]
        high = sorted(((energy(frame, rate, hz), hz) for hz in HIGH), reverse=True)[0]
        # A real DTMF pair has both frequencies present; a dial tone (350/440) has neither.
        if low[1] in LOW and high[1] in HIGH and min(low[0], high[0]) > STRENGTH:
            digit = DIGITS[LOW.index(low[1])][HIGH.index(high[1])]
        else:
            digit = ""
        runs.append({"digit": digit, "frames": 1, "energy": min(low[0], high[0])})
    grouped: list[dict] = []
    for run in runs:
        if grouped and grouped[-1]["digit"] == run["digit"]:
            grouped[-1]["frames"] += 1
            grouped[-1]["energy"] = max(grouped[-1]["energy"], run["energy"])
        else:
            grouped.append(dict(run))
    # One strong run is one digit. Two 5s in a row are two runs separated by the gap between
    # them, so they must not be merged again here: a repeated digit is not the same digit.
    return [dict(run) for run in grouped if run["digit"] and run["frames"] >= MIN_FRAMES]


def registry() -> dict[str, dict]:
    if not STATE.is_file():
        return {}
    rows = json.loads(STATE.read_text(encoding="utf-8")).get("civilians") or []
    return {row["id"]: row for row in rows if isinstance(row, dict) and row.get("id")}


def digits_of(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch.isdigit())


PAGE_ID = "tone-probe"
POPIT_RECEIPT = ROOT / "artifacts" / "receipts" / "tone-probe-popit.json"


def build(row_filter: str = "") -> dict:
    """Every tone file read back to digits, with the roster's number beside it."""
    rows = registry()
    files = sorted(TONES.glob("*-outgoing.wav"))
    if row_filter:
        files = [path for path in files if path.name.startswith(row_filter + "-")]
    out = []
    for path in files:
        stem = path.name[: -len("-outgoing.wav")]
        # A tone written for a carried number is named `<row>-<digits>`: the digits in the
        # name are what it dials, and the roster row is only there for the lane's own line.
        carried = ""
        row_id = stem
        head, _, tail = stem.rpartition("-")
        if head and tail.isdigit():
            row_id, carried = head, tail
        row = rows.get(row_id) or {}
        rate, samples = read_wav(path)
        heard = decode(rate, samples)
        played = "".join(item["digit"] for item in heard)
        want = carried or digits_of(row.get("number"))[-7:]
        out.append({"row": row_id, "name": row.get("name") or "",
                    "number": carried or row.get("number") or "",
                    "source": "call" if carried else "roster", "played": played,
                    "roster_digits": want, "frames": [item["frames"] for item in heard],
                    "matches_roster": bool(played) and played == want})
    return {"schema": "popit.tone-probe/1", "tone_rev": TONE_REV,
            "rows": out, "mismatched": [row["row"] for row in out if not row["matches_roster"]]}


def page(report: dict) -> str:
    cells = "".join(
        "<tr><td>{row}</td><td>{name}</td><td class=mono>{number}</td>"
        "<td class=mono>{played}</td><td class=mono>{want}</td>"
        "<td class={cls}>{state}</td></tr>".format(
            row=row["row"], name=row["name"], number=row["number"], played=row["played"],
            want=row["roster_digits"],
            cls="ok" if row["matches_roster"] else "bad",
            state="matches roster" if row["matches_roster"] else "differs")
        for row in report["rows"])
    return """<!doctype html><meta charset=utf-8>
<title>tone probe</title>
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
<h1>Tone probe</h1>
<p class=meta>Every outgoing dial tone, decoded back to digits · tone revision {rev}</p>
<table id="tone-table"><thead><tr><th>row</th><th>name</th><th>number</th><th>dialled</th>
<th>roster</th><th>state</th></tr></thead><tbody>{cells}</tbody></table>
<p class=sum id="tone-summary">{total} tone file(s) · {bad} differing</p>
</div>
""".format(pid=PAGE_ID, rev=report["tone_rev"], cells=cells,
           total=len(report["rows"]), bad=len(report["mismatched"]))


def serve(port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401 - quiet server
            return

        def do_GET(self):  # noqa: N802 - http.server's name
            if self.path.startswith("/report.json"):
                body = json.dumps(build(), indent=2).encode("utf-8")
                kind = "application/json"
            elif self.path in ("/", "/index.html"):
                body = page(build()).encode("utf-8")
                kind = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    print(f"tone probe on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def probe(port: int) -> int:
    """Read the page and its report over loopback; a printed pass is not a reading."""
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
                body = json.dumps(build(), indent=2).encode("utf-8")
                kind = "application/json"
            else:
                body = page(build()).encode("utf-8")
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
    check("surface-serves", bool(html), f"{len(html)} byte(s) of page") if html else \
        check("surface-serves", False, "surface-absent: no page answered")
    check("surface-is-marked", f'data-popit="{PAGE_ID}"' in html, "data-popit on the page")
    check("surface-has-the-table", 'id="tone-table"' in html, "#tone-table present")
    check("report-schema", report.get("schema") == "popit.tone-probe/1",
          str(report.get("schema")))
    check("report-has-a-row-per-tone", len(report.get("rows") or []) > 0,
          f"{len(report.get('rows') or [])} row(s)")
    check("every-tone-dials-the-number-it-names", not report.get("mismatched"),
          ", ".join(report.get("mismatched") or []) or "no differing row")
    receipt = {"schema": "popit.tone-probe/popit", "at": datetime.datetime.now(
        datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "port": port, "checks": checks, "failed": [row for row in checks if not row["ok"]]}
    POPIT_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    POPIT_RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"{len(checks) - len(receipt['failed'])} passed, {len(receipt['failed'])} failed -> {POPIT_RECEIPT}")
    return 0 if not receipt["failed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--row", default="")
    parser.add_argument("--serve", type=int, default=0)
    parser.add_argument("--probe", type=int, default=0)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return 0
    if args.probe:
        return probe(args.probe)
    rows = registry()
    files = sorted(TONES.glob("*-outgoing.wav"))
    if args.row:
        files = [path for path in files if path.name.startswith(args.row + "-")]
    out = []
    for path in files:
        row_id = path.name[: -len("-outgoing.wav")]
        row = rows.get(row_id) or {}
        rate, samples = read_wav(path)
        heard = decode(rate, samples)
        played = "".join(item["digit"] for item in heard)
        want = digits_of(row.get("number"))[-7:]
        out.append({
            "row": row_id, "name": row.get("name") or "", "number": row.get("number") or "",
            "played": played, "roster_digits": want,
            "matches_roster": bool(played) and played == want,
            "registers": len(row.get("dialins") or []),
        })
        print(f"{row_id:22} played={played or '(none)':8} roster={want or '(none)':8} "
              f"{'same' if played and played == want else 'DIFFERENT'}")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps({"schema": "popit.tone-probe/1", "rows": out}, indent=2),
                       encoding="utf-8")
    print(f"{len(out)} tone file(s) -> {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
