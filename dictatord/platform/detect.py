"""Session detection.

Probed in strict order, because the obvious check is wrong on every
XWayland-enabled desktop: under XWayland ``DISPLAY`` is set on a *Wayland*
session, so ``if DISPLAY: use_x11()`` selects the broken backend everywhere
(v2.md §5.1, G-00).
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SessionType(str, Enum):
    WAYLAND = "wayland"
    X11 = "x11"
    HEADLESS = "headless"


@dataclass(frozen=True)
class Session:
    type: SessionType
    #: How the decision was reached, for ``dictator doctor``.
    evidence: str
    desktop: str = ""
    wayland_display: str = ""
    x_display: str = ""

    @property
    def is_wayland(self) -> bool:
        return self.type is SessionType.WAYLAND

    @property
    def is_x11(self) -> bool:
        return self.type is SessionType.X11

    @property
    def is_headless(self) -> bool:
        return self.type is SessionType.HEADLESS


def _wayland_socket(environ: dict[str, str]) -> Path | None:
    display = environ.get("WAYLAND_DISPLAY", "")
    if not display:
        return None
    candidate = Path(display)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    runtime = environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return None
    candidate = Path(runtime) / display
    return candidate if candidate.exists() else None


def _x_display_reachable(environ: dict[str, str]) -> bool:
    """Confirm an X server actually answers, rather than trusting ``DISPLAY``."""
    display = environ.get("DISPLAY", "")
    if not display:
        return False
    try:
        head = display.split(":", 1)[1]
        number = int(head.split(".", 1)[0])
    except (IndexError, ValueError):
        return False
    unix = Path(f"/tmp/.X11-unix/X{number}")
    if unix.exists():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                sock.connect(str(unix))
            return True
        except OSError:
            return False
    host = display.split(":", 1)[0]
    if host:
        try:
            with socket.create_connection((host, 6000 + number), timeout=0.5):
                return True
        except OSError:
            return False
    return False


def detect(environ: dict[str, str] | None = None) -> Session:
    """Resolve the session type. Pure with respect to ``environ``."""
    env = dict(os.environ if environ is None else environ)
    desktop = env.get("XDG_CURRENT_DESKTOP", "")
    wayland_display = env.get("WAYLAND_DISPLAY", "")
    x_display = env.get("DISPLAY", "")

    declared = env.get("XDG_SESSION_TYPE", "").strip().lower()
    if declared == "wayland":
        return Session(
            SessionType.WAYLAND,
            "XDG_SESSION_TYPE=wayland",
            desktop,
            wayland_display,
            x_display,
        )
    if declared == "x11":
        return Session(
            SessionType.X11, "XDG_SESSION_TYPE=x11", desktop, wayland_display, x_display
        )

    if _wayland_socket(env) is not None:
        return Session(
            SessionType.WAYLAND,
            f"WAYLAND_DISPLAY={wayland_display} socket present",
            desktop,
            wayland_display,
            x_display,
        )

    if _x_display_reachable(env):
        return Session(
            SessionType.X11,
            f"DISPLAY={x_display} reachable",
            desktop,
            wayland_display,
            x_display,
        )

    reason = "no XDG_SESSION_TYPE, no Wayland socket, no reachable X display"
    return Session(SessionType.HEADLESS, reason, desktop, wayland_display, x_display)
