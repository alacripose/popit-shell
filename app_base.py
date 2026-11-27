"""The app-package base: an app package is a mutated signed subscription to the settings app.

Owner, verbatim: *"it is not enough to derive from the settings window it must create the app
package base by creating mutated signed subscriptions for any project in the app store to be
able to use simple derivations cannot be allowed otheriwse things like the dialin app still
being a handrolled view happen"*.

So a package is not a page that happens to link the settings window's sheets. It is built from
the settings package's **signed delivery** — its identity, digest and payload digest — and then
a declared list of mutations names every slot the app changes, each with the value the settings
window holds and the value the app takes, and why. That document is canonicalised, digested and
carried inside the app's own payload, so the app's signature covers the base it came from.

Consequences the signer enforces:

* a payload without a mutated subscription is refused `app-not-mutated` — a plain derivation is
  exactly how a hand-rolled view slips in;
* a subscription whose base identity is not the settings package currently published is
  refused `app-base-stale`, so a package cannot keep signing against an old base;
* a mutation record whose digest does not recompute is refused `app-base-digest`.

The base is generic: any project in the app store builds its package by calling
`subscription(settings, name, spec, baseline=...)` with its own slots. Nothing here knows about
dialin, the springboard or the bridge.
"""
from __future__ import annotations

import re

from blake3 import blake3

import dialin
import settings_package

SCHEMA = "popit.app-base/1"
BASE_PACKAGE = "popit-settings"
# The settings slots an app receives through the subscription and does not re-author.
FIELDS = ("theme", "frame", "material", "motion", "motionPreference", "dpi", "colors",
          "layout", "device")
# The second baseline every app is built from: the family's project setup. The settings
# window gives the app its look; this record gives its project the acts a family project
# owes — a ticket before the change, a named refusal, its own failure row, an authority
# ledger row, a CI job and a landing page rendered from its pins, a live driver on every
# republish and copy read by the family prose checker. It is pinned here and carried in
# the signed base, so a package built against an older project setup is refused.
PROJECT_SETUP = {
    "schema": "popit.project-setup/1",
    "ticket": "a ticket states the requirement before the change (tickets/TICKET-NNNN-*.md)",
    "refusal": "a refusal is named by code; an empty field is not a refusal",
    "failure": "the program writes its own failure row; a printed pass is not a row",
    "ledger": "runlogs/<unit>/ledger.jsonl beside logs/authority/<date>-<unit>.jsonl",
    "ci": ".github/workflows/ci.yml runs the secrets gate, the landing page, the gate and the app probes",
    "landing": "tools/landing.py renders docs/index.html from its pins",
    "driver": "a republish names the live CUA driver that carried it",
    "prose": "drawn copy is read by the family checker, imported never copied",
}
# The app's own slots. Each one is a mutation against the settings window's value.
SLOTS = ("kind", "entry", "title", "summary", "pages", "adds", "hosts", "regions",
         "files", "script", "links", "body")
WHY = {
    "kind": "the app is its own kind of surface (window or phone), the base is a window",
    "entry": "the app enters by its own page",
    "title": "the app names itself",
    "summary": "the app says what it adds",
    "pages": "the app has its own pages",
    "adds": "the app lists what it adds to the family",
    "hosts": "the app declares what it hosts",
    "regions": "the app carries the family regions itself",
    "files": "the app signs its own served files",
    "script": "the copy runs the app's script instead of the settings window's",
    "links": "the copy wears the app's stylesheet instead of the settings page's",
    "body": "the copy carries the app's body page instead of the settings rail",
}


class Refused(Exception):
    """A named refusal from the base builder."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def _plain(value: object) -> object:
    return list(value) if isinstance(value, (tuple, list)) else value


# The family's control baseline. The settings window's material and motion choices are the
# buttons every app paints with: they carry the family's pressed and hover states, its padding
# and its motion. They were authored in ui/toast.css and lived only there, which is why each app
# could and did drift. Pinned here, an app subscribes to them like it subscribes to the colours,
# and a package built against a different baseline is refused instead of merely noticed.
CONTROLS = {
    "schema": "popit.controls/1",
    "source": "ui/toast.css .style-option — the settings window's material and motion choices",
    "padding": "3px",
    "paddingTight": "1px 4px",
    "minHeight": "29px",
    "border": "1px solid var(--line)",
    "background": "rgba(0, 0, 0, 0.20)",
    "ink": "var(--text)",
    "gap": "4px",
    "motion": ("color var(--t-fast) var(--ease-out), border-color var(--t-fast) var(--ease-out), "
               "background var(--t-fast) var(--ease-out), transform var(--t-fast) var(--ease-pop)"),
    "hover": {"lift": "translateY(-1px)", "border": "var(--emphasis)",
              "background": "rgba(255, 255, 255, 0.09)"},
    "pressed": {"border": "var(--primary)", "background": "rgba(255, 255, 255, 0.12)",
                "ink": "var(--title)"},
    "focus": {"outline": "1px solid var(--emphasis)", "offset": "2px"},
}
# One list, used both by the served stylesheet and by the audit that reads the app sheets.
CONTROL_SELECTORS = (".popit-button", ".style-option", ".theme-choice", ".settings-row button",
                     ".settings-source button", ".settings-tabs button", ".planet-filter button",
                     ".planet-readout button", ".palette-editor-head button",
                     ".palette-library-row button", ".palette-actions button",
                     ".palette-community button", ".agent-button", ".voice-button")


def write_controls(ui_root) -> str:
    """Write the pinned baseline into the app's signed file set, from the record itself.

    The sheet is a served file an app declares, so it has to exist as bytes a signature covers;
    it is never edited by hand. Its content is `controls_css()`, so the record stays the one
    source and a page cannot subscribe to an older rendering of the buttons.
    """
    target = ui_root / "controls.css"
    body = controls_css()
    if not target.exists() or target.read_text(encoding="utf-8") != body:
        target.write_text(body, encoding="utf-8")
    return str(target)


def controls_digest() -> str:
    """The pin an app package carries: a package built against another baseline is stale."""
    return "blake3:" + blake3(dialin.canonical_json(CONTROLS)).hexdigest()


def project_digest() -> str:
    """The project setup pin: an app built against another setup is refused."""
    return "blake3:" + blake3(dialin.canonical_json(PROJECT_SETUP)).hexdigest()


def controls_css() -> str:
    """The baseline as the stylesheet apps link, generated from the pinned record."""
    hover, pressed, focus = CONTROLS["hover"], CONTROLS["pressed"], CONTROLS["focus"]
    selectors = ",\n".join(CONTROL_SELECTORS)
    focus_selectors = ",\n".join(f"{name}:focus-visible" for name in CONTROL_SELECTORS)
    hover_selectors = ",\n".join(f"{name}:hover" for name in CONTROL_SELECTORS)
    pressed_selectors = ",\n".join(f'{name}[aria-pressed="true"]' for name in CONTROL_SELECTORS)
    return (
        "/* popit-controls/1 — generated from app_base.CONTROLS " + controls_digest() + "\n"
        "   Every app links this and paints its buttons with it. A local padding, motion or\n"
        "   pressed state on a button is divergence; the audit reads the app sheets for it. */\n"
        ":root {\n"
        f'  --control-padding: {CONTROLS["padding"]};\n'
        f'  --control-padding-tight: {CONTROLS["paddingTight"]};\n'
        f'  --control-min-height: {CONTROLS["minHeight"]};\n'
        f'  --control-border: {CONTROLS["border"]};\n'
        f'  --control-background: {CONTROLS["background"]};\n'
        f'  --control-ink: {CONTROLS["ink"]};\n'
        f'  --control-gap: {CONTROLS["gap"]};\n'
        f'  --control-motion: {CONTROLS["motion"]};\n'
        f'  --control-lift: {hover["lift"]};\n'
        f'  --control-hover-border: {hover["border"]};\n'
        f'  --control-hover-background: {hover["background"]};\n'
        f'  --control-pressed-border: {pressed["border"]};\n'
        f'  --control-pressed-background: {pressed["background"]};\n'
        f'  --control-pressed-ink: {pressed["ink"]};\n'
        "}\n"
        f"{selectors} {{\n"
        "  padding: var(--control-padding);\n"
        "  min-height: var(--control-min-height);\n"
        "  border: var(--control-border);\n"
        "  background: var(--control-background);\n"
        "  color: var(--control-ink);\n"
        "  transition: var(--control-motion);\n"
        "  cursor: pointer;\n"
        "}\n"
        f"{hover_selectors} {{\n"
        "  transform: var(--control-lift);\n"
        "  border-color: var(--control-hover-border);\n"
        "  background: var(--control-hover-background);\n"
        "}\n"
        f"{pressed_selectors} {{\n"
        "  border-color: var(--control-pressed-border);\n"
        "  background: var(--control-pressed-background);\n"
        "  color: var(--control-pressed-ink);\n"
        "}\n"
        f"{focus_selectors} {{\n"
        f'  outline: {focus["outline"]};\n'
        f'  outline-offset: {focus["offset"]};\n'
        "}\n"
        "[data-control-size=\"tight\"] { padding: var(--control-padding-tight); }\n"
        "@media (prefers-reduced-motion: reduce) {\n"
        f"{selectors} {{ transition: none; }}\n"
        f"{hover_selectors} {{ transform: none; }}\n"
        "}\n")


def subscription(settings, name: str, spec: dict, baseline: dict) -> dict:
    """The mutated signed subscription this app package is built from.

    `settings` is the settings package (the subscription's source), `spec` is the app's own
    slots and `baseline` is the settings window's slot values, so every mutation can name the
    value it changes instead of claiming a blank origin.
    """
    try:
        delivery = settings.delivery()
    except settings_package.Refused as error:
        raise Refused("app-base-absent", f"{name}: {error.code}") from error
    base = {
        "package": BASE_PACKAGE,
        "identity": delivery["identity"],
        "digest": delivery["digest"],
        "payload_digest": delivery["payload_digest"],
        "publisher": "popit-publisher",
        "fields": list(FIELDS),
        # The control baseline is the base's provision, like its colours: an app receives the
        # buttons it may paint with, and a package built against a different baseline is refused
        # rather than allowed to keep a button of its own.
        "controls": CONTROLS,
        "controls_digest": controls_digest(),
        # The app's project is a family project: the setup it owes travels with the base,
        # so the signature covers the ticket, ledger, CI, landing and prose duties too.
        "project": PROJECT_SETUP,
        "project_digest": project_digest(),
    }
    mutations = []
    for slot in SLOTS:
        if slot not in spec:
            continue
        mutations.append({
            "slot": slot,
            "from": _plain(baseline.get(slot)),
            "to": _plain(spec.get(slot)),
            "why": WHY[slot],
        })
    document = {"schema": SCHEMA, "name": f"app-{name}", "base": base,
                "mutations": mutations}
    document["digest"] = "blake3:" + blake3(dialin.canonical_json(document)).hexdigest()
    return document


SETTINGS_PAGE = "settings.html"
TITLE_RE = r"<h1>SETTINGS</h1>"
BODY_OPEN = '<div class="pages" data-region="body">'
KICKER_RE = r'<span class="kicker">POPIT</span>'

HEAD_RE = re.compile(r"<head>(?P<head>.*?)</head>", re.DOTALL | re.IGNORECASE)
BODY_RE = re.compile(r"<body(?P<attrs>[^>]*)>(?P<body>.*?)</body>", re.DOTALL | re.IGNORECASE)
# Whole head items, never bare opening tags: a script copied as `<script>` without its body
# swallows every link after it, and the page it produces loads no stylesheet and runs nothing.
HEAD_ITEM_RE = re.compile(
    r"<script\b[^>]*>.*?</script>|<script\b[^>]*/>|<link\b[^>]*>|<meta\b[^>]*>|<title>.*?</title>",
    re.DOTALL | re.IGNORECASE)


def render(base_html: str, app_html: str, identity: str = "") -> str:
    """The page a window is delivered: the settings package's document, the app's body slot.

    A window is a mutation of the settings window, not a page that merely links its sheets. The
    base supplies the document, its head and its link and script provision; the app supplies the
    body children it declared, so the desk's markup sits inside the settings package's document
    and its own provenance is written on the body for the audit to read.
    """
    base_head = HEAD_RE.search(base_html)
    base_body = BODY_RE.search(base_html)
    app_body = BODY_RE.search(app_html)
    if not (base_head and base_body and app_body):
        raise Refused("app-base-page", "the settings page or the app page carries no head and body")
    head = base_head.group("head")
    seen = {match.group(0).strip().lower() for match in HEAD_ITEM_RE.finditer(head)}
    app_head = HEAD_RE.search(app_html)
    extra: list[str] = []
    if app_head:
        for match in HEAD_ITEM_RE.finditer(app_head.group("head")):
            item = match.group(0).strip()
            if item.lower().startswith("<title"):
                continue
            if item.lower() in seen:
                continue
            seen.add(item.lower())
            extra.append(item)
    attrs = " ".join(part for part in (base_body.group("attrs"), app_body.group("attrs")) if part.strip())
    provenance = f' data-base-package="{BASE_PACKAGE}" data-base-document="{SETTINGS_PAGE}"'
    if identity:
        provenance += f' data-base-identity="{identity}"'
    additions = ("\n" + "\n".join(extra)) if extra else ""
    return ("<!doctype html>\n<html lang=\"en\">\n<head>" + head.rstrip() + additions
            + "\n</head>\n<body" + attrs + provenance + ">" + app_body.group("body")
            + "</body>\n</html>\n")


def check(document: object, name: str, settings) -> dict:
    """Refuse a payload that is not a current mutated subscription; return it when it is."""
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise Refused("app-not-mutated",
                      f"{name}: no mutated subscription; a simple derivation is not a package")
    base = document.get("base")
    if not isinstance(base, dict) or base.get("package") != BASE_PACKAGE:
        raise Refused("app-not-mutated",
                      f"{name}: the subscription does not name {BASE_PACKAGE} as its base")
    if not document.get("mutations"):
        raise Refused("app-not-mutated", f"{name}: the subscription mutates nothing")
    if base.get("controls_digest") != controls_digest():
        raise Refused("app-controls-stale",
                      f"{name}: the package's control baseline is not the published one")
    if base.get("project_digest") != project_digest():
        raise Refused("app-project-baseline-stale",
                      f"{name}: the package's project setup is not the published one")
    body = {key: value for key, value in document.items() if key != "digest"}
    if document.get("digest") != "blake3:" + blake3(dialin.canonical_json(body)).hexdigest():
        raise Refused("app-base-digest", f"{name}: the mutation record does not recompute")
    try:
        delivery = settings.delivery()
    except settings_package.Refused as error:
        raise Refused("app-base-absent", f"{name}: {error.code}") from error
    if base.get("identity") != delivery["identity"]:
        raise Refused("app-base-stale",
                      f"{name}: subscribes to {base.get('identity')}, the settings package is "
                      f"{delivery['identity']}")
    return document
