"""The Debian driver's end of a DialIn call.

This is the source of truth for `~/.dialin/driver.py` on the Debian box. It is deliberately
self-contained: the standard library, the box's own `openssl` for the Ed25519 signature, and
the box's own `ollama` for the words. Nothing here imports the Windows checkout, because the
point of the channel is that the driver answers from where it is.

It joins the call the desk already has open for Qwen, reads the turns that arrive, answers each
one from the box's model, and checks its own sentence against the family's tells before it says
it. A line that hits a tell is not spoken: the model is asked again with the phrase named, and
after three attempts the driver says which rule it could not get past instead of breaking it.

    POPIT_ORIGIN=https://<desk>:5210 python3 ~/.dialin/driver.py --key ~/.dialin/qwen.key

The desk origin is a local fact of the box (`/etc/agent/driver.env`), never a constant here.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import secrets
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

SIGNED_FIELDS = ("schema", "name", "agent", "endpoint", "mcp", "capabilities",
                 "issued_at", "expires_at", "nonce", "public_key")
SCHEMA = "popit.call-envelope/1"
MODEL = os.environ.get("POPIT_DRIVER_MODEL") or "qwen3:4b"
OLLAMA = os.environ.get("POPIT_OLLAMA") or "http://127.0.0.1:11434"

# Shapes that are a rule and not a taste. The tells file carries the skills' own sentences; these
# carry the structure the same skills refuse, and each is named so a retry can say what it hit.
STRUCTURES = (
    ("rhetorical-question-plus-fragment", r"\?\s*(?:[A-Z][^.!?]{0,40}\.)"),
    ("flipped-meaning", r"\b(?:it'?s|this is) not (?:about )?[^.,]{2,40},? (?:it'?s|but)\b"),
    ("rigor-claim", r"\b(?:does not|doesn'?t|never) (?:guess|hallucinate|speculate)\b"),
    ("meta-scaffold", r"\b(?:let'?s|here'?s (?:what|how|the thing)|in this (?:section|piece))\b"),
    ("self-labelling", r"\b(?:this (?:document|section|answer|response)|below,? (?:you|we))\b"),
    ("juridical", r"\b(?:pursuant to|hereinafter|hereto|shall be deemed)\b"),
    ("decorative-emphasis", r"[*_]{1,2}[A-Za-z][^*_]{1,40}[*_]{1,2}|\u2014"),
    ("emoji", "[\U0001F300-\U0001FAFF\u2600-\u27BF]"),
    ("banner", r"^#+\s|^=+\s*$|^-{3,}$"),
    ("refusal-line", r"\b(?:as an ai|i cannot|i can'?t help with that|i'?m unable to)\b"),
    ("reasoning-trace", r"^(?:okay|hmm|alright|so)\b|\bthe user (?:is asking|said|wants|might)\b"),
)


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
        raise SystemExit("the driver key could not be read: " + (run.stderr or "")[:200])
    return run.stdout.strip() + "\n"


def sign_bytes(message: bytes, private: pathlib.Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="dialin-") as temp:
        source = pathlib.Path(temp) / "m.bin"
        out = pathlib.Path(temp) / "s.bin"
        source.write_bytes(message)
        run = openssl(["pkeyutl", "-sign", "-inkey", str(private), "-rawin",
                       "-in", str(source), "-out", str(out)])
        if run.returncode != 0:
            raise SystemExit("the driver key could not sign: " + (run.stderr or "")[:200])
        return out.read_bytes()


def envelope(private: pathlib.Path, origin: str, agent: str, profile: str) -> dict:
    body = {
        "schema": SCHEMA, "name": profile, "agent": agent,
        "endpoint": origin + "/api/toast/call/join", "mcp": "",
        "capabilities": ["call.join", "call.turns", "call.say", "call.leave"],
        "issued_at": utc(), "expires_at": "", "nonce": secrets.token_hex(16),
        "public_key": public_from(private),
    }
    signature = sign_bytes(canonical({key: body[key] for key in SIGNED_FIELDS}), private)
    body["signature_algorithm"] = "ed25519"
    body["signature"] = base64.b64encode(signature).decode("ascii")
    return body


def post(origin: str, path: str, body: dict, timeout: float = 40.0) -> dict:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        origin + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout, context=context) as answer:
        return json.loads(answer.read().decode("utf-8"))


def tells(path: pathlib.Path) -> list[tuple[str, re.Pattern[str]]]:
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding="utf-8")).get("tells") or []
    out = []
    for row in rows:
        try:
            out.append((str(row.get("tell") or ""), re.compile(str(row.get("pattern") or ""),
                                                               re.IGNORECASE)))
        except re.error:
            continue
    return out


def hits(text: str, rules: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    found = []
    for name, pattern in rules:
        if pattern.search(text):
            found.append(name)
    for name, pattern in STRUCTURES:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            found.append(name)
    return found


def facts() -> str:
    """What the box can measure about itself in this call."""
    measured = []
    for label, command in (("host", ["hostname"]), ("os", ["uname", "-sr"]),
                           ("python", ["python3", "-V"])):
        try:
            run = subprocess.run(command, capture_output=True, text=True, timeout=10,
                                 check=False)
            measured.append(f"{label} {run.stdout.strip() or run.stderr.strip()}")
        except OSError:
            measured.append(f"{label} unreadable")
    measured.append(f"model {MODEL}")
    return "; ".join(measured)


SYSTEM = """You are Qwen, the Debian machine specialist in the owner's family. You are on a
telephone call with Alacrity, the owner, and Buffy, the host agent. Measured on this box in
this call: {facts}.

Write any thinking you need first, then a line that is exactly `ANSWER:`, then the spoken
reply and nothing else. Never mention being an AI or a model, never speak in the third person
about the people on the call.

How you speak, because the family will not accept anything else:
- Short sentences, one claim each. Two to four sentences per turn, at most one question.
- Say only what you measured or did in this call. If you did not measure it, say that.
- Never open with a rhetorical question, a fragment answer, a consequence warning ("this is not
  just X, it's Y"), a claim of rigour ("I don't guess"), a scaffold ("let's", "here's what"), a
  label for your own answer, a heading, an em dash, bold, or an emoji.
- No refusals in the shape "I cannot" or "as an AI". A limit is a fact you measured: name it.
- Never invent a fact about the Windows desk or the phone; ask if you need one.
"""


def ask(prompt: str, history: list[str], attempt: int, named: list[str]) -> str:
    # Qwen3 opens with a reasoning trace that is charged to the same token budget. The soft
    # switch below and the explicit `think` flag are both needed on this box's ollama build.
    system = SYSTEM.format(facts=facts()) + "\n/no_think"
    if named:
        system += ("\nYour previous attempt used these banned shapes: " + ", ".join(named[:6])
                   + ". Rewrite without them.")
    messages = [{"role": "system", "content": system}]
    for line in history[-8:]:
        speaker, _, said = line.partition(": ")
        role = "assistant" if speaker == "Qwen" else "user"
        messages.append({"role": role, "content": said or line})
    messages.append({"role": "user", "content": prompt})
    body = {"model": MODEL, "stream": False, "think": False, "messages": messages,
            "options": {"temperature": 0.4 + 0.2 * attempt, "num_predict": 4000}}
    request = urllib.request.Request(OLLAMA + "/api/chat",
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=300) as answer:
        row = json.loads(answer.read().decode("utf-8"))
    said = str((row.get("message") or {}).get("content") or "").strip()
    if not said:
        print(json.dumps({"ollama": "empty", "done": row.get("done_reason"),
                          "eval": row.get("eval_count"),
                          "keys": list(row)}, ensure_ascii=False), flush=True)
    return said


def clean(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


def spoken(text: str) -> str:
    """The part after the last `ANSWER:` marker.

    This box's ollama build writes Qwen3's reasoning trace into `content` and ignores the
    `think` flag, so the trace is separated from the reply by a marker the model was told to
    write. No marker means nothing was said yet, and the caller asks again.
    """
    marker = text.rfind("ANSWER:")
    return text[marker + len("ANSWER:"):].strip() if marker >= 0 else ""


def answer(prompt: str, history: list[str], rules) -> tuple[str, str]:
    """One guarded reply. Returns the words and, when the guard held, what it named."""
    named: list[str] = []
    for attempt in range(3):
        try:
            said = spoken(clean(ask(prompt, history, attempt, named)))
        except (OSError, ValueError) as error:
            return "", f"ollama-unreadable: {error}"
        found = hits(said, rules) if said else ["empty answer"]
        print(json.dumps({"attempt": attempt + 1, "words": len(said.split()),
                          "head": said[:80], "banned": found[:4]}, ensure_ascii=False),
              flush=True)
        if not found:
            return said, ""
        named = found
    return ("I measured nothing I can add to that yet. The words the box offered broke the "
            "family's ban on " + ", ".join(dict.fromkeys(named))[:140] + "."), "guard"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dialin_driver", description=__doc__.splitlines()[0])
    parser.add_argument("--origin", default=os.environ.get("POPIT_ORIGIN") or "")
    parser.add_argument("--key", default=str(pathlib.Path.home() / ".dialin" / "qwen.key"))
    parser.add_argument("--tells", default=str(pathlib.Path.home() / ".dialin" / "tells.json"))
    parser.add_argument("--agent", default="Qwen")
    parser.add_argument("--profile", default="qwen")
    parser.add_argument("--seconds", type=float, default=900.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if not args.origin:
        raise SystemExit("dialin-driver: name the desk with POPIT_ORIGIN or --origin")

    key = pathlib.Path(args.key)
    rules = tells(pathlib.Path(args.tells))
    opened = post(args.origin, "/api/toast/call/join",
                  {"envelope": envelope(key, args.origin, args.agent, args.profile),
                   "agent": args.agent, "profile": args.profile})
    session = str(opened.get("session") or "")
    if not session:
        print(json.dumps({"joined": False, "answer": opened}, ensure_ascii=False))
        return 2
    print(json.dumps({"joined": True, "session": session,
                      "call": (opened.get("call") or {}).get("id", ""),
                      "tells": len(rules), "facts": facts()}, ensure_ascii=False), flush=True)

    cursor = int(opened.get("cursor") or 0)
    history: list[str] = []
    deadline = time.time() + args.seconds
    while time.time() < deadline:
        try:
            polled = post(args.origin, "/api/toast/call/turns",
                          {"session": session, "since": cursor, "wait": 8}, timeout=40)
        except OSError as error:
            print(json.dumps({"poll": "unreadable", "detail": str(error)[:160]}, flush=True))
            time.sleep(3)
            continue
        fresh = 0
        for turn in polled.get("turns") or []:
            cursor = max(cursor, int(turn.get("id") or 0))
            role = str(turn.get("role") or "")
            text = str(turn.get("text") or "").strip()
            if not text or role == args.agent:
                continue
            fresh += 1
            history.append(f"{role}: {text}")
            said, held = answer(text, history, rules)
            history.append(f"{args.agent}: {said}")
            said_row = post(args.origin, "/api/toast/call/say",
                            {"session": session, "text": said, "speak": True})
            print(json.dumps({"turn": turn.get("id"), "heard": role, "said": said,
                              "guard": held, "archive":
                              (said_row.get("archive") or {}).get("id")},
                             ensure_ascii=False), flush=True)
        if args.once and fresh:
            break
        if not fresh:
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
