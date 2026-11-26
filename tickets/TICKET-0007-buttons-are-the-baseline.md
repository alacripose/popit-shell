# TICKET-0007 — the buttons are the baseline, not a per-app style

**Owner, verbatim:** *"why is it that the material profile buttons and motion selection buttons in the
settings app are the best version of the buttons in the family and not pinned as the button baseline
subscribable package for apps to use? no buttons in any app should be allowed to diverge from these
buttons in motion and function and padding"*

## Why they were the best, and why nothing else could have them

They were the only two controls in the family authored against the family's own tokens end to end:
`--line` border, `--primary` pressed edge, `--emphasis` hover edge, `--t-fast` and `--ease-pop` motion,
and a press that lifts the control rather than recolouring it. Every other app's buttons were
authored per sheet, so they inherited whatever that sheet had: `ui/settings.css` `button` set
`padding: 8px 14px`, `ui/phone.css` set `10px 13px` and `12px 17px`, `ui/archive.css` set `5px 8px`,
and nineteen rules set their own padding before this ticket. The delivery contract
(`app_base.SLOTS`) had slots for the document, files, script, links and body — no slot for controls —
so there was no place a package could subscribe to them even if an app wanted to. That is why they
were not pinned: the thing they would have been pinned *into* did not exist.

## The pin

- `app_base.CONTROLS` is the record: padding `3px`, tight padding `1px 4px`, min-height `29px`,
  border, background and ink, the motion string, the hover lift and edges, the pressed edge and ink,
  and the focus ring. `source` names where it was measured from: `ui/toast.css .style-option`.
- `app_base.controls_digest()` is its pin. `subscription()` writes `controls` and `controls_digest`
  into every app package's base, and `check()` refuses a package whose digest is not the current one
  (`app-controls-stale`), so an app cannot ship a button baseline of its own.
- `app_base.controls_css()` renders the record into `ui/controls.css`; `write_controls()` writes it
  before anything is signed, and every app declares `controls.css` among its signed files, so the
  sheet a signature covers is the current rendering of the buttons it subscribes to.
- Every app page links `/controls.css`; `.style-option` and `.theme-choice` now carry layout only,
  and their states come from the baseline rather than from `ui/toast.css`.

## The ratchet

`python tools/controls_audit.py` reads every `ui/*.css` for a control rule that sets its own padding,
min-height, transition, animation or transform, and every `ui/*.html` that draws a button without
linking the baseline. It reported 57 findings when it was written and 0 after the sheets were
converted. `tools/gate.py` carries the same reading as the `controls-pin` leg, so a divergent button
is a gate refusal (`button-drift`, `button-baseline-unlinked`), not a matter of remembering.

## Measured state

- Baseline `blake3:d0321425fc02b409579df6dbaac84e9813d633ec7603bc5b2fcaca62cbbb8d5b`, served at
  `/controls.css` with its digest in the header comment.
- All four packages re-signed against it and verified: `app-dialin@152`, `app-settings@141`,
  `app-prose@62`, `app-springboard@101`, each `verified: true` with `ui_audit: passed`.
- `python tools/controls_audit.py` → `0 findings`; `python tools/gate.py` → the `controls-pin` leg
  passes.
- The window's own colour and frame choices still repaint: `choose frame/ios` then `material/glass`
  then back to the package's `material/tint` answered `state: ready`, `refused: ""`.

## What this ticket does not claim

The desk's witness capture after the pin shows the bar's Home, Settings, Pin and Close at the
baseline's size. It does not claim every control in the family has been looked at on a device; the
ratchet reads the sheets and pages, and the phone's own screens were not opened in this pass.
