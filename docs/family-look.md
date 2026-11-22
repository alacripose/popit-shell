# The family look

This is the pinned visual example for family applications. The contour is the framing
authority, and every painted surface is a nine-slice of the same page 9 profile.

## One corner for every surface

The profile is measured in the PDF's own units and pinned in `tools/family_look.json`.
A bar cell, a card, a field, the plate and a window frame all take the same corner:
7.67 px wide and 11.00 px tall. The corner never grows with the box it sits in.

Only the rails lengthen. A window 660 px tall and a button 40 px tall show the identical
corner, and a reader can put the two edge to edge without seeing a step.

## Two layers, one outline

The body paints through a path clip at 0.5 px. The frame is the same contour stroked at
1 px from 1.5 px, so the stroke is drawn whole and never cut. A window's mask sits at the
window box, never inside the outline.

## What a refusal looks like

Each of these is refused by name in `tools/gate.py` rather than drawn:

- `contour-not-stretched`: a per-axis map instead of one corner factor.
- `contour-crown-inside-frame` and `contour-crown-outside-frame`: a crown that leaves its box.
- `window-frame-is-the-profile`: a window frame that scales the corner to its own size.
- `frame-not-clipped`: a mask that cuts the drawn stroke.
- `taskbar-pinned`: the pinned strip changed its numbers or its cells.

## Checking a change against the pin

```
python tools/gate.py
```

The gate recomputes the corner from `ui/contour.js` and refuses a pin that no longer
matches what the surfaces draw.
