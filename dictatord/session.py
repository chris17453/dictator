"""The dictation session state machine.

One chord, two behaviours. A press starts recording immediately. What happens
on release depends on how long the key was held:

* released within ``hold_threshold_ms`` — a *tap*. Recording continues; the
  next tap stops it. This is toggle mode.
* held longer — a *hold*. Recording stops on release. This is push-to-talk.

The user never chooses a mode; the distinction is in their fingers. Starting on
press either way means the first word is captured in both, and the pre-roll ring
buffer covers the moment before the chord even registered.
"""
from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Awaitable, Callable

import numpy as np

from .audio.capture import Capture
from .audio.vad import EnergyVad
from .errors import Fault
from .logging import get_logger
from .platform.base import ShortcutEvent

log = get_logger(__name__)


class State(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    DELIVERING = "delivering"


class Mode(str, Enum):
    TOGGLE = "toggle"
    HOLD = "hold"


class Session:
    """Accumulates audio for one utterance and reports its own state."""

    _next_id = 0

    def __init__(self, mode: Mode, profile_override: str = "") -> None:
        Session._next_id += 1
        self.id = Session._next_id
        self.mode = mode
        self.profile_override = profile_override
        self.started_at = time.monotonic()
        self.chunks: list[np.ndarray] = []
        self.cancelled = False
        self.partial_text = ""
        self._samples = 0

    def add(self, block: np.ndarray) -> None:
        self.chunks.append(block)
        self._samples += block.size

    @property
    def sample_count(self) -> int:
        return self._samples

    def audio(self) -> np.ndarray:
        if not self.chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.chunks)

    def duration_s(self, sample_rate: int) -> float:
        return self._samples / float(sample_rate) if sample_rate else 0.0

    @property
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at


class SessionManager:
    """Drives sessions from shortcut events and audio blocks."""

    def __init__(
        self,
        capture: Capture,
        *,
        hold_threshold_ms: int = 250,
        max_utterance_s: int = 300,
        supports_release: bool = True,
        vad: EnergyVad | None = None,
        on_state: Callable[[State, dict], None] | None = None,
        on_finished: Callable[[Session], Awaitable[None]] | None = None,
    ) -> None:
        self.capture = capture
        self.hold_threshold = hold_threshold_ms / 1000.0
        self.max_utterance_s = max_utterance_s
        #: Whether the shortcut backend reports key release. Without it a
        #: press can only ever mean toggle: no release will arrive to end a
        #: hold, and the session would be impossible to stop from the chord.
        self.supports_release = supports_release
        self.vad = vad
        self.on_state = on_state
        self.on_finished = on_finished

        self.state = State.IDLE
        self.session: Session | None = None
        self._press_at: float | None = None
        self._press_shortcut: str | None = None
        self._promoted_to_toggle = False
        self._timeout_task: asyncio.Task | None = None

    # -- state -----------------------------------------------------------

    def _set_state(self, state: State, **detail) -> None:
        if self.state is state and not detail:
            return
        self.state = state
        log.debug("state", state=state.value, **detail)
        if self.on_state is not None:
            self.on_state(state, {k: str(v) for k, v in detail.items()})

    @property
    def is_active(self) -> bool:
        return self.session is not None and self.state is State.LISTENING

    # -- shortcut events -------------------------------------------------

    async def on_shortcut(
        self, shortcut_id: str, event: ShortcutEvent, profile_override: str = ""
    ) -> None:
        if event is ShortcutEvent.PRESSED:
            await self._on_press(shortcut_id, profile_override)
        else:
            await self._on_release(shortcut_id)

    async def _on_press(self, shortcut_id: str, profile_override: str) -> None:
        if self.is_active:
            # A second press while listening always means stop, whichever mode
            # we are in. This is what makes tap-tap work.
            if (
                self._promoted_to_toggle
                or self.session.mode is Mode.TOGGLE
                or not self.supports_release
            ):
                await self.stop()
            return

        if self.state is not State.IDLE:
            log.debug("press ignored; busy", state=self.state.value)
            return

        self._press_at = time.monotonic()
        self._press_shortcut = shortcut_id
        self._promoted_to_toggle = False
        await self.start(
            Mode.HOLD if self.supports_release else Mode.TOGGLE,
            profile_override=profile_override,
        )

    async def _on_release(self, shortcut_id: str) -> None:
        if self._press_at is None or shortcut_id != self._press_shortcut:
            return
        held = time.monotonic() - self._press_at
        self._press_at = None

        if not self.is_active:
            return

        if held < self.hold_threshold:
            # A tap. Stay recording; the next press stops us.
            self._promoted_to_toggle = True
            self.session.mode = Mode.TOGGLE
            self._set_state(State.LISTENING, mode="toggle")
            log.info("tap detected; recording until the next press",
                     held_ms=int(held * 1000))
            return

        log.debug("hold released; stopping", held_ms=int(held * 1000))
        await self.stop()

    # -- lifecycle -------------------------------------------------------

    async def start(self, mode: Mode = Mode.TOGGLE, profile_override: str = "") -> Session:
        if self.session is not None:
            return self.session

        session = Session(mode=mode, profile_override=profile_override)
        self.session = session

        # The audio from just before the chord registered. This is what stops
        # the first word being clipped.
        preroll = self.capture.take_preroll()
        if preroll.size:
            session.add(preroll)

        if self.vad is not None:
            self.vad.reset()

        self._set_state(State.LISTENING, session=session.id, mode=mode.value)
        log.info(
            "session started",
            id=session.id,
            mode=mode.value,
            preroll_ms=int(1000 * preroll.size / max(1, self.capture.sample_rate)),
        )
        self._timeout_task = asyncio.create_task(self._enforce_timeout(session))
        return session

    async def _enforce_timeout(self, session: Session) -> None:
        try:
            await asyncio.sleep(self.max_utterance_s)
        except asyncio.CancelledError:
            return
        if self.session is session and self.is_active:
            log.warning("utterance hit the maximum duration; stopping",
                        seconds=self.max_utterance_s)
            await self.stop()

    async def stop(self) -> Session | None:
        session = self.session
        if session is None:
            return None
        self._cancel_timeout()
        self.session = None
        self._press_at = None
        self._promoted_to_toggle = False

        if session.sample_count == 0:
            self._set_state(State.IDLE, reason="no audio")
            return session

        self._set_state(State.TRANSCRIBING, session=session.id)
        if self.on_finished is not None:
            await self.on_finished(session)
        return session

    async def cancel(self) -> bool:
        session = self.session
        if session is None:
            return False
        session.cancelled = True
        self._cancel_timeout()
        self.session = None
        self._press_at = None
        self._promoted_to_toggle = False
        self._set_state(State.IDLE, reason="cancelled")
        log.info("session cancelled", id=session.id)
        return True

    def _cancel_timeout(self) -> None:
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    def finish(self) -> None:
        """Return to idle once transcription and delivery have completed."""
        self._set_state(State.IDLE)

    # -- audio -----------------------------------------------------------

    def feed(self, block: np.ndarray) -> None:
        """Called for every captured block, from the event loop."""
        session = self.session
        if session is None or self.state is not State.LISTENING:
            return
        session.add(block)
