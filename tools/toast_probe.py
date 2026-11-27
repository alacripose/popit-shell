#!/usr/bin/env python3
"""Prove the toast's pip: capture, delegated CUA tasks, per-driver voices, mic, contour.

Run from the repo root: `python tools/toast_probe.py`.
Writes `runlogs/toast/receipt.json`; exits non-zero on any refusal.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import secrets
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cua  # noqa: E402
import dialin  # noqa: E402
import envelope  # noqa: E402
import external_agents  # noqa: E402
import settings_package  # noqa: E402
import toast as toast_app  # noqa: E402
import voice as voice_app  # noqa: E402


def get(port: int, path: str) -> tuple[int, bytes, str]:
    # A refusal is a row the probe must read, not an exception that stops the run.
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as reply:
            return reply.status, reply.read(), reply.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type", "")


def post(port: int, path: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return reply.status, json.loads(reply.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def until(predicate, seconds: float = 12.0, pause: float = 0.1):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(pause)
    return None


def main() -> int:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + ((" — " + detail) if detail else ""))

    external_temp = tempfile.mkdtemp(prefix="popit-external-probe-")
    app = toast_app.Toast(probe_seconds=3600, play_voice=False)
    app.external = external_agents.ExternalAgents(pathlib.Path(external_temp))
    server = toast_app.serve(app, 0)
    port = server.server_port
    try:
        status, body, kind = get(port, "/api/toast")
        state = json.loads(body)
        check("state-schema", status == 200 and state.get("schema") == toast_app.SCHEMA,
              state.get("schema", ""))
        check("ui-served", get(port, "/toast.html")[0] == 200, "/toast.html")
        check("contour-served", get(port, "/contour.json")[0] == 200, "/contour.json")
        status, published = post(port, "/api/toast/settings/publish", {})
        check("settings-package-publish", status == 200
              and str(published.get("identity", "")).startswith("popit-settings@")
              and "+blake3:" in str(published.get("identity", "")),
              str(published.get("identity", "")))
        status, settings_body, _ = get(port, "/api/toast/settings")
        settings_state = json.loads(settings_body)
        check("settings-package-state", status == 200
              and settings_state.get("identity") == published.get("identity")
              and settings_state.get("publisher_fingerprint", "").startswith("blake3:"),
              settings_state.get("identity", ""))
        status, window_html, _ = get(port, "/settings.html")
        window_text = window_html.decode("utf-8")
        check("settings-window-served", status == 200
              and 'data-popit="settings-package"' in window_text
              and 'id="package-identity"' in window_text
              and 'id="device-rows"' in window_text,
              "/settings.html")
        status, document, _ = get(port, "/api/toast/settings/package")
        held = json.loads(document)
        digest = dialin.package_digest(held.get("manifest") or {},
                                       str(held.get("payload", "")).encode("utf-8"))
        check("settings-package-binds-bytes", status == 200
              and f"{held['manifest']['name']}@{held['manifest']['revision']}+{digest}"
              == held.get("identity"), held.get("identity", ""))
        trust_probe = pathlib.Path(external_temp) / "settings-trust.json"
        app.settings.trust_path = trust_probe
        window_dir = pathlib.Path(external_temp) / "settings-window"
        envelope.keygen(window_dir / "window.key", window_dir / "window.pem")
        window_key = (window_dir / "window.pem").read_text(encoding="utf-8").strip()
        envelope.trust_key(window_key, "Probe settings window", trust_probe)
        issued_at = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        subscription = {
            "schema": settings_package.SUBSCRIPTION_SCHEMA,
            "window": "Probe settings window", "issued_at": issued_at,
            "nonce": secrets.token_hex(16), "public_key": window_key,
        }
        subscription["signature"] = envelope.sign_payload(subscription, window_dir / "window.key")
        status, delivered = post(port, "/api/toast/settings/subscribe", subscription)
        delivery = delivered.get("delivery") or {}
        check("settings-subscription-delivered", status == 200
              and delivery.get("identity") == held.get("identity")
              and delivery.get("payload_digest") == held.get("payload_digest")
              and delivery.get("settings") == settings_state.get("settings"),
              str(delivery.get("identity", "")))
        status, replayed = post(port, "/api/toast/settings/subscribe", subscription)
        check("settings-subscription-replay-refused", status == 409
              and (replayed.get("refused") or {}).get("code") == "settings-replay",
              str((replayed.get("refused") or {}).get("code", "")))
        unsigned = {key: value for key, value in subscription.items() if key != "signature"}
        unsigned["nonce"] = secrets.token_hex(16)
        status, refused = post(port, "/api/toast/settings/subscribe", unsigned)
        check("settings-subscription-unsigned-refused", status == 409
              and (refused.get("refused") or {}).get("code") == "settings-signature",
              str((refused.get("refused") or {}).get("code", "")))
        status, roster_body, _ = get(port, "/family-roster.json")
        roster = json.loads(roster_body)
        check("family-roster-served", status == 200 and len(roster.get("themes", [])) == 17,
              f"{len(roster.get('themes', []))} family schemes")
        status, pairs_body, _ = get(port, "/popit-pairs.json")
        pairs = json.loads(pairs_body)
        check("player-pairs-served", status == 200 and len(pairs.get("pairs", [])) == 37,
              f"{len(pairs.get('pairs', []))} player colours")
        status, phone_html, _ = get(port, "/phone.html")
        phone_text = phone_html.decode("utf-8")
        check("external-phone-surface", status == 200
              and all(marker in phone_text for marker in
                      ('id="agents-screen"', 'id="call-sheet"', 'id="call-audio"')),
              "agents screen and incoming call sheet")
        status, phone_js, _ = get(port, "/phone-calls.js")
        check("external-phone-module", status == 200
              and b"PopitAgents" in phone_js and b"/api/toast/external/incoming" in phone_js,
              "phone-calls.js served")
        status, cert_body, cert_kind = get(port, "/popit-cert.cer")
        check("phone-cert-installable", status == 200
              and cert_kind == "application/x-x509-ca-cert"
              and cert_body.startswith(b"0") and b"BEGIN CERTIFICATE" not in cert_body,
              "DER certificate served as an installable CA download")
        status, agent_html, _ = get(port, "/agent-line.html")
        agent_text = agent_html.decode("utf-8")
        check("external-agent-surface", status == 200
              and all(marker in agent_text for marker in
                      ('id="agent-enroll"', 'id="agent-call"', 'id="agent-audio"')),
              "external agent enrollment and call surface")
        status, agent_js, _ = get(port, "/agent-line.js")
        check("external-agent-webrtc", status == 200
              and b"Ed25519" in agent_js and b"RTCPeerConnection" in agent_js
              and b"/api/toast/external/call" in agent_js,
              "agent-line.js signs and opens WebRTC")
        status, contacts_body, _ = get(port, "/api/toast/external/contacts")
        contacts_empty = json.loads(contacts_body)
        check("external-contact-book-empty", status == 200
              and contacts_empty.get("contacts") == [], "empty verified book")
        status, invitation = post(port, "/api/toast/external/enrollment",
                                  {"name": "Probe external agent"})
        check("external-invite-issued", status == 200 and bool(invitation.get("code"))
              and bool(invitation.get("expires_at")), "one-time code")
        keys = pathlib.Path(external_temp) / "probe-keys"
        made = envelope.keygen(keys / "agent.key", keys / "agent.pem")
        public_key = (keys / "agent.pem").read_text(encoding="utf-8").strip()
        issued_at = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")
        registration = {
            "schema": external_agents.REGISTRATION_SCHEMA,
            "name": "Probe external agent", "endpoint": "https://agent.example/mcp",
            "public_key": public_key, "issued_at": issued_at, "code": invitation["code"],
        }
        registration["signature"] = envelope.sign_payload(registration, keys / "agent.key")
        status, enrolled = post(port, "/api/toast/external/enroll", registration)
        contact = enrolled.get("contact") or {}
        check("external-enrollment-verified", status == 200
              and contact.get("status") == "verified" and contact.get("line", "").startswith("POPIT-")
              and bool(contact.get("workspace")),
              f"{contact.get('name')} {contact.get('line')} {json.dumps(enrolled)[:300]}")
        check("external-workspace-created", bool(enrolled.get("workspace"))
              and (pathlib.Path(enrolled.get("workspace", "")) / "README.md").exists(),
              str(enrolled.get("workspace", "")))
        status, book, _ = get(port, "/api/toast/external/contacts")
        book_rows = json.loads(book).get("contacts") or []
        check("external-contact-registered", status == 200 and len(book_rows) == 1
              and book_rows[0].get("name") == "Probe external agent",
              json.dumps(book_rows[0].get("line") if book_rows else ""))
        offer = ("v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=popit-probe\r\nt=0 0\r\n"
                 "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n")
        nonce = secrets.token_hex(16)
        ticket = {"schema": external_agents.CALL_SCHEMA, "agent": contact["id"],
                  "nonce": nonce, "issued_at": issued_at, "offer": offer}
        ticket["signature"] = envelope.sign_payload(ticket, keys / "agent.key")
        status, opened = post(port, "/api/toast/external/call", ticket)
        check("external-call-rings", status == 200 and opened.get("state") == "ringing"
              and bool(opened.get("call_id")), opened.get("call_id", ""))
        status, incoming, _ = get(port, "/api/toast/external/incoming")
        ringing = json.loads(incoming).get("calls") or []
        check("external-incoming-surface", status == 200 and len(ringing) == 1
              and ringing[0].get("name") == "Probe external agent" and ringing[0].get("offer"),
              ringing[0].get("line", "") if ringing else "")
        answer = ("v=0\r\no=- 2 2 IN IP4 127.0.0.1\r\ns=popit-probe-answer\r\nt=0 0\r\n"
                  "m=audio 9 UDP/TLS/RTP/SAVPF 111\r\n")
        status, answered = post(port, "/api/toast/external/call/answer",
                                {"call_id": opened["call_id"], "answer": answer})
        check("external-call-answered", status == 200 and answered.get("state") == "active",
              answered.get("call_id", ""))
        status, call_state = post(port, "/api/toast/external/call/state",
                                  {"call_id": opened["call_id"]})
        check("external-call-signal-readable", status == 200
              and call_state.get("answer") == answer.strip() and call_state.get("state") == "active",
              call_state.get("state", ""))
        status, ended = post(port, "/api/toast/external/call/end",
                             {"call_id": opened["call_id"], "outcome": "ended"})
        check("external-call-ended", status == 200 and ended.get("state") == "ended",
              ended.get("state", ""))
        profiles = state.get("voice", {}).get("profiles", [])
        profile_ids = {row.get("id") for row in profiles}
        check("voice-profiles", len(profiles) >= 11
              and {"assistant", "cua-chat", "civilian"} <= profile_ids,
              str(len(profiles)))
        check("mic-declared", state.get("mic", {}).get("device") == "default capture device",
              str(state.get("mic", {}).get("device")))

        state = json.loads(get(port, "/api/toast")[1])
        check("composer-unread-until-an-agent-asks",
              (state.get("harness") or {}).get("state") == "unread",
              str((state.get("harness") or {}).get("code")))
        try:
            app.ask_mind("the desk answers with no composer read behind it", "cua-chat")
            gate_code = "answered"
        except Exception as error:  # a lane's own refusal is not the freshness gate
            gate_code = str(getattr(error, "code", type(error).__name__))
        check("answering-needs-no-freshness-gate", gate_code != "harness-unprobed", gate_code)

        probe = app.run_probe()
        check("freebuff-captured", probe.get("state") == "live",
              f"{probe.get('state')} {probe.get('code', '')}")
        state = json.loads(get(port, "/api/toast")[1])
        harness = state.get("harness") or {}
        regions = harness.get("regions") or {}
        check("bare-capture-is-not-a-read", harness.get("state") == "captured",
              f"{harness.get('state')} {harness.get('code', '')}")
        check("harness-regions-probed", all((regions.get(name) or {}).get("digest")
              for name in ("history", "working", "textbox")),
              " ".join(f"{name}={(regions.get(name) or {}).get('height')}" for name in ("history", "working", "textbox")))
        # The agent's own read: the tool an active mission calls, never a timer.
        receipt = app.read_composer("toast-probe", "the desk's own contract probe")
        check("composer-read-on-request",
              receipt.get("source") in ("uia", "image")
              and receipt.get("submitted") is False and receipt.get("focus_stolen") is False
              and not receipt.get("keys_sent"),
              f"{receipt.get('source')} {receipt.get('chars')} chars")
        harness = (json.loads(get(port, "/api/toast")[1]).get("harness") or {})
        check("desk-names-the-reader", harness.get("state") == "read"
              and harness.get("by") == "toast-probe",
              f"{harness.get('state')} {harness.get('by')}")
        status, image, kind = get(port, "/api/toast/harness.png")
        check("harness-textbox-http", status == 200 and kind == "image/png" and len(image) > 1_000,
              f"{len(image)} bytes")
        check("capture-named", bool(probe.get("digest")) and (probe.get("width") or 0) > 0,
              f"{probe.get('width')}x{probe.get('height')} {probe.get('digest')}")
        status, image, kind = get(port, "/api/toast/capture.png")
        check("capture-http", status == 200 and kind == "image/png" and len(image) > 10_000,
              f"{len(image)} bytes")

        point = cua.wt.POINT()
        cua.user32.GetCursorPos(cua.ctypes.byref(point))
        origin = (point.x, point.y)
        status, reply = post(port, "/api/toast/delegate", {
            "driver": "cua-2",
            "actions": [{"action": "move", "x": point.x + 1, "y": point.y + 1}],
        })
        task_id = reply.get("task", {}).get("id", "")
        receipt = app.fleet.wait(task_id, timeout=5) if task_id else {}
        check("driver-accepts-task", status == 200 and receipt.get("status") == "done",
              f"{task_id} {receipt.get('status')}")
        cua.user32.GetCursorPos(cua.ctypes.byref(point))
        check("driver-moved-cursor", (point.x, point.y) != origin,
              f"{origin} -> {(point.x, point.y)}")
        cua.move(*origin)

        status, reply = post(port, "/api/toast/delegate", {
            "driver": "cua-2",
            "actions": [{"action": "capture", "window": toast_app.FREEBUFF}],
            "announce": True,
        })
        task_id = reply.get("task", {}).get("id", "")
        receipt = app.fleet.wait(task_id, timeout=10) if task_id else {}
        shot = (receipt.get("results") or [{}])[0] if receipt.get("status") == "done" else {}
        check("driver-captured-freebuff", bool(shot.get("digest")) and pathlib.Path(shot.get("path", "")).exists(),
              f"{task_id} {shot.get('name', '')}")
        announced = until(
            lambda: any(row.get("profile") == "cua-2" for row in app.voice.state().get("queue", []))
            or (app.voice.state().get("last") or {}).get("profile") == "cua-2",
            seconds=5,
        )
        check("driver-speaks-in-own-profile", bool(announced), "cua-2 task announcement")

        status, reply = post(port, "/api/toast/delegate", {
            "driver": "cua-2", "actions": [{"action": "shell", "cmd": "whoami"}],
        })
        check("undeclared-action-refused", status == 409
              and reply.get("refused", {}).get("code") == "action-not-declared",
              str(reply.get("refused", {}).get("code")))

        # Three profiles, one sentence: distinct generated waveforms, not one voice renamed.
        digests = {}
        for profile in ("assistant", "cua-chat", "civilian"):
            target = voice_app.ARTIFACTS / f"probe-{profile}.wav"
            made = app.voice.engine.synthesize(
                app.voice.profile(profile), "One short line for the voice gate.", target)
            digests[profile] = hashlib.sha256(target.read_bytes()).hexdigest()
            check(f"voice-generated-{profile}", made["seconds"] > 0.4 and made["bytes"] > 10_000,
                  f"{made['seconds']}s {made['bytes']}b")
        check("voices-distinct", len(set(digests.values())) == 3,
              " / ".join(value[:10] for value in digests.values()))

        status, reply = post(port, "/api/toast/say", {
            "profile": "civilian",
            "text": "The lane is clear. Please walk. I will tell you when to stop.",
        })
        voice_reply = reply.get("voice", {})
        check("civilian-queue-gated", status == 200 and voice_reply.get("lines") == 3
              and voice_reply.get("gate", {}).get("min_gap_ms") == 2200,
              json.dumps(voice_reply.get("gate", {})))
        check("voice-api-refuses-empty", post(port, "/api/toast/say", {
            "profile": "assistant", "text": ""})[0] == 409, "voice-line-empty")

        mic = app.mic.start()
        ready = until(lambda: app.mic.state_dict()["state"] in ("listening", "heard"), seconds=60)
        check("default-microphone-listening", bool(ready),
              f"{app.mic.state_dict()['state']} {app.mic.state_dict()['detail']}")

        css = (ROOT / "ui" / "toast.css").read_text(encoding="utf-8")
        theme_sheet = (ROOT / "ui" / "contour-theme.css").read_text(encoding="utf-8")
        check("contour-frame-absolute", css.index(".toast > .contour-frame") > css.index(".toast > *"),
              "rule follows the flex-item rule")
        check("no-page-scroll", "overflow: hidden" in css and "max-height: 74px" in css,
              "the page is clipped; only the heard queue scrolls")
        html = (ROOT / "ui" / "toast.html").read_text(encoding="utf-8")
        check("voice-controls-present", 'id="participants"' in html and 'id="mic"' in html
              and 'id="live"' in html, "participant, mic and live controls")
        check("settings-and-resize-present", 'id="settings-panel"' in html
              and 'id="dpi-range"' in html and 'data-resize="bottomright"' in html,
              "DPI + native resize grips")
        check("participants-and-windows-present", 'id="participants"' in html
              and 'id="window-list"' in html, "shared participant/window rows")
        check("workspace-and-heard-present", 'id="workspace-state"' in html
              and 'id="workspace-label"' in html and 'id="workdoc"' in html
              and 'id="workdoc-body"' in html,
              "workspace loader and shared heard document")
        js = (ROOT / "ui" / "toast.js").read_text(encoding="utf-8")
        check("settings-theme-roles", 'data-settings-tab-choice="surface"' in html
              and 'data-settings-tab-choice="palettes"' in html
              and 'id="contour-frames"' in html and 'id="contour-types"' in html
              and 'id="motion-types"' in html
              and "data-contour-frame-choice" in js and "data-contour-type-choice" in js
              and "data-motion-type-choice" in js and "CONTOUR_FRAMES" in js
              and "POPIT_THEMES" in js and "family-roster.json" in js
              and "popit-pairs.json" in js and "loadThemes" in js,
              "frame/material/motion surface plus the family roster")
        check("settings-palette-forge", 'id="planet-field"' in html
              and 'data-planet-source-choice' in html and 'id="palette-editor"' in html
              and 'id="palette-name"' in html and 'id="palette-save"' in html
              and 'id="palette-load"' in html and 'id="palette-undo"' in html
              and 'id="palette-redo"' in html and 'id="palette-import"' in html
              and 'id="palette-export"' in html
              and "customPalettes" in js and "importPalettes" in js
              and "exportPalettes" in js and "planetBodies" in js,
              "planetoid chooser, editor history, community import/export")
        check("settings-layout-contains", "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
              and "grid-template-columns: minmax(0, 1fr) auto" in css
              and "overflow-x: hidden" in css
              and "width: min(320px, calc(100% - 16px))" in css,
              "tab and editor tracks shrink instead of crossing the panel edge")
        check("settings-motion-and-outlines", 'data-motion-choice' in html
              and "applyMotion" in js and "settings-in" in css
              and ".settings .contour-frame path" in css
              and "contour-material" in (css + theme_sheet)
              and "data-material" in (css + theme_sheet)
              and "settings-snap" in css and "allowedFrame" in js
              and "frameForTheme" in js,
              "persisted motion, drawn frames and the clipped material layer")
        check("sourced-goodies-materials", all(f'id: "{name}"' in js for name in ("paper", "card", "glass", "tint", "ink", "accent", "bare"))
              and "LEGACY_MATERIAL_IDS" in js
              and "sourced" in (ROOT / "docs" / "family-look.md").read_text(encoding="utf-8"),
              "seven Goodies Bag materials, legacy ids mapped")
        status, apps_body, _ = get(port, "/api/toast/apps")
        apps = json.loads(apps_body) if status == 200 else {}
        check("app-packages-signed", status == 200
              and apps.get("schema") == toast_app.app_package.STATE_SCHEMA
              and apps.get("publisher") == "popit-publisher"
              and all(row.get("verified") for row in apps.get("apps", {}).values())
              and len(apps.get("apps") or {}) == len(toast_app.app_package.APPS)
              and "ide" not in (apps.get("apps") or {}),
              "every served surface is a signed app package")
        status, one_body, _ = get(port, "/api/toast/apps/springboard")
        spring = json.loads(one_body) if status == 200 else {}
        check("springboard-theme-from-settings", status == 200
              and spring.get("verified") is True
              and bool((spring.get("theme") or {}).get("frame"))
              and bool(spring.get("theme_identity")),
              "the SpringBoard takes its theme from the settings package")
        status, _, _ = get(port, "/package.js")
        check("app-package-client-served", status == 200,
              "the shared app-package client is served")
        status, _, _ = get(port, "/contour-theme.css")
        theme_sheet = (ROOT / "ui" / "contour-theme.css").read_text(encoding="utf-8")
        package_js = (ROOT / "ui" / "package.js").read_text(encoding="utf-8")
        phone_html = (ROOT / "ui" / "phone.html").read_text(encoding="utf-8")
        check("shared-surface-theme", status == 200
              and 'href="/contour-theme.css"' in html
              and 'href="/contour-theme.css"' in phone_html
              and 'html[data-material="paper"]' in theme_sheet
              and 'html[data-material="paper"]' not in css
              and "motion-fold" in theme_sheet,
              "contour, material and motion come from one family sheet")
        check("settings-dpi-scales", "style.zoom" in package_js
              and "theme.colors" in package_js and "style.zoom" in js,
              "the published DPI zooms the surface and its roles are painted")
        status, _ = post(port, "/api/toast/settings/state", {"dpi": 135})
        _, scaled_body, _ = get(port, "/api/toast/apps/dialin")
        scaled = json.loads(scaled_body) if scaled_body else {}
        check("settings-dpi-published", status == 200
              and (scaled.get("theme") or {}).get("dpi") == 135,
              "a panel DPI change reaches the signed package other apps read")
        status, refused_body, _ = get(port, "/api/toast/apps/not-an-app")
        refused = json.loads(refused_body) if refused_body else {}
        check("app-package-unknown-refused", status == 409
              and (refused.get("refused") or {}).get("code") == "app-unknown",
              "a name that is not an app package is refused by name")
        status, landing_body, _ = get(port, "/")
        landing = landing_body.decode("utf-8", "replace") if isinstance(landing_body, bytes) else landing_body
        check("root-is-the-springboard", status == 200
              and "SPRINGBOARD" in landing and "class=\"toast\"" not in landing,
              "the LAN root is the phone home, not the desk wrapped in a shell")
        check("surface-audit-gates-packages",
              "app-ui-audit" in (ROOT / "app_package.py").read_text(encoding="utf-8")
              and "/api/toast/ui-audit" in (ROOT / "toast.py").read_text(encoding="utf-8")
              and "ui-x-overflow" in (ROOT / "ui" / "ui-audit.js").read_text(encoding="utf-8"),
              "a package is signed only after its surface measures clean")
        phone_js = (ROOT / "ui" / "phone.js").read_text(encoding="utf-8")
        check("springboard-is-the-phone-home", 'id="springboard"' in html
              and 'data-src="/phone.html"' in html and 'id="app-grid"' not in html
              and "setSurface" in js and 'data.source !== "popit-springboard"' in js
              and '/api/toast/apps' in phone_js and 'data-package-identity' in phone_js
              and 'label: "Commons"' not in phone_js
              and 'label: "Voice Call"' not in phone_js
              and 'label: "Agent lines"' not in phone_js
              and 'source: "popit-springboard"' in phone_js
              and '.toast[data-surface="springboard"]' in css,
              "the frame loads the phone home it already serves; apps hand control back")
        check("settings-slider-and-scrollbar-themed", "::-webkit-slider-runnable-track" in css
              and "::-moz-range-progress" in css and "--range-progress" in js
              and "scrollbar-color: var(--popit-primary" in css
              and "scrollbar-color: var(--brass)" not in css,
              "DPI track and scrollbars inherit the selected theme")
        check("participant-glyphs", "☎" in js and "✕" in js and "End " in js,
              "number buttons carry call and end glyphs")
        people = ["Buffy", "Qwen", "Ash", "Bram"]
        check("addressing-named", app._recipients("Qwen, what do you see?", people) == ["Qwen"],
              "Qwen")
        check("addressing-default-host", app._recipients("hello there", people) == ["Buffy"],
              "Buffy")
        check("addressing-all", set(app._recipients("both of you, look", people)) == set(people),
              "both")
        check("addressing-contraction", app._recipients("How y'all feeling?", people) == ["Buffy"],
              "Buffy, not a broadcast")
        check("no-text-inputs", html.count('type="text"') == 2
              and 'id="owner-text"' in html and 'id="contact-search"' in html
              and 'id="palette-name"' in html and 'textarea' not in html,
              "owner lane, contact search and the deliberate palette name; no stray text inputs")

        from PySide6.QtWidgets import QApplication
        from window import contour_region
        QApplication.instance() or QApplication([])
        shape = json.loads((ROOT / "contour.json").read_text(encoding="utf-8"))
        region = contour_region(434, 610, shape)
        rows = {rect.y(): rect.width() for rect in region}
        check("window-masked-to-contour", bool(rows) and min(rows.values()) < 430,
              f"{len(rows)} bands, crown {rows.get(min(rows), 0)}px wide")
    finally:
        app.mic.stop()
        app.voice.stop()
        server.shutdown()
        app.stop()
    shutil.rmtree(external_temp, ignore_errors=True)

    receipt = {
        "schema": "popit.toast.probe/1",
        "at": toast_app.iso(),
        "checks": checks,
        "passed": sum(1 for row in checks if row["ok"]),
        "failed": sum(1 for row in checks if not row["ok"]),
    }
    path = ROOT / "runlogs" / "toast" / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"\n{receipt['passed']} passed, {receipt['failed']} failed -> {path}")
    return 0 if receipt["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
