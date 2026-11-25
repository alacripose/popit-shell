# Civilian contracts: full design and blockers

The implemented route is `POST /api/toast/civilian/contract` with the seven governance
fields. That is a **base contract**, not the full social contract in the family design.
The full design below is `popit.civilian-contract/2`; it is deliberately not routable yet.

## The object

```json
{
  "schema": "popit.civilian-contract/2",
  "id": "contract:...",
  "parent": "contract:... or empty",
  "parties": [
    {"lane": "Ash", "role": "worker"},
    {"lane": "Bram", "role": "supplier"}
  ],
  "mission": "one bounded sentence",
  "scope": ["named operation or place"],
  "constraints": ["a boundary that cannot be widened"],
  "resources": {"minutes": 20, "items": {"oak_log": 2}},
  "ownership": {"before": "family", "after": "family", "custody": "Ash"},
  "actions": ["move", "gather", "deliver"],
  "region": {"kind": "site", "ref": "site:..."},
  "starts_at": "ISO-8601",
  "expires_at": "ISO-8601",
  "renewal": "none | owner-approval",
  "success": ["an observable condition"],
  "failure": ["an observable condition"],
  "breach": ["the boundary that was crossed"],
  "termination": ["who may stop it and what is recorded"],
  "evidence": ["artifact or event reference"],
  "deliverable": "the thing that closes the contract",
  "stop": "the condition that stops work immediately",
  "ticket": "ticket:... or empty",
  "validation": {"state": "unverified | passed | refuted", "ref": ""},
  "state": "proposed | active | suspended | breached | closed | retired",
  "created_at": "ISO-8601"
}
```

## What each family source requires

| Field group | Family source | Why |
|---|---|---|
| mission, scope, constraints, resources, evidence, deliverable, stop | Laya `gov/model.py` `ContractEnvelope` | The seven governance fields already wired |
| parties and roles | V4 §12.4 | A contract names who is bound |
| region/target set | V4 §12.4 | Work has a bounded place |
| allowed action vocabulary | V4 §12.4 | Authority is an action set, not a mood |
| resource budget and ownership | V4 §12.4 | Custody and consumption are not implied by a role |
| start, expiry and renewal | V4 §12.4 | A term is part of authority |
| success, failure, breach, termination | V4 §12.4 | Closing is evidence, not a claim |
| parent contract | V4 §12.4; CIVILIANS §3.6 | A child may only narrow |
| ticket, evidence, validation | V4 §12.2, §23.6 | The contract is not the execution receipt |
| office, term, vacancy | CIVILIANS §3.6 | An office is a named scope with a holder and term |

## Narrowing rule

For a child contract with parent P:

1. every child scope item is a member of P's scope, or a declared refinement of one;
2. every child action is in P's allowed action vocabulary;
3. every child resource is less than or equal to P's remaining budget;
4. the child expiry is at or before P's expiry;
5. the child region is inside P's region;
6. the child cannot add a party that P did not authorize;
7. the child cannot widen ownership or custody;
8. the child's termination cannot remove P's stop condition.

A violation is a named refusal (`contract-widen`), not a silently clamped field. The child
never mutates the parent.

## Lifecycle

| State | Allowed transition | Evidence |
|---|---|---|
| `proposed` | to `active` by the bound authority | offer + acceptance |
| `active` | to `suspended` by conviction/bond/owner; to `breached` by a finding; to `closed` by validation | separate records, never a field mutation |
| `suspended` | back to `active` only by the declared revocation rule | suspension row retained |
| `breached` | to `closed` or `retired` | finding + disposition |
| `closed` | to `retired` only | validation receipt |
| `retired` | terminal | kept and superseded, never deleted |

## Why this is not routable yet

- `civilian_scope.py` row `social-contract` is `partial`: the seven-field route exists, the
  material fields and narrowing do not.
- `subcontract-narrowing` is `blocked`: no parent/child store exists.
- `ticket-evidence` is `partial`: calls have archive rows, not ticket/validation records.
- `office` is `blocked`: no office record, term, vacancy or suspension exists.

The research questions are in the scope rows. A future route must add a migration and a
negative test for every narrowing rule before it can move out of `blocked`.
