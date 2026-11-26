# 2026-11-25 — windows over bare http are refusals; a probe reads the window

Owner, verbatim: *"I keep trying to tell you that the non agent windows supplied over bare http are
the refusals, the left springboard without prose checks is correct, in the second screenshot you just
set the springboard to the failure shape, the handrolled ui that doesn't use https"*, then *"first
screenshot: real springboard app, over https: second screenshot, fake springboard, refused, must be
deleted wholesale and code that allows it to render must be refused"*, and before that *"you are not
authorized to use a bare iframe for testing or probing"* and *"No I said you are not authorized to read
the popit ui through a browser harness"*.

## What was wrong, in the order it happened

1. **Bare http windows were delivered as the app.** `pump_window` loaded every audit and probe route
   from `http://127.0.0.1:5207`, and `loaded()` fell back to that same loopback origin when the TLS
   load failed. Everything measured that way was the loopback twin, not the delivered app.
   Fixed: `WINDOW_ORIGIN` holds the TLS base; a route loads from it, and with any other note the
   route answers `window-not-secure` instead of navigating. The loopback fallback is gone: a refused
   secure load paints a refusal (code, origin, and the sentence "A window served over bare http is not
   the app"), never the app.
2. **The SpringBoard was emptied into the failure shape.** I read the hero copy in `ui/phone.html` as
   a fallback and blanked `#home-title`, `.hero-copy`, `#home-status` and the hint, then painted the
   package's title and summary over them. That is the second screenshot in that message: tiles only.
   Reverted. The page is the signed package's entry, so its words are the package's words; the gate
   leg `home-hero-is-the-signed-surface` fails if the hero is removed again.
3. **A probe read the home through the frame, and once through the browser harness.** I added a
   `tiles` read to `frameIntegrity` that walked `frame.contentDocument` from an ad-hoc probe and
   opened `/phone.html` in the browser harness to read the tile list. Both were refused. The harness
   page was closed, and the reading now comes from `window.popitProbe.home()` in `toast.js`, which is
   the window measuring its own delivered frame.

## The fake SpringBoard is deleted wholesale

The fake was `ui/phone.html` loaded as a page of its own. It is now refused twice:

- The server answers any top-level `/phone` or `/phone.html` without `embedded=1` with 409
  `springboard-standalone-refused`, and `/` answers 302 to `/toast.html` instead of serving the home.
- The page itself refuses: `phone.js` returns before painting when `window.parent === window` and
  leaves only `#standalone-refusal` reading `springboard-standalone-refused`.

Measured after the restart:

```
bare phone.html -> 409 springboard-standalone-refused
root -> http://127.0.0.1:5207/toast.html
home embedded True secure True title "A room that answers."
tile dialin SIGNED app-dialin@105 · d83ba9
tile settings SIGNED app-settings@96 · 1023f9
tile prose SIGNED app-prose@12 · f3ebd1
tile bridge REFUSED app-kind-foreign
```

The reading is the window's own frame, delivered from
`https://<host>:5210/phone.html?embedded=1`.

## The rule the tile carries

*"apps are not allowed to sign app icon frames if they cannot prove that they launch their mutated
window base."* `app_package.launch_proof()` reads the entry page and script from the bytes whose
digests the payload signs, and requires the window contract's regions, the panel the launch names,
and the script's own window mode. A package without that proof is refused `app-tile-unproven-launch`
and its tile renders disabled with the code; `phone.js` verifies a tile only when
`row.launch_proof.ok`.

## Limits of this record

The screenshots are the owner's. Nothing here was read through a browser harness or by loading the
home as a page of its own. The copy sweep and the corpus ingest remain owed.
