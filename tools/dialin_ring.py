"""Ring the owner's phone from the Debian box, over the shell's external-agent line.

This is the source of truth for `~/.dialin/ringer.py` on the box. Two acts, both signed with
the box's own Ed25519 key:

    enroll  one one-time code, a signed `popit.agent-registration/1`, and the box becomes a
            verified contact with a Popit line id. The private key stays on the box.
    ring    a real SDP offer from aiortc, signed inside a `popit.agent-call/1` ticket. The
            phone polls `/api/toast/external/incoming`, shows the verified name and line, and
            the owner decides.

    python3 ~/.dialin/ringer.py enroll --origin https://<desk>:5210 --code <one-time-code>
    python3 ~/.dialin/ringer.py ring --origin https://<desk>:5210 --seconds 90

The offer is the media library's own. The host refuses a synthesized one, and so does this
client: no aiortc means no ring, named rather than implied.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import pathlib
import secrets
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave

NAME = "Qwen on the Debian box"
REGISTRATION_SCHEMA = "popit.agent-registration/1"
CALL_SCHEMA = "popit.agent-call/1"
STATE = pathlib.Path.home() / ".dialin" / "rings.json"


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def openssl(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(["openssl", *args], capture_output=True, text=True,
                          timeout=timeout, check=False)


def public_from(private: pathlib.Path) -> str:
    run = openssl(["pkey", "-in", str(private), "-pubout"])
    if run.returncode != 0:
        raise SystemExit("the box key could not be read: " + (run.stderr or "")[:200])
    return run.stdout.strip() + "\n"


def sign(message: bytes, private: pathlib.Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="ring-") as temp:
        source = pathlib.Path(temp) / "m.bin"
        out = pathlib.Path(temp) / "s.bin"
        source.write_bytes(message)
        run = openssl(["pkeyutl", "-sign", "-inkey", str(private), "-rawin",
                       "-in", str(source), "-out", str(out)])
        if run.returncode != 0:
            raise SystemExit("the box key could not sign: " + (run.stderr or "")[:200])
        return out.read_bytes()


def post(origin: str, path: str, body: dict, timeout: float = 40.0) -> dict:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        origin + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as answer:
            return json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"{path} refused with {error.code}: {detail}") from None


def remember(row: dict) -> None:
    book = {"rings": []}
    if STATE.is_file():
        try:
            book = json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    book["rings"] = (book.get("rings") or [])[-40:] + [row]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(book, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def enroll(origin: str, key: pathlib.Path, code: str, endpoint: str) -> dict:
    # The host strips the key before it builds its own copy of this payload, so the signed
    # copy has to be stripped too: one trailing newline changes every signed byte.
    payload = {"schema": REGISTRATION_SCHEMA, "name": NAME, "endpoint": endpoint,
               "public_key": public_from(key).strip(), "issued_at": utc(), "code": code}
    signature = base64.b64encode(sign(canonical(payload), key)).decode("ascii")
    row = post(origin, "/api/toast/external/enroll", {**payload, "signature": signature})
    remember({"at": utc(), "act": "enroll", "contact": row.get("contact") or {}})
    return row


def tone(path: pathlib.Path) -> None:
    """A quiet two-tone line, so the offer carries real audio rather than a silent track."""
    rate = 16000
    seconds = 4
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        frames = bytearray()
        for index in range(rate * seconds):
            value = int(3000 * math.sin(2 * math.pi * 440 * index / rate)
                        + 3000 * math.sin(2 * math.pi * 620 * index / rate))
            frames += struct.pack("<h", value)
        out.writeframes(bytes(frames))


async def offer() -> tuple[str, object]:
    from aiortc import RTCPeerConnection
    from aiortc.contrib.media import MediaPlayer

    context = tempfile.TemporaryDirectory(prefix="ring-tone-")
    wav = pathlib.Path(context.name) / "line.wav"
    tone(wav)
    player = MediaPlayer(str(wav), loop=True)
    if player.audio is None:
        raise SystemExit("aiortc produced no audio track from the tone file")
    pc = RTCPeerConnection()
    pc.addTrack(player.audio)
    await pc.setLocalDescription(await pc.createOffer())
    return pc.localDescription.sdp, (pc, player, context)


async def ring(origin: str, key: pathlib.Path, seconds: float) -> dict:
    book = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {}
    # The contact is the most recent enrollment, not the most recent act: a ring row says
    # nothing about which line this box may dial.
    contact = next((row.get("contact") for row in reversed(book.get("rings") or [])
                    if row.get("contact")), {})
    agent = str(contact.get("id") or "")
    if not agent:
        raise SystemExit("this box has no contact yet; run `enroll` with a one-time code first")

    sdp, held = await offer()
    ticket = {"schema": CALL_SCHEMA, "agent": agent, "nonce": secrets.token_hex(16),
              "issued_at": utc(), "offer": sdp}
    ticket["signature"] = base64.b64encode(sign(canonical(ticket), key)).decode("ascii")
    opened = post(origin, "/api/toast/external/call", ticket)
    call_id = str(opened.get("call_id") or "")
    print(json.dumps({"ringing": True, "call": call_id, "line": contact.get("line"),
                      "state": opened.get("state")}, ensure_ascii=False), flush=True)

    pc, player, context = held
    seen_ice = 0
    deadline = time.time() + seconds
    answered = False
    while time.time() < deadline:
        await asyncio.sleep(1.2)
        state = post(origin, "/api/toast/external/call/state",
                     {"agent": agent, "call_id": call_id, "nonce": secrets.token_hex(16),
                      "issued_at": utc()})
        answer = str(state.get("answer") or "")
        if answer and not answered:
            await pc.setRemoteDescription(
                __import__("aiortc").RTCSessionDescription(sdp=answer, type="answer"))
            answered = True
            print(json.dumps({"answered": True, "consent": state.get("consent")},
                             ensure_ascii=False), flush=True)
        for row in (state.get("phone_ice") or [])[seen_ice:]:
            await pc.addIceCandidate(__import__("aiortc").RTCIceCandidate(
                sdpMid=row.get("sdpMid"), sdpMLineIndex=row.get("sdpMLineIndex"),
                candidate=row.get("candidate")))
            seen_ice += 1
        if state.get("state") in ("ended", "missed", "declined"):
            print(json.dumps({"state": state.get("state"), "at": utc()}, ensure_ascii=False),
                  flush=True)
            break
    await pc.close()
    player.audio.stop() if hasattr(player.audio, "stop") else None
    context.cleanup()
    remember({"at": utc(), "act": "ring", "call": call_id, "answered": answered})
    return {"call": call_id, "answered": answered}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dialin_ring", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("enroll", "ring"))
    parser.add_argument("--origin", default="")
    parser.add_argument("--key", default=str(pathlib.Path.home() / ".dialin" / "qwen.key"))
    parser.add_argument("--code", default="")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--seconds", type=float, default=90.0)
    args = parser.parse_args(argv)
    origin = args.origin
    if not origin:
        raise SystemExit("dialin-ring: name the desk with --origin or POPIT_ORIGIN")
    key = pathlib.Path(args.key)
    if args.action == "enroll":
        if not args.code:
            raise SystemExit("dialin-ring: enroll needs the one-time code the desk minted")
        row = enroll(origin, key, args.code, args.endpoint or origin + "/api/toast/call/join")
        print(json.dumps(row, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(asyncio.run(ring(origin, key, args.seconds)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
