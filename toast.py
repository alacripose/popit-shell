#!/usr/bin/env python3
"""Popit pinned toast: live Freebuff chat probe through delegated CUA drivers.

The window is real Qt on the desktop, masked to the family contour. The loopback server
serves the toast view and a small API. A `cua-chat` driver probes the Freebuff window on a
timer with `probe_chat`; other drivers accept delegated capture/input tasks. The toast
never screenshots the desktop itself: every reading is a driver task with a receipt.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
from urllib.parse import parse_qs, quote, urlsplit

ROOT = pathlib.Path(__file__).resolve().parent
UI = ROOT / "ui"
PORT = 5207
PHONE_CERT = ROOT / "runlogs" / "toast" / "phone-cert.pem"
PHONE_KEY = ROOT / "runlogs" / "toast" / "phone-key.pem"
SCHEMA = "popit.toast/1"
FREEBUFF = "Freebuff: The free coding agent"
PHANTOM_HEARD = {
    "thanks for watching", "thank you for watching", "thank you so much for watching",
    "please subscribe", "see you in the next video",
    "i will see you in the next video", "i'll see you in the next video",
}

# Each name is a separate lane, not a second copy of the same assistant. The lane text
# keeps the shared Debian mind from repeating the same machine answer in every voice.
WORK_ASK = re.compile(
    r"\b(work|job|task|build|fix|implement|handle|deliver|deploy)\b"
    r"|\bplease\s+(?:do|run|make|take)\b", re.I,
)
# An act the owner asks of the machine, not a topic to answer with words. A lane used to
# reply "I would click it" and leave the machine nothing to process; the request is placed on
# the machine's wish queue before the model composes anything.
ACT_ASK = re.compile(
    r"\b(?:click|double-click|right-click|press|tap|drag|type|scroll|hover)\b"
    r"|\b(?:open|close|launch|focus|minimi[sz]e|maximi[sz]e)\s+"
    r"(?:the\s+)?(?:window|app|application|installer|dialog|menu|button|tab)\b",
    re.I,
)
# Lane packages, by name. Buffy is not one of them: that is the Freebuff harness's own
# nickname for the agent on this machine, so a prompt that says "You are Buffy" makes a local
# model speak in its name and answer as a chat assistant. The Buffy line is answered by the
# joined harness and by nothing else; see `ask_mind`'s `buffy-line-without-harness` refusal.
LANES = {
    "Qwen": (
        "You are Qwen, the Debian machine and tool specialist. Inspect the actual Debian "
        "host when needed, answer as Qwen, and do not repeat Buffy's host work, Whisper's "
        "listening channel, Ash's resident work, or Bram's supply work."
    ),
    "Whisper": (
        "You are Whisper, a listening agent with your own voice channel. You own what was "
        "actually said: transcribe, distinguish owner speech from agent output, and speak "
        "only from the audio evidence you have. Do not let another lane rewrite your words; "
        "do not repeat Buffy's host work or Qwen's machine answers."
    ),
    "Ash": (
        "You are Ash, a resident civilian with an embodied local view. Speak from what a "
        "resident can see, need, carry and do; do not run Debian machine work or repeat "
        "Buffy's host work."
    ),
    "Bram": (
        "You are Bram, a resident civilian concerned with storage, supply, movement and "
        "trade. Answer as Bram and do not repeat Ash's or Qwen's work."
    ),
}

# What a lane is for, in the family's own words. A line opens by saying what it is and how its
# own record stands, so two lanes with different lives never open the same way.
ROLES = {
    "Buffy": "the host line",
    "Qwen": "the Debian machine and its tools",
    "Whisper": "the listening channel",
    "Ash": "a resident's embodied view",
    "Bram": "storage, supply and movement",
}


def opening_line(desk, worker: dict, human: dict, wish: str, contract: dict | None) -> str:
    """This lane's opening, read from its civilian record rather than a template.

    A civilian with a need below the care floor says so before it says anything else. One with
    no contract says it will answer and claim nothing. One with a scoped contract names the
    scope. Condition rides along, so an ill lane does not sound like a healthy one.
    """
    lane = str(worker.get("name") or "")
    owner = str(human.get("name") or "")
    role = ROLES.get(lane, "a family civilian")
    try:
        preflight = desk.operation(lane, wish, contract=contract or None)
        life = preflight.get("life") or desk.life_state(lane)
    except civilian_features.Refused as error:
        return (f"{owner}, it's {lane} on {role}. My civilian record will not read ({error.code}), "
                "so I am on the line only to say that.")
    condition = str(preflight.get("condition") or life.get("condition") or "unknown")
    needs = {name: float(value) for name, value in (life.get("needs") or {}).items()
             if isinstance(value, (int, float))}
    need = min(needs, key=needs.get) if needs else ""
    state = str(preflight.get("state") or "")
    # Every lane's record carries its own numbers, so every opening carries them too: the lowest
    # need and its value, the capacity, the last choice it made. Two lanes never read the same.
    facts = []
    if need:
        facts.append(f"{need} reads {needs[need]:.2f}")
    capacity = life.get("capacity")
    if isinstance(capacity, (int, float)):
        facts.append(f"capacity reads {float(capacity):.2f}")
    last = (life.get("lastDecision") or {}).get("kind")
    if last:
        facts.append(f"last choice {last}")
    head = f"{owner}, it's {lane} on {role}."
    if condition not in ("ok", "unknown"):
        head = f"{owner}, it's {lane} on {role}, and my condition reads {condition}."
    standing = ("My " + " and ".join(facts) + ".") if facts else ""
    if state == "care-first":
        care = str(preflight.get("care_line") or "")
        if facts:
            return head + " " + standing + (" " + care if care else " Care comes before work.")
        return head + " Care comes before any work here."
    if state == "work-allowed":
        scope = (contract or {}).get("scope") or []
        first = str(scope[0]) if scope else str((contract or {}).get("mission") or "")
        if first:
            return head + " " + standing + f" The contract is scoped to {first}."
        return head + " " + (standing or "") + " I can take work inside the contract."
    if state == "speech-only":
        return (head + " " + (standing or "") +
                " No contract is attached, so I answer you and claim no deliverable.")
    return head + " " + (standing or "I am listening.")


sys.path.insert(0, str(ROOT))
import archive as archive_mod  # noqa: E402
import axis_bridge  # noqa: E402
import bridge as bridge_mod  # noqa: E402
import calls as calls_mod  # noqa: E402
import civilian_features  # noqa: E402
import civilian_scope  # noqa: E402
import cua  # noqa: E402
import desk_auth  # noqa: E402
import debian_view  # noqa: E402
import debian_window  # noqa: E402
import dialin  # noqa: E402
import envelope  # noqa: E402
import external_agents  # noqa: E402
import hosts  # noqa: E402
import mind_bridge  # noqa: E402
import session_archive  # noqa: E402
import settings_package  # noqa: E402
import app_base  # noqa: E402
import app_package  # noqa: E402
import voice  # noqa: E402

# The remote listener's sign-in ledger: draft sessions and one-time desk codes, in the same
# runlogs tree the phone certificate already lives in.
DESK_STORE = desk_auth.Store(ROOT / "runlogs" / "toast")


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


# -- the bridge ---------------------------------------------------------------
# The client's tools side lives on the family Debian box. This window reads it, and can run one
# bounded command there; both answers name a refusal instead of painting an empty page.

BRIDGE_HOME = pathlib.Path(os.environ.get("MC3_BRIDGE_HOME", r"F:\Documents\mc3-client13"))
BRIDGE_STATE_URL = "http://127.0.0.1:8797/state.json"


def bridge_state() -> dict:
    """The live bridge reading, else the receipt it last wrote, else a named refusal."""
    try:
        with urllib.request.urlopen(BRIDGE_STATE_URL, timeout=2) as reply:
            body = json.loads(reply.read().decode("utf-8") or "{}")
        return {"ok": True, "source": "live", **body}
    except (OSError, ValueError):
        pass
    receipt = BRIDGE_HOME / "artifacts" / "receipts" / "bridge-status.json"
    try:
        body = json.loads(receipt.read_text(encoding="utf-8"))
        return {"ok": True, "source": "receipt", **body}
    except (OSError, ValueError):
        return {"ok": False, "refused": "bridge-offline", "source": "none", "checks": []}


def bridge_run(command: str, timeout: float = 120.0) -> dict:
    """Run one command on the box through the bridge tool, bounded by its own timeout."""
    command = (command or "").strip()
    if not command:
        return {"ok": False, "refused": "bridge-run-empty"}
    tool = BRIDGE_HOME / "tools" / "bridge.py"
    if not tool.is_file():
        return {"ok": False, "refused": "bridge-tool-absent"}
    try:
        completed = subprocess.run(
            [sys.executable, str(tool), "run", "--timeout", str(int(timeout)), "--", command],
            capture_output=True, text=True, timeout=timeout + 15, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "refused": "bridge-run-timeout"}
    return {"ok": completed.returncode == 0, "code": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr,
            "refused": "" if completed.returncode == 0 else "bridge-run-failed"}


class Toast:
    def __init__(self, *, probe_seconds: float = 4.0, play_voice: bool = True) -> None:
        self.lock = threading.RLock()
        self.fleet = cua.Fleet(drivers=4)
        self.voice = voice.VoiceService(play=play_voice)
        self.axis = axis_bridge.AxisBridge()
        self.debian = debian_view.DebianView()
        self.archive = archive_mod.Archive(ROOT / "runlogs" / "toast" / "archive.jsonl")
        # The Debian mind acts on the Debian box through that box's own CUA driver. It never
        # receives the Windows fleet: a model on Debian must not click the owner's desktop.
        self.mind = mind_bridge.DebianMind(self.debian, archive=self.archive,
                                           cua=self.delegate_debian)
        self.window_token = secrets.token_urlsafe(18)
        self.window = debian_window.DebianWindow(
            target_host=hosts.lan_host(), target_port=5208, token=self.window_token,
        )
        self.dialin = dialin.CivilianDialin(ROOT / "runlogs" / "toast", play=play_voice)
        self.external = external_agents.ExternalAgents(ROOT / "runlogs" / "toast" / "external")
        self.envelope_trust = ROOT / "runlogs" / "toast" / "envelope-trust.json"
        self.envelope_nonces = ROOT / "runlogs" / "toast" / "envelope-nonces.json"
        self.settings = settings_package.SettingsPackage(
            ROOT / "runlogs" / "toast" / "settings", trust_path=self.envelope_trust)
        # One publisher, one registry: every app surface is signed with the settings key
        # and verified against the trust file the phone already reads.
        self.apps = app_package.AppPackages(
            ROOT / "runlogs" / "toast" / "apps", ROOT / "ui", settings=self.settings,
            drivers=self.fleet)
        # The pinned control baseline is written from its record before anything is signed, so
        # the sheet an app declares is the current rendering of the buttons it subscribes to.
        app_base.write_controls(ROOT / "ui")
        # A surface is signed before it is served, whether this process is the shell or a
        # probe reading the same routes.
        self.apps.ensure_all()
        self.calls = calls_mod.CallLedger(ROOT / "runlogs" / "toast" / "calls.json", self.dialin,
                                          opening=opening_line)
        self.civilians = civilian_features.CivilianDesk(
            ROOT / "runlogs" / "toast" / "civilians.json")
        self.bridge_ledger = bridge_mod.BridgeLedger(
            ROOT / "runlogs" / "toast" / "bridge-ledger.json")
        # The bridge has its own forward, not the archive kiosk's: a bridge flap must not
        # move the window the owner is reading, and a kiosk restart must not reset a
        # measured heartbeat. Both point at the same token-gated listener.
        self.bridge = bridge_mod.TunnelSupervisor(
            self.window_token, target_host=hosts.lan_host(), target_port=5208,
            target_file=ROOT / "runlogs" / "toast" / "bridge-target.json",
        )
        self.live = True
        self.call = "natural-language"
        self.working = 0
        self.responders: list[str] = []
        self.lane_states: dict[str, dict] = {}
        self.bridge_lock = threading.RLock()
        self.bridges: dict[str, dict] = {}
        # Lane selectors choose which open agents answer an unaddressed owner turn.
        # The commons lane itself is constant: every open line hears it and cannot
        # be closed. Selecting every lane makes the commons unrestricted broadcast.
        self.selected_lanes: set[str] = set()
        self.mic = voice.MicListener(self.voice, on_phrase=self._heard)
        self.fleet.on_task = self._announce_task
        self._heard_lock = threading.Lock()
        self._ask_lock = threading.Lock()
        self.audio_epoch = 0
        self._heard_at = 0.0
        self._heard_text = ""
        self.revision = 0
        self.port = 0
        self.lines: list[dict] = []
        self.capture_path: pathlib.Path | None = None
        self.capture_ts = 0
        self.probe = {
            "state": "waiting", "code": "", "detail": "no probe has run",
            "window": FREEBUFF, "digest": "", "changed": False, "at": "", "age": None,
        }
        self.harness = {
            "state": "waiting", "code": "harness-unprobed",
            "detail": "the Freebuff harness textbox has not been probed",
            "digest": "", "changed": False, "at": "", "typing_at": "", "age": None,
        }
        self.harness_path: pathlib.Path | None = None
        self.harness_history_path: pathlib.Path | None = None
        self.harness_working_path: pathlib.Path | None = None
        self.pending = {"hide": False, "show": False, "pin": None, "close": False,
                        "grab": False, "reload": False}
        self.probe_seconds = max(1.0, probe_seconds)
        self._stop = threading.Event()

    def start(self) -> None:
        self.calls.clear_queues()
        self.archive.repair_hallucinations()
        if not self.settings.state().get("identity"):
            self.settings.publish()
        self.apps.ensure_all()
        threading.Thread(target=self._loop, daemon=True).start()
        self.axis.start()
        self.debian.start()
        self.window.start()
        self.bridge.start()
        for row in self.dialin.bootstrap():
            self.archive.add(
                "event", f"{row['name']} dialed in · {row['number']}",
                role=row["name"], civilian=row["name"], number=row["number"],
                package=row["package_identity"], verified=row["verified"],
                tones=row["tones"],
            )
        self.mic.start()

    def stop(self) -> None:
        self._stop.set()
        self.mic.stop()
        self.axis.stop()
        self.debian.stop()
        self.bridge.stop()
        self.window.stop()
        self.voice.stop()

    def _heard(self, text: str, *, typed: bool = False, phone: dict | None = None) -> bool:
        """A heard question is queued for the family; it never force-cuts a speaking agent.

        `typed` is the owner's text input. It skips only the owner-microphone guards
        below; no branch here ever filters an agent's outgoing lane. Returns whether the
        turn passed the owner guard, so the phone path can publish the same heard state
        as the live microphone.
        """
        clean = " ".join(str(text or "").split())
        if len(clean) < 2:
            return False
        tokens = clean.lower().split()
        stripped = clean.lower().strip(" .!?,;:")
        if not typed:
            if stripped in PHANTOM_HEARD:
                return False
            if len(tokens) == 1 and stripped not in {"yes", "no", "stop", "buffy", "qwen", "whisper", "ash", "bram"}:
                return False
            if len(tokens) >= 6 and len(set(tokens)) <= 2:
                # Whisper can loop on a silent tail; that is a recognizer artifact, not a turn.
                return False
            # A line that is mostly the current TTS output is speaker echo, not the owner.
            if self.voice.echoes(clean):
                return False
            # Quiet-mic ASR can turn static into a long repeated sign-off. It is not
            # an owner turn, so it never reaches a lane, the archive, or an agent answer.
            if archive_mod.is_hallucination(clean):
                self.archive.add("event", "microphone hallucination discarded · quiet-mic sign-off",
                                 role="repair", source="audio", sample=clean[:120])
                return False
        now = time.monotonic()
        with self._heard_lock:
            if clean == self._heard_text and now - self._heard_at < 2.5:
                return False
            self._heard_text, self._heard_at = clean, now
        # Owner speech is a new turn, not a remote control for the current one. The
        # prior implementation cleared the voice queue and stopped playback here, which
        # made the owner's microphone an interruption authority. It is not: the speaking
        # agent decides whether to yield, and its current line is allowed to finish.
        with self.lock:
            epoch = self.audio_epoch
        # In a call every utterance is ordinary language for the Debian mind. The microphone
        # button and Live toggle are the only controls; no spoken command grammar is parsed.
        actives = self.calls.actives()
        reached = [call["agent"] for call in actives]
        addressed = self._recipients(clean, reached, fallback=False)
        selected = [name for name in reached if name in self.selected_lanes]
        # Empty selection is the commons lane: every open agent is addressed. A lane
        # selector narrows that to the chosen lane; an explicit name always wins.
        targets = addressed or selected or list(reached)
        with self.lock:
            self.revision += 1
        self.archive.add(
            "user", clean, role="you",
            calls=[call["id"] for call in actives],
            targets=targets or ["Buffy"], heard_by=reached,
            lanes=sorted(self.selected_lanes), typed=typed,
        )
        if actives or self.live:
            threading.Thread(target=self._live_ask,
                             args=(clean, targets, epoch, phone), daemon=True).start()
            return True
        # Hold the transcript for correction. The microphone pauses here so the next sound
        # cannot replace the words the user is editing; Send resumes it.
        self.mic.stop()
        with self.mic.lock:
            self.mic.detail = "held transcript; send to resume"
        self._line(f"you · {clean}", "ok")
        return True

    def phone_heard(self, text: str, lane: str | None = None) -> dict:
        """Owner text from the secure phone surface, using the normal owner turn."""
        clean = " ".join(str(text or "").split())
        if not clean:
            return {"ok": False, "refused": "empty-text"}
        if lane:
            self.set_lanes([lane])
        self._heard(clean, typed=True)
        return {"ok": True, "heard": clean, "lane": lane or "COMMONS",
                "lanes": self.lane_state()}

    def phone_audio(self, data: bytes, lane: str | None = None, *,
                    reply: bool = False) -> dict:
        """Transcribe a browser mic WAV, then feed it through the owner voice path.

        With `reply=True` the request follows the turn through the mind, renders the
        answer in the active natural voice, and returns the WAV to the phone. It never
        plays the answer on the Windows output: the phone is the endpoint's speaker.
        """
        if not data:
            return {"ok": False, "refused": "empty-audio"}
        if len(data) > 12 * 1024 * 1024:
            return {"ok": False, "refused": "audio-too-large"}
        if not data.startswith(b"RIFF"):
            return {"ok": False, "refused": "audio-not-wav"}
        if lane:
            self.set_lanes([lane])
        PHONE_CERT.parent.mkdir(parents=True, exist_ok=True)
        source = PHONE_CERT.parent / f"phone-{secrets.token_hex(6)}.wav"
        source.write_bytes(data)
        script = ROOT / "tools" / "transcribe_wav.py"
        try:
            result = subprocess.run(
                [sys.executable, str(script), str(source)], cwd=str(ROOT),
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=150,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            source.unlink(missing_ok=True)
            return {"ok": False, "refused": "asr-unavailable", "detail": str(error)[:240]}
        finally:
            source.unlink(missing_ok=True)
        lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
        try:
            receipt = json.loads(lines[-1]) if lines else {}
        except ValueError:
            receipt = {}
        text = " ".join(str(receipt.get("text") or "").split())
        if result.returncode != 0 or not text:
            return {"ok": False, "refused": "asr-no-text",
                    "detail": str(receipt.get("error") or (result.stderr or "")[-240:])[:500]}
        # This is captured owner speech, not typed text: the same quiet-mic guards apply.
        turn = None
        if reply:
            turn = {"id": secrets.token_hex(8), "event": threading.Event(), "result": None}
        accepted = self._heard(text, typed=False, phone=turn)
        if not accepted:
            return {"ok": False, "refused": "owner-guard", "transcript": text,
                    "lane": lane or "COMMONS", "lanes": self.lane_state()}
        self.mic.record_phone(text)
        if turn is None:
            return {"ok": True, "transcript": text, "lane": lane or "COMMONS",
                    "lanes": self.lane_state()}
        if not turn["event"].wait(180):
            return {"ok": False, "refused": "answer-timeout", "transcript": text,
                    "lane": lane or "COMMONS", "lanes": self.lane_state()}
        result = turn.get("result") or {}
        answer = str(result.get("answer") or "").strip()
        return {
            "ok": bool(answer), "transcript": text, "answer": answer,
            "audio_b64": str(result.get("audio_b64") or ""),
            "audio_mime": str(result.get("audio_mime") or "audio/wav"),
            "voice_profile": str(result.get("profile") or ""),
            "voice_engine": str(result.get("engine") or ""),
            "answer_state": str(result.get("state") or ""),
            "refused": "" if answer else str(result.get("refused") or "no-answer"),
            "lane": lane or "COMMONS", "lanes": self.lane_state(),
        }

    def _recipients(self, text: str, names: list[str], *, fallback: bool = True) -> list[str]:
        """Every open line hears the owner; only the addressed line answers.

        The earlier routing made every connected civilian speak at once. On a call that
        becomes a chorus of unrelated greetings, and the owner cannot tell which lane is
        actually listening. Addressed names select a lane; otherwise Buffy is the host.
        A line is still archived for every open call, so the other lanes hear it in their
        own history without claiming the floor.
        """
        words = " ".join(str(text or "").lower().split())
        # A collective address is an explicit request for every live lane, not a
        # request for the host to answer alone. The old grammar only understood
        # names, so "both of you" silently fell back to Buffy.
        if len(names) > 1 and re.search(r"\b(both|everyone|everybody)\b", words):
            return list(names)
        addressed: list[str] = []
        for name in names or []:
            folded = " ".join(str(name).lower().split())
            first = folded.split()[0] if folded else ""
            if (folded and re.search(rf"\b{re.escape(folded)}\b", words)) or \
               (first and re.search(rf"\b{re.escape(first)}\b", words)):
                addressed.append(name)
        if not fallback:
            return addressed
        return addressed or (["Buffy"] if "Buffy" in (names or []) else list(names)[:1])

    def lane_state(self) -> dict:
        """The constant commons lane plus the selectable live agent lanes."""
        actives = self.calls.actives()
        active_names = {call["agent"] for call in actives}
        with self.lock:
            self.selected_lanes &= active_names
            selected = sorted(self.selected_lanes)
        profiles = {row["id"]: row for row in self.voice.state().get("profiles", [])}
        lanes = []
        for call in actives:
            profile = profiles.get(str(call.get("agent_id") or "")) or {}
            lanes.append({
                "name": call["agent"], "id": call.get("agent_id"), "call": call["id"],
                "channel": profile.get("channel") or "default",
                "selected": call["agent"] in selected,
            })
        return {
            "schema": "popit.lanes/1",
            "commons": {"open": True, "unrestricted": True, "label": "COMMONS",
                        "all": not selected,
                        "agents": [call["agent"] for call in actives]},
            "selected": selected,
            "active": lanes,
        }

    def set_lanes(self, names: list[str]) -> dict:
        """Select which unaddressed owner turns each open lane answers.

        This applies to every lane identically; Whisper is not special-cased. The
        commons lane remains open even when no lane is selected.
        """
        actives = self.calls.actives()
        valid = {call["agent"] for call in actives}
        chosen = sorted({str(name) for name in names if str(name) in valid})
        with self.lock:
            self.selected_lanes = set(chosen)
            self.revision += 1
        self.archive.add(
            "event", f"lanes selected · {', '.join(chosen) or 'commons · all lanes'}",
            role="lanes", lanes=chosen, commons=not chosen,
        )
        return self.lane_state()

    def begin_call(self, call: dict, incoming: bool = False) -> None:
        """Every call opens with the line tone, both voices, then persistent listening."""
        def run() -> None:
            # The package tone is the first thing on a line, before the microphone can
            # hear its own DTMF. Never skip it when a package or roster is refreshed.
            tone = "incoming" if incoming else "outgoing"
            try:
                edge = self.dialin.call_tone(
                    {"id": call.get("agent_id") or str(call.get("agent") or "").lower()},
                    tone,
                    # The number the call carried wins over the roster's number: the owner
                    # hears the line that actually rang, not a sequence the roster holds.
                    number=str(call.get("number") or ""),
                )
                heard = "played" if edge.get("played") else "retained · output busy"
                self.archive.add("call-tone", f"{tone} dial tone · {call['agent']} · {heard}",
                                 role="call", call=call["id"], tone=tone, played=edge.get("played", False),
                                 path=edge.get("path", ""), number=edge.get("number", ""),
                                 dialled=edge.get("dialled", ""), source=edge.get("source", ""))
            except dialin.Refused as error:
                self.archive.add("event", f"{tone} tone refused · {error.code}",
                                 role="call", call=call["id"])
            self.calls.start_listening(call["id"])
            self._lane(call["agent"], "listening", "own thread")
            self.archive.add(
                "call-listen",
                f"{call['civilian']} and {call['agent']} are listening for the next response",
                role="call", call=call["id"], civilian=call["civilian"], agent=call["agent"],
            )
            self.mic.start()
            for intro in call.get("opening") or []:
                profile = str(intro.get("profile") or intro.get("name") or "cua-chat")
                try:
                    self.voice.say(profile, intro["line"])
                except voice.Refused as error:
                    self.archive.add("event", f"opening voice refused · {error.code}",
                                     role="call", call=call["id"])
                self.archive.add(
                    "call-opening", intro["line"], role=intro.get("name", ""),
                    call=call["id"], presence=intro.get("presence", ""),
                    want=intro.get("want", ""),
                )
        threading.Thread(target=run, daemon=True).start()

    def opening_line(self, worker: dict, human: dict, wish: str,
                     contract: dict | None) -> str:
        """The ledger's builder: each opening comes from the lane's own civilian record."""
        return opening_line(self.civilians, worker, human, wish, contract)

    def call_back(self, row: dict) -> dict:
        """A hang-up is answered by dialling the same lane back, and saying who rang.

        The desk had no hang-up: ending a line posted the wish-close route with a proof
        path, so the owner hanging up was archived as work completed and no one dialled
        back. The callback is its own line, opened as incoming, so the owner hears it.
        """
        back = self.calls.open(
            str(row["civilian"]), str(row["agent"]),
            f"call back after the hang-up on {row['id']}",
            f"line {row['id']} closed by {row['civilian']} at {row.get('closed') or iso()}",
            0, allow_multiple=True)
        self.archive.add(
            "call-callback",
            f"callback {back['id']} · {row['agent']} ringing {row['civilian']} back",
            role="call", call=back["id"], agent=back["agent"], civilian=back["civilian"],
            from_call=row["id"],
        )
        self.begin_call(back, incoming=True)
        return back

    def harness_fresh(self, limit: float | None = None) -> tuple[bool, str]:
        """A reply is allowed only after the CUA textbox band was probed recently."""
        harness = self.harness
        if harness.get("state") != "live" or not harness.get("at"):
            return False, str(harness.get("detail") or "the harness textbox is unprobed")
        if not all(harness.get(key) for key in ("history_digest", "working_digest")):
            return False, "the harness history or working area is unprobed"
        try:
            moment = datetime.datetime.fromisoformat(harness["at"])
            age = (datetime.datetime.now(datetime.timezone.utc) - moment).total_seconds()
        except ValueError:
            return False, "the harness textbox probe time is unreadable"
        allowed = limit if limit is not None else max(8.0, self.probe_seconds * 3.0)
        if age > allowed:
            return False, f"the harness textbox was last probed {int(age)}s ago"
        return True, ""

    def require_harness(self) -> None:
        fresh, detail = self.harness_fresh()
        if not fresh:
            raise cua.Refused("harness-unprobed", detail)

    def _lane(self, name: str, stage: str, detail: str = "") -> None:
        """Publish where one civilian's processing thread actually is."""
        with self.lock:
            self.lane_states[str(name)] = {"stage": stage, "detail": detail, "at": iso()}

    def begin_work(self) -> None:
        with self.lock:
            self.working += 1

    def end_work(self) -> None:
        with self.lock:
            self.working = max(0, self.working - 1)

    def delegate_debian(self, payload: dict) -> dict:
        """One small act for the Debian box's own body, in the acts that box exposes.

        The loop on Debian executes with the host's `xdotool` and reads the world back. Its
        exposed acts are pointer *move* and screen capture; it has no click act. A click is
        refused by name here, because the alternatives are a simulated click (a lie) or the
        Windows fleet (the wrong machine).
        """
        actions = payload.get("actions") or []
        action = dict(actions[0]) if actions else {}
        kind = str(action.get("action") or "").strip().lower()
        if kind in ("capture", "screen"):
            row = self.axis.tool("screen.capture", {})
        elif kind in ("move", "pointer"):
            row = self.axis.tool("input.pointer", {"x": int(action.get("x") or 0),
                                                    "y": int(action.get("y") or 0)})
        elif kind == "click":
            raise axis_bridge.Refused(
                "click-act-absent",
                "the Debian body exposes pointer move, screen capture and typing tasks, but "
                "no click act; nothing was clicked here or on the owner's Windows machine")
        elif kind in ("type", "key", "window", "focus", "windows", "list"):
            raise axis_bridge.Refused(
                "act-not-exposed", f"{kind} is not an act the Debian loop exposes over "
                "/v1/tools/call; it runs windows and typed text through its own task steps")
        else:
            raise axis_bridge.Refused(
                "task-tool-unknown", f"{kind or 'no action'} is not a Debian driver action")
        return {"id": f"debian-{row['at']}", "status": "done" if row["ok"] else "refused",
                "tool": row["tool"], "result": row["result"], "at": row["at"]}

    def place_wish(self, text: str, *, intent: str = "act", agent: str = "",
                   call: str = "", extra: dict | None = None) -> dict:
        """Put the owner's request on the machine before any lane answers it.

        The spoken answer stays the lane's; this is the request the machine can process. A
        refusal is recorded by name, never swallowed into an answer that sounds like work.
        """
        payload = dict(extra or {})
        if agent:
            payload["lane"] = agent
        if call:
            payload["call"] = call
        try:
            row = self.axis.wish(intent, text, payload)
        except axis_bridge.Refused as error:
            self._line(f"wish refused · {error.code}", "refused")
            self.archive.add("wish", f"refused · {error.code} · {error.detail}", role="wish",
                             question=text, agent=agent, call=call, intent=intent,
                             refused=error.as_dict())
            return {"ok": False, "refused": error.as_dict()}
        answer = row.get("answer") or {}
        wish_id = ""
        if isinstance(answer, dict):
            wish_id = str(answer.get("task_id") or answer.get("id") or answer.get("wish")
                          or answer.get("task") or "")
        status = str((answer or {}).get("status") or "").lower()
        if status not in ("accepted", "ok", "deferred"):
            # A queue that answered "declined" did not take the request. Saying so by name is
            # the difference between a refusal and a wish that only looks placed.
            code = str((answer or {}).get("code") or "wish-declined")
            detail = str((answer or {}).get("detail") or status or "no status")
            self._line(f"wish refused · {code}", "refused")
            self.archive.add("wish", f"refused · {code} · {detail}", role="wish",
                             question=text, agent=agent, call=call, intent=intent,
                             refused={"code": code, "detail": detail})
            return {"ok": False, "wish": wish_id, "intent": intent, "answer": answer,
                    "refused": {"code": code, "detail": detail},
                    "queue": dict(self.axis.wish_health)}
        label = text if len(text) <= 70 else text[:67] + "..."
        self._line(f"wish {'· ' + wish_id + ' ' if wish_id else ''}· {label}", "ok")
        self.archive.add("wish", text, role="wish", question=text, agent=agent, call=call,
                         intent=intent, wish=wish_id, answer=answer)
        return {"ok": True, "wish": wish_id, "intent": intent, "answer": answer,
                "queue": dict(self.axis.wish_health)}

    def ask_axis(self, text: str, profile: str = "cua-chat") -> dict:
        row = self.axis.ask(text)
        if row.get("answer"):
            self._line(f"axis · {row['answer']}", "ok")
            self.archive.add("axis", row["answer"], role="axis", question=text)
            self.voice.say(profile, row["answer"])
        else:
            missing = ", ".join(row.get("missing") or []) or "an unattested shape"
            self._line(f"axis kept quiet · {missing}", "refused")
            self.archive.add("axis", f"kept quiet · {missing}", role="axis", question=text)
        return row

    def bridge_join(self, agent: str = "Buffy", profile: str = "buffy",
                    admission: dict | None = None) -> dict:
        """Attach a general agent harness to an existing call as a speaking participant.

        This is the missing edge between a coding agent and the telephone surface: the
        harness receives owner and sibling-lane turns, and can speak with the same voice
        and document grammar as a local lane. Once joined, the local Qwen Buffy lane
        yields; otherwise two different minds would answer under one name.

        A signed admission is authoritative about the caller's name. The local MCP
        bridge calls this without one because it is already on the host loopback; the
        public `/api/toast/call/join` route verifies an envelope before it gets here.
        """
        name = " ".join(str((admission or {}).get("agent") or agent or "Buffy").split()) or "Buffy"
        # An enrolled external civilian is named for the machine it sits on ("Qwen on the
        # Debian box"), while the line is opened for the lane ("Qwen"). Read the lane out of
        # the enrollment so the same line answers to both names instead of refusing.
        lane = name.split(" on the ")[0] or name
        call = next((row for row in self.calls.actives()
                     if row.get("agent") in (name, lane)
                     or row.get("agent_id") == lane.lower()
                     or row.get("caller") == name), None)
        if call is None:
            open_lanes = ", ".join(sorted(str(row.get("agent")) for row in self.calls.actives())) or "none"
            raise calls_mod.Refused("bridge-line-absent",
                                    f"no open call for {name} · open lines: {open_lanes}")
        session = f"callbridge-{secrets.token_hex(8)}"
        call = self.calls.mark_external(call["id"], True, session)
        latest = max((int(row.get("id") or 0) for row in self.archive.read(200)), default=0)
        with self.bridge_lock:
            self.bridges[session] = {
                "session": session, "call": call["id"], "agent": name,
                "profile": str(profile or call.get("agent_id") or name.lower()),
                "cursor": max(0, latest - 12), "joined": iso(), "seen": iso(),
                "caller": str((admission or {}).get("caller") or ""),
                "fingerprint": str((admission or {}).get("fingerprint") or ""),
            }
        self.calls.start_listening(call["id"])
        self.mic.start()
        self._lane(name, "listening", "external harness")
        self.archive.add("event", f"external agent harness joined · {name} · {call['id']}",
                         role=name, call=call["id"], external=True, session=session,
                         caller=(admission or {}).get("caller") or "",
                         fingerprint=(admission or {}).get("fingerprint") or "")
        return {"session": session, "call": call, "cursor": max(0, latest - 12),
                "agent": name, "caller": (admission or {}).get("caller") or "",
                "fingerprint": (admission or {}).get("fingerprint") or "",
                "profile": profile or call.get("agent_id") or name.lower()}

    def _bridge(self, session: str) -> dict:
        with self.bridge_lock:
            state = dict(self.bridges.get(str(session)) or {})
        if not state:
            raise calls_mod.Refused("bridge-session-unknown", str(session or ""))
        call = next((row for row in self.calls.actives()
                     if row.get("id") == state["call"]), None)
        if call is None or not call.get("external"):
            raise calls_mod.Refused("bridge-line-closed", state["call"])
        return state

    def bridge_turns(self, session: str, since: int | None = None,
                     wait: float = 0.0) -> dict:
        """Long-poll the call for owner speech and sibling-agent lines."""
        state = self._bridge(session)
        cursor = int(since if since is not None else state.get("cursor") or 0)
        limit = max(0.0, min(25.0, float(wait or 0.0)))
        deadline = time.monotonic() + limit
        turns: list[dict] = []
        while True:
            rows = self.archive.read(200)
            turns = [dict(row) for row in rows
                     if int(row.get("id") or 0) > cursor
                     and (row.get("kind") in ("user", "cua")
                          or row.get("kind") in ("call-tone", "call-opening", "call-listen"))]
            if turns or time.monotonic() >= deadline:
                break
            time.sleep(0.2)
        if turns:
            cursor = max(int(row.get("id") or 0) for row in turns)
        with self.bridge_lock:
            if session in self.bridges:
                self.bridges[session]["cursor"] = cursor
                self.bridges[session]["seen"] = iso()
        # The external lane answers from its own civilian record, not from my description of it.
        # The C9 condition, the care choice and the contract boundary reach the box with the
        # turns, because the box is the one that has to write inside them.
        try:
            grounding = self.civilians.context(state["agent"])
            life = self.civilians.life_state(state["agent"])
        except civilian_features.Refused as error:
            grounding = f"civilian record unreadable · {error.code}"
            life = {"condition": "unknown", "needs": {}, "state": "unreadable"}
        return {"session": session, "call": state["call"], "agent": state["agent"],
                "cursor": cursor, "turns": turns, "waiting": not turns,
                "context": grounding, "life": life}

    def bridge_say(self, session: str, text: str, *, speak: bool = True) -> dict:
        """Speak and archive a line from the attached general agent harness."""
        state = self._bridge(session)
        clean = " ".join(str(text or "").split())
        if not clean:
            raise calls_mod.Refused("bridge-empty", "a spoken bridge line needs words")
        call = next(row for row in self.calls.actives() if row["id"] == state["call"])
        # The same preflight a host lane gets: a dead lane does not answer, an incomplete
        # contract cannot claim a deliverable, and care below the floor speaks without work.
        preflight = self.civilians.operation(state["agent"], clean,
                                             contract=(call.get("contract") or None),
                                             call=state["call"])
        if not preflight.get("allowed", True):
            refusal = preflight.get("refusal") or {}
            raise calls_mod.Refused(str(refusal.get("code") or "civilian-refused"),
                                    str(refusal.get("detail") or "")[:240])
        row = self.archive.add("cua", clean, role=state["agent"], call=call["id"],
                               external=True, source="agent-harness", session=session)
        self.calls.queue_response(call["id"], state["agent"], "agent", clean)
        self._lane(state["agent"], "speaking", "external agent harness")
        receipt = self.voice.say(state["profile"], clean) if speak else {"state": "silent"}
        self._lane(state["agent"], "listening", "external harness")
        with self.bridge_lock:
            if session in self.bridges:
                self.bridges[session]["seen"] = iso()
        return {"session": session, "call": call["id"], "archive": row,
                "voice": receipt, "agent": state["agent"],
                "civilian": {"state": preflight.get("state"),
                             "work_allowed": preflight.get("work_allowed"),
                             "condition": preflight.get("condition"),
                             "care_line": preflight.get("care_line")}}

    def bridge_leave(self, session: str) -> dict:
        state = self._bridge(session)
        call = self.calls.mark_external(state["call"], False)
        with self.bridge_lock:
            self.bridges.pop(session, None)
        self.archive.add("event", f"external agent harness left · {state['agent']} · {state['call']}",
                         role=state["agent"], call=state["call"], external=False)
        return {"session": session, "call": call, "agent": state["agent"]}

    def ask_mind(self, text: str, profile: str = "cua-chat",
                 targets: list[str] | None = None, epoch: int | None = None,
                 speak: bool = True) -> dict:
        """One addressed lane answers; the other connected lanes only hear it."""
        self.require_harness()
        actives = self.calls.actives()
        by_name = {call["agent"]: call for call in actives}
        if targets is None:
            chosen = list(by_name.values())
        else:
            chosen = [by_name[name] for name in targets if name in by_name]
        external = [call for call in chosen if call.get("external")]
        chosen = [call for call in chosen if not call.get("external")]
        if actives and not chosen:
            if external:
                self._lane(external[0]["agent"], "listening", "external harness turn")
                return {"answer": "", "bridge": "external",
                        "call": external[0]["id"], "agent": external[0]["agent"]}
            chosen = list(by_name.values()) or [actives[0]]
        # The machine's queue hears an act request even while the lane composes an answer.
        # Without this, "click the Steam installer" left a transcript and an empty queue.
        wish_row = None
        if ACT_ASK.search(text):
            lead = chosen[0] if chosen else (actives[0] if actives else {})
            wish_row = self.place_wish(text, intent="act",
                                       agent=str(lead.get("agent") or ""),
                                       call=str(lead.get("id") or ""))
        self.begin_work()
        with self.lock:
            self.responders = [call["agent"] for call in chosen]
        for call in chosen:
            self._lane(call["agent"], "queued", "waiting for its lane turn")
        last: dict = {}
        try:
            if chosen:
                for call in chosen:
                    if call["agent"] == "Buffy" and not call.get("external"):
                        # No package speaks in the harness's name. Without the joined harness
                        # this line says so, instead of a local model inventing Buffy's voice.
                        code = "buffy-line-without-harness"
                        answer = ("No harness is joined on the Buffy line, so nothing here will "
                                  "answer as Buffy. Join the harness to this line first.")
                        self._lane("Buffy", "refused", code)
                        self._line(f"Buffy · {answer}", "refused")
                        self.archive.add("cua", answer, role="Buffy", question=text,
                                         call=call["id"], refused={"code": code})
                        self.calls.queue_response(call["id"], "Buffy", "agent", answer)
                        last = {"answer": answer, "refused": {"code": code}}
                        continue
                    self._lane(call["agent"], "thinking", "reading your line")
                    persona = LANES.get(
                        call["agent"],
                        f"You are {call['agent']}, a family civilian with your own view and "
                        "work. Answer in your own voice; do not repeat another civilian's "
                        "answer or claim work you did not inspect.",
                    )
                    if len(chosen) > 1:
                        others = ", ".join(item["agent"] for item in chosen if item is not call)
                        persona += (
                            "\n\nYou are sharing this live call with " + others +
                            ". You can hear that lane, but answer only from your own work; "
                            "do not claim their work or say they are absent from the call."
                        )
                    grounding = self.civilians.context(call["agent"])
                    if grounding:
                        persona += "\n\nFamily civilian grounding:\n" + grounding
                    contract = call.get("contract") or {}
                    try:
                        preflight = self.civilians.operation(
                            call["agent"], text, contract=contract, call=call["id"],
                        )
                    except civilian_features.Refused as error:
                        answer = f"I cannot take that turn: {error.code}."
                        self._lane(call["agent"], "refused", error.code)
                        self._line(f"{call['agent']} · {answer}", "refused")
                        self.archive.add("cua", answer, role=call["agent"],
                                         question=text, call=call["id"],
                                         refused=error.as_dict())
                        self.calls.queue_response(call["id"], call["agent"], "agent", answer)
                        last = {"answer": answer, "refused": error.as_dict()}
                        continue
                    if not preflight["allowed"]:
                        refused = preflight.get("refusal") or {"code": "civilian-refused"}
                        answer = str(refused.get("line") or
                                     f"I cannot take that turn: {refused['code']}.")
                        self._lane(call["agent"], "refused", refused["code"])
                        self._line(f"{call['agent']} · {answer}", "refused")
                        self.archive.add("cua", answer, role=call["agent"],
                                         question=text, call=call["id"],
                                         refused=refused, operation=preflight)
                        self.calls.queue_response(call["id"], call["agent"], "agent", answer)
                        last = {"answer": answer, "refused": refused,
                                "civilian_operation": preflight}
                        continue
                    persona += "\n\nCivilian operation preflight:\n" + preflight["directive"]
                    if preflight["state"] == "care-first":
                        # The C9 choice is authoritative for this turn. Do not spend a model
                        # call asking a starving or exhausted lane to role-play willingness.
                        answer = str(preflight.get("care_line") or "I need care first.")
                        row = {"answer": answer, "model": "c9-care-gate", "tool_runs": []}
                        self._lane(call["agent"], "care", "below the C9 care floor")
                    elif preflight["state"] == "speech-only" and WORK_ASK.search(text):
                        answer = str(preflight.get("contract_line") or (
                            "I cannot take that task without a seven-field contract. "
                            "Give me the mission, scope, constraints, resources, evidence, "
                            "deliverable and stop first."
                        ))
                        row = {"answer": answer, "model": "contract-gate", "tool_runs": []}
                        self._lane(call["agent"], "refused", "contract-absent")
                    else:
                        row = self.mind.ask(text, persona=persona,
                                            identity=str(call.get("agent_id") or call["agent"]))
                    last = row
                    answer = str(row.get("answer") or "").strip()
                    if not answer:
                        self._lane(call["agent"], "listening", "no answer returned")
                        continue
                    try:
                        row["civilian_operation"] = self.civilians.record_operation(
                            preflight["id"], answer, confidence=row.get("confidence"),
                        )
                    except civilian_features.Refused as error:
                        row["civilian_operation"] = {"refused": error.as_dict()}
                    if epoch is not None and epoch != self.audio_epoch:
                        continue
                    self._lane(call["agent"], "composing", f"answer · {len(answer)} chars")
                    self._line(f"{call['agent']} · {answer}", "ok")
                    self.archive.add("cua", answer, role=call["agent"],
                                     question=text, tools=row.get("tool_runs") or [],
                                     call=call["id"])
                    self.calls.queue_response(call["id"], call["agent"], "agent", answer)
                    if speak:
                        try:
                            self.voice.say(str(call.get("agent_id") or profile), answer)
                            self._lane(call["agent"], "speaking", "voice queued in its own queue")
                        except voice.Refused as error:
                            self._line(f"voice · {call['agent']} · {error.code}", "refused")
                            self._lane(call["agent"], "refused", error.code)
                    else:
                        self._lane(call["agent"], "speaking", "phone endpoint voice")
            else:
                last = self.mind.ask(text)
                answer = str(last.get("answer") or "").strip()
                if answer:
                    if epoch is not None and epoch != self.audio_epoch:
                        return last
                    self._line(f"cua · {answer}", "ok")
                    self.archive.add("cua", answer, role="cua", question=text,
                                     tools=last.get("tool_runs") or [])
                    if speak:
                        self.voice.say(profile, answer)
        finally:
            for call in chosen:
                self._lane(call["agent"], "listening", "own thread")
            with self.lock:
                self.responders = []
            self.end_work()
        if wish_row is not None:
            last = dict(last or {})
            last["wish"] = wish_row
        return last

    def _live_ask(self, text: str, targets: list[str] | None = None,
                  epoch: int | None = None, phone: dict | None = None) -> None:
        """One persistent spoken turn: the microphone stays open while the mind answers."""
        active = self.calls.active()
        profile = str((active or {}).get("agent_id") or "cua-chat")
        self._line(f"you · {text}", "ok")
        self.archive.add("buffy", "handed the turn to the Debian mind", role="buffy")
        row: dict = {}
        try:
            # One owner turn at a time: words heard while an agent is speaking are
            # queued behind that answer instead of cancelling or outrunning it.
            with self._ask_lock:
                row = self.ask_mind(text, profile, targets, epoch, speak=phone is None)
        except (mind_bridge.Refused, axis_bridge.Refused) as error:
            self._line(f"delegation · {error.code}", "refused")
            if phone is not None:
                phone["result"] = {"refused": error.code, "answer": "", "profile": profile}
            elif epoch is None or epoch == self.audio_epoch:
                try:
                    self.voice.say(profile, f"The Debian lane refused: {error.code}.")
                except voice.Refused:
                    pass
        except Exception as error:  # a phone turn must end with a receipt, not a hung request
            self._line(f"delegation · answer-failed — {str(error)[:120]}", "refused")
            if phone is not None:
                phone["result"] = {"refused": "answer-failed", "answer": "",
                                  "detail": str(error)[:240], "profile": profile}
        finally:
            if phone is not None:
                result = dict(phone.get("result") or {})
                answer = str((row or {}).get("answer") or result.get("answer") or "").strip()
                if answer:
                    try:
                        made = self.voice.render(profile, answer)
                        result.update({
                            "answer": answer, "audio_b64": base64.b64encode(made["audio"]).decode("ascii"),
                            "audio_mime": "audio/wav", "profile": made["profile"],
                            "engine": made["engine"], "seconds": made["seconds"],
                            "state": "rendered",
                        })
                    except voice.Refused as error:
                        result.update({"answer": answer, "profile": profile,
                                       "refused": error.code, "state": "text-only"})
                elif not result.get("refused"):
                    result.update({"answer": "", "profile": profile,
                                   "refused": "no-answer", "state": "text-only"})
                phone["result"] = result
                phone["event"].set()

    def _announce_task(self, task: cua.Task) -> None:
        """A delegated driver reports in its own profile, never in the assistant's voice."""
        action = str((task.actions[0] if task.actions else {}).get("action") or "task")
        if task.status == "done":
            text = f"Task complete. I finished the {action}."
        else:
            text = f"Task refused. The {action} gave a named refusal."
        try:
            self.voice.say(task.driver, text)
        except voice.Refused:
            pass  # the task receipt remains the record; a voice refusal cannot erase it

    def _line(self, text: str, tone: str) -> None:
        with self.lock:
            self.lines = (self.lines + [{"text": text, "tone": tone, "at": iso()[11:19]}])[-6:]
        try:
            self.archive.add("event", text, role="system", tone=tone)
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.wait(self.probe_seconds):
            # A periodic failure is a row, never a dead thread: an exception here used to end
            # the only probe loop, so the harness stayed `waiting` for the whole life of the
            # desk and every spoken turn was refused `harness-unprobed`.
            try:
                # Repair is also periodic: a quiet stretch can be archived before the
                # recognizer's final pass is corrected, and the owner should not have to
                # restart to remove that row.
                self.archive.repair_hallucinations()
            except Exception as error:
                self._line(f"archive repair · {str(error)[:120]}", "refused")
            try:
                self.run_probe()
            except Exception as error:
                self._line(f"chat probe · {str(error)[:120]}", "refused")

    def run_probe(self) -> dict:
        try:
            shot = self.fleet.probe_freebuff(FREEBUFF)
        except cua.Refused as error:
            with self.lock:
                self.probe = {
                    "state": "refused", "code": error.code, "detail": error.detail,
                    "window": FREEBUFF, "digest": "", "changed": False,
                    "at": iso(), "age": 0,
                }
                self.harness = {
                    "state": "refused", "code": "harness-unprobed",
                    "detail": f"the cua-chat textbox probe refused: {error.code}",
                    "digest": "", "changed": False, "at": "", "typing_at": "", "age": 0,
                }
                self._line(f"chat probe · {error.code} — {error.detail}", "refused")
                self.revision += 1
            return dict(self.probe)
        except Exception as error:  # a driver failure is a refusal, not a crash
            with self.lock:
                self.probe = {
                    "state": "refused", "code": "probe-failed", "detail": str(error),
                    "window": FREEBUFF, "digest": "", "changed": False,
                    "at": iso(), "age": 0,
                }
                self.harness = {
                    "state": "refused", "code": "harness-unprobed",
                    "detail": f"the cua-chat textbox probe failed: {str(error)[:180]}",
                    "digest": "", "changed": False, "at": "", "typing_at": "", "age": 0,
                }
                self._line("chat probe · probe-failed — " + str(error), "refused")
                self.revision += 1
            return dict(self.probe)

        previous = self.probe.get("digest")
        changed = bool(previous and previous != shot["digest"]) or not previous
        regions = shot.get("regions") or {}
        textbox = regions.get("textbox") or shot.get("textbox") or {}
        history = regions.get("history") or {}
        working = regions.get("working") or {}
        typing = bool(textbox.get("changed"))
        with self.lock:
            self.capture_path = pathlib.Path(shot["path"])
            self.capture_ts = int(time.time() * 1000)
            if textbox.get("path"):
                self.harness_path = pathlib.Path(textbox["path"])
            if history.get("path"):
                self.harness_history_path = pathlib.Path(history["path"])
            if working.get("path"):
                self.harness_working_path = pathlib.Path(working["path"])
            complete = bool(textbox.get("digest") and history.get("digest") and working.get("digest"))
            self.harness = {
                "state": "live" if complete else "refused",
                "code": "" if complete else "harness-region-missing",
                "detail": "Freebuff history, working area and textbox probed" if complete
                          else "the cua-chat capture did not contain all three harness regions",
                "digest": textbox.get("digest", ""), "changed": typing,
                "delta": textbox.get("delta"), "at": shot["at"],
                "history_digest": history.get("digest", ""),
                "working_digest": working.get("digest", ""),
                "regions": {name: {"box": value.get("box"), "digest": value.get("digest"),
                                    "width": value.get("width"), "height": value.get("height")}
                            for name, value in regions.items()},
                "typing_at": shot["at"] if typing else self.harness.get("typing_at", ""),
                "width": textbox.get("width"), "height": textbox.get("height"),
                "age": 0,
            }
            self.probe = {
                "state": "live", "code": "", "detail": "",
                "window": shot["window"]["title"],
                "hwnd": shot["window"]["hwnd"],
                "width": shot["width"], "height": shot["height"],
                "digest": shot["digest"], "changed": changed,
                "at": shot["at"], "age": 0,
            }
            if changed:
                self._line(
                    f"chat capture {shot['width']}×{shot['height']} · {shot['digest']}",
                    "ok",
                )
            self.revision += 1
        return dict(self.probe)

    def state(self) -> dict:
        with self.lock:
            probe = dict(self.probe)
            if probe.get("at"):
                try:
                    moment = datetime.datetime.fromisoformat(probe["at"])
                    probe["age"] = int((datetime.datetime.now(datetime.timezone.utc) - moment).total_seconds())
                except ValueError:
                    probe["age"] = None
            harness = dict(self.harness)
            if harness.get("at"):
                try:
                    moment = datetime.datetime.fromisoformat(harness["at"])
                    age = int((datetime.datetime.now(datetime.timezone.utc) - moment).total_seconds())
                    harness["age"] = age
                    if harness.get("state") == "live" and age > max(8.0, self.probe_seconds * 3.0):
                        harness["state"] = "refused"
                        harness["code"] = "harness-unprobed"
                        harness["detail"] = f"the Freebuff harness textbox was last probed {age}s ago"
                except ValueError:
                    harness["age"] = None
            if self.harness_path:
                harness["path"] = str(self.harness_path)
            fleet = self.fleet.state()
            return {
                "schema": SCHEMA,
                "revision": self.revision,
                "at": iso(),
                "probe": probe,
                "harness": harness,
                "capture_ts": self.capture_ts,
                "lines": list(self.lines),
                "fleet": fleet,
                "voice": self.voice.state(),
                "mic": self.mic.state_dict(),
                "axis": self.axis.state_dict(),
                "debian": self.debian.state_dict(),
                "mind": self.mind.state_dict(),
                "archive": self.archive.state(),
                "debian_window": self.window.state_dict(),
                "dialin": self.dialin.state(),
                "settings_package": self.settings.state(),
                "app_packages": self.apps.state(),
                "external": self.external.state(),
                "civilians": self.civilians.state(),
                "calls": self.calls.state(),
                "bridge": self.bridge.state(),
                "bridge_ledger": self.bridge_ledger.state()["counters"],
                "lanes": self.lane_state(),
                "call": self.call,
                "working": self.working > 0,
                "responders": list(self.responders),
                "lane_threads": [{"name": name, **row}
                                   for name, row in self.lane_states.items()],
                "live": self.live,
                "pending": dict(self.pending),
            }

    def bridge_health(self) -> dict:
        """The heartbeat the tunnel supervisor reads back through Debian.

        A change in the bridge's state is written to the archive here: a bridge that went
        down is a failure with a code and a time, not a panel that quietly stopped.
        """
        state = self.bridge.state()
        seen = getattr(self, "_bridge_seen", "")
        if state.get("state") != seen:
            self._bridge_seen = state.get("state")
            self.archive.add(
                "event", f"bridge {state.get('state')} · {state.get('detail') or 'no detail'}"[:300],
                role="bridge", state=state.get("state"), port=state.get("port"),
                restarts=state.get("restarts"),
            )
        return {"ok": True, "schema": bridge_mod.SCHEMA,
                "bridge": self.bridge.state(),
                "ledger": self.bridge_ledger.state(),
                "toast": {"at": iso(), "revision": self.revision},
                "drivers": self.fleet.state()["drivers"]}

    def bridge_receipt(self, task_id: str) -> dict:
        try:
            task = self.task(task_id)
        except cua.Refused as error:
            row = self.bridge_ledger.by_task(task_id)
            if row and row.get("receipt"):
                return {"ok": True, "task": row["receipt"], "source": "ledger",
                        "counters": self.bridge_ledger.state()["counters"]}
            return {"ok": False, "refused": error.as_dict()}
        return {"ok": True, "task": task, "source": "fleet",
                "counters": self.bridge_ledger.state()["counters"]}

    def bridge_cua(self, body: dict) -> dict:
        """One idempotent act from the Debian side: key, sequence, then a real receipt.

        The key is checked before the fleet is touched, so a retry after a tunnel flap
        returns the first receipt. A new key must carry a sequence above this client's
        last one, so a spooled replay cannot reorder acts.
        """
        key = str(body.get("key") or "")
        actions = body.get("actions")
        if not isinstance(actions, list) or not actions:
            raise bridge_mod.Refused("bridge-actions", "actions must be a non-empty list")
        seq = body.get("seq")
        try:
            seq = int(seq) if seq is not None else None
        except (TypeError, ValueError):
            raise bridge_mod.Refused("bridge-seq", str(seq)[:40]) from None
        client = str(body.get("client") or "debian")[:60]
        driver = str(body.get("driver") or "")
        digest = hashlib.sha256(
            json.dumps(actions, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        held = self.bridge_ledger.accept(key, "/api/bridge/cua", digest,
                                         seq=seq, client=client)
        if held:
            # The receipt survives a toast restart in the ledger, so a replay after one
            # still answers with what the driver did instead of `task-not-found`.
            try:
                task = self.task(str(held.get("task") or ""))
                source = "fleet"
            except cua.Refused:
                task = dict(held.get("receipt") or {
                    "id": held.get("task") or "", "status": held.get("status") or "done"})
                source = "ledger"
            return {"ok": True, "replayed": True, "key": key, "task": task,
                    "source": source}
        task = self.fleet.submit(actions, driver, announce=bool(body.get("announce")),
                                 key=key)
        self.bridge_ledger.record(key, "/api/bridge/cua", digest, task=task,
                                  seq=seq, client=client)
        try:
            wait = float(body.get("wait") or 12.0)
        except (TypeError, ValueError):
            wait = 12.0
        try:
            receipt = self.fleet.wait(task["id"], timeout=min(30.0, max(0.5, wait)))
        except cua.Refused:
            receipt = task  # still running; the receipt route answers it later by id
        self.bridge_ledger.settle(key, receipt)
        self.archive.add("tool", f"bridge act {key} {receipt.get('status')}", role="bridge",
                         task=task["id"], key=key, client=client,
                         refused=receipt.get("refusal") or None)
        return {"ok": True, "replayed": bool(task.get("replayed")), "key": key,
                "task": receipt, "bridge": self.bridge.state()}

    def delegate(self, body: dict) -> dict:
        actions = body.get("actions")
        driver = str(body.get("driver") or "")
        task = self.fleet.submit(actions, driver, announce=bool(body.get("announce")),
                                 key=str(body.get("key") or ""))
        try:
            wait = float(body.get("wait") or 0)
        except (TypeError, ValueError):
            wait = 0.0
        if wait > 0:
            # The caller asked for the receipt, not the id. A task still running after the
            # wait returns as `running` rather than being reported as done.
            try:
                return self.fleet.wait(task["id"], timeout=min(30.0, wait))
            except cua.Refused:
                return task
        return task

    def task(self, task_id: str) -> dict:
        with self.fleet.lock:
            task = next((item for item in self.fleet.tasks if item.id == task_id), None)
            if task is None:
                raise cua.Refused("task-not-found", task_id)
            return task.as_dict()


# The delivered window audits itself. The shell loads the page into the window it already
# shows with the audit flag; that page measures its own surface and posts the report to
# /api/toast/ui-audit. A route that typed "passed" here would be a lie, so this only opens a
# surface and records what the window measured.
# One family prose pass at a time, started by the prose app's own button. A second request
# inside the window replays instead of starting a second pass over every project.
PROSE_RUN = {"at": 0.0, "pid": 0}


def prose_run() -> dict:
    """Start `tools/prose_family.py run` in the background and say which process carries it."""
    import subprocess
    import sys
    import time
    now = time.time()
    pid = int(PROSE_RUN.get("pid") or 0)
    if now - float(PROSE_RUN.get("at") or 0) < 20 and pid:
        return {"ok": True, "started": False, "pid": pid,
                "detail": "a pass started less than twenty seconds ago"}
    log = ROOT / "runlogs" / "prose" / "run.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen([sys.executable, str(ROOT / "tools" / "prose_family.py"), "run"],
                                   cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        handle.close()
    PROSE_RUN.update({"at": now, "pid": process.pid})
    return {"ok": True, "started": True, "pid": process.pid}


WINDOW_AUDIT_ROUTES = {
    "dialin": "/toast.html?uiaudit=1&app=dialin",
    "settings": "/toast.html?window=settings&uiaudit=1&app=settings",
    # The prose app is the settings window's page in its prose mode, so its audit opens the
    # window the owner opens, not a page beside it.
    "prose": "/toast.html?window=prose&uiaudit=1&app=prose",
    # The two rebuilt apps are the settings window's page in their own modes, so each audit
    # opens the window the owner opens.
    "archive": "/toast.html?window=archive&uiaudit=1&app=archive",
    "evidence": "/toast.html?window=evidence&uiaudit=1&app=evidence",
    # The SpringBoard is measured as its own signed app, top level in the shell's window: never
    # by reading it through the frame it is delivered in.
    "springboard": "/phone.html?embedded=1&uiaudit=1&app=springboard",
    "bridge": "/bridge.html?uiaudit=1&app=bridge",
    # No springboard route: the home is only ever the frame inside this window, so it is
    # measured there rather than loaded as a page of its own.
    "desk": "/toast.html",
}
WINDOW_QUEUE: list[tuple] = []
WINDOW_VIEW: dict = {}
# Measurement runs in a second, hidden view loaded from the same signed origin. A probe that
# acts — repainting a frame, refusing a package, navigating an audit route — must act there:
# the desk the owner is working in is not a test fixture, and a probe that changes it is a
# defect the owner has now hit twice.
# What the owner's own window says about itself, pushed by that window. A probe reads the hidden
# measurement view; the desk is read from here, so measuring never has to touch it.
WINDOW_REPORT: dict = {}
WINDOW_RESULTS: dict = {}
WINDOW_EVAL_SEQ: list[int] = [0]
WINDOW_PROBES = ("springboard", "springboardState", "springboardTiles", "goHome",
                 "springboardAudit", "frameIntegrity",
                 "prose", "archive", "evidence", "home", "openApp", "windowClose",
                 "windowState", "paint", "fallback", "choose")


def queue_window(item: tuple) -> bool:
    """Queue an act for the delivered window; a window that is not up refuses by name."""
    if not WINDOW_VIEW.get("view"):
        return False
    WINDOW_QUEUE.append(item)
    return True


def window_audit(route: str) -> bool:
    return queue_window(("route", route, ""))


# Probes that change the page they run in. The desk is the owner's working window, so an acting
# probe is refused against it by name: measurement reads the desk (the window reports its own
# paint) and an act gets a measurement window of its own. The owner has been repainted by a
# "choose" probe twice; this is the refusal that stops a third.
ACTING_PROBES = ("choose", "fallback", "goHome", "openApp", "windowClose")


def window_eval(name: str, argument: object = None) -> str:
    """Ask the window to perform one of its named probes; the answer is kept under the id."""
    WINDOW_EVAL_SEQ[0] += 1
    key = f"{name}-{WINDOW_EVAL_SEQ[0]}"
    WINDOW_RESULTS[key] = {"state": "queued", "value": None, "at": None}
    if name in ACTING_PROBES:
        WINDOW_RESULTS[key] = {"state": "refused", "value": None, "at": time.time(),
                               "refused": "probe-act-needs-measurement-window",
                               "detail": f"{name} changes the page; the desk is not a fixture"}
        print(f"toast-probe refused {key} probe-act-needs-measurement-window", flush=True)
        return key
    if not queue_window(("eval", key, name, argument)):
        WINDOW_RESULTS[key] = {"state": "window-absent", "value": None, "at": None}
    return key


APP_PAGE_CACHE: dict[str, tuple[tuple, bytes]] = {}


def app_page(name: str, entry: str, apps) -> bytes:
    """The delivered page for one window: the settings base with the app's body slot.

    Cached on the files' own stamps and the app's identity, so an edit or a new signed revision
    is what the window is served next; nothing here answers from a page the files no longer say.
    """
    base = UI / app_base.SETTINGS_PAGE
    page = UI / entry
    identity = ""
    try:
        identity = str((apps.state().get("apps") or {}).get(name, {}).get("identity") or "")
    except Exception:  # noqa: BLE001 - an app state that cannot answer is not an identity
        identity = ""
    key = (base.stat().st_mtime_ns, page.stat().st_mtime_ns, identity)
    held = APP_PAGE_CACHE.get(name)
    if held and held[0] == key:
        return held[1]
    body = app_base.render(base.read_text(encoding="utf-8"),
                           page.read_text(encoding="utf-8"), identity).encode("utf-8")
    APP_PAGE_CACHE[name] = (key, body)
    return body


class Handler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        """Serve TLS per connection, in this worker thread.

        The listener used to be wrapped once, so the handshake ran in the accept loop: a client
        that refused the certificate (a second renderer, a probe storm) held the loop and the
        desk's own view could not reach the origin it is delivered from, which is how the desk
        died. A handshake per worker thread isolates one bad client, and a short socket timeout
        keeps a silent one from holding a thread forever.
        """
        context = getattr(self.server, "ssl_context", None)
        if context is not None:
            try:
                self.request.settimeout(15)
                self.request = context.wrap_socket(self.request, server_side=True)
                self.request.settimeout(30)
            except (ssl.SSLError, OSError) as error:
                print(f"popit-tls handshake refused · {error.__class__.__name__}", flush=True)
                raise
        super().setup()

    server_version = "popit-toast/1"

    def log_message(self, fmt, *args):  # the toast log is its own file
        pass

    def send_body(self, body: bytes, kind: str = "application/json", code: int = 200,
                  filename: str = "") -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("X-Content-Type-Options", "nosniff")
        if getattr(self, "_set_archive_cookie", False):
            self.send_header("Set-Cookie",
                             f"popit_archive={self.server.archive_token}; Path=/; HttpOnly; SameSite=Strict")
        if getattr(self, "_desk_cookie", None) is not None:
            self.send_header("Set-Cookie", self._desk_cookie)
        self.end_headers()
        self.wfile.write(body)

    def archive_allowed(self, path: str) -> bool:
        """The Debian listener is token-gated; the loopback listener is not."""
        if not getattr(self.server, "archive", False):
            return True
        query = urlsplit(self.path).query
        token = self.server.archive_token
        if f"token={token}" in query:
            self._set_archive_cookie = True
            return True
        from http.cookies import SimpleCookie
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            return False
        value = cookie.get("popit_archive")
        if value is not None and secrets.compare_digest(value.value, token):
            return True
        return False

    def json(self, value: object, code: int = 200) -> None:
        self.send_body(json.dumps(value).encode("utf-8"), "application/json", code)

    SIGNIN_PUBLIC = ("/signin.html", "/signin.js", "/signin.css",
                     "/api/toast/signin", "/api/toast/signout", "/api/toast/signin/state",
                     "/popit-cert.pem", "/popit-cert.cer",
                     "/popit-icon.svg", "/popit-icon-512.png")

    def remote_allowed(self, path: str) -> bool:
        """The remote listener answers a signed-in browser, and nothing else.

        This gate belongs to the surface a tunnel exposes to the internet. The loopback desk
        and the phone's own LAN origin are unchanged: they are the owner's own network, and
        the desk window must keep loading without a second login.
        """
        if not getattr(self.server, "remote", False):
            return True
        if path in self.SIGNIN_PUBLIC:
            return True
        session = desk_auth.session_for(DESK_STORE, self.headers.get("Cookie") or "")
        self.desk_session = session
        return session is not None

    def remote_refusal(self, path: str) -> None:
        wants_json = (path.startswith("/api/")
                      or "application/json" in (self.headers.get("Accept") or "")
                      or self.headers.get("X-Popit-Desk") == "json")
        if wants_json:
            return self.json({"ok": False, "refused": "desk-signin-required",
                              "detail": "sign in at /signin.html"}, 401)
        target = self.path if self.path.startswith("/") and not self.path.startswith("//") \
            else "/toast.html"
        self.send_response(302)
        self.send_header("Location", "/signin.html?next=" + quote(target, safe=""))
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        path = urlsplit(self.path).path
        toast: Toast = self.server.toast
        if not self.archive_allowed(path):
            return self.json({"ok": False, "refused": "archive-token"}, 403)
        if not self.remote_allowed(path):
            return self.remote_refusal(path)
        if path.startswith("/api/toast/prose/stage/"):
            # The prose program's staging bundle: the driver pulls a project's prose over the
            # shell's own origin, so the transfer names the shell instead of a second server.
            if not getattr(self.server, "tls", False) and self.client_address[0] not in ("127.0.0.1", "::1"):
                return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
            name = path.rsplit("/", 1)[-1]
            suffix = ".tar.gz" if name.endswith(".tar.gz") else ".json" if name.endswith(".json") else ""
            stem = name[:-len(suffix)] if suffix else ""
            if not stem or not all(char.isalnum() or char in "-_" for char in stem):
                return self.json({"ok": False, "refused": "prose-stage-name"}, 404)
            target = ROOT / "runlogs" / "prose" / "stage" / (stem + suffix)
            if not target.is_file():
                return self.json({"ok": False, "refused": "prose-stage-absent", "detail": stem}, 404)
            kind = "application/gzip" if suffix == ".tar.gz" else "application/json"
            return self.send_body(target.read_bytes(), kind, 200, name)
        if path in ("/api/toast/prose/report.json", "/api/toast/prose/progress.json"):
            # The prose app reads the family's receipts through the shell; the page holds no
            # clock and no reading of its own.
            report = path.endswith("report.json")
            target = (ROOT / "artifacts" / "receipts" / "prose-family.json") if report \
                else (ROOT / "runlogs" / "prose" / "progress.json")
            if not target.is_file():
                return self.json({"schema": "popit.prose-family/1", "rows": [], "state": "not-run"})
            return self.send_body(target.read_bytes(), "application/json", 200, target.name)
        if path.startswith("/api/toast/prose/doc/"):
            project = path.rsplit("/", 1)[-1]
            target = ROOT / "docs" / "prose" / project / "index.html"
            if not project or not all(char.isalnum() or char in "-_" for char in project) \
                    or not target.is_file():
                return self.json({"ok": False, "refused": "prose-doc-absent", "detail": project[:60]}, 404)
            return self.send_body(target.read_bytes(), "text/html; charset=utf-8", 200, "index.html")
        if path == "/api/toast/session":
            return self.json(session_archive.state())
        if path == "/api/toast/session/files":
            query = parse_qs(urlsplit(self.path).query)
            try:
                return self.json(session_archive.files((query.get("slug") or [""])[0]))
            except session_archive.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
        if path == "/api/toast/window/report":
            if not WINDOW_REPORT:
                return self.json({"ok": False, "refused": "window-report-absent"}, 404)
            return self.json({"ok": True, "report": WINDOW_REPORT})
        if path == "/api/toast/window/eval":
            key = (parse_qs(urlsplit(self.path).query).get("id") or [""])[0]
            result = WINDOW_RESULTS.get(key)
            if not result:
                return self.json({"ok": False, "refused": "window-eval-id"}, 404)
            if result.get("state") == "refused":
                return self.json({"ok": False, "state": "refused",
                                  "refused": result.get("refused", "probe-refused"),
                                  "detail": result.get("detail", "")}, 409)
            if result.get("state") != "measured":
                return self.json({"ok": False, "state": result.get("state")}, 202)
            return self.json({"ok": True, "state": "measured", "value": result.get("value")})
        if path == "/api/toast/signin/state":
            session = desk_auth.session_for(DESK_STORE, self.headers.get("Cookie") or "")
            return self.json({"ok": True, "signed_in": bool(session),
                              "caller": (session or {}).get("caller", ""),
                              "expires": (session or {}).get("expires", ""),
                              "remote": bool(getattr(self.server, "remote", False))})
        if path == "/signin.html":
            return self.file("signin.html", "text/html; charset=utf-8")
        if path == "/signin.js":
            return self.file("signin.js", "text/javascript; charset=utf-8")
        if path == "/signin.css":
            return self.file("signin.css", "text/css; charset=utf-8")
        if path == "/":
            # The home is never a page of its own: it is the signed SpringBoard app delivered in
            # the agent window. A bare home is the fake surface, so the bare route is the desk.
            self.send_response(302)
            self.send_header("Location", "/toast.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/toast.html":
            # The dialin window is the settings window's document with the desk's body in its
            # body slot: a mutation of the signed baseline, not a page of its own that merely
            # links the same sheets.
            try:
                return self.send_body(app_page("dialin", "toast.html", toast.apps),
                                      "text/html; charset=utf-8")
            except app_package.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
        if path == "/ui-audit.js":
            return self.file("ui-audit.js", "text/javascript; charset=utf-8")
        if path == "/chrome.js":
            # Every window's bar carries this: a window whose own script did not take it still
            # answers settings, home and close, and an empty surface returns to the springboard.
            return self.file("chrome.js", "text/javascript; charset=utf-8")
        if path == "/toast.js":
            return self.file("toast.js", "text/javascript; charset=utf-8")
        if path == "/toast.css":
            return self.file("toast.css", "text/css; charset=utf-8")
        if path == "/controls.css":
            # The pinned control baseline, generated from the package's own record: every app
            # links this instead of authoring a button of its own.
            return self.send_body(app_base.controls_css().encode("utf-8"),
                                  "text/css; charset=utf-8")
        if path == "/settings.html":
            # The settings window is the delivered window: its own signed page, opened in its
            # own named window, and the package every app subscribes to for its look.
            return self.file("settings.html", "text/html; charset=utf-8")
        if path == "/bridge.html":
            try:
                return self.file("bridge.html", "text/html; charset=utf-8")
            except app_package.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
        if path == "/settings.js":
            return self.file("settings.js", "text/javascript; charset=utf-8")
        if path == "/settings.css":
            return self.file("settings.css", "text/css; charset=utf-8")
        if path == "/manifest.webmanifest":
            return self.file("manifest.webmanifest", "application/manifest+json; charset=utf-8")
        if path == "/popit-icon.svg":
            return self.file("popit-icon.svg", "image/svg+xml")
        if path == "/popit-icon-512.png":
            return self.file("popit-icon-512.png", "image/png")
        if path in ("/popit-cert.pem", "/popit-cert.cer"):
            if not PHONE_CERT.exists():
                return self.json({"ok": False, "refused": "phone-cert-absent"}, 404)
            try:
                body = ssl.PEM_cert_to_DER_cert(PHONE_CERT.read_text(encoding="ascii"))
            except (OSError, ValueError) as error:
                return self.json({"ok": False, "refused": "phone-cert-invalid",
                                  "detail": str(error)[:160]}, 500)
            return self.send_body(body, "application/x-x509-ca-cert", 200, "popit-cert.cer")
        if path in ("/phone", "/phone.html"):
            # Only the window's own delivery may load the home. A top-level request for it is
            # the refused fake SpringBoard, named rather than served.
            query = parse_qs(urlsplit(self.path).query)
            if not query.get("embedded"):
                return self.json({"ok": False, "refused": "springboard-standalone-refused",
                                  "detail": "the home is delivered in the agent window; "
                                            "request it with embedded=1 from that frame"}, 409)
            return self.file("phone.html", "text/html; charset=utf-8")
        if path == "/phone.css":
            return self.file("phone.css", "text/css; charset=utf-8")
        if path == "/phone.js":
            return self.file("phone.js", "text/javascript; charset=utf-8")
        if path == "/phone-calls.js":
            return self.file("phone-calls.js", "text/javascript; charset=utf-8")
        if path == "/agent-line.html":
            return self.file("agent-line.html", "text/html; charset=utf-8")
        if path == "/agent-line.js":
            return self.file("agent-line.js", "text/javascript; charset=utf-8")
        if path == "/agent-line.css":
            return self.file("agent-line.css", "text/css; charset=utf-8")
        if path == "/phone-sw.js":
            return self.file("phone-sw.js", "text/javascript; charset=utf-8")
        if path == "/phone-manifest.webmanifest":
            return self.file("phone-manifest.webmanifest", "application/manifest+json; charset=utf-8")
        if path == "/popit-sw.js":
            return self.file("popit-sw.js", "text/javascript; charset=utf-8")
        if path in ("/bridge", "/bridge.html"):
            return self.file("bridge.html", "text/html; charset=utf-8")
        if path == "/bridge.js":
            return self.file("bridge.js", "text/javascript; charset=utf-8")
        if path == "/contour.js":
            return self.file("contour.js", "text/javascript; charset=utf-8")
        if path == "/package.js":
            return self.file("package.js", "text/javascript; charset=utf-8")
        if path == "/contour-theme.css":
            return self.file("contour-theme.css", "text/css; charset=utf-8")
        if path == "/contour.json":
            return self.send_body((ROOT / "contour.json").read_bytes(), "application/json")
        if path == "/family-roster.json":
            return self.file("family-roster.json", "application/json; charset=utf-8")
        if path == "/popit-pairs.json":
            return self.file("popit-pairs.json", "application/json; charset=utf-8")
        if path == "/api/toast/settings":
            return self.json(toast.settings.state())
        if path == "/api/toast/settings/package":
            try:
                return self.json(toast.settings.package_document())
            except settings_package.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
        if path == "/api/toast/bridge":
            return self.json(bridge_state())
        if path == "/api/toast/apps":
            return self.json(toast.apps.state())
        if path.startswith("/api/toast/apps/"):
            try:
                return self.json(toast.apps.document(path.rsplit("/", 1)[-1]))
            except app_package.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
        if path == "/api/bridge/health":
            return self.json(toast.bridge_health())
        if path.startswith("/api/bridge/receipt/"):
            payload = toast.bridge_receipt(path.rsplit("/", 1)[-1])
            return self.json(payload, 200 if payload.get("ok") else 404)
        if path == "/api/toast":
            return self.json(toast.state())
        if path == "/api/toast/civilians":
            return self.json({"ok": True, "civilians": toast.civilians.state()})
        if path == "/api/toast/civilians/scope":
            return self.json({"ok": True, "scope": civilian_scope.state()})
        if path == "/api/toast/external/contacts":
            return self.json({"ok": True, "contacts": toast.external.contacts()})
        if path == "/api/toast/external/incoming":
            return self.json({"ok": True, "calls": toast.external.incoming()})
        if path == "/api/toast/civilian/life":
            lane = (parse_qs(urlsplit(self.path).query).get("lane") or [""])[0]
            return self.json({"ok": True, "life": toast.civilians.life_state(lane)})
        if path == "/api/toast/civilian/resume":
            # What a civilian has held and earned: the brief's resume plane, read by lane.
            lane = (parse_qs(urlsplit(self.path).query).get("lane") or [""])[0]
            return self.json({"ok": True, "resume": toast.civilians.resume(lane)})
        if path == "/api/toast/events":
            # Lightspeed transport: one persistent same-origin stream instead of a
            # one-second poll between the owner's voice and the toast surface.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                while True:
                    payload = json.dumps(toast.state(), ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.28)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
        if path == "/api/toast/capture.png":
            with toast.lock:
                target = toast.capture_path
            if not target or not target.exists():
                return self.json({"ok": False, "refused": "capture-absent"}, 404)
            return self.send_body(target.read_bytes(), "image/png")
        if path == "/api/toast/harness.png":
            with toast.lock:
                target = toast.harness_path
            if not target or not target.exists():
                return self.json({"ok": False, "refused": "harness-textbox-absent"}, 404)
            return self.send_body(target.read_bytes(), "image/png")
        if path in ("/api/toast/harness/history.png", "/api/toast/harness/working.png"):
            with toast.lock:
                target = (toast.harness_history_path if path.endswith("history.png")
                          else toast.harness_working_path)
            if not target or not target.exists():
                return self.json({"ok": False, "refused": "harness-region-absent"}, 404)
            return self.send_body(target.read_bytes(), "image/png")
        if path == "/api/toast/debian.png":
            body = toast.debian.snapshot()
            if not body:
                return self.json({"ok": False, "refused": "debian-capture-absent"}, 404)
            return self.send_body(body, "image/png")
        if path.startswith("/api/toast/task/"):
            try:
                return self.json(toast.task(path.rsplit("/", 1)[-1]))
            except cua.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 404)
        return self.json({"ok": False, "refused": "not-found"}, 404)

    def file(self, name: str, kind: str) -> None:
        target = UI / name
        if not target.exists():
            return self.json({"ok": False, "refused": "ui-absent", "detail": name}, 404)
        return self.send_body(target.read_bytes(), kind)

    def do_POST(self):  # noqa: N802
        path = urlsplit(self.path).path
        toast: Toast = self.server.toast
        if not self.archive_allowed(path):
            return self.json({"ok": False, "refused": "archive-token"}, 403)
        if not self.remote_allowed(path):
            return self.remote_refusal(path)
        if path == "/api/toast/signin":
            # The one route a remote browser reaches without a session: it spends a signed
            # desk package or a one-time desk code, and answers with the session cookie.
            body = self.read_json()
            mode = str(body.get("mode") or "envelope")
            try:
                if mode == "code":
                    token, row, session = desk_auth.admit_code(DESK_STORE,
                                                               str(body.get("code") or ""))
                    detail = {"mode": "code", "caller": row.get("caller", "")}
                else:
                    token, admission, session = desk_auth.admit_envelope(
                        DESK_STORE, body.get("envelope"),
                        trust_path=toast.envelope_trust, nonce_path=toast.envelope_nonces)
                    detail = {"mode": "envelope", "caller": admission["caller"],
                              "agent": admission["agent"],
                              "fingerprint": admission["fingerprint"]}
            except desk_auth.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 403)
            self._desk_cookie = desk_auth.cookie_for(token)
            print(f"popit desk sign-in · {detail.get('caller', '')} · {detail['mode']}", flush=True)
            # The session row is returned without its token hash: a browser gets the cookie,
            # never the stored form of it.
            public = {key: value for key, value in session.items() if key != "token"}
            return self.json({"ok": True, "signed_in": True, "session": public, **detail})
        if path == "/api/toast/signout":
            token = desk_auth.token_from(self.headers.get("Cookie") or "")
            session = DESK_STORE.lookup(token) if token else None
            removed = DESK_STORE.revoke(session["id"]) if session else 0
            self._desk_cookie = desk_auth.cookie_clear()
            print("popit desk sign-out", flush=True)
            return self.json({"ok": True, "signed_out": True, "revoked": removed})
        if path == "/api/toast/bridge/run":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self.json({"ok": False, "refused": "bridge-run-body"}, 400)
            return self.json(bridge_run(str((body or {}).get("command") or "")))
        if path == "/api/toast/ui-error":
            # A window's own script error, kept where the shell's log already is.
            try:
                length = int(self.headers.get("Content-Length") or 0)
                report = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                report = {}
            line = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "report": report}, ensure_ascii=False)
            target = ROOT / "runlogs" / "toast" / "ui-errors.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            print(f"toast-ui-error {str(report)[:200]}", flush=True)
            return self.json({"ok": True})
        if path == "/api/toast/window/report":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self.json({"ok": False, "refused": "window-report-body"}, 400)
            paint = (body or {}).get("paint")
            if not isinstance(paint, dict):
                return self.json({"ok": False, "refused": "window-report-paint"}, 400)
            WINDOW_REPORT.clear()
            WINDOW_REPORT.update({"paint": paint, "at": time.time(),
                                  "origin": str((body or {}).get("at") or "")})
            return self.json({"ok": True})
        if path == "/api/toast/window/eval":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self.json({"ok": False, "refused": "window-eval-body"}, 400)
            name = str((body or {}).get("name") or "")
            if name not in WINDOW_PROBES:
                return self.json({"ok": False, "refused": "window-eval-name"}, 400)
            # A probe that performs an act names what it acts on; the argument is JSON, not a
            # fragment spliced into JavaScript.
            argument = (body or {}).get("arg")
            return self.json({"ok": True, "id": window_eval(name, argument), "name": name})
        if path == "/api/toast/window/audit":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self.json({"ok": False, "refused": "window-audit-body"}, 400)
            app = str((body or {}).get("app") or "")
            route = WINDOW_AUDIT_ROUTES.get(app)
            if not route:
                return self.json({"ok": False, "refused": "window-audit-app"}, 400)
            # An audit loads its route in the page it measures, and that page is the owner's
            # desk. The refusal is here so a caller is told no instead of being promised a
            # navigation the window will not perform.
            return self.json({"ok": False, "app": app, "route": route,
                              "refused": "route-needs-measurement-window",
                              "detail": f"{route} would navigate the owner's desk"}, 409)
        if path == "/api/toast/ui-audit":
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self.json({"ok": False, "refused": "ui-audit-body"}, 400)
            app = str((body or {}).get("app") or "")
            report = (body or {}).get("report")
            if not isinstance(report, dict):
                return self.json({"ok": False, "refused": "ui-audit-report"}, 400)
            try:
                row = toast.apps.record_ui_audit(app, report)
            except app_package.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
            # A passing measurement republishes the app it measured, so the shell's
            # identity returns to green without waiting for the next start.
            published = None
            try:
                published = toast.apps.ensure(app)
            except app_package.Refused as error:
                published = {"app": app, "verified": False, "refused": error.as_dict()}
            return self.json({"ok": True, "audit": row, "package": published})
        if path == "/api/toast/phone/audio":
            if not getattr(self.server, "tls", False):
                return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length <= 0 or length > 12 * 1024 * 1024:
                return self.json({"ok": False, "refused": "audio-size"}, 400)
            data = self.rfile.read(length)
            query = parse_qs(urlsplit(self.path).query)
            lane = (query.get("lane") or [""])[0]
            reply = (query.get("reply") or [""])[0].lower() in ("1", "true", "yes")
            return self.json(toast.phone_audio(data, lane or None, reply=reply))
        if path.startswith("/api/toast/phone/"):
            if not getattr(self.server, "tls", False):
                return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
        body = self.read_json()
        if path == "/mcp":
            return self.mcp(body)
        loopback = self.client_address[0] in ("127.0.0.1", "::1")
        try:
            if path == "/api/toast/apps/ensure":
                # Hot reload's signing half: a changed surface is re-signed by this shell's
                # publisher, attributed to the live driver, without restarting the process.
                # A measurement is not implied: a re-signed package carries `ui_audit:
                # pending` until the driver audits the page, and tools/freshness.py names
                # that act instead of letting the audit go stale.
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                return self.json({"ok": True, "apps": toast.apps.ensure_all()})
            if path == "/api/toast/prose/run":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                return self.json(prose_run())
            if path == "/api/toast/apps/verify":
                # The app registry keeps the phone's posture: a signed identity is read
                # over a secure origin, and loopback is the machine itself.
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                return self.json(toast.apps.document(str(body.get("app") or "")))
            if path.startswith("/api/toast/session/"):
                # The two desk apps act through the shell, never through a second server: a
                # mutation is loopback or TLS, and Explorer only opens from this machine.
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                try:
                    if path == "/api/toast/session/backup":
                        slugs = body.get("slugs")
                        result = session_archive.start_backup(
                            [str(item) for item in slugs] if isinstance(slugs, list)
                            else ([str(body["slug"])] if body.get("slug") else []),
                            all_projects=bool(body.get("all")),
                            mode=str(body.get("mode") or "evidence"))
                        return self.json({"ok": True, "result": result})
                    if path == "/api/toast/session/clean":
                        if not body.get("apply"):
                            return self.json({"ok": False, "refused": {
                                "code": "archive-clean-confirm",
                                "detail": "a clean lists the cache trees first; apply removes them"
                            }}, 409)
                        result = session_archive.clean(str(body.get("slug") or ""), True)
                        return self.json({"ok": True, "result": result})
                    if path == "/api/toast/session/rescan":
                        index = session_archive.ensure_index(force=True)
                        return self.json({"ok": True, "result": {
                            "index": index.get("state") or "ready",
                            "building": bool(index.get("building")),
                            "roots": index.get("roots") or []}})
                    if path == "/api/toast/session/show":
                        if not loopback:
                            return self.json({"ok": False,
                                              "refused": "archive-show-loopback"}, 403)
                        result = session_archive.show(
                            str(body.get("slug") or ""),
                            str(body.get("which") or "project"),
                            str(body.get("path") or ""))
                        return self.json({"ok": True, "result": result})
                except session_archive.Refused as error:
                    return self.json({"ok": False, "refused": error.as_dict()}, 409)
                return self.json({"ok": False, "refused": "session-route-unknown"}, 404)
            if path == "/api/toast/external/enrollment":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                row = toast.external.open_enrollment(str(body.get("name") or "external agent"))
                toast.archive.add("event", f"external enrollment opened · {row['name']}",
                                  role="external", enrollment=row["name"],
                                  expires_at=row["expires_at"])
                return self.json({"ok": True, **row})
            if path == "/api/toast/external/enroll":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                row = toast.external.enroll(body)
                toast.archive.add("event", f"external agent enrolled · {row['contact']['name']} · {row['contact']['line']}",
                                  role="external", contact=row["contact"],
                                  workspace=row["workspace"])
                return self.json(row)
            if path == "/api/toast/external/call":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                row = toast.external.open_call(body)
                toast.archive.add("event", f"external call ringing · {row['contact']['name']} · {row['call_id']}",
                                  role="external", call=row["call_id"], contact=row["contact"],
                                  transport="webrtc")
                return self.json(row)
            if path == "/api/toast/external/call/answer":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                row = toast.external.answer(body)
                toast.archive.add("event", f"external call answered · {row['call_id']}",
                                  role="external", call=row["call_id"], state=row["state"])
                return self.json(row)
            if path == "/api/toast/external/call/consent":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                row = toast.external.consent(body)
                shared = ", ".join(row["consent"]["scopes"]) or "nothing shared"
                toast.archive.add("event", f"external call consent · {row['call_id']} · {shared}",
                                  role="external", call=row["call_id"], consent=row["consent"])
                return self.json(row)
            if path == "/api/toast/external/call/state":
                return self.json(toast.external.state_for(body))
            if path == "/api/toast/external/call/ice":
                return self.json(toast.external.ice(body))
            if path == "/api/toast/external/call/end":
                row = toast.external.end(body)
                toast.archive.add("event", f"external call {row['state']} · {row['call_id']}",
                                  role="external", call=row["call_id"], state=row["state"])
                return self.json(row)
            if path == "/api/refuse":
                # A surface refused by the contour audit is a row, not a console warning: the
                # audit posts here from every app that runs it.
                code = str(body.get("code") or "surface-refused")[:60]
                surface = str(body.get("surface") or "")[:160]
                toast.archive.add("event", f"surface refused · {code} · {surface}",
                                  role="ui", code=code, surface=surface)
                return self.json({"ok": True, "code": code})
            if path == "/api/bridge/cua":
                return self.json(toast.bridge_cua(body))
            if path == "/api/toast/grab":
                toast.pending["grab"] = True
                return self.json({"ok": True})
            if path == "/api/toast/reload":
                toast.pending["reload"] = True
                return self.json({"ok": True})
            if path == "/api/toast/probe":
                return self.json({"ok": True, "probe": toast.run_probe()})
            if path == "/api/toast/delegate":
                return self.json({"ok": True, "task": toast.delegate(body)})
            if path == "/api/toast/say":
                return self.json({"ok": True,
                                  "voice": toast.voice.say(str(body.get("profile") or "assistant"),
                                                          str(body.get("text") or ""))})
            if path == "/api/toast/wish":
                return self.json({"ok": True, "wish": toast.place_wish(
                    str(body.get("request") or body.get("text") or ""),
                    intent=str(body.get("intent") or "read"),
                    agent=str(body.get("agent") or ""))})
            if path == "/api/toast/ask":
                targets = body.get("targets")
                return self.json({"ok": True,
                                  "mind": toast.ask_mind(str(body.get("text") or ""),
                                                          str(body.get("profile") or "cua-chat"),
                                                          [str(name) for name in targets]
                                                          if isinstance(targets, list) else None)})
            if path == "/api/toast/lanes":
                names = body.get("names")
                if body.get("all"):
                    names = []
                return self.json({"ok": True, "lanes": toast.set_lanes(
                    [str(name) for name in names] if isinstance(names, list) else [])})
            if path == "/api/toast/hear":
                text = str(body.get("text") or "")
                toast._heard(text, typed=True)
                return self.json({"ok": True, "heard": text, "lanes": toast.lane_state()})
            if path == "/api/toast/phone/hear":
                return self.json(toast.phone_heard(str(body.get("text") or ""),
                                                   str(body.get("lane") or "") or None))
            if path == "/api/toast/axis":
                return self.json({"ok": True,
                                  "axis": toast.ask_axis(str(body.get("text") or ""),
                                                          str(body.get("profile") or "cua-chat"))})
            if path == "/api/toast/live":
                toast.live = bool(body.get("on", True))
                return self.json({"ok": True, "live": toast.live})
            if path == "/api/toast/civilian/duration":
                return self.json({"ok": True,
                                  "chain": toast.civilians.duration(str(body.get("text") or ""))})
            if path == "/api/toast/civilian/life/tick":
                opportunities = body.get("opportunities")
                row = toast.civilians.life_tick(
                    str(body.get("lane") or ""),
                    opportunities if isinstance(opportunities, list) else None,
                    apply_care=bool(body.get("apply_care")),
                )
                toast.archive.add(
                    "event", f"civilian life · {body.get('lane') or ''} · {row['decision'].get('kind')} · {row['decision'].get('reason', '')[:120]}",
                    role="civilian", decision=row["decision"], life=row["life"],
                )
                return self.json({"ok": True, **row})
            if path == "/api/toast/civilian/life/apply":
                decision = body.get("decision")
                if not isinstance(decision, dict):
                    raise civilian_features.Refused("civilian-decision", "decision must be an object")
                life = toast.civilians.life_apply(str(body.get("lane") or ""), decision)
                return self.json({"ok": True, "life": life})
            if path == "/api/toast/civilian/retire":
                row = toast.civilians.retire(str(body.get("lane") or ""),
                                             str(body.get("reason") or ""),
                                             evidence=str(body.get("evidence") or ""))
                toast.archive.add(
                    "event", f"civilian retired · {row['lane']} · {row['reason']}",
                    role="civilian", lane=row["lane"], grade=row.get("grade") or "",
                    evidence=row.get("evidence") or "",
                )
                return self.json({"ok": True, "retired": row})
            if path == "/api/toast/civilian/reinstate":
                row = toast.civilians.reinstate(
                    str(body.get("lane") or ""),
                    reason=str(body.get("reason") or ""),
                    evidence=str(body.get("evidence") or ""),
                    by=str(body.get("by") or "owner"),
                )
                toast.archive.add(
                    "event", f"civilian reinstated · {row['lane']} · {row['reason']}",
                    role="civilian", lane=row["lane"], retirement=row.get("retirement") or {},
                )
                return self.json({"ok": True, "reinstated": row})
            if path == "/api/toast/civilian/promote":
                evidence = body.get("evidence")
                row = toast.civilians.promote(
                    str(body.get("lane") or ""), str(body.get("grade") or ""),
                    evidence=evidence if isinstance(evidence, list) else [],
                    by=str(body.get("by") or "owner"),
                )
                toast.archive.add(
                    "event", f"civilian grade · {row['lane']} · {row['grade']}",
                    role="civilian", lane=row["lane"], grade=row["grade"],
                    evidence=row.get("evidence") or [],
                )
                return self.json({"ok": True, "grade": row})
            if path == "/api/toast/civilian/life/steps":
                decision = body.get("decision")
                if not isinstance(decision, dict):
                    raise civilian_features.Refused("civilian-decision", "decision must be an object")
                steps = toast.civilians.life_steps(str(body.get("lane") or ""), decision)
                return self.json({"ok": True, "steps": steps})
            if path == "/api/toast/civilian/name":
                row = toast.civilians.name(
                    str(body.get("lane") or ""), str(body.get("primary") or ""),
                    str(body.get("secondary") or ""), str(body.get("tertiary") or ""),
                    confidence=body.get("confidence") or 0.0,
                    source=str(body.get("source") or "human"),
                )
                toast.archive.add("event", f"civilian identity · {row['lane']} · {row['path']}",
                                  role=row["lane"], identity=row)
                return self.json({"ok": True, "identity": row})
            if path == "/api/toast/civilian/decision":
                row = toast.civilians.decide(
                    str(body.get("lane") or ""), str(body.get("kind") or ""),
                    str(body.get("question") or ""), body.get("answer"),
                    confidence=body.get("confidence") or 0.0, act=body.get("act"),
                    ground_truth=str(body.get("ground_truth") or ""),
                    provenance=str(body.get("provenance") or "",),
                )
                if row.get("gate") == "escalate":
                    toast.archive.add("event", f"civilian decision escalated · {row['lane']} · {row['question'][:120]}",
                                      role=row["lane"], decision=row)
                return self.json({"ok": True, "decision": row})
            if path == "/api/toast/civilian/verify":
                try:
                    index = int(body.get("index") if body.get("index") is not None else -1)
                except (TypeError, ValueError):
                    raise civilian_features.Refused("decision-index", "index must be an integer")
                row = toast.civilians.verify(
                    index, str(body.get("ground_truth") or ""),
                    passed=bool(body.get("passed")), detail=str(body.get("detail") or ""),
                )
                return self.json({"ok": True, "decision": row})
            if path == "/api/toast/civilian/contract":
                row = toast.civilians.contract(body.get("contract") or {},
                                                call=str(body.get("call") or ""))
                toast.archive.add("event", f"civilian contract · {row['mission'][:120]}",
                                  role="contract", contract=row)
                return self.json({"ok": True, "contract": row})
            if path == "/api/toast/settings/state":
                held = toast.settings.adopt(body)
                # The desk is the authoring surface and the package is what every other app
                # reads, so a real change publishes. An unchanged push mints no revision.
                try:
                    published = toast.settings.delivery().get("settings") or {}
                except settings_package.Refused:
                    published = {}
                apps: dict = {}
                if held != published:
                    toast.settings.publish()
                    # A real publish moves the base identity; the apps that subscribe to it
                    # are re-signed in the same act, so no window is left app-base-stale.
                    apps = toast.apps.ensure_all()
                return self.json({"ok": True, "settings": held, "apps": apps})
            if path == "/api/toast/settings/publish":
                row = toast.settings.publish(body if isinstance(body, dict) and body else None)
                # The same act re-signs every subscribing app: a new base identity does not
                # leave the windows that read it refused.
                apps = toast.apps.ensure_all()
                return self.json({"ok": True, "identity": row["identity"],
                                  "digest": row["digest"], "revision": row["revision"],
                                  "payload_digest": row["payload_digest"],
                                  "signature": row["signature"],
                                  "published_at": row["published_at"],
                                  "apps": apps})
            if path == "/api/toast/settings/subscribe":
                return self.json({"ok": True, **toast.settings.subscribe(body)})
            if path == "/api/toast/dialin":
                row = toast.dialin.enroll(str(body.get("name") or ""),
                                           str(body.get("role") or "civilian"),
                                           "", str(body.get("kind") or "civilian"))
                row = toast.dialin.dial(row)
                toast.archive.add(
                    "event", f"{row['name']} dialed in · {row['number']}",
                    role=row["name"], civilian=row["name"], number=row["number"],
                    package=row["package_identity"], verified=row["verified"],
                    tones=row["tones"],
                )
                return self.json({"ok": True, "civilian": row})
            if path == "/api/toast/call/participant":
                name = " ".join(str(body.get("name") or "").split())
                if not name:
                    raise calls_mod.Refused("participant-empty", "name a participant")
                row = toast.calls.open(
                    "Alacrity", name, f"talk with {name}",
                    "the participant's spoken reply", 0, allow_multiple=True,
                )
                toast.archive.add(
                    "event", f"call {row['id']} · {name} on the line · {row['minutes']}m",
                    role="call", civilian=row["civilian"], agent=row["agent"],
                    proof=row["proof"], task_id=row["task_id"], call=row["id"],
                )
                toast.begin_call(row)
                return self.json({"ok": True, "call": row})
            if path == "/api/toast/call/open":
                contract = body.get("contract")
                checked = toast.civilians.contract(contract) if isinstance(contract, dict) else None
                try:
                    minutes = int(body.get("minutes") or 5)
                except (TypeError, ValueError):
                    raise calls_mod.Refused("call-minutes", "minutes must be an integer")
                row = toast.calls.open(
                    str(body.get("civilian") or ""), str(body.get("agent") or ""),
                    str(body.get("wish") or ""), str(body.get("proof") or ""),
                    minutes, contract=checked,
                    # The desk runs several lines at once; a host-side caller (a drill, a
                    # callback) says so instead of being refused because one is already open.
                    allow_multiple=bool(body.get("allow_multiple")),
                )
                toast.archive.add(
                    "event", f"wish {row['id']} · {row['civilian']} → {row['agent']} · {row['minutes']}m",
                    role="wish", civilian=row["civilian"], agent=row["agent"],
                    proof=row["proof"], task_id=row["task_id"], call=row["id"],
                )
                toast.begin_call(row, incoming=bool(body.get("incoming")))
                return self.json({"ok": True, "call": row})
            if path == "/api/toast/envelope/admit":
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                package = body.get("envelope")
                if not isinstance(package, dict):
                    raise envelope.Refused("envelope-required",
                                           "POST a signed envelope in the envelope field")
                admission = envelope.admit(
                    package, trust_path=toast.envelope_trust,
                    nonce_path=toast.envelope_nonces,
                )
                toast.archive.add(
                    "event", f"signed envelope admitted · {admission['caller']} · {admission['agent']}",
                    role="envelope", caller=admission["caller"], agent=admission["agent"],
                    fingerprint=admission["fingerprint"], endpoint=admission["endpoint"],
                )
                return self.json({"ok": True, "admission": admission})
            if path == "/api/toast/call/join":
                package = body.get("envelope")
                if not isinstance(package, dict):
                    raise envelope.Refused(
                        "envelope-required",
                        "call.join needs a signed envelope; local MCP uses the /mcp edge",
                    )
                admission = envelope.admit(
                    package, trust_path=toast.envelope_trust,
                    nonce_path=toast.envelope_nonces,
                )
                return self.json({"ok": True, **toast.bridge_join(
                    str(body.get("agent") or admission["agent"]),
                    str(body.get("profile") or "buffy"), admission=admission)})
            if path == "/api/toast/call/turns":
                since = body.get("since")
                return self.json({"ok": True, **toast.bridge_turns(
                    str(body.get("session") or ""),
                    int(since) if since is not None else None,
                    float(body.get("wait") or 0))})
            if path == "/api/toast/call/say":
                return self.json({"ok": True, **toast.bridge_say(
                    str(body.get("session") or ""), str(body.get("text") or ""),
                    speak=bool(body.get("speak", True)))})
            if path == "/api/toast/call/leave":
                return self.json({"ok": True, **toast.bridge_leave(str(body.get("session") or ""))})
            if path == "/api/toast/call/close":
                hangup = bool(body.get("hangup"))
                row = toast.calls.close(str(body.get("id") or ""),
                                          str(body.get("evidence") or ""),
                                          proof=not bool(body.get("hangup")))
                callback_line = str(row.get("wish") or "").startswith("call back after")
                if hangup and callback_line:
                    # A callback that is hung up does not dial again; one hang-up, one ring.
                    toast.archive.add(
                        "call-hangup",
                        f"{row['civilian']} hung up on the callback {row['id']} · no further ring",
                        role="call", call=row["id"], civilian=row["civilian"],
                        agent=row["agent"], evidence=row["evidence"],
                    )
                    return self.json({"ok": True, "call": row, "hangup": True, "callback": None})
                if hangup:
                    # The owner ended the line. That is not a finished wish, and it is not
                    # silence: he hung up, so the lane rings him back and says so.
                    toast.archive.add(
                        "call-hangup",
                        f"{row['civilian']} hung up on {row['agent']} · line {row['id']}",
                        role="call", call=row["id"], civilian=row["civilian"],
                        agent=row["agent"], evidence=row["evidence"],
                    )
                    try:
                        back = toast.call_back(row)
                    except calls_mod.Refused as error:
                        toast.archive.add("event", f"callback refused · {error.code}",
                                         role="call", call=row["id"], agent=row["agent"])
                        return self.json({"ok": True, "call": row, "hangup": True,
                                          "callback": None,
                                          "refused_callback": error.as_dict()})
                    return self.json({"ok": True, "call": row, "hangup": True,
                                      "callback": back})
                toast.archive.add(
                    "event", f"wish {row['id']} closed with proof · {row['evidence']}",
                    role="wish", call=row["id"], civilian=row["civilian"],
                    agent=row["agent"], evidence=row["evidence"],
                )
                return self.json({"ok": True, "call": row})
            if path == "/api/toast/mic":
                on = bool(body.get("on", True))
                return self.json({"ok": True,
                                  "mic": toast.mic.start() if on else toast.mic.stop() or toast.mic.state_dict()})
            if path == "/api/toast/debian/run":
                toast.begin_work()
                try:
                    row = toast.debian.run(str(body.get("command") or ""),
                                           float(body.get("timeout") or 30))
                finally:
                    toast.end_work()
                toast.archive.add("command", str(body.get("command") or ""),
                                  role="command", exit=row.get("exit"),
                                  output=str(row.get("output") or "")[:800])
                return self.json({"ok": bool(row.get("ok")), "run": row})
            if path == "/api/toast/debian/capture":
                return self.json({"ok": True, "capture": toast.debian.capture()})
            if path == "/api/toast/hide":
                toast.pending["hide"] = True
                return self.json({"ok": True})
            if path == "/api/toast/show":
                toast.pending["show"] = True
                return self.json({"ok": True})
            if path == "/api/toast/pin":
                toast.pending["pin"] = bool(body.get("pinned", True))
                return self.json({"ok": True, "pinned": toast.pending["pin"]})
            if path == "/api/toast/close":
                toast.pending["close"] = True
                return self.json({"ok": True})
        except (cua.Refused, voice.Refused, axis_bridge.Refused, debian_view.Refused,
                mind_bridge.Refused, dialin.Refused, calls_mod.Refused,
                civilian_features.Refused, envelope.Refused,
                settings_package.Refused, app_package.Refused,
                external_agents.Refused, bridge_mod.Refused) as error:
            return self.json({"ok": False, "refused": error.as_dict()}, 409)
        return self.json({"ok": False, "refused": "not-found"}, 404)

    def mcp(self, body: dict) -> None:
        """A small MCP tools endpoint over the toast's own loopback service."""
        toast: Toast = self.server.toast
        request_id = body.get("id")
        method = str(body.get("method") or "")
        params = body.get("params") or {}
        tools = [
            {
                "name": "voice.speak", "description": "Speak one line through the host speaker.",
                "inputSchema": {"type": "object", "properties": {
                    "text": {"type": "string"},
                    "profile": {"type": "string", "default": "cua-chat"}},
                    "required": ["text"]},
            },
            {
                "name": "voice.listen", "description": "Start or stop the live microphone.",
                "inputSchema": {"type": "object", "properties": {
                    "on": {"type": "boolean", "default": True}},
                    "required": ["on"]},
            },
            {
                "name": "voice.status", "description": "Read voice queue and microphone state.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "mind.ask", "description": "Ask the Debian Qwen3 tool loop one question.",
                "inputSchema": {"type": "object", "properties": {
                    "text": {"type": "string"}}, "required": ["text"]},
            },
            {
                "name": "debian.command", "description": "Run one agent command on Debian as root.",
                "inputSchema": {"type": "object", "properties": {
                    "command": {"type": "string"}}, "required": ["command"]},
            },
            {
                "name": "axis.ask", "description": "Ask the corpus-attested CUA axis.",
                "inputSchema": {"type": "object", "properties": {
                    "text": {"type": "string"}}, "required": ["text"]},
            },
            {
                "name": "dialin.list", "description": "List civilians, numbers and verified dial-in packages.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "dialin.enroll", "description": "Give a new civilian a name, number and package dial-in.",
                "inputSchema": {"type": "object", "properties": {
                    "name": {"type": "string"}, "role": {"type": "string"}},
                    "required": ["name"]},
            },
            {
                "name": "call.join", "description": "Attach this general agent harness to an open call and receive its session cursor.",
                "inputSchema": {"type": "object", "properties": {
                    "agent": {"type": "string", "default": "Buffy"},
                    "profile": {"type": "string", "default": "buffy"}}},
            },
            {
                "name": "call.turns", "description": "Long-poll the call for owner speech, sibling agents, and call edges since a cursor.",
                "inputSchema": {"type": "object", "properties": {
                    "session": {"type": "string"}, "since": {"type": "integer"},
                    "wait": {"type": "number", "default": 20}},
                    "required": ["session"]},
            },
            {
                "name": "call.say", "description": "Speak and archive a line in the joined call as this agent.",
                "inputSchema": {"type": "object", "properties": {
                    "session": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["session", "text"]},
            },
            {
                "name": "call.leave", "description": "Leave the joined call and return the lane to the local mind.",
                "inputSchema": {"type": "object", "properties": {
                    "session": {"type": "string"}}, "required": ["session"]},
            },
            {
                "name": "toast.state", "description": "Read the full toast state.",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
        if method == "initialize":
            return self.json({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "popit-toast", "version": "1"},
            }})
        if method == "notifications/initialized":
            return self.json({"jsonrpc": "2.0", "id": request_id, "result": {}})
        if method == "tools/list":
            return self.json({"jsonrpc": "2.0", "id": request_id,
                              "result": {"tools": tools}})
        if method == "tools/call":
            name = str(params.get("name") or "")
            args = params.get("arguments") or {}
            try:
                if name == "voice.speak":
                    value = toast.voice.say(str(args.get("profile") or "cua-chat"),
                                            str(args.get("text") or ""))
                elif name == "voice.listen":
                    on = bool(args.get("on", True))
                    value = toast.mic.start() if on else (toast.mic.stop() or toast.mic.state_dict())
                elif name == "voice.status":
                    value = {"voice": toast.voice.state(), "mic": toast.mic.state_dict()}
                elif name == "mind.ask":
                    value = toast.ask_mind(str(args.get("text") or ""))
                elif name == "debian.command":
                    value = toast.debian.run(str(args.get("command") or ""))
                elif name == "axis.ask":
                    value = toast.ask_axis(str(args.get("text") or ""))
                elif name == "dialin.list":
                    value = toast.dialin.state()
                elif name == "dialin.enroll":
                    row = toast.dialin.enroll(str(args.get("name") or ""),
                                              str(args.get("role") or "civilian"))
                    value = toast.dialin.dial(row)
                elif name == "call.join":
                    value = toast.bridge_join(str(args.get("agent") or "Buffy"),
                                              str(args.get("profile") or "buffy"))
                elif name == "call.turns":
                    since = args.get("since")
                    value = toast.bridge_turns(str(args.get("session") or ""),
                                               int(since) if since is not None else None,
                                               float(args.get("wait") or 0))
                elif name == "call.say":
                    value = toast.bridge_say(str(args.get("session") or ""),
                                             str(args.get("text") or ""))
                elif name == "call.leave":
                    value = toast.bridge_leave(str(args.get("session") or ""))
                elif name == "toast.state":
                    value = toast.state()
                else:
                    raise mind_bridge.Refused("mcp-tool-unknown", name)
                return self.json({"jsonrpc": "2.0", "id": request_id, "result": {
                    "content": [{"type": "text",
                                 "text": json.dumps(value, ensure_ascii=False)}],
                    "isError": False,
                }})
            except Exception as error:
                return self.json({"jsonrpc": "2.0", "id": request_id,
                                  "error": {"code": -32000, "message": str(error)}})
        return self.json({"jsonrpc": "2.0", "id": request_id,
                          "error": {"code": -32601, "message": f"unknown method {method}"}})

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 64 * 1024:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}


def lan_address() -> str:
    """The Ethernet address a phone on the same network can dial."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            value = str(probe.getsockname()[0])
        if value and not value.startswith("127."):
            return value
    except OSError:
        pass
    try:
        value = socket.gethostbyname(socket.gethostname())
        return value if value and not value.startswith("127.") else "127.0.0.1"
    except OSError:
        return "127.0.0.1"


def pinned_certificate_sha256() -> str:
    """The fingerprint of the certificate this shell serves, for pinning the app window to it."""
    try:
        der = ssl.PEM_cert_to_DER_cert(PHONE_CERT.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return ""
    if isinstance(der, str):  # older ssl returns DER as text
        der = der.encode("latin-1")
    return hashlib.sha256(der).hexdigest()


def cert_covers_loopback() -> bool:
    """True when the certificate names 127.0.0.1, so the window can load it over TLS."""
    if not PHONE_CERT.exists():
        return False
    try:
        result = subprocess.run([envelope._OPENSSL, "x509", "-in", str(PHONE_CERT),
                                 "-noout", "-text"],
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        # A certificate that could not be read is not read as covering loopback: a failed
        # measurement that answered "yes" is how a certificate with no SAN kept loading a
        # window it could never verify.
        return False
    if result.returncode != 0:
        return False
    return "IP Address:127.0.0.1" in result.stdout


def build_token() -> str:
    """A token over the window's own files, so a launch never runs an older script.

    The window is a page of files that this session edits; a URL that never changes lets the
    engine, a service worker or a cache answer with the previous build, and the window then
    draws code that no longer exists on disk.
    """
    digest = hashlib.sha256()
    for path in sorted((ROOT / "ui").glob("*")):
        if path.suffix not in {".js", ".css", ".html", ".json"} or not path.is_file():
            continue
        stat = path.stat()
        digest.update(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}".encode())
    return digest.hexdigest()[:12]


def app_window_origin(https_server, bind: str, https_port: int,
                      loopback_port: int, window_https=None) -> tuple[str, str]:
    """The origin the desktop window loads: the delivered app package, over TLS.

    There is no bare-http twin. A window served over http has no certificate to pin, so its
    package cannot be proven and its frame cannot be trusted; the earlier fallback to
    `http://127.0.0.1` was a loosening of that rule, and it is removed rather than left as a
    quiet branch. With no TLS listener the origin is empty and every window route refuses by name
    (`window-not-secure`) instead of drawing a window that cannot prove what it is.
    """
    token = build_token()
    if window_https is not None:
        return (f"https://127.0.0.1:{window_https.server_port}/toast.html?v={token}",
                "https-loopback")
    if https_server is not None and bind:
        return f"https://{bind}:{https_port}/toast.html?v={token}", "https"
    # No secure listener: no window. The shape is a refusal, not an http page.
    return "", "window-not-secure"


def ensure_phone_cert(bind: str) -> bool:
    """Generate a local SAN certificate for the phone's secure origin."""
    if PHONE_CERT.exists() and PHONE_KEY.exists() and cert_covers_loopback():
        return True
    PHONE_CERT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        envelope._OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(PHONE_KEY), "-out", str(PHONE_CERT), "-days", "825",
        "-subj", f"/CN={bind}",
        "-addext", f"subjectAltName=IP:{bind},IP:127.0.0.1,DNS:popit.local,DNS:localhost",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"popit phone cert refused · {error}", flush=True)
        return False
    if result.returncode != 0:
        print(f"popit phone cert refused · {result.stderr[-240:]}", flush=True)
        return False
    return True


class PopitHTTPServer(ThreadingHTTPServer):
    """Keep expected phone disconnects out of the server log."""

    def handle_error(self, request, client_address) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (ConnectionResetError, ConnectionAbortedError,
                              BrokenPipeError, ssl.SSLError, ssl.SSLEOFError)):
            return
        super().handle_error(request, client_address)


def serve(toast: Toast, port: int = PORT, *, bind: str = "127.0.0.1",
          archive: bool = False, tls: bool = False,
          remote: bool = False) -> ThreadingHTTPServer:
    server = PopitHTTPServer((bind, port), Handler)
    server.toast = toast
    server.archive = archive
    server.archive_token = toast.window_token
    server.tls = tls
    # The remote listener is the one a tunnel exposes: it answers only a signed-in browser.
    server.remote = remote
    # The first listener is the loopback app server; the IDE window is told to load from it.
    if not getattr(toast, "port", 0):
        toast.port = server.server_port
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(PHONE_CERT), str(PHONE_KEY))
        # The handshake belongs to the connection, not the listener: see Handler.setup.
        server.ssl_context = context
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    # Print never fails on a glyph. A probe value carrying ◉ or ☎ raised UnicodeEncodeError
    # on a cp1252 console, and because that print ran inside a Qt callback the desk died with
    # it: the log is a record of what the window answered, so it is written as UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--probe-seconds", type=float, default=4.0)
    parser.add_argument("--lan-port", type=int, default=5209)
    parser.add_argument("--https-port", type=int, default=5210)
    # The window's own TLS listener on loopback: the delivered app is never the bare-http twin.
    parser.add_argument("--window-https-port", type=int, default=5211)
    parser.add_argument("--lan-bind", default="")
    parser.add_argument("--no-lan", action="store_true")
    parser.add_argument("--no-https", action="store_true")
    # The internet-facing surface: its own TLS listener, answered only after sign-in.
    parser.add_argument("--remote-port", type=int, default=5222)
    parser.add_argument("--remote-bind", default="127.0.0.1")
    parser.add_argument("--no-remote", action="store_true")
    # A launch may open the desk's own window at an app's audit route. The window the owner
    # opens is the app window, so the measurement that signs it is taken there, in the desk's
    # one view, over the origin it pins — never in a page opened beside the app.
    parser.add_argument("--window-route", default="")
    args = parser.parse_args()

    toast = Toast(probe_seconds=args.probe_seconds)
    server = serve(toast, args.port)
    lan_bind = args.lan_bind or lan_address()
    archive_server = serve(toast, 5208, bind=lan_bind, archive=True)
    lan_server = None
    https_server = None
    window_https = None
    if not args.no_lan:
        try:
            lan_server = serve(toast, args.lan_port, bind=lan_bind)
        except OSError as error:
            print(f"popit lan refused · {lan_bind}:{args.lan_port} · {error}", flush=True)
        if not args.no_https:
            if ensure_phone_cert(lan_bind):
                try:
                    https_server = serve(toast, args.https_port, bind=lan_bind, tls=True)
                except (OSError, ssl.SSLError) as error:
                    print(f"popit https refused · {lan_bind}:{args.https_port} · {error}", flush=True)
            else:
                print("popit https refused · a local certificate could not be generated", flush=True)
            # The window loads its own TLS origin, which needs no LAN name to resolve.
            try:
                window_https = serve(toast, args.window_https_port, bind="127.0.0.1",
                                     tls=True)
            except (OSError, ssl.SSLError) as error:
                print(f"popit window https refused · 127.0.0.1:{args.window_https_port} · {error}",
                      flush=True)
    remote_server = None
    if not args.no_remote:
        # A tunnel connects to this listener, not to the phone's own LAN origin: the surface
        # that leaves the network is the one that asks for a signed session.
        if ensure_phone_cert(lan_bind):
            try:
                remote_server = serve(toast, args.remote_port, bind=args.remote_bind,
                                      tls=True, remote=True)
            except (OSError, ssl.SSLError) as error:
                print(f"popit remote refused · {args.remote_bind}:{args.remote_port} · {error}",
                      flush=True)
        else:
            print("popit remote refused · a local certificate could not be generated", flush=True)
    toast.start()
    print(f"popit toast http://127.0.0.1:{server.server_port}/", flush=True)
    if lan_server is not None:
        print(f"popit phone http://{lan_bind}:{args.lan_port}/phone.html", flush=True)
    if https_server is not None:
        print(f"popit phone https://{lan_bind}:{args.https_port}/phone.html", flush=True)
        print(f"popit certificate https://{lan_bind}:{args.https_port}/popit-cert.cer", flush=True)
    if remote_server is not None:
        print(f"popit remote https://{args.remote_bind}:{remote_server.server_port}/signin.html",
              flush=True)
    if args.no_window:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0

    from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QUrl, Slot
    from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap, QPolygon
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon
    from window import contour_region

    shape = json.loads((ROOT / "contour.json").read_text(encoding="utf-8"))
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    QWebEngineProfile.defaultProfile().setHttpCacheType(QWebEngineProfile.NoCache)
    window = QMainWindow()
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                          | Qt.NoDropShadowWindowHint)
    window.setAttribute(Qt.WA_TranslucentBackground, True)
    window.setWindowTitle("Popit toast")
    view = QWebEngineView(window)
    WINDOW_VIEW["view"] = view
    # A hidden second QWebEngineView in this process killed the desk: the window process died
    # every twenty seconds and the watchdog replaced it. The desk holds exactly one view; a
    # measurement that has to act in a page gets its own process instead, never this one.
    # Set once the delivered origin is known: the base a window route is loaded from, and why.
    WINDOW_ORIGIN = {"base": "", "note": ""}

    def pump_window() -> None:
        """Run the act a caller asked the delivered window to perform, if any."""
        if not WINDOW_QUEUE:
            return
        item = WINDOW_QUEUE.pop(0)
        kind, first, name = item[0], item[1], item[2]
        argument = item[3] if len(item) > 3 else None
        if kind == "route":
            # A route act navigates a page. The desk is the owner's working window, so a route
            # act against it is refused by name: an audit runs in its own measurement window.
            base, note = WINDOW_ORIGIN["base"], WINDOW_ORIGIN["note"]
            if note not in ("https", "https-loopback") or not base:
                WINDOW_RESULTS[first] = {"state": "refused", "refused": "window-not-secure",
                                         "detail": f"the app window is {note or 'unbound'}",
                                         "at": time.time()}
                print(f"toast-window route-refused {first} window-not-secure ({note})", flush=True)
                return
            WINDOW_RESULTS[first] = {"state": "refused",
                                     "refused": "route-needs-measurement-window",
                                     "detail": f"{first} would navigate the owner's desk",
                                     "at": time.time()}
            print(f"toast-route-refused {first} route-needs-measurement-window", flush=True)
            return
        call = "window.popitProbe && window.popitProbe[" + json.dumps(name) + "]("
        script = call + ")" if argument is None else call + json.dumps(argument) + ")"

        def keep(value: object) -> None:
            WINDOW_RESULTS[first] = {"state": "measured", "value": value, "at": time.time()}
            print(f"toast-window probe={first} value={value}", flush=True)

        view.page().runJavaScript(script, 0, keep)

    window_pump = QTimer(window)
    window_pump.timeout.connect(pump_window)
    window_pump.start(400)
    view.page().setBackgroundColor(Qt.transparent)

    class WindowBridge(QObject):
        @Slot()
        def begin_drag(self) -> None:
            """Let the HTML header move the real frameless window."""
            try:
                import ctypes
                hwnd = int(window.winId())
                ctypes.windll.user32.ReleaseCapture()
                ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, 2, 0)  # WM_NCLBUTTONDOWN, HTCAPTION
            except Exception as error:
                print(f"toast-drag refused: {error}", flush=True)

        @Slot(str)
        def begin_resize(self, edge: str) -> None:
            """Enter the native resize loop from an HTML grip."""
            hits = {"left": 10, "right": 11, "top": 12, "topleft": 13,
                    "topright": 14, "bottom": 15, "bottomleft": 16,
                    "bottomright": 17}
            key = str(edge).lower()
            hit = hits.get(key)
            if hit is None:
                print(f"toast-resize refused: {edge}", flush=True)
                return
            qedges = {
                "left": Qt.LeftEdge, "right": Qt.RightEdge, "top": Qt.TopEdge,
                "topleft": Qt.LeftEdge | Qt.TopEdge, "topright": Qt.RightEdge | Qt.TopEdge,
                "bottom": Qt.BottomEdge, "bottomleft": Qt.LeftEdge | Qt.BottomEdge,
                "bottomright": Qt.RightEdge | Qt.BottomEdge,
            }
            try:
                handle = window.windowHandle()
                if handle is not None and handle.startSystemResize(qedges[key]):
                    return
            except Exception:
                pass
            try:
                import ctypes
                hwnd = int(window.winId())
                ctypes.windll.user32.ReleaseCapture()
                ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, hit, 0)
            except Exception as error:
                print(f"toast-resize refused: {error}", flush=True)

        @Slot(float)
        def set_zoom(self, factor: float) -> None:
            value = max(0.6, min(1.8, float(factor or 1.0)))
            view.setZoomFactor(value)
            print(f"toast-zoom={value:.2f}", flush=True)

        @Slot(int, int)
        def resize_to(self, width: int, height: int) -> None:
            w = max(360, min(1400, int(width or 434)))
            h = max(480, min(1200, int(height or 610)))
            window.resize(w, h)
            window.setMask(contour_region(w, h, shape))
            print(f"toast-resize={w}x{h}", flush=True)

    window_bridge = WindowBridge()
    channel = QWebChannel(view.page())
    channel.registerObject("popitWindow", window_bridge)
    view.page().setWebChannel(channel)

    def console(level, message, line, source) -> None:
        print(f"toast-view {source}:{line} {message}", flush=True)

    view.page().javaScriptConsoleMessage = console

    # The secure origin is self-signed, so it is not trusted by the platform store. The window
    # pins the shell's own certificate instead: the exact certificate this process serves is
    # accepted, anything else is refused. That is narrower than the platform's trust, never
    # wider, and it keeps the app window on the same HTTPS origin the phone is served from.
    pinned_cert = pinned_certificate_sha256()

    def certificate_error(error) -> None:
        digest = ""
        try:
            chain = error.certificateChain()
            digest = hashlib.sha256(bytes(chain[0].toDer())).hexdigest() if chain else ""
        except (AttributeError, TypeError, ValueError):
            digest = ""
        if pinned_cert and digest == pinned_cert:
            print("toast-cert=pin-accepted", flush=True)
            try:
                error.acceptCertificate()
            except (AttributeError, RuntimeError) as refusal:
                print(f"toast-cert=pin-accept-refused {refusal}", flush=True)
            return
        print(f"toast-cert=refused pinned={pinned_cert[:16]}({len(pinned_cert)})"
              f" got={digest[:16]}({len(digest)})", flush=True)
        try:
            error.rejectCertificate()
        except (AttributeError, RuntimeError):
            pass

    try:
        view.page().certificateError.connect(certificate_error)
        print("toast-cert=pin-armed", flush=True)
    except (AttributeError, TypeError) as unavailable:
        print(f"toast-cert=pin-unavailable {unavailable}", flush=True)

    secure_loaded = False
    retries = {"count": 0, "max": 3}

    def retry() -> None:
        retries["count"] += 1
        print(f"toast-view retry={retries['count']}/{retries['max']} · {origin}", flush=True)
        view.load(QUrl(origin))

    def loaded(ok: bool) -> None:
        nonlocal secure_loaded
        print(f"toast-view loaded={ok}", flush=True)
        if ok:
            if origin.startswith("https"):
                secure_loaded = True
            retries["count"] = 0
        elif retries["count"] < retries["max"]:
            # A failed load does not end the desk. It is retried with a backoff and the attempt
            # is in the log; a transient network or renderer failure is not a reason to stop
            # being the window, and a client storming the origin used to end it exactly here.
            QTimer.singleShot(1200 * (retries["count"] + 1), retry)
            print("toast-view retry-scheduled", flush=True)
            return
        elif not secure_loaded and origin.startswith("https"):
            # A window that cannot be delivered over TLS is not shown over bare http: the
            # loopback twin is the refusal shape, so the window says what refused instead.
            print("toast-origin=refused window-not-secure after three refused secure loads",
                  flush=True)
            WINDOW_ORIGIN["note"] = "https-refused"
            view.setHtml(
                "<!doctype html><meta charset='utf-8'>"
                "<body style='background:#0c0e11;color:#e9e2d0;font:14px/1.5 monospace;"
                "padding:24px'><p>window-not-secure</p>"
                f"<p>The app window could not be delivered over TLS from {origin}.</p>"
                "<p>A window served over bare http is not the app.</p></body>")
            return
        if ok and origin.startswith("https"):
            secure_loaded = True
        view.page().runJavaScript(
            "JSON.stringify({body:document.body.innerText.slice(0,80),"
            "bar:document.querySelector('.bar')?.getBoundingClientRect().toJSON(),"
            "at:document.elementsFromPoint(210,40).map(e=>e.className||e.tagName),"
            "color:document.querySelector('.bar h1')&&getComputedStyle(document.querySelector('.bar h1')).color,"
            "springboard:(()=>{const f=document.querySelector('#springboard-frame');"
            "return f?{pending:f.dataset.pending||'',ready:f.dataset.ready||'',hidden:f.hidden,"
            "src:f.getAttribute('src')||''}:null})()})",
            0,
            lambda value: print(
                ("toast-view dom=" + str(value)).encode("ascii", "backslashreplace").decode(),
                flush=True,
            ),
        )

    view.loadFinished.connect(loaded)
    window.setCentralWidget(view)

    def grab() -> None:
        path = ROOT / "runlogs" / "toast" / "view-grab.png"
        view.grab().save(str(path))
        print(f"toast-view grab={path}", flush=True)

    QTimer.singleShot(2500, grab)
    placement_path = ROOT / "runlogs" / "toast" / "window-state.json"
    try:
        placement = json.loads(placement_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        placement = {}
    width = max(360, min(1400, int(placement.get("width") or 434)))
    height = max(480, min(1200, int(placement.get("height") or 610)))
    window.setMinimumSize(360, 480)
    window.resize(width, height)
    window.setMask(contour_region(width, height, shape))
    screen = QGuiApplication.primaryScreen().availableGeometry()
    saved_x, saved_y = placement.get("x"), placement.get("y")
    on_screen = (isinstance(saved_x, (int, float)) and isinstance(saved_y, (int, float))
                 and screen.left() - width < saved_x < screen.right()
                 and screen.top() < saved_y < screen.bottom())
    if on_screen:
        window.move(int(saved_x), int(saved_y))
    else:
        window.move(screen.right() - width - 22, screen.top() + 22)

    def save_placement() -> None:
        try:
            placement_path.parent.mkdir(parents=True, exist_ok=True)
            placement_path.write_text(json.dumps({
                "width": window.width(), "height": window.height(),
                "x": window.x(), "y": window.y(),
            }, indent=2) + "\n", encoding="utf-8")
        except OSError as error:
            print(f"toast-placement refused: {error}", flush=True)

    placement_timer = QTimer()
    placement_timer.setSingleShot(True)
    placement_timer.timeout.connect(save_placement)

    def schedule_placement() -> None:
        placement_timer.start(240)

    app.aboutToQuit.connect(save_placement)
    # The window loads the app package this shell delivers. Over TLS it is the same package the
    # phone reads, on the origin whose certificate is pinned above.
    origin, origin_note = app_window_origin(https_server, lan_bind, args.https_port,
                                            server.server_port, window_https)
    if args.window_route and origin:
        wanted = str(args.window_route).strip()
        allowed = set(WINDOW_AUDIT_ROUTES.values())
        if wanted not in allowed:
            # Only a route the family itself names for a surface is a launch; anything else is
            # a page this shell would be loading as if it were an app.
            print(f"toast-window route-refused {wanted} not-a-window-route", flush=True)
        else:
            base, _, query = origin.partition("?")
            # The base already names a page; the route names its own, so the page is replaced
            # rather than appended to (a route appended to /toast.html read /toast.html/toast.html).
            base = base.rsplit("/", 1)[0]
            path, _, extra = wanted.partition("?")
            merged = "&".join(part for part in (query, extra) if part)
            origin = f"{base}{path}?{merged}"
            print(f"toast-window route={wanted}", flush=True)
    print(f"toast-origin={origin} ({origin_note})", flush=True)
    # The window's origin carries its build token (`?v=…`), so the base is its scheme and host,
    # not the origin minus a path suffix: comparing the whole string left the base empty and
    # every route act — the window audit's own route among them — refused as insecure.
    window_parts = urlsplit(origin)
    window_base = (f"{window_parts.scheme}://{window_parts.netloc}"
                   if window_parts.scheme == "https" else "")
    WINDOW_ORIGIN.update({"base": window_base, "note": origin_note})
    view.load(QUrl(origin))

    def show_window() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def tray_icon() -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#e2c188"))
        painter.drawPolygon(QPolygon([QPoint(16, 3), QPoint(29, 16),
                                      QPoint(16, 29), QPoint(3, 16)]))
        painter.end()
        return QIcon(pixmap)

    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip("Popit agent toast · Debian LXDE")
    tray_menu = QMenu()
    show_action = tray_menu.addAction("Show agent")
    show_action.triggered.connect(show_window)
    hide_action = tray_menu.addAction("Hide agent")
    hide_action.triggered.connect(window.hide)
    tray_menu.addSeparator()
    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: show_window()
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None
    )
    tray.show()

    pinned = {"on": True}

    def pump() -> None:
        if toast.pending.get("reload"):
            toast.pending["reload"] = False
            print("toast-view reload=requested", flush=True)
            view.reload()
        if toast.pending.get("grab"):
            toast.pending["grab"] = False
            grab()
        if toast.pending.get("show"):
            toast.pending["show"] = False
            show_window()
        if toast.pending["hide"]:
            toast.pending["hide"] = False
            window.hide()
        if toast.pending["close"]:
            toast.pending["close"] = False
            app.quit()
            return
        wanted = toast.pending["pin"]
        if wanted is not None:
            toast.pending["pin"] = None
            pinned["on"] = bool(wanted)
            window.setWindowFlag(Qt.WindowStaysOnTopHint, pinned["on"])
            window.show()

    timer = QTimer()
    timer.timeout.connect(pump)
    timer.start(200)
    def on_resize(event) -> None:
        QMainWindow.resizeEvent(window, event)
        window.setMask(contour_region(window.width(), window.height(), shape))
        schedule_placement()

    def on_move(event) -> None:
        QMainWindow.moveEvent(window, event)
        schedule_placement()

    window.resizeEvent = on_resize
    window.moveEvent = on_move
    window.show()
    view.setFocus()
    try:
        return app.exec()
    finally:
        # The desk is already closing; a shutdown that cannot reach the Debian box must not
        # replace the exit with a traceback about the tunnel.
        try:
            toast.stop()
        except Exception as error:
            print(f"toast-stop refused · {error.__class__.__name__}: {error}", flush=True)
        server.shutdown()
        archive_server.shutdown()
        if lan_server is not None:
            lan_server.shutdown()
        if window_https is not None:
            window_https.shutdown()
        if https_server is not None:
            https_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
