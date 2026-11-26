"""Probe: every app package is signed, and a package that moved is refused by name.

This is the kept probe for the app-package registry. It copies one app's served files into
a temporary directory, publishes it with a temporary settings publisher, and then asks the
registry the three questions a window asks: is the identity signed, is a tampered file
refused, and is a package from a registry that does not hold the key refused.

    python tools/app_package_probe.py

Exit 0 when every row passes; the receipt is runlogs/toast/app-package-probe.json.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from blake3 import blake3

import app_base  # noqa: E402
import app_package  # noqa: E402
import dialin  # noqa: E402
import envelope  # noqa: E402
import settings_package  # noqa: E402

APP = "dialin"
ROWS: list[dict] = []


class Fleet:
    """The fleet a real publisher holds: two live drivers, no tasks yet."""

    def state(self) -> dict:
        return {"drivers": [{"id": "cua-1"}, {"id": "cua-2"}], "tasks": []}


def check(name: str, passed: bool, detail: str) -> None:
    ROWS.append({"name": name, "passed": bool(passed), "detail": detail})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="popit-app-probe-") as temp:
        root = pathlib.Path(temp)
        ui = root / "ui"
        ui.mkdir()
        for name in app_package.FILES[APP]:
            shutil.copy2(ROOT / "ui" / name, ui / name)
        # The base renders every window from the settings window's own page.
        shutil.copy2(ROOT / "ui" / "settings.html", ui / "settings.html")
        trust = root / "envelope-trust.json"
        settings = settings_package.SettingsPackage(root / "settings", trust_path=trust)
        settings.publish()
        apps = app_package.AppPackages(root / "apps", ui, settings=settings,
                                       drivers=Fleet())

        entry_name = app_package.APPS[APP]["entry"]

        clean = {"size": {"width": 390, "height": 844}, "findings": []}
        document = apps.publish(APP)  # nothing has measured this surface yet
        check("app-ui-audit-pending-recorded", document.get("ui_audit") == "pending",
              str(document.get("ui_audit")))
        apps.record_ui_audit(APP, {"size": clean["size"],
                                   "findings": [{"code": "ui-overlap",
                                                 "detail": "probe: two controls on one box"}]})
        try:
            # A republish names its driver first; the audit refusal is what this case measures.
            apps.publish(APP, driver="cua-1")
            check("app-ui-audit-refuses-findings", False,
                  "a surface with overlapping controls was signed")
        except app_package.Refused as error:
            check("app-ui-audit-refuses-findings", error.code == "app-ui-audit", error.code)
        apps.record_ui_audit(APP, clean)
        # A mutation before the fleet names a driver is refused: the store has to know who
        # developed a new revision, and "nobody" is not an author.
        try:
            apps.publish(APP)
            no_driver = None
        except app_package.Refused as error:
            no_driver = error.code
        check("app-no-driver-refused", no_driver == "app-no-driver", str(no_driver))
        check("app-ui-audit-passed-recorded",
              apps.publish(APP, driver="cua-1").get("ui_audit") == "passed",
              "clean measurement recorded")
        identity = document.get("identity", "")
        check("app-package-signed", document.get("verified") is True
              and identity.startswith(f"app-{APP}@1+")
              and "+blake3:" in identity
              and len(document.get("files") or []) == len(app_package.FILES[APP]),
              identity or "no identity")
        check("app-package-publisher-trusted",
              envelope.trusted(document.get("public_key", ""), trust_path=trust),
              envelope.fingerprint(document.get("public_key", "")))
        body = json.loads(apps.payload(APP))
        authored = body.get("authored") or {}
        check("app-authored-manifest",
              body.get("schema") == app_package.APP_SCHEMA
              and authored.get("kind") == app_package.APPS[APP]["kind"]
              and bool(authored.get("entry")) and bool(authored.get("pages"))
              and bool(authored.get("adds"))
              and "theme" in (body.get("derives") or {}).get("fields", [])
              and "layout" in (body.get("derives") or {}).get("fields", []),
              f"{body.get('schema')} · {len(authored.get('pages') or [])} pages")
        # A payload that only lists files is the pre-standard package: it is refused by
        # name before any tamper comparison, not published under a new signature.
        held = apps._held(APP)
        legacy = dialin.canonical_json({
            "schema": "popit.app-package/1", "app": APP,
            "files": [{"name": name, "bytes": 1, "digest": "blake3:" + "0" * 64}
                      for name in app_package.FILES[APP]],
        })
        (pathlib.Path(held["package"]) / "payload.bin").write_bytes(legacy)
        try:
            apps.verify(APP)
            legacy_code = None
        except app_package.Refused as error:
            legacy_code = error.code
        check("app-legacy-refused", legacy_code == "app-legacy", str(legacy_code))
        # The legacy bytes were planted to prove the refusal; restore the authored payload
        # so the tamper check below still measures a tampered file, not a legacy document.
        (pathlib.Path(held["package"]) / "payload.bin").write_bytes(apps.payload(APP))
        # A window package without its family regions is refused, not signed: the entry
        # page must actually carry the bar, status, body and foot it declares.
        entry = ui / app_package.APPS[APP]["entry"]
        original_entry = entry.read_text(encoding="utf-8")
        entry.write_text(original_entry.replace('data-region="body"', 'data-region="body-gone"'),
                         encoding="utf-8")
        try:
            apps.verify(APP)
            incomplete = None
        except app_package.Refused as error:
            incomplete = error.code
        finally:
            entry.write_text(original_entry, encoding="utf-8")
        check("app-window-incomplete-refused", incomplete == "app-window-incomplete",
              str(incomplete))
        check("app-package-carries-settings-theme",
              (document.get("theme") or {}).get("frame") == settings.current()["frame"]
              and bool(document.get("theme_identity")),
              str(document.get("theme_identity")))

        target = ui / "toast.css"
        target.write_bytes(target.read_bytes() + b"\n/* probe: a byte the package never signed */\n")
        try:
            apps.verify(APP)
            check("app-package-tamper-refused", False, "the changed file verified")
        except app_package.Refused as error:
            check("app-package-tamper-refused", error.code == "app-tampered", error.code)

        empty = root / "empty-trust.json"
        empty.write_text(json.dumps({"schema": envelope.TRUST_SCHEMA, "keys": []}) + "\n",
                         encoding="utf-8")
        apps.record_ui_audit(APP, clean)  # the changed bytes need their own measurement
        apps.publish(APP, driver="cua-2")  # republish so the files match again
        held = apps.trust_path
        apps.trust_path = empty
        try:
            apps.verify(APP)
            check("app-package-untrusted-refused", False, "a key outside the registry verified")
        except app_package.Refused as error:
            check("app-package-untrusted-refused", error.code == "app-untrusted", error.code)
        finally:
            apps.trust_path = held

        # An app adds pages, never window furniture. A payload that names bar controls is
        # refused before it can be signed, so a package cannot put a control in the shell's
        # bar the way the retired IDE chip sat in the desk.
        held = apps._held(APP)
        target_payload = pathlib.Path(held["package"]) / "payload.bin"
        signed = target_payload.read_bytes()
        planted = json.loads(signed.decode("utf-8"))
        planted["authored"]["bar_controls"] = ["ide-chip"]
        target_payload.write_bytes(dialin.canonical_json(planted))
        try:
            apps.verify(APP)
            bar_control = None
        except app_package.Refused as error:
            bar_control = error.code
        check("app-bar-control-refused", bar_control == "app-bar-control", str(bar_control))
        target_payload.write_bytes(signed)

        # An app delivers its window the way the settings window does: its page names the
        # window it is delivered in, and a page that does not name one is refused by name.
        kept_entry = (ui / entry_name).read_bytes()
        (ui / entry_name).write_text(
            kept_entry.decode("utf-8").replace(
                f'data-window="{apps.window_name(APP)}"', ''), encoding="utf-8")
        try:
            apps.payload(APP)
            delivered = None
        except app_package.Refused as error:
            delivered = error.code
        (ui / entry_name).write_bytes(kept_entry)
        check("app-not-delivered-as-window-refused",
              delivered == "app-not-delivered-as-window", str(delivered))

        # The two conventions of a mutable package: it subscribes to the settings app, and it
        # signs every asset it loads. A dependency outside the declared set is refused by
        # name, and so is a script that never attaches to the settings document — the two
        # ways a new feature could otherwise be served without being covered by the identity.
        real_ui = apps.ui_root
        scratch = root / "scratch-ui"
        shutil.copytree(real_ui, scratch)
        apps.ui_root = scratch
        try:
            (scratch / "toast.js").write_text(
                'import { attach } from "/package.js";\n'
                'import "/probe-undeclared-dependency.js";\nattach("dialin");\n',
                encoding="utf-8")
            try:
                apps.payload(APP)
                dependency = None
            except app_package.Refused as error:
                dependency = error.code
            check("app-dependency-undeclared-refused",
                  dependency == "app-dependency-undeclared", str(dependency))
            (scratch / "toast.js").write_text("// a desk that paints its own copy\n",
                                              encoding="utf-8")
            try:
                apps.payload(APP)
                subscribed = None
            except app_package.Refused as error:
                subscribed = error.code
            check("app-not-subscribed-refused", subscribed == "app-not-subscribed",
                  str(subscribed))
        finally:
            apps.ui_root = real_ui
            shutil.rmtree(scratch, ignore_errors=True)

        # The base is a mutated signed subscription, not a derivation: a payload without one
        # is refused, and so is a package still subscribed to an older settings package.
        held = apps._held(APP)
        target_payload = pathlib.Path(held["package"]) / "payload.bin"
        signed = target_payload.read_bytes()
        without = json.loads(signed.decode("utf-8"))
        without.pop("base", None)
        target_payload.write_bytes(dialin.canonical_json(without))
        try:
            apps.verify(APP)
            mutated = None
        except app_package.Refused as error:
            mutated = error.code
        check("app-not-mutated-refused", mutated == "app-not-mutated", str(mutated))
        class OldBase:
            """A settings package that is no longer the published one."""

            def delivery(self) -> dict:
                return {"identity": "popit-settings@1+blake3:" + "0" * 64,
                        "digest": "blake3:" + "0" * 64,
                        "payload_digest": "blake3:" + "0" * 64}

        stale = json.loads(signed.decode("utf-8"))
        stale["base"] = app_base.subscription(OldBase(), APP, app_package.APPS[APP],
                                              app_package.APPS["settings"])
        target_payload.write_bytes(dialin.canonical_json(stale))
        try:
            apps.verify(APP)
            stale_code = None
        except app_package.Refused as error:
            stale_code = error.code
        check("app-base-stale-refused", stale_code == "app-base-stale", str(stale_code))
        target_payload.write_bytes(signed)

        # The settings app package is the floating settings window; every other window is
        # built from it. A window whose entry stops loading the settings window's sheets is
        # refused by name.
        derivation_ui = root / "derivation-ui"
        shutil.copytree(real_ui, derivation_ui)
        apps.ui_root = derivation_ui
        entry = derivation_ui / app_package.APPS[APP]["entry"]
        kept_page = entry.read_text(encoding="utf-8")
        try:
            entry.write_text(kept_page.replace('/contour-theme.css', ''), encoding="utf-8")
            try:
                apps.payload(APP)
                derived = None
            except app_package.Refused as error:
                derived = error.code
            check("app-not-derived-from-settings-refused",
                  derived == "app-not-derived-from-settings", str(derived))
            # The chrome, the motion and the control look are the settings window's to
            # provide; a copy rendered without that provision is refused.
            settings_page = derivation_ui / "settings.html"
            kept_settings = settings_page.read_text(encoding="utf-8")
            try:
                settings_page.write_text(
                    kept_settings.replace('data-chrome="popit-settings"', ''),
                    encoding="utf-8")
                try:
                    apps.payload(APP)
                    chrome = None
                except app_package.Refused as error:
                    chrome = error.code
            finally:
                settings_page.write_text(kept_settings, encoding="utf-8")
            # A copy rendered without the settings window's chrome marker is refused; either
            # named check may catch it, and both mean the chrome was not the base's.
            check("app-chrome-handrolled-refused",
                  chrome in ("app-chrome-handrolled", "app-not-derived-from-settings"),
                  str(chrome))
        finally:
            entry.write_text(kept_page, encoding="utf-8")
            apps.ui_root = real_ui
            shutil.rmtree(derivation_ui, ignore_errors=True)

        try:
            apps.document("not-an-app")
            check("app-package-unknown-refused", False, "an unknown app was served")
        except app_package.Refused as error:
            check("app-package-unknown-refused", error.code == "app-unknown", error.code)

    for row in ROWS:
        print(f"{'PASS' if row['passed'] else 'FAIL'} {row['name']} · {row['detail']}")
    receipt = ROOT / "runlogs" / "toast" / "app-package-probe.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"schema": "popit.app-package-probe/1",
                                   "rows": ROWS}, indent=2) + "\n", encoding="utf-8")
    failed = [row["name"] for row in ROWS if not row["passed"]]
    print(f"{len(ROWS) - len(failed)} passed, {len(failed)} failed -> {receipt}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
