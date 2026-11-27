# Family Axis — nine-part suite evidence map and anti-reduction contract

**Status:** Source-backed audit and proposed family DevKit requirement. This document names the current nine-part Axis vocabulary and the distinct star/ladder/count systems found across the family. It does not claim the proposed DevKit enforcement is implemented.

## 1. Canonical distinction

The current formal Axis vocabulary is **nine typed axes / ladders**. The machine-readable identifiers are:

1. evidence_grade
2. certification_tier
3. procedural_gate
4. grade
5. org_rank
6. support_level
7. ticket_evidence
8. prose_kind
9. establishment

In the current Shploingus source this is AxisKind::ALL, AXIS_COUNT = 9, and one total coverage table. The names, token sets, and sources are declared in crates/voxel-model/src/axis.rs. The separate crate crates/axis/ladder re-exports that one declaration and has a test named the_layer_has_nine_ladders_and_every_one_has_a_coverage_row.

The owner's phrase **nine-star suite** is retained as a human-facing description of the full Axis suite. The canonical schema and implementation language must say **nine axes / nine ladders**, not a single nine-star score or a nine-rung ordinal. A user-facing alias must never change the typed contract.

## 2. The nine members and their provenance

| # | Axis identifier | What it asks | Declared values | Source declared by the current coverage table |
|---:|---|---|---|---|
| 1 | evidence_grade | How strong the evidence for a claim is | A, B, C, D | godplan/axes.py, EvidenceGrade, rule 19.1 |
| 2 | certification_tier | Which threshold band is satisfied across the whole requirement vector | bronze, silver, gold, diamond, platinum | godplan/axes.py, CertificationTier and TIER_REQUIREMENTS |
| 3 | procedural_gate | The statuses of named predicates under an action policy | PASS, FAIL, NOT_APPLICABLE, EXPIRED, BLOCKED | godplan/axes.py, GateStatus over ProceduralGate predicates |
| 4 | grade | A unit's own progression rung | F, E, D, C, B, A, S, SS, SSS | godplan/axes.py, Grade, GRADE_ORDER, rule 19.2 |
| 5 | org_rank | A person's office grant/rank in an organisation | applicant, associate, member, senior_member, lead, manager, senior_manager, director, senior_director, vice_president, senior_vice_president, chief_operating_officer, president, chief_executive_officer | godplan/axes.py and organizations.md rules 101–108 |
| 6 | support_level | How directly an assertion is supported | direct, strongly_supported, supported, inferred, self_reported, unverified | ala-system evidence/support.ts, EvidenceLevel; registered, not redefined here |
| 7 | ticket_evidence | How the cited evidence came to exist | A, B, C, D | voxel-model ticket EvidenceOrigin, sourced from ala-cities gov Evidence; D is this tree's additional mechanical-derivation rung |
| 8 | prose_kind | What kind of statement a prose unit makes | definition, obligation, prohibition, permission, fact, principle, condition, procedure | agent_god_files/prose_logic claim AtomKind; eight labels without an order |
| 9 | establishment | What an instrument found when a subject was checked | active, inactive, stale, unchecked, refused | Shploingus axis.rs; moved from voxel-package features.rs, where the census/feature states already existed |

**Important semantic constraints:**

- These are different types and different questions. Identical spellings do not make values interchangeable. In particular, evidence_grade A, grade A, and ticket_evidence A have different meanings.
- certification_tier is evaluated as a threshold over all requirements up to that band. It is not max(evidence_grade). A strong claim cannot conceal three unresolved critical requirements.
- procedural_gate is a set of named predicates and their statuses. Flattening it to one generic green/red flag loses which predicate failed.
- grade has nine rungs, but that does not make the Axis set eighteen or nine ordinal stars. It is one ladder among the nine.
- org_rank's highest office is reached through election; it is not a routine numeric promotion.
- support_level's token set is declared here, but the current source explicitly says its original ordering belongs to ala-system support.ts and has not been re-derived in that build. Do not invent a ranking or numeric mapping.
- ticket_evidence letters are labels of origin, not an ordered grade. A is external oracle, B is read-back from world state, C is self-report, D is mechanically derived in this tree.
- prose_kind is a type taxonomy, not a rank.
- establishment preserves active, inactive, stale, unchecked and refused as distinct readings. Unchecked is never a pass.

## 3. Family lineage — what came from which project

### 3.1 ala-cities: the civic/governance and read-back design ancestor

ala-cities is an important domain ancestor, not a place where the current nine-member AxisKind list is already declared as one enum.

Its C9 design record establishes the domain decisions that later Axis readers must preserve: skill is computed from a citizen's own completed-work record rather than stored as a scalar (Q96); organisations have premises, roster and scope (Q94); citizens found organisations (Q100); government and offices emerge through citizen-held authority (Q106, Q112, Q124); courts are adjudicative benches (Q125); and authority is a recorded grant (Q126). The C9 record also describes citizen jobs, obligations, claims, public work, progression and institutional history across simulation cadence.

Its technical governor, src/gov/mod.rs, supplies the work-governance substrate: operations are authorized before world changes, validation reads the world back, retirements preserve history, and an unreadable governor refuses rather than falling back. Its ticket model supplies the originating ticket/evidence concepts. The current Shploingus ticket module explicitly attributes TicketStatus, TicketKind, Expectation, Evidence and RetirementReason to ala-cities.

Do not confuse ala-cities' technical governor/ticket ledger with the separate in-world government that citizens must found and staff. Nor should the existence of a governor file be treated as proof that the whole civic design is implemented.

### 3.2 Shploingus: the nine-member typed contract and coverage gate

The strongest direct enumeration is:

- crates/voxel-model/src/axis.rs: provenance comment, all nine AxisKind variants, AXIS_COUNT = 9, exhaustive declared_values(), per-type Ladder implementations, the typed refusals and COVERAGE.
- crates/voxel-model/src/axis.rs: COVERAGE is typed as [CoverageRow; AXIS_COUNT], every row names the axis, its type, its token values and the source; COVERAGE_IS_TOTAL is a compile-time length assertion.
- crates/voxel-model/src/axis.rs: check_coverage rejects empty rows, rows whose values disagree with the ladder's own declaration, duplicated rows and missing axes; it collects refusals rather than returning the first.
- crates/axis/ladder/src/lib.rs: re-exports the model's single AxisKind, nine ladders and coverage table; its test explicitly asserts nine ladder names and nine coverage rows.
- crates/axis/coverage/src/lib.rs: re-exports that same coverage table and tests that a forged row is refused by name.

The canonical source is voxel-model/src/axis.rs. The axis/ladder crate is an adapter/re-export, not a second authority or a separate set of token copies.

### 3.3 ala_civ_bots_prototype: a downstream port, not a second definition

src/main/java/dev/ensouled/axis/AxisVocabulary.java explicitly describes itself as ported from voxel-model/src/axis.rs. It declares AXIS_COUNT = 9 and the same nine names and token sets, validates qualified tokens and refuses cross-ladder comparisons, scalar reductions and fabricated coverage. It is valuable proof that the nine-part vocabulary was carried into the civilian prototype, but its port must not be allowed to replace the canonical Shploingus declaration.

### 3.4 Secure Shell and Restore: additional receipt stars over the nine ladders

Secure Shell server/stars.mjs explicitly says its **six top-level receipt stars are distinct from the prototype's nine typed ladders**. It exports AXIS_COUNT = 9, LADDERS with the nine identifiers, and STAR_COUNT = 6. The six receipt stars have their own IDs, owners, lenses and requirements: presence, craft, evidence, standing, conduct and continuity.

Secure Shell Restore TICKET-0018 defines the six-star-on-every-receipt work and its 1,000-driver positive/control measurement. That six-star receipt contract is an additional verification projection; it is not a replacement for the nine Axis ladders.

### 3.5 Shploingus matrix stars: another distinct use of “star”

crates/axis/matrix/src/star.rs defines STAR_COUNT = 5. These five ordinal display levels count how many declared predicate rows actually ran and passed. The matrix uses those stars per (segment, axis) cell alongside a bronze-to-platinum certification tier. This is not the nine-member AxisKind vocabulary and not Secure Shell's six receipt stars.

## 4. Similar-looking counts that must never be merged

| Count | Owner/type | Meaning | Not the same as |
|---:|---|---|---|
| 9 | AxisKind / AXIS_COUNT | Nine typed Axis dimensions/ladders | Star glyph count, ticket states, or Grade rungs |
| 9 | Grade::ALL | Nine progression levels F through SSS inside the grade ladder | Nine Axis dimensions |
| 9 | TicketStatus::ALL | Nine ticket lifecycle states (queued, open, active, blocked, review, complete, rejected, handled, dropped) | AxisKind |
| 5 | matrix::Star / STAR_COUNT | Predicate-run-and-passed rating for a matrix cell | Nine Axis dimensions |
| 6 | Secure Shell STARS / STAR_COUNT | Six separately owned receipt lenses on each Axis action receipt | Nine Axis dimensions |

The word **axis** itself is also overloaded in the family: it can mean the typed vocabulary, a game/civilian axis reading, a server authorization service, or a layout/content lane. A repository path or a name alone is not enough to prove that two of these are the same subsystem.

## 5. The non-reduction contract for family agents

Before any agent edits, ports, summarizes, audits or creates a client surface around Axis, the CUA driver must:

1. Locate all nine AxisKind identifiers in the canonical source and reconcile them against the full COVERAGE table, not a partial search result.
2. Read the provenance field for every coverage row and record whether the referenced source itself was accessible, pinned, excluded or unavailable. A citation in a comment is a locator, not proof that the referenced source was independently read.
3. Compare downstream ports (including ala_civ_bots_prototype) against the canonical names, tokens, semantics and refusal behavior. A port is corroboration, not authority to silently fork the contract.
4. Inspect the five-star matrix and six-star receipt implementations as separate consumers. Never use their count as the count of AxisKind.
5. Preserve distinct types, ladders, meanings, refusal codes, coverage rows and consumer paths. Never merge ladders because their token strings overlap, turn them into a score, treat one as a maximum, replace a predicate set with a boolean, or substitute a receipt-star total for a per-axis reading.
6. Treat a missing, unreadable or unmeasured axis as named missing/unchecked/refused state, never as zero, false, passed or implicitly absent from the contract.
7. Propose any addition, removal, rename, merge, token change or change of meaning as an owner-level decision. Preserve the old schema/version, source pins, migrations, downstream compatibility map, fixtures and supersession record. An agent may not “simplify” the count during an implementation or documentation pass.
8. Require tests that reject: each missing coverage row, duplicate row, forged token, bare token, cross-ladder comparison, scalar reduction, max certification, stale source pin and any mismatch between a port and the canonical declaration.
9. Publish two views if useful: the complete nine-axis authority/evidence matrix and a separate UI rendering such as five matrix stars or six receipt stars. The visual projection cannot become the canonical data model.

**Refusal name:** axis-contract-reduced. The refusal must list the missing or collapsed members, the prior source pin, the consumer affected and the ticket that would be required to propose a legitimate change.

## 6. Evidence pins and limits of this audit

| Repository | Artifact | Pin |
|---|---|---|
| ala-cities | docs/GRILLING-C9.md | 70fbc9d6d1647b2a54a4f32168a2cfbada5adac9 |
| ala-cities | src/gov/mod.rs | 86ed95c3348d1bad5af6dcd22b85dca6f227b59d |
| Shploingus Clean | crates/voxel-model/src/axis.rs | 9c6981306d254587bccc9604d19ea601e2172125 |
| Shploingus Clean | crates/voxel-model/src/ticket.rs | 13fd58ea55231c2ff12d6cfdf3380bda354d6de9 |
| Shploingus Clean | crates/axis/ladder/src/lib.rs | 491e76811fc911f339d8e08a1b689686abc3be89 |
| Shploingus Clean | crates/axis/coverage/src/lib.rs | 04780169ea243ff9615193d0dc65cd2369c7c1f8 |
| Shploingus Clean | crates/axis/matrix/src/star.rs | e682dbc7e7720113bb11257d8783121ebdd63783 |
| ala_civ_bots_prototype | AxisVocabulary.java | ef080c0bc983a923b69d6a6453584fecb88593dd |
| Secure Shell | server/stars.mjs | efa465aec527e8d147960213f0a78001389c80f3 |
| Secure Shell | patches/PATCH-004-five-star-axis.md | 633af8e8bb01fd63cbd1a704bccb834f34ae6213 |
| Secure Shell Restore | tickets/TICKET-0018-six-stars-on-every-receipt.md | 0711cac9af54cf7fe9b4adae2b356e4a49a00706 |

This source audit did not run the Rust or Java test suites, access the private/upstream cited source trees (godplan/axes.py, ala-system support.ts, prose_logic AtomKind), execute the real Debian Axis service, inspect local drive copies or produce a CUA receipt. The Shploingus Rust source provides its own source-locator table, but those upstream source bodies were not independently available in the inspected public tree. Current source and port declarations are directly observed; runtime acceptance remains to be witnessed by the registered CUA driver.
