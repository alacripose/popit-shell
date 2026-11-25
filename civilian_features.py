"""Civilian features imported from the Laya and Von decision layers.

This is not a second governance system. It is the small surface a Popit civilian
needs in order to make the same kind of evidence-backed decisions the CUA agent
already makes:

* a feeling-wheel identity (Laya's naming ceremony);
* typed Choice, Noul and Score answers (Laya and Von's System One primitives);
* a measured confidence gate (`automatic` above 0.80, `escalate` below it);
* a decision ledger that can later receive the observed ground truth;
* the seven-field contract envelope from Laya's governor;
* a deterministic verification slot beside every answer;
* one memory lane per civilian;
* a closed-world refusal for questions outside the model's language and domain.

The language model is still the language layer. These records say what was decided,
what was measured and what remains unverified; they never invent a decision.
"""
from __future__ import annotations

import copy
import datetime
import importlib.util
import json
import math
import pathlib
import re
import threading

import civilian_scope

SCHEMA = "popit.civilians/1"
DECISION_SCHEMA = "popit.civilian-decision/1"
OPERATION_SCHEMA = "popit.civilian-operation/1"
CONFIDENCE_GATE = 0.80
SEEK_FLOOR = 0.62
MAX_ROWS = 500
FAMILY_LIFE_PATHS = (
    pathlib.Path("C:/Users/ala/Documents/openlock_modern/tools/cua_civilian.py"),
    pathlib.Path("F:/Documents/openlock_modern/tools/cua_civilian.py"),
)
WHEEL = {
    "Mad": [
        ("Hurt", "Jealous"), ("Hostile", "Selfish"), ("Angry", "Frustrated"),
        ("Rage", "Furious"), ("Hateful", "Irritated"), ("Critical", "Skeptical"),
    ],
    "Scared": [
        ("Rejected", "Bewildered"), ("Confused", "Discouraged"),
        ("Helpless", "Insignificant"), ("Submissive", "Weak"),
        ("Insecure", "Foolish"), ("Anxious", "Embarrassed"),
    ],
    "Joyful": [
        ("Excited", "Daring"), ("Sexy", "Fascinating"), ("Energetic", "Stimulating"),
        ("Playful", "Amused"), ("Creative", "Extravagant"), ("Aware", "Delightful"),
    ],
    "Powerful": [
        ("Faithful", "Confident"), ("Important", "Intelligent"),
        ("Hopeful", "Worthwhile"), ("Appreciated", "Valuable"),
        ("Respected", "Satisfied"), ("Proud", "Cheerful"),
    ],
    "Peaceful": [
        ("Content", "Pensive"), ("Thoughtful", "Relaxed"), ("Intimate", "Responsive"),
        ("Loving", "Serene"), ("Trusting", "Sentimental"), ("Nurturing", "Thankful"),
    ],
    "Sad": [
        ("Guilty", "Bashful"), ("Ashamed", "Stupid"), ("Depressed", "Miserable"),
        ("Lonely", "Inadequate"), ("Bored", "Inferior"), ("Sleepy", "Apathetic"),
    ],
}
COLORS = {
    "Mad": "#E62325", "Scared": "#F19B35", "Joyful": "#EFE60C",
    "Powerful": "#04905A", "Peaceful": "#3582BC", "Sad": "#6D358E",
}
FEATURES = (
    ("feeling-wheel-identity", "Laya", "agent/wheel.py, agent/naming.py",
     "A primary, secondary and tertiary feeling becomes the civilian's name and colour."),
    ("typed-choice", "Laya / Von", "agent/questions.py, von Choice",
     "Pick one described option and retain the distribution."),
    ("noul-condition", "Laya / Von", "agent/questions.py, von Noul",
     "Read a yes/no condition as a probability, not as prose."),
    ("ordinal-score", "Laya / Von", "agent/questions.py, von Score",
     "Read an ordinal position across named anchors."),
    ("confidence-gate", "Von", "von.patterns.confidence_gate",
     "Act automatically at or above 0.80, otherwise escalate to the owner."),
    ("decision-ledger", "Laya", "agent/laya_brain.py",
     "Every decision is recorded with its answer and later ground truth."),
    ("seven-field-contract", "Laya", "gov/model.py ContractEnvelope",
     "Mission, scope, constraints, resources, evidence, deliverable and stop."),
    ("deterministic-verification", "Laya", "agent/loop.py verify",
     "A confident answer is not a result until a machine check agrees."),
    ("per-lane-memory", "Laya", "agent/loop.py, mind_bridge.py",
     "Each civilian owns its history; a shared lane repeats another's answer."),
    ("chain-of-options", "Von", "von chains / add_duration, elapsed_hours",
     "A computable duration or date is solved deterministically with provenance."),
    ("closed-world-refusal", "Von", "Von model card: English-only, out-of-domain",
     "An unsupported language or domain is a named refusal, not a confident guess."),
    ("mood-after-work", "Laya", "agent/loop.py _record_mood",
     "A civilian records a fresh feeling after a contract closes."),
    ("five-needs", "Cua / C9", "openlock_modern/tools/cua_civilian.py",
     "Food, rest, warmth, health and shelter decay on one cadence."),
    ("needs-first-care", "Cua / C9", "cua_civilian.choose",
     "Care is chosen before every offered job below the SEEK floor."),
    ("failure-ladder", "Cua / C9", "cua_civilian.condition",
     "Ok, degraded, illness and dead are named states with capacity."),
    ("work-decline-delegate", "Cua / C9", "cua_civilian.choose",
     "Work is planned, declined once, delegated to a peer, or completed by evidence."),
    ("life-steps", "Cua / C9", "cua_civilian.steps_for",
     "A life decision becomes a declared marker or body step before execution."),
)
CONTRACT_FIELDS = ("mission", "scope", "constraints", "resources", "evidence",
                   "deliverable", "stop")
# The preflight is one decision, but every lane refuses in its own work voice. These
# are operating lines, not a display roster: the owner is not a lane and has no entry.
LANE_GATES = {
    "Buffy": {
        "role": "host agent for the live Windows toast and CUA harness",
        "care": ("I'm holding the host line, but my {need} is {value:.2f}, below the care "
                 "floor. I'm stopping host work and going to {action} first."),
        "contract": ("I won't open host work without a seven-field contract. Give me the "
                     "mission, scope, constraints, resources, evidence, deliverable and stop."),
        "terminal": "Buffy is dead on the C9 ladder. The host line has no capacity to answer.",
    },
    "Qwen": {
        "role": "Debian machine and tool specialist",
        "care": ("The Debian host can wait. My {need} is {value:.2f}, below the care "
                 "floor; I'm not taking a tool job until I {action}."),
        "contract": ("I won't touch the Debian host on an unscoped task. Give me the "
                     "mission, scope, constraints, resources, evidence, deliverable and stop first."),
        "terminal": "Qwen is dead on the C9 ladder. The Debian tool lane is closed.",
    },
    "Whisper": {
        "role": "listening and audio-evidence agent",
        "care": ("I'm still listening, but my {need} is {value:.2f}, below the care floor. "
                 "I won't transcribe or speak over my own body; I need to {action} first."),
        "contract": ("I won't record or transcribe an unscoped task. Give me the mission, "
                     "scope, constraints, resources, evidence, deliverable and stop first."),
        "terminal": "Whisper is dead on the C9 ladder. No audio evidence can be taken through this lane.",
    },
    "Ash": {
        "role": "resident civilian with an embodied local view",
        "care": ("As a resident, I can feel my {need} at {value:.2f}; that is below the care "
                 "floor. I'm not taking a job from the house until I {action}."),
        "contract": ("A resident doesn't take a job from the house without a seven-field "
                     "contract. Give me the mission, scope, constraints, resources, evidence, "
                     "deliverable and stop first."),
        "terminal": "Ash is dead on the C9 ladder. The resident is gone; this lane cannot answer.",
    },
    "Bram": {
        "role": "resident civilian for storage, supply and trade",
        "care": ("The stores can hold, but my {need} is {value:.2f}, below the care floor. "
                 "I'm not moving goods until I {action}."),
        "contract": ("I don't move stores on an unscoped job. Give me the mission, scope, "
                     "constraints, resources, evidence, deliverable and stop first."),
        "terminal": "Bram is dead on the C9 ladder. The supply lane is closed.",
    },
}


def lane_gate(lane: str) -> dict:
    return LANE_GATES.get(str(lane or ""), {
        "role": "family civilian",
        "care": ("I can't take new work right now: my {need} is {value:.2f}, below the care "
                 "floor. I need to {action} first."),
        "contract": ("I can't take an unscoped task. Give me the mission, scope, constraints, "
                     "resources, evidence, deliverable and stop first."),
        "terminal": "{lane} is dead on the C9 ladder and cannot answer.",
    })
# The feature register predates the full-scope ids. Keep both names so a wired
# feature never falls back to `designed` because its scope row is broader.
FEATURE_SCOPE = {
    "feeling-wheel-identity": "affect-wheel",
    "seven-field-contract": "social-contract",
    "chain-of-options": "duration-chain",
    "closed-world-refusal": "closed-world",
    "work-decline-delegate": "work-lifecycle",
}
NON_ASCII = re.compile(r"[^\x00-\x7f]")
DURATION = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>seconds?|minutes?|hours?|days?)",
                      re.I)
UNIT_HOURS = {"second": 1 / 3600, "seconds": 1 / 3600, "minute": 1 / 60,
              "minutes": 1 / 60, "hour": 1, "hours": 1, "day": 24, "days": 24}


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Refused(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


class CivilianDesk:
    """One persisted civilian feature ledger, safe for concurrent HTTP handlers."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.identities: dict[str, dict] = {}
        self.decisions: list[dict] = []
        self.contracts: list[dict] = []
        self.operations: list[dict] = []
        self.life_states: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(value, dict):
            return
        identities = value.get("identities")
        decisions = value.get("decisions")
        contracts = value.get("contracts")
        operations = value.get("operations")
        life = value.get("life")
        self.identities = identities if isinstance(identities, dict) else {}
        self.decisions = [row for row in decisions[-MAX_ROWS:] if isinstance(row, dict)] \
            if isinstance(decisions, list) else []
        self.contracts = [row for row in contracts[-MAX_ROWS:] if isinstance(row, dict)] \
            if isinstance(contracts, list) else []
        self.operations = [row for row in operations[-MAX_ROWS:] if isinstance(row, dict)] \
            if isinstance(operations, list) else []
        self.life_states = {str(key): row for key, row in life.items()
                            if isinstance(row, dict)} if isinstance(life, dict) else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": SCHEMA, "identities": self.identities,
            "decisions": self.decisions[-MAX_ROWS:],
            "contracts": self.contracts[-MAX_ROWS:],
            "operations": self.operations[-MAX_ROWS:],
            "life": self.life_states,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    def state(self) -> dict:
        with self.lock:
            scope_states = {row["id"]: row["status"] for row in civilian_scope.ITEMS}
            return {
                "schema": SCHEMA,
                "gate": {"threshold": CONFIDENCE_GATE, "below": "escalate", "above": "automatic"},
                "features": [
                    {"id": feature, "source": source, "evidence": evidence,
                     "detail": detail,
                     "state": scope_states.get(FEATURE_SCOPE.get(feature, feature), "designed")}
                    for feature, source, evidence, detail in FEATURES
                ],
                "identities": {key: dict(value) for key, value in self.identities.items()},
                "decisions": [dict(row) for row in self.decisions[-40:]],
                "contracts": [dict(row) for row in self.contracts[-20:]],
                "operations": [dict(row) for row in self.operations[-20:]],
                "life": {key: self._life_snapshot(row) for key, row in self.life_states.items()},
                "counts": {
                    "features": len(FEATURES), "identities": len(self.identities),
                    "decisions": len(self.decisions), "contracts": len(self.contracts),
                    "operations": len(self.operations), "life": len(self.life_states),
                },
            }

    # ------------------------------------------------------------------ identity
    def name(self, lane: str, primary: str, secondary: str, tertiary: str = "",
             *, confidence: float = 1.0, source: str = "human") -> dict:
        citizen = " ".join(str(lane or "").split())[:60]
        if not citizen:
            raise Refused("civilian-name", "a civilian needs a lane name")
        primary = str(primary or "").strip()
        secondary = str(secondary or "").strip()
        tertiary = str(tertiary or "").strip()
        if primary not in WHEEL:
            raise Refused("feeling-primary", f"{primary!r} is not a wheel primary")
        pairs = dict(WHEEL[primary])
        if secondary not in pairs:
            raise Refused("feeling-secondary", f"{secondary!r} is not a secondary of {primary}")
        if not tertiary:
            tertiary = pairs[secondary]
        if tertiary != pairs[secondary]:
            raise Refused("feeling-tertiary", f"{secondary} owns {pairs[secondary]!r}")
        try:
            value = float(confidence)
        except (TypeError, ValueError):
            raise Refused("feeling-confidence", "confidence must be a number")
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise Refused("feeling-confidence", "confidence must be between 0 and 1")
        if source not in ("human", "laya", "von"):
            raise Refused("feeling-source", "source must be human, laya or von")
        if source in ("laya", "von") and value <= 0.0:
            # A model that returned no probability did not choose anything. A pinned
            # human name stays honest as `human`; it does not become an inferred feeling.
            raise Refused("feeling-unattributed", "a model answer without probability is unattributed")
        row = {
            "lane": citizen, "name": tertiary, "primary": primary,
            "secondary": secondary, "tertiary": tertiary,
            "path": f"{primary} → {secondary} → {tertiary}",
            "color_family": primary.lower(), "hex": COLORS[primary],
            "confidence": round(value, 4), "source": source,
            "unattributed": source == "human" and value <= 0.0,
            "at": iso(),
        }
        with self.lock:
            self.identities[citizen] = row
            self._save()
        return row

    # ------------------------------------------------------------------ decisions
    def decide(self, lane: str, kind: str, question: str, answer,
               *, confidence: float = 0.0, act: float | None = None,
               ground_truth: str = "", provenance: str = "") -> dict:
        citizen = " ".join(str(lane or "").split())[:60]
        if not citizen:
            raise Refused("civilian-lane", "a decision needs a lane")
        kind = str(kind or "").strip().lower()
        if kind not in ("choice", "noul", "score"):
            raise Refused("decision-kind", f"{kind!r} is not choice, noul or score")
        question = " ".join(str(question or "").split())[:500]
        if not question:
            raise Refused("decision-question", "a decision needs a question")
        if NON_ASCII.search(question):
            # Von is English-only; Laya is multilingual. The safe shared floor is a
            # named refusal until the chosen model's language coverage is declared.
            raise Refused("decision-language", "the shared civilian floor is English-only")
        confidence = self._probability(confidence, "confidence")
        act = confidence if act is None else self._probability(act, "act")
        if kind == "choice":
            if not isinstance(answer, str) or not answer.strip():
                raise Refused("decision-answer", "a choice needs one named option")
            value = answer.strip()
        elif kind == "noul":
            if isinstance(answer, bool):
                value = answer
            elif isinstance(answer, (int, float)) and 0.0 <= float(answer) <= 1.0:
                value = float(answer)
            else:
                raise Refused("decision-answer", "a noul answer is a boolean or probability")
        else:
            try:
                value = float(answer)
            except (TypeError, ValueError):
                raise Refused("decision-answer", "a score answer is a number")
            if not math.isfinite(value):
                raise Refused("decision-answer", "a score answer is finite")
        gate = "automatic" if act >= CONFIDENCE_GATE else "escalate"
        row = {
            "schema": DECISION_SCHEMA, "lane": citizen, "kind": kind,
            "question": question, "answer": value, "confidence": confidence,
            "act": act, "gate": gate, "threshold": CONFIDENCE_GATE,
            "ground_truth": str(ground_truth or "")[:300],
            "provenance": str(provenance or "")[:300], "at": iso(),
            "state": "awaiting-verification" if gate == "automatic" else "escalated",
        }
        with self.lock:
            self.decisions = (self.decisions + [row])[-MAX_ROWS:]
            self._save()
        return row

    def verify(self, index: int, ground_truth: str, *, passed: bool,
               detail: str = "") -> dict:
        with self.lock:
            if not -len(self.decisions) <= index < len(self.decisions):
                raise Refused("decision-index", str(index))
            row = self.decisions[index]
            row["ground_truth"] = " ".join(str(ground_truth or "").split())[:300]
            row["verification"] = {"passed": bool(passed), "detail": str(detail or "")[:300],
                                   "at": iso()}
            row["state"] = "verified" if passed else "refuted"
            self._save()
            return dict(row)

    # ------------------------------------------------------------------ contract
    def contract(self, fields: dict, *, call: str = "") -> dict:
        if not isinstance(fields, dict):
            raise Refused("contract-shape", "a contract must be an object")
        missing = [name for name in CONTRACT_FIELDS if not fields.get(name)]
        if missing:
            raise Refused("contract-field", ", ".join(missing))
        scope = fields.get("scope")
        constraints = fields.get("constraints")
        evidence = fields.get("evidence")
        if not all(isinstance(item, list) and item for item in (scope, constraints, evidence)):
            raise Refused("contract-list", "scope, constraints and evidence must be non-empty lists")
        resources = fields.get("resources")
        if not isinstance(resources, dict) or not resources:
            raise Refused("contract-resources", "resources must be a non-empty object")
        row = {
            "call": str(call or ""), "mission": " ".join(str(fields["mission"]).split())[:500],
            "scope": [str(item)[:120] for item in scope],
            "constraints": [str(item)[:240] for item in constraints],
            "resources": {str(key)[:80]: value for key, value in list(resources.items())[:24]},
            "evidence": [str(item)[:240] for item in evidence],
            "deliverable": " ".join(str(fields["deliverable"]).split())[:300],
            "stop": " ".join(str(fields["stop"]).split())[:300],
            "at": iso(),
        }
        with self.lock:
            self.contracts = (self.contracts + [row])[-MAX_ROWS:]
            self._save()
        return row

    # ------------------------------------------------------------------ chain
    def duration(self, text: str) -> dict:
        """Von's chain rule for a computable duration, with its spans retained."""
        source = " ".join(str(text or "").split())[:500]
        matches = list(DURATION.finditer(source))
        if not matches:
            raise Refused("chain-not-computable", "no duration span was found")
        hours = 0.0
        spans = []
        for match in matches:
            unit = match.group("unit").lower()
            value = float(match.group("value"))
            hours += value * UNIT_HOURS[unit]
            spans.append({"text": match.group(0), "value": value, "unit": unit,
                          "start": match.start(), "end": match.end()})
        return {"schema": "popit.civilian-chain/1", "text": source, "hours": round(hours, 6),
                "spans": spans, "operator": "add_duration", "at": iso()}

    # ------------------------------------------------------------------ C9 life
    @staticmethod
    def _family_life():
        path = next((item for item in FAMILY_LIFE_PATHS if item.exists()), None)
        if path is None:
            raise Refused("civilian-life-absent",
                          "openlock_modern/tools/cua_civilian.py is not on this host")
        try:
            spec = importlib.util.spec_from_file_location("popit_family_civilian_life", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as error:  # noqa: BLE001 - the refusal names the family path
            raise Refused("civilian-life-load", f"{path}: {error}"[:300]) from error
        return module

    def _life(self, lane: str) -> dict:
        citizen = " ".join(str(lane or "").split())[:60]
        if not citizen:
            raise Refused("civilian-lane", "a life needs a lane")
        module = self._family_life()
        with self.lock:
            row = self.life_states.get(citizen)
            if not row:
                row = module.new_state(f"civilian:{citizen}")
            try:
                row = module.normalize_state(row, f"civilian:{citizen}")
            except module.Refusal as error:
                raise Refused(error.code, error.detail) from error
            self.life_states[citizen] = row
            return copy.deepcopy(row)

    def _life_snapshot(self, row: dict) -> dict:
        try:
            return self._family_life().snapshot(row)
        except Refused:
            return {"schema": "civilian.life/1", "id": row.get("id") if isinstance(row, dict) else None,
                    "condition": "unknown", "needs": {}, "state": "unreadable"}

    def life_state(self, lane: str) -> dict:
        row = self._life(lane)
        return self._life_snapshot(row)

    def life_tick(self, lane: str, opportunities: list[dict] | None = None,
                  *, apply_care: bool = False) -> dict:
        module = self._family_life()
        row = self._life(lane)
        try:
            row, decision = module.tick(row, opportunities)
            if apply_care and decision.get("kind") == "care":
                row = module.apply_decision(row, decision)
        except module.Refusal as error:
            raise Refused(error.code, error.detail) from error
        citizen = " ".join(str(lane or "").split())[:60]
        with self.lock:
            self.life_states[citizen] = row
            self._save()
        return {"life": self._life_snapshot(row), "decision": decision,
                "applied": decision.get("kind") == "care" and apply_care}

    def life_apply(self, lane: str, decision: dict) -> dict:
        module = self._family_life()
        row = self._life(lane)
        kind = str((decision or {}).get("kind") or "")
        try:
            if kind == "decline" and (decision or {}).get("opportunity"):
                row = module.record_declined_job(row, decision)
            elif kind == "work" and (decision or {}).get("delegate_to"):
                row = module.record_delegation(row, decision)
            elif kind == "complete":
                row = module.complete_work(row, decision)
            else:
                row = module.apply_decision(row, decision)
        except module.Refusal as error:
            raise Refused(error.code, error.detail) from error
        citizen = " ".join(str(lane or "").split())[:60]
        with self.lock:
            self.life_states[citizen] = row
            self._save()
        return self._life_snapshot(row)

    def life_steps(self, lane: str, decision: dict) -> list[dict]:
        module = self._family_life()
        root = self.path.parent / "civilian-steps"
        try:
            return module.steps_for(decision, root, root)
        except module.Refusal as error:
            raise Refused(error.code, error.detail) from error

    def context(self, lane: str) -> str:
        """The family state a lane should carry into an answer.

        This is deliberately small: identity, C9 needs, condition and the care floor.
        It never contains a key, a transcript, or another lane's private memory.
        """
        citizen = " ".join(str(lane or "").split())[:60]
        if not citizen:
            return ""
        with self.lock:
            identity = dict(self.identities.get(citizen) or {})
            row = self.life_states.get(citizen)
        parts: list[str] = []
        if identity:
            parts.append(
                f"Feeling identity: {identity.get('path')} ({identity.get('hex')}); "
                f"source {identity.get('source')} at confidence {identity.get('confidence')}."
            )
        if row:
            snapshot = self._life_snapshot(row)
            needs = snapshot.get("needs") or {}
            low = [name for name, value in needs.items()
                   if isinstance(value, (int, float)) and value < SEEK_FLOOR]
            need_text = ", ".join(f"{name} {float(value):.2f}" for name, value in needs.items())
            parts.append(
                f"C9 life condition: {snapshot.get('condition', 'unknown')}; needs {need_text}. "
                + (f"Below the care floor: {', '.join(low)}. Name care before accepting new work. "
                   if low else "No need is below the care floor. ")
                + "A confident decision is not a result until a deterministic check agrees."
            )
        return "\n".join(parts)

    # ------------------------------------------------------------------ operation
    def operation(self, lane: str, text: str, *, contract: dict | None = None,
                  call: str = "") -> dict:
        """The preflight every speaking lane uses, not a display record.

        The language layer must see the C9 condition, the care choice and the contract
        boundary before it writes an answer. A dead lane does not answer. An ill or
        degraded lane may speak, but cannot accept work. A lane below the SEEK floor
        must name care before any new job. A contract without its seven fields is a
        named refusal, and an absent contract can never claim a deliverable.
        """
        citizen = " ".join(str(lane or "").split())[:60]
        if not citizen:
            raise Refused("civilian-lane", "an operation needs a lane")
        question = " ".join(str(text or "").split())[:500]
        row = self._life(citizen)
        snapshot = self._life_snapshot(row)
        needs = snapshot.get("needs") or {}
        condition = str(snapshot.get("condition") or "unknown")
        low = [name for name, value in needs.items()
               if isinstance(value, (int, float)) and value < SEEK_FLOOR]
        scope = dict(contract) if isinstance(contract, dict) else {}
        missing = [name for name in CONTRACT_FIELDS if not scope.get(name)]
        contract_state = "absent" if not scope else ("incomplete" if missing else "scoped")
        voice = lane_gate(citizen)

        if condition == "dead":
            result = self._operation_row(
                citizen, question, call, condition, snapshot, needs, low, scope,
                contract_state, None, "terminal",
                "The failure ladder reached dead; this lane has no capacity to answer.",
            )
            result["allowed"] = False
            result["work_allowed"] = False
            line = voice["terminal"].format(lane=citizen)
            result["refusal"] = {"code": "civilian-terminal",
                                 "detail": f"{citizen} is dead on the C9 ladder",
                                 "line": line}
            result["directive"] = line
            self._record_operation(result)
            return result
        if contract_state == "incomplete":
            result = self._operation_row(
                citizen, question, call, condition, snapshot, needs, low, scope,
                contract_state, None, "terminal",
                "The attached contract is missing " + ", ".join(missing) + ".",
            )
            result["allowed"] = False
            result["work_allowed"] = False
            line = voice["contract"] + " Missing: " + ", ".join(missing) + "."
            result["refusal"] = {"code": "contract-incomplete",
                                 "detail": ", ".join(missing), "line": line}
            result["directive"] = line
            self._record_operation(result)
            return result

        module = self._family_life()
        try:
            decision = module.choose(row)
        except module.Refusal as error:
            raise Refused(error.code, error.detail) from error
        chain = None
        try:
            chain = self.duration(question)
        except Refused:
            chain = None
        work_allowed = condition == "ok" and not low and contract_state == "scoped"
        if low or condition in ("illness", "degraded"):
            state = "care-first"
        elif work_allowed:
            state = "work-allowed"
        else:
            state = "speech-only"
        care = (decision.get("say") or decision.get("reason") or "care comes first")
        care_need = str(decision.get("need") or "")
        care_value = needs.get(care_need)
        care_line = (
            voice["care"].format(need=care_need, value=float(care_value),
                                  action=decision.get("action") or "care")
            if care_need and isinstance(care_value, (int, float)) else
            voice["care"].format(need="care", value=0.0, action="care")
        )
        contract_line = voice["contract"]
        parts = [
            f"Lane role: {voice['role']}.",
            f"C9 condition: {condition}; capacity {snapshot.get('capacity', 0)}. "
            f"Needs: " + ", ".join(f"{name} {float(value):.2f}" for name, value in needs.items()),
            f"C9 choice: {decision.get('kind')} · {care}",
        ]
        if chain:
            parts.append(
                f"Deterministic duration: {chain['hours']:g} hours from "
                + ", ".join(span["text"] for span in chain["spans"])
                + ". Use this exact computed value, not a guess."
            )
        if state == "care-first":
            parts.append(
                "Care is chosen before every offered job. Do not accept, plan or claim new "
                "work. Tell the owner what care is needed in your own words, then stop."
            )
        elif state == "speech-only":
            parts.append(
                "No seven-field contract is attached. You may answer the owner's present "
                "question, but do not claim a deliverable, completion or accepted job."
            )
        else:
            parts.append(
                "The contract is scoped and no need is below the care floor. Answer only "
                "inside its scope; a request outside scope is a named refusal."
            )
        if scope:
            parts.append(
                f"Contract mission: {scope.get('mission')} · scope: {scope.get('scope')} · "
                f"stop: {scope.get('stop')} · evidence due: {scope.get('evidence')}"
            )
            parts.append(
                "Do not claim the deliverable until the evidence field is satisfied by an "
                "observed machine result. The turn itself has no calibrated confidence; its "
                "result stays unverified until a deterministic check agrees."
            )
        directive = "\n".join(parts)
        result = self._operation_row(
            citizen, question, call, condition, snapshot, needs, low, scope,
            contract_state, decision, state, directive,
        )
        result.update({"allowed": True, "work_allowed": work_allowed,
                       "refusal": None, "directive": directive, "care_line": care_line,
                       "contract_line": contract_line})
        self._record_operation(result)
        return result

    def _operation_row(self, citizen: str, question: str, call: str, condition: str,
                       snapshot: dict, needs: dict, low: list[str], scope: dict,
                       contract_state: str, decision: dict | None, state: str,
                       reason: str) -> dict:
        return {
            "schema": OPERATION_SCHEMA, "id": f"op-{int(datetime.datetime.now().timestamp())}-{len(self.operations) + 1}",
            "at": iso(), "lane": citizen, "call": str(call or ""),
            "question": question, "condition": condition,
            "capacity": snapshot.get("capacity"), "needs": dict(needs),
            "care_floor": list(low), "contract_state": contract_state,
            "contract": {name: scope.get(name) for name in ("mission", "scope", "stop", "evidence")
                         if scope.get(name)},
            "decision": ({key: decision.get(key) for key in ("kind", "action", "need", "reason", "say")
                          if decision.get(key)} if decision else None),
            "state": state, "reason": reason, "answer": "", "gate": "unverified",
            "verification_required": True,
        }

    def _record_operation(self, row: dict) -> None:
        with self.lock:
            self.operations = (self.operations + [row])[-MAX_ROWS:]
            self._save()

    def record_operation(self, operation_id: str, answer: str,
                         *, confidence: float | None = None) -> dict:
        """Attach the lane's actual answer to its preflight; never invent confidence."""
        with self.lock:
            row = next((item for item in reversed(self.operations)
                        if item.get("id") == operation_id), None)
            if row is None:
                raise Refused("operation-unknown", str(operation_id))
            row["answer"] = " ".join(str(answer or "").split())[:1200]
            if confidence is None:
                row["gate"] = "unverified"
                row["state"] = "answered-unverified"
            else:
                value = self._probability(confidence, "confidence")
                row["confidence"] = value
                row["gate"] = "automatic" if value >= CONFIDENCE_GATE else "escalate"
                row["state"] = ("answered-awaiting-verification"
                                if row["gate"] == "automatic" else "answered-escalated")
            self._save()
            return dict(row)

    @staticmethod
    def _probability(value, name: str) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise Refused("decision-probability", f"{name} must be a number")
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise Refused("decision-probability", f"{name} must be between 0 and 1")
        return round(number, 4)
