#!/usr/bin/env python3
"""Listen on the Windows default microphone and emit Whisper phrases as JSON lines.

The toast's `voice.MicListener` reads these events exactly as it read the old System.Speech
helper. Whisper-tiny.en is cached locally; the recognizer runs on the CPU so this helper has
no network dependency once the model is present.

One phrase is the audio between the first voiced block and roughly 2.2 seconds of silence.
A longer silence gate is deliberate: the owner thinks between clauses, and cutting at 0.6 s
produced a row per fragment instead of one spoken thought.
The pre-roll keeps the first syllable, and the maximum keeps a stuck room from growing forever.
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
import threading
import time
from collections import Counter

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

print('{"event": "status", "detail": "starting microphone helper"}', flush=True)

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402


HALLUCINATIONS = {
    "the end", "thanks for watching", "thank you for watching",
    "thank you so much for watching", "please subscribe", "whoa",
    "i'll see you in the next video", "see you in the next video",
    "i will see you in the next video", "see you next time", "i'll see you next time",
    "see you in the next one", "i'll see you in the next one",
}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def plausible(text: str) -> bool:
    """Whisper invents YouTube sign-offs on room silence; drop those."""
    clean = " ".join(text.lower().replace("’", "'").split()).strip(".!?,;: ")
    if not clean or clean in HALLUCINATIONS:
        return False
    if "thanks for watching" in clean or "see you in the next video" in clean:
        return False
    # Whisper repeats its YouTube sign-off when the microphone is quiet. One
    # mention can be a real quote; two or more, or a long repetition, cannot be
    # an owner turn. This runs only on microphone ASR, never on agent output.
    signoffs = sum(clean.count(phrase) for phrase in (
        "thank you for watching", "thanks for watching", "please subscribe",
        "see you in the next video", "i'll see you in the next video",
        "see you next time", "i'll see you next time",
        "see you in the next one", "i'll see you in the next one",
    ))
    if signoffs >= 2 or (len(clean) > 140 and signoffs >= 1):
        return False
    if clean in {"buffy", "qwen", "whisper", "ash", "bram"}:
        return True
    words = re.findall(r"[a-z']+", clean)
    if len(words) <= 1 and clean not in {"yes", "no", "stop", "buffy", "qwen", "whisper", "ash", "bram"}:
        # One-word silence artifacts were reaching the archive as owner turns. "Whoa"
        # was the visible one; an addressed name or a real short answer still passes.
        return False
    if len(words) >= 4:
        count, hits = Counter(words).most_common(1)[0]
        # Whisper loops on a silent or clipped tail: "okay okay okay ..." is not an
        # owner utterance, and letting it reach the call makes every lane answer nothing.
        if hits >= 4 and hits / len(words) > 0.45:
            return False
    return len(clean) >= 3


def main() -> int:
    from transformers import pipeline

    emit({"event": "status", "detail": "loading whisper-tiny.en for live speech"})
    # One fast model, not a slow final gate. The owner hears their own words arriving;
    # an accurate 15 s delayed sentence was the problem, not a missing second model.
    partial_asr = pipeline("automatic-speech-recognition", model="openai/whisper-tiny.en", device=-1)
    asr = partial_asr
    asr_lock = threading.Lock()
    partial_lock = threading.Lock()
    partial_pending: dict = {"audio": None, "generation": 0}
    partial_generation = 0

    def finish(samples: np.ndarray) -> None:
        """Transcribe a finished phrase off the capture thread.

        The old final pass ran on the capture loop with the same model lock as the
        partial pass. A long phrase could stop the live text and make the microphone
        look frozen; capture now stays live while the final text settles.
        """
        try:
            with asr_lock:
                result = asr(samples)
            text = " ".join(str(result.get("text", "")).split())
        except Exception as error:  # a failed phrase is reported, not fatal
            emit({"event": "error", "detail": f"whisper: {error}"})
            return
        if text and plausible(text):
            emit({"event": "phrase", "text": text, "confidence": 0.9,
                  "engine": "whisper-tiny.en"})
        else:
            emit({"event": "silence"})

    def partial_worker() -> None:
        """Transcribe the live speech tail without blocking the capture loop."""
        nonlocal partial_pending
        last_text = ""
        while True:
            with partial_lock:
                work = partial_pending
                partial_pending = {"audio": None, "generation": work["generation"]}
            chunk = work.get("audio")
            if chunk is None:
                time.sleep(0.05)
                continue
            try:
                with asr_lock:
                    result = partial_asr(chunk)
                text = " ".join(str(result.get("text", "")).split())
            except Exception:
                continue
            if not text or not plausible(text) or len(text) < 4:
                continue
            with partial_lock:
                if work.get("generation") != partial_generation:
                    continue
            if text != last_text:
                last_text = text
                emit({"event": "partial", "text": text, "confidence": 0.55,
                      "engine": "whisper-tiny.en"})

    threading.Thread(target=partial_worker, daemon=True).start()

    rate = 16000
    block = 1600  # 100 ms
    preroll = collections.deque(maxlen=5)
    audio: list[np.ndarray] = []
    speaking = False
    voiced_blocks = 0
    silent_blocks = 0
    noise = 0.006
    last_silence = 0.0
    last_partial = 0.0
    queue: collections.deque[np.ndarray] = collections.deque()

    def callback(indata, frames, moment, status) -> None:
        queue.append(indata[:, 0].copy())

    try:
        with sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                            blocksize=block, callback=callback):
            emit({"event": "ready", "device": "default capture device", "engine": "whisper-tiny.en"})
            while True:
                if not queue:
                    time.sleep(0.01)
                    continue
                chunk = queue.popleft()
                level = float(np.sqrt(np.mean(chunk * chunk)))
                noise = noise * 0.995 + level * 0.005
                threshold = max(0.010, noise * 2.5)
                voiced = level >= threshold

                if not speaking:
                    preroll.append(chunk)
                    if voiced:
                        speaking = True
                        voiced_blocks = 1
                        silent_blocks = 0
                        audio = list(preroll)
                        preroll.clear()
                    elif time.monotonic() - last_silence > 1.0:
                        emit({"event": "silence", "level": round(level, 4)})
                        last_silence = time.monotonic()
                    continue

                audio.append(chunk)
                if voiced:
                    voiced_blocks += 1
                    silent_blocks = 0
                else:
                    silent_blocks += 1

                # Stream a provisional phrase while the owner is still speaking. The
                # worker runs off the capture thread; the final phrase below replaces it.
                now = time.monotonic()
                if len(audio) >= 8 and now - last_partial >= 0.45:
                    snapshot = np.concatenate(audio[-30:])
                    with partial_lock:
                        partial_generation += 1
                        generation = partial_generation
                        partial_pending = {"audio": snapshot, "generation": generation}
                    last_partial = now

                if silent_blocks < 22 and len(audio) < 240:
                    continue

                if voiced_blocks < 3:  # shorter than 0.3 s of speech is a room tick
                    audio.clear()
                    speaking = False
                    continue

                samples = np.concatenate(audio)
                rms = float(np.sqrt(np.mean(samples * samples)))
                audio.clear()
                speaking = False
                last_partial = 0.0
                # Invalidate any partial still in flight; it belongs to the finished phrase.
                with partial_lock:
                    partial_generation += 1
                    partial_pending = {"audio": None, "generation": partial_generation}
                if rms < 0.012:
                    continue
                # This English-only model refuses language/task arguments. Passing
                # them raises and drops every spoken phrase.
                threading.Thread(target=finish, args=(samples,), daemon=True).start()
    except Exception as error:
        emit({"event": "error", "detail": f"microphone: {error}"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
