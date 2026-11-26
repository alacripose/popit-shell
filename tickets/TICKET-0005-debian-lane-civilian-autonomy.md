# TICKET-0005 — the Debian lane stands on its own civilian record

**State:** open
**Owner:** ala
**Opened:** 2026-11-26

## Requirement

The owner's words, verbatim:

> the qwen machine can't do development by itself entirely yet since you still haven't given it it's
> full civilian autonomy

So the lane that answers from the Debian box is not a chat endpoint attached to a line. It is a
civilian with a record: a C9 condition and needs, a care choice before work, a seven-field contract
before it accepts anything, and a preflight that lets it speak but refuse work. The box reads its own
record and answers inside it; the host does not describe the lane to it.

## Acceptance

- `A1` — `bridge_turns` returns the lane's `context` and `life` from `civilian_features.CivilianDesk`,
  so the box receives its own C9 paragraph with each poll.
- `A2` — `bridge_say` runs `CivilianDesk.operation` before a line is spoken: a dead lane or an
  incomplete contract refuses by code, and the response carries `state`, `work_allowed`, `condition`
  and `care_line`.
- `A3` — `~/.dialin/driver.py` puts that paragraph into its system prompt and logs the `civilian`
  block for every line it speaks.
- `A4` — a spoken line on the Qwen lane shows `civilian.state` in the box's `driver.log`, and the
  archive row exists for it.
- `A5` — a contract with a missing field is refused `contract-incomplete` at the box, not at the host.

## Evidence

| Item | Where | Reading |
|---|---|---|
| The desk | `civilian_features.CivilianDesk.operation` | condition, needs, care, contract state, `allowed`, `work_allowed`, `directive` |
| The turns | `toast.py bridge_turns` | returns `context` and `life` |
| The say | `toast.py bridge_say` | preflight before speech; refusal raises the desk's code |
| The box | `tools/dialin_driver.py` | `grounding` into the system prompt; `civilian` in the join/say log |
| The lane today | `call-1795577129-34` | session `callbridge-4e7ab2e6a9232e02`, 298 tells, joined after the route learned the lane's enrollment name |

## What is not met yet

- `A1`–`A3` are coded and pushed to the box; `A4` needs one spoken line after the current shell
  restart, and `A5` needs a contract with a field removed to be offered to the lane.
- The lane has no feeling-wheel name yet (`CivilianDesk.name` is unset), so its identity row is the
  enrollment name only. Naming it from a model answer without a real probability is refused by the
  desk (`feeling-unattributed`), which is why it stays unnamed rather than guessed.
