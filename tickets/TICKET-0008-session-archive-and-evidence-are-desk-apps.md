# TICKET-0008 — the session archive and the evidence backup are desk apps

## Requirement

Owner, verbatim: *"update the legacy shell evidence backup and session archive apps into real
popit-shell desk apps created from the subscribed mutated settings window baseline and project
setup baseline"*, with the icon frame signed, no security lowered from https, development in the
client harness, a launch proved over the desk, the family prose gate and secrets gate passed, and
ticket, refusal, failure, error, ledger and CI plus landing tracking kept by the CUA agents.

The legacy shell served one loopback page, `ui/archive.html`, which polled `/api/toast` on a
server that never answered it, and the shell's server pointed `/api/archive/*` at functions that
had been dropped. It is replaced by two windows built from the settings package's signed
delivery and the pinned project setup: `archive` (the session archive) and `evidence` (the
evidence backup).

## Acceptance

- **A1** — `app_package.APPS["archive"]` and `APPS["evidence"]` are kind `window`, entry
  `toast.html`, delivered in `popit-settings-package`, and their payload carries the mutated
  subscription plus `project_digest`.
- **A2** — each window signs its icon frame only with a proven launch:
  `launch_proof().ok` is true for `/toast.html?window=archive` and `?window=evidence`, and the
  SpringBoard paints a tile only while that identity verifies.
- **A3** — the windows are delivered over the desk's pinned TLS origin
  (`https://127.0.0.1:5211/toast.html?window=…`); the shell's archive window loads that origin,
  and a desk that does not answer is a named refusal, never a bare-http page.
- **A4** — a fixture project proves the copy and the cache rule: source and record files are
  copied, a 9 MB asset is recorded by size and time, a clean lists before it removes, and it
  removes only the four family cache trees.
- **A5** — every act that cannot be shown is refused by code: `archive-unknown-project`,
  `archive-backup-none`, `archive-path-outside`, `archive-clean-confirm`,
  `archive-legacy-retired` and the rest, answered 409 or 410.
- **A6** — the program writes its own rows: `runlogs/session-archive/ledger.jsonl` per act and
  `logs/authority/2026-11-26-session-archive-apps.jsonl` for the unit.
- **A7** — `python tools/app_package_probe.py` (21 passed),
  `python tools/session_archive_probe.py` (19 passed, 0 failed, 2 blocked),
  `python tools/secrets_gate.py --check` (0 findings) and `python tools/landing.py --check`
  pass. `python tools/gate.py` reports 86 checks with two refusals it names:
  `freshness-no-stale-rows` (the six audits are still pending) and `family-prose-ratchet`
  (the family-wide regression receipt, which predates this unit). Neither is edited to pass.

## Evidence

- `tools/session_archive_probe.py` · receipt `artifacts/receipts/session-archive.json`
- `runlogs/session-archive/ledger.jsonl` · `artifacts/receipts/window-audit.json`
- `docs/app-store.json` (built by `tools/app_store.py` from the signed registry)
- `logs/authority/2026-11-26-session-archive-apps.jsonl`

## State

`open`. The signing, the launch proof, the fixture measurement and the gate pass. The window
capture that closes A3 is a CUA driver act on this machine: `python tools/window_audit.py
report` in the delivered window, then a `screen.capture` of the desk on each mode. No capture is
recorded yet, so the ticket is not closed.

## Handover

The desk that was serving these packages was an older process holding 5207–5211, so every
edited file read as `app-tampered`. It was ended, a clean desk was started through
`tools/desk_launcher.py`, and all six packages re-signed: `archive` and `evidence` at revision 1
with `launch_proof.ok` true and their modes named, the four existing packages republished.
`docs/app-store.json` was rebuilt from that registry (6 packages, 1 refused — the foreign
bridge). Acknowledged in `logs/authority/2026-11-26-session-archive-apps.jsonl`.

The two apps' refusals were being written to `runlogs/session-archive/ledger.jsonl` and read by
nobody: `tools/family_failures.py` did not scan that directory, and a row that named a refusal
did not say it was one. Both are fixed (`runlogs/session-archive/*.jsonl` in the sweep's globs;
`result: refused` on a named row), so the family register now counts `archive-unknown-project`
and `archive-backup-none` against this project instead of passing them over as plain acts.

## Launch and audit, in the desk's own window

The audit that signs an app is the measurement its window makes of itself. A page opened beside
the app is not that window, so the standalone measurement was withdrawn. `toast.py` now takes
`--window-route`, which opens the desk's single view at a route the family names in
`WINDOW_AUDIT_ROUTES` (anything else is refused `not-a-window-route`), and the page posts its
own audit. Each of the six packages was measured that way over `https://127.0.0.1:5211` with the
desk certificate pinned: archive 06:15:41Z, evidence 06:17:31Z, dialin 06:19:21Z, settings
06:21:20Z, prose 06:23:04Z, springboard 06:24:55Z (the SpringBoard is measured in the frame the
window delivers, through `springboardAudit`), at 1007x604 with no findings. The desk's own view
grab is kept as `artifacts/receipts/<app>-window.png`.

A failed window load is now retried three times with a backoff and then reported; the desk no
longer exits because its page did not load. The window origin's TLS handshake moved to the
connection, one per worker thread: a client that refuses the certificate is refused per
connection instead of holding the accept loop the desk's own view needs. Measured: 40 failing
handshakes against 5211, same desk pid, `/api/toast` still 200.

## Prose ratchet, measured not edited

`python tools/gate.py` reports 87 checks with one refusal, `family-prose-ratchet`. The shared
checker fails 12 of 12 projects. popit-shell's 33 named hits are all `label-invented` (Popit
Family, Import JSON, Export JSON, Refresh Debian, HTTP READ ONLY, ANSWER WITHOUT SHARING, ...)
and two `structure: emoji`; none names archive or evidence. Each project carries a
`prose-baseline.json`, but none of them has keys for `label-invented` or `copy-unrequested`, so
the checker reads every one of those as a regression (`copy-unrequested 0 -> 5303`). Passing
this check means repairing that copy across the family, which the baseline cannot be re-cut to
hide.

## Measured hazard

A measurement window in its own process was tried for the pending audits. Its first attempt
refused the desk certificate while the certificate-error handler was still wrong, and Chromium
retried the handshake in a storm against `127.0.0.1:5211`; the desk's own view then failed to
load `https://127.0.0.1:5211/toast.html?v=1`, and `toast.py` exits when its window fails to
load (`toast-view loaded=False`, then `toast.stop()`). The desk was restored and the measurement
tool was deleted rather than kept as a second way to kill the desk. Two facts worth acting on:
**the desk exits on a transient failure to load its own page**, and **one rejected-certificate
client can starve the window origin enough to cause it**. Neither is changed here; both are
outside this unit's subject and belong in their own ticket.

## Supersession

Replaces the retired `ui/archive.html`, `ui/archive.js` and `ui/archive.css` page and the
`/api/archive/*` routes that answered it.
