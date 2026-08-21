"""Continuous audio capture.

The stream stays open for the daemon's lifetime rather than being started per
utterance. That is what removes the cold-open cost of G-09, and it is what
makes the pre-roll ring buffer possible at all.

Levels are computed here and published as a signal, replacing the practice of
printing ``LEVEL:n`` to a subprocess's stderr and parsing it back (G-10).
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .devices import Device, resolve
from .resample import Resampler
from .ring import RingBuffer

log = get_logger(__name__)

#: Log-spaced band edges as a fraction of Nyquist, for the spectrum display.
_BAND_EDGES = np.array([0.0, 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.0])


@dataclass(frozen=True)
class LevelFrame:
    """One meter update. Drives the VU bar, waveform, and spectrum alike."""

    peak: float
    rms: float
    clipping: bool
    bands: tuple[float, ...]

    def as_tuple(self):
        return self.peak, self.rms, self.clipping, list(self.bands)


LevelCallback = Callable[[LevelFrame], None]
AudioCallback = Callable[[np.ndarray], None]


class Capture:
    """Owns the PortAudio stream, the ring buffer, and the level meter."""

    def __init__(
        self,
        sample_rate: int = 16000,
        preroll_ms: int = 300,
        block_ms: int = 20,
        level_hz: int = 50,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.block_size = max(1, int(self.sample_rate * block_ms / 1000))
        # The ring holds the pre-roll plus a safety margin, so a late reader
        # never races the writer for the audio it is about to claim.
        self.ring = RingBuffer(max(self.sample_rate, int(self.sample_rate * (preroll_ms + 700) / 1000)))
        self.preroll_samples = int(self.sample_rate * preroll_ms / 1000)

        self._stream = None
        self._device: Device | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._level_callback: LevelCallback | None = None
        self._audio_callback: AudioCallback | None = None
        self._lost_callback: Callable[[str], None] | None = None
        self._level_period = 1.0 / max(1, level_hz)
        self._last_level_at = 0.0
        self._running = threading.Event()
        self._error_reported = False
        #: The rate the device actually gave us, which is often not the rate
        #: Whisper wants. Anything above the pipeline feeds through a resampler.
        self.device_rate = self.sample_rate
        self._resampler: Resampler | None = None

    # -- properties ------------------------------------------------------

    @property
    def device(self) -> Device | None:
        return self._device

    @property
    def running(self) -> bool:
        return self._running.is_set()

    # -- lifecycle -------------------------------------------------------

    async def start(
        self,
        device_query: str | None = None,
        on_level: LevelCallback | None = None,
        on_audio: AudioCallback | None = None,
        on_lost: Callable[[str], None] | None = None,
    ) -> Device:
        """Open the stream. Idempotent for the same device."""
        self._loop = asyncio.get_running_loop()
        self._level_callback = on_level
        self._audio_callback = on_audio
        self._lost_callback = on_lost

        device = resolve(device_query)
        if self._stream is not None and self._device and device and self._device.name == device.name:
            return self._device

        await self.stop()
        await asyncio.get_running_loop().run_in_executor(None, self._open, device)
        return self._device

    def _open(self, device: Device | None) -> None:
        import os

        import sounddevice as sd

        self._error_reported = False
        self._resampler = None
        # A device reached through an aggregate has no PortAudio index of its
        # own, so the stream would silently open the default source instead.
        # The PulseAudio client library picks the source from the environment.
        previous_source = os.environ.get("PULSE_SOURCE")
        if device is not None and device.needs_routing:
            os.environ["PULSE_SOURCE"] = device.server_source
            log.debug("routing capture by name", source=device.server_source)
        elif previous_source is not None:
            del os.environ["PULSE_SOURCE"]
        # Whisper wants 16 kHz, but plenty of microphones offer only 44.1 or
        # 48 kHz and refuse anything else. Ask for what we want, then take what
        # the device has and resample rather than failing.
        candidates = [self.sample_rate]
        if device is not None and int(device.sample_rate) not in candidates:
            candidates.append(int(device.sample_rate))
        for rate in (48000, 44100, 32000, 16000):
            if rate not in candidates:
                candidates.append(rate)

        last_error: Exception | None = None
        opened_rate = None
        try:
            for rate in candidates:
                try:
                    self._stream = sd.InputStream(
                        samplerate=rate,
                        blocksize=max(1, int(rate * self.block_size / self.sample_rate)),
                        device=device.index if device else None,
                        channels=1,
                        dtype="float32",
                        callback=self._on_block,
                        finished_callback=self._on_finished,
                    )
                    self._stream.start()
                    opened_rate = rate
                    break
                except Exception as exc:
                    last_error = exc
                    self._stream = None

            if opened_rate is None:
                raise Fault(
                    code=FaultCode.STREAM_FAILED,
                    message=(
                        f"could not open {device.description if device else 'the default device'} "
                        f"at any of {', '.join(str(r) for r in candidates)} Hz: {last_error}"
                    ),
                    remedy=(
                        "Check the microphone is not held exclusively by another "
                        "application, then run: dictator devices"
                    ),
                ) from last_error
        finally:
            if previous_source is None:
                os.environ.pop("PULSE_SOURCE", None)
            else:
                os.environ["PULSE_SOURCE"] = previous_source

        self.device_rate = opened_rate
        if opened_rate != self.sample_rate:
            self._resampler = Resampler(opened_rate, self.sample_rate)
            log.info(
                "capturing at the device rate and resampling",
                device_rate=opened_rate,
                pipeline_rate=self.sample_rate,
            )
        self._device = device
        self.ring.clear()
        self._running.set()
        log.info(
            "capture started",
            device=device.name if device else "default",
            rate=self.sample_rate,
            block=self.block_size,
        )

    async def stop(self) -> None:
        self._running.clear()
        stream, self._stream = self._stream, None
        if stream is None:
            return

        def _close():
            try:
                stream.stop()
                stream.close()
            except Exception as exc:  # pragma: no cover - driver dependent
                log.debug("closing the audio stream failed", error=str(exc))

        await asyncio.get_running_loop().run_in_executor(None, _close)
        log.info("capture stopped")

    # -- the audio thread ------------------------------------------------

    def _on_block(self, indata, frames, time_info, status) -> None:
        """PortAudio callback. Must not block and must not raise."""
        try:
            if status:
                # Overflows are informational; a device error is not.
                if getattr(status, "input_overflow", False):
                    log.debug("input overflow")
                elif not self._error_reported:
                    self._error_reported = True
                    log.warning("audio stream status", status=str(status))

            mono = np.asarray(indata[:, 0], dtype=np.float32)
            if self._resampler is not None:
                mono = self._resampler.process(mono)
                if mono.size == 0:
                    return
            self.ring.write(mono)

            if self._audio_callback is not None and self._loop is not None:
                block = mono.copy()
                self._loop.call_soon_threadsafe(self._safe_audio, block)

            now = time.monotonic()
            if now - self._last_level_at >= self._level_period:
                self._last_level_at = now
                self._emit_level(mono)
        except Exception as exc:  # pragma: no cover - never kill the stream
            log.error("audio callback failed", error=str(exc))

    def _safe_audio(self, block: np.ndarray) -> None:
        try:
            if self._audio_callback is not None:
                self._audio_callback(block)
        except Exception as exc:
            log.error("audio consumer failed", error=str(exc))

    def _emit_level(self, mono: np.ndarray) -> None:
        if self._level_callback is None or self._loop is None:
            return
        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(mono, dtype=np.float64)))) if mono.size else 0.0
        frame = LevelFrame(
            peak=peak,
            rms=rms,
            clipping=peak >= 0.99,
            bands=self._bands(mono),
        )
        self._loop.call_soon_threadsafe(self._safe_level, frame)

    def _safe_level(self, frame: LevelFrame) -> None:
        try:
            if self._level_callback is not None:
                self._level_callback(frame)
        except Exception as exc:
            log.error("level consumer failed", error=str(exc))

    def _bands(self, mono: np.ndarray) -> tuple[float, ...]:
        """Eight log-spaced magnitude bands, normalised to 0..1."""
        if mono.size < 32:
            return (0.0,) * 8
        windowed = mono * np.hanning(mono.size).astype(np.float32)
        spectrum = np.abs(np.fft.rfft(windowed))
        if spectrum.size == 0:
            return (0.0,) * 8
        edges = (_BAND_EDGES * (spectrum.size - 1)).astype(int)
        out = []
        for low, high in zip(edges[:-1], edges[1:]):
            high = max(high, low + 1)
            magnitude = float(np.mean(spectrum[low:high]))
            # Compress to something a meter can render without a log scale.
            out.append(min(1.0, magnitude / (mono.size * 0.05)))
        return tuple(out)

    def _on_finished(self) -> None:
        """PortAudio ends the stream when a device disappears."""
        if not self._running.is_set():
            return
        self._running.clear()
        log.warning("the audio stream ended unexpectedly; the device may be gone")
        if self._lost_callback is not None and self._loop is not None:
            name = self._device.name if self._device else "the input device"
            self._loop.call_soon_threadsafe(self._lost_callback, name)

    # -- reading ---------------------------------------------------------

    def take_preroll(self) -> np.ndarray:
        """The audio captured just before the chord registered."""
        return self.ring.read_last(self.preroll_samples)
