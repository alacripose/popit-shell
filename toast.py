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
import json
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
from urllib.parse import parse_qs, urlsplit

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
LANES = {
    "Buffy": (
        "You are Buffy, the host agent for this Windows toast. You keep the live Freebuff "
        "harness and the CUA drivers moving, speak directly to Alacrity, and do not repeat "
        "Qwen's machine inspection, Ash's resident work, or Bram's supply work."
    ),
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

sys.path.insert(0, str(ROOT))
import archive as archive_mod  # noqa: E402
import axis_bridge  # noqa: E402
import calls as calls_mod  # noqa: E402
import civilian_features  # noqa: E402
import civilian_scope  # noqa: E402
import cua  # noqa: E402
import debian_view  # noqa: E402
import debian_window  # noqa: E402
import dialin  # noqa: E402
import envelope  # noqa: E402
import external_agents  # noqa: E402
import hosts  # noqa: E402
import mind_bridge  # noqa: E402
import settings_package  # noqa: E402
import app_package  # noqa: E402
import voice  # noqa: E402


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Toast:
    def __init__(self, *, probe_seconds: float = 4.0, play_voice: bool = True) -> None:
        self.lock = threading.RLock()
        self.fleet = cua.Fleet(drivers=4)
        self.voice = voice.VoiceService(play=play_voice)
        self.axis = axis_bridge.AxisBridge()
        self.debian = debian_view.DebianView()
        self.archive = archive_mod.Archive(ROOT / "runlogs" / "toast" / "archive.jsonl")
        self.mind = mind_bridge.DebianMind(self.debian, archive=self.archive, cua=self.delegate)
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
            ROOT / "runlogs" / "toast" / "apps", ROOT / "ui", settings=self.settings)
        # A surface is signed before it is served, whether this process is the shell or a
        # probe reading the same routes.
        self.apps.ensure_all()
        self.calls = calls_mod.CallLedger(ROOT / "runlogs" / "toast" / "calls.json", self.dialin)
        self.civilians = civilian_features.CivilianDesk(
            ROOT / "runlogs" / "toast" / "civilians.json")
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
                )
                heard = "played" if edge.get("played") else "retained · output busy"
                self.archive.add("call-tone", f"{tone} dial tone · {call['agent']} · {heard}",
                                 role="call", call=call["id"], tone=tone, played=edge.get("played", False),
                                 path=edge.get("path", ""))
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
        call = next((row for row in self.calls.actives()
                     if row.get("agent") == name), None)
        if call is None:
            raise calls_mod.Refused("bridge-line-absent", f"no open call for {name}")
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
        return {"session": session, "call": state["call"], "agent": state["agent"],
                "cursor": cursor, "turns": turns, "waiting": not turns}

    def bridge_say(self, session: str, text: str, *, speak: bool = True) -> dict:
        """Speak and archive a line from the attached general agent harness."""
        state = self._bridge(session)
        clean = " ".join(str(text or "").split())
        if not clean:
            raise calls_mod.Refused("bridge-empty", "a spoken bridge line needs words")
        call = next(row for row in self.calls.actives() if row["id"] == state["call"])
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
                "voice": receipt, "agent": state["agent"]}

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
        self.begin_work()
        with self.lock:
            self.responders = [call["agent"] for call in chosen]
        for call in chosen:
            self._lane(call["agent"], "queued", "waiting for its lane turn")
        last: dict = {}
        try:
            if chosen:
                for call in chosen:
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
            # Repair is also periodic: a quiet stretch can be archived before the
            # recognizer's final pass is corrected, and the owner should not have to
            # restart to remove that row.
            self.archive.repair_hallucinations()
            self.run_probe()

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
                "lanes": self.lane_state(),
                "call": self.call,
                "working": self.working > 0,
                "responders": list(self.responders),
                "lane_threads": [{"name": name, **row}
                                   for name, row in self.lane_states.items()],
                "live": self.live,
                "pending": dict(self.pending),
            }

    def delegate(self, body: dict) -> dict:
        actions = body.get("actions")
        driver = str(body.get("driver") or "")
        return self.fleet.submit(actions, driver, announce=bool(body.get("announce")))

    def task(self, task_id: str) -> dict:
        with self.fleet.lock:
            task = next((item for item in self.fleet.tasks if item.id == task_id), None)
            if task is None:
                raise cua.Refused("task-not-found", task_id)
            return task.as_dict()


class Handler(BaseHTTPRequestHandler):
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

    def do_GET(self):  # noqa: N802
        path = urlsplit(self.path).path
        toast: Toast = self.server.toast
        if not self.archive_allowed(path):
            return self.json({"ok": False, "refused": "archive-token"}, 403)
        if path == "/":
            # The phone's home is the SpringBoard, not the desk: the desk is the dialin app
            # package, and wrapping it in a shell on a phone draws two chromes over one page.
            return self.file("phone.html", "text/html; charset=utf-8")
        if path == "/toast.html":
            return self.file("toast.html", "text/html; charset=utf-8")
        if path == "/ui-audit.js":
            return self.file("ui-audit.js", "text/javascript; charset=utf-8")
        if path == "/toast.js":
            return self.file("toast.js", "text/javascript; charset=utf-8")
        if path == "/toast.css":
            return self.file("toast.css", "text/css; charset=utf-8")
        if path == "/settings.html":
            return self.file("settings.html", "text/html; charset=utf-8")
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
        if path in ("/archive", "/archive.html"):
            return self.file("archive.html", "text/html; charset=utf-8")
        if path == "/archive.js":
            return self.file("archive.js", "text/javascript; charset=utf-8")
        if path == "/archive.css":
            return self.file("archive.css", "text/css; charset=utf-8")
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
        if path == "/api/toast/apps":
            return self.json(toast.apps.state())
        if path.startswith("/api/toast/apps/"):
            try:
                return self.json(toast.apps.document(path.rsplit("/", 1)[-1]))
            except app_package.Refused as error:
                return self.json({"ok": False, "refused": error.as_dict()}, 409)
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
            if path == "/api/toast/apps/verify":
                # The app registry keeps the phone's posture: a signed identity is read
                # over a secure origin, and loopback is the machine itself.
                if not getattr(self.server, "tls", False) and not loopback:
                    return self.json({"ok": False, "refused": "secure-origin-required"}, 403)
                return self.json(toast.apps.document(str(body.get("app") or "")))
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
                if held != published:
                    toast.settings.publish()
                return self.json({"ok": True, "settings": held})
            if path == "/api/toast/settings/publish":
                row = toast.settings.publish(body if isinstance(body, dict) and body else None)
                return self.json({"ok": True, "identity": row["identity"],
                                  "digest": row["digest"], "revision": row["revision"],
                                  "payload_digest": row["payload_digest"],
                                  "signature": row["signature"],
                                  "published_at": row["published_at"]})
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
                row = toast.calls.close(str(body.get("id") or ""),
                                          str(body.get("evidence") or ""))
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
                external_agents.Refused) as error:
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


def ensure_phone_cert(bind: str) -> bool:
    """Generate a local SAN certificate for the phone's secure origin."""
    if PHONE_CERT.exists() and PHONE_KEY.exists():
        return True
    PHONE_CERT.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(PHONE_KEY), "-out", str(PHONE_CERT), "-days", "825",
        "-subj", f"/CN={bind}",
        "-addext", f"subjectAltName=IP:{bind},DNS:popit.local,DNS:localhost",
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
          archive: bool = False, tls: bool = False) -> ThreadingHTTPServer:
    server = PopitHTTPServer((bind, port), Handler)
    server.toast = toast
    server.archive = archive
    server.archive_token = toast.window_token
    server.tls = tls
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(PHONE_CERT), str(PHONE_KEY))
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--probe-seconds", type=float, default=4.0)
    parser.add_argument("--lan-port", type=int, default=5209)
    parser.add_argument("--https-port", type=int, default=5210)
    parser.add_argument("--lan-bind", default="")
    parser.add_argument("--no-lan", action="store_true")
    parser.add_argument("--no-https", action="store_true")
    args = parser.parse_args()

    toast = Toast(probe_seconds=args.probe_seconds)
    server = serve(toast, args.port)
    lan_bind = args.lan_bind or lan_address()
    archive_server = serve(toast, 5208, bind=lan_bind, archive=True)
    lan_server = None
    https_server = None
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
    toast.start()
    print(f"popit toast http://127.0.0.1:{server.server_port}/", flush=True)
    if lan_server is not None:
        print(f"popit phone http://{lan_bind}:{args.lan_port}/phone.html", flush=True)
    if https_server is not None:
        print(f"popit phone https://{lan_bind}:{args.https_port}/phone.html", flush=True)
        print(f"popit certificate https://{lan_bind}:{args.https_port}/popit-cert.cer", flush=True)
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

    def loaded(ok: bool) -> None:
        print(f"toast-view loaded={ok}", flush=True)
        view.page().runJavaScript(
            "JSON.stringify({body:document.body.innerText.slice(0,80),"
            "bar:document.querySelector('.bar')?.getBoundingClientRect().toJSON(),"
            "at:document.elementsFromPoint(210,40).map(e=>e.className||e.tagName),"
            "color:document.querySelector('.bar h1')&&getComputedStyle(document.querySelector('.bar h1')).color})",
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
    view.load(QUrl(f"http://127.0.0.1:{server.server_port}/toast.html"))

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
        toast.stop()
        server.shutdown()
        archive_server.shutdown()
        if lan_server is not None:
            lan_server.shutdown()
        if https_server is not None:
            https_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
