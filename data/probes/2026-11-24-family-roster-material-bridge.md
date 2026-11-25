# 2026-11-24 — family roster, player colours and the contour material bridge

Target: the Popit settings theme system must show the whole family design
evidence, not only LittleBigPlanet. The family roster is primary; LBP is one
player-colour source. `contour` is the bridge between the nine-slice geometry,
the clipped raster material/blend layer and motion, not a corner-size selector.

## Sources

- `C:/Users/ala/Documents/portal-shell/internal/theme/roster.go` — family
  schemes, registers, Popit suite, Deadlock, Alpha, Holo, Material, iOS,
  TouchWiz and simulator legacy.
- `C:/Users/ala/Documents/openlock_modern/docs/design/FAMILY-BRAND-SYNTHESIS.md`
  and `family-design-tokens.json` — family precedence and web/kiosk provenance.
- `C:/Users/ala/Documents/popit_base/references/POPIT-AUDIT.md` —
  LBP1 glossy/static, LBP2 flat/animated, LBP3 translucent/folded; corner
  radius is a weak identifier.
- `F:/Documents/popit-blender/design/popit-pairs.json` — all 37 player pairs.
- `F:/Documents/popit-shell/docs/family-look.md` — one nine-slice profile,
  plus the new material/motion bridge section.

## Registry files

`ui/family-roster.json` and `ui/popit-pairs.json` are served by the live
`toast.py` handler:

```text
GET /family-roster.json  200  application/json; charset=utf-8
GET /popit-pairs.json    200  application/json; charset=utf-8
```

Measured lengths:

```text
family schemes:   17
player colours:   37
```

Family groups rendered by the panel:

```text
Popit shell · 1
Family register · 3
Popit suite · 1
Deadlock · 1
Openlock shell · 1
Android · 2
Material Design · 1
iOS · 1
TouchWiz · 1
Simulator legacy · 5
```

Player groups rendered by the panel:

```text
Popit Forge default · 1
LittleBigPlanet · 12
LittleBigPlanet 3 · 24
```

## Live settings measurements

The live UI was inspected at `http://127.0.0.1:5207/toast.html` after
restarting the live server (PID `9220`, loopback listener `127.0.0.1:5207`).

Source tabs:

```text
FAMILY          aria-pressed=true when a family scheme is current
PLAYER COLOURS  aria-pressed=true when a player pair is current
Theme roster count follows the active source: 17 or 37.
```

Selected values read from the rendered panel:

```text
Popit Family   surface #14100b, text #f4f2ea, material family, motion reveal
Brass Meridian surface #0b1a1c, text #f4f2ea, material metal, motion reveal
Holo Light     surface #ffffff, text #10131a, material flat, motion snap
Cool Island    surface #2569cc, text #f4f2ea, material translucent, motion fold
```

The Holo Light check exposed two real defects that were fixed before this
record:

1. `var(--surface)` was the final `background` layer, which CSS rejects as an
   image, so the surface colour was never painted. The panel now has an actual
   `background-color: var(--surface)` beneath its radial/overlay gradients.
2. Ink was chosen with a brightness threshold, leaving light text on a light
   surface. `inkOn()` now chooses the higher-contrast ink, and light surfaces
   use light overlays with dark text.

## Material layer

`ui/contour.js` appends one `.contour-material` child to every
`[data-contour]` surface, clipped by the same `--clip` path as the frame. The
layer is below content and above surface paint.

Measured on `.settings` with Popit Family:

```text
.contour-material present: true
mix-blend-mode:            soft-light
background-blend-mode:     screen, soft-light (family profile)
opacity:                   0.72
material background:       radial highlight + linear brass/ink wash
```

Measured on Holo Light:

```text
material:                  flat
background-blend-mode:     normal, soft-light
surface:                   rgb(255, 255, 255)
text:                      #10131a
```

Measured on Cool Island:

```text
material:                  translucent
surface:                   rgb(37, 105, 204)
text:                      #f4f2ea
```

The theme-choice buttons carry the same clipped material layer and frame; the
settings source buttons were added to the contour surface list so they use the
same path rather than a second rounded shape.

## Motion

The selected family/player scheme writes `data-motion-profile` on the document
and the settings panel. Holo Light measured:

```text
animation-name: settings-snap
motion-profile: snap
```

`reveal` uses the base `settings-in`; `pop`, `fold`, `snap` and `sweep` have
named keyframes. The existing reduced-motion rule still clamps duration. The
theme choice title carries both values, e.g. `family / reveal` or
`flat / snap`, so the contour is legible as a material and motion bridge.

Persistence was checked after reload:

```text
localStorage.popit.theme = lbp3-cool-island
theme panel dataset       = lbp3-cool-island
active source             = PLAYER COLOURS
count                     = 37
```

## Checks

```text
node --check ui/toast.js                        0
python -m py_compile toast.py                   0
python tools/gate.py                            27 checks, 0 refusals
python tools/toast_probe.py                     56 passed, 0 failed
python tools/landing.py                         wrote docs/
```

`tools/toast_probe.py` now checks both served registries (`17` family schemes
and `37` player colours) and the roster/material contract in the settings
surface. The receipt is at `runlogs/toast/receipt.json`.

## Not verified

- The physical phone microphone/speaker path was not part of this slice.
- The Debian secure-shell settings window remains unavailable as a visible
  window; its earlier capture was black. This record is from the live Windows
  loopback surface.
- No commit or push was made; the existing uncommitted popit-shell work was
  left intact.
