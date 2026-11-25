"""Verify an outside agent holding only its own key can reach this shell's phone line.

The probe plays the external service end to end from a scratch workspace: it mints its own
Ed25519 key there, signs its registration and call tickets, and talks to a running shell over
HTTP. The shell is the owner's side; nothing here holds the owner's key or a copy of their
contacts book.

What is checked, in order:

* an unsigned registration is refused before any code is spent;
* the owner's one-time invite admits a signed registration and creates a server-side contact
  with a Popit line and the agent's own declared number (recorded, never verified);
* the contact appears in the owner's contact book;
* a call ticket signed with the same key rings the phone, and replaying its nonce is refused;
* the call carries a signed request for named scopes only;
* the owner's answer grants a subset of those scopes, and a grant for a scope that was never
  asked for is refused;
* the state the agent reads back carries the request and exactly what was granted;
* either side ends the call.

Run against a live shell on loopback::

    python tools/external_call_verify.py --origin http://127.0.0.1:5207

The probe uses HTTP on loopback, which the host treats as the machine itself. It does not
claim that a public address, a TURN relay or a carrier number exists: those remain separate
blockers recorded in docs/external-agents.md.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import secrets
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import envelope  # noqa: E402

OFFER = (
    "v=0\r\n"
    "o=- 4611731400430051336 2 IN IP4 127.0.0.1\r\n"
    "s=-\r\n"
    "t=0 0\r\n"
    "a=group:BUNDLE 0\r\n"
    "a=mid:0\r\n"
    "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    "a=sendrecv\r\n"
)
ANSWER = OFFER.replace("a=sendrecv", "a=recvonly")


class Probe:
    def __init__(self, origin: str) -> None:
        self.origin = origin.rstrip("/")
        self.failures = 0

    def call(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.origin + path, data=data, method="POST" if body is not None else "GET")
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw or "{}")
            except json.JSONDecodeError:
                return error.code, {"raw": raw}

    def check(self, name: str, condition: bool, detail: object = "") -> None:
        if condition:
            print(f"PASS {name}")
            return
        self.failures += 1
        print(f"FAIL {name} {detail}")


def iso() -> str:
    return envelope.iso(envelope.utc_now())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:5207")
    parser.add_argument("--name", default="")
    parser.add_argument("--number", default="+15550100")
    parser.add_argument("--keep", action="store_true", help="keep the scratch workspace")
    parser.add_argument("--ring", action="store_true",
                        help="stop while the phone is ringing, so the owner surface can be seen")
    args = parser.parse_args()

    probe = Probe(args.origin)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="popit-scratch-agent-"))
    private = scratch / "agent-private.pem"
    public = scratch / "agent-public.pem"
    envelope.keygen(private, public)
    public_key = public.read_text(encoding="utf-8").strip()
    name = args.name or f"Scratch agent {secrets.token_hex(3)}"
    print(f"scratch workspace: {scratch}")
    print(f"agent public key: {envelope.fingerprint(public_key)}")

    # 1. An unsigned registration must be refused, and must not spend the invite.
    status, receipt = probe.call("/api/toast/external/enrollment", {"name": name})
    probe.check("invite-issued", status == 200 and bool(receipt.get("code")), receipt)
    code = str(receipt.get("code") or "")
    if not code:
        return 1

    issued_at = iso()
    registration = {
        "schema": "popit.agent-registration/1",
        "name": name,
        "endpoint": "https://agent.example/mcp",
        "public_key": public_key,
        "issued_at": issued_at,
        "code": code,
        "number": args.number,
    }
    status, receipt = probe.call("/api/toast/external/enroll", {**registration, "signature": "bm90LWEtc2ln"})
    refused = (receipt.get("refused") or {}).get("code")
    probe.check("unsigned-registration-refused", status >= 400 and refused == "enrollment-signature", receipt)

    # 2. The same invite still works with a signature from the workspace key.
    signature = envelope.sign_payload(registration, private)
    status, receipt = probe.call("/api/toast/external/enroll", {**registration, "signature": signature})
    contact = receipt.get("contact") or {}
    probe.check("signed-registration-accepted", status == 200 and bool(contact.get("id")), receipt)
    probe.check("popit-line-issued", str(contact.get("line") or "").startswith("POPIT-"), contact)
    probe.check("declared-number-recorded",
                contact.get("number") == args.number and contact.get("number_verified") is False, contact)
    workspace = pathlib.Path(str(receipt.get("workspace") or ""))
    probe.check("scratch-workspace-created", workspace.is_dir() and (workspace / "contact.json").is_file(), workspace)
    agent_id = str(contact.get("id") or "")
    if not agent_id:
        return 1

    # 3. The owner's contact book is server-side: a browser's storage is not involved here.
    status, receipt = probe.call("/api/toast/external/contacts")
    rows = receipt.get("contacts") or []
    mine = next((row for row in rows if row.get("id") == agent_id), None)
    probe.check("contact-in-owner-book", status == 200 and mine is not None, receipt)
    probe.check("contact-number-in-book", bool(mine) and mine.get("number") == args.number, mine)

    def ticket(nonce: str, extra: dict, key=private) -> dict:
        payload = {"schema": "popit.agent-call/1", "agent": agent_id, "nonce": nonce,
                   "issued_at": iso(), **extra}
        return {**payload, "signature": envelope.sign_payload(payload, key)}

    # 4. A call signed with the workspace key rings the phone.
    nonce = secrets.token_hex(16)
    body = ticket(nonce, {"offer": OFFER})
    status, receipt = probe.call("/api/toast/external/call", body)
    probe.check("signed-call-rings", status == 200 and receipt.get("state") == "ringing", receipt)
    first_call = str(receipt.get("call_id") or "")

    status, receipt = probe.call("/api/toast/external/call", body)
    refused = (receipt.get("refused") or {}).get("code")
    probe.check("replayed-nonce-refused", status >= 400 and refused == "call-replay", receipt)

    # 5. A call carrying a data request, signed in the same ticket.
    asked = {"scopes": ["profile", "contacts"], "note": "to answer you with your own context"}
    status, receipt = probe.call("/api/toast/external/call", ticket(secrets.token_hex(16), {"offer": OFFER, "request": asked}))
    probe.check("call-with-request-rings", status == 200 and receipt.get("state") == "ringing", receipt)
    call_id = str(receipt.get("call_id") or "")
    if not call_id:
        return 1

    status, receipt = probe.call("/api/toast/external/incoming")
    call = next((row for row in receipt.get("calls") or [] if row.get("call_id") == call_id), None)
    probe.check("phone-sees-request", bool(call) and (call.get("request") or {}).get("scopes") == ["profile", "contacts"], call)
    if args.ring:
        print(f"ringing call: {call_id}")
        print(f"contact: {agent_id} · {contact.get('line')} · {args.number}")
        return 0 if not probe.failures else 1

    # 6. The owner may only grant what was asked for, and records the decision before media.
    status, receipt = probe.call("/api/toast/external/call/consent", {
        "call_id": call_id, "consent": {"granted": True, "scopes": ["archive"]},
    })
    refused = (receipt.get("refused") or {}).get("code")
    probe.check("unrequested-scope-refused", status >= 400 and refused == "call-consent-scope", receipt)

    status, receipt = probe.call("/api/toast/external/call/consent", {
        "call_id": call_id, "consent": {"granted": True, "scopes": ["profile"]},
    })
    consent = receipt.get("consent") or {}
    probe.check("owner-grants-a-subset",
                status == 200 and receipt.get("state") == "ringing"
                and consent.get("granted") is True and consent.get("scopes") == ["profile"], receipt)

    status, receipt = probe.call("/api/toast/external/call/answer", {"call_id": call_id, "answer": ANSWER})
    probe.check("answer-keeps-the-grant", status == 200 and receipt.get("state") == "active", receipt)

    status, receipt = probe.call("/api/toast/external/call/state", {"call_id": call_id, "agent": agent_id})
    consent = receipt.get("consent") or {}
    probe.check("agent-reads-exact-grant",
                receipt.get("state") == "active"
                and consent.get("granted") is True and consent.get("scopes") == ["profile"], receipt)
    probe.check("agent-reads-answer", "v=0" in str(receipt.get("answer") or ""), receipt)

    status, receipt = probe.call("/api/toast/external/call/end", {"call_id": call_id})
    probe.check("call-ended", status == 200 and receipt.get("state") == "ended", receipt)

    if first_call:
        probe.call("/api/toast/external/call/end", {"call_id": first_call, "outcome": "declined"})

    if not args.keep:
        for path in sorted(scratch.glob("*"), reverse=True):
            if path.is_file():
                path.unlink()
        try:
            scratch.rmdir()
        except OSError:
            pass
    print(f"\n{probe.failures} failure(s)" if probe.failures else "\nall external-agent checks passed")
    return 1 if probe.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
