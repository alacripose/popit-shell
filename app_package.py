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
import re
import threading

from blake3 import blake3

import app_base
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
# A package may not sign an icon frame it cannot prove opens: every window names the launch URL
# of its mutated base, the window is measured before its tile verifies, and the tile opens that
# URL. A window without a launch is refused `app-tile-without-launch` and gets no signature.
LAUNCH_RULE = "entry page + ?window=<name> for a named window, the entry page for the desk"

# The only signing forms a mutable package may take are the two reference packages':
# dialin and settings are `window`, the springboard is `phone`. There is no hosted-surface
# kind: an app that is neither a window nor the phone home is refused `app-kind-foreign`
# instead of being signed as a third form.
KINDS = ("window", "phone")
# A page of its own shape is not a package: the bridge is a window page (its own bar, tabs and
# body), and a window is the settings window with its body mutated. It is hosted by the shell,
# listed in the store as refused, and never signed — the same way the retired IDE chip was.
FOREIGN: dict[str, str] = {"bridge": "window page"}
# An app adds pages; it never adds window furniture. A payload that names bar controls,
# chrome or a control set is refused `app-bar-control`, so a package cannot inject a button
# into the shell's bar the way the retired IDE chip did.
BAR_CONTROL_KEYS = ("bar_controls", "chrome", "controls")

APPS = {
    "dialin": {
        "kind": "window",
        "entry": "toast.html",
        # The desk is delivered in the settings window the family's panel lives in.
        "window": "popit-settings-package",
        "launch": "/toast.html",
        "title": "DialIn desk",
        "summary": "the agent desk: calls, lanes, the voice document and the window chrome",
        "pages": ["local", "mind", "settings", "call"],
        "adds": ["call desk", "lane selection", "voice document", "probe log",
                 "the bridge surface"],
        "hosts": ["bridge"],
        "regions": REGIONS,
        # The copy of the settings window carries the desk's script and stylesheet.
        # The desk's own script is not loaded by the copy: the copy is the settings window,
        # and the desk body is the rebuild's to author.
        "script": "",
        "links": [],
        "files": ("toast.html", "toast.js", "toast.css", "settings.css", "package.js",
                  "contour-theme.css", "controls.css", "contour.js", "popit-sw.js",
                  "ui-audit.js", "chrome.js"),
    },
    "settings": {
        "kind": "window",
        # The settings window is the panel inside the desk, restored to its own bytes: that page
        # is the subscribed baseline, and settings.html stays served as the package document.
        "entry": "toast.html",
        "launch": "/toast.html?window=settings",
        "title": "Settings package",
        "summary": "the mutable base: appearance, motion, layout, apps and functions",
        "pages": ["appearance", "motion", "layout", "apps", "functions", "device", "package"],
        "adds": ["appearance", "motion", "layout", "apps", "functions", "device", "package"],
        "regions": REGIONS,
        "files": ("toast.html", "toast.js", "toast.css", "settings.html",
                  "settings.js", "settings.css", "package.js", "popit-sw.js",
                  "contour-theme.css", "controls.css", "contour.js", "ui-audit.js",
                  "chrome.js"),
    },
    # Prose is the family's written surface: every project's copy, where it lives and the rule
    # it breaks, as a window built from the settings window's own page. Its body is the one
    # mutation; its frame, motion and palette are the package's.
    "prose": {
        "kind": "window",
        "entry": "toast.html",
        "window": "popit-settings-package",
        "launch": "/toast.html?window=prose",
        "title": "Prose",
        "summary": "every family project's prose, the rule it breaks and its document",
        "pages": ["family"],
        "adds": ["prose inventory", "per-project progress", "external document links"],
        "regions": REGIONS,
        "files": ("toast.html", "toast.js", "toast.css", "settings.css", "package.js",
                  "contour-theme.css", "controls.css", "contour.js", "popit-sw.js",
                  "ui-audit.js", "chrome.js"),
    },
    "springboard": {
        "kind": "phone",
        "entry": "phone.html",
        "title": "SpringBoard",
        "summary": "the home: signed tiles that launch apps by name",
        "pages": ["home", "dialin", "settings"],
        "adds": ["signed tiles", "app launch", "offline shell"],
        "regions": REGIONS,
        "files": ("phone.html", "phone.js", "phone-calls.js", "phone.css", "phone-sw.js",
                  "package.js", "contour-theme.css", "controls.css", "contour.js",
                  "ui-audit.js", "chrome.js"),
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
    # The icon frame is only as honest as the window it opens. A window names its base's launch
    # URL and that URL must open the entry page in this app's own window mode.
    if spec["kind"] == "window":
        launch = str(spec.get("launch") or "")
        mode = str(spec.get("window") or "")
        entry = str(spec.get("entry") or "")
        named = f"window={name}" in launch
        expected = named or (name == "dialin" and launch == f"/{entry}")
        if not launch.startswith(f"/{entry}") or not expected:
            raise Refused("app-tile-without-launch",
                          f"{name}: a window signs its tile only with the launch that opens it "
                          f"({LAUNCH_RULE})")
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
        # The two conventions of a mutable app package are checked on the same bytes that
        # are about to be signed: it subscribes to the settings app, and it declares every
        # file it loads. A new feature or dependency that skips either is refused by name.
        self._check_subscription(name)
        self._check_dependencies(name)
        self._check_derivation(name)
        return facts

    # The settings app package is the floating settings window; every other window is built
    # from it. A window that does not carry the shared sheets it is built from is refused.
    DERIVED_SHEETS = ("contour-theme.css", "package.js", "contour.js")

    def _check_derivation(self, name: str) -> None:
        """A window that is not the settings window must be built from it.

        Owner's rule: the settings app package is the floating window that appears, and a
        window that is not from it is refused. So a `window` package carries the shared
        sheets the settings window publishes and links them from its entry page; only the
        settings package itself is the baseline.
        """
        spec = _spec(name)
        if spec["kind"] != "window" or name == "settings":
            return
        # A window package is the settings window's own page with its body mutated. A window
        # with a page of its own is a re-creation of the window, and a re-creation drifts from
        # the one the owner uses — refused `app-handrolled-window`, naming the baseline entry.
        baseline_entry = str(_spec("settings")["entry"])
        if str(spec["entry"]) != baseline_entry:
            raise Refused("app-handrolled-window",
                          f"{name}: its entry {spec['entry']} is a page of its own; a window "
                          f"is {baseline_entry} with its body mutated")
        files = set(spec["files"])
        missing = [sheet for sheet in self.DERIVED_SHEETS if sheet not in files]
        if missing:
            raise Refused("app-not-derived-from-settings",
                          f"{name}: a window is built from the settings window; missing "
                          f"{', '.join(missing)}")
        page = (self.ui_root / spec["entry"]).read_text(encoding="utf-8")
        scripts = "".join((self.ui_root / file).read_text(encoding="utf-8")
                          for file in spec["files"] if file.endswith(".js"))
        if "/contour-theme.css" not in page or "/package.js" not in (page + scripts):
            raise Refused("app-not-derived-from-settings",
                          f"{name}: its entry does not load the settings window's sheets")
        # The chrome, the motion and how a control looks are the settings window's provision:
        # a window carries its chrome sheet and marks its window with the settings chrome.
        # Delivery is the settings window's delivery: the page declares the window it is
        # delivered in, and it carries the settings chrome. An app that does not name its
        # own delivered window is refused, and so is one that paints its own chrome.
        window = self.window_name(name)
        if f'data-window="{window}"' not in page:
            raise Refused("app-not-delivered-as-window",
                          f"{name}: its page is not delivered as {window} the way the "
                          "settings window is")
        # The chrome, the motion and how a control looks are the baseline window's provision:
        # a window wears every sheet the baseline wears, and paints no motion of its own.
        baseline_page = (self.ui_root / _spec("settings")["entry"]).read_text(encoding="utf-8")
        baseline_sheets = set(re.findall(r'href="(/[^"]+\.css)"', baseline_page))
        sheets = set(re.findall(r'href="(/[^"]+\.css)"', page))
        missing_sheets = sorted(baseline_sheets - sheets)
        if not baseline_sheets or missing_sheets or re.search(r"@keyframes", page):
            raise Refused("app-chrome-handrolled",
                          f"{name}: it does not wear the baseline window's chrome "
                          f"({', '.join(missing_sheets) or 'private keyframes'})")

    # The assets a page loads rather than navigates to. A route, an image or the phone's
    # manifest is not a package dependency; a script or a stylesheet is.
    DEPENDENCY_RE = re.compile(r"['\"](/[A-Za-z0-9_\-./]+\.(?:js|css))['\"]")

    def deprecated(self, name: str) -> str:
        """The reason an app is retired, or an empty string when it is a live app."""
        return str(_spec(name).get("deprecated") or "")

    def window_name(self, name: str) -> str:
        """The window an app is delivered in: the same naming the settings window uses.

        An app declares its window in its spec when it is delivered inside another window —
        the desk is delivered in the settings window the family's panel lives in, and it says
        so instead of claiming a window of its own that does not exist.
        """
        declared = str(_spec(name).get("window") or "")
        return declared or f"popit-{name}-package"

    def _check_subscription(self, name: str) -> None:
        """Every app package subscribes to the settings app; the script attaches by name.

        The owner made this project convention: an app reads the signed settings document
        (`attach("<name>")` from `/package.js`) instead of carrying a private theme copy.
        """
        scripts = [file for file in _spec(name)["files"] if file.endswith(".js")]
        for file in scripts:
            text = (self.ui_root / file).read_text(encoding="utf-8")
            if f'attach("{name}"' in text:
                return
        raise Refused("app-not-subscribed",
                      f'{name}: no signed script attaches to the settings package '
                      f'(attach("{name}"))')

    def _check_dependencies(self, name: str) -> None:
        """A package signs everything it loads; an undeclared dependency is refused.

        The owner's condition for the rebuild: the app must still sign properly when it
        brings in new features and dependencies. A script or stylesheet the page loads but
        the package does not declare would be served, audited and rendered without being
        covered by the identity, so it is refused before signing.
        """
        spec = _spec(name)
        declared = set(spec["files"])
        for file in spec["files"]:
            if not file.endswith((".html", ".js")):
                continue
            text = (self.ui_root / file).read_text(encoding="utf-8")
            for match in self.DEPENDENCY_RE.finditer(text):
                dependency = match.group(1).lstrip("/")
                if dependency not in declared:
                    raise Refused("app-dependency-undeclared",
                                  f"{name}: {file} loads /{dependency}, which its signed "
                                  "files do not declare")

    def payload(self, name: str) -> bytes:
        spec = _spec(name)
        retired = self.deprecated(name)
        if retired:
            raise Refused("app-deprecated", f"{name}: {retired}")
        authored = {key: spec[key] for key in
                    ("kind", "entry", "title", "summary", "pages", "adds", "regions")}
        authored["hosts"] = list(spec.get("hosts") or [])
        # The base is the settings package's signed delivery plus this app's mutations. A
        # package that cannot name that base is not signed: a simple derivation is what lets
        # a hand-rolled view through, so the mutation record is part of the signed payload.
        try:
            base = app_base.subscription(self.settings, name, spec, APPS["settings"])
        except app_base.Refused as error:
            raise Refused(error.code, error.detail) from error
        return dialin.canonical_json({
            "schema": APP_SCHEMA,
            "app": name,
            "authored": authored,
            "derives": DERIVES,
            "base": base,
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

    def launch_proof(self, name: str, files: list) -> dict:
        """What the icon frame would open, read from the bytes the signature covers.

        An icon frame is a signature on a promise: tapping it opens this app's window. The proof
        is the signed entry page, carrying every region of the window contract and the panel the
        launch names, with the signed script implementing that window mode, and each byte read is
        checked against the digest the payload signs. A package that cannot show it is refused
        `app-tile-unproven-launch` rather than signed.
        """
        spec = _spec(name)
        if spec["kind"] != "window":
            # The home is not an icon frame: it is the surface the frames sit on.
            return {"ok": True, "url": "", "kind": spec["kind"], "home": True,
                    "mode": "", "entry": str(spec.get("entry") or ""), "refused": ""}
        launch = str(spec.get("launch") or "")
        entry = str(spec.get("entry") or "")
        mode = launch.split("?window=", 1)[1].split("&", 1)[0] if "?window=" in launch else ""
        signed = {str(row.get("name") or ""): str(row.get("digest") or "")
                  for row in files if isinstance(row, dict)}

        def read(file: str) -> str:
            """The file's text, only when its digest is the one the payload signed."""
            if file not in signed:
                return ""
            try:
                raw = (self.ui_root / file).read_bytes()
            except OSError:
                return ""
            if "blake3:" + blake3(raw).hexdigest() != signed[file]:
                return ""
            return raw.decode("utf-8", "replace")

        html = read(entry) if entry else ""
        if not html:
            return {"ok": False, "url": launch, "mode": mode, "entry": entry,
                    "refused": "app-tile-unproven-launch",
                    "detail": "the entry page is not the byte the payload signs"}
        script = read("toast.js")
        regions = [region for region in REGION_CONTRACT
                   if f'data-region="{region}"' not in html]
        panel = (not mode) or f'id="{mode}"' in html or f'id="{mode}-panel"' in html
        implemented = (not mode) or f'get("window") === "{mode}"' in script
        ok = bool(launch) and bool(html) and not regions and panel and implemented
        return {"ok": ok, "url": launch, "mode": mode, "entry": entry,
                "regions": REGION_CONTRACT, "panel": panel,
                "mode_implemented": implemented,
                "refused": "" if ok else "app-tile-unproven-launch",
                "detail": "" if ok else (
                    f"missing regions {','.join(regions)}" if regions else
                    "the launch names a panel this page does not carry" if not panel else
                    "the signed script has no window mode for this launch")}

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
        spec = _spec(name)
        retired = str(spec.get("deprecated") or "")
        if retired:
            raise Refused("app-deprecated", f"{name}: {retired}")
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
        # An app adds pages, never window furniture. A payload that names bar controls or
        # chrome is refused by name: the bar belongs to the shell, and a package that could
        # add a control there would be a second, unsigned author of the window.
        controls = [key for key in BAR_CONTROL_KEYS if authored.get(key)]
        if controls:
            raise Refused("app-bar-control",
                          f"{name}: adds {', '.join(controls)}; a package adds pages, not controls")
        # The app-package base: a mutated signed subscription to the settings package. No
        # subscription → app-not-mutated; an old base → app-base-stale; a mutation record
        # that does not recompute → app-base-digest. Plain derivation is refused, because it
        # is exactly how a hand-rolled view (the desk's private palette) got signed before.
        try:
            app_base.check(body.get("base"), name, self.settings)
        except app_base.Refused as error:
            raise Refused(error.code, error.detail) from error
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
            # The measurement the window produced: size, timestamp and findings, so a reader
            # sees the numbers and not only the word "passed".
            "ui_audit_report": self.ui_audit(name) or {},
            "launch_proof": self.launch_proof(
                name, json.loads(published.decode("utf-8")).get("files", [])),
            "app_standard": record.get("app_standard", APP_SCHEMA),
            "driver": record.get("driver", ""),
            "authored": body.get("authored") or {},
            "derives": body.get("derives") or {},
            "launch": str(_spec(name).get("launch") or ""),
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
        spec = _spec(name)
        retired = str(spec.get("deprecated") or "")
        if retired:
            raise Refused("app-deprecated", f"{name}: {retired}")
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
            "ui_audit_report": facts.get("ui_audit_report") or {},
            "launch": facts.get("launch", ""),
            "launch_proof": facts.get("launch_proof") or {},
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
                            "launch": facts.get("launch", ""),
                            "launch_proof": facts.get("launch_proof") or {},
                            "driver": facts.get("driver", "")})
            except Refused as error:
                row["refused"] = error.as_dict()
            rows[name] = row
        # A foreign surface is reported, not hidden: a name that is not a signable kind is
        # listed with the refusal that says why, rather than silently dropped.
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
