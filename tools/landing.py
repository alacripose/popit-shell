"""Generate the family landing page from the machine's readings and the repository's pins.

The page's sentences are not written here. Two records supply every word:

* the Debian machine's axis surface (`/api/axis/system`, `/api/axis/civilians`,
  `/api/axis/stars`), which is the family's own reading of what it is and what it holds;
* this repository's `tools/family_look.json`, `contour.json`, the refusal names in
  `tools/gate.py` and `requirements.txt`.

The readings are fetched over the network from WSL (`FAMILY_AXIS`, default
`http://127.0.0.1:8787`), saved with their digest in `docs/landing-copy.json`, and the page is
rendered from that copy. `--check` therefore needs no machine: it re-renders from the saved
copy and refuses a page that has drifted, a copy whose digest no longer matches, or a pin that
moved since the copy was taken.

Every sentence is checked by the family prose tools before it is written: `ui_prose.py` from
deadlock-model-forge and `prose.mjs` from brass-meridian.

    python tools/landing.py            # read the machine, write the copy and the page
    python tools/landing.py --check    # exit 1 when the page, the copy or the pin drifted
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PIN = ROOT / "tools" / "family_look.json"
CONTOUR = ROOT / "contour.json"
ENGINE = ROOT / "ui" / "contour.js"
GATE = ROOT / "tools" / "gate.py"
REQUIREMENTS = ROOT / "requirements.txt"
COPY = DOCS / "landing-copy.json"
SERVICE_WORKER = ROOT / "ui" / "sw.js"

MACHINE = os.environ.get("FAMILY_AXIS", "http://127.0.0.1:8787")
WSL_DISTRO = os.environ.get("FAMILY_AXIS_DISTRO", "Debian")
READINGS = ("/api/axis/system", "/api/axis/civilians", "/api/axis/stars")

PROSE_TOOLS = (
    Path(os.path.expanduser("~/Documents/deadlock-model-forge/tools/ui_prose.py")),
    Path("F:/Documents/portal-shell/tools/ui_prose.py"),
)
PROSE_MJS = Path("F:/Documents/brass-meridian/tools/prose.mjs")

MAX_WORDS = 18
MAX_CHARS = 92
# The machine fields the page prints, stored so the page renders without the machine.
READING_FIELDS = (
    "host", "version", "platform", "score", "band",
    "star_count", "axis_count", "first_star", "last_star",
)


# ----------------------------------------------------------------- the machine's readings
def _fetch(path: str) -> dict:
    """Read one axis route, from Windows when it resolves and through WSL when it does not."""
    url = f"{MACHINE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=6) as answer:  # noqa: S310 - loopback only
            return json.loads(answer.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass
    run = subprocess.run(
        ["wsl.exe", "-d", WSL_DISTRO, "-e", "curl", "-s", "-m", "6", f"http://127.0.0.1:8787{path}"],
        capture_output=True, text=True, check=False,
    )
    if run.returncode != 0 or not run.stdout.strip():
        raise SystemExit(f"landing-machine-absent: {path} did not answer at {MACHINE}")
    try:
        return json.loads(run.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"landing-machine-refused: {path} returned no json, {error}") from error


def machine() -> dict:
    """The machine's own account of itself, with a digest over the exact bytes read."""
    readings = {path: _fetch(path) for path in READINGS}
    raw = json.dumps(readings, sort_keys=True, ensure_ascii=False).encode("utf-8")
    system = readings["/api/axis/system"]
    civilians = readings["/api/axis/civilians"]
    stars = readings["/api/axis/stars"].get("contract", {})
    entries = stars.get("stars", [])
    return {
        "version": str(system.get("version", "CUA")),
        "host": str(system.get("host", "Debian")),
        "platform": str(system.get("platform", "linux")),
        "score": civilians.get("score", 0),
        "band": str(civilians.get("band", "unknown")),
        "star_count": int(stars.get("starCount", len(entries))),
        "axis_count": int(stars.get("axisCount", 0)),
        "first_star": str(entries[0].get("id", "")) if entries else "",
        "last_star": str(entries[-1].get("id", "")) if entries else "",
        "digest": hashlib.sha256(raw).hexdigest(),
        "readings": readings,
    }


# ----------------------------------------------------------------- the repository's pins
def pins() -> dict:
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    profile = json.loads(CONTOUR.read_text(encoding="utf-8"))
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    refusals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if name == "check" and isinstance(node.args[0], ast.Constant):
            refusals.append(str(node.args[0].value))
    run = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    remote = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()
    slug = remote.split("github.com")[-1].lstrip(":/").removesuffix(".git") if "github.com" in remote else ""
    corner = pin["corner_px"]
    constants = pin["constants"]
    return {
        "corner_w": f"{corner['width']:.2f}",
        "corner_h": f"{corner['height']:.2f}",
        "clip_pad": f"{constants['clip_pad']}",
        "frame_pad": f"{constants['frame_pad']}",
        "stroke": f"{constants['stroke_width']}",
        "bar": f"{constants['bar_height']}",
        "surfaces": len(pin["surfaces"]),
        "refusal_count": len(refusals),
        "refusals": refusals,
        "check_count": len(dict.fromkeys(refusals)),
        "segments": len(profile["segments"]),
        "requirements": run,
        "repo": f"https://github.com/{slug}" if slug else "",
        "release": f"https://github.com/{slug}/releases" if slug else "",
        "pin": pin,
    }


# ----------------------------------------------------------------- the page's sentences
def compose(m: dict, p: dict) -> dict[str, str]:
    first, last = (p["refusals"][0], p["refusals"][-1]) if p["refusals"] else ("", "")
    return {
        "title": f"{p['repo'].rsplit('/', 1)[-1]} on {m['host'] or 'unknown host'}",
        "eyebrow": f"{m['host'] or 'unknown host'} reading",
        "headline": f"{m['version']} holds {m['star_count']} stars over {m['axis_count']} axes",
        "lede": f"This machine scores the repository {m['score']} in band {m['band']}",
        "caption": f"The pin is {p['corner_w']} by {p['corner_h']} px on {p['surfaces']} surfaces",
        "cta_release": "Download the release",
        "cta_source": "Source and gate",
        "card1_title": "The machine",
        "card1_body": f"{m['host'] or 'unknown host'} runs {m['version']} on {m['platform']}",
        "card2_title": "The stars",
        "card2_body": f"{m['star_count']} stars run from {m['first_star'] or 'none'} to {m['last_star'] or 'none'}",
        "card3_title": "The gate",
        "card3_body": f"The gate runs {p['check_count']} checks, first is {first}",
        "numbers_title": "Pinned numbers",
        "numbers_note": f"The reading is {m['digest'][:12]} over three routes",
        "run_title": "Run it",
        "run_note": "Windows 10 or 11 with Python 3.13",
        "footer": f"{m['host'] or 'unknown host'} wrote this page from its own readings",
    }


def numbers(m: dict, p: dict) -> list[tuple[str, str]]:
    constants = p["pin"]["constants"]
    return [
        ("Corner, every surface", f"{p['corner_w']} by {p['corner_h']} px"),
        ("Clip pad", f"{constants['clip_pad']} px"),
        ("Frame pad", f"{constants['frame_pad']} px"),
        ("Stroke", f"{constants['stroke_width']} px"),
        ("Strip height", f"{constants['bar_height']} px"),
        ("Profile", f"{p['segments']} cubics"),
        ("Surfaces", f"{p['surfaces']} draw the one corner"),
        ("Machine", f"{m['host']} {m['version']}"),
        ("Gate checks", f"{p['check_count']} named"),
        ("Stars and axes", f"{m['star_count']} over {m['axis_count']}"),
        ("Machine score", f"{m['score']} in band {m['band']}"),
    ]


# ----------------------------------------------------------------- family prose tools
def prose_seal(texts: list[str]) -> str:
    """The digest of the copy the family tools approved, so `--check` needs no tool on disk."""
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()


def prose_check(texts: list[str]) -> None:
    for text in texts:
        words = len(text.split())
        if words > MAX_WORDS or len(text) > MAX_CHARS:
            raise SystemExit(f"landing-prose-budget: {words} words, {len(text)} chars: {text[:60]}")
    tool = next((path for path in PROSE_TOOLS if path.exists()), None)
    if tool is None:
        raise SystemExit("landing-prose-missing: the family prose checker is not on disk")
    spec = importlib.util.spec_from_file_location("family_ui_prose", tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as folder:
        planted = Path(folder) / "landing.py"
        planted.write_text("".join(f"hint(layout, {text!r})\n" for text in texts), encoding="utf-8")
        # The rule set is the scanner. The coverage floor belongs to the addon's own file count.
        hits, visible = module.scan([planted])
    if hits or visible == 0:
        detail = "; ".join(f"{hit['rule']} {hit['text'][:50]}" for hit in hits[:4])
        raise SystemExit(f"landing-prose-refused: {detail or 'no string was read'}")
    if PROSE_MJS.exists() and shutil.which("node"):
        markdown = "\n\n".join(texts)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "copy.md"
            path.write_text(markdown, encoding="utf-8")
            script = (
                f'import {{ reviewProse }} from {json.dumps(PROSE_MJS.as_uri())};'
                'import { readFileSync } from "node:fs";'
                f'const issues = reviewProse(readFileSync({json.dumps(str(path).replace(chr(92), "/"))}, "utf8"));'
                'if (issues.length) { console.error(JSON.stringify(issues)); process.exit(1); }'
            )
            run = subprocess.run(["node", "--input-type=module", "-e", script],
                                 capture_output=True, text=True, check=False)
        if run.returncode != 0:
            raise SystemExit(f"landing-prose-refused: prose.mjs said {run.stderr.strip()[:160]}")


# ----------------------------------------------------------------- the page
def digest(path: Path) -> str:
    # The name is the hash of the bytes the server sends, not of this checkout's line endings, so
    # two checkouts of the same content publish the same asset name.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:10]


def versions() -> dict[str, str]:
    """The published assets are named by their own bytes."""
    return {"js": digest(ENGINE), "json": digest(CONTOUR)}


def sw(build: str) -> str:
    return SERVICE_WORKER.read_text(encoding="utf-8").replace("__BUILD__", build)


def build_id(copy: dict[str, str], p: dict, m: dict) -> str:
    """One build name for the page and its worker, from the page's own bytes.

    The page is rendered with a placeholder first, so the name is a function of the content rather
    than of the clock; a build that changes nothing keeps its name, and a build that changes
    anything gets a new one.
    """
    v = versions()
    seed = page(copy, p, m, v, "0000000000") + v["js"] + v["json"]
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]


def page(copy: dict[str, str], p: dict, m: dict, v: dict[str, str] | None = None,
         build: str = "") -> str:
    v = v or versions()
    build = build or "0000000000"
    rows = "\n".join(f"        <tr><td>{name}</td><td>{value}</td></tr>" for name, value in numbers(m, p))
    cards = "\n".join(
        f"""      <article class="card surface" data-contour="card">
        <h3>{copy[f'card{index}_title']}</h3>
        <p>{copy[f'card{index}_body']}</p>
      </article>"""
        for index in (1, 2, 3)
    )
    run = "\n".join(p["requirements"] + ["python shell.py"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{copy['title']}</title>
<meta name="description" content="{copy['lede']}">
<meta name="openlock-build" content="{build}">
<style>
  :root {{
    --paper: #d9c9a6;
    --brass: #b08d57;
    --brass-lit: #e2c188;
    --ink: #0b0906;
    --panel: #14100b;
    --line: rgba(176, 141, 87, 0.32);
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; background: var(--ink); }}
  body {{
    background: radial-gradient(1200px 620px at 18% -10%, #1d1710 0%, var(--ink) 62%);
    color: var(--paper);
    font: 16px/1.6 Georgia, "Times New Roman", serif;
  }}
  main {{ max-width: 1060px; margin: 0 auto; padding: 60px 26px 90px; }}

  /* A surface paints through the contour clip and strokes its frame. No radius anywhere. */
  .surface {{ position: relative; background: none; }}
  .surface::before {{
    content: "";
    position: absolute;
    inset: 0;
    z-index: 0;
    clip-path: var(--clip, none);
    background:
      linear-gradient(180deg, rgba(176, 141, 87, 0.10), rgba(176, 141, 87, 0.02) 70%, transparent),
      var(--panel);
  }}
  .surface > * {{ position: relative; z-index: 1; }}
  .contour-frame {{ position: absolute; inset: 0; z-index: 2; width: 100%; height: 100%; pointer-events: none; overflow: visible; }}
  .contour-frame path {{ stroke: rgba(176, 141, 87, 0.55); fill: none; }}
  .surface:hover .contour-frame path {{ stroke: var(--brass-lit); }}

  .eyebrow, h2 {{
    margin: 0 0 12px;
    font: 600 12px/1.4 "Segoe UI", system-ui, sans-serif;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--brass);
  }}
  h1 {{ margin: 0 0 16px; font-size: clamp(28px, 4.2vw, 48px); line-height: 1.1; font-weight: 400; }}
  .lede {{ margin: 0 0 30px; max-width: 60ch; font-size: 18px; color: #cbb894; }}

  .hero {{ padding: 10px; }}
  .hero img {{ display: block; width: 100%; height: auto; }}
  .caption {{ margin: 10px 2px 0; font: 12px/1.5 "Segoe UI", system-ui, sans-serif; color: #9c8a6b; }}

  .grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
  section {{ margin-top: 52px; }}
  .card {{ padding: 20px 22px 22px; }}
  .card h3 {{ margin: 0 0 8px; font-size: 18px; font-weight: 400; color: var(--brass-lit); }}
  .card p {{ margin: 0; font-size: 15px; color: #cbb894; }}

  .panel {{ padding: 18px 22px; }}
  table {{ width: 100%; border-collapse: collapse; font: 14px/1.5 Consolas, ui-monospace, monospace; }}
  td {{ padding: 9px 4px; border-bottom: 1px solid rgba(176, 141, 87, 0.16); color: #cbb894; }}
  td:first-child {{ color: var(--paper); }}
  td:last-child {{ text-align: right; color: var(--brass-lit); }}

  .run {{ padding: 18px 22px; }}
  .run pre {{ margin: 0; font: 14px/1.8 Consolas, ui-monospace, monospace; color: #d6c3a0; overflow-x: auto; }}

  .links {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }}
  .links a {{ display: inline-block; padding: 12px 22px; text-decoration: none; }}
  .links a span {{ font: 600 14px/1 "Segoe UI", system-ui, sans-serif; color: var(--brass-lit); }}
  .links a:hover span {{ color: #f2d9a8; }}

  footer {{ margin-top: 60px; font: 12px/1.6 "Segoe UI", system-ui, sans-serif; color: #857257; }}
  a {{ color: var(--brass-lit); }}
</style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">{copy['eyebrow']}</p>
    <h1>{copy['headline']}</h1>
    <p class="lede">{copy['lede']}</p>
    <figure class="surface hero" data-contour="card">
      <img src="hero.png" alt="{copy['caption']}">
      <figcaption class="caption">{copy['caption']}</figcaption>
    </figure>
    <div class="links">
      <a class="surface" data-contour="card" href="{p['release']}"><span>{copy['cta_release']}</span></a>
      <a class="surface" data-contour="card" href="{p['repo']}"><span>{copy['cta_source']}</span></a>
    </div>
  </header>

  <section>
    <h2>The record</h2>
    <div class="grid">
{cards}
    </div>
  </section>

  <section>
    <h2>{copy['numbers_title']}</h2>
    <div class="surface panel" data-contour="card">
      <table>
{rows}
      </table>
      <p class="caption">{copy['numbers_note']}</p>
    </div>
  </section>

  <section>
    <h2>{copy['run_title']}</h2>
    <div class="surface run" data-contour="card">
      <pre>{run}</pre>
    </div>
    <p class="caption">{copy['run_note']}</p>
  </section>

  <footer>{copy['footer']} <a href="family-look.md">The look in prose</a></footer>
</main>
<script type="module">
  // The assets are named by their own bytes, so a page and the module it asks for cannot be from
  // two different builds: a fresh page never pairs with a module an old visit left in the cache.
  import {{ loadContour, fillContours }} from "./contour.js?v={v['js']}";
  await loadContour("./contour.json?v={v['json']}");
  fillContours(document);
  // Every surface is measured again when its box changes, exactly as the shell does it.
  const again = () => fillContours(document);
  new ResizeObserver(again).observe(document.body);
  window.addEventListener("resize", again);
  // Pages serves every file with a ten minute cache, so a returning visitor can be handed the page
  // it already had. The worker takes over the document and the module and always asks the server
  // first, which is what makes this page converge on the deployment rather than on a memory of it.
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {{
    navigator.serviceWorker.register("./sw.js", {{ updateViaCache: "none", scope: "./" }}).catch(() => {{}});
  }}
</script>
</body>
</html>
"""


def publish(copy: dict[str, str], p: dict, m: dict) -> str:
    """Write the published build from the copy and the pins, and nothing else.

    The published files are a function of the sources: the page, the module, the drawing and the
    worker are all rendered here, so `docs/` can be rebuilt on any machine without the readings.
    """
    DOCS.mkdir(parents=True, exist_ok=True)
    v = versions()
    build = build_id(copy, p, m)
    (DOCS / "index.html").write_text(page(copy, p, m, v, build), encoding="utf-8")
    shutil.copyfile(ENGINE, DOCS / "contour.js")
    shutil.copyfile(CONTOUR, DOCS / "contour.json")
    (DOCS / "sw.js").write_text(sw(build), encoding="utf-8")
    return build


def rebuild() -> None:
    """Rebuild the published build from the stored copy; no machine is needed."""
    stored = json.loads(COPY.read_text(encoding="utf-8"))
    reading = stored.get("reading", {})
    m = {key: reading.get(key, "") for key in READING_FIELDS}
    m["digest"] = stored.get("machine", "")
    build = publish(stored["copy"], pins(), m)
    print(f"rebuilt docs/ from the stored copy, build {build}")


def write() -> None:
    m = machine()
    p = pins()
    copy = compose(m, p)
    prose_check(list(copy.values()))
    stored = {
        "schema": "popit-shell.landing-copy/1",
        "machine": m["digest"],
        "prose": prose_seal(list(copy.values())),
        "reading": {key: m[key] for key in READING_FIELDS},
        "copy": copy,
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    COPY.write_text(json.dumps(stored, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    build = publish(copy, p, m)
    print(f"wrote docs/ from {m['host']} {m['version']} reading {m['digest'][:12]}, build {build}")


def check() -> int:
    problems = []
    if not COPY.exists():
        problems.append("docs/landing-copy.json is missing, run python tools/landing.py on the machine")
        stored, copy = {}, {}
    else:
        stored = json.loads(COPY.read_text(encoding="utf-8"))
        copy = stored.get("copy", {})
    p = pins()
    reading = stored.get("reading", {}) if stored else {}
    m = {key: reading.get(key, "") for key in READING_FIELDS}
    m["digest"] = stored.get("machine", "") if stored else ""
    if copy:
        # The page is the copy rendered against the pins as they stand. A moved pin is drift.
        if not stored.get("machine"):
            problems.append("landing-copy-unsealed: the stored reading digest is missing")
        if copy != compose(m, p):
            problems.append("landing-copy-stale: the copy no longer matches the reading or the pins")
        seal = stored.get("prose", "")
        if not seal:
            problems.append("landing-prose-unsealed: the copy was never prose checked")
        elif seal != prose_seal(list(copy.values())):
            problems.append("landing-prose-changed: the copy is not the text that was checked")
        target = (DOCS / "index.html").read_text(encoding="utf-8") if (DOCS / "index.html").exists() else ""
        if not target:
            problems.append("docs/index.html is missing")
        elif target != page(copy, p, m, versions(), build_id(copy, p, m)):
            problems.append("docs/index.html is stale against its copy, run python tools/landing.py")
        if "border-radius" in target:
            problems.append("landing-rounded-rectangle: a rounded rectangle is not the contour")
        if 'data-contour="card"' not in target or "contour.js" not in target:
            problems.append("landing-not-contoured: the page does not draw the contour")
        for name in ("contour.js", "contour.json"):
            if not (DOCS / name).exists():
                problems.append(f"docs/{name} is missing, run python tools/landing.py")
        # The published build is the source build, byte for byte: a copied module that drifted, an
        # unversioned asset name or a worker of another build is the stale page a visitor also gets.
        for source, published in ((ENGINE, DOCS / "contour.js"), (CONTOUR, DOCS / "contour.json")):
            if published.exists() and published.read_bytes() != source.read_bytes():
                problems.append(f"docs/{published.name} is not the source {source.name}")
        worker = DOCS / "sw.js"
        if not worker.exists():
            problems.append("docs/sw.js is missing, run python tools/landing.py")
        elif worker.read_text(encoding="utf-8") != sw(build_id(copy, p, m)):
            problems.append("docs/sw.js is not this build's worker")
        v = versions()
        if f'from "./contour.js?v={v["js"]}"' not in target:
            problems.append("landing-assets-unversioned: the module URL is not the module's own bytes")
        if f'loadContour("./contour.json?v={v["json"]}")' not in target:
            problems.append("landing-drawing-unversioned: the drawing URL is not the drawing's own bytes")
    for problem in problems:
        print(f"[FAIL] {problem}")
    if problems:
        return 1
    print("landing page is the machine's reading of the pinned look")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--check" in args:
        return check()
    if "--rebuild" in args:
        rebuild()
        return 0
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
