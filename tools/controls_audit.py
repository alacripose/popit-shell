"""The control baseline's ratchet.

The settings window's material and motion choices are the family's buttons: `app_base.CONTROLS`
pins their padding, height, border, motion and pressed and hover states, and `/controls.css`
serves them. An app that sets any of those on a button of its own is divergence, and this reads
the app sheets and pages by name rather than trusting that nobody did.

    python tools/controls_audit.py            # text rows, exit 1 on findings
    python tools/controls_audit.py --json     # the same rows as JSON

Nothing here repairs a sheet: a finding is the work list, and the fix is the sheet's own edit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
sys.path.insert(0, str(ROOT))

import app_base  # noqa: E402

# The three axes the owner named — padding, motion, function — plus the box that padding sets.
# A button's own colour or a variant's plate is not divergence in those axes, so it is not read
# here; a local padding, a local transition or a local press is, because the baseline is what
# every app subscribes to.
PINNED = ("padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
          "min-height", "transition", "animation", "transform")
RULE_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.DOTALL)
DECL_RE = re.compile(r"(?P<prop>[-a-zA-Z]+)\s*:\s*(?P<value>[^;]+);?")
CONTROL_WORDS = ("button", "btn", "style-option", "theme-choice", "popit-button")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def control_selector(selectors: str) -> bool:
    """True when this rule paints a control: a button element or one of the baseline's classes."""
    for part in selectors.split(","):
        head = part.strip().lstrip(".").split()[0] if part.strip() else ""
        head = head.split(":")[0].split("[")[0]
        if any(word in head for word in CONTROL_WORDS):
            return True
    return False


def audit_sheet(path: Path) -> list[dict]:
    if path.name == "controls.css":
        # The baseline is the rule, not a sheet under it: its generated `transition: none`
        # under reduced motion is the baseline's own statement.
        return []
    text = path.read_text(encoding="utf-8")
    findings = []
    for match in RULE_RE.finditer(text):
        selectors = match.group("selectors").strip()
        if not control_selector(selectors):
            continue
        body_start = match.start("body")
        for decl in DECL_RE.finditer(match.group("body")):
            prop = decl.group("prop").lower()
            value = decl.group("value").strip()
            if prop not in PINNED:
                continue
            if value.startswith("var(--control-"):
                continue
            if prop in ("background", "background-color") and value in ("none", "transparent"):
                continue
            findings.append({
                "code": "button-drift",
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "line": line_of(text, body_start + decl.start("prop")),
                "selector": selectors.split(",")[0].strip(),
                "prop": prop,
                "value": value,
            })
    return findings


def audit_pages() -> list[dict]:
    findings = []
    for path in sorted(UI.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        if "<button" not in text:
            continue
        if 'href="/controls.css"' not in text:
            findings.append({
                "code": "button-baseline-unlinked",
                "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "line": 1,
                "selector": "link",
                "prop": "controls.css",
                "value": "not linked",
            })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the app sheets for button divergence.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = []
    for path in sorted(UI.glob("*.css")):
        findings.extend(audit_sheet(path))
    findings.extend(audit_pages())
    report = {
        "schema": "popit.controls-audit/1",
        "baseline": app_base.controls_digest(),
        "sheets": len(list(UI.glob("*.css"))),
        "pages": len(list(UI.glob("*.html"))),
        "findings": findings,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"baseline {report['baseline']} over {report['sheets']} sheets, "
              f"{report['pages']} pages")
        for row in findings:
            print(f"{row['code']} {row['file']}:{row['line']} {row['selector']} "
                  f"{row['prop']}={row['value']}")
        print(f"{len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
