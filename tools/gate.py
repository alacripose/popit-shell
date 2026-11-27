"""The contour gate: a drawn surface that is not the nine-slice is refused by name.

The contour is the framing and scale authority. Every surface this shell draws is the
measured profile cut into nine regions: the corner keeps the contour's own blend and the
four edges stay straight, so a bar cell and a launcher are cut the same way and a large
window cannot flower its corners out. A rounded rectangle, a bare rectangle, a stretched
contour or a shadow shape is not the contour and this gate refuses it instead of letting
it be drawn.

The clip padding is pinned here too. A one pixel frame drawn on the clip boundary is
shaved by the clip and an edge on a half pixel lights two pixels instead of one, which is
the uneven aliasing the owner sees; the gate refuses both.

Run: python tools/gate.py [--selftest]
Exit status is 0 only when every surface on disk is the nine-slice and the mapping holds.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import app_package  # noqa: E402 - the package contract this gate reads
CONTOUR = ROOT / "contour.json"
SHAPE_AUTHORITY = UI / "contour.js"

# The corner blend the measured path turns through, in the drawing's own units.
CORNER_BAND_X = 16.38
CORNER_BAND_Y = 23.48
CORNER_UNITS = 27.8
BAR_HEIGHT = 48
CORNER_PX = CORNER_UNITS * BAR_HEIGHT / 121.348

BAR_PIN = ROOT / "tools" / "bar_pin.json"

REFUSALS: list[str] = []
CHECKS: list[str] = []
HOST_BOUND: list[str] = []


def refuse(code: str, where: str, detail: str) -> None:
    REFUSALS.append(f"{code}: {where}: {detail}")


def check(code: str, label: str, ok: bool, where: str = "", detail: str = "") -> None:
    if ok:
        CHECKS.append(f"{code} {label}")
        return
    refuse(code, where or label, detail or label)


def host_bound(code: str, label: str, reason: str) -> None:
    """A check whose evidence never travels is refused where the evidence can be read.

    The family prose sweep writes a receipt naming every project's strings, home paths and
    addresses, so it is kept on the machine that scanned rather than committed. A host without
    the family checkout cannot read it; the gate names that instead of failing every runner
    over a file the repository is not allowed to carry.
    """
    HOST_BOUND.append(f"{code} {label}: {reason}")


LOOP = (
    (461.43, 634.0), (510.57, 634.0), (525.0, 612.17), (525.0, 537.83),
    (510.57, 516.0), (461.43, 516.0), (447.0, 537.83), (447.0, 612.17),
)

PROFILE_END = (
    (461.43, 634.0, 510.57, 634.0),
    (510.57, 634.0, 525.0, 612.17),
    (525.0, 612.17, 525.0, 537.83),
    (525.0, 537.83, 510.57, 516.0),
    (510.57, 516.0, 461.43, 516.0),
    (461.43, 516.0, 447.0, 537.83),
    (447.0, 537.83, 447.0, 612.17),
    (447.0, 612.17, 461.43, 634.0),
)


def nine_slice(width: float, height: float, shape: dict, pad: float = 1.5,
               corner_px: float | None = None) -> list[tuple[float, float]]:
    """The faithful slice: the drawing's box placed on the surface by one factor.

    Each loop point belongs to one corner and is placed by that corner's translation, so the
    crown reaches the frame, the rails keep the drawing's inset and every control point keeps
    its measured offset. Nothing is scaled per axis.
    """
    inset = min(pad, width / 6, height / 6)
    box_w = max(2.0, width - 2 * inset)
    box_h = max(2.0, height - 2 * inset)
    corner = CORNER_PX if corner_px is None else corner_px
    scale = min(corner / CORNER_BAND_Y, box_h / 3 / CORNER_BAND_Y, box_w / 3 / CORNER_BAND_X)
    right = inset + box_w
    bottom = inset + box_h
    corners = {
        "BL": (inset - shape["left"] * scale, bottom - shape["bottom"] * scale),
        "BR": (right - shape["right"] * scale, bottom - shape["bottom"] * scale),
        "TR": (right - shape["right"] * scale, inset - shape["top"] * scale),
        "TL": (inset - shape["left"] * scale, inset - shape["top"] * scale),
    }
    owner = ("BL", "BR", "BR", "TR", "TR", "TL", "TL", "BL")
    loop = []
    for index, point in enumerate(LOOP):
        tx, ty = corners[owner[index]]
        loop.append((point[0] * scale + tx, point[1] * scale + ty))
    points = [loop[0]]
    for i, seg in enumerate(shape["segments"]):
        sx, sy, ex, ey = PROFILE_END[i]
        dsx, dsy = loop[i]
        dex, dey = loop[(i + 1) % len(loop)]
        points.append((dsx + (seg[0] - sx) * scale, dsy + (seg[1] - sy) * scale))
        points.append((dex + (seg[2] - ex) * scale, dey + (seg[3] - ey) * scale))
        points.append((dex, dey))
    return points


def corner_span(points: list[tuple[float, float]], width: float) -> float:
    """How far the profile reaches in from the left edge before its edge turns flat."""
    tops = [y for x, y in points if x < width * 0.5]
    if not tops:
        return 0.0
    flat = min(tops)
    corner = [x for x, y in points if x < width * 0.5 and abs(y - flat) < 0.75]
    return min(corner) if corner else 0.0


def authority_numbers() -> dict[str, float]:
    """The numbers the view itself declares, read back so a pin compares the shipped file."""
    text = (UI / "contour.js").read_text(encoding="utf-8")

    def number(name: str) -> float:
        match = re.search(rf"const {name} = ([0-9.]+);", text)
        return float(match.group(1)) if match else -1.0

    return {
        "BAR_HEIGHT": number("BAR_HEIGHT"),
        "FRAME_PAD": number("FRAME_PAD"),
        "CLIP_PAD": number("CLIP_PAD"),
        "CORNER_UNITS": number("CORNER_UNITS"),
        "UNITS_H": number("UNITS_H"),
    }


FAMILY_LOOK = ROOT / "tools" / "family_look.json"


def family_look_pin() -> None:
    """The pinned family look is what the surfaces draw, not a copy of an older drawing.

    The pin is the family example: a corner of 7.67 by 11.00 px on every surface, one
    clip pad, one frame pad. A pin that drifts from ui/contour.js is refused by name.
    """
    try:
        pin = json.loads(FAMILY_LOOK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        check("family-look-pinned", "the family look is pinned", False, "tools/family_look.json", str(error))
        return
    numbers = authority_numbers()
    corner = numbers["CORNER_UNITS"] * numbers["BAR_HEIGHT"] / numbers["UNITS_H"]
    constants = pin["constants"]
    pinned_corner = float(pin["corner_px"]["height"])
    pinned_width = float(pin["corner_px"]["width"])
    band_x = 16.38
    band_y = 23.48
    drawn_width = band_x * corner / band_y
    surfaces_same = all(
        [round(surface["corner_px"][0], 2), round(surface["corner_px"][1], 2)
         ] == [round(pinned_width, 2), round(pinned_corner, 2)]
        for surface in pin["surfaces"]
    )
    check(
        "family-look-pinned",
        "the family look pin matches what the surfaces draw",
        abs(corner - pinned_corner) < 0.02
        and abs(drawn_width - pinned_width) < 0.02
        and abs(constants["corner_units"] - numbers["CORNER_UNITS"]) < 0.001
        and abs(constants["bar_height"] - numbers["BAR_HEIGHT"]) < 0.001
        and abs(constants["frame_pad"] - numbers["FRAME_PAD"]) < 0.001
        and abs(constants["clip_pad"] - numbers["CLIP_PAD"]) < 0.001
        and surfaces_same
        and len(pin["surfaces"]) >= 4,
        "tools/family_look.json",
        "the pinned family look is no longer the drawn one",
    )


def landing_pin() -> None:
    """The landing page is generated from these records, so a hand edit is refused.

    `tools/landing.py` writes `docs/index.html` from the pin, the gate's own refusal names and
    `contour.json`, and refuses a rounded rectangle. A page that no longer matches the
    generator is stale, and a stale page is the same drift as a stale pin.
    """
    import subprocess

    run = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "landing.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    detail = (run.stdout + run.stderr).strip().replace("\n", " | ")[:220]
    check(
        "landing-generated",
        "the landing page is generated from the pinned look",
        run.returncode == 0,
        "docs/index.html",
        detail or "the landing generator refused the page",
    )


def bar_pin() -> dict:
    """The taskbar's outline, pinned: the numbers and the cells the strip is drawn with."""
    numbers = authority_numbers()
    shape = json.loads(CONTOUR.read_text(encoding="utf-8"))
    corner = numbers["CORNER_UNITS"] * numbers["BAR_HEIGHT"] / numbers["UNITS_H"]
    cells = {}
    for width, height in ((120, 36), (190, 40), (265, 40)):
        points = nine_slice(width, height, shape, numbers["FRAME_PAD"], corner)
        cells[f"{width}x{height}"] = [f"{x:.2f},{y:.2f}" for x, y in points]
    return {
        "BAR_HEIGHT": numbers["BAR_HEIGHT"],
        "FRAME_PAD": numbers["FRAME_PAD"],
        "CLIP_PAD": numbers["CLIP_PAD"],
        "CORNER_PX": round(corner, 4),
        "cells": cells,
    }


def taskbar_pin(pin: bool) -> None:
    """The accepted taskbar is pinned. A change to its outline is refused by name."""
    current = bar_pin()
    if pin:
        BAR_PIN.write_text(json.dumps(current, indent=2) + chr(10), encoding="utf-8")
        check("taskbar-pinned", "the taskbar's outline is recorded", True, "tools/bar_pin.json",
              "pinned the strip as it is")
        return
    if not BAR_PIN.exists():
        refuse("taskbar-not-pinned", "tools/bar_pin.json", "the taskbar has no recorded outline")
        return
    recorded = json.loads(BAR_PIN.read_text(encoding="utf-8"))
    changed = [key for key in recorded if recorded[key] != current.get(key)]
    check(
        "taskbar-pinned",
        "the taskbar's outline is the one the owner accepted",
        not changed,
        "tools/bar_pin.json",
        f"changed: {', '.join(changed)}" if changed else "unchanged",
    )


def read_sources() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(UI.glob("*"))
        if path.suffix in {".css", ".js", ".html"}
    }


def probe_isolation() -> None:
    """A probe reads a second view: the desk the owner works in is never the measurement.

    Every acting probe — a frame choice, a refusal, a home press — ran inside the delivered
    window, so measuring repainted and navigated the desk the owner was using. The pump now
    routes probes and audit routes to a hidden view loaded from the same pinned origin, and the
    window reports its own paint for checks to read instead of being asked.
    """
    source = (ROOT / "toast.py").read_text(encoding="utf-8")
    page = (ROOT / "ui" / "toast.js").read_text(encoding="utf-8")
    check(
        "probes-run-off-the-owners-window",
        "an acting probe or a route act is refused against the desk, never run in it",
        'ACTING_PROBES = ("choose", "fallback", "goHome", "openApp", "windowClose")' in source
        and "probe-act-needs-measurement-window" in source
        and "route-needs-measurement-window" in source
        and "probe_view" not in source.split("def main")[1]
        and 'get("probe") === "1"' in page,
        "toast.py",
        "a probe still runs in the window the owner is using",
    )
    check(
        "window-reports-its-own-paint",
        "the desk pushes what it painted; a check reads that instead of probing it",
        "/api/toast/window/report" in source and "reportPaint()" in page
        and "if (MEASURE_VIEW) return;" in page,
        "ui/toast.js",
        "the window has no self-report, so a reading has to touch it",
    )
    # The owner's correction: the agent owns the decision to read its own channel. The desk
    # supplies the capability and the receipt, never a timer that calls a picture a reading.
    cua_now = (ROOT / "cua.py").read_text(encoding="utf-8")
    loop_body = source.split("def _loop")[1].split("def run_probe")[0] \
        if "def _loop" in source else ""
    read_body = cua_now.split("def _composer_reading")[1].split("def _trim")[0] \
        if "def _composer_reading" in cua_now else ""
    check(
        "composer-read-is-agent-initiated",
        "the composer is read when an agent calls the tool, not by a shell timer",
        bool(loop_body) and "run_probe()" not in loop_body
        and "freebuff.composer.read" in source
        and "freebuff.composer.read" in page
        and '"action": "composer_read"' in cua_now
        and "self.fleet.read_composer(FREEBUFF)" in source
        and '"state": "read"' in source
        and '"submitted": False' in source and '"keys": []' in source
        and bool(read_body) and "focus(" not in read_body
        and "type_text" not in read_body and "click(" not in read_body,
        "cua.py",
        "the composer is polled, or a read takes focus, sends keys or submits",
    )


def controls_pin() -> None:
    """The family's buttons are the baseline's: a sheet that authors its own is a refusal.

    The owner's rule is that no app may diverge from the settings window's material and motion
    choices in motion, function or padding. `app_base.CONTROLS` carries those as a pinned record
    and `/controls.css` serves them; this leg reads every app sheet and page for a button that
    still sets its own, so the pin is enforced by the gate rather than by memory.
    """
    import tools.controls_audit as controls_audit  # noqa: PLC0415 - a leg, loaded when read

    findings = []
    for path in sorted((ROOT / "ui").glob("*.css")):
        findings.extend(controls_audit.audit_sheet(path))
    findings.extend(controls_audit.audit_pages())
    for row in findings:
        refuse(row["code"], f"{row['file']}:{row['line']}",
               f"{row['selector']} {row['prop']}={row['value']}")
    check("controls-pinned", "every app button paints from the pinned baseline",
          not findings, "ui/*.css", "a local button padding, height or motion")


def toast_refusals() -> None:
    """The toast is a window, not a scrolling page: its frame and voice controls are pinned."""
    css = (UI / "toast.css").read_text(encoding="utf-8")
    html = (UI / "toast.html").read_text(encoding="utf-8")
    spinner_blocks = [
        block for selector, block in re.findall(r"(?s)([^{}]+)\{([^{}]*)\}", css)
        if "spinner" in selector.lower() and "border:" in block
    ]
    check(
        "toast-spinner-round",
        "spinning loaders keep round geometry instead of becoming squares",
        bool(spinner_blocks)
        and all("border-radius: 50%" in block for block in spinner_blocks),
        "ui/toast.css",
        f"{len(spinner_blocks)} spinner rule(s); all must carry border-radius: 50%",
    )
    frame = css.find(".toast > .contour-frame")
    flex = css.find(".toast > *")
    check(
        "toast-contour-frame",
        "the toast frame is outside the flex column",
        frame > flex >= 0 and "position: absolute" in css[frame:frame + 180],
        "ui/toast.css",
        "a relative contour SVG takes the body's height and pushes the readings off screen",
    )
    # Scrolling inside a list is not the window scrolling. The pinned window is the
    # html/body/.toast block; a >150px document list still needs its own scrollbar.
    window_blocks = re.findall(
        r"(?m)^\s*(?:html\s*,\s*body|\.toast)\s*\{[^}]*\}", css, re.S
    )
    window_scroll = any(
        re.search(r"overflow\s*:\s*(?:auto|scroll)", block) for block in window_blocks
    )
    check(
        "toast-no-scroll",
        "the toast clips instead of scrolling",
        not window_scroll,
        "ui/toast.css",
        "the window is a pinned surface, not a scroll container",
    )
    check(
        "toast-no-invented-controls",
        "the call desk carries only controls that act on the live call",
        not any(f'data-say="{name}"' in html for name in ("assistant", "cua-chat", "civilian"))
        and "civilians.html" not in html,
        "ui/toast.html",
        "the retired assistant, driver and civilian buttons were a miscount of how civilians work",
    )
    board_html = (ROOT / "ui" / "toast.html").read_text(encoding="utf-8")
    board_js = (ROOT / "ui" / "toast.js").read_text(encoding="utf-8")
    board_css = (ROOT / "ui" / "toast.css").read_text(encoding="utf-8")
    phone_js = (ROOT / "ui" / "phone.js").read_text(encoding="utf-8")
    client_pages = {
        "ui/toast.js": (ROOT / "ui" / "toast.js").read_text(encoding="utf-8"),
        "ui/phone.js": (ROOT / "ui" / "phone.js").read_text(encoding="utf-8"),
        "ui/settings.js": (ROOT / "ui" / "settings.js").read_text(encoding="utf-8"),
    }
    theme_sheet_path = ROOT / "ui" / "contour-theme.css"
    theme_sheet = theme_sheet_path.read_text(encoding="utf-8") if theme_sheet_path.exists() else ""
    phone_html = (ROOT / "ui" / "phone.html").read_text(encoding="utf-8")
    package_js = (ROOT / "ui" / "package.js").read_text(encoding="utf-8")
    check(
        "shared-surface-theme",
        "contour, material and motion are one family sheet both apps load",
        'href="/contour-theme.css"' in board_html
        and 'href="/contour-theme.css"' in phone_html
        and 'html[data-material="paper"]' in theme_sheet
        and 'html[data-material="paper"]' not in board_css
        and "motion-fold" in theme_sheet,
        "ui/contour-theme.css",
        "a surface with its own copy of the theme drifts from the family",
    )
    check(
        "settings-dpi-scales",
        "the published DPI and roles scale every app that reads the package",
        "style.zoom" in package_js and "theme.colors" in package_js
        and "document.documentElement.style.zoom" in board_js,
        "ui/package.js",
        "a DPI that only writes a variable leaves the desk at 100%",
    )
    check(
        "app-packages-use-the-family-signature",
        "every app surface reads the signed package and the settings theme",
        all('from "/package.js"' in source for source in client_pages.values())
        and 'id="package-identity"' in board_html
        and 'id="package-identity"' in (ROOT / "ui" / "phone.html").read_text(encoding="utf-8"),
        "ui/package.js",
        "an app that does not read its signed identity is not a family package",
    )
    try:
        app_probe = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "app_package_probe.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, cwd=str(ROOT),
        )
        app_ok = app_probe.returncode == 0
        app_detail = (app_probe.stdout or app_probe.stderr or "").strip().splitlines()[-1:] or [""]
    except (OSError, subprocess.TimeoutExpired) as error:
        app_ok = False
        app_detail = [str(error)[:160]]
    check(
        "app-package-probe",
        "signing, tamper, trust and unknown-name refusals are measured, not assumed",
        app_ok,
        "tools/app_package_probe.py",
        " ".join(app_detail),
    )
    audit_js = (ROOT / "ui" / "ui-audit.js").read_text(encoding="utf-8")
    package_source = (ROOT / "app_package.py").read_text(encoding="utf-8")
    toast_source = (ROOT / "toast.py").read_text(encoding="utf-8")
    check(
        "surface-audit-gates-packages",
        "a package is signed only after its surface measures clean",
        "app-ui-audit" in package_source
        and "/api/toast/ui-audit" in toast_source
        and "ui-overlap" in audit_js and "ui-x-overflow" in audit_js
        and 'path == "/"' in toast_source,
        "ui/ui-audit.js",
        "an unchecked surface is signed as if it could be drawn",
    )
    check(
        "springboard-is-the-phone-home",
        "the SpringBoard frame loads the existing phone home, and its apps hand back",
        'id="springboard"' in board_html
        # The home is the phone page the family already serves, requested as the window's own
        # delivery: a bare /phone.html is refused, so the frame names itself embedded.
        and 'data-src="/phone.html?embedded=1"' in board_html
        and 'id="app-grid"' not in board_html
        # The desk's surfaces and the settings engine moved into the shared module, so the
        # function is looked up where it now lives, not weakened.
        and "function setSurface" in board_js
        and 'data.source !== "popit-springboard"' in board_js
        and '/api/toast/apps' in phone_js
        and 'data-package-identity' in phone_js
        and 'label: "Commons"' not in phone_js
        and 'label: "Voice Call"' not in phone_js
        and 'label: "Agent lines"' not in phone_js
        and 'source: "popit-springboard"' in phone_js
        and '.toast[data-surface="springboard"]' in board_css,
        "ui/toast.html",
        "the home is the phone page the family already serves, not a second launcher",
    )
    try:
        table = json.loads((ROOT / "voice_profiles.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        refuse("toast-voice-gate", "voice_profiles.json", str(error))
        return
    civilian = table.get("profiles", {}).get("civilian", {})
    check(
        "toast-voice-gate",
        "a civilian address has a slower floor than a driver line",
        civilian.get("min_gap_ms", 0) >= 2000
        and len(table.get("profiles", {})) >= 6,
        "voice_profiles.json",
        f"civilian gap {civilian.get('min_gap_ms')} ms across {len(table.get('profiles', {}))} profiles",
    )
    baseline = table.get("baseline") or {}
    profiles = table.get("profiles") or {}
    default_engine = str((table.get("engine") or {}).get("name") or "")
    below_baseline = sorted(
        name for name, profile in profiles.items()
        if str(profile.get("engine") or default_engine) != "piper"
    )
    baseline_model = str(baseline.get("model") or "")
    unpinned = sorted(
        name for name, profile in profiles.items()
        if name != "buffy" and str(profile.get("model") or "") != baseline_model
    )
    model_path = ROOT / baseline_model if baseline_model else None
    model_present = bool(model_path and model_path.is_file())
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest() if model_present else ""
    pin = str(baseline.get("model_sha256") or "")
    # Voice weights are a local asset store (`models/` is ignored by git), so a clean checkout
    # carries the declaration and the pin, not 60 MB of ONNX. Where the weights are present the
    # digest must match the pin; where they are absent nothing can be synthesized, so the claim
    # is the declaration and the pin, and a present model store missing its baseline is refused.
    store = ROOT / "models"
    store_without_baseline = store.is_dir() and any(store.iterdir()) and not model_present
    declared = (
        baseline.get("profile") == "civilian"
        and baseline_model == "models/en_US-amy-medium.onnx"
        and len(pin) == 64
        and not below_baseline
        and not unpinned
        and (profiles.get("buffy") or {}).get("engine") == "piper"
    )
    verified = digest == pin if model_present else not store_without_baseline
    check(
        "toast-voice-baseline",
        "every synthesized voice uses the pinned Piper baseline or the AWA3D host voice",
        declared and verified,
        "voice_profiles.json",
        f"baseline {baseline.get('profile')} {baseline_model} "
        f"{('sha256 ' + digest[:12] + ' matches the pin') if model_present else ('weights are local (gitignored), pin ' + pin[:12] + ' declared')}; "
        f"below baseline {below_baseline or 'none'}; unpinned {unpinned or 'none'}",
    )


# The shell's own controls. Home is one of them: the owner asked for the springboard's home in
# the desk's bar, so the bar carries it and nothing of an app's own.
BAR_CONTROLS = ("home", "settings", "pin", "close")


def bar_control_refusals() -> None:
    """The bar belongs to the shell and is closed: no app package may add a control to it.

    The retired IDE lived as a button in the window's own furniture: a package's control in
    the shell's bar, which could only be removed by editing the desk and made the app look
    like part of the window. The bar's controls are pinned here, a chip or a hosted surface
    inside a bar or status region is refused, and the signed payload may not name controls.
    """
    html = (UI / "toast.html").read_text(encoding="utf-8")
    match = re.search(r'(?s)<header[^>]*data-region="bar"[^>]*>(.*?)</header>', html)
    if not match:
        refuse("bar-region-absent", "ui/toast.html", 'no header carries data-region="bar"')
        return
    bar = match.group(1)
    found = re.findall(r'<button[^>]*id="([^"]+)"', bar)
    extra = [name for name in found if name not in BAR_CONTROLS]
    missing = [name for name in BAR_CONTROLS if name not in found]
    check(
        "bar-controls-pinned",
        "the bar carries only the shell's own home, settings, pin and close controls",
        not extra and not missing,
        "ui/toast.html",
        f"extra {extra or 'none'}; missing {missing or 'none'}",
    )
    check(
        "bar-no-app-surface",
        "no chip, app button or hosted surface sits in the window's bar",
        "chip" not in bar and "iframe" not in bar and "ide" not in bar.lower(),
        "ui/toast.html",
        "an app package injected a control into the window's bar",
    )
    nav = re.search(r'(?s)<nav[^>]*data-region="status"[^>]*>(.*?)</nav>', html)
    if nav:
        strip = nav.group(1)
        check(
            "status-strip-does-not-launch-an-app",
            "the status strip names state; it does not launch an app",
            "iframe" not in strip
            and not re.search(r'<button[^>]*class="[^"]*\bchip\b', strip)
            and not re.search(r"<button[^>]*>\s*(?:IDE|BRIDGE|SPRINGBOARD)\s*</button>", strip, re.I),
            "ui/toast.html",
            "an app was given a control in the status strip",
        )


FRESHNESS_FAMILIES = ("landing", "ci", "audits", "failures", "ledgers", "refusals",
                      "packages", "tiles")


def freshness_register() -> None:
    """Landing, ci, audits, failures, ledgers, refusals, packages and tiles are measured.

    `tools/freshness.py probe` is the driver's work list: it reads the Popit page over
    loopback, writes `artifacts/receipts/freshness.json`, and names the act that clears
    every stale row. The gate reads that receipt, so a register that stops covering a
    family and a family that has gone stale are both refused here by name.
    """
    source_path = ROOT / "tools" / "freshness.py"
    source = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
    receipt = ROOT / "artifacts" / "receipts" / "freshness.json"
    body: dict = {}
    if receipt.is_file():
        try:
            body = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            body = {}
    covered = {entry.get("family") for entry in body.get("rows") or []}
    check(
        "freshness-register-covers-the-family",
        "landing, ci, audits, failures, ledgers, refusals, packages and tiles are rows",
        'data-popit="freshness"' in source
        and all(f'"{family}"' in source for family in FRESHNESS_FAMILIES)
        and body.get("schema") == "popit.freshness/1"
        and set(FRESHNESS_FAMILIES) <= covered,
        "tools/freshness.py",
        f"covered {sorted(covered) or 'nothing'} from the receipt",
    )
    stale = [entry.get("code") for entry in body.get("rows") or []
             if entry.get("state") == "stale"]
    check(
        "freshness-no-stale-rows",
        "a stale landing, audit, receipt, ledger, refusal, package or tile is a driver act",
        bool(body) and not stale,
        "artifacts/receipts/freshness.json",
        f"stale: {', '.join(stale) or 'none'}",
    )


def capacity_audit_checks() -> None:
    """Work cut for context, capacity or session length is refused by name.

    The owner's rule: an assistant that stops or shrinks a unit because the conversation is
    long, the context is nearly full or the work is assumed not to fit has to have that
    reason found and refused by the harness. `tools/capacity_audit.py` reads the decision
    records (authority rows, probes, docs), refuses every excuse it has not been told the
    owed unit for, and serves the reading on its own Popit page; this reads its receipt.
    """
    source_path = ROOT / "tools" / "capacity_audit.py"
    source = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
    receipt = ROOT / "artifacts" / "receipts" / "capacity.json"
    body: dict = {}
    if receipt.is_file():
        try:
            body = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            body = {}
    check(
        "capacity-audit-covers-the-records",
        "the capacity audit scans authority rows, probes and docs and serves its reading",
        'data-popit="capacity-audit"' in source
        and body.get("schema") == "popit.capacity/1"
        and set(body.get("scanned") or []) == {"authority", "probes", "docs"},
        "tools/capacity_audit.py",
        f"scanned {body.get('scanned') or 'nothing'} from {receipt.name}",
    )
    refused = [f"{row.get('file')}:{row.get('line')}" for row in body.get("rows") or []
               if row.get("state") == "refused"]
    check(
        "no-unacked-capacity-excuse",
        "a capacity excuse is refused unless the record names the unit that still owes it",
        bool(body) and not refused,
        "artifacts/receipts/capacity.json",
        f"refused: {', '.join(refused) or 'none'}",
    )


def settings_package_checks() -> None:
    """The settings document is a real package, signed, and only served to admitted windows."""
    import secrets
    import tempfile

    sys.path.insert(0, str(ROOT))
    import envelope
    import settings_package

    with tempfile.TemporaryDirectory(prefix="popit-settings-gate-") as temp:
        root = Path(temp) / "settings"
        trust = Path(temp) / "trust.json"
        package = settings_package.SettingsPackage(root, trust_path=trust)
        published = package.publish({
            "theme": "popit", "frame": "ios", "material": "glass", "motion": "pop",
            "motionPreference": "reduced", "dpi": 125, "palettes": [],
        })
        target = Path(published["package"])
        held = package.verify(target)
        expected = f"{settings_package.NAME}@{held['revision']}+{held['digest']}"
        check(
            "settings-package-identity",
            "the settings document is a canonical BLAKE3 package",
            held["identity"] == expected
            and (target / "identity.txt").read_text(encoding="utf-8").strip() == expected
            and held["digest"].startswith("blake3:") and len(held["digest"]) == 71,
            "settings_package.py", held["identity"],
        )
        record = json.loads((target / "signature.json").read_text(encoding="utf-8"))
        unsigned_record = {key: value for key, value in record.items() if key != "signature"}
        check(
            "settings-package-signed",
            "the publisher signs the identity and the payload digest",
            envelope.verify_payload(unsigned_record, record["signature"], record["public_key"])
            and held["payload_digest"].startswith("blake3:")
            and held["payload_digest"] != held["digest"],
            "settings_package.py", f"{record['public_key'][:24]}…",
        )
        payload_path = target / "payload.bin"
        original = payload_path.read_bytes()
        payload_path.write_bytes(original + b"\n")
        try:
            package.verify(target)
            tampered = ""
        except Exception as error:  # noqa: BLE001 - the refusal code is the assertion
            tampered = getattr(error, "code", "")
        finally:
            payload_path.write_bytes(original)
        check(
            "settings-package-tamper-refused",
            "a payload that no longer matches its signature is refused",
            tampered in ("settings-signature", "length"),
            "settings_package.py", tampered or "accepted a tampered payload",
        )
        keys = Path(temp) / "window"
        envelope.keygen(keys / "window.key", keys / "window.pem")
        window_key = (keys / "window.pem").read_text(encoding="utf-8").strip()
        package.trust(window_key, "Probe settings window")
        request = {
            "schema": settings_package.SUBSCRIPTION_SCHEMA, "window": "Probe settings window",
            "issued_at": envelope.iso(), "nonce": secrets.token_hex(16),
            "public_key": window_key,
        }
        request["signature"] = envelope.sign_payload(request, keys / "window.key")
        delivery = package.subscribe(request)["delivery"]
        check(
            "settings-subscription-admitted",
            "a trusted window receives the signed package",
            delivery["identity"] == held["identity"]
            and delivery["payload_digest"] == held["payload_digest"]
            and delivery["settings"]["frame"] == "ios",
            "settings_package.py", delivery["identity"],
        )
        replay = ""
        try:
            package.subscribe(request)
        except settings_package.Refused as error:
            replay = error.code
        check(
            "settings-subscription-replay-refused",
            "a nonce is spent once, so a captured request cannot be replayed",
            replay == "settings-replay", "settings_package.py", replay or "replayed",
        )
        stranger = Path(temp) / "stranger"
        envelope.keygen(stranger / "window.key", stranger / "window.pem")
        untrusted_key = (stranger / "window.pem").read_text(encoding="utf-8").strip()
        untrusted = {
            "schema": settings_package.SUBSCRIPTION_SCHEMA, "window": "Untrusted window",
            "issued_at": envelope.iso(), "nonce": secrets.token_hex(16),
            "public_key": untrusted_key,
        }
        untrusted["signature"] = envelope.sign_payload(untrusted, stranger / "window.key")
        refused = ""
        try:
            package.subscribe(untrusted)
        except settings_package.Refused as error:
            refused = error.code
        unsigned = {key: value for key, value in request.items() if key != "signature"}
        unsigned["nonce"] = secrets.token_hex(16)
        stripped = ""
        try:
            package.subscribe(unsigned)
        except settings_package.Refused as error:
            stripped = error.code
        check(
            "settings-subscription-refusals",
            "an untrusted signer and an unsigned request are refused by name",
            refused == "settings-untrusted" and stripped == "settings-signature",
            "settings_package.py",
            f"untrusted={refused or 'accepted'} unsigned={stripped or 'accepted'}",
        )
        # The device report is delivered live with the package, not signed into its bytes: the
        # signed payload names the document and a digest, and the readings a window receives are
        # the shell's current ones.
        device = ((published.get("delivery") or {}).get("device")
                  or published.get("device") or {})
        check(
            "settings-device-report",
            "the package owns an honestly measured device report",
            bool(device.get("reported_at"))
            and (device.get("screen") is None or len(device["screen"]) == 2)
            and device.get("platform") in (None, "Windows", "Linux", "Darwin"),
            "settings_package.py", f"{device.get('platform')} {device.get('screen')}",
        )
    html = (UI / "toast.html").read_text(encoding="utf-8")
    kept = ("contour-frames", "contour-types", "motion-types", "planet-stage",
            "palette-save", "dpi-range", "motion-full")
    check(
        "settings-panel-preserved",
        "the settings app keeps its frames, materials, motion, palettes and DPI",
        all(f'id="{name}"' in html for name in kept),
        "ui/toast.html",
        "a package window is not a replacement for the settings the owner already had",
    )


def shape_refusals(sources: dict[str, str]) -> None:
    for name, text in sources.items():
        # A loader is geometry, not a surface: a 50% radius on a spinner is the only
        # rounded shape allowed, and it must not be used to smuggle in a rounded panel.
        for rule in re.finditer(r"(?s)([^{}]+)\{([^{}]*)\}", text):
            selector, block = rule.group(1).lower(), rule.group(2)
            for match in re.finditer(r"border-radius\s*:\s*([^;]+)", block):
                value = match.group(1).strip()
                if value == "50%" and ("spinner" in selector or "loader" in selector):
                    continue
                refuse("rounded-rectangle", name, match.group(0).strip())
        for match in re.finditer(r"clip-path\s*:\s*([^;]+)", text):
            value = match.group(1).strip()
            if name.endswith("contour.js") and value.startswith("path"):
                continue
            # A stylesheet may only consume the authority's own clip variable.
            if value.startswith("var(--clip"):
                continue
            refuse("shape-not-nine-slice", name, f"clip-path {value[:60]}")
        for pattern in ("polygon(", "ellipse(", "circle(", "inset(", "rect("):
            if pattern in text and not name.endswith("contour.js"):
                refuse("shape-not-nine-slice", name, f"{pattern.rstrip('(')} outside the contour authority")
        for match in re.finditer(r"borderRadius|clipPath\s*=\s*[\"'](?!path)", text):
            if name.endswith("contour.js"):
                continue
            refuse("shape-not-nine-slice", name, match.group(0))


def surface_refusals(sources: dict[str, str]) -> None:
    """A painted surface in a generated row must ask for the contour in the same tag."""
    for name, text in sources.items():
        if not name.endswith((".js", ".html")):
            continue
        for match in re.finditer(r"<[a-z]+[^>]*class=\"[^\"]*\b(card|cell|field|plate|bar|shell)\b[^\"]*\"[^>]*>", text):
            tag = match.group(0)
            if "data-contour" in tag:
                continue
            refuse("surface-without-contour", name, tag[:70])


def clip_padding_refusals(sources: dict[str, str]) -> None:
    """The clip padding is pinned: a frame that crosses its own clip aliases unevenly."""
    authority = sources.get("ui/contour.js", "")
    match = re.search(r"const CLIP_PAD = ([0-9.]+);", authority)
    pad = float(match.group(1)) if match else 0.0
    check(
        "clip-without-padding",
        "the clip is inset by at least half the frame's width",
        pad >= 0.5,
        "ui/contour.js",
        f"CLIP_PAD is {pad}",
    )
    check(
        "clip-without-padding",
        "the padding is applied by the path",
        "const inset = Math.min(pad" in authority and "Math.max(2, width - 2 * inset)" in authority,
        "ui/contour.js",
        "the path does not apply the padding",
    )
    check(
        "fractional-clip-box",
        "the clip and the frame use whole pixels",
        "Math.floor(rect.width)" in authority and "Math.floor(rect.height)" in authority,
        "ui/contour.js",
        "a fractional box puts the one pixel frame on a half pixel",
    )
    check(
        "outline-without-frame",
        "every clipped surface is stroked with the same path",
        'element.style.setProperty("--clip", `path(' in authority and 'stroke.setAttribute("d", d)' in authority and "background: var(--paint, none)" in sources.get("ui/bar.css", ""),
        "ui/contour.js",
        "the clip and the frame must be one path",
    )
    # A half pixel inset puts a one pixel stroke exactly on the pixel grid: it fills one
    # whole pixel instead of two half lit ones, which is the uneven edge the owner sees.
    points = nine_slice(240, 40, json.loads(CONTOUR.read_text(encoding="utf-8")))
    left = min(x for x, _ in points)
    top = min(y for _, y in points)
    check(
        "stroke-off-pixel-grid",
        "a straight edge lands on a half pixel",
        abs((left % 1) - 0.5) < 0.01 and abs((top % 1) - 0.5) < 0.01,
        "ui/contour.js",
        f"edge at {left:.2f},{top:.2f} sits off the pixel grid",
    )


def contour_refusals(shape: dict) -> None:
    segments = shape.get("segments") or []
    check("contour-profile", "eight cubics", len(segments) == 8, "contour.json", f"{len(segments)} segments")
    start = tuple(shape.get("start") or ())
    end = tuple(segments[-1][4:]) if segments else ()
    check(
        "contour-profile",
        "the profile closes on its start point",
        start == end,
        "contour.json",
        f"start {start} end {end}",
    )

    # One corner size for the family: a wide button and a narrow one are cut the same.
    authority = read_sources().get("ui/contour.js", "")
    check(
        "contour-not-stretched",
        "the path is not mapped by a separate factor per axis",
        "const mapX = (x) =>" not in authority and "spanX) * innerW" not in authority
        and "spanY) * innerH" not in authority,
        "ui/contour.js",
        "the view maps the profile per axis instead of cutting it faithfully",
    )
    check(
        "contour-not-stretched",
        "the view refuses a crown that leaves its own frame",
        "contourFits(" in authority and "contour-crown-outside-frame" in authority,
        "ui/contour.js",
        "the runtime has no guard against an outline that is clipped",
    )
    mask_source = (ROOT / "window.py").read_text(encoding="utf-8")
    check(
        "frame-not-clipped",
        "the window mask sits outside the drawn outline so neither edge is cut",
        "shape: dict, pad: float = 0.0" in mask_source,
        "window.py",
        "the mask cuts the window's own stroke",
    )
    # A window frame does not scale the contour: the corner keeps the profile's own units and
    # the rails take the span. The buttons keep the family corner and are untouched by it.
    check(
        "window-frame-is-the-profile",
        "the window frame takes the accepted corner, the one a bar button uses",
        "export function contourWindowPath(" in authority
        and "return contourPath(width, height, pad);" in authority
        and "pad = FRAME_PAD, cornerPx = CORNER_PX)" in authority
        and "contourPath(w, h, FRAME_PAD)" in authority,
        "ui/contour.js",
        "the window frame scales the contour instead of drawing it",
    )
    for width, height in ((150, 40), (620, 660), (1920, 48)):
        points = nine_slice(width, height, shape, 1.5)
        inside = all(1.5 - 0.75 <= x <= width - 1.5 + 0.75
                     and 1.5 - 0.75 <= y <= height - 1.5 + 0.75 for x, y in points)
        check(
            "contour-crown-inside-frame",
            f"the crown stays inside a {width}x{height} frame",
            inside,
            "contour.json",
            f"{width}x{height} keeps every drawn point inside the frame: {inside}",
        )

    # One profile at every size: the drawn outline reaches every edge of its surface, so a
    # narrow surface and a wide one are cut the same way and the profile is never shrunk.
    narrow = nine_slice(200, 36, shape)
    wide = nine_slice(900, 36, shape)
    huge = nine_slice(1400, 1400, shape)

    def fills(points, width, height, pad=1.5):
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        return (abs(min(xs) - pad) < 0.01 and abs(max(xs) - (width - pad)) < 0.01
                and abs(min(ys) - pad) < 0.01 and abs(max(ys) - (height - pad)) < 0.01)

    check(
        "corners-scale-with-the-contour",
        "the drawing's profile fills a narrow surface, a wide one and a huge one",
        fills(narrow, 200, 36) and fills(wide, 900, 36) and fills(huge, 1400, 1400),
        "contour.json",
        f"narrow {fills(narrow, 200, 36)}, wide {fills(wide, 900, 36)}, huge {fills(huge, 1400, 1400)}",
    )

    tall = nine_slice(620, 660, shape)
    left = min(x for x, _ in tall)
    right = max(x for x, _ in tall)
    check(
        "corners-scale-with-the-contour",
        "the window keeps its crown, centred",
        max(y for _, y in tall) >= 657 and abs(left - (620 - right)) < 1.0,
        "contour.json",
        f"crown {left:.1f}..{right:.1f} of 620, depth {max(y for _, y in tall):.1f} of 660",
    )

    # A large window must not flower: the profile's corner is the drawing's own share of the
    # surface and never reaches past the middle of the window.
    span = min(620, 660) / 2
    check(
        "corners-do-not-flower",
        "a large window's corner stays a corner",
        corner_span(tall, 620) <= span,
        "contour.json",
        f"window corner {corner_span(tall, 620):.1f}px against a limit of {span:.1f}px",
    )


def selftest() -> int:
    """Plant each shape this gate exists to refuse and require the refusal."""
    planted = {
        "ui/planted.css": ".card { border-radius: 6px; }",
        "ui/planted.js": "el.style.clipPath = 'polygon(0 0, 100% 0, 100% 100%)';",
        "ui/planted.html": '<div class="card">no contour here</div>',
        "ui/planted-pad.js": "const CLIP_PAD = 0;\nel.style.clipPath = `path('M 0 0')`;",
    }
    failures = 0
    for name, text in planted.items():
        REFUSALS.clear()
        shape_refusals({name: text})
        surface_refusals({name: text})
        if "CLIP_PAD" in text:
            clip_padding_refusals({name: text})
        print(f"planted {name}: {REFUSALS[-1] if REFUSALS else 'NOT REFUSED'}")
        if not REFUSALS:
            failures += 1
        REFUSALS.clear()
    REFUSALS.clear()
    shape_refusals({"ui/planted-spinner.css": ".spinner { border-radius: 50%; }"})
    round_ok = not REFUSALS
    print("planted spinner radius:", "allowed" if round_ok else "refused")
    if not round_ok:
        failures += 1
    REFUSALS.clear()
    shape_refusals({"ui/planted-spinner.css": ".spinner { border-radius: 6px; }"})
    square_ok = bool(REFUSALS)
    print("planted spinner square:", "refused" if square_ok else "NOT REFUSED")
    if not square_ok:
        failures += 1
    REFUSALS.clear()
    print("selftest", "pass" if failures == 0 else f"fail ({failures} planted shapes were drawn)")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    try:
        shape = json.loads(CONTOUR.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"[FAIL] contour.json: {error}")
        return 1
    sources = read_sources()
    shape_refusals(sources)
    surface_refusals(sources)
    contour_refusals(shape)
    taskbar_pin("--pin-bar" in sys.argv[1:])
    clip_padding_refusals(sources)

    family_look_pin()
    landing_pin()
    toast_refusals()
    probe_isolation()
    controls_pin()
    bar_control_refusals()
    freshness_register()
    capacity_audit_checks()
    settings_package_checks()

    authority = sources.get("ui/contour.js", "")
    check(
        "contour-authority",
        "the nine-slice is defined once",
        authority.count("export function contourPath") == 1,
        "ui/contour.js",
        "contourPath must be defined once",
    )

    # The settings package is the mutable window base: layout travels with the theme in the
    # same signed document, and the apps read it rather than owning their own numbers.
    package_src = (ROOT / "settings_package.py").read_text(encoding="utf-8", errors="replace")
    package_js = sources.get("ui/package.js", "")
    settings_html = sources.get("ui/settings.html", "")
    settings_css = sources.get("ui/settings.css", "")
    check(
        "settings-carries-layout",
        "the settings package publishes the layout every app derives",
        all(token in package_src for token in ("LAYOUT_APPS", '"layout"', "settings-layout"))
        and "--popit-columns" in package_js and "layout || {}" in package_js,
        "settings_package.py",
        "layout must be signed with the theme",
    )
    settings_window = sources.get("ui/toast.html", "")
    app_src = (ROOT / "app_package.py").read_text(encoding="utf-8", errors="replace")
    check(
        "settings-category-rail",
        "settings has a scrolling rail and a page per category",
        # The settings window is the panel the desk draws, and its surface list is that panel's:
        # one tab and one pane per family surface, on a rail that scrolls.
        settings_window.count("data-settings-tab-choice=") >= 2
        and settings_window.count("data-settings-pane=") >= 2
        and "overflow" in sources.get("ui/toast.css", "")
        and "var(--popit-" in sources.get("ui/toast.css", ""),
        "ui/settings.html",
        "every category needs a page on a scrollable rail",
    )
    check(
        "apps-are-authored-packages",
        "an app payload declares what it adds and derives",
        all(token in app_src for token in ('APP_SCHEMA = "popit.app/2"', "app-legacy",
                                           "app-not-authored", "app-window-incomplete",
                                           '"derives": DERIVES', '"authored": authored',
                                           'REGION_CONTRACT = ("bar", "status", "body", "foot")'))
        and app_src.count('"kind":') >= 3 and app_src.count('"pages":') >= 3,
        "app_package.py",
        "a files-only or thin-page payload must be refused",
    )
    regions = ("bar", "status", "body", "foot")
    thin = [name for name in ("ui/toast.html", "ui/settings.html", "ui/phone.html")
            if not all(f'data-region="{region}"' in sources.get(name, "") for region in regions)]
    check(
        "every-window-carries-the-family-regions",
        "a window is bar, status, body and foot",
        not thin,
        "ui/toast.html",
        f"missing regions in {', '.join(thin) or 'none'}",
    )
    # The reference forms are read from the registry itself, not from a count typed here: a
    # window is a window (dialin, settings, prose, archive, evidence) and the home is the
    # phone, so a new app joins the family by name instead of by editing a number.
    windows_named = [name for name, spec in app_package.APPS.items()
                     if spec.get("kind") == "window"]
    phones_named = [name for name, spec in app_package.APPS.items()
                    if spec.get("kind") == "phone"]
    check(
        "mutable-package-kinds-are-the-reference-forms",
        "a mutable package is a window or the phone home; the archive apps are windows",
        'KINDS = ("window", "phone")' in app_src
        and 'FOREIGN: dict[str, str] = {"bridge": "window page"}' in app_src
        and '"kind": "surface"' not in app_src
        and "app-kind-foreign" in app_src
        and all(spec.get("kind") in app_package.KINDS for spec in app_package.APPS.values())
        and set(windows_named) == {"dialin", "settings", "prose", "archive", "evidence"}
        and phones_named == ["springboard"],
        "app_package.py",
        f"windows {windows_named}, phone {phones_named}",
    )
    # The desk is the settings window's own page: its palette and motion ARE the baseline's,
    # and no other window may copy them.
    copied = [name for name in ("ui/bridge.css", "ui/phone.css", "ui/settings.css")
              if re.search(r"--primary:\s*#|@keyframes", sources.get(name, ""))]
    check(
        "dialin-reads-the-settings-formats",
        "the desk takes its visual and motion formats from the signed settings package",
        "contour-theme.css" in sources.get("ui/toast.html", "")
        and 'attach("dialin"' in sources.get("ui/toast.js", "")
        and 'data-window="popit-settings-package"' in sources.get("ui/toast.html", "")
        and not copied
        and "ide:" not in sources.get("ui/package.js", "")
        and "data-motion=\"" not in sources.get("ui/toast.html", ""),
        "ui/toast.html",
        "a window kept its own copy of the palette or motion: "
        + (", ".join(copied) or "none"),
    )
    # Project convention from 2026-11-25: every app package subscribes to the signed settings
    # app instead of carrying a private theme, and signs every asset it loads, so bringing in
    # a feature or a dependency keeps signing properly.
    # The bridge is a foreign window page, not a package: only the packages that are signed
    # subscribe. A page that is listed as foreign cannot stand in for one of them.
    subscribed = all(
        f'attach("{name}"' in (UI / script).read_text(encoding="utf-8")
        for name, script in (("dialin", "toast.js"), ("settings", "settings.js"),
                             ("springboard", "phone.js"), ("archive", "toast.js"),
                             ("evidence", "toast.js")))
    bridged = ("app_package.FOREIGN" in app_src or 'FOREIGN: dict[str, str] = {"bridge": "window page"}' in app_src)
    check(
        "packages-subscribe-the-settings-app",
        "every app attaches to the settings app and declares every asset it loads",
        subscribed and "app-not-subscribed" in app_src
        and "app-dependency-undeclared" in app_src,
        "app_package.py",
        "an app kept a private theme or an asset the package does not sign",
    )
    # The settings app package is the floating settings window: every other window is built
    # from it, and the SpringBoard's settings tile opens it itself.
    phone_js = (UI / "phone.js").read_text(encoding="utf-8")
    sheets = ("contour-theme.css", "package.js", "contour.js")
    derived = all(
        all(sheet in app_package.APPS[name]["files"] for sheet in sheets)
        and "/contour-theme.css" in (UI / app_package.APPS[name]["entry"]).read_text(encoding="utf-8")
        for name in ("dialin", "settings")) and bridged
    app_base_src = (ROOT / "app_base.py").read_text(encoding="utf-8") \
        if (ROOT / "app_base.py").is_file() else ""
    chrome_pages = ("toast.html", "settings.html")
    own_chrome = [page for page in ("phone.html", "settings.html")
                  if "@keyframes" in sources.get(f"ui/{page}", "")]
    check(
        "chrome-comes-from-the-settings-window",
        "the chrome, the motion and how buttons look are the settings window's provision",
        "--popit-" in sources.get("ui/toast.css", "")
        and all("/contour-theme.css" in sources.get(f"ui/{page}", "") for page in chrome_pages)
        and not own_chrome
        and "app-chrome-handrolled" in app_src,
        "ui/toast.css",
        "a window painted its own chrome or a button look of its own: "
        + (", ".join(own_chrome) or "none"),
    )
    check(
        "no-handrolled-window-pages",
        "a window package is the settings window's page, never a page of its own",
        'raise Refused("app-handrolled-window"' in app_src
        and "baseline_entry" in app_src
        and 'FOREIGN: dict[str, str] = {"bridge": "window page"}' in app_src,
        "app_package.py",
        "a hand-rolled window page could be signed as a package",
    )
    check(
        "packages-are-mutated-subscriptions",
        "an app package is a mutated signed subscription, never a plain derivation",
        'SCHEMA = "popit.app-base/1"' in app_base_src
        and "app-not-mutated" in app_base_src
        and "app-base-stale" in app_base_src
        and "import app_base" in app_src
        and 'app_base.subscription(self.settings, name, spec' in app_src
        and "app_base.check(body.get(\"base\")" in app_src,
        "app_base.py",
        "a package could be signed without a current mutated subscription",
    )
    # Delivery is the settings window's delivery: every app names the window it is delivered
    # in, and the shell opens each app in its own named window through one helper — no app is
    # navigated into, and none is special-cased into the settings window.
    delivered = {
        "dialin": "popit-settings-package",
        "settings": "popit-settings-package",
    }
    # The contour is drawn by the window's own script from the measured path, so a window that
    # fails to load it looks exactly like a refused package. The settings window therefore reads
    # its package first, refuses by name, and only then draws the contour.
    desk_js = sources.get("ui/toast.js", "")
    check(
        "window-contour-implies-a-verified-package",
        "a window draws the contour only after its package is delivered, and names a refusal",
        'attach("dialin"' in desk_js
        and 'get("window") === "settings"' in desk_js
        and 'dataset.windowMode = "settings"' in desk_js
        and 'body[data-window-mode="settings"]' in sources.get("ui/toast.css", "")
        and "app-not-delivered-as-window" in app_src,
        "ui/toast.js",
        "the settings window is the desk's own page, or a copy of it was served",
    )
    check(
        "apps-deliver-windows-like-the-settings-window",
        "every app is served as its own page and opened in its own named window",
        derived and "app-not-delivered-as-window" in app_src
        and all(f'data-window="{window}"' in sources.get(f"ui/{page}", "")
                for (name, window), page in zip(delivered.items(), chrome_pages))
        # Every tile opens in the window that delivered the SpringBoard, the way the desk
        # does: no popup, and no second window holding a copy of a surface.
        and "location.assign(route)" in phone_js
        and "window.open" not in phone_js
        and 'data.app === "settings"' in desk_js
        and 'data.app === "bridge"' in desk_js
        # The settings tile opens the settings app package's window, never the package
        # document page that names its revision.
        and 'settings: "/toast.html?window=settings"' in phone_js
        and 'settings: "/settings.html"' not in phone_js,
        "ui/phone.js",
        "an app did not name its delivered window, or the shell special-cased one app",
    )
    check(
        "no-app-bar-control",
        "a package payload cannot add a control to the shell's bar",
        "BAR_CONTROL_KEYS = (\"bar_controls\", \"chrome\", \"controls\")" in app_src
        and 'raise Refused("app-bar-control"' in app_src,
        "app_package.py",
        "a package that names bar controls is refused, not signed",
    )
    store_path = ROOT / "docs" / "app-store.json"
    store = {}
    try:
        store = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        store = {}
    listed = {str(row.get("name")) for row in store.get("apps") or [] if isinstance(row, dict)}
    check(
        "app-store-lists-only-standard-packages",
        "the landing-page store carries signed window and phone packages only",
        store.get("schema") == "popit.app-store/1"
        and store.get("kinds") == ["window", "phone"]
        and listed == set(app_package.APPS)
        and "ide" not in listed
        # A window page is rejected from the store by name, the same rejection the IDE got.
        and {str(row.get("name")) for row in store.get("refused") or []
             if isinstance(row, dict)} == {"bridge"},
        "docs/app-store.json",
        f"lists {sorted(listed) or 'nothing'}",
    )
    # Family prose is one program, one rule set and an external document per project. The rules
    # are imported from portal-shell's checker, so this project cannot drift into its own bans.
    prose_src = (ROOT / "tools" / "prose_family.py").read_text(encoding="utf-8") \
        if (ROOT / "tools" / "prose_family.py").is_file() else ""
    prose_page = (ROOT / "tools" / "prose_ui" / "index.html").read_text(encoding="utf-8") \
        if (ROOT / "tools" / "prose_ui" / "index.html").is_file() else ""
    prose_index = ROOT / "docs" / "prose" / "index.html"
    prose_rows = list((ROOT / "docs" / "prose").glob("*/index.html")) \
        if (ROOT / "docs" / "prose").is_dir() else []
    check(
        "prose-program-reads-the-family-rules",
        "the prose program imports the family checker and carries no ban list of its own",
        "spec_from_file_location" in prose_src and "FAMILY_CHECKER" in prose_src
        and "WORDS = (" not in prose_src and "PHRASES = (" not in prose_src
        and all(f'"{phase}"' in prose_src for phase in ("inventory", "driver", "docs", "verify")),
        "tools/prose_family.py",
        "the prose program kept a private copy of the rules or lost a phase",
    )
    check(
        "prose-program-renders-every-family-document",
        "every family project has an external prose document, and the index links them",
        prose_index.is_file() and 'id="family-index"' in prose_index.read_text(encoding="utf-8")
        and len(prose_rows) >= 6
        and all('data-doc="prose"' in row.read_text(encoding="utf-8") for row in prose_rows),
        "docs/prose",
        f"{len(prose_rows)} project document(s)",
    )
    check(
        "prose-driver-fact-is-asked-not-assumed",
        "which projects the box has staged is read over the bridge, and a miss is named",
        "STAGED_ROOT" in prose_src and "prose-not-staged" in prose_src
        and "driver-unreachable" in prose_src and '"run", "--"' in prose_src
        and "subprocess.run" in prose_src,
        "tools/prose_family.py",
        "the prose program assumed the driver's staging state",
    )
    app_src_now = (ROOT / "app_package.py").read_text(encoding="utf-8")
    toast_html = sources.get("ui/toast.html", "")
    toast_js = sources.get("ui/toast.js", "")
    phone_js_now = sources.get("ui/phone.js", "")
    css_now = sources.get("ui/toast.css", "")
    check(
        "prose-app-is-a-signed-window",
        "prose is a package delivered in the settings window, not a page of its own",
        '"prose": {' in app_src_now and '"kind": "window"' in app_src_now
        and '"entry": "toast.html"' in app_src_now
        and 'attach("prose"' in toast_js
        and 'id="prose-panel"' in toast_html
        and 'body[data-window-mode="prose"]' in css_now,
        "app_package.py",
        "the prose surface is not the settings window with a prose body",
    )
    check(
        "prose-app-is-tiled-and-measured",
        "the SpringBoard carries its tile and the window audit opens its window",
        "prose: { label:" in phone_js_now
        and 'prose: "/toast.html?window=prose"' in phone_js_now
        and '"prose": "/toast.html?window=prose&uiaudit=1&app=prose"' in (ROOT / "toast.py").read_text(encoding="utf-8")
        and 'popitProse' in toast_js and 'prose-spin' in css_now,
        "ui/phone.js",
        "the prose window is not tiled, not audited, or has no spinner",
    )
    toast_src_now = (ROOT / "toast.py").read_text(encoding="utf-8")
    # The family's prose ratchet: the shared checker writes a receipt naming every project's
    # counts, and the gate refuses a receipt that is stale or that records a regression.
    family_receipt = ROOT / "artifacts" / "receipts" / "prose-ratchet.json"
    family_body: dict = {}
    try:
        family_body = json.loads(family_receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        family_body = {}
    # The family checkout sits beside this one, which is how every other family tool finds it.
    checker_now = ROOT.parent / "portal-shell" / "tools" / "ui_prose.py"
    fresh_enough = (family_receipt.is_file() and checker_now.is_file()
                    and family_receipt.stat().st_mtime >= checker_now.stat().st_mtime)
    if checker_now.is_file():
        check(
            "family-prose-ratchet",
            "every family project is held by its own prose ratchet, none regressed",
            bool(family_body) and int(family_body.get("checked") or 0) >= 11
            and int(family_body.get("regressed") or 0) == 0 and fresh_enough,
            "artifacts/receipts/prose-ratchet.json",
            "the family prose ratchet is missing, stale, or a project regressed",
        )
    else:
        host_bound(
            "family-prose-ratchet",
            "every family project is held by its own prose ratchet, none regressed",
            "the family checkout that writes the receipt is not on this host",
        )
    check(
        "app-windows-are-delivered-over-https",
        "every window route loads the TLS origin; bare http is a refusal, not a fallback",
        'WINDOW_ORIGIN = {"base": "", "note": ""}' in toast_src_now
        and "window-not-secure" in toast_src_now
        and 'fallback-loopback' not in toast_src_now
        and 'view.load(QUrl(f"http://127.0.0.1:{server.server_port}' not in toast_src_now,
        "toast.py",
        "a window is still delivered over the loopback http twin",
    )
    check(
        "springboard-has-no-standalone-page",
        "the home renders only inside the agent window; a bare page is refused by server and page",
        "springboard-standalone-refused" in toast_src_now
        and 'window.parent === window' in phone_js_now
        and 'standalone-refusal' in phone_js_now
        and 'embedded=1' in sources.get("ui/toast.html", "")
        and 'phone.html?embedded=1' in toast_js,
        "toast.py",
        "the fake SpringBoard can still be rendered as a page of its own",
    )
    check(
        "home-carries-no-invented-copy",
        "the home draws names, states and identities; no hero copy and no tile descriptions",
        "A room that answers." not in sources.get("ui/phone.html", "")
        and "Tap a signed app" not in sources.get("ui/phone.html", "")
        and 'class="hero-copy"' not in sources.get("ui/phone.html", "")
        and 'id="home-hint"' not in sources.get("ui/phone.html", "")
        and "sub:" not in phone_js_now
        and "tile-sub" not in phone_js_now,
        "ui/phone.html",
        "invented copy came back onto the SpringBoard",
    )
    check(
        "no-window-is-served-over-bare-http",
        "the window origin is TLS or nothing: no http twin survives as a fallback",
        "http://127.0.0.1:{loopback_port}/toast.html" not in toast_src_now
        and '"window-not-secure"' in toast_src_now
        and 'https-not-bound' not in toast_src_now
        and 'https-no-host' not in toast_src_now,
        "toast.py",
        "a window can still be delivered over bare http",
    )
    check(
        "a-refused-window-keeps-its-grips",
        "a refusal hides the app body, never the window's own bar and resize grips",
        ":not(.bar):not(.grip)" in sources.get("ui/toast.css", "")
        and 'class="grip' in sources.get("ui/toast.html", ""),
        "ui/toast.css",
        "a refused window has no way to be resized",
    )
    check(
        "a-window-theme-is-the-settings-package",
        "no window paints before the settings package names its theme, frame and material",
        "__popitThemeAuthor" in toast_js
        and "settings-theme-unknown" in toast_js
        and 'dataset.windowState = "refused"' in toast_js
        and 'window.__popitThemeAuthor' in toast_js
        and "__popitPackageStyle" in sources.get("ui/package.js", ""),
        "ui/toast.js",
        "a window can still paint its own default theme before the package arrives",
    )
    check(
        "the-home-is-the-fallback",
        "a package window that cannot verify shows the SpringBoard, never a bare themed bar",
        "function showHome()" in toast_js
        and 'if (app !== "springboard") setSurface("springboard")' in toast_js
        and "delete document.body.dataset.windowMode" in toast_js
        and 'if (data.app === "springboard") setSurface("springboard")' in toast_js,
        "ui/toast.js",
        "a refused window can still resolve to a bar with no frame and no resize",
    )
    check(
        "app-tiles-prove-their-launch",
        "an icon frame verifies only with the launch it opens and a measured window",
        'LAUNCH_RULE =' in app_src_now
        and 'def launch_proof(' in app_src_now
        and 'app-tile-without-launch' in app_src_now
        and 'app-tile-unproven-launch' in phone_js_now
        and 'row.launch_proof.ok' in phone_js_now
        and 'function launchFor(' in phone_js_now
        and 'ui_audit' not in phone_js_now,
        "app_package.py",
        "a tile is signed without proving the window it launches",
    )
    check(
        "prose-surface-is-not-a-page",
        "the prose engine is headless: no server, no port, no page of its own",
        not (ROOT / "tools" / "prose_ui").exists()
        and "HTTPServer" not in prose_src and "ThreadingHTTPServer" not in prose_src
        and 'def probe(' in prose_src and "/api/toast/prose/doc/" in prose_src
        and 'popit.prose-probe/1' in prose_src,
        "tools/prose_family.py",
        "the prose surface went back to being a hand-rolled page beside the client",
    )
    theme_css = sources.get("ui/contour-theme.css", "")
    check(
        "scrollbars-are-themed",
        "no app shows a browser-default scrollbar",
        "scrollbar-color" in theme_css and "::-webkit-scrollbar-thumb" in theme_css
        and "var(--popit-ground" in theme_css,
        "ui/contour-theme.css",
        "the theme sheet must paint every window's scrollbars",
    )
    check(
        "window-ground-is-the-published-ground",
        "a window ground is derived, not the raw deep role",
        "--popit-ground" in sources.get("ui/package.js", "")
        and "groundFrom" in sources.get("ui/package.js", "")
        # The ground is the theme sheet's to paint from the published ground role; a window
        # that painted the raw deep role would read as a hole rather than a surface.
        and "var(--popit-ground" in sources.get("ui/contour-theme.css", "")
        and "--popit-deep" not in sources.get("ui/toast.html", ""),
        "ui/package.js",
        "an app painting the raw deep role stops reading as a window",
    )
    check(
        "surfaces-read-the-layout",
        "an app's frame comes from the published layout",
        all("var(--popit-" in sources.get(name, "") for name in
            ("ui/toast.css", "ui/phone.css", "ui/contour-theme.css")),
        "ui/settings.css",
        "a hard-coded frame does not derive from settings",
    )

    # The session archive and the evidence backup are the two legacy apps rebuilt as desk
    # windows. Every check below reads the signed spec, the app's own page and script, the
    # SpringBoard tile and the project block the payload carries.
    desk_apps = ("archive", "evidence")
    session_src = (ROOT / "session_archive.py").read_text(encoding="utf-8") \
        if (ROOT / "session_archive.py").is_file() else ""
    server_src = (ROOT / "server.py").read_text(encoding="utf-8", errors="replace")
    archive_windows = all(
        app_package.APPS[name]["kind"] == "window"
        and app_package.APPS[name]["entry"] == "toast.html"
        and app_package.APPS[name]["window"] == "popit-settings-package"
        and f'id="{name}-panel"' in toast_html
        and f'get("window") === "{name}"' in toast_js
        and f'body[data-window-mode="{name}"]' in css_now
        and f'{name}: {{ label:' in phone_js_now
        and f'{name}: "/toast.html?window={name}"' in phone_js_now
        and f'"{name}": "/toast.html?window={name}&uiaudit=1&app={name}"' in toast_src_now
        for name in desk_apps)
    check(
        "session-archive-apps-are-desk-windows",
        "the archive and the evidence backup are settings-window modes with their own tile and audit",
        archive_windows,
        "app_package.py",
        "an archive app is not the settings window with its panel as the body",
    )
    try:
        launches = {name: app_package._spec(name)["launch"] for name in desk_apps}
        launch_form = True
    except app_package.Refused as error:  # a tile without a launch gets no signature
        launches, launch_form = {}, False
        refuse("app-tile-without-launch", "app_package.py", error.detail)
    check(
        "archive-apps-sign-their-icon-frame",
        "an icon frame signs only the launch that opens the window it mutates",
        launch_form
        and all(launch.endswith(f"window={name}") for name, launch in launches.items())
        and 'def launch_proof(' in app_src_now
        and 'app-tile-unproven-launch' in app_src_now
        and 'row.launch_proof.ok' in phone_js_now,
        "app_package.py",
        f"launches {launches}",
    )
    project_ok = all(
        spec.get("project", {}).get("ticket")
        and (ROOT / "tickets" / f"{spec['project']['ticket']}.md").is_file()
        and str(spec["project"].get("ledger", "")).startswith("runlogs/")
        and (ROOT / spec["project"]["ci"]).is_file()
        and (ROOT / spec["project"]["landing"]).is_file()
        for spec in (app_package.APPS[name] for name in desk_apps))
    check(
        "archive-apps-carry-the-project-baseline",
        "both apps are built from the settings baseline and the pinned project setup",
        project_ok
        and 'PROJECT_SETUP = {' in app_base_src
        and '"PROJECT_SETUP_DIGEST"' not in app_base_src
        and '"project_digest": project_digest()' in app_base_src
        and 'app-project-baseline-stale' in app_base_src
        and '"project": "popit.project-setup/1"' in app_src_now
        and 'authored["project"]' in app_src_now
        and (ROOT / "logs" / "authority" / "2026-11-26-session-archive-apps.jsonl").is_file(),
        "app_base.py",
        "an archive app carries no ticket, ledger, CI, landing page or project pin",
    )
    codes = ("archive-unknown-project", "archive-root-unreadable", "archive-root-absent",
             "archive-backup-none", "archive-backup-mode", "archive-path-outside",
             "archive-path-absent", "archive-evidence-absent", "archive-show-loopback",
             "archive-clean-confirm", "archive-legacy-retired", "archive-evidence-unreadable")
    check(
        "session-archive-refusals-are-named",
        "an act that cannot be shown is refused by name on both origins",
        "class Refused" in session_src
        and all(code in session_src + toast_src_now + server_src for code in codes)
        and 'with LEDGER.open("a", encoding="utf-8")' in session_src
        and 'secure-origin-required' in toast_src_now
        and 'CACHE_DIRS = ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")'
        in session_src,
        "session_archive.py",
        "the apps act without a named refusal or outside the family cache rule",
    )
    check(
        "legacy-archive-page-is-retired",
        "the loopback archive page is gone; the desk app is the only archive",
        not (UI / "archive.html").exists() and not (UI / "archive.js").exists()
        and not (UI / "archive.css").exists()
        and 'archive.html' not in toast_src_now
        and 'archive-legacy-retired' in server_src
        and 'archive.html' not in sources.get("ui/toast.js", "")
        and 'desk_window = "https://127.0.0.1:5211/toast.html?window=archive"'
        in (ROOT / "shell.py").read_text(encoding="utf-8"),
        "ui/archive.html",
        "a legacy archive page or a bare-http window is still served",
    )

    for line in CHECKS:
        print(f"[ok] {line}")
    for line in HOST_BOUND:
        print(f"[n/a] {line}")
    for line in REFUSALS:
        print(f"[FAIL] {line}")
    print(f"{len(CHECKS)} checks, {len(REFUSALS)} refusals")
    return 0 if not REFUSALS else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
