# TICKET-0006 — the OpenLock brief's civilian planes

**State:** open
**Owner:** ala
**Authority:** `logs/authority/2026-11-26-dialin-call-and-phone-line.jsonl`
**Source:** `deadlock-model-forge/docs/openlock_thread_consolidated_brief.md`, read in full 2026-11-26

## Requirement

The owner's instruction, verbatim:

> read the docs/openlock_thread_consolidated_brief.md for everything missing from civilians logic for
> the agents

The brief's own requirements, quoted where the requirement is the family's:

> Citizens act independently of the player. The player should also act independently of the citizens.
> Society should be able to develop institutions, rules, work, and memory.

> when testing is complete, they must be handled gracefully so they can exercise their freedom rather
> than being discarded or reset as disposable test fixtures

> Separate planes … Governor Base. Civilians. Contracts. Resumes. Retirement. Tickets. Organizations.

> Verification and certification levels, with Bronze, Silver, Gold, Diamond, and Platinum-like
> progression … Graduation is a terminal transition, not merely a warning or cosmetic label.

> Civilian verification step in which agents live through cadence ticks, jobs, work, courts, and
> learning trees.

## Acceptance

- `A1` — `civilian_scope.py` names every plane the brief requires, each with its status, blocker and
  research question: `resume`, `retirement`, `graduation`, `organization`, `learning-tree`,
  `cadence-ticks`, `materials`, `cells-and-lines`. `civilian_scope.validate()` reports no findings.
- `A2` — a contract names the lane it belongs to, so a resume can be derived per civilian.
- `A3` — `CivilianDesk.resume(lane)` returns the contracts held, the evidence earned, the grade and the
  retirement record.
- `A4` — `CivilianDesk.promote(lane, grade, evidence=[...])` refuses `grade-evidence` with no evidence,
  `grade-name` for an undeclared grade, and `grade-backwards` below the current grade.
- `A5` — `CivilianDesk.retire(lane, reason, evidence=)` records the exit with grade and contract count,
  and refuses a second retirement (`already-retired`) or an empty reason (`retire-reason`).
- `A6` — an operation on a retired lane returns `state: retired`, `allowed: true`,
  `work_allowed: false`, and a directive that says answer but take no work.
- `A7` — the host serves `GET /api/toast/civilian/resume?lane=`, `POST /api/toast/civilian/retire` and
  `POST /api/toast/civilian/promote`, each archiving its row.
- `A8` — `docs/civilians-from-openlock-brief.md` maps every brief section to register rows and to the
  code that carries it, and lists what is still missing without claiming it built.

## Evidence

| Item | Where | Reading |
|---|---|---|
| Register | `civilian_scope.py` | 54 rows: 30 blocked, 8 partial, 13 wired, 1 owed, 2 designed; `validate()` 0 findings |
| Contract attribution | `CivilianDesk.contract(..., lane=)` | row carries `lane`; measured `Qwen` |
| Resume | `CivilianDesk.resume` | `counts {'contracts': 1, 'evidence': 1}`, grade `silver`, retired true |
| Promotion | `CivilianDesk.promote` | `grade-evidence` with no evidence; `silver` accepted; `grade-backwards` refused for bronze |
| Retirement | `CivilianDesk.retire` | keeps grade `silver`, 1 contract, reason recorded |
| Retired operation | `CivilianDesk.operation` | `state retired`, `allowed True`, `work_allowed False`, directive named |
| Routes | `toast.py` | `/api/toast/civilian/resume`, `/retire`, `/promote` |
| Mapping | `docs/civilians-from-openlock-brief.md` | §1 to §4 |

## What is not met yet

- `A7` is measured on the live host: `GET /api/toast/civilian/resume?lane=Qwen` returns
  `{"contracts": 0, "evidence": 0}`; `POST promote` with no evidence is refused `grade-evidence`;
  the same promotion with `artifacts/receipts/hangup-probe.json` records grade `bronze`; `POST retire`
  records the exit; `GET resume` then carries the retirement row.
- `A5`/`A6` revealed a real error: the retire call was made against the live Qwen lane to measure the
  path, which took a working lane off work. `reinstate(lane, reason, evidence)` and its route now exist,
  the retirement is kept inside the reinstatement record, and Qwen is reinstated with the reason named.
  Retirement itself stays terminal for the civilian; only a recorded reinstatement returns one.
- Nothing schedules a civilian's own retirement or cadence: retirement is recorded when someone asks
  for it. The brief's cadence (A-row `cadence-ticks`) is still partial.
- No rule decides what earns a grade. The desk records a promotion with its evidence and refuses to
  invent thresholds, so `graduation` stays partial until the family states the rule.
- No window draws the resume, grade or retirement yet; they are host routes only.
