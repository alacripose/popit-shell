"""Desk sign-in for a remote browser.

A caller does not get the desk by reaching the port. It signs the same Ed25519 envelope a
call uses, carrying the capability ``desk.access``; the host verifies the signature against
the envelope trust registry and spends the nonce before it issues a session. A browser that
cannot hold a private key enrols once with a one-time desk code minted on this machine, and
from then on presents a session cookie: HttpOnly, Secure, SameSite=Strict, hashed at rest,
expiring and revocable by name.

Nothing here lowers TLS. The remote listener serves the session cookie over its own TLS
listener only, and the sign-in page is the only surface it answers without one.
"""
from __future__ import annotations

import datetime
import hmac
import json
import pathlib
import secrets
import threading
from http.cookies import SimpleCookie

from blake3 import blake3

import envelope

COOKIE = "popit_desk"
SESSION_SCHEMA = "popit.desk-sessions/1"
CODE_SCHEMA = "popit.desk-codes/1"
SESSION_DAYS = 30
CODE_MINUTES = 10
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_ROWS = 500


class Refused(Exception):
    """A named refusal, so the sign-in page can say why instead of "failed"."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def _stamp(value: datetime.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse(text: str) -> datetime.datetime:
    parsed = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def digest(value: str) -> str:
    return "blake3:" + blake3(str(value).encode("utf-8")).hexdigest()


def normalize_code(value: str) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


class Store:
    """The host's own session and code ledger, one file each under runlogs/toast."""

    def __init__(self, directory: pathlib.Path | str,
                 days: int = SESSION_DAYS, code_minutes: int = CODE_MINUTES) -> None:
        self.dir = pathlib.Path(directory)
        self.path = self.dir / "desk-sessions.json"
        self.codes_path = self.dir / "desk-codes.json"
        self.days = days
        self.code_minutes = code_minutes
        self.lock = threading.RLock()

    # -- files -----------------------------------------------------------------
    def _read(self, path: pathlib.Path, schema: str) -> list[dict]:
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = value.get("rows") if isinstance(value, dict) else None
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _write(self, path: pathlib.Path, schema: str, rows: list[dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": schema, "rows": rows[-MAX_ROWS:]},
                                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _live(self, rows: list[dict]) -> list[dict]:
        current = _now()
        live = []
        for row in rows:
            try:
                if _parse(row.get("expires") or "") > current:
                    live.append(row)
            except (TypeError, ValueError):
                continue
        return live

    # -- sessions --------------------------------------------------------------
    def create(self, caller: str, fingerprint: str = "", mode: str = "envelope") -> tuple[str, dict]:
        token = secrets.token_urlsafe(32)
        current = _now()
        row = {
            "id": digest(token)[7:23],
            "token": digest(token),
            "caller": " ".join(str(caller or "").split())[:60] or "remote",
            "fingerprint": str(fingerprint or ""),
            "mode": mode,
            "created": _stamp(current),
            "expires": _stamp(current + datetime.timedelta(days=self.days)),
            "last": _stamp(current),
        }
        with self.lock:
            rows = self._live(self._read(self.path, SESSION_SCHEMA))
            rows.append(row)
            self._write(self.path, SESSION_SCHEMA, rows)
        return token, dict(row)

    def lookup(self, token: str) -> dict | None:
        if not token:
            return None
        wanted = digest(token)
        with self.lock:
            rows = self._read(self.path, SESSION_SCHEMA)
            live = self._live(rows)
            found = None
            for row in live:
                if hmac.compare_digest(str(row.get("token") or ""), wanted):
                    row["last"] = _stamp(_now())
                    found = row
            if len(live) != len(rows) or found is not None:
                self._write(self.path, SESSION_SCHEMA, live)
            return dict(found) if found else None

    def sessions(self) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self._live(self._read(self.path, SESSION_SCHEMA))]

    def revoke(self, ident: str = "") -> int:
        with self.lock:
            rows = self._live(self._read(self.path, SESSION_SCHEMA))
            wanted = str(ident or "").strip()
            if wanted:
                keep = [row for row in rows
                        if wanted not in (row.get("id"), row.get("caller"), row.get("fingerprint"))]
            else:
                keep = []
            removed = len(rows) - len(keep)
            self._write(self.path, SESSION_SCHEMA, keep)
            return removed

    # -- one-time codes --------------------------------------------------------
    def mint_code(self, caller: str = "remote") -> dict:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        current = _now()
        row = {"code": digest(normalize_code(code)), "caller": str(caller or "remote")[:60],
               "created": _stamp(current),
               "expires": _stamp(current + datetime.timedelta(minutes=self.code_minutes)),
               "used": False}
        with self.lock:
            rows = self._live(self._read(self.codes_path, CODE_SCHEMA))
            rows.append(row)
            self._write(self.codes_path, CODE_SCHEMA, rows)
        return {"code": code, "expires": row["expires"], "caller": row["caller"]}

    def take_code(self, code: str) -> dict:
        wanted = digest(normalize_code(code))
        if not normalize_code(code):
            raise Refused("desk-code-empty", "a desk code is eight characters")
        with self.lock:
            rows = self._live(self._read(self.codes_path, CODE_SCHEMA))
            found = None
            for row in rows:
                if row.get("used"):
                    continue
                if hmac.compare_digest(str(row.get("code") or ""), wanted):
                    row["used"] = True
                    row["used_at"] = _stamp(_now())
                    found = row
                    break
            self._write(self.codes_path, CODE_SCHEMA, rows)
            if found is None:
                raise Refused("desk-code", "that code is not live on this machine")
            return dict(found)


def cookie_for(token: str, days: int = SESSION_DAYS) -> str:
    return (f"{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; "
            f"Max-Age={int(days * 86400)}")


def cookie_clear() -> str:
    return f"{COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0"


def token_from(cookie_header: str) -> str:
    if not cookie_header:
        return ""
    jar = SimpleCookie()
    try:
        jar.load(cookie_header)
    except Exception:
        return ""
    morsel = jar.get(COOKIE)
    return morsel.value if morsel is not None else ""


def session_for(store: Store, cookie_header: str) -> dict | None:
    return store.lookup(token_from(cookie_header))


def admit_envelope(store: Store, package: object, *, trust_path: pathlib.Path,
                   nonce_path: pathlib.Path) -> tuple[str, dict, dict]:
    """Spend a signed desk package: signature, trust, window and nonce, then a session."""
    if not isinstance(package, dict):
        raise Refused("envelope-required",
                      "POST the signed package this machine minted for the desk")
    try:
        admission = envelope.admit(package, trust_path=trust_path, nonce_path=nonce_path,
                                   capability="desk.access")
    except envelope.Refused as error:
        raise Refused(error.code, error.detail) from error
    token, row = store.create(admission["caller"], admission["fingerprint"], "envelope")
    return token, admission, row


def admit_code(store: Store, code: str) -> tuple[str, dict, dict]:
    row = store.take_code(code)
    token, session = store.create(row.get("caller") or "remote", "desk-code", "code")
    return token, row, session
