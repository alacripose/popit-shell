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

## The contour carries material and motion

The contour is not only the corner profile. Every surface that takes the nine-slice
carries one clipped material layer inside the same path, below the content and above
the surface colour. The material vocabulary is the Popit Goodies Bag's own seven
entries, read from `openlock/docs/UI-PASS.md` and
`openlock/clientaddon/panorama/scripts/openlock_popit.js` (`MATERIALS` and
`paintPopitCell`):

| Profile | Family wash | Evidence |
|---|---|---|
| Paper | `panel` | Goodies Bag material row |
| Card | `title` | Goodies Bag material row |
| Glass | `meta` | Goodies Bag material row |
| Tint | player colour | Goodies Bag material row |
| Ink | `ink` | Goodies Bag material row |
| Accent | `accent` | Goodies Bag material row |
| Bare | no wash | Goodies Bag restore row |

The earlier `family`, `metal`, `gloss`, `flat`, `translucent` and `parchment`
names were a handrolled layer with no family source; they are retired rather than
kept as a second vocabulary. Each of the seven names above is sourced from that
ship, not chosen here, and `LEGACY_MATERIAL_IDS` in `ui/toast.js` maps the retired
ids onto them so a palette stored under an old name still paints. The generation descriptions remain evidence for how a
scheme reads, not extra profile ids: LBP1 is glossy, LBP2 flat and LBP3 translucent
(`POPIT-AUDIT.md` §3–§4, §7).

The original optical documentation in `shploingus-clean/docs/MATERIALS.md` and
`APPEARANCE.md` is the family's material-physics reference: appearance is derived
from material truth and optics, and a missing value is not replaced by an invented
constant. That is the reason these profiles use the shell's role colours rather
than handpicked `rgba` sheens. Those documents describe the voxel world's materials,
not the Popit Goodies Bag names; `openlock` is the authority for the seven names and
for the paint roles above.

The four family frames are the forms openlock actually ships:
`openlock/shell/alpha-shell/forms/{popit,ios,material,touchwiz}.form`. They inherit
the one measured contour and carry identity and colour rules only; no form declares
a second silhouette. The settings panel reads the frame, material and motion beside
the corner dimensions so the bridge is visible in use.

The same contour carries the motion vocabulary: `reveal`, `pop`, `fold`, `snap` and
`sweep`.


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
