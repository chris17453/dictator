"""Input injection through the kernel's uinput device.

The prompt-free counterpart to :mod:`evdev_shortcuts`. A virtual keyboard is
registered with the kernel, so synthetic keys arrive by the same route as a
real one — which means the compositor delivers them normally and no portal
consent is involved.

Needs write access to ``/dev/uinput``, arranged by ``dictator setup
--no-portal``. That is an input-injection capability: any process running as
this user can then type into any window. Same trust model as X11, and exactly
what ydotool requires.

Clipboard handling is delegated, because uinput moves keys, not selections.
"""
from __future__ import annotations

import asyncio
import time

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .base import Capability, InjectionBackend
from .chords import Chord
from .clipboard import Clipboard, NullClipboard

log = get_logger(__name__)

UINPUT_DEVICE = "/dev/uinput"

_MODIFIER_KEYS = {
    "Ctrl": "KEY_LEFTCTRL",
    "Alt": "KEY_LEFTALT",
    "Shift": "KEY_LEFTSHIFT",
    "Super": "KEY_LEFTMETA",
}

_KEY_ALIASES = {
    "Escape": "KEY_ESC",
    "Return": "KEY_ENTER",
    "space": "KEY_SPACE",
    "Tab": "KEY_TAB",
    "BackSpace": "KEY_BACKSPACE",
    "Delete": "KEY_DELETE",
    "Up": "KEY_UP",
    "Down": "KEY_DOWN",
    "Left": "KEY_LEFT",
    "Right": "KEY_RIGHT",
    "comma": "KEY_COMMA",
    "period": "KEY_DOT",
    "slash": "KEY_SLASH",
    "backslash": "KEY_BACKSLASH",
    "semicolon": "KEY_SEMICOLON",
    "apostrophe": "KEY_APOSTROPHE",
    "grave": "KEY_GRAVE",
    "minus": "KEY_MINUS",
    "equal": "KEY_EQUAL",
    "bracketleft": "KEY_LEFTBRACE",
    "bracketright": "KEY_RIGHTBRACE",
}

#: Characters typeable on a US layout, as (key name, needs shift).
_CHARS: dict[str, tuple[str, bool]] = {}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _CHARS[_c] = (f"KEY_{_c.upper()}", False)
    _CHARS[_c.upper()] = (f"KEY_{_c.upper()}", True)
for _d in "1234567890":
    _CHARS[_d] = (f"KEY_{_d}", False)
for _plain, _shifted, _name in (
    ("`", "~", "KEY_GRAVE"), ("-", "_", "KEY_MINUS"), ("=", "+", "KEY_EQUAL"),
    ("[", "{", "KEY_LEFTBRACE"), ("]", "}", "KEY_RIGHTBRACE"),
    ("\\", "|", "KEY_BACKSLASH"), (";", ":", "KEY_SEMICOLON"),
    ("'", '"', "KEY_APOSTROPHE"), (",", "<", "KEY_COMMA"),
    (".", ">", "KEY_DOT"), ("/", "?", "KEY_SLASH"),
):
    _CHARS[_plain] = (_name, False)
    _CHARS[_shifted] = (_name, True)
for _digit, _symbol in zip("1234567890", "!@#$%^&*()"):
    _CHARS[_symbol] = (f"KEY_{_digit}", True)
_CHARS[" "] = ("KEY_SPACE", False)
_CHARS["\n"] = ("KEY_ENTER", False)
_CHARS["\t"] = ("KEY_TAB", False)


def _import_evdev():
    try:
        import evdev
        from evdev import UInput

        return evdev, UInput
    except Exception as exc:  # pragma: no cover
        raise Fault(
            code=FaultCode.NO_INJECTION_BACKEND,
            message=f"python-evdev is not usable: {exc}",
            remedy="Install it: pip install evdev",
        ) from exc


class UinputInjection(InjectionBackend):
    name = "uinput"

    def __init__(self, clipboard: Clipboard | None = None,
                 key_delay_ms: float = 4.0, **_ignored) -> None:
        self._clipboard = clipboard or NullClipboard()
        self._device = None
        self._delay = key_delay_ms / 1000.0

    # -- probe -----------------------------------------------------------

    @classmethod
    async def probe(cls) -> Capability:
        import os

        try:
            _import_evdev()
        except Fault as fault:
            return Capability(name=cls.name, available=False, reason=fault.message)
        if not os.path.exists(UINPUT_DEVICE):
            return Capability(
                name=cls.name, available=False,
                reason=f"{UINPUT_DEVICE} does not exist (load the uinput module)",
            )
        if not os.access(UINPUT_DEVICE, os.W_OK):
            return Capability(
                name=cls.name, available=False,
                reason=f"{UINPUT_DEVICE} is not writable",
            )
        return Capability(
            name=cls.name,
            available=True,
            supports_focus_query=False,
            requires_consent=False,
            trust="unrestricted; writing /dev/uinput can type into any window",
            detail="uinput virtual keyboard",
            # Preferred over the portal when available: it never prompts.
            rank=110,
        )

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if self._device is not None:
            return
        evdev, UInput = _import_evdev()
        # Advertise every key we might send, since the capability set is fixed
        # when the device is created.
        codes = sorted({
            int(getattr(evdev.ecodes, name))
            for name in set(_MODIFIER_KEYS.values())
            | set(_KEY_ALIASES.values())
            | {entry[0] for entry in _CHARS.values()}
            if hasattr(evdev.ecodes, name)
        })
        try:
            self._device = UInput(
                {evdev.ecodes.EV_KEY: codes},
                name="dictator-virtual-keyboard",
                vendor=0x1209,
                product=0x0001,
            )
        except Exception as exc:
            raise Fault(
                code=FaultCode.NO_INJECTION_BACKEND,
                message=f"could not create the virtual keyboard: {exc}",
                remedy="Grant access to /dev/uinput: dictator setup --no-portal",
            ) from exc
        # The compositor needs a moment to notice a new keyboard; keys sent
        # before it does are dropped silently.
        await asyncio.sleep(0.3)
        log.info("uinput injection ready")

    async def stop(self) -> None:
        await self._clipboard.stop()
        if self._device is not None:
            try:
                self._device.close()
            except Exception:  # pragma: no cover
                pass
            self._device = None

    # -- clipboard -------------------------------------------------------

    async def set_clipboard(self, text: str) -> None:
        await self._clipboard.set_text(text)

    async def get_clipboard(self) -> str | None:
        return await self._clipboard.get_text()

    # -- injection -------------------------------------------------------

    def _require(self):
        if self._device is None:
            raise Fault(
                code=FaultCode.INJECTION_FAILED,
                message="the virtual keyboard is not open",
                remedy="Run: dictator restart",
            )
        return self._device

    def _tap(self, evdev, codes: list[int]) -> None:
        device = self._require()
        for code in codes:
            device.write(evdev.ecodes.EV_KEY, code, 1)
        device.syn()
        time.sleep(self._delay)
        for code in reversed(codes):
            device.write(evdev.ecodes.EV_KEY, code, 0)
        device.syn()
        time.sleep(self._delay)

    async def send_chord(self, chord: Chord) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, self._send_chord_sync, chord
        )

    def _send_chord_sync(self, chord: Chord) -> None:
        evdev, _ = _import_evdev()
        codes = []
        for modifier in ("Ctrl", "Alt", "Shift", "Super"):
            if modifier in chord.modifiers:
                codes.append(int(getattr(evdev.ecodes, _MODIFIER_KEYS[modifier])))
        name = _KEY_ALIASES.get(chord.key)
        if name is None:
            entry = _CHARS.get(chord.key)
            name = entry[0] if entry else f"KEY_{chord.key.upper()}"
        code = getattr(evdev.ecodes, name, None)
        if code is None:
            raise Fault(
                code=FaultCode.INJECTION_FAILED,
                message=f"cannot send the key {chord.key!r}",
                remedy="Choose a different chord.",
            )
        codes.append(int(code))
        self._tap(evdev, codes)

    async def type_text(self, text: str) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, self._type_text_sync, text
        )

    def _type_text_sync(self, text: str) -> None:
        evdev, _ = _import_evdev()
        shift = int(evdev.ecodes.KEY_LEFTSHIFT)
        skipped = 0
        for char in text:
            entry = _CHARS.get(char)
            if entry is None:
                # uinput sends keys, not characters; anything off the layout
                # cannot be typed. Paste delivery has no such limit, which is
                # why it is the default.
                skipped += 1
                continue
            name, needs_shift = entry
            code = int(getattr(evdev.ecodes, name))
            self._tap(evdev, [shift, code] if needs_shift else [code])
        if skipped:
            log.warning(
                "characters could not be typed on this layout; use paste delivery",
                skipped=skipped,
            )
