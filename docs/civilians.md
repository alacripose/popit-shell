# Civilian systems in Popit

**The page is retired.** `/civilians.html` is no longer served, the call desk no longer
links it, and the Springboard has no Civilians tile. The separate assistant, driver and
civilian buttons are retired too: they described a lane relationship the family does not
have, and a button that is not an action on the live call is a miscount of how civilians
work. What remains is the record itself, readable at `/api/toast/civilians` and written
through `POST /api/toast/civilian/name`; the call desk shows the lanes, the shared document
and the real voice state.

The civilian record is the family's lived layer inside the Popit toast. It does not replace
the language model or the Freebuff harness. It gives a lane an identity, a measured decision
surface, a contract, five needs and a life state that the agent carries into a call.

## What is wired

| Feature | Family evidence | What it does in Popit |
|---|---|---|
| `feeling-wheel-identity` | `laya-cua-agent/agent/wheel.py`, `naming.py` | A primary, secondary and tertiary feeling becomes the lane name, path and colour |
| `typed-choice` | `agent/questions.py`, Von `Choice` | One named option plus its measured confidence |
| `noul-condition` | `agent/questions.py`, Von `Noul` | A yes/no answer may be a probability, never prose |
| `ordinal-score` | `agent/questions.py`, Von `Score` | A number on an ordered scale |
| `confidence-gate` | `von.patterns.confidence_gate` | `automatic` at 0.80 or above; `escalate` below it |
| `decision-ledger` | `agent/laya_brain.py` | Every decision is retained with its later ground truth |
| `seven-field-contract` | `gov/model.py` `ContractEnvelope` | Mission, scope, constraints, resources, evidence, deliverable, stop |
| `deterministic-verification` | `agent/loop.py` verify | A confident answer is not a result until a check agrees |
| `per-lane-memory` | `agent/loop.py`, `mind_bridge.py` | Each lane answers from its own identity and state |
| `chain-of-options` | Von chains, `add_duration` | Durations and dates have deterministic provenance |
| `closed-world-refusal` | Von model card | English-only and out-of-domain questions are named refusals |
| `mood-after-work` | `agent/loop.py` `_record_mood` | A fresh feeling can follow a closed contract |
| `five-needs` | `openlock_modern/tools/cua_civilian.py` | Food, rest, warmth, health and shelter decay on one cadence |
| `needs-first-care` | `cua_civilian.choose` | Care is chosen before an offered job below the SEEK floor |
| `failure-ladder` | `cua_civilian.condition` | `ok`, `degraded`, `illness` and `dead` are named states |
| `work-decline-delegate` | `cua_civilian.choose` | Work can be planned, declined once, delegated or completed with evidence |
| `life-steps` | `cua_civilian.steps_for` | A life decision becomes a declared marker or body step |

The C9 module is loaded from the family checkout, not copied into this repository. The
adapter looks for `C:/Users/ala/Documents/openlock_modern/tools/cua_civilian.py` first and
then `F:/Documents/openlock_modern/tools/cua_civilian.py`.

## Decisions

`POST /api/toast/civilian/decision`

```json
{
  "lane": "Ash",
  "kind": "choice",
  "question": "Which work comes next",
  "answer": "write the note",
  "confidence": 0.83,
  "act": 0.83
}
```

The response carries `gate`, `state`, `threshold`, `confidence` and `act`. The ledger is
`runlogs/toast/civilians.json`. A decision can be checked later with
`POST /api/toast/civilian/verify`:

```json
{"index": -1, "ground_truth": "the note exists", "passed": true, "detail": "file checked"}
```

A failed numeric input, an unsupported feeling pair, a missing contract field, a non-English
question and an out-of-range score are refusals with a code, not a 500.

## Contracts

`POST /api/toast/civilian/contract` accepts exactly the seven fields. `scope`,
`constraints` and `evidence` are non-empty lists; `resources` is a non-empty object.
`POST /api/toast/call/open` may include the same object in `contract`; the call row keeps it.
The full `popit.civilian-contract/2` design, including parties, region, action vocabulary,
ownership, expiry, breach, parent narrowing, tickets and lifecycle states, is in
[`civilians-contracts.md`](civilians-contracts.md). It is deliberately marked non-routable:
the scope rows name the missing store and tests instead of pretending the seven fields are
the whole contract.

When a lane answers inside a call, `ToastMind.ask_mind` adds this to its persona:

- the lane's feeling identity, if one is recorded;
- its C9 condition and five needs;
- the care floor (`0.62`) and the deterministic-check rule;
- the call's mission, scope and stop fields, if a contract was attached.

That is the logic change: the agent no longer answers as a generic voice when a civilian
state exists. It answers as the lane, and it must name care before new work when a need is
below the floor.

## Life and care

`GET /api/toast/civilian/life?lane=Ash` reads or creates one lane's C9 state.
`POST /api/toast/civilian/life/tick` decays needs and returns the chosen decision;
`apply_care: true` applies a care decision immediately. `POST /api/toast/civilian/life/apply`
applies a returned decision, and `POST /api/toast/civilian/life/steps` turns it into declared
steps. The basic desk still exposes **Tick** and **Apply care** per lane; the scope register is
not another interaction view.

## Every speaking turn is gated

The features meet the agent at `CivilianDesk.operation`, before `DebianMind.ask` is called.
For each lane on a live call, `toast.ask_mind` now asks for a preflight that:

- reads that lane's own C9 state and the failure ladder;
- runs `cua_civilian.choose`; a need below 0.62 becomes a **care-first** turn and the lane is
  told not to accept, plan or claim new work;
- refuses a dead lane before the model is called (`civilian-terminal`);
- allows speech from an ill or degraded lane but sets `work_allowed: false`;
- refuses an incomplete attached contract (`contract-incomplete`);
- tells the lane its exact mission, scope, stop and evidence, and that an absent contract can
  never claim a deliverable;
- records the operation in a persisted ledger, then attaches the answer with an **unverified**
  gate because the local model does not return a calibrated probability. A task claim is not a
  result until an observed machine check agrees.

`GET /api/toast/civilians` returns the last operations under `civilians.operations`. This is
the behaviour record, not a feature gallery. Alacrity is the owner on the line; the agent
lanes are Buffy, Qwen, Whisper, Ash and Bram.

## Full scope and named blocks

`civilian_scope.py` is the complete register, not the 17-feature shortcut. It has 46 rows
across being, life, memory, social, governance and call. Each row carries:

- `status`: `wired`, `partial`, `designed`, `blocked` or `owed`;
- the exact family `evidence` path and section;
- the Popit `surface` or `none`;
- a `blocker` for anything not wired;
- a `research` question for anything blocked, partial or owed.

The first full register is **13 wired, 7 partial, 1 designed, 24 blocked and 1 owed**. The
25 blocked/owed rows are not deleted from the design; they are returned by
`GET /api/toast/civilians/scope` and documented here and in `civilians-contracts.md`. They
are not a separate interaction view. The suite refuses a blocked row without a blocker or a
research question (`civilian_scope.validate`).

The current 17-row feature register is a subset and its states now come from this scope. In
particular, `deterministic-verification` and `per-lane-memory` are `partial`;
`mood-after-work` is `designed`; `seven-field-contract` is `partial` because it has the
governance fields but not the V4 §12.4 material fields or parent/child narrowing. Calling all
17 `wired` was the overclaim this register corrects.

## Coverage and its limit

The audit at `tools/civilian_audit.py` scans the family Documents roots plus Popit, Laya,
Portal, Brass Meridian, Income Engine, AWA3D and Openlock. Its latest run covers 3,886
files, 618 code files, 2,648 documents and 16 PDFs; 2,169 files match civilian, agent, voice,
call or CUA terms. The report embeds the 17-feature register and the 46-row scope, and the
probe checks both plus the agent preflight.

The broad family document `agent_god_files/reference/CIVILIANS.md` also describes
ensoulment, violence, office, death and estate. Those are in scope for the audit inventory,
but Popit does not claim a complete simulation of them. The working register covers the
identity, decision, contract, need, care, failure, work and life-step surfaces that have a
concrete family implementation. Adding a new surface requires a feature row, a route or a
call-grounding rule, and a receipt; a document mention alone is not counted as wired.

## Reproduction

```sh
python tools/civilian_audit.py scan --max-files 12000
python tools/civilian_audit.py probe --port 5311
python tools/gate.py
python -m py_compile civilian_features.py toast.py calls.py
node --check ui/civilians.js
curl -s http://127.0.0.1:5207/api/toast/civilians
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5207/civilians.html
```

The last live receipt for the desk is under `runlogs/civilian-audit/`; the Toast receipt is
`GET /api/toast`.
