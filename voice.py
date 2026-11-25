"""Packaged voice layer for the Popit toast.

The Debian CUA host is headless: it has no audio device and no `aplay`/`arecord`. The
voice is therefore generated on the Windows client from a pinned profile table, written
as a WAV artifact, played through the default output, and recorded one row per breath.

Profiles are per driver and per role. `cua-chat` and the other drivers each have their
own base voice, rate and pitch; the assistant has a separate, slower profile. The
`civilian` profile is the queue gate: a slower rate, a longer sentence pause and a
2.2-second floor between lines, so a civilian is addressed one sentence at a time.

Microphone input is the Windows default capture device through System.Speech's dictation
recognizer, which runs in a kept PowerShell helper. A line is ignored while the client is
speaking so the agents do not hear their own output.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
import wave
import winsound
from collections import deque
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent
PROFILES = ROOT / "voice_profiles.json"
ARTIFACTS = ROOT / "runlogs" / "voice"
RECEIPTS = ROOT / "runlogs" / "voice" / "receipts.jsonl"
MIC_SCRIPT = ROOT / "tools" / "mic_whisper.py"
PIPER_MODEL = ROOT / "models" / "en_US-amy-medium.onnx"
PIPER_CONFIG = ROOT / "models" / "en_US-amy-medium.onnx.json"
PYTHON = pathlib.Path(sys.executable).with_name("python.exe")
SCHEMA = "popit.voice/1"
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Refused(Exception):
    def __init__(self, code: str, detail: str = "", **extra) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.extra = extra

    def as_dict(self) -> dict:
        body = {"code": self.code, "detail": self.detail}
        body.update(self.extra)
        return body


def load_profiles(path: pathlib.Path = PROFILES) -> dict:
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Refused("voice-profiles-unreadable", str(path), error=str(error)) from error
    if table.get("schema") != SCHEMA or not isinstance(table.get("profiles"), dict):
        raise Refused("voice-profiles-unreadable", str(path), "schema or profiles absent")
    return table


def sentences(text: str) -> list[str]:
    """One line per breath: punctuation splits a longer address, never a guessed phrase."""
    clean = " ".join(str(text or "").split())
    if not clean:
        return []
    return [part.strip() for part in SENTENCE.split(clean) if part.strip()]


class SapiEngine:
    """SAPI in the playback worker's own COM apartment."""

    def __init__(self, play: bool = True) -> None:
        self.play = play
        # SAPI objects live in the COM apartment that created them. The playback worker
        # and the probe are different threads, so each thread gets its own engine rather
        # than marshalling a voice across apartments.
        self._local = threading.local()
        self._lock = threading.Lock()

    def _load(self):
        cached = getattr(self._local, "voice", None)
        if cached is not None:
            return cached
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        voices: dict[str, object] = {}
        for index in range(voice.GetVoices().Count):
            item = voice.GetVoices().Item(index)
            description = str(item.GetDescription()).lower()
            if "david" in description:
                voices["david"] = item
            if "zira" in description:
                voices["zira"] = item
        if not voices:
            raise Refused("voice-engine-absent", "SAPI has no installed voice")
        self._local.voice = voice
        self._local.voices = voices
        return voice

    def synthesize(self, profile: dict, text: str, target: pathlib.Path) -> dict:
        import win32com.client

        with self._lock:
            voice = self._load()
            base = str(profile.get("voice") or "").lower()
            token = getattr(self._local, "voices", {}).get(base)
            if token is None:
                raise Refused("voice-not-installed", base,
                              installed=sorted(getattr(self._local, "voices", {})))
            voice.Voice = token
            voice.Rate = max(-10, min(10, int(profile.get("rate", 0))))
            pitch = max(-10, min(10, int(profile.get("pitch", 0))))
            pause = max(0, min(2000, int(profile.get("sentence_pause_ms", 220))))
            body = escape(text)
            if pause:
                body = body.replace(". ", f'.<break time="{pause}ms"/> ')
                body = body.replace("? ", f'?<break time="{pause}ms"/> ')
                body = body.replace("! ", f'!<break time="{pause}ms"/> ')
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            target.parent.mkdir(parents=True, exist_ok=True)
            stream.Open(str(target), 3, False)
            voice.AudioOutputStream = stream
            try:
                voice.Speak(f'<pitch absmiddle="{pitch}"/>{body}', 8)
            finally:
                stream.Close()
                voice.AudioOutputStream = None
        with wave.open(str(target), "rb") as audio:
            seconds = audio.getnframes() / float(audio.getframerate())
        return {"path": str(target), "seconds": round(seconds, 2), "bytes": target.stat().st_size}

    def play_file(self, path: pathlib.Path) -> None:
        if self.play:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)


class PiperEngine:
    """Local Piper voice, one subprocess per line, WAV on the Windows client."""

    def __init__(self, play: bool = True) -> None:
        self.play = play

    def synthesize(self, profile: dict, text: str, target: pathlib.Path) -> dict:
        model = PIPER_MODEL
        config = PIPER_CONFIG
        chosen = str(profile.get("model") or "").strip()
        if chosen:
            model = pathlib.Path(chosen)
            if not model.is_absolute():
                model = ROOT / model
            config = pathlib.Path(str(model) + ".json")
        if not model.exists() or not config.exists():
            raise Refused("voice-engine-absent", f"Piper model absent: {model}")
        length = profile.get("length_scale")
        if length is None:
            length = 1.0 - max(-10, min(10, int(profile.get("rate", 0)))) * 0.035
        command = [
            str(PYTHON if PYTHON.exists() else sys.executable), "-m", "piper",
            "-m", str(model), "-c", str(config),
            "-f", str(target), "--length-scale", f"{float(length):.3f}",
        ]
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                command, input=text + "\n", text=True, capture_output=True,
                timeout=45, creationflags=0x08000000,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Refused("voice-synthesis-failed", str(error)) from error
        if result.returncode != 0 or not target.exists():
            detail = (result.stderr or result.stdout or "").strip()[:300]
            raise Refused("voice-synthesis-failed", detail or f"piper exited {result.returncode}")
        with wave.open(str(target), "rb") as audio:
            seconds = audio.getnframes() / float(audio.getframerate())
        return {"path": str(target), "seconds": round(seconds, 2),
                "bytes": target.stat().st_size, "engine": "piper"}

    def play_file(self, path: pathlib.Path) -> None:
        if self.play:
            winsound.PlaySound(str(path), winsound.SND_FILENAME)


class VoiceService:
    def __init__(self, *, play: bool = True, profiles: pathlib.Path = PROFILES) -> None:
        self.table = load_profiles(profiles)
        self.default_engine = str((self.table.get("engine") or {}).get("name") or "windows-sapi")
        self.engines = {
            "piper": PiperEngine(play=play),
            "windows-sapi": SapiEngine(play=play),
            "sapi": SapiEngine(play=play),
        }
        if self.default_engine not in self.engines:
            raise Refused("voice-engine-absent", self.default_engine)
        self.engine = self.engines[self.default_engine]
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.items: deque[dict] = deque()
        self.speaking: dict | None = None
        self.last: dict | None = None
        self._next_at = 0.0
        self._ignore_until = 0.0
        self.generation = 0
        self._stop = threading.Event()
        self._seq = 0
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def profile(self, name: str) -> dict:
        profiles = self.table["profiles"]
        if name in profiles:
            return {"id": name, **profiles[name]}
        for key, profile in profiles.items():
            if profile.get("driver") == name:
                return {"id": key, **profile}
        # A family roster can be ingested without hand-authoring a profile for every
        # name. Derive a stable, distinct SAPI breath from the name itself so wide
        # rosters still speak as individuals instead of failing on a missing row.
        slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-") or "civilian"
        digest = hashlib.sha256(slug.encode("utf-8")).digest()
        return {
            "id": slug,
            "label": str(name or slug).strip() or slug,
            "driver": "civilian",
            "engine": "sapi",
            "voice": "zira" if digest[0] % 2 else "david",
            "rate": -2 + digest[1] % 5,
            "pitch": -3 + digest[2] % 7,
            "sentence_pause_ms": 220,
            "min_gap_ms": 1200,
        }

    def say(self, profile_name: str, text: str) -> dict:
        profile = self.profile(profile_name)
        lines = sentences(text)
        if not lines:
            raise Refused("voice-line-empty", profile_name)
        limit = int(self.table["limits"]["line_chars"])
        max_queue = int(self.table["limits"]["max_queue"])
        with self.cond:
            if len(self.items) + len(lines) > max_queue:
                raise Refused("voice-queue-full", profile_name,
                              queued=len(self.items), limit=max_queue)
            ids = []
            for line in lines:
                if len(line) > limit:
                    raise Refused("voice-line-too-long", profile_name,
                                  chars=len(line), limit=limit)
                self._seq += 1
                item = {
                    "id": f"voice-{self._seq:04d}",
                    "profile": profile["id"],
                    "label": profile.get("label", profile["id"]),
                    "text": line,
                    "chars": len(line),
                    "at": iso(),
                    "min_gap_ms": int(profile.get("min_gap_ms", 900)),
                }
                self.items.append(item)
                ids.append(item["id"])
            self.cond.notify_all()
        return {
            "schema": SCHEMA,
            "state": "queued",
            "profile": profile["id"],
            "ids": ids,
            "lines": len(ids),
            "gate": {"min_gap_ms": int(profile.get("min_gap_ms", 900))},
        }

    def render(self, profile_name: str, text: str) -> dict:
        """Synthesize one answer for the phone without queueing Windows playback."""
        profile = self.profile(profile_name)
        clean = " ".join(str(text or "").split())[:1200]
        if not clean:
            raise Refused("voice-line-empty", profile_name)
        engine_name = str(profile.get("engine") or self.default_engine)
        engine = self.engines.get(engine_name)
        if engine is None:
            raise Refused("voice-engine-absent", engine_name)
        target = ARTIFACTS / ("phone-" + hashlib.sha1(
            (profile["id"] + "\n" + clean).encode("utf-8", "replace")).hexdigest()[:16] + ".wav")
        try:
            made = engine.synthesize(profile, clean, target)
            body = target.read_bytes()
        except Refused:
            raise
        except Exception as error:
            raise Refused("voice-synthesis-failed", str(error)[:240]) from error
        return {
            "profile": profile["id"], "label": profile.get("label", profile["id"]),
            "engine": engine_name, "audio": body, "seconds": made["seconds"],
            "bytes": len(body),
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            with self.cond:
                while not self.items and not self._stop.is_set():
                    self.cond.wait(0.5)
                if self._stop.is_set():
                    return
                item = self.items.popleft()
                delay = self._next_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            profile = self.profile(item["profile"])
            engine_name = str(profile.get("engine") or self.default_engine)
            engine = self.engines.get(engine_name)
            generation = self.generation
            slug = re.sub(r"[^a-z0-9]+", "-", item["text"].lower())[:32].strip("-")
            target = ARTIFACTS / f"{item['id']}-{slug}.wav"
            receipt = {
                "schema": SCHEMA, "row": "voice-line", "id": item["id"],
                "profile": item["profile"], "label": item["label"],
                "engine": engine_name, "channel": str(profile.get("channel") or "default"),
                "chars": item["chars"], "text": item["text"], "at": iso(),
                "state": "speaking", "produced": False, "digest": "", "artifact": "",
            }
            with self.lock:
                self.speaking = item
            try:
                if engine is None:
                    raise Refused("voice-engine-absent", engine_name)
                made = engine.synthesize(profile, item["text"], target)
                if generation != self.generation:
                    receipt.update(state="interrupted", refusal="barge-in")
                    continue
                receipt.update(made, state="produced", produced=True)
                receipt["digest"] = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()[:24]
                engine.play_file(target)
                receipt["state"] = "played" if engine.play else "produced"
            except Refused as error:
                receipt.update(state="refused", refusal=error.code, reason=error.detail)
            except Exception as error:  # a voice failure is a visible receipt, not a crash
                receipt.update(state="refused", refusal="voice-synthesis-failed", reason=str(error))
            finally:
                with self.lock:
                    self.speaking = None
                    self.last = receipt
                    self._ignore_until = time.monotonic() + 0.9
                    self._next_at = time.monotonic() + item["min_gap_ms"] / 1000
                self._record(receipt)

    def _record(self, receipt: dict) -> None:
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            with RECEIPTS.open("a", encoding="utf-8") as log:
                log.write(json.dumps(receipt) + "\n")

    def listening(self) -> bool:
        with self.lock:
            return self.speaking is not None or time.monotonic() < self._ignore_until

    def echoes(self, text: str) -> bool:
        """A phrase that is mostly the line currently playing is speaker echo, not the owner."""
        words = set(re.findall(r"[a-z0-9']+", str(text or "").lower()))
        if len(words) < 2:
            # A single addressed name (for example "Whisper") must survive even
            # when that name is present in recent agent speech.
            return False
        with self.lock:
            recent = [self.speaking] if self.speaking else []
            recent += [self.last] if self.last else []
            recent += list(self.items)[-3:]
        for row in recent:
            spoken = set(re.findall(r"[a-z0-9']+", str((row or {}).get("text") or "").lower()))
            if spoken and len(words & spoken) / max(1, len(words)) >= 0.6:
                return True
        return False

    def interrupt(self, reason: str = "owner-barge-in") -> dict:
        """The owner always wins: drop queued answers and stop the current playback."""
        with self.cond:
            self.generation += 1
            self.items.clear()
            self._next_at = 0.0
            self._ignore_until = 0.0
            generation = self.generation
            self.cond.notify_all()
        try:
            winsound.PlaySound(None, 0)
        except Exception:
            pass
        return {"generation": generation, "reason": reason}

    def state(self) -> dict:
        with self.lock:
            last = dict(self.last) if self.last else None
            return {
                "schema": SCHEMA,
                "engine": self.table["engine"],
                "profiles": [
                    {"id": key, "label": value.get("label", key),
                     "driver": value.get("driver", ""), "engine": value.get("engine") or self.default_engine,
                     "voice": value.get("voice"), "rate": value.get("rate"), "pitch": value.get("pitch"),
                     "channel": value.get("channel") or "default",
                     "min_gap_ms": value.get("min_gap_ms")}
                    for key, value in self.table["profiles"].items()
                ],
                "queue": list(self.items),
                "speaking": dict(self.speaking) if self.speaking else None,
                "last": last,
                "gate": {
                    "min_gap_ms": (last or {}).get("min_gap_ms", 900),
                    "civilian_min_gap_ms": self.table["profiles"]["civilian"]["min_gap_ms"],
                    "one_line_per_breath": True,
                },
            }

    def stop(self) -> None:
        with self.cond:
            self._stop.set()
            self.cond.notify_all()


class MicListener:
    """Default Windows microphone, read through the installed dictation engine."""

    def __init__(self, voice: VoiceService, on_phrase=None) -> None:
        self.voice = voice
        self.on_phrase = on_phrase
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.state = "idle"
        self.detail = ""
        self.last: dict | None = None
        self.partial: dict | None = None
        self.count = 0
        self._thread: threading.Thread | None = None

    def start(self) -> dict:
        with self.lock:
            if self.process and self.process.poll() is None:
                return self.state_dict()
            if not MIC_SCRIPT.exists():
                self.state, self.detail = "refused", f"helper absent: {MIC_SCRIPT}"
                return self.state_dict()
            creation = 0x08000000  # CREATE_NO_WINDOW
            try:
                self.process = subprocess.Popen(
                    [str(PYTHON if PYTHON.exists() else sys.executable), "-u", str(MIC_SCRIPT)],
                    cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True, encoding="utf-8", errors="replace", creationflags=creation,
                )
            except OSError as error:
                self.state, self.detail = "refused", str(error)
                return self.state_dict()
            self.state, self.detail = "starting", ""
            self._thread = threading.Thread(target=self._read, daemon=True)
            self._thread.start()
        return self.state_dict()

    def _read(self) -> None:
        process = self.process
        if process is None:
            return
        assert process.stdout is not None
        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("event")
                with self.lock:
                    if kind == "error":
                        self.state, self.detail = "refused", str(event.get("detail", ""))
                    elif kind == "status":
                        self.state = "starting"
                        self.detail = str(event.get("detail", ""))
                    elif kind == "ready":
                        self.state = "listening"
                        self.detail = str(event.get("engine", ""))
                    elif kind == "partial":
                        text = str(event.get("text", "")).strip()
                        if text:
                            self.state = "hearing"
                            self.partial = {"text": text, "at": iso(),
                                            "confidence": event.get("confidence")}
                    elif kind == "phrase":
                        # Never drop the owner's phrase because an agent is talking. The
                        # callback queues the words; it does not force an agent to stop.
                        text = str(event.get("text", "")).strip()
                        confidence = event.get("confidence")
                        if not text:
                            continue
                        # The engine emits short room noises (one measured false phrase was
                        # "Low" at 0.369). A heard line is a phrase it is willing to stand behind.
                        if isinstance(confidence, (int, float)) and confidence < 0.45:
                            continue
                        self.state = "heard"
                        self.partial = None
                        self.count += 1
                        self.last = {
                            "text": text,
                            "confidence": event.get("confidence"),
                            "at": iso(),
                        }
                        callback = self.on_phrase
                        if callback:
                            threading.Thread(target=callback, args=(text,), daemon=True).start()
                    elif kind == "silence":
                        if self.state != "refused":
                            self.state = "listening"
        finally:
            with self.lock:
                if process.poll() not in (0, None) and self.state != "refused":
                    self.state, self.detail = "refused", f"microphone helper exited {process.returncode}"

    def record_phone(self, text: str) -> None:
        """Publish a guarded phrase accepted from the secure phone WAV path."""
        clean = " ".join(str(text or "").split())
        if not clean:
            return
        with self.lock:
            self.state = "heard"
            self.detail = "phone wav · whisper-tiny.en"
            self.partial = None
            self.count += 1
            self.last = {"text": clean, "confidence": None,
                         "at": iso(), "source": "phone"}

    def state_dict(self) -> dict:
        with self.lock:
            return {
                "state": self.state,
                "detail": self.detail,
                "last": dict(self.last) if self.last else None,
                "partial": dict(self.partial) if self.partial else None,
                "phrases": self.count,
                "pid": self.process.pid if self.process else None,
                "device": "default capture device",
            }

    def stop(self) -> None:
        with self.lock:
            process = self.process
            self.process = None
            self.state = "stopped"
            self.detail = "microphone turned off by the user"
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
