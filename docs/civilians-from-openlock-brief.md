# What the OpenLock brief asks of civilians, and what the desk still lacks

**Source:** `deadlock-model-forge/docs/openlock_thread_consolidated_brief.md` (compiled 2026-11-18, 1197 lines), read in full on 2026-11-26.
**Register:** `civilian_scope.py`, 54 rows after this pass (30 blocked, 8 partial, 13 wired, 1 owed, 2 designed).
**Rule:** a row moves only on its own evidence. Nothing here is claimed as done because the brief asks for it.

## 1. The brief's civilian doctrine, in its own words

| Brief | What it requires | Register rows |
|---|---|---|
| §3.2 | Citizens act independently of the player; the player is an independent actor too; society develops institutions, rules, work and memory; production has causal steps; history is kept as evidence | `work-lifecycle`, `life-steps`, `organization`, `materials`, `memory-episodic` |
| §12.3 | Multi-step work, conserved material economy, citizens create institutions and governance, a living society rather than decorative population | `materials`, `organization`, `office`, `work-lifecycle` |
| §12.4 | Persistent citizens with identity, memory, embodiment, continuity; **never stateless**; when testing is done they are *"handled gracefully so they can exercise their freedom rather than being discarded or reset as disposable test fixtures"* | `durable-identity`, `retirement`, `memory-*` |
| §13.1 | Paper is evidence, not authority | `deterministic-verification`, `decision-ledger` |
| §13.2 | Separate planes: Governor Base, Civilians, Contracts, Resumes, Retirement, Tickets, Organizations — not merged for convenience | `resume`, `retirement`, `organization`, `ticket-evidence` |
| §13.3 | Verification grades (Bronze → Platinum); graduation is a terminal transition; a refusal is a valid outcome | `graduation`, `closed-world` |
| §13.4 | Civilian life is an Axis star: agents live through **cadence ticks, jobs, work, courts and learning trees**; institutions arise through participation | `cadence-ticks`, `violence-court`, `learning-tree`, `apprenticeship` |
| §17.7 | Connections must matter to inhabitants: where people live, work, travel, meet, trade, create and remember | `cells-and-lines`, `relations`, `commitments` |
| §6, §17.5 | Cells and lines: a civilian, package or world is a locally coherent cell; calls, contracts and routes are lines between them | `cells-and-lines` |

## 2. What the desk carries after this pass

| Plane | Code | Status |
|---|---|---|
| Needs, care floor, failure ladder | `civilian_features.py` (`life_tick`, `operation`) | wired |
| Contract, seven fields | `CivilianDesk.contract(fields, call=, lane=)` | wired, now attributed to a lane |
| Decisions, confidence gate, duration chain | `decide`, `verify`, `duration` | wired |
| Work lifecycle, life steps | `life_tick`, `life_apply`, `life_steps` | wired |
| **Resume** | `resume(lane)` → contracts held, evidence earned, grade, retirement | partial: derived, no page |
| **Retirement** | `retire(lane, reason, evidence=)`; a retired lane's `operation` returns `work_allowed: false` | partial: recorded, nothing schedules it |
| **Grades / graduation** | `promote(lane, grade, evidence=[...])`, grades `bronze…platinum, graduated`, refuses without evidence and refuses backwards | partial: no rule for what earns a grade |
| Lane opening lines | `toast.opening_line` reads role, condition, lowest need, capacity, contract state | wired |
| Call line integrity | hang-up → `call-hangup` → one callback; `call_tone` dials the carried number | wired (drill pending a free desk) |

## 3. What is still missing, in the order the brief argues for it

1. **Durable identity (`durable-identity`, blocked).** A lane is a name string in `civilians.json`; its life is keyed by that name. Renaming a lane or losing the store loses the person. The brief wants one identity across session, process and body replacement.
2. **Cadence (`cadence-ticks`, partial).** `life_tick` runs when a call arrives, so an idle civilian stops living. The brief's cadence means the record advances whether or not anyone watches, with a tick receipt.
3. **Memory planes (`memory-*`, 6 blocked).** Working, episodic, semantic, procedural, social and autobiographical memory are named and absent. Nothing a lane does today is remembered as an episode with participants and an outcome, which is also why the desk cannot answer "what did you do last week".
4. **Social record (`relations`, `commitments`, `office`, `organization`, blocked).** A civilian has no relationships, debts, promises or membership. `office` is declared in the register and nothing implements it; `organization` is new in this pass.
5. **Learning tree (`learning-tree`, blocked).** `apprenticeship` names skill transfer; there is no prerequisite graph, no node state, no verified unlock.
6. **Materials (`materials`, blocked).** Work counts jobs; nothing is consumed or produced, so a deliverable costs nothing and nothing the brief calls causal economy exists.
7. **Extended needs (`extended-needs`, blocked).** Social contact, belonging and purpose are declared as needs and not modelled; five needs are all there is.
8. **Court (`violence-court`, blocked).** The brief puts courts inside civilian life. There is no act vocabulary and no finding record.
9. **Cells and lines (`cells-and-lines`, designed).** The desk draws lines between lanes but no record calls a lane a cell or a call a line.
10. **Grades without a rule (`graduation`, partial).** The record exists; what observations earn a grade is undecided, and the desk refuses to invent a threshold.

## 4. Honest position

The desk now records a resume, a grade earned on named evidence, and a retirement that keeps the record and refuses work while still allowing the lane to speak. Everything else in §3 is registered as blocked or designed with its blocker and research question, and none of it is claimed as built.
