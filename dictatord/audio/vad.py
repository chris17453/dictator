"""Voice activity detection.

An energy gate with hysteresis, which needs no model download and no extra
dependency. It exists to answer one question — has the speaker stopped? — so
trailing silence is never decoded and an utterance can close itself (G-13).

The interface is deliberately narrow so a neural VAD can replace it without
touching the session machinery.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class SpeechState(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"


@dataclass
class VadResult:
    state: SpeechState
    #: True on the frame where speech began.
    started: bool = False
    #: True on the frame where a speech segment closed.
    ended: bool = False
    level: float = 0.0


class EnergyVad:
    """Root-mean-square gate with attack and release hysteresis.

    A single threshold chatters on breath and room tone. Requiring
    ``min_speech_ms`` of continuous energy to open, and ``silence_ms`` of
    continuous quiet to close, is what makes the segment boundaries usable.
    """

    def __init__(
        self,
        sample_rate: int,
        threshold: float = 0.02,
        silence_ms: int = 700,
        min_speech_ms: int = 150,
        release_ratio: float = 0.6,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.threshold = float(threshold)
        # Closing at a lower level than opening prevents flapping at the edge.
        self.release_threshold = float(threshold) * float(release_ratio)
        self.silence_samples = int(sample_rate * silence_ms / 1000)
        self.min_speech_samples = int(sample_rate * min_speech_ms / 1000)

        self.state = SpeechState.SILENCE
        self._speech_run = 0
        self._silence_run = 0
        self._pending_speech = 0
        self.last_level = 0.0

    def reset(self) -> None:
        self.state = SpeechState.SILENCE
        self._speech_run = 0
        self._silence_run = 0
        self._pending_speech = 0
        self.last_level = 0.0

    @staticmethod
    def rms(frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))

    def feed(self, frame: np.ndarray) -> VadResult:
        """Advance the detector by one frame of mono float32 audio."""
        level = self.rms(frame)
        self.last_level = level
        count = int(frame.size)
        started = ended = False

        if self.state is SpeechState.SILENCE:
            if level >= self.threshold:
                self._pending_speech += count
                if self._pending_speech >= self.min_speech_samples:
                    self.state = SpeechState.SPEECH
                    self._speech_run = self._pending_speech
                    self._silence_run = 0
                    self._pending_speech = 0
                    started = True
            else:
                self._pending_speech = 0
        else:
            if level >= self.release_threshold:
                self._speech_run += count
                self._silence_run = 0
            else:
                self._silence_run += count
                if self._silence_run >= self.silence_samples:
                    self.state = SpeechState.SILENCE
                    self._speech_run = 0
                    self._silence_run = 0
                    ended = True

        return VadResult(state=self.state, started=started, ended=ended, level=level)

    @property
    def in_speech(self) -> bool:
        return self.state is SpeechState.SPEECH
