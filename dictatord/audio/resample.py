"""Sample-rate conversion for capture.

Whisper is trained at 16 kHz, but plenty of microphones offer only 44.1 or
48 kHz and refuse anything else outright — PortAudio answers with
``Invalid sample rate [PaErrorCode -9997]`` and the stream never opens. Rather
than treat that as an unsupported device, capture runs at whatever the hardware
gives and converts here.
"""
from __future__ import annotations

from math import gcd

import numpy as np


class Resampler:
    """Streaming rational resampler with continuity across blocks.

    Resampling each block independently produces a click at every boundary,
    because the filter starts cold each time. Carrying a tail of the previous
    block across the call removes the discontinuity, which matters here: those
    clicks look like speech onsets to a voice-activity detector.
    """

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("sample rates must be positive")
        self.source_rate = int(source_rate)
        self.target_rate = int(target_rate)
        divisor = gcd(self.source_rate, self.target_rate)
        self.up = self.target_rate // divisor
        self.down = self.source_rate // divisor
        #: Overlap carried between blocks, in source samples.
        self._overlap = max(32, self.down * 8)
        self._tail = np.zeros(0, dtype=np.float32)
        self._method = self._pick_method()

    @property
    def is_identity(self) -> bool:
        return self.source_rate == self.target_rate

    def _pick_method(self):
        try:
            from scipy.signal import resample_poly  # noqa: F401

            return "poly"
        except Exception:
            # Linear interpolation is audibly worse but keeps the product
            # working without scipy; speech recognition tolerates it.
            return "linear"

    def reset(self) -> None:
        self._tail = np.zeros(0, dtype=np.float32)

    def process(self, block: np.ndarray) -> np.ndarray:
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        if self.is_identity or block.size == 0:
            return block

        padded = np.concatenate((self._tail, block))
        self._tail = padded[-self._overlap :].copy() if padded.size >= self._overlap else padded.copy()

        if self._method == "poly":
            from scipy.signal import resample_poly

            converted = resample_poly(padded, self.up, self.down).astype(np.float32)
        else:
            count = int(round(padded.size * self.target_rate / self.source_rate))
            if count <= 0:
                return np.zeros(0, dtype=np.float32)
            converted = np.interp(
                np.linspace(0, padded.size - 1, count, dtype=np.float64),
                np.arange(padded.size),
                padded,
            ).astype(np.float32)

        # Drop the region that came from the carried tail, so audio is neither
        # repeated nor lost between blocks.
        skip = int(round(min(self._tail.size, self._overlap) * self.target_rate / self.source_rate))
        return converted[skip:] if skip < converted.size else np.zeros(0, dtype=np.float32)
