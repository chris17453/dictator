"""The tap-or-hold state machine: one chord, two behaviours."""
import asyncio

import numpy as np
import pytest

from dictatord.audio.capture import Capture
from dictatord.platform.base import ShortcutEvent as E
from dictatord.session import Mode, SessionManager, State


def make_manager(finished, hold_ms=250):
    capture = Capture(sample_rate=16000, preroll_ms=300)
    capture.ring.write(np.full(16000, 0.1, dtype=np.float32))

    async def on_finished(session):
        finished.append(session)

    return SessionManager(capture, hold_threshold_ms=hold_ms, on_finished=on_finished)


def block(value=0.2, n=1600):
    return np.full(n, value, dtype=np.float32)


@pytest.mark.asyncio
async def test_hold_stops_on_release():
    finished = []
    manager = make_manager(finished)
    await manager.on_shortcut("dictate", E.PRESSED)
    assert manager.state is State.LISTENING
    manager.feed(block())
    await asyncio.sleep(0.4)
    await manager.on_shortcut("dictate", E.RELEASED)
    assert len(finished) == 1
    assert finished[0].mode is Mode.HOLD


@pytest.mark.asyncio
async def test_tap_keeps_listening_and_second_tap_stops():
    finished = []
    manager = make_manager(finished)
    await manager.on_shortcut("dictate", E.PRESSED)
    await asyncio.sleep(0.02)
    await manager.on_shortcut("dictate", E.RELEASED)
    assert manager.state is State.LISTENING, "a tap must not stop recording"
    assert not finished

    manager.feed(block())
    await manager.on_shortcut("dictate", E.PRESSED)
    assert len(finished) == 1
    assert finished[0].mode is Mode.TOGGLE


@pytest.mark.asyncio
async def test_preroll_is_captured_so_the_first_word_survives():
    finished = []
    manager = make_manager(finished)
    session = await manager.start(Mode.TOGGLE)
    # 300 ms of pre-roll at 16 kHz.
    assert session.sample_count == pytest.approx(4800, abs=1)


@pytest.mark.asyncio
async def test_cancel_discards_without_delivering():
    finished = []
    manager = make_manager(finished)
    await manager.start(Mode.TOGGLE)
    manager.feed(block())
    assert await manager.cancel() is True
    assert manager.state is State.IDLE
    assert not finished


@pytest.mark.asyncio
async def test_cancel_when_idle_is_a_no_op():
    manager = make_manager([])
    assert await manager.cancel() is False


@pytest.mark.asyncio
async def test_release_without_press_is_ignored():
    finished = []
    manager = make_manager(finished)
    await manager.on_shortcut("dictate", E.RELEASED)
    assert manager.state is State.IDLE
    assert not finished


@pytest.mark.asyncio
async def test_audio_is_only_accumulated_while_listening():
    finished = []
    manager = make_manager(finished)
    manager.feed(block())  # ignored: idle
    session = await manager.start(Mode.TOGGLE)
    before = session.sample_count
    manager.feed(block())
    assert session.sample_count == before + 1600


@pytest.mark.asyncio
async def test_empty_session_returns_to_idle_without_delivering():
    finished = []
    capture = Capture(sample_rate=16000, preroll_ms=0)

    async def on_finished(session):
        finished.append(session)

    manager = SessionManager(capture, on_finished=on_finished)
    await manager.start(Mode.TOGGLE)
    await manager.stop()
    assert manager.state is State.IDLE
    assert not finished, "silence must not run the delivery pipeline"


@pytest.mark.asyncio
async def test_max_duration_stops_the_session():
    finished = []
    capture = Capture(sample_rate=16000, preroll_ms=0)

    async def on_finished(session):
        finished.append(session)

    manager = SessionManager(capture, max_utterance_s=0.05, on_finished=on_finished)
    await manager.start(Mode.TOGGLE)
    manager.feed(block())
    await asyncio.sleep(0.2)
    assert manager.state is not State.LISTENING
    assert len(finished) == 1
