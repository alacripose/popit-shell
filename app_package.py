"""App packages: every Popit surface names its bytes and is signed by the family publisher.

The settings package proved the shape (canonical JSON, `secure-shell.package/1` identity,
one Ed25519 signature over the identity record, the same trust registry the phone uses).
This module applies that shape to every app the shell serves, so a surface is not just a
page: it is a package with an identity a window can show and a signature it can refuse.

The identity is over the *served* files, not a build. Hashing the files the server hands
out means the identity a window reads is the identity it is actually running; a file that
changed after publishing is refused by name (`app-tampered`) instead of being served
quietly under an old signature.

The publisher key is the settings package's key, and the trust file is the one the phone
and the settings window already read, so there is one publisher and one registry rather
than a second authority per app.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import threading

from blake3 import blake3

import dialin
import envelope
import settings_package

SCHEMA = "popit.app-package/1"
STATE_SCHEMA = "popit.app-packages/1"
PUBLISHER = "popit-publisher"

# The files each app actually serves. A file that is not listed is not part of the app's
# identity, so adding a surface means adding it here rather than widening the trust.
APPS = {
    "dialin": ("toast.html", "toast.js", "toast.css", "package.js", "contour-theme.css",
               "ui-audit.js"),
    "settings": ("settings.html", "settings.js", "settings.css", "package.js", "ui-audit.js"),
    "springboard": ("phone.html", "phone.js", "phone.css", "phone-sw.js", "package.js",
                    "contour-theme.css", "ui-audit.js"),
}


class Refused(Exception):
    """A named refusal; a package that cannot be shown is refused, never guessed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def _files(facts: dict) -> list[dict]:
    return [facts[name] for name in sorted(facts)]


class AppPackages:
    """The signed identity of every surface this shell serves."""

    def __init__(self, root: pathlib.Path, ui_root: pathlib.Path, *,
                 settings: settings_package.SettingsPackage) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ui_root = pathlib.Path(ui_root)
        self.packages = self.root / "packages"
        self.packages.mkdir(exist_ok=True)
        self.state_path = self.root / "apps.json"
        self.ui_audit_path = self.root / "ui-audit.json"
        self.settings = settings
        self.key = settings.key
        self.public_key = settings.public_key
        self.trust_path = settings.trust_path
        self.lock = threading.RLock()

    # -- identity -----------------------------------------------------------------------
    def _read(self, name: str) -> dict:
        facts = {}
        for file in APPS[name]:
            target = self.ui_root / file
            if not target.exists():
                raise Refused("app-file-absent", f"{name}: {file}")
            data = target.read_bytes()
            facts[file] = {"name": file, "bytes": len(data),
                           "digest": "blake3:" + blake3(data).hexdigest()}
        return facts

    def payload(self, name: str) -> bytes:
        if name not in APPS:
            raise Refused("app-unknown", str(name))
        return dialin.canonical_json({
            "schema": SCHEMA,
            "app": name,
            "files": _files(self._read(name)),
        })

    def _state(self) -> dict:
        if not self.state_path.exists():
            return {"schema": STATE_SCHEMA, "apps": {}}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema": STATE_SCHEMA, "apps": {}}
        if not isinstance(value, dict) or not isinstance(value.get("apps"), dict):
            return {"schema": STATE_SCHEMA, "apps": {}}
        return value

    def _write_state(self, state: dict) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True,
                                              ensure_ascii=False) + "\n", encoding="utf-8")

    def _held(self, name: str) -> dict | None:
        row = self._state()["apps"].get(name)
        return row if isinstance(row, dict) and row.get("package") else None

    # -- publishing ---------------------------------------------------------------------
    def publish(self, name: str) -> dict:
        """Sign the app's current files and keep the package beside the settings ones."""
        if name not in APPS:
            raise Refused("app-unknown", str(name))
        with self.lock:
            state = self._state()
            previous = state["apps"].get(name) or {}
            revision = int(previous.get("revision") or 0) + 1
            payload = self.payload(name)
            payload_digest = "blake3:" + blake3(payload).hexdigest()
            # A package is signed only after its page has been measured. Overlapping
            # controls, a clipped reading or a locked horizontal axis are refusals named
            # here, so a signature never covers a surface that cannot be drawn.
            audit = self.ui_audit(name)
            if audit is not None and audit.get("payload_digest") != payload_digest:
                audit = None  # a measurement of other bytes says nothing about these
            if audit is not None and audit.get("findings"):
                codes = sorted({str(row.get("code", "ui")) for row in audit["findings"]
                                if isinstance(row, dict)})
                raise Refused("app-ui-audit", f"{name}: " + ", ".join(codes[:6]))
            audit_state = "passed" if audit is not None else "pending"
            manifest = {
                "name": f"app-{name}",
                "revision": revision,
                "schemas": sorted([dialin.PACKAGE_SCHEMA, SCHEMA]),
                "dependencies": [],
                "entry_points": ["surface"],
                "lengths": {"payload": len(payload)},
            }
            digest = dialin.package_digest(manifest, payload)
            identity = f"app-{name}@{revision}+{digest}"
            target = self.packages / f"app-{name}@{revision}"
            target.mkdir(parents=True, exist_ok=True)
            (target / "payload.bin").write_bytes(payload)
            (target / "manifest.json").write_bytes(
                dialin.canonical_json(dialin._kept(manifest)))
            (target / "identity.txt").write_text(identity + "\n", encoding="utf-8")
            record = {
                "schema": SCHEMA,
                "app": name,
                "identity": identity,
                "digest": digest,
                "payload_digest": "blake3:" + blake3(payload).hexdigest(),
                "revision": revision,
                "published_at": iso(),
                "ui_audit": audit_state,
                "public_key": self.public_key,
                "signature_algorithm": envelope.SIGNATURE_ALGORITHM,
            }
            record["signature"] = envelope.sign_payload(record, self.key)
            (target / "signature.json").write_text(
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8")
            state["apps"][name] = {
                "package": str(target),
                "identity": identity,
                "digest": digest,
                "payload_digest": record["payload_digest"],
                "revision": revision,
                "published_at": record["published_at"],
            }
            self._write_state(state)
            self.verify(name)
            return self.document(name)

    def ensure(self, name: str) -> dict:
        """Publish when the app has no package, or when the served files moved on."""
        held = self._held(name)
        if not held:
            return self.publish(name)
        target = pathlib.Path(held["package"])
        if not (target / "payload.bin").exists():
            return self.publish(name)
        if (target / "payload.bin").read_bytes() != self.payload(name):
            return self.publish(name)
        return self.document(name)

    def ensure_all(self) -> dict:
        rows = {}
        for name in APPS:
            try:
                rows[name] = self.ensure(name)
            except Refused as error:
                rows[name] = {"app": name, "verified": False, "refused": error.as_dict()}
        return rows

    # -- surface audit ------------------------------------------------------------------
    def ui_audit(self, name: str) -> dict | None:
        """The last measured surface report for this app, or None when it was never run."""
        try:
            rows = json.loads(self.ui_audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        row = (rows.get("apps") or {}).get(name)
        return row if isinstance(row, dict) else None

    def record_ui_audit(self, name: str, report: dict) -> dict:
        """Keep the page's own measurement, keyed to the bytes it measured."""
        if name not in APPS:
            raise Refused("app-unknown", str(name))
        findings = report.get("findings") if isinstance(report.get("findings"), list) else []
        digest = "blake3:" + blake3(self.payload(name)).hexdigest()
        with self.lock:
            try:
                held = json.loads(self.ui_audit_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                held = {}
            apps = held.get("apps") if isinstance(held.get("apps"), dict) else {}
            apps[name] = {
                "payload_digest": digest,
                "findings": [row for row in findings[:12] if isinstance(row, dict)],
                "size": report.get("size") if isinstance(report.get("size"), dict) else {},
                "at": iso(),
                "schema": str(report.get("schema") or "popit.ui-audit/1"),
            }
            self.ui_audit_path.write_text(
                json.dumps({"schema": "popit.ui-audit-store/1", "apps": apps},
                           indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return apps[name]

    # -- verifying ----------------------------------------------------------------------
    def verify(self, name: str) -> dict:
        """The package must still describe the files, and the publisher must be trusted."""
        if name not in APPS:
            raise Refused("app-unknown", str(name))
        held = self._held(name)
        if not held:
            raise Refused("app-unsigned", str(name))
        target = pathlib.Path(held["package"])
        record_path = target / "signature.json"
        if not record_path.exists():
            raise Refused("app-unsigned", str(name))
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise Refused("app-record", str(error)[:200]) from error
        published = (target / "payload.bin").read_bytes()
        if published != self.payload(name):
            raise Refused("app-tampered", f"{name}: served files differ from {held['identity']}")
        if "blake3:" + blake3(published).hexdigest() != record.get("payload_digest"):
            raise Refused("app-tampered", f"{name}: payload digest does not match its record")
        # Recompute the identity from the bytes rather than trusting the record's copy.
        try:
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise Refused("app-record", str(error)[:200]) from error
        digest = dialin.package_digest(manifest, published)
        identity = f"app-{name}@{manifest['revision']}+{digest}"
        if (target / "identity.txt").read_text(encoding="utf-8").strip() != identity:
            raise Refused("app-identity", f"{name}: identity.txt does not recompute")
        if record.get("identity") != identity:
            raise Refused("app-identity", f"{name}: the signature names another identity")
        signature = str(record.get("signature") or "")
        public_key = str(record.get("public_key") or "")
        # The signature is over the record without its own signature field, exactly as the
        # settings publisher signs its record.
        unsigned = {key: value for key, value in record.items() if key != "signature"}
        if not envelope.verify_payload(unsigned, signature, public_key):
            raise Refused("app-signature", name)
        if not envelope.trusted(public_key, trust_path=self.trust_path):
            raise Refused("app-untrusted", name)
        return {
            "app": name,
            "verified": True,
            "ui_audit": record.get("ui_audit", ""),
            "identity": identity,
            "digest": digest,
            "payload_digest": record.get("payload_digest", ""),
            "revision": int(record.get("revision") or 0),
            "published_at": record.get("published_at", ""),
            "files": json.loads(published.decode("utf-8")).get("files", []),
            "public_key": public_key,
            "signature": signature,
            "signature_algorithm": record.get("signature_algorithm", ""),
        }

    def document(self, name: str) -> dict:
        """What a window reads: the signed identity plus the theme the family published."""
        if name not in APPS:
            raise Refused("app-unknown", str(name))
        facts = self.verify(name)
        theme = {}
        theme_identity = ""
        try:
            delivery = self.settings.delivery()
            theme = delivery.get("settings") or {}
            theme_identity = delivery.get("identity", "")
        except settings_package.Refused:
            theme = self.settings.current()
        return {
            "schema": SCHEMA,
            "state": "delivered",
            "app": name,
            "identity": facts["identity"],
            "digest": facts["digest"],
            "revision": facts["revision"],
            "published_at": facts["published_at"],
            "ui_audit": facts.get("ui_audit", ""),
            "files": facts["files"],
            "public_key": facts["public_key"],
            "signature": facts["signature"],
            "signature_algorithm": facts["signature_algorithm"],
            "verified": True,
            "theme": theme,
            "theme_identity": theme_identity,
            "theme_verifier": PUBLISHER,
        }

    def state(self) -> dict:
        rows = {}
        for name in APPS:
            held = self._held(name)
            row = {"app": name, "identity": held["identity"] if held else "",
                   "verified": False, "refused": None}
            try:
                facts = self.verify(name)
                row.update({"identity": facts["identity"], "verified": True,
                            "revision": facts["revision"]})
            except Refused as error:
                row["refused"] = error.as_dict()
            rows[name] = row
        return {"schema": STATE_SCHEMA, "publisher": PUBLISHER,
                "fingerprint": envelope.fingerprint(self.public_key),
                "trust": str(self.trust_path), "apps": rows}
