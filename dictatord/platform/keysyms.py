"""Unicode to X keysym translation.

Both injection backends speak keysyms: the portal's ``NotifyKeyboardKeysym``
and X11's ``XTestFakeKeyEvent`` (after a keycode lookup). Keeping the mapping
in one place means typing behaves identically on both.
"""
from __future__ import annotations

#: Modifier keysyms, left-hand variants.
MODIFIER_KEYSYMS = {
    "Shift": 0xFFE1,   # XK_Shift_L
    "Ctrl": 0xFFE3,    # XK_Control_L
    "Alt": 0xFFE9,     # XK_Alt_L
    "Super": 0xFFEB,   # XK_Super_L
}

#: Named keys whose keysym is not derivable from a character.
NAMED_KEYSYMS = {
    "BackSpace": 0xFF08,
    "Tab": 0xFF09,
    "Return": 0xFF0D,
    "Escape": 0xFF1B,
    "Delete": 0xFFFF,
    "Home": 0xFF50,
    "Left": 0xFF51,
    "Up": 0xFF52,
    "Right": 0xFF53,
    "Down": 0xFF54,
    "Prior": 0xFF55,
    "Next": 0xFF56,
    "End": 0xFF57,
    "Insert": 0xFF63,
    "space": 0x0020,
}
for _n in range(1, 25):
    NAMED_KEYSYMS[f"F{_n}"] = 0xFFBE + (_n - 1)

#: Characters that need Shift held on a US layout. Used only by the X11
#: keycode path; the portal resolves keysyms itself.
_SHIFTED = set('~!@#$%^&*()_+{}|:"<>?') | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def char_to_keysym(char: str) -> int:
    """Keysym for a single character.

    Latin-1 maps directly; everything else uses the Unicode keysym range
    (``0x01000000 | codepoint``) that X11 and the portal both understand.
    """
    code = ord(char)
    if code == 0x0A or code == 0x0D:
        return NAMED_KEYSYMS["Return"]
    if code == 0x09:
        return NAMED_KEYSYMS["Tab"]
    if 0x20 <= code <= 0xFF:
        return code
    return 0x01000000 | code


def key_to_keysym(key: str) -> int:
    """Keysym for a :class:`~dictatord.platform.chords.Chord` key name."""
    if key in NAMED_KEYSYMS:
        return NAMED_KEYSYMS[key]
    if len(key) == 1:
        return char_to_keysym(key)
    # Fall back to the X keysym table for exotic names (AudioPlay, etc.).
    try:
        from Xlib import XK

        keysym = XK.string_to_keysym(key)
        if keysym:
            return int(keysym)
    except Exception:  # pragma: no cover - Xlib optional at runtime
        pass
    raise KeyError(f"no keysym for key name {key!r}")


def needs_shift(char: str) -> bool:
    return char in _SHIFTED
