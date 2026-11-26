# TICKET-0002 — the call desk's copy passes the family prose program

**State:** open
**Owner:** ala
**Opened:** 2026-11-26

## Requirement

The owner's words, verbatim:

> if you're going to use the call line page then you still have to run family prose and secrets checks
> on them and fix the buttons missing text

> you are not allowed to only implement minimal prose checks and gates you must use the full prose
> application from the popit shell

So the desk's copy is measured by `tools/prose_family.py` — the roster, the per-project document, the
window, the probe — and not by a hand-run of `ui_prose.py` that leaves the program's own reading out.
Secrets on the same tree go through `tools/secrets_gate.py`.

## Acceptance

- `A1` — `python tools/prose_family.py report` stages every roster project, the call desk included,
  and writes `docs/prose/popit-shell/inventory.json` with the desk's files in the inventory.
- `A2` — `python tools/prose_family.py probe` passes all nine window and driver checks
  (`prose-window-shows-every-project`, `prose-window-links-every-document`,
  `prose-window-is-in-its-own-mode`, `prose-window-knows-the-driver`, `prose-window-audit-is-measured`
  included).
- `A3` — `python tools/secrets_gate.py --check --all-files --root call-client` reports
  `0 findings`.
- `A4` — every button on the desk's page carries a label (no empty second line under a control).

## Evidence

| Item | Where | Reading |
|---|---|---|
| The desk's copy today | `call-client/` | 31 hits under `ui_prose.py` (from 81), the number that matters is the program's |
| The program's own probe | `tools/prose_family.py probe` | 4 passed, 5 failed: window `0 row(s) for 11 project(s)`, mode `dialin`, `0 document link(s)`, driver `0 staged`, audit `pending` |
| The receipt | `artifacts/receipts/prose-probe.json` | the five named refusals |
| Secrets | `tools/secrets_gate.py` on `call-client` | `0 findings (high 0, medium 0, low 0)` |

## What is not met yet

- `A2` is refused by the program itself: the window reports no rows for 11 projects, its mode is
  `dialin` rather than `prose`, no document links resolve, the driver stages 0, and the audit is
  `pending`. Those five are the work.
- `A1` needs the desk to be read as part of popit-shell's inventory; `report` stages 12 projects, and
  whether the desk's own files are inside popit-shell's inventory is still to be read from
  `docs/prose/popit-shell/inventory.json`.
