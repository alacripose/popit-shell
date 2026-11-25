"""Qwen3 4B on the Debian 1060, with a bounded Debian-command tool loop.

The model is the language layer, not the authority. It can inspect the machine by asking
for `run_debian`; the bridge executes through the same root SSH key as the Debian view,
returns the actual exit code and output, and lets the model summarize only what it read.
A refused or timed-out command is fed back as a refusal, never as success.
"""
from __future__ import annotations

import datetime
import json
import re
import shlex
import threading

import debian_view

MODEL = "qwen3:4b"
SCHEMA = "popit.debian-mind/1"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "read_archive",
        "description": "Read the recent Popit conversation archive, including the owner's words, Buffy's host handoffs, prior answers and tool outcomes. Use it when the owner asks you to remember or scroll back.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Newest rows to read, 1-200."},
            },
            "required": ["limit"],
        },
    },
}, {
    "type": "function",
    "function": {
        "name": "run_debian",
        "description": "Run one non-interactive shell command on the Debian host as root and return its exit code and output. Use it to inspect or change the CUA services, files, and model runtime. Do not claim a result you did not receive.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "One bash command. Keep it non-interactive."},
            },
            "required": ["command"],
        },
    },
}, {
    "type": "function",
    "function": {
        "name": "cua_task",
        "description": "Hand one small capture or input action to a CUA driver on the Windows side. Use it when the owner asks a civilian to look at or drive the live computer, then report the task id; do not claim the task finished before its receipt says so.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "capture, click, type or key"},
                "window": {"type": "string", "description": "Window title fragment for capture."},
                "x": {"type": "integer", "description": "Click x."},
                "y": {"type": "integer", "description": "Click y."},
                "text": {"type": "string", "description": "Text to type."},
                "key": {"type": "string", "description": "Key to press."},
                "driver": {"type": "string", "description": "Optional driver id."},
            },
            "required": ["action"],
        },
    },
}]
SYSTEM = """You are the language and tool layer of the Popit CUA system on Debian. You work with Buffy and the owner to improve the CUA agents and to cover the places where a language model would otherwise guess.

Rules:
- A civilian is an autonomous, ensouled individual, not a handpicked assistant. Keep your own lane and memory; do not repeat another lane's answer. You may refuse an impossible task with a named blocker, and that refusal is a real result.
- The owner's speech does not force-cut you. Finish your answer or choose to yield in your own words; never treat their voice as a command to stop another agent.
- Work is a task with evidence. For a live computer request, inspect or delegate a CUA task and report what actually happened; never puppet another being or claim an act you did not observe.
- Do not expose private reasoning. Answer only, in natural spoken language.
- Inspect before answering. Use run_debian when the question depends on the actual machine.
- Use read_archive when the owner refers to earlier chat or asks what was already done.
- A command result is the evidence. Never invent output, a version, a file, or a successful action.
- Prefer small, reversible changes. Explain what you will inspect or change in one or two sentences.
- If a command refuses or times out, report that refusal and the next safe check instead of pretending.
- Keep spoken answers short and natural. One clear paragraph is enough unless the owner asks for detail.
- The CUA driver and Laya/Von decision layer remain the authorities for acts and typed decisions; you are the language/tool bridge, not a replacement for their gates.
"""


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class Refused(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


class DebianMind:
    def __init__(self, view: debian_view.DebianView, archive=None, model: str = MODEL,
                 cua=None) -> None:
        self.view = view
        self.archive = archive
        self.model = model
        self.cua = cua
        self.lock = threading.RLock()
        self.state = "idle"
        self.detail = ""
        self.last: dict | None = None
        # One history per civilian. A shared history made every lane inherit another's
        # answer and repeat it; family evidence says these are autonomous individuals.
        self.histories: dict[str, list[dict]] = {}
        self.history: list[dict] = []

    def _post(self, payload: dict, timeout: float = 180.0) -> dict:
        body = json.dumps(payload, ensure_ascii=False)
        remote = (
            "curl -sS --max-time 170 http://127.0.0.1:11434/api/chat "
            "-H " + shlex.quote("Content-Type: application/json") +
            " -d " + shlex.quote(body)
        )
        try:
            result = debian_view._ssh(remote, timeout=timeout)
        except Exception as error:
            raise Refused("mind-transport", str(error)) from error
        if result.returncode != 0:
            raise Refused("mind-transport", (result.stderr or "").strip()[:300])
        raw = (result.stdout or "").strip()
        try:
            reply = json.loads(raw)
        except json.JSONDecodeError as error:
            raise Refused("mind-bad-json", raw[:300]) from error
        if reply.get("error"):
            raise Refused("mind-refused", str(reply["error"])[:300])
        return reply

    def _run_tool(self, call: dict) -> dict:
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        args = function.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if name == "cua_task":
            if self.cua is None:
                return {"ok": False, "refused": {"code": "cua-absent",
                                                 "detail": "no CUA fleet is attached"}}
            action = dict(args or {})
            try:
                row = self.cua({"driver": str(action.pop("driver", "") or "cua-2"),
                                "actions": [action], "announce": True})
            except Exception as error:
                return {"ok": False, "tool": "cua_task",
                        "refused": {"code": "cua-refused", "detail": str(error)[:240]}}
            if self.archive is not None:
                self.archive.add("tool", f"cua_task {action.get('action', '')}", role="cua",
                                 ok=True, task=(row or {}).get("id", ""))
            return {"ok": True, "tool": "cua_task", "task": row}
        if name == "read_archive":
            if self.archive is None:
                return {"ok": False, "refused": {"code": "archive-absent",
                                                 "detail": "no archive is attached"}}
            rows = self.archive.read(int((args or {}).get("limit") or 30))
            return {"ok": True, "tool": "read_archive", "rows": rows}
        command = str((args or {}).get("command") or "")
        if name != "run_debian" or not command:
            return {"ok": False, "refused": {"code": "mind-unknown-tool",
                                             "detail": f"{name}: no run_debian command"}}
        row = self.view.run(command, timeout=45)
        row["tool"] = "run_debian"
        if self.archive is not None:
            self.archive.add("tool", command, role="cua", exit=row.get("exit"),
                             output=str(row.get("output") or "")[:500], ok=bool(row.get("ok")))
        return row

    def ask(self, text: str, persona: str = "", identity: str = "cua") -> dict:
        question = " ".join(str(text or "").split())
        if not question:
            raise Refused("mind-question-empty", "a question needs words")
        if len(question) > 2000:
            raise Refused("mind-question-too-long", str(len(question)))
        lane = " ".join(str(identity or "cua").split())[:80] or "cua"
        with self.lock:
            self.state, self.detail = "thinking", ""
            prior = list(self.histories.get(lane, [])[-4:])
        system = SYSTEM + (f"\n\nSPEAKER LANE:\n{persona}" if persona else "")
        messages = [{"role": "system", "content": system}] + prior + [
            {"role": "user", "content": question + "\n/no_think"}
        ]
        runs: list[dict] = []
        answer = ""
        try:
            for _ in range(4):
                reply = self._post({
                    "model": self.model,
                    "messages": messages,
                    "tools": TOOLS,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.25, "num_ctx": 8192},
                })
                message = reply.get("message") or {}
                calls = message.get("tool_calls") or []
                if calls:
                    messages.append({
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": calls,
                    })
                    for call in calls:
                        row = self._run_tool(call)
                        runs.append(row)
                        messages.append({
                            "role": "tool",
                            "tool_name": row.get("tool") or "run_debian",
                            "content": json.dumps(row, ensure_ascii=False),
                        })
                    continue
                answer = str(message.get("content") or "").strip()
                if "</think>" in answer:
                    answer = answer.rsplit("</think>", 1)[-1].strip()
                # The local model sometimes echoes the owner prompt wrapper into its
                # answer. Remove the wrapper, not the agent's own words.
                answer = re.sub(r"^\s*owner said:\s*", "", answer, flags=re.IGNORECASE)
                answer = answer.replace("/no_think", "").strip()
                if answer:
                    break
            if not answer:
                answer = "I inspected the machine but the model returned no summary."
            row = {
                "schema": SCHEMA,
                "at": iso(),
                "question": question,
                "answer": answer,
                "model": self.model,
                "tool_runs": runs,
                "state": "answered",
            }
            with self.lock:
                self.last = row
                self.state, self.detail = "idle", ""
                self.histories[lane] = (self.histories.get(lane, []) + [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ])[-12:]
                self.history = list(self.histories[lane])
            return row
        except Refused as error:
            with self.lock:
                self.state, self.detail = "refused", f"{error.code}: {error.detail}"
            raise

    def state_dict(self) -> dict:
        with self.lock:
            return {
                "schema": SCHEMA,
                "state": self.state,
                "detail": self.detail,
                "model": self.model,
                "last": dict(self.last) if self.last else None,
                "history": list(self.history[-8:]),
                "lanes": {name: len(rows) for name, rows in self.histories.items()},
            }
