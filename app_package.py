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

SCHEMA = "popit.app-package/2"
STATE_SCHEMA = "popit.app-packages/2"
APP_SCHEMA = "popit.app/2"
PUBLISHER = "popit-publisher"

# An app is authored, not a folder of files: the signed payload declares what kind of
# surface it is, which page it enters by, what it adds to the shell and what it derives
# from the settings package. A payload that only lists files is a legacy package and is
# refused by name, because nothing in it says how the app joins the family.
DERIVES = {"package": "popit-settings", "fields": ["theme", "layout", "motion", "dpi"]}

# A window package is furniture, not a page: dialin has a bar, a status strip, a body and a
# foot. An app that declares fewer regions, or whose entry page does not carry them, is
# refused `app-window-incomplete` — the thin-page class never gets a signature.
REGION_CONTRACT = ("bar", "status", "body", "foot")
REGIONS = list(REGION_CONTRACT)

# The only signing forms a mutable package may take are the three reference packages':
# dialin and settings are `window`, the springboard is `phone`. A surface hosted inside a
# window is not a package and has no identity of its own; it is refused `app-kind-foreign`
# rather than signed as a fourth kind. The IDE is exactly that case.
KINDS = ("window", "phone")
FOREIGN = {"ide": "surface"}

APPS = {
    "dialin": {
        "kind": "window",
        "entry": "toast.html",
        "title": "DialIn desk",
        "summary": "the agent desk: calls, lanes, the voice document and the window chrome",
        "pages": ["local", "mind", "settings", "call"],
        "adds": ["call desk", "lane selection", "voice document", "probe log",
                 "hosted IDE surface"],
        "hosts": ["ide", "bridge"],
        "regions": REGIONS,
        "files": ("toast.html", "toast.js", "toast.css", "package.js", "contour-theme.css",
                  "ui-audit.js"),
    },
    "bridge": {
        "kind": "window",
        "entry": "bridge.html",
        "title": "Bridge",
        "summary": "the client's tools side on the family Debian box: host, steam, proton, queue",
        "pages": ["host", "tools", "queue"],
        "adds": ["host audit", "steam and proton rows", "job queue", "a remote command from the window"],
        "hosts": [],
        "regions": REGIONS,
        # No stylesheet of its own: the window wears contour-theme.css and the desk's chrome
        # stylesheet, and package.js applies the published theme, motion and DPI.
        "files": ("bridge.html", "bridge.js", "package.js", "contour-theme.css", "toast.css",
                  "ui-audit.js"),
    },
    "settings": {
        "kind": "window",
        "entry": "settings.html",
        "title": "Settings package",
        "summary": "the mutable base: appearance, motion, layout, apps and functions",
        "pages": ["appearance", "motion", "layout", "apps", "functions", "device", "package"],
        "adds": ["appearance", "motion", "layout", "apps", "functions", "device", "package"],
        "regions": REGIONS,
        "files": ("settings.html", "settings.js", "settings.css", "package.js", "ui-audit.js"),
    },
    "springboard": {
        "kind": "phone",
        "entry": "phone.html",
        "title": "SpringBoard",
        "summary": "the home: signed tiles that launch apps by name",
        "pages": ["home", "dialin", "settings"],
        "adds": ["signed tiles", "app launch", "offline shell"],
        "regions": REGIONS,
        "files": ("phone.html", "phone.js", "phone.css", "phone-sw.js", "package.js",
                  "contour-theme.css", "ui-audit.js"),
    },
}

FILES = {name: spec["files"] for name, spec in APPS.items()}


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


def _spec(name: str) -> dict:
    """The signing form for a name. A foreign surface is refused, never signed."""
    kind = FOREIGN.get(name)
    if kind:
        raise Refused("app-kind-foreign",
                      f"{name}: a {kind} is hosted by its window, not signed as a package")
    spec = APPS.get(name)
    if spec is None:
        raise Refused("app-unknown", str(name))
    if spec["kind"] not in KINDS:
        raise Refused("app-kind-foreign", f"{name}: {spec['kind']} is not a mutable kind")
    return spec


def _files(facts: dict) -> list[dict]:
    return [facts[name] for name in sorted(facts)]


class AppPackages:
    """The signed identity of every surface this shell serves."""

    def __init__(self, root: pathlib.Path, ui_root: pathlib.Path, *,
                 settings: settings_package.SettingsPackage, drivers=None) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ui_root = pathlib.Path(ui_root)
        self.packages = self.root / "packages"
        self.packages.mkdir(exist_ok=True)
        self.state_path = self.root / "apps.json"
        self.ui_audit_path = self.root / "ui-audit.json"
        self.settings = settings
        # The fleet that develops packages. A mutation names the driver that carried it, so
        # the store can say who developed a package instead of attributing it to nobody.
        self.drivers = drivers
        self.key = settings.key
        self.public_key = settings.public_key
        self.trust_path = settings.trust_path
        self.lock = threading.RLock()

    # -- identity -----------------------------------------------------------------------
    def _read(self, name: str) -> dict:
        facts = {}
        for file in FILES[name]:
            target = self.ui_root / file
            if not target.exists():
                raise Refused("app-file-absent", f"{name}: {file}")
            data = target.read_bytes()
            facts[file] = {"name": file, "bytes": len(data),
                           "digest": "blake3:" + blake3(data).hexdigest()}
        return facts

    def payload(self, name: str) -> bytes:
        spec = _spec(name)
        authored = {key: spec[key] for key in
                    ("kind", "entry", "title", "summary", "pages", "adds", "regions")}
        authored["hosts"] = list(spec.get("hosts") or [])
        return dialin.canonical_json({
            "schema": APP_SCHEMA,
            "app": name,
            "authored": authored,
            "derives": DERIVES,
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
    def _driver(self) -> str:
        """The fleet driver that carries this mutation, or '' when no fleet is attached."""
        if self.drivers is None:
            return ""
        try:
            state = self.drivers.state()
        except Exception:  # noqa: BLE001 - a fleet that cannot answer is no driver
            return ""
        tasks = state.get("tasks") or []
        if tasks and tasks[0].get("driver"):
            return str(tasks[0]["driver"])
        rows = state.get("drivers") or []
        return str(rows[0].get("id")) if rows else ""

    def _driver_ids(self) -> list[str]:
        if self.drivers is None:
            return []
        try:
            rows = self.drivers.state().get("drivers") or []
        except Exception:  # noqa: BLE001
            return []
        return [str(row.get("id")) for row in rows if row.get("id")]

    def publish(self, name: str, driver: str = "") -> dict:
        """Sign the app's current files and keep the package beside the settings ones."""
        _ = _spec(name)
        with self.lock:
            state = self._state()
            previous = state["apps"].get(name) or {}
            revision = int(previous.get("revision") or 0) + 1
            # A republish is a mutation: the CUA driver that changed the package is named
            # in the signed record. With a fleet attached, a mutation without a live driver
            # is refused rather than attributed to nobody.
            if revision > 1 and self.drivers is not None:
                live = self._driver_ids()
                if not driver or driver not in live:
                    raise Refused("app-no-driver",
                                  f"{name}: {driver or 'no driver'} is not a live CUA driver")
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
                "schemas": sorted([dialin.PACKAGE_SCHEMA, APP_SCHEMA, SCHEMA]),
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
                "app_standard": APP_SCHEMA,
                "identity": identity,
                "digest": digest,
                "payload_digest": "blake3:" + blake3(payload).hexdigest(),
                "revision": revision,
                "published_at": iso(),
                "ui_audit": audit_state,
                "driver": driver,
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
                "ui_audit": audit_state,
                "driver": driver,
            }
            self._write_state(state)
            self.verify(name)
            return self.document(name)

    def ensure(self, name: str) -> dict:
        """Publish when the app has no package, its files moved on, or its audit is new.

        A surface is signed before it is measured, so the first record carries
        `ui_audit: pending`. The measurement arrives later, against the same bytes; without
        republishing here that clean report could never lift the pending state, and the
        documented "a passing measurement republishes the app" would not happen.
        """
        driver = self._driver()
        held = self._held(name)
        if not held:
            return self.publish(name, driver=driver)
        target = pathlib.Path(held["package"])
        payload_path = target / "payload.bin"
        if not payload_path.exists():
            return self.publish(name, driver=driver)
        payload = self.payload(name)
        if payload_path.read_bytes() != payload:
            return self.publish(name, driver=driver)
        try:
            record = json.loads((target / "signature.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.publish(name, driver=driver)
        if record.get("ui_audit") != "passed":
            audit = self.ui_audit(name)
            if (audit and not audit.get("findings")
                    and audit.get("payload_digest") == "blake3:" + blake3(payload).hexdigest()):
                return self.publish(name, driver=driver)
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
        _ = _spec(name)
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
        _ = _spec(name)
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
        # A payload that only lists files predates the authored standard: it says nothing
        # about how the app joins the shell, so it is refused as legacy before any tamper
        # comparison, which would otherwise report the upgrade as a changed file.
        try:
            body = json.loads(published.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Refused("app-legacy", f"{name}: payload is not an authored document")
        if body.get("schema") != APP_SCHEMA:
            raise Refused("app-legacy", f"{name}: {body.get('schema')} is not {APP_SCHEMA}")
        authored = body.get("authored") or {}
        missing = [key for key in ("kind", "entry", "title", "pages", "adds")
                   if not authored.get(key)]
        if missing:
            raise Refused("app-not-authored", f"{name}: manifest missing {', '.join(missing)}")
        if "theme" not in (body.get("derives") or {}).get("fields", []):
            raise Refused("app-not-authored", f"{name}: does not derive the settings theme")
        # The window contract: the manifest declares the family regions and the entry page
        # actually carries them. A page with a header and a list is not a window package.
        declared = authored.get("regions") or []
        absent = [region for region in REGION_CONTRACT if region not in declared]
        if absent:
            raise Refused("app-window-incomplete",
                          f"{name}: regions not declared: {', '.join(absent)}")
        entry = self.ui_root / str(authored.get("entry") or "")
        try:
            page = entry.read_text(encoding="utf-8")
        except OSError:
            raise Refused("app-window-incomplete", f"{name}: entry page is unreadable")
        missing_regions = [region for region in REGION_CONTRACT
                           if f'data-region="{region}"' not in page]
        if missing_regions:
            raise Refused("app-window-incomplete",
                          f"{name}: entry lacks {', '.join(missing_regions)}")
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
            "app_standard": record.get("app_standard", APP_SCHEMA),
            "driver": record.get("driver", ""),
            "authored": body.get("authored") or {},
            "derives": body.get("derives") or {},
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
        _ = _spec(name)
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
            "app_standard": facts.get("app_standard", APP_SCHEMA),
            "authored": facts.get("authored") or {},
            "derives": facts.get("derives") or {},
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
            spec = APPS[name]
            row = {"app": name, "identity": held["identity"] if held else "",
                   "kind": spec["kind"], "entry": spec["entry"],
                   "pages": len(spec["pages"]), "regions": len(spec["regions"]),
                   "app_standard": APP_SCHEMA, "driver": "",
                   "verified": False, "ui_audit": "", "refused": None}
            try:
                facts = self.verify(name)
                row.update({"identity": facts["identity"], "verified": True,
                            "revision": facts["revision"],
                            "ui_audit": facts.get("ui_audit", ""),
                            "driver": facts.get("driver", "")})
            except Refused as error:
                row["refused"] = error.as_dict()
            rows[name] = row
        # A foreign surface is reported, not hidden: the springboard and the store both
        # read this list to say why the IDE is not a signed package.
        foreign = {}
        for name, kind in FOREIGN.items():
            try:
                _spec(name)
            except Refused as error:
                foreign[name] = {"kind": kind, "refused": error.as_dict()}
        return {"schema": STATE_SCHEMA, "publisher": PUBLISHER,
                "kinds": list(KINDS), "foreign": foreign,
                "fingerprint": envelope.fingerprint(self.public_key),
                "trust": str(self.trust_path), "apps": rows}
