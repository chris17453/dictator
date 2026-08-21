"""Chord parsing, normalisation, and per-backend rendering.

One representation, three renderings: a canonical string for config and
display, the XDG shortcuts syntax the portal expects, and the
(keysym, modifier-mask) pair X11 needs. Backends never parse user strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: Canonical modifier names, in the order they are always rendered.
MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Super")

_MODIFIER_ALIASES = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "primary": "Ctrl",
    "alt": "Alt",
    "meta": "Alt",
    "option": "Alt",
    "shift": "Shift",
    "super": "Super",
    "win": "Super",
    "windows": "Super",
    "cmd": "Super",
    "command": "Super",
    "logo": "Super",
}

#: Names that differ between what a user types and the X keysym name.
_KEY_ALIASES = {
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Return",
    "return": "Return",
    "space": "space",
    "spacebar": "space",
    "tab": "Tab",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "comma": "comma",
    "period": "period",
    "dot": "period",
    "slash": "slash",
    "backslash": "backslash",
    "semicolon": "semicolon",
    "apostrophe": "apostrophe",
    "grave": "grave",
    "backtick": "grave",
    "minus": "minus",
    "dash": "minus",
    "equal": "equal",
    "equals": "equal",
    "bracketleft": "bracketleft",
    "bracketright": "bracketright",
}

#: Portal (XDG shortcuts spec) spells modifiers in upper case.
_PORTAL_MODIFIER = {
    "Ctrl": "CTRL",
    "Alt": "ALT",
    "Shift": "SHIFT",
    "Super": "SUPER",
}


class ChordError(ValueError):
    """A chord string that cannot be parsed or is not usable as a shortcut."""


@dataclass(frozen=True, order=True)
class Chord:
    """A modifier set plus exactly one non-modifier key."""

    modifiers: frozenset[str]
    key: str

    # -- construction ----------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> "Chord":
        if not text or not text.strip():
            raise ChordError("empty chord")
        parts = [p.strip() for p in text.replace("<", "").replace(">", "+").split("+")]
        parts = [p for p in parts if p]
        if not parts:
            raise ChordError(f"empty chord: {text!r}")

        modifiers: set[str] = set()
        key: str | None = None
        for part in parts:
            lowered = part.lower()
            if lowered in _MODIFIER_ALIASES:
                modifiers.add(_MODIFIER_ALIASES[lowered])
                continue
            if key is not None:
                raise ChordError(
                    f"{text!r} names more than one non-modifier key "
                    f"({key!r} and {part!r}); a chord needs exactly one"
                )
            key = cls._normalise_key(part)

        if key is None:
            raise ChordError(
                f"{text!r} is only modifiers; a chord needs one ordinary key too"
            )
        return cls(frozenset(modifiers), key)

    @staticmethod
    def _normalise_key(part: str) -> str:
        lowered = part.lower()
        if lowered in _KEY_ALIASES:
            return _KEY_ALIASES[lowered]
        if len(part) == 1:
            # Single characters are lower-cased: Shift is expressed as a
            # modifier, never by capitalising the letter.
            return part.lower()
        if lowered.startswith("f") and lowered[1:].isdigit():
            number = int(lowered[1:])
            if 1 <= number <= 24:
                return f"F{number}"
            raise ChordError(f"no such function key: {part!r}")
        # Assume it is already an X keysym name (e.g. "AudioPlay").
        return part[0].upper() + part[1:]

    # -- rendering -------------------------------------------------------

    def __str__(self) -> str:
        ordered = [m for m in MODIFIER_ORDER if m in self.modifiers]
        return "+".join(ordered + [self.key])

    @property
    def canonical(self) -> str:
        return str(self)

    def to_portal(self) -> str:
        """XDG shortcuts syntax, e.g. ``SUPER+d``."""
        ordered = [_PORTAL_MODIFIER[m] for m in MODIFIER_ORDER if m in self.modifiers]
        return "+".join(ordered + [self.key])

    def to_gsettings(self) -> str:
        """GNOME keybinding syntax, e.g. ``<Super>d``."""
        ordered = [f"<{m}>" for m in MODIFIER_ORDER if m in self.modifiers]
        return "".join(ordered) + self.key

    # -- properties used by policy ---------------------------------------

    @property
    def is_bare_key(self) -> bool:
        """True when no modifier is held. Such a chord would swallow typing."""
        return not self.modifiers

    def describe(self) -> str:
        """Human phrasing for notifications and help text."""
        return str(self).replace("+", " + ")


def parse(text: str) -> Chord:
    return Chord.parse(text)


def parse_optional(text: str | None) -> Chord | None:
    """Parse a chord that is allowed to be unset (empty string means unbound)."""
    if text is None or not text.strip():
        return None
    return Chord.parse(text)


def validate_usable(chord: Chord) -> None:
    """Reject chords that are legal to express but bad to bind."""
    if chord.is_bare_key:
        raise ChordError(
            f"{chord} has no modifier, so it would capture the key everywhere. "
            f"Add at least one of {', '.join(MODIFIER_ORDER)}."
        )
    if chord.modifiers == {"Shift"}:
        raise ChordError(
            f"{chord} uses only Shift, which would capture ordinary typing. "
            f"Add Ctrl, Alt, or Super."
        )


def format_all(chords: Iterable[Chord]) -> str:
    return ", ".join(str(c) for c in chords)
