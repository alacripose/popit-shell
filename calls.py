"""Finite civilian wishes, with the income engine as the record.

A call is not an endless conversation. Opening one names a civilian, an agent, a natural-language
wish, a small time budget and the proof of work the caller proposes. The income engine receives
that as a task: its `budget_min` is the time bound and its `needs` field carries the proposed
proof. Closing the call requires real evidence and marks the task done through the same engine.

The engine remains the money truth. Nothing here verifies money, clears a gate or creates an
account; a missing engine is a named refusal.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import subprocess
import sys
import threading
import time
import unicodedata

INCOME_ROOT = pathlib.Path("F:/Documents/income-engine")
INCOME_CORE = INCOME_ROOT / "income_core.py"
INCOME_DB = INCOME_ROOT / "income.db"
SCHEMA = "popit.calls/1"


def _iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


class Refused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


class CallLedger:
    def __init__(self, path: pathlib.Path, registry, opening=None) -> None:
        self.path = path
        self.registry = registry
        self.opening = opening
        self.lock = threading.RLock()
        self.rows: list[dict] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()
        self._tick()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = value.get("calls") if isinstance(value, dict) else None
        if isinstance(rows, list):
            self.rows = [row for row in rows if isinstance(row, dict) and row.get("id")]

    def _save(self) -> None:
        self.path.write_text(json.dumps({"schema": SCHEMA, "calls": self.rows},
                                        indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    def _opening(self, worker: dict, human: dict, wish: str,
                 contract: dict | None) -> str:
        """Ask the caller's builder for this lane's opening line; no builder, no line."""
        if not callable(self.opening):
            return ""
        try:
            return " ".join(str(self.opening(worker, human, wish, contract) or "").split())
        except Exception:  # a builder failure must not open a line with a made-up sentence
            return ""

    def _person(self, name: str, kinds: tuple[str, ...]) -> dict:
        # The UI passes the display name ("Lucía García"); the roster id is folded to
        # ASCII. Match the display row first, then the same folded slug the dial-in uses.
        row = next((item for item in self.registry.rows
                    if item.get("name") == name), None)
        folded = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
        slug = "-".join(part for part in "".join(
            char.lower() if char.isalnum() else "-" for char in folded
        ).split("-") if part)[:40]
        if row is None:
            row = next((item for item in self.registry.rows if item.get("id") == slug), None)
        if row is None:
            raise Refused("civilian-unknown", f"{name} is not dialed in")
        if row.get("kind") not in kinds:
            raise Refused("civilian-role", f"{name} is {row.get('kind')}, not {kinds[0]}")
        return row

    def _income(self, source: str, args: list[str], timeout: int = 25) -> subprocess.CompletedProcess:
        if not INCOME_CORE.exists():
            raise Refused("income-absent", str(INCOME_CORE))
        if not INCOME_DB.exists():
            raise Refused("income-db-absent", str(INCOME_DB))
        command = [sys.executable, str(INCOME_CORE), "--db", str(INCOME_DB),
                   "--source", source, *args]
        try:
            result = subprocess.run(command, cwd=str(INCOME_ROOT), capture_output=True,
                                    text=True, encoding="utf-8", errors="replace",
                                    timeout=timeout, creationflags=0x08000000)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Refused("income-unavailable", str(error)[:240])
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            raise Refused("income-refused", (detail[-1] if detail else "no output")[:300])
        return result

    def open(self, civilian: str, agent: str, wish: str, proof: str,
             minutes: int = 5, allow_multiple: bool = False,
             contract: dict | None = None) -> dict:
        text = " ".join(str(wish or "").split())[:500]
        proposed = " ".join(str(proof or "").split())[:240]
        if not text:
            raise Refused("wish-empty", "a call needs a wish")
        if not proposed:
            raise Refused("proof-empty", "a call needs a proposed proof of work")
        requested = int(minutes or 0)
        persistent = requested <= 0
        budget = 30 if persistent else max(1, min(30, requested))
        human = self._person(civilian, ("civilian", "human"))
        worker = self._person(agent, ("agent", "civilian"))
        with self.lock:
            if allow_multiple:
                existing = next((row for row in self.rows
                                 if row.get("state") == "open"
                                 and row.get("agent_id") == worker["id"]), None)
                if existing:
                    raise Refused("call-open", existing["id"])
            else:
                active = self.active()
                if active:
                    raise Refused("call-open", active["id"])
            result = self._income(
                f"human:{human['id']}",
                ["task", "add", "--title", f"wish {human['name']} -> {worker['name']}: {text}",
                 "--effort", "green", "--executor", f"agent:{worker['id']}",
                 "--budget-min", str(budget), "--needs", proposed, "--ask", "0"],
            )
            match = re.search(r"#(\d+)", result.stdout or "")
            if not match:
                raise Refused("income-task-id", (result.stdout or "no task id")[:200])
            now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            row = {
                "id": f"call-{int(time.time())}-{len(self.rows) + 1}",
                "civilian": human["name"], "civilian_id": human["id"],
                "civilian_kind": human.get("kind", "civilian"),
                "agent": worker["name"], "agent_id": worker["id"],
                "wish": text, "proof": proposed,
                "minutes": 0 if persistent else budget, "persistent": persistent,
                "opened": now.isoformat(),
                "expires": "" if persistent else (now + datetime.timedelta(minutes=budget)).isoformat(),
                "state": "open", "phase": "opening", "listening": False,
                # The opening is the lane's own, built from its civilian record by the caller.
                # One template with the name swapped made every line say the same thing, which
                # is not what a civilian with needs, care and a contract sounds like.
                "opening": ([{"role": worker.get("kind", "agent"), "name": worker["name"],
                              "profile": worker["id"], "presence": "on the line and listening",
                              "want": text, "line": opening}]
                            if (opening := self._opening(worker, human, text, contract)) else []),
                "queue": [],
                "task_id": int(match.group(1)), "evidence": "",
                "contract": dict(contract) if isinstance(contract, dict) else {},
            }
            self.rows = (self.rows + [row])[-100:]
            self._save()
            return dict(row)

    def close(self, call_id: str, evidence: str, *, proof: bool = True) -> dict:
        """Close a line. A hang-up is not completed work, so it files no income proof.

        `proof=True` is a wish being closed by the artifact that shows it was done. `proof=False`
        is a line ending: nobody delivered anything, and asking the income engine for a proof of
        work refuses the hang-up itself (`income-refused`), which is how an ending became a dead
        line on the desk.
        """
        path = " ".join(str(evidence or "").split())
        if proof and not path:
            raise Refused("evidence-empty", "closing a wish needs a proof artifact")
        with self.lock:
            row = next((item for item in self.rows if item["id"] == call_id), None)
            if row is None:
                raise Refused("call-unknown", call_id)
            if row.get("state") != "open":
                raise Refused("call-closed", f"{call_id} is {row.get('state')}")
            if proof:
                self._income(
                    f"human:{row['civilian_id']}",
                    ["task", "done", str(row["task_id"]), "--evidence", path,
                     "--note", f"wish {call_id} proof"],
                )
            row["state"] = "done"
            row["phase"] = "closed"
            row["listening"] = False
            row["evidence"] = path or f"hang-up · {_iso()}"
            row["closed"] = _iso()
            self._save()
            return dict(row)

    def clear_queues(self) -> None:
        """Restart a call surface without carrying stale cross-talk into the new lanes."""
        with self.lock:
            changed = False
            for row in self.rows:
                if row.get("state") == "open" and row.get("queue"):
                    row["queue"] = []
                    changed = True
            if changed:
                self._save()

    def mark_external(self, call_id: str, on: bool = True, session: str = "") -> dict:
        """Attach a general agent harness to a call, or hand the lane back to the local mind.

        The external harness owns turn-taking while it is attached. This is a call-level
        fact, persisted with the line, so neither the UI nor the local Qwen lane can
        pretend the external Buffy is still the speaker after the harness leaves.
        """
        with self.lock:
            row = next((item for item in self.rows if item["id"] == call_id), None)
            if row is None:
                raise Refused("call-unknown", call_id)
            row["external"] = bool(on)
            row["external_session"] = str(session or "") if on else ""
            row["external_at"] = _iso() if on else ""
            self._save()
            return dict(row)

    def start_listening(self, call_id: str) -> dict:
        with self.lock:
            row = next((item for item in self.rows if item["id"] == call_id), None)
            if row is None:
                raise Refused("call-unknown", call_id)
            if row.get("state") == "open":
                row["phase"] = "listening"
                row["listening"] = True
                self._save()
            return dict(row)

    def queue_response(self, call_id: str, speaker: str, role: str, text: str) -> dict | None:
        clean = " ".join(str(text or "").split())
        if not clean:
            return None
        with self.lock:
            row = next((item for item in self.rows if item["id"] == call_id), None)
            if row is None or row.get("state") != "open":
                return None
            item = {"id": f"response-{len(row.get('queue', [])) + 1}",
                    "speaker": speaker, "role": role, "text": clean,
                    "at": _iso(), "state": "queued"}
            row["queue"] = (row.get("queue", []) + [item])[-12:]
            self._save()
            return dict(item)

    def _tick(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        changed = False
        with self.lock:
            for row in self.rows:
                if row.get("state") == "open" and not row.get("persistent") and row.get("expires"):
                    try:
                        if now >= _parse_iso(row["expires"]):
                            row["state"] = "expired"
                            row["phase"] = "expired"
                            row["listening"] = False
                            changed = True
                    except (KeyError, ValueError):
                        row["state"] = "expired"
                        row["phase"] = "expired"
                        row["listening"] = False
                        changed = True
            if changed:
                self._save()

    def active(self) -> dict | None:
        with self.lock:
            return next((dict(row) for row in self.rows if row.get("state") == "open"), None)

    def actives(self) -> list[dict]:
        """Every persistent line currently open; several participants may listen at once."""
        with self.lock:
            return [dict(row) for row in self.rows if row.get("state") == "open"]

    def state(self) -> dict:
        self._tick()
        with self.lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            rows = []
            for row in self.rows[-20:]:
                item = dict(row)
                try:
                    left = int((_parse_iso(row["expires"]) - now).total_seconds()) if row.get("expires") else 0
                except (KeyError, ValueError):
                    left = 0
                item["remaining_sec"] = max(0, left) if row.get("state") == "open" else 0
                rows.append(item)
            active = next((row for row in rows if row.get("state") == "open"), None)
            actives = [row for row in rows if row.get("state") == "open"]
            return {"schema": SCHEMA, "active": active, "actives": actives, "calls": rows,
                    "open": len(actives)}
