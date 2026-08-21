"""Global shortcuts on X11 via XGrabKey.

A real grab on the root window, not a passive listener. This is the correct
X11 mechanism and the reason it gives both press *and* release, so
hold-to-talk needs nothing extra (v2.md §5.2).

The defects that make hand-rolled X11 hotkeys feel flaky are all handled here:
lock-modifier permutations, every screen's root window, layout changes via
MappingNotify, and BadAccess reported as a real fault naming the chord.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .base import BindResult, Capability, ShortcutBackend, ShortcutCallback, ShortcutEvent
from .chords import Chord

log = get_logger(__name__)

_MODIFIER_MASK_NAMES = {
    "Shift": "ShiftMask",
    "Ctrl": "ControlMask",
    "Alt": "Mod1Mask",
    "Super": "Mod4Mask",
}


def _import_xlib():
    try:
        from Xlib import X, XK, display, error  # noqa: F401
        from Xlib.protocol import event as xevent  # noqa: F401

        return display, X, XK, error, xevent
    except Exception as exc:  # pragma: no cover - depends on host
        raise Fault(
            code=FaultCode.NO_SHORTCUT_BACKEND,
            message=f"python-xlib is not usable: {exc}",
            remedy="Install python-xlib: pip install python-xlib",
        ) from exc


class X11Shortcuts(ShortcutBackend):
    name = "x11"

    def __init__(self) -> None:
        self._display = None
        self._roots: list[Any] = []
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._callback: ShortcutCallback | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        #: (keycode, base_mask) -> shortcut_id
        self._grabs: dict[tuple[int, int], str] = {}
        self._bound: dict[str, Chord] = {}
        self._lock_masks: list[int] = [0]

    # -- probe -----------------------------------------------------------

    @classmethod
    async def probe(cls) -> Capability:
        try:
            display, _X, _XK, _error, _ev = _import_xlib()
        except Fault as fault:
            return Capability(name=cls.name, available=False, reason=fault.message)
        try:
            conn = display.Display()
            screens = conn.screen_count()
            conn.close()
        except Exception as exc:
            return Capability(
                name=cls.name,
                available=False,
                reason=f"cannot open the X display: {exc}",
            )
        return Capability(
            name=cls.name,
            available=True,
            supports_release=True,
            supports_focus_query=True,
            requires_consent=False,
            trust="unrestricted; any X client may grab keys or inject input",
            detail=f"X11, {screens} screen(s)",
            rank=90,
        )

    # -- lifecycle -------------------------------------------------------

    async def start(self, callback: ShortcutCallback) -> None:
        if self._thread is not None:
            self._callback = callback
            return
        self._callback = callback
        self._loop = asyncio.get_running_loop()

        display, X, _XK, _error, _ev = _import_xlib()
        try:
            self._display = display.Display()
        except Exception as exc:
            raise Fault(
                code=FaultCode.NO_SHORTCUT_BACKEND,
                message=f"cannot open the X display: {exc}",
                remedy="Check that DISPLAY is set and the X server is reachable.",
            ) from exc

        self._roots = [
            self._display.screen(i).root
            for i in range(self._display.screen_count())
        ]
        # Watch for layout changes so keycodes can be re-resolved.
        for root in self._roots:
            root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)

        self._compute_lock_masks()
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._pump, name="x11-shortcuts", daemon=True
        )
        self._thread.start()
        log.info("x11 shortcut backend started", screens=len(self._roots))

    def _compute_lock_masks(self) -> None:
        """Every permutation of the lock modifiers.

        A grab matches an *exact* modifier mask. Without this, the chord stops
        working the moment Num Lock or Caps Lock is on — the single most common
        cause of "my hotkey works sometimes".
        """
        _display, X, XK, _error, _ev = _import_xlib()
        caps = X.LockMask
        num = self._modifier_mask_for_keysym(XK.XK_Num_Lock) or X.Mod2Mask
        scroll = self._modifier_mask_for_keysym(XK.XK_Scroll_Lock) or 0

        masks = {0}
        for extra in (caps, num, scroll):
            if not extra:
                continue
            masks |= {m | extra for m in masks}
        self._lock_masks = sorted(masks)
        log.debug("lock modifier permutations", count=len(self._lock_masks))

    def _modifier_mask_for_keysym(self, keysym: int) -> int:
        """Find which modifier index a keysym is mapped to, if any."""
        try:
            keycode = self._display.keysym_to_keycode(keysym)
            if not keycode:
                return 0
            mapping = self._display.get_modifier_mapping()
            for index, keycodes in enumerate(mapping):
                if keycode in list(keycodes):
                    return 1 << index
        except Exception:  # pragma: no cover - server dependent
            return 0
        return 0

    # -- binding ---------------------------------------------------------

    def _resolve(self, chord: Chord) -> tuple[int, int]:
        _display, X, XK, _error, _ev = _import_xlib()
        keysym = XK.string_to_keysym(chord.key)
        if not keysym:
            # Single characters not in the keysym table (rare) and names we
            # normalised differently.
            keysym = XK.string_to_keysym(chord.key.capitalize())
        if not keysym:
            raise Fault(
                code=FaultCode.SHORTCUT_BIND_FAILED,
                message=f"X11 does not know a key named {chord.key!r} (in chord {chord})",
                remedy=f"Choose a different key: dictator keys set dictate <chord>",
            )
        keycode = self._display.keysym_to_keycode(keysym)
        if not keycode:
            raise Fault(
                code=FaultCode.SHORTCUT_BIND_FAILED,
                message=f"{chord.key!r} is not on the current keyboard layout (chord {chord})",
                remedy="Switch layout, or choose a different key for the shortcut.",
            )
        mask = 0
        for modifier in chord.modifiers:
            mask |= getattr(X, _MODIFIER_MASK_NAMES[modifier])
        return keycode, mask

    async def bind(
        self, shortcuts: dict[str, Chord], descriptions: dict[str, str]
    ) -> BindResult:
        if self._display is None:
            raise Fault(
                code=FaultCode.SHORTCUT_BIND_FAILED,
                message="bind() called before start()",
                remedy="Report this with the output of: dictator doctor --verbose",
            )
        self._ungrab_all()
        result = BindResult()
        for shortcut_id, chord in shortcuts.items():
            try:
                keycode, mask = self._resolve(chord)
                self._grab(keycode, mask, chord)
            except Fault as fault:
                result.rejected[shortcut_id] = fault.message
                log.warning("shortcut rejected", id=shortcut_id, chord=str(chord),
                            reason=fault.message)
                continue
            self._grabs[(keycode, mask)] = shortcut_id
            result.bound[shortcut_id] = chord
            log.info("shortcut grabbed", id=shortcut_id, chord=str(chord), keycode=keycode)
        self._bound = dict(result.bound)
        return result

    def _grab(self, keycode: int, mask: int, chord: Chord) -> None:
        _display, X, _XK, error, _ev = _import_xlib()
        catcher = error.CatchError(error.BadAccess)
        for root in self._roots:
            for lock in self._lock_masks:
                root.grab_key(
                    keycode,
                    mask | lock,
                    True,
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                    onerror=catcher,
                )
        self._display.sync()
        if catcher.get_error():
            self._ungrab(keycode, mask)
            raise Fault(
                code=FaultCode.SHORTCUT_TAKEN,
                message=f"{chord} is already grabbed by another application",
                remedy=(
                    f"Another program owns {chord}. Free it there, or pick a different "
                    f"chord: dictator keys set dictate <chord>"
                ),
            )

    def _ungrab(self, keycode: int, mask: int) -> None:
        for root in self._roots:
            for lock in self._lock_masks:
                try:
                    root.ungrab_key(keycode, mask | lock)
                except Exception:  # pragma: no cover - best effort
                    pass

    def _ungrab_all(self) -> None:
        for keycode, mask in list(self._grabs):
            self._ungrab(keycode, mask)
        self._grabs.clear()
        if self._display is not None:
            try:
                self._display.sync()
            except Exception:  # pragma: no cover
                pass

    # -- event pump ------------------------------------------------------

    def _pump(self) -> None:
        _display, X, _XK, _error, _ev = _import_xlib()
        display = self._display
        while not self._stopping.is_set():
            try:
                count = display.pending_events()
                if not count:
                    # Xlib has no timeout-aware wait; poll the fd instead of
                    # blocking forever so stop() is responsive.
                    import select

                    ready, _, _ = select.select([display.fileno()], [], [], 0.2)
                    if not ready:
                        continue
                    count = display.pending_events()
                for _ in range(count):
                    event = display.next_event()
                    self._handle(event, X)
            except Exception as exc:  # pragma: no cover - server may vanish
                if not self._stopping.is_set():
                    log.error("x11 event pump failed", error=str(exc))
                break

    def _handle(self, event, X) -> None:
        if event.type == X.MappingNotify:
            # Layout changed; keycodes may have moved under our grabs.
            try:
                self._display.refresh_keyboard_mapping(event)
            except Exception:  # pragma: no cover
                pass
            log.info("keyboard mapping changed, re-resolving shortcuts")
            self._rebind_after_mapping_change()
            return

        if event.type not in (X.KeyPress, X.KeyRelease):
            return

        base = event.state & ~self._all_lock_bits()
        shortcut_id = self._grabs.get((event.detail, base))
        if shortcut_id is None:
            return
        which = ShortcutEvent.PRESSED if event.type == X.KeyPress else ShortcutEvent.RELEASED
        self._emit(shortcut_id, which)

    def _all_lock_bits(self) -> int:
        bits = 0
        for mask in self._lock_masks:
            bits |= mask
        return bits

    def _rebind_after_mapping_change(self) -> None:
        current = dict(self._bound)
        if not current:
            return
        self._ungrab_all()
        for shortcut_id, chord in current.items():
            try:
                keycode, mask = self._resolve(chord)
                self._grab(keycode, mask, chord)
                self._grabs[(keycode, mask)] = shortcut_id
            except Fault as fault:
                log.warning(
                    "shortcut lost after layout change",
                    id=shortcut_id,
                    chord=str(chord),
                    reason=fault.message,
                )

    def _emit(self, shortcut_id: str, which: ShortcutEvent) -> None:
        if self._callback is None or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._callback, shortcut_id, which)

    # -- teardown --------------------------------------------------------

    async def stop(self) -> None:
        self._stopping.set()
        if self._display is not None:
            self._ungrab_all()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._display is not None:
            try:
                self._display.close()
            except Exception:  # pragma: no cover
                pass
            self._display = None
        self._bound.clear()

    def bound(self) -> dict[str, Chord]:
        return dict(self._bound)
