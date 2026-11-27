"""Put the Popit archive window on the Debian LXDE desktop.

The toast stays the one server and one ledger. Debian's sshd allocates a loopback reverse port
for the tunnel (never a fixed port, which can be left held by a dead session), maps it to the
Windows toast's 5207, and Firefox on :0 opens `/archive` from that loopback port. The page polls
the same `/api/toast` state and reads the same archive rows.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import threading
import time

import hosts

ROOT = pathlib.Path(__file__).resolve().parent
DISTRO = "Debian"
HOST = hosts.debian_host()
KEY = "m0/id_ed25519"
TOAST_PORT = 5207
ARCHIVE_PORT = 5208
LOG = ROOT / "runlogs" / "toast" / "debian-window.log"


def _log(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {line}\n")


def _wsl(remote: str, timeout: float = 20.0) -> subprocess.CompletedProcess:
    import shlex
    script = (
        "cd /root; PATH=/usr/bin:/bin /usr/bin/ssh -o BatchMode=yes "
        f"-o ConnectTimeout=5 -i {KEY} root@{HOST} {shlex.quote(remote)}"
    )
    return subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "--", "sh", "-c", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=0x08000000,
    )


class DebianWindow:
    def __init__(self, *, target_host: str = "",
                 target_port: int = ARCHIVE_PORT, token: str = "") -> None:
        self.tunnel: subprocess.Popen | None = None
        self.remote_port = 0
        self.target_host = target_host or hosts.lan_host()
        self.target_port = target_port
        self.token = token
        self.state = "starting"
        self.detail = ""

    def start(self) -> None:
        self.stop()
        self.remote_port = 0
        try:
            script = (
                "cd /root; PATH=/usr/bin:/bin exec /usr/bin/ssh -N -v "
                "-o ExitOnForwardFailure=yes -o ServerAliveInterval=20 "
                f"-R 0:{self.target_host}:{self.target_port} -i {KEY} root@{HOST}"
            )
            self.tunnel = subprocess.Popen(
                ["wsl.exe", "-d", DISTRO, "-u", "root", "--", "sh", "-c", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", bufsize=1,
                creationflags=0x08000000,
            )
            ready = threading.Event()

            def read_stderr() -> None:
                assert self.tunnel is not None
                for line in self.tunnel.stderr or []:
                    match = re.search(r"Allocated port (\d+)", line)
                    if match:
                        self.remote_port = int(match.group(1))
                        ready.set()
                    if "remote forward failure" in line or "Permission denied" in line:
                        self.detail = line.strip()[:300]
                        _log(self.detail)
                        ready.set()

            threading.Thread(target=read_stderr, daemon=True).start()
            if not ready.wait(10) or not self.remote_port:
                self.state = "refused"
                self.detail = self.detail or "Debian did not allocate a reverse archive port"
                _log(self.detail)
                self.stop()
                return
            if not self._wait_remote(self.remote_port):
                self.state = "refused"
                self.detail = f"the Debian archive port {self.remote_port} did not answer"
                _log(self.detail)
                return
            self._launch_firefox(self.remote_port)
            if not self._firefox_running():
                self.state = "refused"
                self.detail = "Firefox did not start on the Debian desktop; see /tmp/popit-firefox.log"
                _log(self.detail)
                return
            self.state, self.detail = "live", ""
            _log(f"archive live on Debian :0 via 127.0.0.1:{self.remote_port}")
        except Exception as error:
            self.state, self.detail = "refused", str(error)[:300]
            _log(self.detail)

    def _wait_remote(self, port: int) -> bool:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                result = _wsl(
                    f"curl -sS --max-time 2 -o /dev/null -w '%{{http_code}}' "
                    f"http://127.0.0.1:{port}/archive?token={self.token}"
                )
                if (result.stdout or "").strip().startswith("200"):
                    return True
            except Exception:
                pass
            time.sleep(0.4)
        return False

    def _launch_firefox(self, port: int) -> None:
        # Firefox refuses to run as root inside a normal user's graphical session, and a
        # path without a prefs.js produces a Profile Missing dialog instead of the page.
        user = hosts.debian_user()
        home = f"/home/{user}"
        profile = f"{home}/.mozilla/firefox/popit.default"
        _wsl(f"pkill -u {user} firefox 2>/dev/null || true", timeout=8)
        _wsl(f"install -d -o {user} -g {user} -m 700 " + profile, timeout=8)
        command = (
            f"runuser -u {user} -- env HOME={home} DISPLAY=:0 "
            f"XAUTHORITY={home}/.Xauthority "
            "XDG_RUNTIME_DIR=/run/user/1000 "
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
            f"setsid firefox --no-remote --profile {profile} --kiosk "
            f"http://127.0.0.1:{port}/archive?token={self.token} "
            ">/tmp/popit-firefox.log 2>&1 < /dev/null & echo $!"
        )
        _wsl(command, timeout=15)
        time.sleep(5)

    def _firefox_running(self) -> bool:
        try:
            result = _wsl(
                f"pgrep -af 'firefox.*:{self.remote_port}/archive' | head -1", timeout=8)
            return bool((result.stdout or "").strip())
        except Exception:
            return False

    def stop(self) -> None:
        process, self.tunnel = self.tunnel, None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        # Same leak as the bridge: the ssh client lives inside WSL, and terminating the
        # Windows `wsl.exe` leaves it holding a forward. Stop this window's own forward.
        try:
            _wsl(f"/usr/bin/pkill -f 'ssh -N .*-R 0:{self.target_host}:{self.target_port}'",
                 timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass

    def state_dict(self) -> dict:
        return {
            "state": self.state,
            "detail": self.detail,
            "port": self.remote_port,
            "url": f"http://127.0.0.1:{self.remote_port}/archive" if self.remote_port else "",
            "fullscreen": True,
        }
