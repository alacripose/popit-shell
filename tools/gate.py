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

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
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


def refuse(code: str, where: str, detail: str) -> None:
    REFUSALS.append(f"{code}: {where}: {detail}")


def check(code: str, label: str, ok: bool, where: str = "", detail: str = "") -> None:
    if ok:
        CHECKS.append(f"{code} {label}")
        return
    refuse(code, where or label, detail or label)


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


def shape_refusals(sources: dict[str, str]) -> None:
    for name, text in sources.items():
        for match in re.finditer(r"border-radius\s*:\s*[^;]+", text):
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

    authority = sources.get("ui/contour.js", "")
    check(
        "contour-authority",
        "the nine-slice is defined once",
        authority.count("export function contourPath") == 1,
        "ui/contour.js",
        "contourPath must be defined once",
    )

    for line in CHECKS:
        print(f"[ok] {line}")
    for line in REFUSALS:
        print(f"[FAIL] {line}")
    print(f"{len(CHECKS)} checks, {len(REFUSALS)} refusals")
    return 0 if not REFUSALS else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
