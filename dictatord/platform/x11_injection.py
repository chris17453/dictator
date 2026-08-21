"""Input injection on X11 via XTEST.

X11 is strictly more capable than Wayland here: it can also name the focused
application from ``WM_CLASS``, which makes per-application paste profiles fully
automatic (v2.md §5.4). It is also strictly less safe — any client may inject
into any other — which ``dictator doctor`` reports rather than hides.
"""
from __future__ import annotations

import asyncio
from typing import Any

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .base import Capability, InjectionBackend
from .chords import Chord
from .clipboard import Clipboard, NullClipboard
from .keysyms import MODIFIER_KEYSYMS, char_to_keysym, key_to_keysym

log = get_logger(__name__)


class X11Injection(InjectionBackend):
    name = "xtest"

    def __init__(
        self,
        clipboard: Clipboard | None = None,
        key_delay_ms: float = 2.0,
    ) -> None:
        self._clipboard = clipboard or NullClipboard()
        self._display = None
        self._key_delay = key_delay_ms / 1000.0
        #: Keycodes we temporarily remapped to reach an unmapped keysym.
        self._scratch_keycode: int | None = None

    # -- probe -----------------------------------------------------------

    @classmethod
    async def probe(cls) -> Capability:
        try:
            from Xlib import display
            from Xlib.ext import xtest
        except Exception as exc:
            return Capability(
                name=cls.name,
                available=False,
                reason=f"python-xlib with the XTEST extension is required: {exc}",
            )
        try:
            conn = display.Display()
            has_xtest = conn.query_extension("XTEST") is not None
            conn.close()
        except Exception as exc:
            return Capability(
                name=cls.name, available=False, reason=f"cannot open the X display: {exc}"
            )
        if not has_xtest:
            return Capability(
                name=cls.name,
                available=False,
                reason="the X server does not offer the XTEST extension",
            )
        return Capability(
            name=cls.name,
            available=True,
            supports_focus_query=True,
            requires_consent=False,
            trust="unrestricted; any X client may inject input into any other",
            detail="XTEST",
            rank=90,
        )

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if self._display is not None:
            return
        from Xlib import display

        try:
            self._display = display.Display()
        except Exception as exc:
            raise Fault(
                code=FaultCode.NO_INJECTION_BACKEND,
                message=f"cannot open the X display: {exc}",
                remedy="Check that DISPLAY is set and the X server is reachable.",
            ) from exc
        log.info("x11 injection ready")

    async def stop(self) -> None:
        await self._clipboard.stop()
        if self._display is not None:
            try:
                self._display.close()
            except Exception:  # pragma: no cover
                pass
            self._display = None

    # -- clipboard -------------------------------------------------------

    async def set_clipboard(self, text: str) -> None:
        await self._clipboard.set_text(text)

    async def get_clipboard(self) -> str | None:
        return await self._clipboard.get_text()

    # -- injection -------------------------------------------------------

    def _require(self):
        if self._display is None:
            raise Fault(
                code=FaultCode.INJECTION_FAILED,
                message="no X display; input cannot be synthesised",
                remedy="Run 'dictator restart' from within your graphical session.",
            )
        return self._display

    def _keycode_for(self, keysym: int) -> tuple[int, bool]:
        """Resolve a keysym to a keycode, remapping a scratch key if needed.

        Characters outside the active layout have no keycode. Rather than
        dropping them, we borrow a spare keycode, map the keysym onto it, use
        it, and restore it afterwards. This is what makes typing layout-safe.
        """
        display = self._require()
        keycode = display.keysym_to_keycode(keysym)
        if keycode:
            return keycode, False

        scratch = self._find_scratch_keycode()
        display.change_keyboard_mapping(scratch, [[keysym, keysym, keysym, keysym]])
        display.sync()
        return scratch, True

    def _find_scratch_keycode(self) -> int:
        if self._scratch_keycode is not None:
            return self._scratch_keycode
        display = self._require()
        info = display.get_keyboard_mapping(8, 248 - 8)
        for offset, entry in enumerate(info):
            if not any(entry):
                self._scratch_keycode = 8 + offset
                return self._scratch_keycode
        # Nothing free: fall back to a high keycode and accept the collision.
        self._scratch_keycode = 247
        return self._scratch_keycode

    def _restore_scratch(self) -> None:
        if self._scratch_keycode is None or self._display is None:
            return
        try:
            self._display.change_keyboard_mapping(
                self._scratch_keycode, [[0, 0, 0, 0]]
            )
            self._display.sync()
        except Exception:  # pragma: no cover
            pass

    def _press(self, keycode: int, down: bool) -> None:
        from Xlib import X
        from Xlib.ext import xtest

        display = self._require()
        xtest.fake_input(display, X.KeyPress if down else X.KeyRelease, keycode)
        display.sync()

    async def send_chord(self, chord: Chord) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_chord_sync, chord)

    def _send_chord_sync(self, chord: Chord) -> None:
        import time

        modifier_codes = []
        for name in chord.modifiers:
            keysym = MODIFIER_KEYSYMS.get(name)
            if keysym is None:
                continue
            code, _ = self._keycode_for(keysym)
            modifier_codes.append(code)

        key_code, remapped = self._keycode_for(key_to_keysym(chord.key))
        try:
            for code in modifier_codes:
                self._press(code, True)
            self._press(key_code, True)
            time.sleep(self._key_delay)
            self._press(key_code, False)
            for code in reversed(modifier_codes):
                self._press(code, False)
        finally:
            if remapped:
                self._restore_scratch()

    async def type_text(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._type_text_sync, text)

    def _type_text_sync(self, text: str) -> None:
        import time

        from Xlib import X
        from Xlib.ext import xtest

        display = self._require()
        shift_code = display.keysym_to_keycode(MODIFIER_KEYSYMS["Shift"])
        remapped_any = False
        try:
            for char in text:
                keysym = char_to_keysym(char)
                keycode = display.keysym_to_keycode(keysym)
                shifted = False
                if keycode:
                    # Determine whether the keysym sits in the shifted slot.
                    entry = display.keycode_to_keysym(keycode, 0)
                    if entry != keysym:
                        shifted = display.keycode_to_keysym(keycode, 1) == keysym
                else:
                    keycode, _ = self._keycode_for(keysym)
                    remapped_any = True

                if shifted and shift_code:
                    self._press(shift_code, True)
                self._press(keycode, True)
                self._press(keycode, False)
                if shifted and shift_code:
                    self._press(shift_code, False)
                if self._key_delay:
                    time.sleep(self._key_delay)
        finally:
            if remapped_any:
                self._restore_scratch()

    # -- focus -----------------------------------------------------------

    async def focused_app_id(self) -> str | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._focused_app_id_sync)

    def _focused_app_id_sync(self) -> str | None:
        """The focused window's WM_CLASS, walking up to the toplevel."""
        try:
            from Xlib import X

            display = self._require()
            window = display.get_input_focus().focus
            if not window or window in (X.NONE, X.PointerRoot):
                return None
            for _ in range(8):
                if window is None or isinstance(window, int):
                    return None
                try:
                    wm_class = window.get_wm_class()
                except Exception:
                    wm_class = None
                if wm_class:
                    # (instance, class); the class is the stable identifier.
                    return (wm_class[1] or wm_class[0] or "").lower() or None
                parent = window.query_tree().parent
                if not parent or parent == window:
                    return None
                window = parent
        except Exception as exc:  # pragma: no cover - server dependent
            log.debug("focused window lookup failed", error=str(exc))
        return None
