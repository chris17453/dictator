"""Global shortcuts read straight from the kernel's input devices.

This is the prompt-free path. It asks no portal and no compositor, so nothing
ever pops up, and because evdev reports key *release* as well as press,
hold-to-talk works exactly as it does on the portal path.

It needs read access to ``/dev/input/event*``, which ``dictator setup
--no-portal`` arranges with a udev rule. That access is a keylogging
capability: any process running as this user can then read every keystroke.
It is the same power an X11 client holds by default and what ydotool and
similar tools require, but it is a real trade and the setup command says so
before making it.

Devices are monitored, not grabbed. Grabbing would take the key away from the
application underneath — and would take *every* key on that device, leaving the
keyboard dead if the daemon died. The cost of monitoring is that the chord also
reaches whatever has focus, so it should be one nothing else is bound to.
"""
from __future__ import annotations

import asyncio
import os
import select
import threading

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .base import BindResult, Capability, ShortcutBackend, ShortcutCallback, ShortcutEvent
from .chords import Chord

log = get_logger(__name__)

#: Chord modifier name -> the evdev key names that satisfy it.
_MODIFIER_KEYS = {
    "Ctrl": ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"),
    "Alt": ("KEY_LEFTALT", "KEY_RIGHTALT"),
    "Shift": ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"),
    "Super": ("KEY_LEFTMETA", "KEY_RIGHTMETA"),
}

#: Chord key names that are not simply KEY_<UPPERCASE>.
_KEY_ALIASES = {
    "Escape": "KEY_ESC",
    "Return": "KEY_ENTER",
    "space": "KEY_SPACE",
    "Tab": "KEY_TAB",
    "BackSpace": "KEY_BACKSPACE",
    "Delete": "KEY_DELETE",
    "Insert": "KEY_INSERT",
    "Home": "KEY_HOME",
    "End": "KEY_END",
    "Prior": "KEY_PAGEUP",
    "Next": "KEY_PAGEDOWN",
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

_RELEASED, _PRESSED, _REPEAT = 0, 1, 2


def _import_evdev():
    try:
        import evdev

        return evdev
    except Exception as exc:  # pragma: no cover - depends on host
        raise Fault(
            code=FaultCode.NO_SHORTCUT_BACKEND,
            message=f"python-evdev is not usable: {exc}",
            remedy="Install it: pip install evdev",
        ) from exc


def keyboards(evdev) -> list:
    """Every readable device that reports ordinary letter keys."""
    found = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except (OSError, PermissionError):
            continue
        capabilities = device.capabilities()
        keys = capabilities.get(evdev.ecodes.EV_KEY, [])
        # A keyboard has letters. A mouse with extra buttons does not.
        if evdev.ecodes.KEY_A in keys and evdev.ecodes.KEY_Z in keys:
            found.append(device)
        else:
            device.close()
    return found


def _code_for(evdev, key: str) -> int:
    name = _KEY_ALIASES.get(key)
    if name is None:
        if len(key) == 1:
            name = f"KEY_{key.upper()}"
        elif key.upper().startswith("F") and key[1:].isdigit():
            name = f"KEY_{key.upper()}"
        else:
            name = f"KEY_{key.upper()}"
    code = getattr(evdev.ecodes, name, None)
    if code is None:
        raise Fault(
            code=FaultCode.SHORTCUT_BIND_FAILED,
            message=f"the kernel has no key named {key!r}",
            remedy="Choose a different key: dictator keys set dictate <chord>",
        )
    return int(code)


class EvdevShortcuts(ShortcutBackend):
    name = "evdev"

    def __init__(self) -> None:
        self._devices: list = []
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._callback: ShortcutCallback | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bound: dict[str, Chord] = {}
        #: shortcut_id -> (key code, {modifier code sets})
        self._targets: dict[str, tuple[int, list[tuple[int, ...]]]] = {}
        self._down: set[int] = set()
        self._active: set[str] = set()
        self._wake_r = self._wake_w = -1

    # -- probe -----------------------------------------------------------

    @classmethod
    async def probe(cls) -> Capability:
        try:
            evdev = _import_evdev()
        except Fault as fault:
            return Capability(name=cls.name, available=False, reason=fault.message)

        devices = keyboards(evdev)
        count = len(devices)
        for device in devices:
            device.close()
        if not count:
            return Capability(
                name=cls.name,
                available=False,
                reason="no readable keyboard under /dev/input (permission denied)",
            )
        return Capability(
            name=cls.name,
            available=True,
            supports_release=True,
            requires_consent=False,
            trust="unrestricted; reading /dev/input is a keylogging capability",
            detail=f"evdev, {count} keyboard(s)",
            # Preferred over the portal when available: it never prompts.
            rank=110,
        )

    # -- lifecycle -------------------------------------------------------

    async def start(self, callback: ShortcutCallback) -> None:
        if self._thread is not None:
            self._callback = callback
            return
        evdev = _import_evdev()
        self._callback = callback
        self._loop = asyncio.get_running_loop()
        self._devices = keyboards(evdev)
        if not self._devices:
            raise Fault(
                code=FaultCode.NO_SHORTCUT_BACKEND,
                message="no readable keyboard under /dev/input",
                remedy="Grant access: dictator setup --no-portal",
            )
        self._wake_r, self._wake_w = os.pipe()
        self._stopping.clear()
        self._thread = threading.Thread(target=self._pump, name="evdev-shortcuts",
                                        daemon=True)
        self._thread.start()
        log.info("evdev shortcut backend started", keyboards=len(self._devices))

    async def bind(self, shortcuts: dict[str, Chord],
                   descriptions: dict[str, str]) -> BindResult:
        evdev = _import_evdev()
        result = BindResult()
        targets: dict[str, tuple[int, list[tuple[int, ...]]]] = {}
        for shortcut_id, chord in shortcuts.items():
            try:
                key_code = _code_for(evdev, chord.key)
                groups = [
                    tuple(int(getattr(evdev.ecodes, n)) for n in _MODIFIER_KEYS[m])
                    for m in chord.modifiers
                ]
            except Fault as fault:
                result.rejected[shortcut_id] = fault.message
                continue
            targets[shortcut_id] = (key_code, groups)
            result.bound[shortcut_id] = chord
            log.info("shortcut watched", id=shortcut_id, chord=str(chord))
        self._targets = targets
        self._bound = dict(result.bound)
        return result

    async def stop(self) -> None:
        self._stopping.set()
        if self._wake_w >= 0:
            try:
                os.write(self._wake_w, b"x")
            except OSError:  # pragma: no cover
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        for descriptor in (self._wake_r, self._wake_w):
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:  # pragma: no cover
                    pass
        self._wake_r = self._wake_w = -1
        for device in self._devices:
            try:
                device.close()
            except Exception:  # pragma: no cover
                pass
        self._devices = []
        self._bound.clear()
        self._targets.clear()

    # -- event pump ------------------------------------------------------

    #: How often to look for keyboards that appeared after startup.
    RESCAN_SECONDS = 2.0

    def _pump(self) -> None:
        import time

        evdev = _import_evdev()
        fds = {device.fd: device for device in self._devices}
        known = {device.path for device in self._devices}
        next_scan = time.monotonic() + self.RESCAN_SECONDS

        while not self._stopping.is_set():
            try:
                ready, _, _ = select.select(list(fds) + [self._wake_r], [], [], 0.5)
            except (OSError, ValueError):  # pragma: no cover - device vanished
                ready = []
            if self._stopping.is_set():
                break

            for fd in ready:
                if fd == self._wake_r:
                    return
                device = fds.get(fd)
                if device is None:
                    continue
                try:
                    for event in device.read():
                        self._handle(event)
                except OSError:
                    # A keyboard was unplugged; stop watching it rather than
                    # spinning on a dead descriptor.
                    log.info("input device disappeared", device=device.path)
                    known.discard(device.path)
                    fds.pop(fd, None)
                    self._forget(device)
                    break

            # A keyboard plugged in after startup must start working without a
            # restart — the same expectation the audio device already meets.
            now = time.monotonic()
            if now >= next_scan:
                next_scan = now + self.RESCAN_SECONDS
                try:
                    for device in keyboards(evdev):
                        if device.path in known:
                            device.close()
                            continue
                        known.add(device.path)
                        fds[device.fd] = device
                        self._devices.append(device)
                        log.info("watching a new keyboard", device=device.name)
                except Exception as exc:  # pragma: no cover - transient
                    log.debug("keyboard rescan failed", error=str(exc))

    def _forget(self, device) -> None:
        try:
            self._devices.remove(device)
        except ValueError:  # pragma: no cover
            pass
        try:
            device.close()
        except Exception:  # pragma: no cover
            pass

    def _handle(self, event) -> None:
        evdev = _import_evdev()
        if event.type != evdev.ecodes.EV_KEY:
            return
        code, value = int(event.code), int(event.value)

        if value == _PRESSED:
            self._down.add(code)
        elif value == _RELEASED:
            self._down.discard(code)
        elif value == _REPEAT:
            # Auto-repeat is not a new press; ignoring it is what stops a held
            # chord from restarting the session over and over.
            return

        for shortcut_id, (key_code, groups) in self._targets.items():
            if code != key_code:
                continue
            satisfied = all(any(m in self._down for m in group) for group in groups)
            if value == _PRESSED and satisfied and shortcut_id not in self._active:
                self._active.add(shortcut_id)
                self._emit(shortcut_id, ShortcutEvent.PRESSED)
            elif value == _RELEASED and shortcut_id in self._active:
                self._active.discard(shortcut_id)
                self._emit(shortcut_id, ShortcutEvent.RELEASED)

    def _emit(self, shortcut_id: str, which: ShortcutEvent) -> None:
        if self._callback is None or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._callback, shortcut_id, which)

    def bound(self) -> dict[str, Chord]:
        return dict(self._bound)
