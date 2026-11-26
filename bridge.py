"""The Windows client bridge: the measured path from Debian to the CUA fleet.

The toast is the only authority for acts on this Windows desktop. A reverse SSH tunnel
gives the Debian box a loopback URL to the toast's token-gated listener, and this module
is the machinery around that one path:

* `TunnelSupervisor` keeps the tunnel open. It asks sshd for a port (`-R 0:`), reads the
  port actually allocated, then heartbeats `/api/bridge/health` from the Debian side. Two
  missed beats close the tunnel and open a new one with bounded backoff, and every flap
  is a counted row instead of a silent stall.
* `BridgeLedger` makes an act idempotent across a flapping tunnel. A key names one act: a
  replay returns the first receipt instead of clicking twice. A client's sequence must
  increase; a regressed sequence is refused by name.
* `BridgeClient` is the Debian side. It spools an act before sending it, retries transport
  failures with backoff, drains the spool after a reconnect, and treats a named refusal as
  a delivered result rather than a transport error.

Nothing here decides whether an act is allowed. The fleet's declared vocabulary and the
driver receipts remain that authority; this module only makes the transport trustworthy.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import hosts

SCHEMA = "popit.windows-bridge/1"
LEDGER_SCHEMA = "popit.bridge-ledger/1"
SPOOL_SCHEMA = "popit.bridge-spool/1"
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{7,95}$")
DISTRO = "Debian"
KEY = "m0/id_ed25519"


def iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def new_key(prefix: str = "bridge") -> str:
    """A key the ledger accepts: lower case, at least eight characters."""
    import secrets
    folded = re.sub(r"[^a-z0-9._:-]+", "-", str(prefix or "bridge").lower()).strip("-")
    return (folded or "bridge")[:60] + "." + secrets.token_hex(6)


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


def _compact(receipt: dict, limit: int = 4000) -> dict:
    """A receipt small enough to persist, complete enough to answer a replay."""
    kept = {}
    for name in ("id", "driver", "status", "at", "finished", "refusal", "key"):
        if receipt.get(name) not in (None, ""):
            kept[name] = receipt[name]
    results = []
    for result in receipt.get("results") or []:
        if not isinstance(result, dict):
            continue
        row = {}
        for name, value in list(result.items())[:14]:
            if isinstance(value, (str, int, float, bool)) or value is None:
                row[name] = value[:200] if isinstance(value, str) else value
            elif isinstance(value, list) and len(value) <= 8:
                row[name] = value
            elif isinstance(value, dict) and name in ("window", "cursor"):
                row[name] = {k: v for k, v in list(value.items())[:6]
                             if isinstance(v, (str, int, float, bool))}
        results.append(row)
    if results:
        kept["results"] = results
    body = json.dumps(kept, ensure_ascii=False)
    if len(body) > limit:
        kept.pop("results", None)
    return kept


def _wsl(remote: str, timeout: float = 20.0) -> subprocess.CompletedProcess:
    """Run one command on the Debian host through the same root key the view uses."""
    script = (
        "cd /root; PATH=/usr/bin:/bin /usr/bin/ssh -o BatchMode=yes "
        f"-o ConnectTimeout=5 -i {KEY} root@{hosts.debian_host()} {shlex.quote(remote)}"
    )
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "--", "sh", "-c", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=0x08000000,
    )


# -- the tunnel ---------------------------------------------------------------

class Tunnel:
    """One `ssh -R 0:` forward from the Debian loopback to the toast listener."""

    def __init__(self, target_host: str, target_port: int, *, host: str = "",
                 distro: str = DISTRO, key: str = KEY) -> None:
        self.target_host = target_host
        self.target_port = int(target_port)
        self.host = host or hosts.debian_host()
        self.distro = distro
        self.key = key
        self.process: subprocess.Popen | None = None
        self.port = 0
        self.error = ""
        self.opened_at = ""
        self._ready = threading.Event()

    def open(self, wait: float = 12.0) -> int:
        self.close()
        self.port = 0
        self.error = ""
        self._ready = threading.Event()
        script = (
            "cd /root; PATH=/usr/bin:/bin exec /usr/bin/ssh -N -v "
            "-o ExitOnForwardFailure=yes -o ServerAliveInterval=8 "
            "-o ServerAliveCountMax=3 -o TCPKeepAlive=yes "
            f"-R 0:{self.target_host}:{self.target_port} -i {self.key} root@{self.host}"
        )
        try:
            self.process = subprocess.Popen(
                ["wsl.exe", "-d", self.distro, "-u", "root", "--", "sh", "-c", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
                creationflags=0x08000000,
            )
        except OSError as error:
            raise Refused("bridge-tunnel-spawn", str(error)[:240]) from error
        threading.Thread(target=self._read, daemon=True).start()
        if not self._ready.wait(wait) or not self.port:
            detail = self.error or "the Debian sshd did not allocate a reverse port"
            self.close()
            raise Refused("bridge-tunnel", detail[:300])
        self.opened_at = iso()
        return self.port

    def _read(self) -> None:
        for line in self.process.stderr or [] if self.process else []:
            match = re.search(r"Allocated port (\d+)", line)
            if match:
                self.port = int(match.group(1))
                self._ready.set()
            if ("remote forward failure" in line or "Permission denied" in line
                    or "Connection refused" in line or "closed by remote host" in line):
                self.error = line.strip()[:300]
                self._ready.set()

    def close(self) -> None:
        process, self.process = self.process, None
        self.port = 0
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()

    def alive(self) -> bool:
        return bool(self.process and self.process.poll() is None and self.port)


class TunnelSupervisor:
    """Keep the bridge tunnel open and measured; a flap is a counted, named row."""

    def __init__(self, token: str, *, target_host: str = "", target_port: int = 5208,
                 interval: float = 6.0, misses: int = 2, host: str = "",
                 distro: str = DISTRO, key: str = KEY, target_file: pathlib.Path | None = None,
                 backoff: float = 1.0, max_backoff: float = 30.0) -> None:
        self.token = token
        self.target_host = target_host or hosts.lan_host()
        self.target_port = int(target_port)
        self.interval = max(2.0, interval)
        self.misses = max(1, misses)
        self.host = host or hosts.debian_host()
        self.distro = distro
        self.key = key
        self.target_file = target_file
        self.tunnel = Tunnel(self.target_host, self.target_port, host=self.host,
                             distro=distro, key=key)
        self.lock = threading.RLock()
        self.state_name = "stopped"
        self.detail = ""
        self.port = 0
        self.beats = 0
        self.flaps = 0
        self.restarts = 0
        self.missed = 0
        self.last_beat = ""
        self.last_error = ""
        self.heartbeat: dict = {}
        self.history: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._backoff = max(0.5, backoff)
        self._max_backoff = max(self._backoff, max_backoff)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.state_name = "starting"
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self.lock:
            self.tunnel.close()
            self.port = 0
            self.state_name = "stopped"

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.tunnel.alive():
                    self._open()
                if self.tunnel.alive():
                    self._beat()
            except Refused as error:
                with self.lock:
                    self.last_error = f"{error.code}: {error.detail}"[:300]
                self._flap(error.detail)
            except Exception as error:  # a supervisor failure must not kill the toast
                with self.lock:
                    self.last_error = str(error)[:300]
                self._flap(str(error))
            self._stop.wait(self.interval)

    def _open(self) -> None:
        with self.lock:
            self.state_name = "opening"
        port = self.tunnel.open()
        with self.lock:
            self.port = port
            self.state_name = "live"
            self.detail = ""
            self.missed = 0
            self._backoff = 1.0
        self._write_target()

    def _flap(self, detail: str) -> None:
        self.tunnel.close()
        with self.lock:
            self.flaps += 1
            self.port = 0
            self.state_name = "degraded"
            self.detail = str(detail or "the bridge tunnel dropped")[:300]
            wait = self._backoff
            self._backoff = min(self._max_backoff, self._backoff * 2)
            self.history = (self.history + [{"at": iso(), "detail": self.detail}])[-8:]
        # Bounded backoff: a Debian box that is asleep is retried, never hammered.
        self._stop.wait(wait)
        if self._stop.is_set():
            return
        try:
            self._restart()
        except Refused as error:
            with self.lock:
                self.last_error = f"{error.code}: {error.detail}"[:300]

    def _restart(self) -> None:
        port = self.tunnel.open()
        with self.lock:
            self.restarts += 1
            self.port = port
            self.state_name = "live"
            self.detail = ""
            self.missed = 0
            self._backoff = 1.0
        self._write_target()

    def _beat(self) -> None:
        port = self.tunnel.port
        if not port:
            raise Refused("bridge-port", "the tunnel has no allocated port")
        remote = (
            "curl -sS --max-time 4 -w '\\n%{http_code}' "
            f"'http://127.0.0.1:{port}/api/bridge/health?token={self.token}'"
        )
        result = _wsl(remote, timeout=10)
        body, _, code = (result.stdout or "").rpartition("\n")
        code = code.strip()
        payload: dict = {}
        try:
            payload = json.loads(body) if body.strip().startswith("{") else {}
        except json.JSONDecodeError:
            payload = {}
        if code != "200" or not payload.get("ok"):
            with self.lock:
                self.missed += 1
                self.last_error = (f"heartbeat {code or 'no-code'}"
                                   + (f": {body.strip()[:160]}" if body.strip() else ""))
            if self.missed >= self.misses:
                raise Refused("bridge-heartbeat", self.last_error)
            return
        with self.lock:
            self.missed = 0
            self.beats += 1
            self.last_beat = iso()
            self.state_name = "live"
            self.detail = ""
            self.heartbeat = {
                "toast_at": (payload.get("toast") or {}).get("at", ""),
                "revision": (payload.get("toast") or {}).get("revision"),
                "ledger": payload.get("ledger") or {},
                "drivers": len(payload.get("drivers") or []),
                "port": port,
                "at": self.last_beat,
            }
        self._write_target()

    def _write_target(self) -> None:
        """Leave the live URL where a Debian-side script can read it."""
        if self.target_file is None or not self.port:
            return
        try:
            self.target_file.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "schema": SCHEMA,
                "url": f"http://127.0.0.1:{self.port}",
                "token": self.token,
                "port": self.port,
                "host": self.host,
                "at": iso(),
            }
            temporary = self.target_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.target_file)
        except OSError as error:
            with self.lock:
                self.last_error = f"bridge-target: {error}"[:300]

    # -- reading ------------------------------------------------------------
    def state(self) -> dict:
        with self.lock:
            age = None
            if self.last_beat:
                try:
                    moment = datetime.datetime.fromisoformat(self.last_beat)
                    age = int((datetime.datetime.now(datetime.timezone.utc) - moment)
                              .total_seconds())
                except ValueError:
                    age = None
            url = f"http://127.0.0.1:{self.port}" if self.port else ""
            return {
                "schema": SCHEMA,
                "state": self.state_name,
                "detail": self.detail,
                "last_error": self.last_error,
                "port": self.port,
                "url": url,
                "target": f"{self.target_host}:{self.target_port}",
                "host": self.host,
                "beats": self.beats,
                "missed": self.missed,
                "flaps": self.flaps,
                "restarts": self.restarts,
                "last_beat": self.last_beat,
                "beat_age": age,
                "opened_at": self.tunnel.opened_at,
                "heartbeat": dict(self.heartbeat),
                "history": list(self.history),
            }


# -- the ledger ---------------------------------------------------------------

class BridgeLedger:
    """Durable idempotency: one key names one act, and its receipt survives a restart."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.rows: list[dict] = []
        self.counters = {"accepted": 0, "replayed": 0, "refused": 0}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(value, dict):
            return
        self.rows = [row for row in value.get("rows", [])
                     if isinstance(row, dict) and row.get("key")][-500:]
        counters = value.get("counters")
        if isinstance(counters, dict):
            for name in self.counters:
                try:
                    self.counters[name] = int(counters.get(name) or 0)
                except (TypeError, ValueError):
                    pass

    def _save(self) -> None:
        payload = {"schema": LEDGER_SCHEMA, "counters": self.counters, "rows": self.rows}
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
        temporary.replace(self.path)

    def _row(self, key: str) -> dict | None:
        return next((row for row in reversed(self.rows) if row.get("key") == key), None)

    def accept(self, key: str, route: str, digest: str, *, seq: int | None = None,
               client: str = "") -> dict | None:
        """Return the held row for a replay, None for a new act, or refuse by name."""
        if not key or not KEY_RE.fullmatch(key):
            with self.lock:
                self.counters["refused"] += 1
                self._save()
            raise Refused("bridge-key", f"{str(key)[:80]!r} is not a bridge act key")
        with self.lock:
            held = self._row(key)
            if held is not None:
                if held.get("digest") != digest:
                    self.counters["refused"] += 1
                    self._save()
                    raise Refused("bridge-key-reused",
                                  f"{key} already names a different act")
                held["replays"] = int(held.get("replays") or 0) + 1
                self.counters["replayed"] += 1
                self._save()
                return dict(held)
            if seq is not None:
                last = max((int(row.get("seq") or 0) for row in self.rows
                            if row.get("client") == client), default=0)
                if int(seq) <= last:
                    self.counters["refused"] += 1
                    self._save()
                    raise Refused("bridge-seq-regressed",
                                  f"seq {seq} is not above {last} for {client or 'local'}")
            return None

    def record(self, key: str, route: str, digest: str, *, task: dict, seq: int | None = None,
               client: str = "") -> dict:
        row = {
            "key": key, "route": route, "digest": digest, "task": task.get("id", ""),
            "driver": task.get("driver", ""), "actions": task.get("actions", 0),
            "status": task.get("status", "queued"), "state": "accepted",
            "seq": int(seq) if seq is not None else None, "client": client,
            "replays": 0, "detail": "", "at": iso(), "settled": "",
        }
        with self.lock:
            self.rows = (self.rows + [row])[-500:]
            self.counters["accepted"] += 1
            self._save()
            return dict(row)

    def settle(self, key: str, receipt: dict) -> dict | None:
        """Keep the receipt, not just its status: a restart must not lose what happened."""
        with self.lock:
            row = self._row(key)
            if row is None:
                return None
            row["status"] = str(receipt.get("status") or row.get("status") or "queued")
            row["state"] = "refused" if receipt.get("refusal") else row["state"]
            row["detail"] = json.dumps(receipt.get("refusal") or {})[:300]
            row["receipt"] = _compact(receipt)
            row["settled"] = iso()
            self._save()
            return dict(row)

    def by_task(self, task_id: str) -> dict | None:
        """Find the ledger row that produced a task id, for a receipt after a restart."""
        with self.lock:
            return next((dict(row) for row in reversed(self.rows)
                         if row.get("task") == task_id), None)

    def state(self) -> dict:
        with self.lock:
            rows = []
            for row in self.rows[-24:][::-1]:
                item = {key: value for key, value in row.items() if key != "receipt"}
                receipt = row.get("receipt") or {}
                item["receipt_id"] = receipt.get("id", "")
                item["receipt_status"] = receipt.get("status", "")
                rows.append(item)
            return {
                "schema": LEDGER_SCHEMA,
                "counters": dict(self.counters),
                "rows": rows,
                "clients": sorted({row.get("client") or "local" for row in self.rows}),
            }


# -- the Debian side ----------------------------------------------------------

class BridgeClient:
    """A retrying, spooling client for the toast bridge. Stdlib only, runs on Debian."""

    def __init__(self, base_url: str, token: str, *, spool: pathlib.Path | None = None,
                 attempts: int = 3, timeout: float = 10.0, client: str = "debian") -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.token = str(token or "")
        self.spool = pathlib.Path(spool) if spool else None
        self.attempts = max(1, int(attempts))
        self.timeout = max(2.0, float(timeout))
        self.client = str(client or "debian")

    @classmethod
    def from_target(cls, path: pathlib.Path, **kwargs) -> "BridgeClient":
        try:
            value = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise Refused("bridge-target", f"{path}: {error}") from error
        if not isinstance(value, dict) or not value.get("url"):
            raise Refused("bridge-target", f"{path} carries no bridge url")
        return cls(str(value["url"]), str(value.get("token") or ""), **kwargs)

    # -- spool --------------------------------------------------------------
    def _read_spool(self) -> dict:
        if self.spool is None or not self.spool.exists():
            return {"schema": SPOOL_SCHEMA, "rows": []}
        try:
            value = json.loads(self.spool.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema": SPOOL_SCHEMA, "rows": []}
        if not isinstance(value, dict) or not isinstance(value.get("rows"), list):
            return {"schema": SPOOL_SCHEMA, "rows": []}
        return value

    def _write_spool(self, value: dict) -> None:
        if self.spool is None:
            return
        self.spool.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.spool.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.spool)

    def _spool_add(self, row: dict) -> None:
        value = self._read_spool()
        value["rows"] = [item for item in value["rows"] if item.get("key") != row["key"]]
        value["rows"].append(row)
        self._write_spool(value)

    def _spool_drop(self, key: str) -> None:
        value = self._read_spool()
        value["rows"] = [item for item in value["rows"] if item.get("key") != key]
        self._write_spool(value)

    def spooled(self) -> list[dict]:
        return list(self._read_spool()["rows"])

    # -- transport ----------------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None = None,
                 timeout: float | None = None, headers: dict | None = None) -> tuple[int, dict]:
        if not self.base_url:
            raise Refused("bridge-url", "no bridge url is configured")
        query = {"token": self.token} if self.token else {}
        url = self.base_url + path
        if query:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            request.add_header(name, str(value))
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as reply:
                return reply.status, json.loads(reply.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                return error.code, {"ok": False, "refused": {"code": "bridge-http",
                                                             "detail": str(error.code)}}
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise Refused("bridge-offline", str(error)[:240]) from error

    def health(self) -> dict:
        status, payload = self._request("GET", "/api/bridge/health")
        if status != 200 or not payload.get("ok"):
            raise Refused("bridge-refused", json.dumps(payload.get("refused") or {})[:240])
        return payload

    def receipt(self, task_id: str) -> dict:
        status, payload = self._request("GET", f"/api/bridge/receipt/{task_id}")
        if status != 200 or not payload.get("ok"):
            raise Refused("bridge-refused", json.dumps(payload.get("refused") or {})[:240])
        return payload

    def cua(self, actions: list[dict], *, driver: str = "", key: str = "",
            seq: int | None = None, wait: float = 12.0) -> dict:
        if not isinstance(actions, list) or not actions:
            raise Refused("bridge-actions", "actions must be a non-empty list")
        key = key or new_key("ide")
        if not KEY_RE.fullmatch(key):
            raise Refused("bridge-key", f"{key!r} is not a bridge act key")
        if seq is None:
            seq = time.time_ns() // 1_000_000
        row = {"key": key, "seq": int(seq), "driver": driver, "actions": actions,
               "wait": float(wait), "at": iso(), "attempts": 0}
        self._spool_add(row)
        body = {"key": key, "seq": int(seq), "client": self.client, "driver": driver,
                "actions": actions, "wait": float(wait)}
        headers = {"X-Popit-Bridge-Key": key, "X-Popit-Bridge-Seq": str(int(seq))}
        last: Refused | None = None
        for attempt in range(self.attempts):
            row["attempts"] = attempt + 1
            try:
                status, payload = self._request(
                    "POST", "/api/bridge/cua", body,
                    timeout=max(self.timeout, float(wait) + 8.0), headers=headers)
            except Refused as error:
                last = error
                time.sleep(min(8.0, 0.4 * (2 ** attempt)))
                continue
            # A delivery is a delivery: a named refusal is the receipt, not a transport error.
            self._spool_drop(key)
            if status != 200 or not payload.get("ok"):
                refusal = payload.get("refused") or {"code": "bridge-refused",
                                                     "detail": f"http {status}"}
                raise Refused(str(refusal.get("code") or "bridge-refused"),
                              str(refusal.get("detail") or "")[:300])
            return payload
        self._spool_add({**row, "attempts": self.attempts})
        raise last or Refused("bridge-offline", "no attempt reached the toast")

    def drain(self) -> list[dict]:
        """Replay every spooled act after a reconnect; the key makes each replay safe."""
        results: list[dict] = []
        for row in self.spooled():
            try:
                payload = self.cua(list(row.get("actions") or []),
                                   driver=str(row.get("driver") or ""),
                                   key=str(row.get("key") or ""),
                                   seq=int(row.get("seq") or 0),
                                   wait=float(row.get("wait") or 12.0))
                results.append({"key": row.get("key"), "ok": True,
                                "task": (payload.get("task") or {}).get("id", ""),
                                "replayed": bool(payload.get("replayed"))})
            except Refused as error:
                results.append({"key": row.get("key"), "ok": False, "refused": error.as_dict()})
        return results
