"""The two narrow interfaces every platform backend implements.

Everything above these — the session FSM, the ASR pipeline, memory, the tray,
the CLI — is display-server agnostic and imports neither concrete backend.
Backends are the only place a platform name appears (v2.md §5).

The interfaces are async because the daemon runs one asyncio loop. Backends
whose native API is blocking (X11) own a thread and marshal events back into
the loop; that detail never leaks upward.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

from .chords import Chord


class ShortcutEvent(str, Enum):
    PRESSED = "pressed"
    RELEASED = "released"


#: Called as ``callback(shortcut_id, event)`` on the daemon's event loop.
ShortcutCallback = Callable[[str, ShortcutEvent], None]


@dataclass(frozen=True)
class Capability:
    """What a backend can actually do, discovered by probing rather than assumed."""

    name: str
    available: bool
    reason: str = ""
    #: Whether the backend reports key release as well as key press. Without
    #: it, hold-to-talk is impossible and must be disabled rather than bound.
    supports_release: bool = True
    #: Whether the backend can name the focused application (v2.md §5.4).
    supports_focus_query: bool = False
    #: Whether using it requires a one-time user consent prompt.
    requires_consent: bool = False
    #: One-line description of the trust model, surfaced by ``dictator doctor``.
    trust: str = ""
    detail: str = ""
    #: Preference within a session type; higher wins. Ties break on order.
    rank: int = 0

    def summary(self) -> str:
        if self.available:
            return f"{self.name}: available"
        return f"{self.name}: unavailable ({self.reason})"


@dataclass
class BindResult:
    """Outcome of binding the full shortcut set."""

    bound: dict[str, Chord] = field(default_factory=dict)
    rejected: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.rejected


class ShortcutBackend(abc.ABC):
    """Binds chords and reports press and release."""

    name: str = "abstract"

    @classmethod
    @abc.abstractmethod
    async def probe(cls) -> Capability:
        """Report whether this backend can run here, without lasting side effects."""

    @abc.abstractmethod
    async def start(self, callback: ShortcutCallback) -> None:
        """Begin delivering events. Idempotent."""

    @abc.abstractmethod
    async def bind(self, shortcuts: dict[str, Chord], descriptions: dict[str, str]) -> BindResult:
        """Register the complete shortcut set, replacing any previous set.

        Binding is all-at-once because the portal's BindShortcuts is: a second
        call with a different set is a new registration, not an addition.
        """

    @abc.abstractmethod
    async def stop(self) -> None:
        """Release every grab and stop delivering events. Idempotent."""

    @property
    def supports_release(self) -> bool:
        return True

    def bound(self) -> dict[str, Chord]:
        return {}


class InjectionBackend(abc.ABC):
    """Places text on the clipboard and puts it into the focused field."""

    name: str = "abstract"

    @classmethod
    @abc.abstractmethod
    async def probe(cls) -> Capability:
        ...

    @abc.abstractmethod
    async def start(self) -> None:
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        ...

    @abc.abstractmethod
    async def set_clipboard(self, text: str) -> None:
        ...

    @abc.abstractmethod
    async def get_clipboard(self) -> str | None:
        """Current clipboard text, or None when it cannot be read."""

    @abc.abstractmethod
    async def send_chord(self, chord: Chord) -> None:
        """Synthesise a key chord into the focused application."""

    @abc.abstractmethod
    async def type_text(self, text: str) -> None:
        """Synthesise the text character by character."""

    async def focused_app_id(self) -> str | None:
        """Identify the focused application, or None when unobtainable.

        Returning None is the correct, expected answer on Wayland; callers fall
        back to the configured default profile (v2.md §5.4).
        """
        return None


class Notifier(Protocol):
    """Minimal desktop-notification surface, so backends need not import a UI."""

    def notify(self, summary: str, body: str = "", urgent: bool = False) -> None: ...
