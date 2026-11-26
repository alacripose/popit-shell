"""Link the pinned control baseline into every app page that draws a button.

The owner's rule: the settings window's material and motion choices are the family's buttons, no
app may diverge from them in motion, function or padding, so every page links `/controls.css` and
paints its buttons from it. This probe is kept: it states the insertion it makes and prints what
it measured, so the diff shows which pages gained the link and which already had it.

    python data/probes/2026-11-26-controls-baseline-link.py
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
UI = ROOT / "ui"
LINK = '<link rel="stylesheet" href="/controls.css" />'
ANCHOR = '<link rel="stylesheet" href="/contour-theme.css" />'


def main() -> int:
    rows = []
    for path in sorted(UI.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        if "<button" not in text or 'href="/controls.css"' in text:
            rows.append((path.name, "already" if 'href="/controls.css"' in text else "no-button"))
            continue
        if ANCHOR in text:
            text = text.replace(ANCHOR, ANCHOR + "\n" + LINK, 1)
        elif "</head>" in text:
            text = text.replace("</head>", LINK + "\n</head>", 1)
        else:
            rows.append((path.name, "no-head"))
            continue
        path.write_text(text, encoding="utf-8")
        rows.append((path.name, "linked"))
    for name, state in rows:
        print(f"{name} {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
