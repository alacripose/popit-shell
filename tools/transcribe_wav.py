#!/usr/bin/env python3
"""One-shot WAV transcription for the phone voice endpoint.

The phone sends a WAV; the Toast runs this process so the long-lived microphone
helper and the Qt process do not each carry a second Whisper model.
"""
from __future__ import annotations

import json
import os
import sys
import warnings

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"text": "", "error": "usage: transcribe_wav.py FILE"}))
        return 2
    path = sys.argv[1]
    try:
        audio, rate = sf.read(path, dtype="float32", always_2d=False)
        audio = np.asarray(audio, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != 16000 and len(audio):
            audio = resample_poly(audio, 16000, int(rate)).astype("float32")
        # The endpoint accepts short utterances; keep a stuck upload bounded.
        audio = audio[:16000 * 30]
        from transformers import pipeline

        recognizer = pipeline(
            "automatic-speech-recognition", model="openai/whisper-tiny.en", device=-1,
        )
        result = recognizer(audio)
        text = " ".join(str(result.get("text") or "").split())
        print(json.dumps({"text": text, "rate": 16000, "seconds": round(len(audio) / 16000, 2)}))
        return 0
    except Exception as error:
        print(json.dumps({"text": "", "error": str(error)[:500]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
