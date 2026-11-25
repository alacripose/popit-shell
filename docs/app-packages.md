# App packages

Every surface the shell serves is an app package: `dialin`, `settings` and `springboard`.
The shape comes from the settings package and the phone's security work, applied once
rather than per page.

## What an app package is

An app names the files it serves (`app_package.APPS`) and hashes them into the family's
`secure-shell.package/1` identity. The record carries the identity, the payload digest and
the publisher's Ed25519 signature; it is signed with the settings package's key and
verified against `runlogs/toast/envelope-trust.json`, the same registry the phone and the
settings window read. There is one publisher (`popit-publisher`), not a second authority
per app.

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
