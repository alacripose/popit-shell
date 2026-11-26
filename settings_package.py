"""The settings package the Popit shell publishes to its own windows.

The settings app is the panel the owner already has: family frame, Goodies material,
motion type, palette planetoids, DPI and the reduced-motion preference. This module does
not replace any of that. It packages what the panel holds into one modern Secure Shell
package and serves it, so another Popit window reads the same settings from a verified
identity instead of a second copy of the panel's JavaScript state.

Two owner rulings decide the shape:

* **N024 — "A streamed settings package owns device reporting."** The device report is
  part of the package payload, measured when the package is published, so a window that
  subscribes gets the owner's screen facts from the same signed document as the theme.
* **N014 — "Device limits recorded honestly so settings can offer display options."**
  The report is read from the machine (`GetSystemMetrics`, `shcore`, `platform`), never
  assumed, and a value the platform will not answer is `null` rather than a guess.

Identity is the family package vocabulary, not a second format: `dialog.canonical`'s
`name@revision+blake3:<hex>` digest over a canonical manifest plus the payload, and the
publisher's Ed25519 key from `envelope.py`. A subscription is a signed request verified
against the same trust registry calls use, with a single-use nonce.

The signature covers the package identity *and* the payload digest, so a subscriber can
check both the document it was handed and the bytes it decodes. A package whose payload
no longer matches its signature is refused by name; it is never delivered with a warning.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import platform
import re
import threading

from blake3 import blake3

import dialin
import envelope

SCHEMA = "popit.settings/1"
SUBSCRIPTION_SCHEMA = "popit.settings-subscription/1"
NAME = "popit-settings"
PUBLISHER = "Popit settings publisher"
MAX_AGE_SECONDS = 900
MAX_NONCES = 500
NONCE_RE = re.compile(r"^[0-9a-f]{32,64}$")

FRAMES = ("popit", "ios", "material", "touchwiz")
MATERIALS = ("paper", "card", "glass", "tint", "ink", "accent", "bare")
MOTION_TYPES = ("reveal", "pop", "fold", "snap", "sweep")
# The family roles the shared surface theme paints from. A palette publishes them so an
# app package can paint the same surface without resolving the theme itself.
COLOR_ROLES = ("surface", "primary", "tertiary", "emphasis", "ink", "line", "panel",
               "card", "meta", "deep")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MOTION_PREFERENCES = ("full", "reduced")
DPI_MIN, DPI_MAX, DPI_STEP = 60, 180, 5
MAX_PALETTES = 64
MAX_PALETTE_BYTES = 64 * 1024

# Layout is carried by the same signed document as the theme: an app reads its own
# columns, gutter, padding, rail width and density, so a layout change is published once
# and every window derives it rather than hard-coding a frame of its own.
LAYOUT_APPS = ("dialin", "settings", "springboard", "bridge")
LAYOUT_DENSITIES = ("compact", "regular", "roomy")
LAYOUT_BOUNDS = {
    "columns": (1, 4),
    "gutter": (0, 32),
    "pad": (0, 32),
    "rail": (0, 420),
}
_DEFAULT_LAYOUT = {
    "dialin": {"columns": 1, "gutter": 8, "pad": 8, "rail": 0, "density": "regular"},
    "settings": {"columns": 2, "gutter": 16, "pad": 18, "rail": 184, "density": "regular"},
    "springboard": {"columns": 3, "gutter": 11, "pad": 16, "rail": 0, "density": "roomy"},
    "bridge": {"columns": 1, "gutter": 10, "pad": 12, "rail": 0, "density": "regular"},
}

REFUSALS = (
    "settings-dpi",
    "settings-frame",
    "settings-layout",
    "settings-material",
    "settings-motion",
    "settings-palette",
    "settings-package-absent",
    "settings-package-unsigned",
    "settings-request",
    "settings-replay",
    "settings-signature",
    "settings-theme",
    "settings-untrusted",
)


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


class Refused(Exception):
    """A named refusal, the shape every package module in this family uses."""

    def __init__(self, code: str, detail: str) -> None:
        assert code in REFUSALS, code
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def device_report() -> dict:
    """What this machine will actually tell us, and `null` where it will not."""
    report: dict = {
        "reported_at": iso(),
        "platform": platform.system() or None,
        "machine": platform.machine() or None,
        "python": platform.python_version(),
        "screen": None,
        "virtual_screen": None,
        "monitors": None,
        "dpi": None,
    }
    try:
        import ctypes

        user32 = ctypes.windll.user32
        width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if width > 0 and height > 0:
            report["screen"] = [int(width), int(height)]
        virtual_width, virtual_height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        if virtual_width > 0 and virtual_height > 0:
            report["virtual_screen"] = [int(virtual_width), int(virtual_height)]
        monitors = user32.GetSystemMetrics(80)
        if monitors > 0:
            report["monitors"] = int(monitors)
        try:
            dpi = ctypes.windll.shcore.GetDpiForSystem()
            if dpi > 0:
                report["dpi"] = int(dpi)
        except (AttributeError, OSError):
            pass
    except (AttributeError, OSError):
        pass
    return report


def _validate(settings: dict) -> dict:
    """Only the values the settings app can actually draw pass; anything else is named."""
    frame = str(settings.get("frame") or "")
    if frame not in FRAMES:
        raise Refused("settings-frame", f"{frame!r} is not one of {', '.join(FRAMES)}")
    material = str(settings.get("material") or "")
    if material not in MATERIALS:
        raise Refused("settings-material",
                      f"{material!r} is not one of {', '.join(MATERIALS)}")
    motion = str(settings.get("motion") or "")
    if motion not in MOTION_TYPES:
        raise Refused("settings-motion",
                      f"{motion!r} is not one of {', '.join(MOTION_TYPES)}")
    preference = str(settings.get("motionPreference") or "")
    if preference not in MOTION_PREFERENCES:
        raise Refused("settings-motion",
                      f"{preference!r} is not one of {', '.join(MOTION_PREFERENCES)}")
    try:
        dpi = int(settings.get("dpi"))
    except (TypeError, ValueError):
        raise Refused("settings-dpi", "dpi must be an integer")
    if dpi < DPI_MIN or dpi > DPI_MAX or dpi % DPI_STEP:
        raise Refused("settings-dpi", f"{dpi} is outside {DPI_MIN}..{DPI_MAX} step {DPI_STEP}")
    theme = _text(settings.get("theme") or "popit", 60)
    if not theme:
        raise Refused("settings-theme", "a theme id is required")
    palettes = settings.get("palettes") or []
    if not isinstance(palettes, list) or len(palettes) > MAX_PALETTES:
        raise Refused("settings-palette", f"palettes must be a list of at most {MAX_PALETTES}")
    held = json.dumps(palettes, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if len(held) > MAX_PALETTE_BYTES:
        raise Refused("settings-palette", f"palettes exceed {MAX_PALETTE_BYTES} bytes")
    for row in palettes:
        if not isinstance(row, dict) or not _text(row.get("name"), 60):
            raise Refused("settings-palette", "every palette needs a name")
    colors = settings.get("colors") or {}
    if not isinstance(colors, dict):
        raise Refused("settings-colors", "colors must be an object of family roles")
    held_colors = {}
    for role, value in colors.items():
        name = str(role)
        if name not in COLOR_ROLES:
            raise Refused("settings-colors", f"{name!r} is not one of {', '.join(COLOR_ROLES)}")
        text = str(value or "").strip()
        if not COLOR_RE.fullmatch(text):
            raise Refused("settings-colors", f"{name} is not a #rrggbb colour: {text!r}")
        held_colors[name] = text
    layout = settings.get("layout") or {}
    if not isinstance(layout, dict):
        raise Refused("settings-layout", "layout must be an object of per-app layouts")
    held_layout: dict = {}
    for name, row in layout.items():
        if name not in LAYOUT_APPS:
            raise Refused("settings-layout",
                          f"{name!r} is not one of {', '.join(LAYOUT_APPS)}")
        if not isinstance(row, dict):
            raise Refused("settings-layout", f"{name} layout must be an object")
        checked_row: dict = {}
        for key, (low, high) in LAYOUT_BOUNDS.items():
            fallback = _DEFAULT_LAYOUT[name][key]
            try:
                value = int(row.get(key, fallback))
            except (TypeError, ValueError):
                raise Refused("settings-layout", f"{name}.{key} must be an integer")
            if value < low or value > high:
                raise Refused("settings-layout",
                              f"{name}.{key}={value} is outside {low}..{high}")
            checked_row[key] = value
        density = str(row.get("density") or _DEFAULT_LAYOUT[name]["density"])
        if density not in LAYOUT_DENSITIES:
            raise Refused("settings-layout",
                          f"{name}.density {density!r} is not one of "
                          f"{', '.join(LAYOUT_DENSITIES)}")
        checked_row["density"] = density
        held_layout[name] = checked_row
    # An older package predates layout: it keeps the family defaults rather than refusing.
    for name in LAYOUT_APPS:
        held_layout.setdefault(name, dict(_DEFAULT_LAYOUT[name]))
    return {
        "theme": theme,
        "frame": frame,
        "material": material,
        "motion": motion,
        "motionPreference": preference,
        "dpi": dpi,
        "palettes": palettes,
        "colors": held_colors,
        "layout": held_layout,
    }


class SettingsPackage:
    """One published settings package, its signature, and who may subscribe to it."""

    def __init__(self, root: pathlib.Path, *, trust_path: pathlib.Path | None = None,
                 publisher: str = PUBLISHER) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.packages = self.root / "packages"
        self.packages.mkdir(exist_ok=True)
        self.key = self.root / "settings.key"
        self.public_path = self.root / "settings.pem"
        self.state_path = self.root / "settings.json"
        self.subscription_path = self.root / "subscriptions.json"
        self.trust_path = pathlib.Path(
            trust_path or (self.root.parent / "envelope-trust.json"))
        self.publisher = publisher
        self.lock = threading.RLock()
        if not self.key.exists() or not self.public_path.exists():
            envelope.keygen(self.key, self.public_path)
        self.public_key = self.public_path.read_text(encoding="utf-8").strip()
        # The publisher is a named key in the same registry callers use, so a window
        # verifies the settings document with the mechanism it already has.
        try:
            envelope.trust_key(self.public_key, publisher, self.trust_path)
        except envelope.Refused:
            pass

    # -- what the panel holds -----------------------------------------------------------
    def defaults(self) -> dict:
        return {
            "theme": "popit",
            "frame": "popit",
            "material": "paper",
            "motion": "reveal",
            "motionPreference": "full",
            "dpi": 100,
            "palettes": [],
            "colors": {},
            "layout": {name: dict(row) for name, row in _DEFAULT_LAYOUT.items()},
        }

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def current(self) -> dict:
        with self.lock:
            held = self._read_state()
            settings = dict(self.defaults())
            if isinstance(held.get("settings"), dict):
                settings.update(held["settings"])
            # A stored layout for an app that no longer exists is dropped, never published:
            # the retired IDE surface left one behind, and a layout row is a signed value.
            layout = settings.get("layout")
            if isinstance(layout, dict):
                settings["layout"] = {name: row for name, row in layout.items()
                                      if name in LAYOUT_APPS}
            return settings

    def adopt(self, settings: dict) -> dict:
        """Take the settings the panel just changed. Adopting is not publishing.

        The panel stays the authoring surface: this stores what it holds without minting
        a new package revision, so a revision always means the owner published one.
        """
        if not isinstance(settings, dict):
            raise Refused("settings-request", "settings must be a JSON object")
        merged = dict(self.current())
        merged.update({key: value for key, value in settings.items()
                       if key in self.defaults()})
        checked = _validate(merged)
        with self.lock:
            held = self._read_state()
            held.update({"schema": SCHEMA, "settings": checked})
            held.setdefault("revision", 0)
            self.state_path.write_text(
                json.dumps(held, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8")
        return checked

    def package_document(self) -> dict:
        """The published document as bytes, so any reader can recompute the identity."""
        target = self._latest()
        self.verify(target)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        payload = (target / "payload.bin").read_bytes()
        record = json.loads((target / "signature.json").read_text(encoding="utf-8"))
        return {
            "schema": SCHEMA,
            "state": "published",
            "manifest": manifest,
            "payload": payload.decode("utf-8"),
            "identity": record["identity"],
            "digest": record["digest"],
            "payload_digest": record["payload_digest"],
            "signature": record["signature"],
            "public_key": record["public_key"],
            "package": str(target),
        }

    # -- build, sign, verify ------------------------------------------------------------
    def publish(self, settings: dict | None = None, *, device: dict | None = None) -> dict:
        """Write the package for these settings and sign its identity and payload."""
        with self.lock:
            merged = dict(self.current())
            if isinstance(settings, dict):
                merged.update({key: value for key, value in settings.items()
                               if key in self.defaults()})
            checked = _validate(merged)
            held = self._read_state()
            # A publish that changes nothing is the same package, not a new revision. Every
            # app subscribes to this identity, so minting a revision on a no-op push would
            # invalidate every window a moment after it was signed (the settings window's own
            # attach included) and the desk would be refused app-base-stale while the owner
            # is using it.
            same_settings = held.get("settings") == checked
            held_device = held.get("device")
            if isinstance(device, dict):
                report = device
            elif same_settings and isinstance(held_device, dict) and held_device:
                # The device report carries live readings; reusing the published one keeps the
                # signed identity still until the owner changes a setting.
                report = held_device
            else:
                report = device_report()
            # A package signed before preferences were removed from signed bytes still carries
            # them. That payload is not a no-op: it is re-signed without them, so the digest
            # cannot keep a copy of the owner's material, frame, motion, dpi or device.
            carries_preferences = False
            try:
                body = json.loads((self._latest() / "payload.bin").read_text(encoding="utf-8"))
                carries_preferences = any(key in body for key in ("settings", "device"))
            except (OSError, ValueError):
                carries_preferences = False
            if held.get("identity") and same_settings and held_device == report \
                    and not carries_preferences:
                return {**self.verify(self._latest()), "delivery": self.delivery()}
            revision = int(held.get("revision") or 0) + 1
            published_at = iso()
            # The signed bytes name the document and a digest of what was authored. They do not
            # carry the preference values themselves: a value in a package is a value re-signed
            # into every window, and the owner's material, frame, motion and dpi are the owner's
            # local state, read live by the windows that already trust this identity.
            payload = dialin.canonical_json({
                "schema": SCHEMA,
                "name": NAME,
                "revision": revision,
                "published_at": published_at,
                "settings_digest": "blake3:" + blake3(
                    dialin.canonical_json(checked)).hexdigest(),
                "settings_keys": sorted(checked),
            })
            manifest = {
                "name": NAME,
                "revision": revision,
                "schemas": sorted([dialin.PACKAGE_SCHEMA, SCHEMA]),
                "dependencies": [],
                "entry_points": ["surface"],
                "lengths": {"payload": len(payload)},
            }
            digest = dialin.package_digest(manifest, payload)
            identity = f"{NAME}@{revision}+{digest}"
            target = self.packages / f"{NAME}@{revision}"
            target.mkdir(parents=True, exist_ok=True)
            (target / "payload.bin").write_bytes(payload)
            (target / "manifest.json").write_bytes(
                dialin.canonical_json(dialin._kept(manifest)))
            (target / "identity.txt").write_text(identity + "\n", encoding="utf-8")
            record = {
                "schema": SCHEMA,
                "identity": identity,
                "digest": digest,
                "payload_digest": "blake3:" + blake3(payload).hexdigest(),
                "revision": revision,
                "published_at": published_at,
                "public_key": self.public_key,
                "signature_algorithm": envelope.SIGNATURE_ALGORITHM,
            }
            record["signature"] = envelope.sign_payload(record, self.key)
            (target / "signature.json").write_text(
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8")
            facts = self.verify(target)
            self.state_path.write_text(json.dumps({
                "schema": SCHEMA,
                "revision": revision,
                "published_at": published_at,
                "identity": identity,
                "digest": digest,
                "payload_digest": record["payload_digest"],
                "package": str(target),
                "settings": checked,
                "device": report,
            }, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            return {**facts, "delivery": self._delivery_from(target, record)}

    def verify(self, target: pathlib.Path) -> dict:
        """Recompute the identity and the signature from the bytes on disk."""
        target = pathlib.Path(target)
        manifest_path = target / "manifest.json"
        payload_path = target / "payload.bin"
        identity_path = target / "identity.txt"
        signature_path = target / "signature.json"
        if not all(path.exists() for path in
                   (manifest_path, payload_path, identity_path)):
            raise Refused("settings-package-absent", target.name)
        raw_manifest = manifest_path.read_bytes()
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise Refused("settings-package-absent", str(error)[:200]) from error
        if dialin.canonical_json(dialin._kept(manifest)) != raw_manifest:
            raise Refused("settings-signature", "manifest is not canonical")
        payload = payload_path.read_bytes()
        digest = dialin.package_digest(manifest, payload)
        identity = f"{manifest['name']}@{manifest['revision']}+{digest}"
        if identity_path.read_text(encoding="utf-8").strip() != identity:
            raise Refused("settings-signature", "identity.txt does not recompute")
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise Refused("settings-signature", f"payload is not JSON: {error}") from error
        if body.get("schema") != SCHEMA or body.get("name") != NAME:
            raise Refused("settings-signature", "payload is not a settings document")
        if body.get("revision") != manifest["revision"]:
            raise Refused("settings-signature", "payload revision differs from the manifest")
        if not signature_path.exists():
            raise Refused("settings-package-unsigned", target.name)
        record = json.loads(signature_path.read_text(encoding="utf-8"))
        unsigned = {key: value for key, value in record.items() if key != "signature"}
        if record.get("identity") != identity:
            raise Refused("settings-signature", "the signature names another identity")
        if record.get("payload_digest") != "blake3:" + blake3(payload).hexdigest():
            raise Refused("settings-signature", "the signed payload digest differs")
        if not envelope.verify_payload(unsigned, str(record.get("signature") or ""),
                                       str(record.get("public_key") or "")):
            raise Refused("settings-signature", "the publisher signature does not verify")
        return {
            "schema": SCHEMA,
            "state": "verified",
            "identity": identity,
            "digest": digest,
            "revision": int(manifest["revision"]),
            "payload_digest": record["payload_digest"],
            "signature": record["signature"],
            "public_key": record["public_key"],
            "published_at": record.get("published_at", ""),
            "package": str(target),
            "settings": self.current(),
            "device": (self._read_state().get("device") or {}),
            "settings_digest": body.get("settings_digest", ""),
            "settings_match": (
                not body.get("settings_digest")
                or body.get("settings_digest") == "blake3:" + blake3(
                    dialin.canonical_json(self.current())).hexdigest()),
        }

    def _latest(self) -> pathlib.Path:
        held = self._read_state()
        package = pathlib.Path(str(held.get("package") or ""))
        if package.is_dir():
            return package
        candidates = sorted(self.packages.glob(f"{NAME}@*"),
                            key=lambda path: int(path.name.rsplit("@", 1)[-1] or 0))
        if not candidates:
            raise Refused("settings-package-absent", str(self.packages))
        return candidates[-1]

    def _delivery_from(self, target: pathlib.Path, record: dict) -> dict:
        payload = (target / "payload.bin").read_bytes()
        body = json.loads(payload.decode("utf-8"))
        return {
            "schema": SCHEMA,
            "state": "delivered",
            "identity": record.get("identity", ""),
            "digest": record.get("digest", ""),
            "payload_digest": record.get("payload_digest", ""),
            "revision": int(record.get("revision") or 0),
            "published_at": record.get("published_at", ""),
            "signature": record.get("signature", ""),
            "signature_algorithm": record.get("signature_algorithm", ""),
            "public_key": record.get("public_key", ""),
            "settings": self.current(),
            "device": (self._read_state().get("device") or {}),
            "settings_digest": body.get("settings_digest", ""),
            "settings_match": (
                not body.get("settings_digest")
                or body.get("settings_digest") == "blake3:" + blake3(
                    dialin.canonical_json(self.current())).hexdigest()),
        }

    def delivery(self) -> dict:
        target = self._latest()
        record_path = target / "signature.json"
        if not record_path.exists():
            raise Refused("settings-package-unsigned", target.name)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.verify(target)
        return self._delivery_from(target, record)

    # -- subscriptions ------------------------------------------------------------------
    def subscribe(self, request: dict) -> dict:
        """Admit a signed subscription from another Popit window and serve it the package."""
        if not isinstance(request, dict):
            raise Refused("settings-request", "a subscription is a JSON object")
        window = _text(request.get("window"), 60)
        nonce = str(request.get("nonce") or "")
        public_key = str(request.get("public_key") or "").strip()
        signature = str(request.get("signature") or "")
        if not window:
            raise Refused("settings-request", "a subscription names its window")
        if not NONCE_RE.fullmatch(nonce):
            raise Refused("settings-request", "nonce must be 32-64 lowercase hex characters")
        if not public_key:
            raise Refused("settings-request", "a subscription carries the window's public key")
        if not signature:
            raise Refused("settings-signature", "a subscription must be signed")
        signed = {
            "schema": SUBSCRIPTION_SCHEMA,
            "window": window,
            "issued_at": str(request.get("issued_at") or ""),
            "nonce": nonce,
            "public_key": public_key,
        }
        try:
            issued = envelope.parse_iso(signed["issued_at"])
        except envelope.Refused as error:
            raise Refused("settings-request", error.detail) from error
        now = envelope.utc_now()
        if abs((now - issued).total_seconds()) > MAX_AGE_SECONDS:
            raise Refused("settings-request", "issued_at is outside the 15 minute window")
        if not envelope.verify_payload(signed, signature, public_key):
            raise Refused("settings-signature", "the subscription signature does not verify")
        if not envelope.trusted(public_key, trust_path=self.trust_path):
            raise Refused("settings-untrusted", envelope.fingerprint(public_key))
        fingerprint = envelope.fingerprint(public_key)
        with self.lock:
            book = self._subscriptions()
            if any(item.get("nonce") == nonce for item in book["nonces"]):
                raise Refused("settings-replay", nonce)
            book["nonces"] = ([item for item in book["nonces"]
                               if item.get("nonce") != nonce] + [
                {"nonce": nonce, "window": window, "fingerprint": fingerprint,
                 "at": iso()}
            ])[-MAX_NONCES:]
            subscribers = [row for row in book["subscribers"]
                           if row.get("fingerprint") != fingerprint]
            previous = next((row for row in book["subscribers"]
                             if row.get("fingerprint") == fingerprint), None)
            subscribers.append({
                "window": window,
                "fingerprint": fingerprint,
                "first_at": (previous or {}).get("first_at", iso()),
                "at": iso(),
                "deliveries": int((previous or {}).get("deliveries") or 0) + 1,
            })
            book["subscribers"] = subscribers
            book["deliveries"] = int(book.get("deliveries") or 0) + 1
            self.subscription_path.write_text(
                json.dumps(book, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8")
        return {
            "schema": SCHEMA,
            "state": "subscribed",
            "window": window,
            "fingerprint": fingerprint,
            "delivery": self.delivery(),
        }

    def _subscriptions(self) -> dict:
        if not self.subscription_path.exists():
            return {"schema": f"{SCHEMA}#subscriptions", "nonces": [],
                    "subscribers": [], "deliveries": 0}
        try:
            value = json.loads(self.subscription_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        value.setdefault("schema", f"{SCHEMA}#subscriptions")
        value.setdefault("nonces", [])
        value.setdefault("subscribers", [])
        value.setdefault("deliveries", 0)
        return value

    def trust(self, public_key: str, name: str) -> dict:
        """Add one window's key to the registry. The owner's act, not the window's."""
        return envelope.trust_key(public_key, name, self.trust_path)

    # -- the surface's reading ----------------------------------------------------------
    def state(self) -> dict:
        held = self._read_state()
        book = self._subscriptions()
        body = {
            "schema": SCHEMA,
            "state": "held" if held.get("identity") else "unpublished",
            "identity": held.get("identity", ""),
            "digest": held.get("digest", ""),
            "revision": int(held.get("revision") or 0),
            "published_at": held.get("published_at", ""),
            "payload_digest": held.get("payload_digest", ""),
            "publisher": self.publisher,
            "publisher_fingerprint": envelope.fingerprint(self.public_key),
            "trust_registry": str(self.trust_path),
            "settings": self.current(),
            "device": device_report(),
            "subscribers": book["subscribers"],
            "deliveries": int(book.get("deliveries") or 0),
            "refusals": list(REFUSALS),
        }
        return body
