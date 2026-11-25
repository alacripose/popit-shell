"""Hosts this shell talks to, read from the machine rather than written into the repository.

A public checkout cannot carry a household's addresses or a desktop account's name. The
Debian host and its login are local facts: the environment supplies them, or a local file
under `runlogs/toast/` does, and the default is loopback so a missing setting fails in the
open instead of quietly reaching for an address that belongs to one network.
"""
from __future__ import annotations

import os
import pathlib
import socket

ROOT = pathlib.Path(__file__).resolve().parent


def _local(name: str, fallback: str = "") -> str:
    path = ROOT / "runlogs" / "toast" / f"{name}.txt"
    try:
        return path.read_text(encoding="utf-8").strip() or fallback
    except OSError:
        return fallback


def debian_host() -> str:
    """The machine that runs the desktop the shell views, when it is not this one."""
    return os.environ.get("POPIT_DEBIAN_HOST") or _local("debian-host", "127.0.0.1")


def debian_user() -> str:
    """The desktop account on that machine; its home path is built from this."""
    return os.environ.get("POPIT_DEBIAN_USER") or _local("debian-user", "popit")


def lan_host() -> str:
    """This machine's address on its own network, asked of the routing table."""
    try:
        # TEST-NET-1 has no route out, so this selects an interface without sending a packet.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            value = probe.getsockname()[0]
            if value and not value.startswith("127."):
                return value
    except OSError:
        pass
    try:
        value = socket.gethostbyname(socket.gethostname())
        return value if value and not value.startswith("127.") else "127.0.0.1"
    except OSError:
        return "127.0.0.1"
