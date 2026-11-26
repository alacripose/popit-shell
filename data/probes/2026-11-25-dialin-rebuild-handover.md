# Dialin stops being hand-rolled: the rebuild is the CUA driver's work

Date: 2026-11-25. Project: `F:\Documents\popit-shell`. Shell: `python toast.py` (PID 23388),
desk origin `https://<host>:5210`, loopback view `http://127.0.0.1:5207`.

## What the owner retired

The desk carried a private copy of the settings app: `POPIT_THEMES`, `themePaint`,
`paintTheme` (palette table and role writes), keyframes `toast-in`, `panel-in`,
`settings-in`, `settings-pop`, `settings-fold`, `settings-snap`, `settings-sweep`, and its own
settings panel implementation inside `ui/toast.html`. Two corrections fixed the direction:

* *"that setttings app withing dialin is the setting spp baseline, apps subscribe to the
  settings app from the store, it is not a private version of the settings app that dialin has,
  dialin needs to move to the upgraded formats"*
* *"the expectation was that the dialin would stop being handrolled in it's entirety and the cua
  drivers would take ver the work to rebuild the application from the settings app package"*

Agent edits to those private copies are not the rebuild. They were stopped at the second
correction; the remaining work is the driver's.

## The handover, measured

`data/probes/2026-11-25-dialin-rebuild-handover.py` sends one `read` wish over the driver's own
wire (`POST http://127.0.0.1:8765/v1/wishes`) from the Debian box through
`tools/bridge.py run` in `F:\Documents\mc3-client13`; the probe reads its token on the box under
`sudo -n` and never prints it.

| Field | Value |
|---|---|
| driver answer | `accepted` · `wish-accepted` |
| task | `task-0003` |
| receipt on the box | `/srv/scratch/popit-dialin-rebuild.json` |
| derives from | `popit-settings` (the signed settings app package) |
| files named | `toast.html`, `toast.js`, `toast.css`, `package.js`, `contour-theme.css`, `ui-audit.js` |
| regions | `bar`, `status`, `body`, `foot` |
| expected codes | `dialin-handrolled`, `dialin-private-palette`, `dialin-private-motion`, `dialin-private-settings-panel`, `dialin-not-derived`, `dialin-audit-pending` |

`receive_wish` adopts `status|read|question` as a peer-sourced task and never executes a body
tool; a wire peer is not an authority over the driver. So the answer is the handover, not the
rebuild: the rebuild happens on the driver's own schedule with its own tools.

## Stopgaps made before the ruling (recorded as stopgaps)

- `ui/toast.css`: the desk's roles derive from the subscribed `--popit-*` roles; the private
  entry and settings keyframes are gone and the panels carry `surface-motion` from
  `/contour-theme.css`.
- `ui/toast.js`: `data-motion-preference` is the desk's motion control, the retired `popit-ide`
  message branch is gone, and `adoptSignedTheme` takes frame/material/motion/preference from the
  verified document; a changed identity re-reads and repaints.
- `ui/package.js`: `LAYOUT_FLOOR` names `bridge` where the retired `ide` was.
- `settings_package.py`: the layout registry names `bridge`, and a stored layout for an app that
  no longer exists is dropped before it is published.

These make the desk *subscribe*; they do not make it derived. The register keeps saying so.

## The register that keeps it visible

`tools/freshness.py` (Popit page on `http://127.0.0.1:5213`, `data-popit="freshness"`; probe
reads `/` and `/report.json`) covers landing, ci, audits, failures, ledgers, refusals, packages
and tiles, and carries the rebuild as `dialin-rebuild` with the driver act. Latest probe: 7
checks passed, 0 failed, 5 stale — four `audit-*` rows (ui_audit pending on the re-signed
packages, act: driver audit + republish) and `dialin-rebuild`.

## What is owed

- `task-0003`: the rebuild itself, signed as `app-dialin@<rev>` with its files listed.
- The four audits (`?uiaudit=1&app=dialin|bridge|settings|springboard`) and the republish that
  lifts `ui_audit: pending`.
- The gate keeps `freshness-no-stale-rows` red until those land; that refusal is the work list,
  not a passing state being claimed.
