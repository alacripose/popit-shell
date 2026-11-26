# TICKET-0003 — a tool here is not finished until its probe reads its own surface

**State:** open
**Owner:** ala
**Opened:** 2026-11-26

## Requirement

The family rule of 2026-11-23 (`AGENTS.md`, and the mod's `TICKET-0037`), verbatim:

> you will have to create popit uis for the tools that you make this is a new requiremnt for the probes
> that you use to work

A probe that only prints a pass is refused, because a print can say pass while the surface the owner
would read shows nothing. Two tools were added this session and neither ships a surface yet:

| Tool | What it measures today | What it owes |
|---|---|---|
| `tools/tone_probe.py` | decodes each dial-tone WAV to digits and compares them with the roster | a Popit page and `/report.json` listing every row: name, number, played digits, source, and a refusal row for a mismatch |
| `tools/hangup_probe.py` | drives open → hang-up → callback and reads the archive rows | a Popit page and `/report.json` with the line, the callback, the check rows and the refusal code when a hang-up does not read as one |

## Acceptance

- `A1` — `python tools/tone_probe.py probe` starts its own server, fetches `/` and `/report.json`, and
  fails by name unless the page carries `data-popit="tone-probe"` with `id="tone-table"` and the report
  carries its schema plus one row per tone file.
- `A2` — `python tools/hangup_probe.py probe` does the same with `data-popit="hangup-probe"` and
  `id="hangup-checks"`; a missing surface is the refusal `surface-absent`, not a printed pass.
- `A3` — both pages use the family web-dark tokens and put the word for a state beside its colour.
- `A4` — receipts at `artifacts/receipts/tone-probe-popit.json` and `...-hangup-probe-popit.json`.

## Evidence

- `tools/tone_probe.py` and `tools/hangup_probe.py` exist, print, and write receipts. Neither serves a
  page. `A1`–`A4` are therefore unmet, and this ticket stays open by its own rule.
