# Every app delivers its window the way the settings window does

Date: 2026-11-25. Owner instruction, verbatim: *"and no, the apps must deliver their windows
the same way the settings window does"*.

## What was wrong before this unit

- The desk and the bridge signed while serving hand-rolled pages, so a signature proved an
  identity and not a window.
- The correction then rendered each window from `settings.html` on the server and refused any
  app whose disk page differed. That copy kept the settings head and dropped the desk's own
  look, so the desk came back unstyled (photographed by the owner), and the refusal
  `app-not-from-settings-window` was a rule about bytes rather than about delivery.

## What the rule is now

| Piece | Contract |
|---|---|
| The page | each window page names the window it is delivered in: `data-window="popit-dialin-package"`, `popit-bridge-package`, `popit-settings-package` |
| The package | `app_package.AppPackages.window_name(name)` is the one naming rule; a page that does not carry its own window is refused `app-not-delivered-as-window` |
| The shell | `ui/phone.js` opens every app through one helper, `window.open(route, \`popit-<name>-package\`, features)`, with geometry from the published layout; the settings special case is removed |
| The gate | `apps-deliver-windows-like-the-settings-window` reads the pages, `phone.js` and `app_package.py` together |
| Serving | `/toast.html`, `/bridge.html`, `/settings.html` are the apps' own pages; no route renders another app's window |

## Measured

- `python tools/app_package_probe.py` — 21 passed, 0 failed, including
  `app-not-delivered-as-window-refused`.
- Live `POST /api/toast/apps/ensure` — `dialin@40`, `bridge@10`, `settings@31`,
  `springboard@41` signed.
- Loopback reads — `/toast.html` 200 / 17404 bytes with `data-window` and
  `data-chrome="popit-settings"`; `/bridge.html` 200 / 3509 bytes; `/settings.html` 200 /
  8438 bytes.
- `python tools/landing.py` rewrote `docs/` from the Debian 13 CUA reading; `tools/app_store.py`
  wrote 3 packages, 0 refused.
- `python tools/freshness.py probe` — 7 passed, 0 failed, 5 stale rows, each naming its act:
  the four `ui_audit: pending` measurements and the dialin rebuild.
- `python tools/gate.py` — 62 checks, 1 refusal (`freshness-no-stale-rows`, the five rows
  above).

## Owed, and to whom

The five stale rows are driver acts, not agent patches: four `?uiaudit=1&app=…` browser
measurements and wish `task-0003` (rebuild the desk inside the delivered window). The gate
stays red on `freshness-no-stale-rows` until they land; that refusal is the work list.

## Not checked by this pass

The visual appearance of the delivered dialin window after the rebuild (the rebuild has not
landed), and a real click through the SpringBoard tiles in a browser window; the reads above
are loopback HTTP plus the package probe.
