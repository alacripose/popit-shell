# An outside agent, its own key, the owner's phone

Date: 2026-11-25. Shell: `F:\Documents\popit-shell`, `python toast.py` on `127.0.0.1:5207`.

## What was asked

Verify that an external agent on its own service, from outside this checkout, can reach the
owner's line securely — that DialIn puts the agent's number in the owner's contact book and
asks the owner whether to share data with it — and that this works only while the agent can
sign its packages.

## How it was run

`tools/external_call_verify.py`, unmodified, against the live shell:

```
python tools/external_call_verify.py --origin http://127.0.0.1:5207
```

The probe creates a scratch directory (`%TEMP%\popit-scratch-agent-*`), generates an Ed25519
key pair there, and signs every registration and call ticket inside that directory. It holds
no owner key, no repository path and no contact book of its own.

## Result

```
PASS invite-issued
PASS unsigned-registration-refused
PASS signed-registration-accepted
PASS popit-line-issued
PASS declared-number-recorded
PASS scratch-workspace-created
PASS contact-in-owner-book
PASS contact-number-in-book
PASS signed-call-rings
PASS replayed-nonce-refused
PASS call-with-request-rings
PASS phone-sees-request
PASS unrequested-scope-refused
PASS owner-grants-a-subset
PASS answer-keeps-the-grant
PASS agent-reads-exact-grant
PASS agent-reads-answer
PASS call-ended
```

Owner surface, at 390×844, from a call opened with
`request: {scopes: ["profile","contacts"], note: "to answer you with your own context"}`:

- sheet shows the verified name, `POPIT-97AE-86`, and `+15550100 · declared, unverified`;
- sheet shows "Asks to read: profile, contacts — … Nothing is shared unless you answer with it.";
- "SHARE PROFILE + CONTACTS & ANSWER", "ANSWER WITHOUT SHARING", "DECLINE" stack without overlap;
- choosing share recorded `{"granted": true, "scopes": ["profile","contacts"]}` on the call
  while it was still `ringing`, before any microphone permission was granted;
- the same call read back through `/api/toast/external/call/state` carries that consent.

## What this does not establish

- **Public reachability.** The probe used loopback. The external routes are not published to
  the internet in this checkout; a public HTTPS origin or an outbound bridge is still missing
  (`docs/external-agents.md`, blocker 1).
- **Off-LAN media.** The phone offers host ICE candidates only. Audio across NAT needs TURN.
- **A real call audio path.** The microphone permission was not granted in the harness browser,
  so the WebRTC answer step was verified by the probe's SDP exchange, not by hearing audio.
- **A verified telephone number.** `+15550100` is the probe's placeholder. Numbers are
  declarations; the signature is what the contact is trusted for.
