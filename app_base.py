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
