"""Application identity, as xdg-desktop-portal derives it.

This matters more than it looks. GNOME's global-shortcuts provider refuses
requests from applications it cannot identify::

    gnome-control-c: Discarded shortcut bind request from application
                     with an invalid app_id ><.

For a sandboxed app the portal reads the identity from the sandbox metadata.
For an ordinary host process it derives it from the systemd unit in the
process's cgroup, following systemd's ``app-<launcher>-<app-id>-<n>.scope``
convention. A process started from a shell has no such unit and therefore no
identity — which is why the daemon must run under its own unit, and why
``dictator setup --install`` is not optional on GNOME.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

#: The desktop entry this product installs. The systemd unit and the
#: ``.desktop`` file must agree on it or the portal will not identify us.
DESKTOP_ID = "com.watkinslabs.Dictator"

_UNIT_PATTERNS = (
    # app-<launcher>-<app-id>-<random>.scope|service
    re.compile(r"app-[^-]+-(?P<id>.+)-\d+\.(?:scope|service)$"),
    # app-<app-id>-<random>.scope|service
    re.compile(r"app-(?P<id>.+)-\d+\.(?:scope|service)$"),
    # app-<app-id>@<instance>.service
    re.compile(r"app-(?P<id>.+)@.*\.service$"),
    # app-<app-id>.service — what our own unit uses. Verified accepted by
    # xdg-desktop-portal-gnome 48; keep it last so the more specific
    # launcher-prefixed forms win when they apply.
    re.compile(r"app-(?P<id>.+)\.(?:scope|service)$"),
)


def _unescape(unit: str) -> str:
    """Reverse systemd's ``\\xNN`` escaping in unit names."""
    return re.sub(
        r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), unit
    )


def _cgroup_unit(pid: int | None = None) -> str:
    path = Path(f"/proc/{pid or 'self'}/cgroup")
    try:
        content = path.read_text()
    except OSError:
        return ""
    for line in content.splitlines():
        # cgroup v2 lines look like "0::/user.slice/.../app-foo-123.scope"
        tail = line.rsplit(":", 1)[-1]
        for part in reversed(tail.split("/")):
            if part.endswith((".scope", ".service")):
                return part
    return ""


@lru_cache(maxsize=1)
def app_id(pid: int | None = None) -> str:
    """The identity the portal will see, or an empty string if it has none."""
    if os.path.exists("/.flatpak-info"):
        # Inside Flatpak the portal uses the sandbox identity directly.
        try:
            for line in Path("/.flatpak-info").read_text().splitlines():
                if line.startswith("name="):
                    return line.split("=", 1)[1].strip()
        except OSError:  # pragma: no cover
            pass

    unit = _unescape(_cgroup_unit(pid))
    if not unit:
        return ""
    for pattern in _UNIT_PATTERNS:
        match = pattern.search(unit)
        if match:
            candidate = match.group("id")
            # A desktop id has at least one dot and no path separators.
            if "." in candidate and "/" not in candidate:
                return candidate
    return ""


def is_identified() -> bool:
    return bool(app_id())


def explain() -> str:
    """One line for ``dictator doctor``."""
    current = app_id()
    if current:
        return f"{current} (from the systemd unit)"
    return "none — GNOME will refuse to bind global shortcuts"
