# App packages

Every surface the shell serves is an app package: `dialin`, `settings`, `springboard` and
`ide`. The shape comes from the settings package and the phone's security work, applied once
rather than per page.

## What an app package is

An app names the files it serves (`app_package.APPS`) and hashes them into the family's
`secure-shell.package/1` identity. The record carries the identity, the payload digest and
the publisher's Ed25519 signature; it is signed with the settings package's key and
verified against `runlogs/toast/envelope-trust.json`, the same registry the phone and the
settings window read. There is one publisher (`popit-publisher`), not a second authority
per app.

An app is **authored**, not a folder of files. The signed payload is a `popit.app/2`
document: `kind` (`window`, `surface` or `phone`), the `entry` page, `title`, `summary`, the
`pages` the app adds, the `adds` list a reader can quote, and `derives` naming the settings
package and the fields it takes from it (`theme`, `layout`, `motion`, `dpi`). A payload that
only lists files is a **legacy package**: `verify()` refuses `app-legacy` before the tamper
comparison, and a document with an incomplete manifest is refused `app-not-authored`. That
is why the IDE could not pass as a hand-written page: its payload now says it is a `surface`
with sessions, turns, probes, drivers and bridge pages, and what it derives from settings.

## The signing forms, and the store

A mutable package may take only the three reference forms: `window` (dialin, settings) and
`phone` (springboard). A surface hosted inside a window is refused `app-kind-foreign` — the
IDE has no package identity of its own; dialin's manifest names it under `hosts`, and the
IDE page carries its host's identity and theme.

Every republish is a mutation and is attributed to the CUA driver that carried it: with a
fleet attached, a mutation without a live driver is refused `app-no-driver`, and the driver
is written into the signed record. `tools/app_store.py` builds `docs/app-store.json` for the
landing pages from the signed registry — three packages, their identities, their driver, and
the IDE's refusal — and refuses to write if a package is unverified or a foreign kind is
listed (`store-no-driver`, `store-unverified`, `store-foreign-package`).

A window package is also furniture. Every app declares four regions — `bar`, `status`,
`body`, `foot` — and the entry page must carry `data-region="…"` for each; a page with a
header and a list is refused `app-window-incomplete` rather than signed. Dialin is the
reference: a bar, the mode strip, the body and the foot that names the identity and theme.

The window ground and its scrollbars are the family's, not the browser's. `ui/package.js`
folds the published `deep` role into a dark ground (`groundFrom`, hue kept, light capped) and
writes `--popit-ground`; `ui/contour-theme.css` paints `html` and every scrollbar from it. A
default scrollbar or a page painted in the raw `deep` role is refused by the gate
(`scrollbars-are-themed`, `window-ground-is-the-published-ground`).

The identity is over the *served* files, not a build. If a file changes after the package
was published, `verify()` refuses `app-tampered` instead of serving the changed surface
under the old identity. `ensure()` republishes on the next start when the files moved on.

Refusals are named: `app-unknown`, `app-unsigned`, `app-tampered`, `app-identity`,
`app-signature`, `app-untrusted`, `app-file-absent`.

## Routes

| Route | Answer |
|---|---|
| `GET /api/toast/apps` | every app's identity and verification state |
| `GET /api/toast/apps/<name>` | one signed document: identity, files, signature, theme |
| `POST /api/toast/apps/verify` | the same document; `secure-origin-required` off TLS and off loopback |

`POST /api/toast/apps/verify` keeps the phone's posture: a signed identity is read over a
secure origin, and loopback is the machine itself.

## The theme an app runs

A document carries `theme` and `theme_identity` from the settings package, so an app takes
the frame, material, motion, motion preference and DPI the owner published rather than a
private copy. `ui/package.js` is the shared client: it refuses a document that is not
verified, applies those attributes to `<html>`, and names the identity it is running. It
does not repaint a surface whose package it cannot verify.

`springboard` is the phone page the family already serves (`/phone.html`), loaded into the
shell when the SpringBoard frame is chosen. The phone's own footer names
`app-springboard@<rev>+blake3:<digest>`, and DialIn and Settings are tiles on that page;
they hand control back to the shell over `postMessage` rather than navigating it away.

## The bar is closed, and a package adds pages, never controls

A past revision shipped an `IDE` button in the desk's own bar and a hosted `/ide` page the
window loaded as a surface. Both are removed: `ui/ide.html|js|css`, `ide.py`,
`tools/ide_probe.py`, the `/ide`, `/ide.js`, `/ide.css` and `/api/ide*` routes, the
`#ide-chip` and `#ide-surface` nodes, the `ide` entry in the window's `SURFACES` map, the
`ide_url` in `bridge.py`'s target record, and the `FOREIGN = {"ide": "surface"}` slot in
`app_package.py`. The signable forms are `window` (dialin, bridge, settings) and `phone`
(the springboard); there is no surface kind to sign.

The defect was ownership, not the page: an app package had a control in the shell's bar, so
removing it meant editing the desk, and to a reader it looked like part of the window. Four
checks hold that line:

- `bar-controls-pinned` — the header carrying `data-region="bar"` holds exactly the shell's
  `settings`, `pin` and `close` buttons.
- `bar-no-app-surface` — no chip, app button or `<iframe>` sits in the bar.
- `status-strip-does-not-launch-an-app` — the status strip names state and holds no chip or
  app button.
- `no-app-bar-control` — a signed payload that names `bar_controls`, `chrome` or `controls`
  is refused `app-bar-control` before signing; `tools/app_package_probe.py` proves it with a
  planted payload.

The desk itself is not hand-rolled any more: the CUA drivers rebuild it from the signed
settings app package (wish `task-0003`), and `tools/freshness.py` carries that rebuild as the
stale row `dialin-rebuild` until it lands.

## Project convention: an app package subscribes to the settings app

The owner made this the convention for every app package from 2026-11-25: *"the new dialin
app package would subscribe to the settings app this is project convention from now on and
the app we use must be able to still sign it's packages properly where we bring in new
features/dependencies and development must be driven in the family byt the cua drivers"*.

A mutable package therefore does two things, and both are refused at signing time:

- **It subscribes.** A signed script calls `attach("<name>")` from `/package.js`; the frame,
  material, motion type, motion preference, the ten colour roles, its layout and DPI come
  from the verified settings document. A package whose scripts never attach is refused
  `app-not-subscribed` — a private theme copy is not a package.
- **It signs every asset it loads.** `/contour.js`, `/package.js`, `/contour-theme.css`,
  `/popit-sw.js`, a second script — each must be in the package's `files`. A page or script
  that loads a served `.js` or `.css` the package does not declare is refused
  `app-dependency-undeclared`, because it would render and be audited without being covered
  by the identity. `contour.js` and `phone-calls.js` were exactly that gap before this rule;
  they are declared now.

`tools/app_package_probe.py` proves both refusals with a throwaway surface (16 rows), and the
gate carries `packages-subscribe-the-settings-app`. Development of the packages themselves is
family work: the CUA drivers carry it (the desk's rebuild is wish `task-0003`), and
`tools/freshness.py` keeps every stale package, tile, audit, ledger, refusal, landing page and
CI row visible with the driver act that clears it.

## What measures it

- `tools/app_package_probe.py` (kept): signing, publisher trust, the settings theme
  binding, tamper refusal, an untrusted registry and an unknown app name. Receipt:
  `runlogs/toast/app-package-probe.json`.
- `tools/toast_probe.py`: `app-packages-signed`, `springboard-theme-from-settings`,
  `app-package-client-served`, `app-package-unknown-refused`.
- `tools/gate.py`: `app-packages-use-the-family-signature`, `app-package-probe`,
  `springboard-is-the-phone-home`.

The desk proves the wiring in the footer: `app-dialin@<rev>+blake3:<digest> · theme
popit-settings@<rev>` in green when verified, `package refused · <code>` in red when not.

## The surface audit

A package is signed only for a surface that can be drawn. `ui/ui-audit.js` measures the
rendered page and reports four refusals: `ui-overlap` (two visible controls on one box),
`ui-clipped` (a text surface hiding content it does not ellipsize), `ui-x-overflow` (a
phone-width page wider than the phone) and `ui-x-locked` (overflow no axis can reach).

A page opened with `?uiaudit=1&app=<name>` posts its report to `/api/toast/ui-audit`. The
server stores it against the payload digest, and `AppPackages.publish` refuses
`app-ui-audit` while that measurement reports findings. A surface nobody has measured
publishes with `ui_audit: pending`; a clean measurement gives `ui_audit: passed`. The
SpringBoard reads the same registry (`/api/toast/apps`), so its tiles exist only for signed
packages, carry the contour frame on the tile and the glyph, print their identity, and a
refused package is a disabled tile rather than a launch that fails later.

The shell root `/` is the SpringBoard. The desk is `/toast.html`, which is where the
pinned window and the DialIn tile point.

## Known limits

- A legitimate edit publishes with `ui_audit: pending` until the page is opened with
  `?uiaudit=1`, and reports `app-tampered` if the edit lands while the shell runs. Both
  clear on the next page load.
- DPI is one control: `--popit-dpi` and `data-dpi` name it, and the applied scale is
  `min(dpi, viewport / floor)` with a per-surface floor (`dialin` 400, `settings` 360,
  `springboard` 320). The desk hands its scale to the Qt bridge when the window exists and
  uses CSS zoom with a matching width elsewhere.
