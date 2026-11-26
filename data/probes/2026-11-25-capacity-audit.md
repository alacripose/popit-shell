# The capacity audit: a unit cut for the session's size is refused

Date: 2026-11-25. Owner instruction, verbatim: *"if you keep refusing to do work or cut down
on work because of context/capacity/session leght or assumed time then you will have to look
for those failurs so the cua driven harness development will refuse those behaviors"*.

## Why a tool rather than a reminder

Three units this session were measured, then left without their records, their re-verification
or their probe document, and the reason given each time was the size of the session. That is a
reason the harness can read: it is written into authority rows and probe notes, which is where
decisions live. So the refusal is mechanical.

## What is measured

`tools/capacity_audit.py` scans `logs/authority/*.jsonl`, `data/probes/*.md` and `docs/*.md` for
the phrases a session uses when it stops for its own size (`context length`, `context window`,
`session length`, `remaining capacity`, `out of time`, `token budget`, `next turn`, `too long
to`, `for now stop`). A line quoting the rule (`verbatim`, `owner's rule`, `the rule`) is not a
hit, because the rule has to be readable where it governs.

| Surface | Contract |
|---|---|
| `GET /` on `http://127.0.0.1:5220` | `data-popit="capacity-audit"`, `id="capacity-state"`, `id="excuse-table"`, `id="receipt-path"` |
| `GET /report.json` | `popit.capacity/1`, `scanned == ["authority","probes","docs"]`, `rows[]` with `state` and `digest` |
| `artifacts/receipts/capacity.json` | the same reading, on disk |
| `python tools/capacity_audit.py probe` | starts the server, reads both, fails by name |

A hit is either `acknowledged` — `logs/capacity/ack.jsonl` names the unit that still owes the
work, which is how a cut is allowed — or `refused`. The gate carries
`capacity-audit-covers-the-records` and `no-unacked-capacity-excuse`, so a refusal fails
`python tools/gate.py` by name.

## Measured in this unit

- `python tools/capacity_audit.py report` over the current records: `0 refused, 0 acknowledged`
  for the phrases it matches, so the mechanism is present and the records are clean on it.
- `python tools/capacity_audit.py probe`: read the page and the served report over loopback;
  the row set is the printed report, and the unacked-excuse row is clean.
- `tools/gate.py` runs both legs with the other checks.

## What this does not decide

The audit cannot see a decision that was never written down. It makes the written reason
refusable and leaves a receipt; a session that cuts work silently still has to be caught by the
freshness register's missing acts. The two are meant to be read together.
