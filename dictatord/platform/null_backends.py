"""Backends that do nothing, on purpose.

Tier 3 in the support matrix. They are what lets the daemon boot, serve its
D-Bus API, and run its whole pipeline with no display server at all — which is
what CI exercises on every commit (v2.md §5.5). They also make the degraded
path explicit rather than leaving ``None`` to be handled at call sites.
"""
from __future__ import annotations

from ..logging import get_logger
from .base import BindResult, Capability, InjectionBackend, ShortcutBackend, ShortcutCallback
from .chords import Chord
from .clipboard import Clipboard, NullClipboard

log = get_logger(__name__)


class NullShortcuts(ShortcutBackend):
    """Accepts bindings and never fires them.

    Dictation remains fully usable through ``dictator toggle`` over D-Bus.
    """

    name = "none"

    def __init__(self) -> None:
        self._bound: dict[str, Chord] = {}
        self._callback: ShortcutCallback | None = None

    @classmethod
    async def probe(cls) -> Capability:
        return Capability(
            name=cls.name,
            available=True,
            supports_release=False,
            requires_consent=False,
            trust="none; no keys are grabbed",
            detail="no global shortcuts; use 'dictator toggle' or bind it yourself",
            rank=0,
        )

    async def start(self, callback: ShortcutCallback) -> None:
        self._callback = callback

    async def bind(self, shortcuts: dict[str, Chord], descriptions: dict[str, str]) -> BindResult:
        self._bound = dict(shortcuts)
        log.warning(
            "no shortcut backend is available; chords are recorded but will not fire",
            chords=", ".join(f"{k}={v}" for k, v in shortcuts.items()) or "none",
        )
        return BindResult(bound=dict(shortcuts))

    async def stop(self) -> None:
        self._bound.clear()
        self._callback = None

    @property
    def supports_release(self) -> bool:
        return False

    def bound(self) -> dict[str, Chord]:
        return dict(self._bound)

    def fire(self, shortcut_id: str, event) -> None:
        """Test seam: drive the daemon without a display server."""
        if self._callback is not None:
            self._callback(shortcut_id, event)


class NullInjection(InjectionBackend):
    """Holds the clipboard and refuses to pretend it typed anything."""

    name = "none"

    def __init__(self, clipboard: Clipboard | None = None, **_ignored) -> None:
        self._clipboard = clipboard or NullClipboard()
        self.typed: list[str] = []
        self.chords: list[Chord] = []

    @classmethod
    async def probe(cls) -> Capability:
        return Capability(
            name=cls.name,
            available=True,
            supports_focus_query=False,
            trust="none; no input is synthesised",
            detail="clipboard only; text is never typed into other applications",
            rank=0,
        )

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        await self._clipboard.stop()

    async def set_clipboard(self, text: str) -> None:
        await self._clipboard.set_text(text)

    async def get_clipboard(self) -> str | None:
        return await self._clipboard.get_text()

    async def send_chord(self, chord: Chord) -> None:
        self.chords.append(chord)
        log.debug("chord not sent; no injection backend", chord=str(chord))

    async def type_text(self, text: str) -> None:
        self.typed.append(text)
        log.debug("text not typed; no injection backend", length=len(text))
