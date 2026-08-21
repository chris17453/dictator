"""Sample-rate conversion.

Whisper wants 16 kHz; plenty of microphones offer only 44.1 or 48 kHz and
refuse anything else outright ("Invalid sample rate [PaErrorCode -9997]").
Capture takes what the device gives and converts here.
"""
import numpy as np
import pytest

from dictatord.audio.resample import Resampler


def tone(frequency, seconds, rate, amplitude=0.5):
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def dominant_frequency(signal, rate):
    spectrum = np.abs(np.fft.rfft(signal))
    return float(np.fft.rfftfreq(signal.size, 1 / rate)[int(np.argmax(spectrum))])


@pytest.mark.parametrize("source,target,up,down", [
    (48000, 16000, 1, 3),
    (44100, 16000, 160, 441),
    (16000, 16000, 1, 1),
    (32000, 16000, 1, 2),
])
def test_ratios_are_reduced(source, target, up, down):
    resampler = Resampler(source, target)
    assert (resampler.up, resampler.down) == (up, down)


def test_identity_passes_audio_through_untouched():
    resampler = Resampler(16000, 16000)
    assert resampler.is_identity
    block = tone(440, 0.1, 16000)
    assert np.array_equal(resampler.process(block), block)


def test_pitch_is_preserved():
    resampler = Resampler(48000, 16000)
    out = resampler.process(tone(440, 0.5, 48000))
    assert dominant_frequency(out, 16000) == pytest.approx(440, abs=15)


def test_output_length_matches_the_ratio():
    resampler = Resampler(48000, 16000)
    out = np.concatenate([resampler.process(tone(440, 0.1, 48000)) for _ in range(5)])
    # 0.5 s at 16 kHz, allowing for filter warm-up on the first block.
    assert 7600 <= out.size <= 8000


def test_streaming_has_no_boundary_discontinuity():
    """Per-block resampling clicks at every seam, and a VAD reads that as speech."""
    rate = 48000
    whole = tone(440, 0.3, rate)
    blocks = np.array_split(whole, 15)

    resampler = Resampler(rate, 16000)
    streamed = np.concatenate([resampler.process(b) for b in blocks])

    # A click is a large sample-to-sample jump. A clean 440 Hz tone at 16 kHz
    # steps by well under 0.2 between adjacent samples.
    assert np.max(np.abs(np.diff(streamed))) < 0.25


def test_empty_blocks_are_harmless():
    resampler = Resampler(48000, 16000)
    assert resampler.process(np.zeros(0, dtype=np.float32)).size == 0


def test_silence_stays_silent():
    resampler = Resampler(48000, 16000)
    out = resampler.process(np.zeros(4800, dtype=np.float32))
    assert out.size == 0 or np.allclose(out, 0.0)


def test_reset_clears_carried_state():
    resampler = Resampler(48000, 16000)
    resampler.process(tone(440, 0.1, 48000))
    resampler.reset()
    assert resampler._tail.size == 0


@pytest.mark.parametrize("bad", [(0, 16000), (48000, 0), (-1, 16000)])
def test_invalid_rates_are_rejected(bad):
    with pytest.raises(ValueError):
        Resampler(*bad)


def test_upsampling_also_works():
    resampler = Resampler(8000, 16000)
    out = resampler.process(tone(300, 0.5, 8000))
    assert out.size > 3000
    assert dominant_frequency(out, 16000) == pytest.approx(300, abs=20)
