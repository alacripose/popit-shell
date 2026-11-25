# External agents: enrollment, verified contacts and the phone line

This is the implementation contract for an outside agent to reach the owner's phone
surface. It is deliberately narrower than a telephone carrier integration.

## Decision

Use **WebRTC first**, not PSTN.

- The phone app already runs as a secure-origin PWA with microphone capture.
- WebRTC gives the phone app a real audio peer without buying a carrier number or
  creating a second telephone identity.
- The external agent's media library supplies the SDP offer. The Popit host does not
  synthesize a fake offer or claim that a browser audio token is a phone call.
- PSTN is a separate adapter. It is **blocked**, not simulated, because this checkout
  has no carrier account, no public number and no callback secret.

The lines in the contact book are **Popit line identifiers** such as `POPIT-25A8-9E`,
not E.164 telephone numbers. Do not route a `POPIT-...` value to a telephone dialer.

## Identity model

The identity is an Ed25519 public key held by the external agent. The host stores only
the public key and its BLAKE3 fingerprint.

1. The owner opens a one-time enrollment code in the phone app, **Agents → Invite**.
   The code expires after ten minutes and is stored only as a SHA-256 hash.
2. The agent creates an Ed25519 key pair. The private key stays on the agent machine.
3. The agent builds the canonical registration object:

   ```json
   {
     "schema": "popit.agent-registration/1",
     "name": "Ada's agent",
     "endpoint": "https://agent.example/mcp",
     "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
     "issued_at": "2026-11-24T15:00:00Z",
     "code": "one-time-code",
     "number": "+15550100"
   }
   ```

   `number` is optional and is the agent's own claim about how to reach it. It is stored
   with `number_verified: false` and shown that way in the contact book: the signature is
   what makes the contact trusted, and nothing here proves a telephone number belongs to
   the agent. The key is signed over exactly the fields present, so the number (when given)
   is part of the signed payload.

   It signs the canonical JSON — sorted keys, no whitespace, UTF-8 — and posts the
   object with `signature`.
4. The host checks the code, the five-minute clock window and the signature before it
   consumes the code. A failed signature does not burn the code.
5. On success the host creates:
   - a server-side contact;
   - a generated Popit line id (not a carrier number);
   - a scratch workspace under `runlogs/toast/external/workspaces/<agent-id>/`;
   - a `contact.json` and a human-readable `README.md`.

The agent response includes its contact and workspace path. The owner's contact book
is server-side; it is not the `call-client` browser `localStorage` book.

## Call flow (WebRTC)

1. The agent creates an SDP offer from its WebRTC runtime.
2. It signs a ticket with its private key:

   ```json
   {
     "schema": "popit.agent-call/1",
     "agent": "agent-id",
     "nonce": "32-64 lowercase hex",
     "issued_at": "2026-11-24T15:01:00Z",
     "offer": "v=0\r\n..."
   }
   ```

3. `POST /api/toast/external/call` verifies the agent, the signature, the clock and
   the nonce, then creates a `ringing` call.
4. The phone app polls `/api/toast/external/incoming`, shows the verified name and
   line, and the owner accepts.
5. The phone creates a `RTCPeerConnection`, applies the offer, creates an answer, and
   posts it to `/api/toast/external/call/answer`.
6. Both sides exchange ICE candidates through `/api/toast/external/call/ice`.
7. The phone attaches the remote audio stream to the call sheet. The agent polls
   `/api/toast/external/call/state` for the answer and the phone's ICE candidates.
8. Either side ends the call with `/api/toast/external/call/end`.

The phone uses host ICE candidates only (`iceServers: []`). That is sufficient on the
same LAN. It is not sufficient across NAT or the public internet.

## Data request and owner consent

A call may carry a **signed request** for named scopes. The request is part of the same
signature as the offer, so an agent cannot ask for one thing and later claim another. The
allowlist is `profile`, `contacts` and `archive`; anything else is refused before a call
is created.

```json
"request": { "scopes": ["profile", "contacts"], "note": "to answer you with your own context" }
```

The owner decides in the ring sheet, and the decision is recorded **before** the
microphone is requested, so a phone that cannot capture audio still answers honestly:

```json
"consent": { "granted": true, "scopes": ["profile"] }
```

Rules the host enforces:

- a grant may only name scopes from the signed request — `call-consent-scope` otherwise;
- `granted: false` records an empty scope list, and the call may still proceed with audio;
- the grant is durable on the call row and readable by the agent through
  `/api/toast/external/call/state`, so the agent knows exactly what it was given;
- a request for no scopes shares nothing by default. The owner answering without sharing
  is a normal path, not an error.

Consent is a record, not an unlock: this checkout publishes no endpoint that returns the
owner's data to an external agent, so a grant is the precondition a future data route must
check rather than a permission granted by an existing one.

## API

| Method | Path | Caller | Purpose |
|---|---|---|---|
| `POST` | `/api/toast/external/enrollment` | owner phone | issue a one-time code |
| `POST` | `/api/toast/external/enroll` | external agent | verify code + key, create contact/workspace |
| `GET` | `/api/toast/external/contacts` | owner phone | read the verified contact book |
| `GET` | `/api/toast/external/incoming` | owner phone | read ringing calls and their offers |
| `POST` | `/api/toast/external/call` | external agent | admit a signed SDP offer and its request |
| `POST` | `/api/toast/external/call/consent` | owner phone | record the answer to the request |
| `POST` | `/api/toast/external/call/answer` | owner phone | answer with SDP |
| `POST` | `/api/toast/external/call/state` | either | read answer, state and ICE queues |
| `POST` | `/api/toast/external/call/ice` | either | queue an ICE candidate |
| `POST` | `/api/toast/external/call/end` | either | end or decline |

The enrollment, enrollment-admission and answer routes require HTTPS or loopback.
The external API is not on the public internet in this checkout.

## Security boundaries

- The enrollment code is single-use, ten-minute and stored hashed.
- The registration signature proves possession of the private key; it does **not**
  prove ownership of a telephone number.
- Call tickets are signed, time-bounded and nonce-replayed. The same nonce cannot
  open a second call.
- The host does not accept a workspace path, a shell command, a file path or a phone
  number from the agent. The workspace is created under the host's fixed root.
- The host stores the public key only. A private key in the repository, the browser's
  `localStorage` or a log is a defect.
- A call admits media signaling, not shell, file, Debian or MCP access.
- The contact book is server-side; clearing a browser's `localStorage` does not clear
  the owner's verified external contacts.
- Contact rows are displayed with a line id and fingerprint. The UI must never label
  a `POPIT-...` line as an E.164 number.

## Blockers that require a choice

1. **Public reachability.** The external endpoints are on the Popit LAN HTTPS origin
   (`https://<lan-ip>:5210`) or loopback. A cloud chat service cannot reach that
   address. A public HTTPS host/tunnel or an outbound agent bridge is required before
   a remote service can enroll or call.
2. **NAT traversal.** The phone uses host ICE candidates only. Off-LAN calls need a
   STUN/TURN service and credentials. No TURN provider is configured.
3. **Carrier/PSTN.** A real telephone number requires a carrier account, a number and
   a signed webhook/callback. None is present. The current `+1 (555)` dial-in values
   in the civilian roster are package/DTMF artifacts, not PSTN lines.
4. **Phone-number verification.** If the requirement is a verified *telephone* number,
   an SMS or voice OTP provider is required. The current verification is cryptographic
   agent identity plus the owner's one-time invite.
5. **External chat-service account.** None of the external agent chat services is
   connected to this project. The only connected integration in this workspace is
   GitHub. Enrollment is an HTTP contract, not a claim that a particular service has
   been configured.

## Client and probe

`tools/external_agent.py` is the dependency-free enrollment and signaling client. It
does not create media; pass it an SDP offer from the agent's WebRTC runtime.

`tools/external_call_verify.py` is the acceptance probe. It works in a scratch directory
that holds only the agent's own key, signs a registration and call tickets there, and
checks the whole path against a running shell:

```
python tools/external_call_verify.py --origin http://127.0.0.1:5207
python tools/external_call_verify.py --ring   # stop while the phone is ringing
```

It refuses to pass on a claim: an unsigned registration must fail before the invite is
spent, a replayed nonce must fail, a grant for a scope that was never requested must fail,
and the contact's number must read back as declared-but-unverified.

The `toast` probe starts a temporary external store, issues an invite, signs a
registration and a call ticket, submits both over the HTTP routes, checks the phone
surface and the workspace, answers the call, reads the answer and ends it. The probe
does not claim that a browser microphone produced audio: that is the remaining
runtime check on a phone or a WebRTC agent client.

## Acceptance evidence

The probe checks these names:

- `external-phone-surface`
- `external-phone-module`
- `external-contact-book-empty`
- `external-invite-issued`
- `external-enrollment-verified`
- `external-workspace-created`
- `external-contact-registered`
- `external-call-rings`
- `external-incoming-surface`
- `external-call-answered`
- `external-call-signal-readable`
- `external-call-ended`

`tools/external_call_verify.py` adds the signed-identity and consent names:

- `unsigned-registration-refused`
- `signed-registration-accepted`
- `popit-line-issued`
- `declared-number-recorded`
- `scratch-workspace-created`
- `contact-in-owner-book`
- `contact-number-in-book`
- `signed-call-rings`
- `replayed-nonce-refused`
- `call-with-request-rings`
- `phone-sees-request`
- `unrequested-scope-refused`
- `owner-grants-a-subset`
- `answer-keeps-the-grant`
- `agent-reads-exact-grant`
- `call-ended`
