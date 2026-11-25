"""External agents: owner-issued enrollment, verified contacts and WebRTC signaling.

The phone shell already has a local voice loop. This module is the missing edge for
an agent outside that loop. It deliberately does not invent a carrier or a second
identity system:

* The owner opens a one-time enrollment code on the phone.
* The agent signs the registration payload with an Ed25519 key.
* The host creates a server-side contact, a Popit line id and a scratch workspace.
* A call is a signed WebRTC offer; the phone answers with its SDP and ICE candidates.

A Popit line id is not an E.164 telephone number. It is a local line identifier for
the phone app. A PSTN adapter would need a carrier account, a public number and a
provider callback; none of those are present in this checkout, so it is refused
explicitly rather than implied by a synthetic number.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import pathlib
import re
import secrets
import threading
from urllib.parse import urlsplit

import envelope

SCHEMA = "popit.external-agents/1"
REGISTRATION_SCHEMA = "popit.agent-registration/1"
CALL_SCHEMA = "popit.agent-call/1"
MAX_OFFER = 200_000
MAX_AGE_SECONDS = 300
NONCE_RE = re.compile(r"^[0-9a-f]{32,64}$")
NUMBER_RE = re.compile(r"^\+?[0-9][0-9 ().-]{3,23}$")
# What an outside agent may ask for before the owner decides. A scope is a name for a
# slice of the owner's data, not a permission the agent holds: nothing is shared until the
# owner answers with consent naming the scopes they chose.
SCOPE_ALLOW = ("profile", "contacts", "archive")


def _scope_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise Refused("call-request-scope", "scopes must be a list")
    chosen: list[str] = []
    for item in value:
        name = _clean(item, 24).lower()
        if name not in SCOPE_ALLOW:
            raise Refused("call-request-scope", f"{name or 'empty'} is not a shareable scope")
        if name not in chosen:
            chosen.append(name)
    return chosen


def _request(value: object) -> dict:
    """A signed ask that travels with the call; it carries no data of its own."""
    if value in (None, "", {}):
        return {"scopes": [], "note": ""}
    if not isinstance(value, dict):
        raise Refused("call-request", "request must be an object with scopes and note")
    return {"scopes": _scope_list(value.get("scopes")), "note": _clean(value.get("note"), 160)}


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _iso(value: datetime.datetime | None = None) -> str:
    return (value or _now()).isoformat().replace("+00:00", "Z")


def _clean(value: object, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _slug(value: str) -> str:
    folded = re.sub(r"[^a-z0-9]+", "-", _clean(value, 80).lower())
    return folded.strip("-")[:40] or "agent"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _code_hash(code: str) -> str:
    return hashlib.sha256(("popit-enrollment:" + code).encode("utf-8")).hexdigest()


class ExternalAgents:
    """One small JSON authority for external identities, contacts and call offers."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "external-agents.json"
        self.workspaces = self.root / "workspaces"
        self.workspaces.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.agents: list[dict] = []
        self.calls: list[dict] = []
        self.codes: list[dict] = []
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
        self.agents = [row for row in value.get("agents", [])
                       if isinstance(row, dict) and row.get("id")]
        self.calls = [row for row in value.get("calls", [])
                      if isinstance(row, dict) and row.get("id")]
        self.codes = [row for row in value.get("codes", [])
                      if isinstance(row, dict) and row.get("code_hash")]

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"schema": SCHEMA, "agents": self.agents,
                   "calls": self.calls, "codes": self.codes}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        temporary.replace(self.path)

    @staticmethod
    def _contact(row: dict) -> dict:
        keys = ("id", "name", "line", "line_kind", "status", "endpoint",
                "number", "number_verified", "fingerprint", "workspace",
                "verified_at", "last_seen", "calls")
        return {key: row.get(key) for key in keys if row.get(key) not in (None, "")}

    def contacts(self) -> list[dict]:
        with self.lock:
            rows = [self._contact(row) for row in self.agents
                    if row.get("status") == "verified"]
            return sorted(rows, key=lambda row: str(row.get("name") or "").casefold())

    def state(self) -> dict:
        with self.lock:
            ringing = sum(1 for row in self.calls if row.get("state") == "ringing")
            active = sum(1 for row in self.calls if row.get("state") == "active")
            return {"schema": SCHEMA, "contacts": len(self.contacts()),
                    "ringing": ringing, "active": active,
                    "pending_codes": sum(1 for row in self.codes
                                         if not row.get("used")
                                         and str(row.get("expires_at") or "") > _iso())}

    def open_enrollment(self, name: str = "external agent") -> dict:
        """Mint one one-time owner invitation; only its hash is stored."""
        display = _clean(name, 60) or "external agent"
        code = secrets.token_urlsafe(24)
        now = _now()
        with self.lock:
            self.codes = [row for row in self.codes
                          if not row.get("used") and str(row.get("expires_at") or "") > _iso(now)]
            self.codes.append({
                "id": "invite-" + secrets.token_hex(6),
                "name": display,
                "code_hash": _code_hash(code),
                "created_at": _iso(now),
                "expires_at": _iso(now + datetime.timedelta(minutes=10)),
                "used": False,
            })
            self._save()
        return {"code": code, "name": display,
                "expires_at": _iso(now + datetime.timedelta(minutes=10))}

    def _enrollment(self, code: str) -> dict:
        digest = _code_hash(code)
        row = next((item for item in self.codes if item.get("code_hash") == digest), None)
        if row is None:
            raise Refused("enrollment-code", "the one-time code is unknown")
        if row.get("used"):
            raise Refused("enrollment-used", "the one-time code was already used")
        if str(row.get("expires_at") or "") <= _iso():
            raise Refused("enrollment-expired", "the one-time code has expired")
        return row

    def enroll(self, body: dict) -> dict:
        """Verify a signed registration, then create a contact and scratch workspace."""
        if not isinstance(body, dict):
            raise Refused("enrollment-shape", "registration must be a JSON object")
        code = _clean(body.get("code"), 200)
        name = _clean(body.get("name"), 60)
        endpoint = _clean(body.get("endpoint"), 500)
        public_key = str(body.get("public_key") or "").strip()
        signature = _clean(body.get("signature"), 5000)
        issued_at = _clean(body.get("issued_at"), 40)
        # The number is the agent's own claim about itself, recorded so the owner can ring it
        # back. It is never verified here; the signature is what the contact is trusted for.
        number = _clean(body.get("number"), 24)
        if number and not NUMBER_RE.fullmatch(number):
            raise Refused("enrollment-number",
                          "a declared number may use digits, spaces, +, -, ( and )")
        if not code or not name or not endpoint or not public_key or not signature or not issued_at:
            raise Refused("enrollment-field",
                          "code, name, endpoint, public_key, signature and issued_at are required")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise Refused("enrollment-endpoint", "the agent endpoint must be https")
        if len(public_key) > 4096 or len(signature) > 5000:
            raise Refused("enrollment-oversize", "public key or signature is too large")
        try:
            issued = envelope.parse_iso(issued_at)
        except envelope.Refused as error:
            raise Refused("enrollment-time", error.detail) from error
        now = _now()
        if issued > now + datetime.timedelta(seconds=120) or now - issued > datetime.timedelta(seconds=MAX_AGE_SECONDS):
            raise Refused("enrollment-time", "registration is outside the five-minute window")
        try:
            fingerprint = envelope.fingerprint(public_key)
        except envelope.Refused as error:
            raise Refused("enrollment-public-key", error.detail) from error
        payload = {"schema": REGISTRATION_SCHEMA, "name": name, "endpoint": endpoint,
                   "public_key": public_key, "issued_at": issued_at, "code": code}
        if number:
            payload["number"] = number
        if not envelope.verify_payload(payload, signature, public_key):
            raise Refused("enrollment-signature", "the registration signature does not verify")
        with self.lock:
            invitation = self._enrollment(code)
            if any(str(row.get("name") or "").casefold() == name.casefold() for row in self.agents):
                raise Refused("agent-exists", name)
            agent_id = _slug(name) + "-" + secrets.token_hex(2)
            line = "POPIT-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(1).upper()
            workspace = self.workspaces / agent_id
            workspace.mkdir(parents=True, exist_ok=True)
            contact = {
                "id": agent_id, "name": name, "line": line,
                "line_kind": "popit-webrtc", "status": "verified",
                "endpoint": endpoint, "public_key": public_key,
                "number": number, "number_verified": False,
                "fingerprint": fingerprint, "workspace": str(workspace),
                "verified_at": _iso(), "created_at": _iso(), "last_seen": "",
                "calls": 0, "nonces": [],
            }
            invitation["used"] = True
            invitation["used_at"] = _iso()
            invitation["agent_id"] = agent_id
            self.agents.append(contact)
            (workspace / "README.md").write_text(
                "# Popit external agent workspace\n\n"
                f"This scratch workspace belongs to **{name}**.\n\n"
                f"- Popit line: `{line}`\n"
                + (f"- Declared number: `{number}` (unverified)\n" if number else "")
                + f"- Fingerprint: `{fingerprint}`\n"
                f"- Enrollment: `{REGISTRATION_SCHEMA}`\n\n"
                "Keep scratch files here. This directory is not a shell, a host credential "
                "store or a path into the Popit checkout.\n",
                encoding="utf-8",
            )
            (workspace / "contact.json").write_text(
                json.dumps({**self._contact(contact), "schema": SCHEMA}, indent=2,
                           ensure_ascii=False) + "\n", encoding="utf-8")
            self._save()
        return {"ok": True, "contact": self._contact(contact),
                "workspace": str(workspace), "schema": REGISTRATION_SCHEMA}

    def _agent(self, agent_id: str) -> dict:
        row = next((item for item in self.agents
                    if item.get("id") == str(agent_id or "")
                    and item.get("status") == "verified"), None)
        if row is None:
            raise Refused("agent-unknown", str(agent_id or ""))
        return row

    def _call(self, call_id: str) -> dict:
        row = next((item for item in self.calls if item.get("id") == str(call_id or "")), None)
        if row is None:
            raise Refused("call-unknown", str(call_id or ""))
        return row

    def _ticket(self, body: dict, fields: tuple[str, ...]) -> dict:
        agent = self._agent(str(body.get("agent") or ""))
        nonce = _clean(body.get("nonce"), 64)
        issued_at = _clean(body.get("issued_at"), 40)
        signature = _clean(body.get("signature"), 5000)
        if not NONCE_RE.fullmatch(nonce):
            raise Refused("call-nonce", "nonce must be 32-64 lowercase hex characters")
        if not issued_at or not signature:
            raise Refused("call-ticket", "agent, nonce, issued_at and signature are required")
        try:
            issued = envelope.parse_iso(issued_at)
        except envelope.Refused as error:
            raise Refused("call-ticket", error.detail) from error
        now = _now()
        if issued > now + datetime.timedelta(seconds=120) or now - issued > datetime.timedelta(seconds=MAX_AGE_SECONDS):
            raise Refused("call-ticket", "the signed ticket is outside the five-minute window")
        payload = {"schema": CALL_SCHEMA, "agent": agent["id"], "nonce": nonce,
                   "issued_at": issued_at}
        for field in fields:
            if field not in payload and body.get(field) is not None:
                payload[field] = body.get(field)
        if not envelope.verify_payload(payload, signature, agent["public_key"]):
            raise Refused("call-signature", "the call ticket signature does not verify")
        if nonce in (agent.get("nonces") or []):
            raise Refused("call-replay", nonce)
        return agent

    def open_call(self, body: dict) -> dict:
        """Admit a signed SDP offer from a verified agent and ring the phone."""
        offer = str(body.get("offer") or "").strip()
        if not offer or len(offer) > MAX_OFFER or "v=0" not in offer:
            raise Refused("call-offer", "a WebRTC SDP offer is required")
        asked = _request(body.get("request"))
        with self.lock:
            agent = self._ticket(body, ("offer", "request"))
            call_id = "extcall-" + secrets.token_hex(12)
            call = {
                "id": call_id, "schema": CALL_SCHEMA, "agent": agent["id"],
                "name": agent["name"], "line": agent["line"],
                "number": agent.get("number") or "", "request": asked,
                "consent": {"granted": False, "scopes": [], "at": ""},
                "state": "ringing", "offer": offer, "answer": "",
                "agent_ice": [], "phone_ice": [],
                "created_at": _iso(), "answered_at": "", "ended_at": "",
            }
            stale = _iso(_now() - datetime.timedelta(minutes=10))
            for row in self.calls:
                if row.get("state") == "ringing" and str(row.get("created_at") or "") < stale:
                    row["state"] = "missed"
                    row["ended_at"] = _iso()
            agent["nonces"] = ((agent.get("nonces") or []) + [body["nonce"]])[-40:]
            agent["last_seen"] = _iso()
            agent["calls"] = int(agent.get("calls") or 0) + 1
            self.calls = (self.calls + [call])[-80:]
            self._save()
        return {"ok": True, "call_id": call_id, "state": "ringing",
                "contact": self._contact(agent)}

    def incoming(self) -> list[dict]:
        with self.lock:
            return [{"call_id": row["id"], "name": row["name"], "line": row["line"],
                     "number": row.get("number") or "",
                     "request": row.get("request") or {"scopes": [], "note": ""},
                     "state": row["state"], "offer": row["offer"], "created_at": row["created_at"]}
                    for row in self.calls if row.get("state") == "ringing"]

    @staticmethod
    def _decide(call: dict, value: object) -> dict:
        """The owner's decision, bounded by what the agent actually asked for."""
        if not isinstance(value, dict):
            raise Refused("call-consent", "consent must be an object")
        granted = bool(value.get("granted"))
        asked = (call.get("request") or {}).get("scopes") or []
        chosen = _scope_list(value.get("scopes"))
        for scope in chosen:
            if scope not in asked:
                raise Refused("call-consent-scope",
                              f"{scope} was not part of the signed request")
        return {"granted": granted, "scopes": chosen if granted else [], "at": _iso()}

    def consent(self, body: dict) -> dict:
        """Record the owner's answer to a signed request before any media is negotiated.

        The decision belongs to the owner, not to whether a microphone opened: a phone that
        cannot capture audio can still answer "nothing" or name the scopes it will share.
        """
        call_id = _clean(body.get("call_id"), 80)
        with self.lock:
            call = self._call(call_id)
            if call.get("state") != "ringing":
                raise Refused("call-state", f"{call_id} is {call.get('state')}")
            call["consent"] = self._decide(call, body.get("consent"))
            self._save()
        return {"ok": True, "call_id": call_id, "state": call.get("state"),
                "consent": call["consent"]}

    def answer(self, body: dict) -> dict:
        call_id = _clean(body.get("call_id"), 80)
        answer = str(body.get("answer") or "").strip()
        if not answer or len(answer) > MAX_OFFER or "v=0" not in answer:
            raise Refused("call-answer", "a WebRTC SDP answer is required")
        with self.lock:
            call = self._call(call_id)
            if call.get("state") != "ringing":
                raise Refused("call-state", f"{call_id} is {call.get('state')}")
            if "consent" in body:
                call["consent"] = self._decide(call, body.get("consent"))
            call["answer"] = answer
            call["state"] = "active"
            call["answered_at"] = _iso()
            self._save()
        return {"ok": True, "call_id": call_id, "state": "active"}

    def state_for(self, body: dict) -> dict:
        call_id = _clean(body.get("call_id"), 80)
        with self.lock:
            call = self._call(call_id)
            agent_id = _clean(body.get("agent"), 80)
            if agent_id and agent_id != call.get("agent"):
                raise Refused("call-owner", "this call belongs to another agent")
            return {"ok": True, "call_id": call_id, "state": call.get("state"),
                    "answer": call.get("answer") or "", "agent_ice": call.get("agent_ice") or [],
                    "phone_ice": call.get("phone_ice") or [],
                    "name": call.get("name"), "line": call.get("line"),
                    "request": call.get("request") or {"scopes": [], "note": ""},
                    "consent": call.get("consent") or {"granted": False, "scopes": [], "at": ""}}

    def ice(self, body: dict) -> dict:
        call_id = _clean(body.get("call_id"), 80)
        side = _clean(body.get("side"), 10)
        if side not in ("agent", "phone"):
            raise Refused("call-ice-side", "side must be agent or phone")
        candidate = body.get("candidate")
        if candidate is not None and not isinstance(candidate, dict):
            raise Refused("call-ice", "candidate must be an object or null")
        with self.lock:
            call = self._call(call_id)
            if call.get("state") not in ("ringing", "active"):
                raise Refused("call-state", f"{call_id} is {call.get('state')}")
            bucket = call.setdefault(side + "_ice", [])
            if len(bucket) < 64:
                bucket.append(candidate)
            self._save()
        return {"ok": True, "call_id": call_id, "side": side, "queued": len(bucket)}

    def end(self, body: dict) -> dict:
        call_id = _clean(body.get("call_id"), 80)
        outcome = "declined" if str(body.get("outcome") or "") == "declined" else "ended"
        with self.lock:
            call = self._call(call_id)
            if call.get("state") in ("ended", "declined"):
                return {"ok": True, "call_id": call_id, "state": call["state"]}
            call["state"] = outcome
            call["ended_at"] = _iso()
            self._save()
        return {"ok": True, "call_id": call_id, "state": outcome}
