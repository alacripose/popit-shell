"""Civilian dial-in as a modern Secure Shell package.

Every agent is a civilian with a number allocated under the local private key. The dial-in is
one modern package directory: canonical `manifest.json`, a separate `payload.bin`, and the
identity `name@revision+blake3:<hex>`. The payload is the current hash-pinned surface document
(`secure-shell.surface/<32 hex>`), so the reader verifies the package before it reads any row.

There is no SHPKG frame, no numeric format id and no second manifest. The DTMF digits are derived
from the verified package digest and played only after the manifest, payload length, payload
digest, surface header and declared surface id all hold.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import pathlib
import secrets
import struct
import threading
import time
import unicodedata
import wave

from blake3 import blake3

SCHEMA = "popit.civilian-roster/1"
TONE_REV = 2
EXCLUDED = {
    "signature", "signature_algorithm", "received_at", "admitted_at",
    "hash", "digest", "nonce", "chunk_frame",
}
DTMF = {
    "0": (941, 1336), "1": (697, 1209), "2": (697, 1336), "3": (697, 1477),
    "4": (770, 1209), "5": (770, 1336), "6": (770, 1477), "7": (852, 1209),
    "8": (852, 1336), "9": (852, 1477),
}


def format_id(family: str, lines: list[str]) -> str:
    digest = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    return f"{family}/{digest[:32]}"


PACKAGE_SCHEMA = format_id("secure-shell.package", [
    "family\tsecure-shell.package",
    "legacy-family\tsecure-shell.package",
    "legacy-schema\t1",
    "reader\tsecure-shell.package.reader.v1",
    "algorithm\tblake3",
    "field\tname", "field\trevision", "field\tschemas", "field\tdependencies",
    "field\tentry_points", "field\tlengths",
    "exclude\tsignature", "exclude\tsignature_algorithm", "exclude\treceived_at",
    "exclude\tadmitted_at", "exclude\thash", "exclude\tdigest", "exclude\tnonce",
    "exclude\tchunk_frame",
])
SURFACE_SCHEMA = format_id("secure-shell.surface", [
    "family\tsecure-shell.surface",
    "legacy-family\tdl-enclave.surface",
    "legacy-schema\t1",
    "reader\tsecure-shell.surface.reader.v1",
    "refusal\taction-count", "refusal\tduplicate-window", "refusal\tformat-hash-mismatch",
    "refusal\tformat-id-legacy-emitted", "refusal\tgeometry-invalid", "refusal\tnode-count",
    "refusal\tnode-depth", "refusal\tpin-not-pinnable", "refusal\tsurface-capability",
    "refusal\tsurface-id", "refusal\tsurface-oversize", "refusal\tsurface-schema",
    "refusal\tunknown-lane", "refusal\tunknown-node-kind", "refusal\tunknown-node-parent",
    "refusal\tunknown-node-role", "refusal\tunknown-rule", "refusal\tunknown-theme-role",
    "refusal\twindow-count",
])
DOMAIN = PACKAGE_SCHEMA.encode("utf-8")
HARD_CEILING = 64 * 1024 * 1024 * 1024
KEY_BYTES = 32

# Only identities that can actually speak are dialable. Cua is the spine; Laya and Von are
# stack internals, not callable civilians. Popit is the shell, and the axis is a corpus lane.
# Giving any of those a civilian name or number is refused by `enroll`.
STACK_IDS = {"cua", "laya", "von", "axis", "popit"}
STACK_NAMES = {"cua", "laya", "von", "axis", "popit", "driver", "shell"}
CORE = (
    ("Alacrity", "human", "owner", "alacrity"),
    ("Buffy", "agent", "agent", "buffy"),
    ("Qwen", "agent", "agent", "qwen"),
    ("Whisper", "agent", "agent", "whisper"),
    ("Ash", "civilian", "resident", "ash"),
    ("Bram", "civilian", "resident", "bram"),
)


def _slug(name: str) -> str:
    folded = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    value = "".join(char.lower() if char.isalnum() else "-" for char in folded.strip())
    return "-".join(part for part in value.split("-") if part)[:40] or "civilian"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_json(value: object) -> bytes:
    """The one canonical form every modern package in this shell is written in."""
    return _canonical(value)


def package_digest(manifest: dict, payload: bytes) -> str:
    """The `secure-shell.package/1` digest, shared by the roster and the settings package.

    Domain-separated and length-framed, so a surface document and a settings document
    can never be swapped for one another under the same identity.
    """
    if len(payload) > HARD_CEILING:
        raise Refused("payload-oversize", str(len(payload)))
    if manifest.get("lengths", {}).get("payload") != len(payload):
        raise Refused("length", "manifest payload length does not match")
    manifest_bytes = _canonical(_kept(manifest))
    hasher = blake3()
    hasher.update(DOMAIN)
    hasher.update(len(manifest_bytes).to_bytes(8, "big"))
    hasher.update(manifest_bytes)
    hasher.update(len(payload).to_bytes(8, "big"))
    hasher.update(payload)
    return "blake3:" + hasher.hexdigest()


def _kept(manifest: dict) -> dict:
    return {key: value for key, value in manifest.items() if key not in EXCLUDED}


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


class CivilianDialin:
    def __init__(self, root: pathlib.Path, *, play: bool = True) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = root / "civilians.json"
        self.key_path = root / "civilian.key"
        self.packages = root / "packages"
        self.tones = root / "tones"
        self.packages.mkdir(exist_ok=True)
        self.tones.mkdir(exist_ok=True)
        self.play = play
        self.lock = threading.RLock()
        self.key = self._key()
        self.rows: list[dict] = []
        self._load()

    def _key(self) -> bytes:
        if self.key_path.exists():
            data = self.key_path.read_bytes()
            if len(data) == KEY_BYTES:
                return data
        data = secrets.token_bytes(KEY_BYTES)
        self.key_path.write_bytes(data)
        try:
            self.key_path.chmod(0o600)
        except OSError:
            pass
        return data

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = value.get("civilians") if isinstance(value, dict) else None
        if isinstance(rows, list):
            kept = [row for row in rows if isinstance(row, dict) and row.get("id")]
            if kept != rows or any(row.get("id") in STACK_IDS for row in kept):
                self.rows = [row for row in kept if row.get("id") not in STACK_IDS]
                self._save()
            else:
                self.rows = kept

    def _save(self) -> None:
        payload = {"schema": SCHEMA, "civilians": self.rows}
        self.state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")

    def _number(self, identity: str) -> tuple[str, str]:
        for attempt in range(100):
            message = f"{identity}:{attempt}".encode("utf-8")
            digest = hmac.new(self.key, message, hashlib.sha256).digest()
            value = int.from_bytes(digest[:8], "big")
            body = 1000000 + value % 9000000
            number = f"+1 (555) {body // 10000:03d}-{body % 10000:04d}"
            if all(row.get("number") != number for row in self.rows):
                proof = hmac.new(self.key, number.encode("utf-8"), hashlib.sha256).hexdigest()
                return number, proof
        raise Refused("number-space-exhausted", identity)

    def enroll(self, name: str, role: str = "civilian", identity: str = "",
               kind: str = "civilian", culture: str = "") -> dict:
        display = " ".join(str(name or "").split())[:60]
        if not display:
            raise Refused("civilian-name", "a citizen needs a name")
        slug = _slug(display)
        if slug in STACK_IDS or slug in STACK_NAMES:
            raise Refused("stack-not-civilian",
                          f"{display} is a stack component, not a callable identity")
        with self.lock:
            existing = next((row for row in self.rows if row["id"] == slug), None)
            if existing:
                changed = False
                if kind and existing.get("kind") != kind:
                    existing["kind"] = kind
                    changed = True
                if culture and existing.get("culture") != culture:
                    existing["culture"] = culture
                    changed = True
                if changed:
                    self._save()
                return dict(existing)
            identity = identity or f"civilian:{slug}"
            number, proof = self._number(identity)
            row = {
                "id": slug, "name": display, "role": role or "civilian", "kind": kind,
                "culture": culture,
                "identity": identity, "number": number, "number_proof": proof,
                "package": "", "package_digest": "", "source_digest": "",
                "package_identity": "", "format": "modern", "tones": "",
                "tone_state": "waiting", "verified": False,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self.rows.append(row)
            self._save()
            return dict(row)

    def _surface(self, row: dict) -> bytes:
        package_name = f"dialin-{row['id']}"
        lines = [
            SURFACE_SCHEMA,
            f"surface\t{package_name}",
            "requires\tobserve",
            f"window\tcivilian-{row['id']}\t{row['name']}\tframe\tfill\t0\t0\t320\t180\t240\t120\tfalse\tfalse\tclose\tdrag\tsurface\t{package_name}",
            f"node\tcivilian-{row['id']}\tname\t-\tlabel\tsmall\t{row['name']}",
            f"node\tcivilian-{row['id']}\tnumber\tname\tfield\tmono\t{row['number']}",
            f"node\tcivilian-{row['id']}\trole\tname\tlabel\tmicro\t{row['role']}",
        ]
        return ("\n".join(lines) + "\n").encode("utf-8")

    def _digest(self, manifest: dict, payload: bytes) -> str:
        return package_digest(manifest, payload)

    def verify_package(self, target: pathlib.Path) -> dict:
        manifest_path = target / "manifest.json"
        payload_path = target / "payload.bin"
        if not manifest_path.exists() or not payload_path.exists():
            raise Refused("package-absent", target.name)
        raw_manifest = manifest_path.read_bytes()
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Refused("manifest", "not canonical JSON")
        if _canonical(_kept(manifest)) != raw_manifest:
            raise Refused("manifest-canonical", target.name)
        payload = payload_path.read_bytes()
        digest = self._digest(manifest, payload)
        expected = f"{manifest['name']}@{manifest['revision']}+{digest}"
        identity_file = target / "identity.txt"
        if not identity_file.exists() or identity_file.read_text(encoding="utf-8").strip() != expected:
            raise Refused("identity", target.name)
        text = payload.decode("utf-8")
        if not text.startswith(SURFACE_SCHEMA + "\n"):
            raise Refused("surface-schema", target.name)
        declared = text.splitlines()[1].split("\t", 1)
        if len(declared) != 2 or declared[0] != "surface" or declared[1] != manifest["name"]:
            raise Refused("surface-id", target.name)
        return {"manifest": manifest, "payload": payload, "digest": digest, "identity": expected}

    def _tones(self, row: dict, digest: str) -> str:
        hex_digest = digest.rsplit(":", 1)[-1]
        digits = "".join(str(int(hex_digest[index:index + 2], 16) % 10) for index in range(0, 12, 2))
        path = self.tones / f"{row['id']}.wav"
        rate = 16000
        samples: list[int] = []
        for digit in digits:
            low, high = DTMF[digit]
            count = int(rate * 0.09)
            for index in range(count):
                moment = index / rate
                value = 0.30 * (math.sin(2 * math.pi * low * moment)
                                + math.sin(2 * math.pi * high * moment)) / 2
                samples.append(int(max(-1.0, min(1.0, value)) * 32767))
            samples.extend([0] * int(rate * 0.045))
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(struct.pack("<" + "h" * len(samples), *samples))
        return digits

    def _tone_wave(self, path: pathlib.Path, samples: list[int], rate: int = 16000) -> None:
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    def call_tone(self, row: dict, kind: str = "outgoing", *,
                  play: bool | None = None) -> dict:
        """A real telephone edge: DTMF for a line we place, a ring for a line arriving.

        The tone is generated before the microphone opens. It is not a decorative sound
        file: outgoing is the verified number's DTMF digits after a dial tone, incoming is
        the two-frequency ring cadence. Both are kept WAV artifacts under the roster.
        """
        with self.lock:
            actual = next((item for item in self.rows if item.get("id") == row.get("id")), None)
            if actual is None:
                raise Refused("civilian-unknown", str(row.get("id") or ""))
            row = actual
            tone = "incoming" if str(kind).lower() == "incoming" else "outgoing"
            path = self.tones / f"{row['id']}-{tone}.wav"
            digits = ""
            if not path.exists() or int(actual.get("call_tone_rev") or 0) != TONE_REV:
                rate = 16000
                samples: list[int] = []

                def add(freqs: tuple[float, ...], seconds: float, amp: float = 0.34) -> None:
                    count = max(1, int(rate * seconds))
                    for index in range(count):
                        moment = index / rate
                        value = amp * sum(math.sin(2 * math.pi * hz * moment) for hz in freqs) / len(freqs)
                        samples.append(int(max(-1.0, min(1.0, value)) * 32767))

                if tone == "incoming":
                    samples.extend([0] * int(rate * 0.08))
                    for _ in range(3):
                        add((440.0, 480.0), 0.46, 0.34)
                        samples.extend([0] * int(rate * 0.22))
                else:
                    add((350.0, 440.0), 0.86, 0.34)
                    samples.extend([0] * int(rate * 0.10))
                    digits = "".join(ch for ch in str(row.get("number") or "") if ch.isdigit())[-7:]
                    for digit in digits:
                        pair = DTMF.get(digit)
                        if pair is None:
                            continue
                        add(pair, 0.12, 0.32)
                        samples.extend([0] * int(rate * 0.045))
                self._tone_wave(path, samples, rate)
            actual["call_tones"] = {**(actual.get("call_tones") or {}), tone: str(path)}
            actual["call_tone_rev"] = TONE_REV
            actual["tone_state"] = "verified"
            self._save()
            played = False
            if play if play is not None else self.play:
                try:
                    import winsound
                    winsound.PlaySound(str(path), winsound.SND_FILENAME)
                    played = True
                except Exception:
                    played = False
            return {"kind": tone, "path": str(path), "digits": digits, "played": played,
                    "civilian": row.get("name"), "number": row.get("number")}

    def dial(self, row: dict, *, play: bool | None = None) -> dict:
        with self.lock:
            actual = next((item for item in self.rows if item.get("id") == row.get("id")), None)
            if actual is None:
                raise Refused("civilian-unknown", str(row.get("id") or ""))
            row = actual
            package_name = f"dialin-{row['id']}"
            payload = self._surface(row)
            manifest = {
                "name": package_name,
                "revision": 1,
                "schemas": sorted([PACKAGE_SCHEMA, SURFACE_SCHEMA]),
                "dependencies": [],
                "entry_points": ["surface"],
                "lengths": {"payload": len(payload)},
            }
            digest = self._digest(manifest, payload)
            target = self.packages / f"{package_name}@1"
            target.mkdir(parents=True, exist_ok=True)
            (target / "payload.bin").write_bytes(payload)
            (target / "manifest.json").write_bytes(_canonical(_kept(manifest)))
            identity = f"{package_name}@1+{digest}"
            (target / "identity.txt").write_text(identity + "\n", encoding="utf-8")
            checked = self.verify_package(target)
            row["package"] = str(target)
            row["package_digest"] = checked["digest"]
            row["source_digest"] = checked["digest"]
            row["package_identity"] = checked["identity"]
            row["tones"] = self._tones(row, checked["digest"])
            # The package owns both call edge tones as retained WAV artifacts. Generating
            # them only at call time left most packages without an incoming ring and let
            # later roster work look like it had removed the dial tone.
            row["call_tones"] = {
                "outgoing": self.call_tone(row, "outgoing", play=False)["path"],
                "incoming": self.call_tone(row, "incoming", play=False)["path"],
            }
            row["tone_state"] = "verified"
            row["verified"] = True
            row["format"] = "modern"
            self._save()
            if (play if play is not None else self.play):
                try:
                    import winsound
                    winsound.PlaySound(str(self.tones / f"{row['id']}.wav"),
                                       winsound.SND_FILENAME)
                except Exception:
                    row["tone_state"] = "generated"
            return dict(row)

    def ingest_corpus(self, path: pathlib.Path | None = None,
                      limit: int = 48) -> list[dict]:
        """Enroll a broad family roster from culture-labelled given/family pairs.

        The old roster was five handpicked names. This reads a corpus, builds every pair
        inside its culture, orders it by a stable digest, and enrolls a wide sample. It is
        deliberately not random at runtime: the same corpus always yields the same
        family, and any additional JSON/CSV corpus can be dropped beside it for ingestion.
        """
        source = pathlib.Path(path or (pathlib.Path(__file__).resolve().parent / "corpora" / "names.json"))
        if not source.exists():
            return []
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        cultures = data.get("cultures") if isinstance(data, dict) else data
        pairs: list[tuple[str, str, str]] = []
        if isinstance(cultures, dict):
            cultures = [{"name": key, **(value or {})} for key, value in cultures.items()]
        for item in cultures or []:
            if not isinstance(item, dict):
                continue
            culture = str(item.get("name") or "family")
            for given in item.get("given") or []:
                for family in item.get("family") or []:
                    if given and family:
                        pairs.append((str(given).strip(), str(family).strip(), culture))
        ranked = sorted(pairs, key=lambda pair: hashlib.sha256(
            f"{pair[2]}|{pair[0]}|{pair[1]}".encode("utf-8")).hexdigest())
        rows = []
        for given, family, culture in ranked[:max(1, int(limit))]:
            display = f"{given} {family}"
            rows.append(self.enroll(display, f"{culture.lower()} civilian",
                                    f"civilian:{_slug(display)}", culture=culture))
        return rows

    def bootstrap(self) -> list[dict]:
        rows = []
        for name, kind, role, identity in CORE:
            row = self.enroll(name, role, f"civilian:{identity}", kind=kind)
            target = pathlib.Path(row.get("package") or "")
            modern = row.get("format") == "modern" and (target / "manifest.json").exists()
            if not row.get("verified") or not modern:
                row = self.dial(row)
            else:
                try:
                    self.verify_package(target)
                    for kind in ("outgoing", "incoming"):
                        self.call_tone(row, kind, play=False)
                    row = dict(next(item for item in self.rows if item["id"] == row["id"]))
                except Refused:
                    row = self.dial(row)
            rows.append(row)
        # The corpus is the family, not a decorative list: each ingested civilian gets a
        # real package and number, but does not play 48 DTMF bursts at startup.
        for row in self.ingest_corpus():
            target = pathlib.Path(row.get("package") or "")
            modern = row.get("format") == "modern" and (target / "manifest.json").exists()
            if not row.get("verified") or not modern:
                row = self.dial(row, play=False)
            else:
                for kind in ("outgoing", "incoming"):
                    self.call_tone(row, kind, play=False)
                row = dict(next(item for item in self.rows if item["id"] == row["id"]))
            rows.append(dict(row))
        return rows

    def state(self) -> dict:
        with self.lock:
            return {
                "schema": SCHEMA,
                "civilians": [dict(row) for row in self.rows],
                "verified": sum(1 for row in self.rows if row.get("verified")),
                "required": True,
                "call": "natural-language",
                "package_schema": PACKAGE_SCHEMA,
                "surface_schema": SURFACE_SCHEMA,
            }
