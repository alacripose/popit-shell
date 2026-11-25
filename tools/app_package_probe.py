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

import app_package  # noqa: E402
import envelope  # noqa: E402
import settings_package  # noqa: E402

APP = "dialin"
ROWS: list[dict] = []


def check(name: str, passed: bool, detail: str) -> None:
    ROWS.append({"name": name, "passed": bool(passed), "detail": detail})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="popit-app-probe-") as temp:
        root = pathlib.Path(temp)
        ui = root / "ui"
        ui.mkdir()
        for name in app_package.APPS[APP]:
            shutil.copy2(ROOT / "ui" / name, ui / name)
        trust = root / "envelope-trust.json"
        settings = settings_package.SettingsPackage(root / "settings", trust_path=trust)
        settings.publish()
        apps = app_package.AppPackages(root / "apps", ui, settings=settings)

        clean = {"size": {"width": 390, "height": 844}, "findings": []}
        document = apps.publish(APP)  # nothing has measured this surface yet
        check("app-ui-audit-pending-recorded", document.get("ui_audit") == "pending",
              str(document.get("ui_audit")))
        apps.record_ui_audit(APP, {"size": clean["size"],
                                   "findings": [{"code": "ui-overlap",
                                                 "detail": "probe: two controls on one box"}]})
        try:
            apps.publish(APP)
            check("app-ui-audit-refuses-findings", False,
                  "a surface with overlapping controls was signed")
        except app_package.Refused as error:
            check("app-ui-audit-refuses-findings", error.code == "app-ui-audit", error.code)
        apps.record_ui_audit(APP, clean)
        check("app-ui-audit-passed-recorded",
              apps.publish(APP).get("ui_audit") == "passed", "clean measurement recorded")
        identity = document.get("identity", "")
        check("app-package-signed", document.get("verified") is True
              and identity.startswith(f"app-{APP}@1+")
              and "+blake3:" in identity
              and len(document.get("files") or []) == len(app_package.APPS[APP]),
              identity or "no identity")
        check("app-package-publisher-trusted",
              envelope.trusted(document.get("public_key", ""), trust_path=trust),
              envelope.fingerprint(document.get("public_key", "")))
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
        apps.publish(APP)  # republish so the files match again
        held = apps.trust_path
        apps.trust_path = empty
        try:
            apps.verify(APP)
            check("app-package-untrusted-refused", False, "a key outside the registry verified")
        except app_package.Refused as error:
            check("app-package-untrusted-refused", error.code == "app-untrusted", error.code)
        finally:
            apps.trust_path = held

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
