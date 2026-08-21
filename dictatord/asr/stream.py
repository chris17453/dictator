"""Partial transcription while the user is still speaking.

The daemon emits partials whether or not anything is listening; the overlay,
the tray, and the TUI are pure subscribers. Delivery uses finals only —
partials are for display, never for injection (v2.md §4.4).

Partials carry a stable prefix so a client can render settled text differently
from the tail that may still be revised, which is what stops the live view
flickering (v2.md K-3).
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import numpy as np

from ..errors import Fault
from ..logging import get_logger
from .engine import Engine

log = get_logger(__name__)


@dataclass
class Partial:
    session_id: int
    text: str
    #: How many characters of ``text`` have been stable across revisions.
    stable_chars: int = 0

    @property
    def stable(self) -> str:
        return self.text[: self.stable_chars]

    @property
    def tail(self) -> str:
        return self.text[self.stable_chars :]


PartialCallback = Callable[[Partial], Awaitable[None]]


def common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


class StreamingDecoder:
    """Re-decodes a growing buffer on a cadence and reports what changed.

    Whisper has no incremental decode, so a partial is a fresh greedy pass over
    the audio so far. That is affordable at this cadence on a GPU and is
    skipped automatically when it is not: if a pass takes longer than the
    interval, the next tick is dropped rather than queued.
    """

    def __init__(
        self,
        engine: Engine,
        sample_rate: int,
        *,
        interval_ms: int = 400,
        min_audio_ms: int = 700,
        on_partial: PartialCallback | None = None,
    ) -> None:
        self.engine = engine
        self.sample_rate = int(sample_rate)
        self.interval = interval_ms / 1000.0
        self.min_samples = int(sample_rate * min_audio_ms / 1000)
        self.on_partial = on_partial

        self._task: asyncio.Task | None = None
        self._last_text = ""
        self._stable = 0
        self._busy = False
        self.skipped = 0

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, session, prompt: str = "") -> None:
        if self.running:
            return
        self._last_text = ""
        self._stable = 0
        self.skipped = 0
        self._task = asyncio.create_task(self._loop(session, prompt))

    async def stop(self) -> str:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return self._last_text

    async def _loop(self, session, prompt: str) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval)
                if session.cancelled:
                    return
                if self._busy:
                    # The previous pass is still running; drop this tick rather
                    # than building a queue we can never drain.
                    self.skipped += 1
                    continue
                audio = session.audio()
                if audio.size < self.min_samples:
                    continue
                await self._decode_once(session, audio, prompt)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - never kill the session
            log.error("partial decode loop failed", error=str(exc))

    async def _decode_once(self, session, audio: np.ndarray, prompt: str) -> None:
        self._busy = True
        try:
            result = await self.engine.transcribe(
                audio, self.sample_rate, prompt=prompt, partial=True
            )
        except Fault as fault:
            log.debug("partial decode failed", error=fault.message)
            return
        finally:
            self._busy = False

        text = result.text.strip()
        if not text or text == self._last_text:
            return

        # Text that has survived a re-decode is unlikely to change again.
        self._stable = common_prefix_length(self._last_text, text)
        self._last_text = text

        if self.on_partial is not None:
            await self.on_partial(
                Partial(session_id=session.id, text=text, stable_chars=self._stable)
            )
