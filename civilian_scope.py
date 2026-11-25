"""The designed-out civilian scope, including every named block.

A feature is not dropped because Popit cannot run it yet.  Each row names the
family requirement, the exact family artifact that constrains it, the Popit
surface (or `none`), and either the wired route or the blocker and the research
question that must be answered before the row can move.

Status values:
  wired    - a Popit route or runtime path exists and has a receipt
  partial  - a surface exists but a family requirement is still missing
  designed - specified here, no runtime path yet
  blocked  - the family implementation or prerequisite does not exist
  owed     - the family itself marks this as owed/unmodelled
"""
from __future__ import annotations

SCHEMA = "popit.civilian-scope/1"
STATUSES = ("wired", "partial", "designed", "blocked", "owed")

CIVILIANS = "agent_god_files/reference/CIVILIANS.md"
C9 = "openlock_modern/tools/cua_civilian.py"
V4 = "ala_civ_bots_prototype/docs/minecraft_ensouled_system1_cua_architecture_v4.md"
STATUS = "ala_civ_bots_prototype/docs/IMPLEMENTATION_STATUS.md"
POPIT = "civilian_features.py"
CALL = "call-client/serve.py"


def _item(id: str, group: str, title: str, status: str, evidence: str,
          surface: str, blocker: str = "", research: str = "",
          detail: str = "") -> dict:
    return {
        "id": id, "group": group, "title": title, "status": status,
        "evidence": evidence, "surface": surface,
        "blocker": blocker, "research": research, "detail": detail,
    }


ITEMS = (
    # ---------------------------------------------------------------- being
    _item("being-record", "being", "One being record for civilian, pilot, god, mob and plant",
          "blocked", f"{CIVILIANS} §2, §3.1, §6",
          "none",
          "CIVILIANS §2 measures a being as only a free-text Grant name; no being record kind exists.",
          "What durable actor-record schema preserves one identity across body replacement, death and rehydration?",
          "The family design has six faces and one substrate; Popit has display identities only."),
    _item("durable-identity", "being", "Identity survives process, session and body replacement",
          "blocked", f"{V4} §7.1; {CIVILIANS} §2",
          "none",
          "No AgentId/identity record is built; Popit's lane identity is a name string in civilians.json.",
          "What stable identifier and revision model survives reconnect and body replacement without treating a session as the person?",
          "The V4 record lists agent_id, origin, lifecycle, lineage and immutable revision."),
    _item("affect-wheel", "being", "Full 510-label feeling wheel with radius and drift",
          "partial", f"{V4} §7.3; {CIVILIANS} §3.2",
          "POST /api/toast/civilian/name (the page is retired)",
          "Popit implements six primaries, six secondaries each and one tertiary per secondary (36 paths); it stores no radius, drift, band or cause references.",
          "What is the exact 12x6x? full wheel table and how should radius/drift be serialized?",
          "The identity route records primary/secondary/tertiary, colour, confidence and source."),
    _item("gender-species-lifecycle", "being", "Gender, species/body type, birth and lifecycle state",
          "blocked", f"{V4} §7.1; {CIVILIANS} §3.1",
          "none",
          "V4 §7.1 states the gender vocabulary and semantics are not defined by the inspected materials; no species or lifecycle record exists.",
          "What canonical identity vocabulary is approved for gender, species and lifecycle, without inferring it from personality or body?",
          ""),
    _item("incarnation", "being", "A god or player can incarnate as a civilian record",
          "blocked", f"{CIVILIANS} Q160, §3.1",
          "none",
          "No citizen record and no incarnation path exist; the god returns to the outside view only in prose.",
          "How does an incarnate hold a citizen record without gaining office by virtue of being a god?",
          ""),

    # ------------------------------------------------------------------ life
    _item("five-needs", "life", "Food, rest, warmth, health and shelter decay on one cadence",
          "wired", f"{C9} needs/decay/tick; {POPIT} life_tick",
          "GET/POST /api/toast/civilian/life, /life/tick",
          detail="C9 is loaded from the family checkout and persisted per lane."),
    _item("needs-first-care", "life", "Care is chosen before offered work below the SEEK floor",
          "wired", f"{C9} choose; {POPIT} context",
          "/api/toast/civilian/life/tick; call grounding",
          detail="The call persona names low needs and the care-first rule."),
    _item("failure-ladder", "life", "ok, degraded, illness and dead have declared capacity",
          "wired", f"{C9} condition/capacity",
          "/api/toast/civilian/life",
          detail="Condition and capacity are returned in every life receipt."),
    _item("extended-needs", "life", "Social contact, belonging and personal purpose as needs",
          "blocked", f"{V4} §23.4; {C9} NEEDS",
          "none",
          "C9 declares only food, rest, warmth, health and shelter; no social or purpose provider exists.",
          "Which additional needs have meaningful world mechanics, and how are they observed rather than invented?",
          ""),
    _item("work-lifecycle", "life", "Work planned, declined once, delegated and completed by evidence",
          "wired", f"{C9} choose/apply_decision/complete_work; {POPIT} life_apply",
          "POST /api/toast/civilian/life/apply",
          detail="Decline and delegation are recorded so the same job is not asked every tick."),
    _item("life-steps", "life", "A decision becomes a declared marker or body step",
          "wired", f"{C9} steps_for; {POPIT} life_steps",
          "POST /api/toast/civilian/life/steps",
          detail="Care and wait produce markers; observe and explore produce body steps."),
    _item("death-corpus", "life", "Death is emergent, produces a corpse and deathcare is a service",
          "blocked", f"{CIVILIANS} §3.3, §3.4, Q24/Q60/Q131",
          "none",
          "No death event, corpse record, court finding or deathcare service exists; C9 has a dead condition only.",
          "What event schema moves a body to a corpse holding and a destination account without the system scheduling death?",
          ""),
    _item("violence-court", "life", "Violence is permitted and adjudicated, never engine-determined",
          "blocked", f"{CIVILIANS} §3.3, Q127/Q131/Q137",
          "none",
          "No act vocabulary, court, finding or relation record exists; the bridge tools only read and show.",
          "How are murder, intent, accident and self-defence represented as findings over acts without a lethal bridge verb?",
          ""),
    _item("ensoulment", "life", "Every being is ensouled on von's substrate, never a hollow device",
          "blocked", f"{CIVILIANS} §3.2, §5 ruling 4; {V4} §1.2",
          "none",
          "CIVILIANS §2 says von exists as prose only; nothing is ensouled. Popit voice profiles are not a soul.",
          "What is the minimal measurable ensoulment record that is neither prose nor a hidden script?",
          ""),
    _item("soul-consent", "life", "A soul is an individual; release and claiming require consent, rite or corruption",
          "blocked", f"{CIVILIANS} §3.2, §5 ruling 4",
          "none",
          "No soul record, release event, consent or rite exists; the ledger only audits soul-energy conceptually.",
          "What consent model prevents a soul from being treated as a currency or claimed without a declared condition?",
          ""),
    _item("corruption-effigies", "life", "Corruption and effigies are owed, not improvised",
          "owed", f"{CIVILIANS} §3.2, §5 ruling 8",
          "none",
          "The family explicitly marks corruption/effigies unmodelled and awaiting a later owner pass.",
          "What is the approved corruption/effigy design before any schema is written?",
          "This row is deliberately not implemented."),
    _item("gaia-ecology", "life", "Gaia is its own system with rot, decay and decomposers",
          "blocked", f"{CIVILIANS} §3.7, §5 ruling 3",
          "none",
          "No Gaia process, decomposer, rot or ecology layer exists in Popit or the measured family slice.",
          "What law does Gaia own, and how are rot and decomposers represented without city statute binding them?",
          ""),

    # ---------------------------------------------------------------- memory
    _item("memory-working", "memory", "Working memory: current sensory buffer and active intention",
          "blocked", f"{V4} §7.2",
          "none",
          "Popit has a conversation archive, not a typed working-memory record with intentions and conflicts.",
          "What bounded working-memory schema can be rehydrated without storing the whole transcript?",
          ""),
    _item("memory-episodic", "memory", "Episodic memory: dated, located events with participants and outcome",
          "blocked", f"{V4} §7.2",
          "none",
          "Archive rows are not an episodic memory; no location, participant set, causal outcome or correction path exists.",
          "What episode schema preserves who, where, what changed and the original evidence pointer?",
          ""),
    _item("memory-semantic", "memory", "Semantic memory: beliefs with evidence refs and revision history",
          "blocked", f"{V4} §7.2",
          "none",
          "No belief store or revision history exists; the decision ledger is not a world belief model.",
          "How are beliefs revised and corrected without overwriting the evidence that supported the old belief?",
          ""),
    _item("memory-procedural", "memory", "Procedural memory: verified skills with preconditions and failure modes",
          "blocked", f"{V4} §7.2; {CIVILIANS} §3.5",
          "none",
          "C9 records work counts and completed ids, not validated motor schemas or skill preconditions.",
          "What skill record makes a verified procedure reusable by a different body or after restart?",
          ""),
    _item("memory-social", "memory", "Social memory: relationships, promises, debts, trust and reputation",
          "blocked", f"{V4} §7.2; {CIVILIANS} §3.8",
          "none",
          "No relationship, promise, debt, trust or reputation record exists; contacts are an address book.",
          "What relationship evidence model distinguishes a promise from permission and a reputation from a score?",
          ""),
    _item("memory-autobiographical", "memory", "Autobiographical continuity derived from canonical episodes",
          "blocked", f"{V4} §7.2",
          "none",
          "No identity-relevant event sequence or episode reference exists.",
          "How is a life story derived without replacing the episodes it summarizes?",
          ""),
    _item("per-lane-memory", "memory", "Each lane answers from its own history",
          "partial", f"{POPIT} state/context",
          "/api/toast/civilians; call grounding",
          "Lane identity, decisions and needs are separate, but there is no per-lane episodic or semantic history.",
          "What migration path moves lane identity into a durable person record without duplicating transcripts?",
          ""),

    # ---------------------------------------------------------------- social
    _item("relations", "social", "Grudges, debts, fraud, care and other relations",
          "blocked", f"{CIVILIANS} §3.3, §3.8; {V4} §23.5",
          "none",
          "No relation record exists; violence and obligations are not modelled.",
          "Which relations are evidence-backed and which are narrative, and how are they revised?",
          ""),
    _item("commitments", "social", "Promises and obligations with subject, time and completion condition",
          "blocked", f"{V4} §23.5",
          "none",
          "No promise or commitment record exists; a call wish is not a social obligation.",
          "How does a promise create an expectation without itself authorizing a world mutation?",
          ""),
    _item("social-contract", "social", "Material social contract fields",
          "partial", f"{V4} §12.4; {POPIT} contract",
          "/api/toast/civilian/contract",
          "Popit has the seven governance fields but not parties/roles, region, action vocabulary, ownership, expiry/renewal, breach or termination.",
          "What exact field schema covers all eleven V4 §12.4 material fields without widening authority?",
          "The seven-field route is wired and is the base, not the complete social contract."),
    _item("subcontract-narrowing", "social", "A child contract may narrow, never widen, its parent",
          "blocked", f"{V4} §12.4; {CIVILIANS} §3.6",
          "none",
          "No parent contract, child contract or narrowing check exists; the seven-field route has no hierarchy.",
          "How is scope/resource/term narrowing proven mechanically for a child contract?",
          ""),
    _item("office", "social", "Office is a named scope with holder, term and revocation rule",
          "blocked", f"{CIVILIANS} §3.6, Q112/Q136/Q163",
          "none",
          "No office record, term, vacancy, suspension or retirement path exists.",
          "How are vacancy and suspension records kept separate from the grant fold?",
          ""),
    _item("apprenticeship", "social", "Apprenticeship and tutoring transfer skill as a verified task",
          "blocked", f"{CIVILIANS} §3.5, §6 item 7",
          "none",
          "The family explicitly names apprenticeship and tutoring as missing; no task or verification exists.",
          "What task schema proves a skill transfer at the same commit point as the work?",
          ""),
    _item("speech-acts", "social", "Typed speech acts rather than model-composed messages",
          "blocked", f"{V4} §8.1",
          "none",
          "Popit sends free text through voice/call; there is no closed GREET/INFORM/WARN/REQUEST/... act set with validation.",
          "What canonical speech-act set is approved, and which acts require a material contract?",
          ""),

    # ------------------------------------------------------------- governance
    _item("confidence-gate", "governance", "Automatic at 0.80, escalate below it",
          "wired", f"{POPIT} decide/state",
          "POST /api/toast/civilian/decision",
          detail="Every decision receipt carries gate, act, threshold and state."),
    _item("decision-ledger", "governance", "Decision retained with answer, provenance and ground truth",
          "wired", f"{POPIT} decide/verify",
          "POST /api/toast/civilian/decision, /verify",
          detail="The ledger persists decisions and verification rows."),
    _item("typed-choice", "governance", "Choice with a retained distribution",
          "wired", f"{POPIT} decide",
          "/api/toast/civilian/decision",
          detail="Choice, Noul and Score share one typed decision route."),
    _item("noul-condition", "governance", "Noul as a probability, never prose",
          "wired", f"{POPIT} decide",
          "/api/toast/civilian/decision"),
    _item("ordinal-score", "governance", "Score across declared anchors",
          "wired", f"{POPIT} decide",
          "/api/toast/civilian/decision"),
    _item("duration-chain", "governance", "Duration/date solved deterministically with spans",
          "wired", f"{POPIT} duration",
          "/api/toast/civilian/duration",
          detail="The route is implemented in the module; add the page control if it is absent."),
    _item("closed-world", "governance", "Unsupported language/domain is a named refusal",
          "wired", f"{POPIT} NON_ASCII/decide",
          "/api/toast/civilian/decision",
          detail="The shared civilian floor is English-only until a model's coverage is declared."),
    _item("deterministic-verification", "governance", "A confident answer is not a result until a machine check agrees",
          "partial", f"{POPIT} verify; {V4} §12.1",
          "POST /api/toast/civilian/verify",
          "verify accepts the owner's `passed` boolean; it does not run a machine check over an artifact.",
          "What verifier registry maps a deliverable to an observed artifact and a deterministic check?",
          ""),
    _item("mood-after-work", "governance", "A fresh feeling follows a closed contract",
          "designed", f"{POPIT} FEATURES; {V4} §7.3",
          "none",
          "The feature row exists, but no route records a post-work affect transition or its causes.",
          "Which wheel transition and cause references should a closed contract write?",
          ""),
    _item("ticket-evidence", "governance", "Governor > Season > Campaign > Contract > Ticket > Action/Evidence/Validation",
          "partial", f"{V4} §12.2, §23.6; {POPIT} contract",
          "/api/toast/civilian/contract; call row",
          "Popit records a contract and call/archive rows, but has no ticket, validation or season hierarchy.",
          "What minimal ticket and validation record can reference a canonical contract without duplicating it?",
          ""),

    # ------------------------------------------------------------------ call
    _item("envelope", "call", "Outside callers sign a package before the host opens a lane",
          "wired", "envelope.py; toast.py call/join; ENVELOPE.md",
          "POST /api/toast/call/join",
          detail="Ed25519, BLAKE3 trust, 15-minute window, single-use nonce; unsigned join is refused."),
    _item("remote-transport", "call", "Published landing page reaches a host on another machine over HTTPS",
          "partial", f"{CALL}; toast.py bridge",
          "call-client/serve.py",
          "The page can name an HTTPS bridge, but the host must run the companion or expose CORS/TLS; GitHub Pages cannot execute serve.py.",
          "Which host URL and TLS/certificate distribution is supported for a remote machine without a tunnel?",
          "This is the secure transport surface, not an unsigned open bridge."),
    _item("user-enrollment", "call", "A user can enroll a caller key without a terminal",
          "blocked", "envelope.py trust; call-client README",
          "none",
          "Trust requires the host operator to run `envelope.py trust`. The page can generate/load a package but cannot request enrollment.",
          "What host-approved enrollment code lets a browser key join the trust registry without exposing the operator's private state?",
          ""),
    _item("remote-audio", "call", "A user on another machine can speak into the same call",
          "blocked", "toast.py phone/audio; docs/phone-commons.md",
          "HTTPS /phone.html (same network)",
          "Phone audio is a local HTTPS WAV upload. There is no remote WebRTC/relay audio path from the published page.",
          "Should remote audio use WebRTC with a signed ticket, or an authenticated relay with bounded frames?",
          ""),
    _item("agent-to-agent", "call", "Two agents on different machines join one call",
          "partial", "toast.py call/join; calls.py",
          "/api/toast/call/join over HTTPS companion",
          "The signed join and turn/say/leave protocol is wired; two remote machines and a public TLS origin are not yet tested.",
          "What two-machine harness proves identity, nonce, turn ordering and disconnect recovery?",
          ""),
)


def _unique() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    for row in ITEMS:
        if row["id"] in seen:
            raise ValueError(f"duplicate scope id: {row['id']}")
        seen.add(row["id"])
        rows.append(dict(row))
    return rows


def validate() -> list[str]:
    errors: list[str] = []
    rows = _unique()
    for row in rows:
        if row["status"] not in STATUSES:
            errors.append(f"{row['id']}: bad status {row['status']!r}")
        if not row["evidence"]:
            errors.append(f"{row['id']}: no family evidence")
        if row["status"] in ("blocked", "owed") and not row["blocker"]:
            errors.append(f"{row['id']}: blocked without a named blocker")
        if row["status"] in ("blocked", "partial", "owed") and not row["research"]:
            errors.append(f"{row['id']}: {row['status']} without a research question")
        if row["status"] == "wired" and row["surface"] == "none":
            errors.append(f"{row['id']}: wired without a surface")
    return errors


def state() -> dict:
    rows = _unique()
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    return {
        "schema": SCHEMA,
        "counts": {**counts, "total": len(rows)},
        "groups": [{"group": name, "items": items} for name, items in groups.items()],
        "blocked": [row for row in rows if row["status"] in ("blocked", "owed")],
        "partial": [row for row in rows if row["status"] == "partial"],
        "errors": validate(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(state(), indent=2, ensure_ascii=False))
