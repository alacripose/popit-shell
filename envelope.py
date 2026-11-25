"""Signed call envelopes for agents outside the Popit shell.

A caller does not get a lane by naming one. It signs a canonical envelope with an
Ed25519 key, the Popit host verifies that signature against its own trust registry,
and only then does `call.join` mint a bridge session. The envelope carries a
short-lived nonce so a captured package cannot be replayed.

The signing convention is deliberately plain: JSON fields in sorted order, no
whitespace, the signed fields listed once in `SIGNED_FIELDS`, and the signature
base64-encoded beside the public key. OpenSSL performs both key operations so the
host and the CLI use the same mechanism; there is no second crypto runtime.

CLI:
    python envelope.py keygen --private caller.key --public caller.pem
    python envelope.py sign --payload caller.json --key caller.key --out signed.json
    python envelope.py verify --envelope signed.json --trust runlogs/toast/envelope-trust.json
    python envelope.py trust --public caller.pem --name "Buffy" \
        --trust runlogs/toast/envelope-trust.json
"""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import datetime
import json
import os
import pathlib
import re
import subprocess
import tempfile
import threading
import time

from blake3 import blake3

SCHEMA = "popit.call-envelope/1"
TRUST_SCHEMA = "popit.envelope-trust/1"
NONCE_SCHEMA = "popit.envelope-nonces/1"
SIGNATURE_ALGORITHM = "ed25519"
SIGNED_FIELDS = (
    "schema", "name", "agent", "endpoint", "mcp", "capabilities",
    "issued_at", "expires_at", "nonce", "public_key",
)
REQUIRED_FIELDS = ("schema", "name", "agent", "endpoint", "capabilities",
                   "issued_at", "nonce", "public_key")
MAX_AGE_SECONDS = 900
MAX_CLOCK_SKEW_SECONDS = 120
MAX_ENVELOPE_BYTES = 16 * 1024
NONCE_RE = re.compile(r"^[0-9a-f]{32,64}$")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_OPENSSL = os.environ.get("POPIT_OPENSSL", "openssl")
_LOCK = threading.RLock()


class Refused(Exception):
    """A named refusal; never a generic auth failure the caller cannot diagnose."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def iso(value: datetime.datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime.datetime:
    text = str(value or "").strip()
    if not text:
        raise Refused("envelope-time", "an envelope needs issued_at")
    try:
        parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise Refused("envelope-time", f"issued_at is not ISO-8601: {error}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def payload_bytes(envelope: dict) -> bytes:
    """The exact bytes the caller signs; adding a field is a protocol change."""
    missing = [field for field in SIGNED_FIELDS if field not in envelope]
    if missing:
        raise Refused("envelope-field", ", ".join(missing))
    return _canonical({field: envelope[field] for field in SIGNED_FIELDS})


def fingerprint(public_key: str) -> str:
    """A stable trust handle for one public key, independent of PEM newline style."""
    text = "\n".join(line.strip() for line in str(public_key or "").splitlines()
                     if line.strip()) + "\n"
    if "BEGIN PUBLIC KEY" not in text:
        raise Refused("envelope-public-key", "public_key is not a PEM SPKI public key")
    return "blake3:" + blake3(text.encode("utf-8")).hexdigest()


def _openssl(args: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [_OPENSSL, *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Refused("envelope-openssl", str(error)[:240]) from error


def keygen(private_path: pathlib.Path, public_path: pathlib.Path) -> dict:
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    result = _openssl(["genpkey", "-algorithm", "ED25519", "-out", str(private_path)])
    if result.returncode != 0:
        raise Refused("envelope-keygen", (result.stderr or "openssl refused")[:240])
    result = _openssl(["pkey", "-in", str(private_path), "-pubout", "-out", str(public_path)])
    if result.returncode != 0:
        raise Refused("envelope-public-key", (result.stderr or "openssl refused")[:240])
    try:
        private_path.chmod(0o600)
    except OSError:
        pass
    return {"private": str(private_path), "public": str(public_path),
            "fingerprint": fingerprint(public_path.read_text(encoding="utf-8"))}


def _public_from_private(private_path: pathlib.Path) -> str:
    with tempfile.TemporaryDirectory(prefix="popit-envelope-") as temp:
        out = pathlib.Path(temp) / "public.pem"
        result = _openssl(["pkey", "-in", str(private_path), "-pubout", "-out", str(out)])
        if result.returncode != 0:
            raise Refused("envelope-public-key", (result.stderr or "openssl refused")[:240])
        return out.read_text(encoding="utf-8")


def sign(payload: dict, private_path: pathlib.Path) -> dict:
    body = copy.deepcopy(payload)
    body["schema"] = str(body.get("schema") or SCHEMA)
    public_key = str(body.get("public_key") or "").strip() or _public_from_private(private_path)
    body["public_key"] = public_key
    body.setdefault("issued_at", iso())
    body.setdefault("expires_at", "")
    body.setdefault("mcp", "")
    body.setdefault("capabilities", ["call.join", "call.turns", "call.say", "call.leave"])
    signature = _sign_bytes(payload_bytes(body), private_path)
    body["signature_algorithm"] = SIGNATURE_ALGORITHM
    body["signature"] = base64.b64encode(signature).decode("ascii")
    return body


def _sign_bytes(message: bytes, private_path: pathlib.Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="popit-envelope-") as temp:
        source = pathlib.Path(temp) / "message.bin"
        signature = pathlib.Path(temp) / "signature.bin"
        source.write_bytes(message)
        result = _openssl(["pkeyutl", "-sign", "-inkey", str(private_path),
                           "-rawin", "-in", str(source), "-out", str(signature)])
        if result.returncode != 0:
            raise Refused("envelope-sign", (result.stderr or "openssl refused")[:240])
        return signature.read_bytes()


def sign_payload(payload: dict, private_path: pathlib.Path) -> str:
    """Sign canonical JSON for the external-agent enrollment/signaling protocol."""
    return base64.b64encode(_sign_bytes(_canonical(payload), private_path)).decode("ascii")


def verify_payload(payload: dict, signature: str, public_key: str) -> bool:
    """Verify a canonical JSON signature without consuming or reserving anything."""
    try:
        parsed = _signature_bytes(signature)
    except Refused:
        return False
    return _verify_bytes(_canonical(payload), parsed, public_key)


def _verify_bytes(message: bytes, signature: bytes, public_key: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="popit-envelope-") as temp:
        root = pathlib.Path(temp)
        source = root / "message.bin"
        signature_path = root / "signature.bin"
        public_path = root / "public.pem"
        source.write_bytes(message)
        signature_path.write_bytes(signature)
        public_path.write_text(str(public_key).strip() + "\n", encoding="utf-8")
        result = _openssl(["pkeyutl", "-verify", "-pubin", "-inkey", str(public_path),
                           "-rawin", "-in", str(source), "-sigfile", str(signature_path)])
        return result.returncode == 0


def _signature_bytes(value: str) -> bytes:
    try:
        signature = base64.b64decode(str(value or ""), validate=True)
    except (ValueError, binascii.Error) as error:
        raise Refused("envelope-signature", "signature is not base64") from error
    if len(signature) != 64:
        raise Refused("envelope-signature", "an Ed25519 signature is 64 bytes")
    return signature


def _trust(trust_path: pathlib.Path) -> list[dict]:
    if not trust_path.exists():
        raise Refused("envelope-trust-absent", str(trust_path))
    try:
        value = json.loads(trust_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Refused("envelope-trust-invalid", str(error)[:240]) from error
    keys = value.get("keys") if isinstance(value, dict) else None
    if not isinstance(keys, list):
        raise Refused("envelope-trust-invalid", "keys must be a list")
    return [row for row in keys if isinstance(row, dict) and row.get("fingerprint")
            and not row.get("revoked")]


def trusted(public_key: str, *, trust_path: pathlib.Path | None = None) -> bool:
    """Is this key in the registry? Read-only, and the one question a subscriber asks."""
    trust_file = pathlib.Path(trust_path or TRUST_PATH_DEFAULT)
    digest = fingerprint(public_key)
    return any(row["fingerprint"] == digest for row in _trust(trust_file))


def trust_key(public_key: str, name: str, trust_path: pathlib.Path) -> dict:
    digest = fingerprint(public_key)
    with _LOCK:
        rows = []
        if trust_path.exists():
            try:
                rows = json.loads(trust_path.read_text(encoding="utf-8")).get("keys", [])
            except (OSError, json.JSONDecodeError):
                rows = []
        rows = [row for row in rows if isinstance(row, dict) and row.get("fingerprint") != digest]
        row = {"name": " ".join(str(name or "").split())[:60] or "external-caller",
               "fingerprint": digest, "public_key": public_key.strip(),
               "added_at": iso()}
        rows.append(row)
        trust_path.parent.mkdir(parents=True, exist_ok=True)
        trust_path.write_text(json.dumps({"schema": TRUST_SCHEMA, "keys": rows},
                                         indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
        return row


def _check_envelope(envelope: dict, now: datetime.datetime) -> None:
    if not isinstance(envelope, dict):
        raise Refused("envelope-shape", "an envelope must be a JSON object")
    if len(_canonical(envelope)) > MAX_ENVELOPE_BYTES:
        raise Refused("envelope-oversize", str(len(_canonical(envelope))))
    missing = [field for field in REQUIRED_FIELDS if not envelope.get(field)]
    if missing:
        raise Refused("envelope-field", ", ".join(missing))
    if envelope.get("schema") != SCHEMA:
        raise Refused("envelope-schema", str(envelope.get("schema") or ""))
    name = " ".join(str(envelope.get("name") or "").split())
    agent = " ".join(str(envelope.get("agent") or "").split())
    if not name or not agent:
        raise Refused("envelope-name", "name and agent must be non-empty")
    if len(name) > 60 or len(agent) > 60:
        raise Refused("envelope-name", "name or agent is too long")
    if not str(envelope.get("endpoint") or "").startswith("https://"):
        raise Refused("envelope-endpoint", "an external caller endpoint must be https")
    capabilities = envelope.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
        raise Refused("envelope-capabilities", "capabilities must be a list of strings")
    if "call.join" not in capabilities:
        raise Refused("envelope-capability", "call.join is required")
    if not NONCE_RE.fullmatch(str(envelope.get("nonce") or "")):
        raise Refused("envelope-nonce", "nonce must be 32-64 lowercase hex characters")
    issued = parse_iso(str(envelope.get("issued_at") or ""))
    if issued > now + datetime.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise Refused("envelope-time", "issued_at is in the future")
    if now - issued > datetime.timedelta(seconds=MAX_AGE_SECONDS):
        raise Refused("envelope-expired", "envelope is older than 15 minutes")
    expires_text = str(envelope.get("expires_at") or "").strip()
    if expires_text:
        expires = parse_iso(expires_text)
        if expires <= now:
            raise Refused("envelope-expired", "expires_at has passed")
        if expires > issued + datetime.timedelta(hours=1):
            raise Refused("envelope-expiry", "expires_at is more than one hour after issue")
    public_key = str(envelope.get("public_key") or "").strip()
    fingerprint(public_key)
    signature = _signature_bytes(str(envelope.get("signature") or ""))
    if envelope.get("signature_algorithm") not in (None, "", SIGNATURE_ALGORITHM):
        raise Refused("envelope-algorithm", str(envelope.get("signature_algorithm")))
    if not _verify_bytes(payload_bytes(envelope), signature, public_key):
        raise Refused("envelope-signature", "the signature does not verify")
    # Trust is a separate authority: admit() and verify() read the registry they
    # were told to use, so a custom host registry is never shadowed by a default.


TRUST_PATH_DEFAULT = pathlib.Path(os.environ.get(
    "POPIT_ENVELOPE_TRUST", "runlogs/toast/envelope-trust.json"))


def _nonces(nonce_path: pathlib.Path) -> dict:
    if not nonce_path.exists():
        return {"schema": NONCE_SCHEMA, "nonces": []}
    try:
        value = json.loads(nonce_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Refused("envelope-nonce-store", str(error)[:240]) from error
    if not isinstance(value, dict) or not isinstance(value.get("nonces"), list):
        raise Refused("envelope-nonce-store", "nonce store has the wrong shape")
    return value


def admit(envelope: dict, *, trust_path: pathlib.Path | None = None,
          nonce_path: pathlib.Path | None = None,
          now: datetime.datetime | None = None) -> dict:
    """Verify a signed package and reserve its nonce; return the caller facts."""
    current = (now or utc_now()).astimezone(datetime.timezone.utc)
    trust_file = pathlib.Path(trust_path or TRUST_PATH_DEFAULT)
    nonce_file = pathlib.Path(nonce_path or trust_file.with_name("envelope-nonces.json"))
    if not isinstance(envelope, dict):
        raise Refused("envelope-shape", "an envelope must be a JSON object")
    # Verify signature and time before consulting the trust file, so an unsigned
    # package cannot get a useful trust oracle.
    if len(_canonical(envelope)) > MAX_ENVELOPE_BYTES:
        raise Refused("envelope-oversize", "envelope exceeds 16 KiB")
    signed = {field: envelope.get(field) for field in SIGNED_FIELDS}
    missing = [field for field in REQUIRED_FIELDS if not signed.get(field)]
    if missing:
        raise Refused("envelope-field", ", ".join(missing))
    signature = _signature_bytes(str(envelope.get("signature") or ""))
    if not _verify_bytes(payload_bytes(signed), signature, str(signed["public_key"])):
        raise Refused("envelope-signature", "the signature does not verify")
    # Re-run the field, time and algorithm checks now that the bytes are known good.
    _check_envelope(envelope, current)
    digest = fingerprint(str(signed["public_key"]))
    if not any(row["fingerprint"] == digest for row in _trust(trust_file)):
        raise Refused("envelope-untrusted", digest)
    nonce = str(signed["nonce"])
    with _LOCK:
        book = _nonces(nonce_file)
        if any(item.get("nonce") == nonce for item in book["nonces"] if isinstance(item, dict)):
            raise Refused("envelope-replay", nonce)
        book["nonces"] = [item for item in book["nonces"]
                          if isinstance(item, dict) and item.get("nonce") != nonce][-500:]
        book["nonces"].append({"nonce": nonce, "at": iso(current), "fingerprint": digest})
        nonce_file.parent.mkdir(parents=True, exist_ok=True)
        nonce_file.write_text(json.dumps(book, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    return {
        "admitted": True, "caller": signed["name"], "agent": signed["agent"],
        "endpoint": signed["endpoint"], "mcp": signed.get("mcp") or "",
        "capabilities": signed["capabilities"], "fingerprint": digest,
        "nonce": nonce, "issued_at": signed["issued_at"], "admitted_at": iso(current),
    }


def verify(envelope: dict, *, trust_path: pathlib.Path | None = None) -> dict:
    """Read-only verification: no nonce is consumed."""
    current = utc_now()
    trust_file = pathlib.Path(trust_path or TRUST_PATH_DEFAULT)
    if not isinstance(envelope, dict):
        raise Refused("envelope-shape", "an envelope must be a JSON object")
    signed = {field: envelope.get(field) for field in SIGNED_FIELDS}
    missing = [field for field in REQUIRED_FIELDS if not signed.get(field)]
    if missing:
        raise Refused("envelope-field", ", ".join(missing))
    signature = _signature_bytes(str(envelope.get("signature") or ""))
    if not _verify_bytes(payload_bytes(signed), signature, str(signed["public_key"])):
        raise Refused("envelope-signature", "the signature does not verify")
    _check_envelope(envelope, current)
    digest = fingerprint(str(signed["public_key"]))
    if not any(row["fingerprint"] == digest for row in _trust(trust_file)):
        raise Refused("envelope-untrusted", digest)
    return {"verified": True, "caller": signed["name"], "agent": signed["agent"],
            "fingerprint": digest, "nonce": signed["nonce"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    key = sub.add_parser("keygen")
    key.add_argument("--private", required=True)
    key.add_argument("--public", required=True)
    signer = sub.add_parser("sign")
    signer.add_argument("--payload", required=True)
    signer.add_argument("--key", required=True)
    signer.add_argument("--out", required=True)
    verifier = sub.add_parser("verify")
    verifier.add_argument("--envelope", required=True)
    verifier.add_argument("--trust", default=str(TRUST_PATH_DEFAULT))
    trust = sub.add_parser("trust")
    trust.add_argument("--public", required=True)
    trust.add_argument("--name", required=True)
    trust.add_argument("--trust", default=str(TRUST_PATH_DEFAULT))
    args = parser.parse_args()
    try:
        if args.command == "keygen":
            print(json.dumps(keygen(pathlib.Path(args.private), pathlib.Path(args.public)),
                             indent=2, ensure_ascii=False))
        elif args.command == "sign":
            payload = json.loads(pathlib.Path(args.payload).read_text(encoding="utf-8"))
            signed = sign(payload, pathlib.Path(args.key))
            pathlib.Path(args.out).write_text(json.dumps(signed, indent=2,
                                                         ensure_ascii=False) + "\n",
                                              encoding="utf-8")
            print(json.dumps({"signed": args.out, "fingerprint":
                              fingerprint(signed["public_key"])}, ensure_ascii=False))
        elif args.command == "verify":
            envelope = json.loads(pathlib.Path(args.envelope).read_text(encoding="utf-8"))
            print(json.dumps(verify(envelope, trust_path=pathlib.Path(args.trust)),
                             indent=2, ensure_ascii=False))
        elif args.command == "trust":
            public_key = pathlib.Path(args.public).read_text(encoding="utf-8")
            print(json.dumps(trust_key(public_key, args.name, pathlib.Path(args.trust)),
                             indent=2, ensure_ascii=False))
    except (Refused, OSError, json.JSONDecodeError) as error:
        code = error.code if isinstance(error, Refused) else "envelope-cli"
        print(json.dumps({"ok": False, "refused": {"code": code, "detail": str(error)}},
                         ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
