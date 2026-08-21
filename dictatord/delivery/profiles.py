"""Per-application paste profiles.

Selecting a profile requires knowing which application has focus. That is
available on X11 and not on Wayland through any standard interface, so the
design degrades explicitly rather than pretending otherwise (v2.md §5.4).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..platform.chords import Chord

#: Applications whose paste chord is Ctrl+Shift+V because Ctrl+V is a control
#: character. Matched as substrings against a lower-cased application id.
TERMINAL_APPS = (
    "gnome-terminal",
    "konsole",
    "xterm",
    "urxvt",
    "rxvt",
    "alacritty",
    "kitty",
    "foot",
    "wezterm",
    "terminator",
    "tilix",
    "xfce4-terminal",
    "termite",
    "st-256color",
    "ghostty",
    "contour",
    "blackbox",
    "org.gnome.console",
    "org.gnome.terminal",
)


@dataclass(frozen=True)
class Profile:
    name: str
    #: The chord that pastes. None means never synthesise input.
    paste: Chord | None
    description: str

    @property
    def synthesises_input(self) -> bool:
        return self.paste is not None


STANDARD = Profile(
    name="standard",
    paste=Chord.parse("Ctrl+v"),
    description="Universal editable-field paste",
)
TERMINAL = Profile(
    name="terminal",
    paste=Chord.parse("Ctrl+Shift+v"),
    description="Terminals, where Ctrl+V is a control character",
)
CLIPBOARD_ONLY = Profile(
    name="clipboard-only",
    paste=None,
    description="Never synthesises input; the text is copied and nothing more",
)

BY_NAME = {p.name: p for p in (STANDARD, TERMINAL, CLIPBOARD_ONLY)}


def for_app(
    app_id: str | None,
    *,
    default: str = "standard",
    clipboard_only_apps: tuple[str, ...] = (),
) -> Profile:
    """Pick a profile for the focused application.

    ``app_id`` is None on Wayland, which is expected. The configured default
    is then used, and the user expresses intent by which chord they pressed.
    """
    fallback = BY_NAME.get(default, STANDARD)
    if not app_id:
        return fallback

    lowered = app_id.lower()
    for pattern in clipboard_only_apps:
        if pattern and pattern.lower() in lowered:
            return CLIPBOARD_ONLY
    if any(term in lowered for term in TERMINAL_APPS):
        return TERMINAL
    return fallback


def resolve(name: str) -> Profile:
    return BY_NAME.get(name, STANDARD)
