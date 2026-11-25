"""Shared, append-only conversation archive for the Popit toast and Debian window.

Rows are the speech and actions the system actually took: the owner's transcript, Buffy's
host handoffs, the Debian mind's answers, tool calls with their exit codes, axis answers,
and commands. The Debian page and the LLM's `archive.read` tool read these same rows.
"""
from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import threading

SCHEMA = "popit.archive/1"
HALLUCINATION_PHRASES = (
    "thank you for watching", "thanks for watching", "thank you so much for watching",
    "please subscribe", "see you in the next video", "i'll see you in the next video",
    "i will see you in the next video", "see you next time", "i'll see you next time",
    "see you in the next one", "i'll see you in the next one",
)
SIGN_OFF = re.compile(
    r"\b(?:thank you for watching|thanks for watching|please subscribe|"
    r"(?:i'?ll )?see you (?:in )?(?:the )?next (?:video|time|one))\b"
)


def is_hallucination(text: str) -> bool:
    """Detect a quiet-microphone ASR artifact, including repeated sign-offs.

    This is deliberately scoped to owner-microphone input. It is never applied to an
    agent's outgoing line; an agent may quote any of these phrases normally.
    """
    clean = " ".join(str(text or "").lower().replace("’", "'").split())
    if not clean:
        return False
    stripped = clean.strip(" .!?,;: ")
    if stripped in HALLUCINATION_PHRASES:
        return True
    hits = sum(clean.count(phrase) for phrase in HALLUCINATION_PHRASES)
    if hits >= 2:
        return True
    words = re.findall(r"[a-z']+", clean)
    if SIGN_OFF.search(clean) and len(words) <= 14:
        return True
    if len(clean) > 140 and hits >= 1:
        return True
    if len(words) >= 8:
        token, frequency = collections.Counter(words).most_common(1)[0]
        if frequency >= 6 and frequency / len(words) > 0.45:
            return True
    return False


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Archive:
    def __init__(self, path: pathlib.Path, limit: int = 500) -> None:
        self.path = path
        self.limit = limit
        self.lock = threading.RLock()
        self.rows: list[dict] = []
        self.quarantine_path = path.with_name(path.stem + "-quarantine.json")
        self.quarantine: set[str] = set()
        self._next = 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            saved = json.loads(self.quarantine_path.read_text(encoding="utf-8"))
            if isinstance(saved, list):
                self.quarantine = {str(item) for item in saved if item}
        except (OSError, json.JSONDecodeError):
            pass
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("text"):
                    self.rows.append(row)
                    self._next = max(self._next, int(row.get("id") or 0) + 1)
            self.rows = self.rows[-self.limit:]

    def add(self, kind: str, text: str, *, role: str = "", **extra) -> dict:
        clean = " ".join(str(text or "").split())
        if not clean:
            return {}
        # The quiet-microphone artifact must not enter the live document at all.
        # This guard is only for owner input; agent rows are never filtered here.
        if kind == "user" and is_hallucination(clean):
            return {}
        with self.lock:
            row = {"schema": SCHEMA, "id": self._next, "at": iso(),
                   "kind": kind, "role": role or kind, "text": clean}
            row.update({key: value for key, value in extra.items() if value is not None})
            self._next += 1
            self.rows = (self.rows + [row])[-self.limit:]
            with self.path.open("a", encoding="utf-8") as log:
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
            return dict(row)

    @staticmethod
    def _key(row: dict) -> str:
        return f"{row.get('id')}:{row.get('at')}"

    def _visible(self, row: dict) -> bool:
        return self._key(row) not in self.quarantine

    def _save_quarantine(self) -> None:
        self.quarantine_path.write_text(
            json.dumps(sorted(self.quarantine), indent=2) + "\n", encoding="utf-8",
        )

    def repair_hallucinations(self) -> list[dict]:
        """Quarantine quiet-mic ASR artifacts and the replies they caused.

        The archive remains append-only; a correction event records the repair, while
        the bad owner row and any cua row whose question was that row are hidden from
        the live document and the archive reader. Agent output is never scanned.
        """
        repaired: list[dict] = []
        with self.lock:
            for row in self.rows:
                kind = row.get("kind")
                if kind == "user":
                    sample = row.get("text")
                elif kind == "cua":
                    sample = row.get("question")
                else:
                    continue
                if not is_hallucination(sample):
                    continue
                key = self._key(row)
                if key in self.quarantine:
                    continue
                self.quarantine.add(key)
                repaired.append(dict(row))
            if repaired:
                self._save_quarantine()
        if repaired:
            ids = ", ".join(str(row.get("id")) for row in repaired[:8])
            self.add("event", f"microphone hallucination quarantined · {len(repaired)} row(s) · {ids}",
                     role="repair", source="archive", quarantined=len(repaired))
        return repaired

    def read(self, limit: int = 30) -> list[dict]:
        count = max(1, min(200, int(limit or 30)))
        with self.lock:
            return [dict(row) for row in self.rows if self._visible(row)][-count:]

    def state(self) -> dict:
        with self.lock:
            visible = [dict(row) for row in self.rows if self._visible(row)]
            return {"schema": SCHEMA, "count": len(visible),
                    "rows": visible[-200:]}
