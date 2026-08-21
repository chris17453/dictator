"""Ring buffer, VAD, and level framing."""
import numpy as np
import pytest

from dictatord.audio.ring import RingBuffer
from dictatord.audio.vad import EnergyVad, SpeechState


def test_ring_holds_recent_samples():
    ring = RingBuffer(10)
    ring.write(np.arange(6, dtype=np.float32))
    assert list(ring.read_all()) == [0, 1, 2, 3, 4, 5]


def test_ring_wraps_and_keeps_the_newest():
    ring = RingBuffer(10)
    ring.write(np.arange(12, dtype=np.float32))
    assert list(ring.read_all()) == list(range(2, 12))


def test_write_larger_than_capacity_keeps_the_tail():
    ring = RingBuffer(4)
    ring.write(np.arange(10, dtype=np.float32))
    assert list(ring.read_all()) == [6, 7, 8, 9]


def test_read_last_is_bounded_by_what_exists():
    ring = RingBuffer(10)
    ring.write(np.arange(3, dtype=np.float32))
    assert len(ring.read_last(100)) == 3


def test_clear_empties():
    ring = RingBuffer(10)
    ring.write(np.arange(5, dtype=np.float32))
    ring.clear()
    assert len(ring) == 0


def test_empty_write_is_harmless():
    ring = RingBuffer(4)
    ring.write(np.zeros(0, dtype=np.float32))
    assert len(ring) == 0


def test_invalid_capacity_is_rejected():
    with pytest.raises(ValueError):
        RingBuffer(0)


# -- VAD -------------------------------------------------------------------


def frames(sample_rate=16000, ms=20):
    n = int(sample_rate * ms / 1000)
    return np.zeros(n, dtype=np.float32), np.full(n, 0.3, dtype=np.float32)


def test_vad_detects_a_speech_segment():
    vad = EnergyVad(16000, threshold=0.02, silence_ms=200, min_speech_ms=100)
    quiet, loud = frames()
    events = []
    for i in range(60):
        result = vad.feed(loud if 10 <= i < 30 else quiet)
        if result.started:
            events.append(("start", i))
        if result.ended:
            events.append(("end", i))
    assert [e[0] for e in events] == ["start", "end"]


def test_vad_ignores_a_brief_click():
    """A single loud frame is noise, not speech."""
    vad = EnergyVad(16000, threshold=0.02, min_speech_ms=200)
    quiet, loud = frames()
    vad.feed(loud)
    assert vad.state is SpeechState.SILENCE


def test_vad_hysteresis_survives_a_quiet_moment_mid_word():
    vad = EnergyVad(16000, threshold=0.02, silence_ms=400, min_speech_ms=40)
    quiet, loud = frames()
    for _ in range(6):
        vad.feed(loud)
    assert vad.in_speech
    for _ in range(3):          # 60 ms of quiet, well under silence_ms
        vad.feed(quiet)
    assert vad.in_speech, "a short pause must not close the segment"


def test_vad_reset_returns_to_silence():
    vad = EnergyVad(16000, threshold=0.02, min_speech_ms=20)
    _, loud = frames()
    for _ in range(5):
        vad.feed(loud)
    vad.reset()
    assert vad.state is SpeechState.SILENCE


def test_rms_of_silence_is_zero():
    assert EnergyVad.rms(np.zeros(100, dtype=np.float32)) == 0.0
    assert EnergyVad.rms(np.zeros(0, dtype=np.float32)) == 0.0
