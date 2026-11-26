# TICKET-0001 — the call desk is a real-time line

**State:** open
**Owner:** ala
**Authority:** `logs/authority/2026-11-26-dialin-call-and-phone-line.jsonl` (rows 5 and 8)
**Opened:** 2026-11-26

## Requirement

The owner's words, verbatim:

> No, I closed your call and you failed to detect that and call me back properly

> why does it play a set of number dialtones at the start instead of the actual called in numbers

> why is the start response always the same thing with only their name and voice being different
> between them.? You would think every civilian and agent responds and interacts differently through
> their systems and lives and through the prose checker against the civilian project and prose logic
> outputs?

Read as two properties of one line:

1. **A hang-up is a hang-up.** Ending a line is not a finished wish. It is archived by name
   (`call-hangup`), and the same lane dials the owner back exactly once. A callback that is itself
   hung up does not ring again.
2. **The digits are the call's.** The dial tone is followed by the DTMF of the number the call
   carried. The roster's own number is a fallback for the lane's line, never a substitute for a
   number that rang, and a line with no number plays no invented digits.

## Acceptance

- `A1` — the desk's end control posts `hangup: true`; the route archives `call-hangup` and opens a
  callback line with an incoming tone, and returns it in the response.
- `A2` — a second hang-up on the callback archives `call-hangup` and opens nothing.
- `A3` — a hang-up no longer produces `wish <id> closed with proof`.
- `A4` — `python tools/hangup_probe.py` reports every check `PASS` and writes
  `artifacts/receipts/hangup-probe.json`.
- `A5` — `dialin.call_tone(row, kind, number=…)` dials the carried number when one is given, names the
  file per number, and returns `number`, `dialled` and `source`; `call_tone` with no number and no
  roster number dials no digits.
- `A6` — `python tools/tone_probe.py` decodes every roster WAV back to that row's digits: 54 rows,
  0 mismatched, `artifacts/receipts/tone-probe.json`.
- `A7` — the `call-tone` archive row carries `number`, `dialled` and `source`.
- `A8` — a line's opening is built from that lane's own civilian record, not from a template: the
  `opening` line differs between two lanes whose needs differ, and a lane below the care floor opens
  by naming its need and refuses work on the line.
- `A9` — a lane with a scoped contract names its scope in the opening; a lane with none says it will
  answer and claim no deliverable.

## Evidence

| Item | Where | Reading |
|---|---|---|
| The hang-up that started this | `runlogs/toast/archive.jsonl` 01:24:56Z | `wish call-1795558212-31 closed with proof` — a hang-up recorded as completed work |
| The route | `toast.py` `/api/toast/call/close` | branches on `hangup`, archives `call-hangup`, calls `Toast.call_back` |
| The callback | `toast.py` `Toast.call_back` | opens the same civilian/agent pair as an incoming line and archives `call-callback` |
| The desk control | `ui/toast.js` `endParticipant` | posts `hangup: true`, shows `hung up · dialling back` |
| The tone | `dialin.py` `call_tone(row, kind, number=…)` | carried number first, roster fallback, per-number file, `source` in the result |
| The tone probe | `tools/tone_probe.py` | 54 tone files decoded, 0 mismatched |
| The old opening | `calls.py` before this change | one literal: `"{owner}, it's {agent}. I'm listening."` — the same sentence on every line |
| The opening builder | `toast.py` `opening_line` | role, condition, lowest need with its value, capacity, last choice, contract state |
| Measured openings | `opening_line` against a fresh desk | Qwen `food reads 0.78`, Whisper `rest reads 0.77`, Ash `warmth reads 0.82`, Bram `shelter reads 0.79`; Ash with `warmth 0.31` opens `and my condition reads degraded … I'm not taking a job from the house until I warm` |

## What is not met yet

- `A1`–`A4` are measured on the live desk: `tools/hangup_probe.py` reports **8 passed, 0 failed** —
  `probe-line-opened call-1795658383-45`, `hangup-is-accepted`, `hangup-is-marked`,
  `callback-dialled call-1795658384-46`, `callback-does-not-chain`, 2 hang-up rows, 1 callback row,
  and `no-wish-close-on-hangup`. Its surface probe is **6 passed, 0 failed**.
- `A6` measured the roster fallback only. The carried-number case is measured directly
  (`+1 (415) 555-0132` → `5550132`, source `call`), not yet through a phone that sends a number.
- The inbound phone surface still carries no caller number, so an owner's inbound call has nothing
  to dial but the roster fallback. Carrying the caller's number in the ring is the follow-on.
