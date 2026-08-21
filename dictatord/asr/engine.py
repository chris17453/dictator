"""The resident transcription engine.

The model is loaded once and held, because loading weights on the first
keystroke costs seconds — one of the three reasons the daemon exists at all
(v2.md §4.1). Model changes are handled by swapping under a lock rather than
by restarting the process.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..errors import Fault, FaultCode
from ..logging import get_logger
from . import cuda, models

log = get_logger(__name__)


@dataclass
class Transcript:
    text: str
    language: str = ""
    confidence: float = 0.0
    duration_s: float = 0.0
    decode_s: float = 0.0
    segments: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def confidence_from_logprob(avg_logprob: float) -> float:
    """Map Whisper's average log-probability onto 0..1.

    Whisper reports roughly -1.0 (poor) to 0.0 (confident). Clamping and
    rescaling gives a number that is comparable across utterances, which is
    what a quality warning needs.
    """
    return float(min(1.0, max(0.0, 1.0 + avg_logprob)))


class Engine:
    """Wraps faster-whisper with load, swap, unload, and decode."""

    def __init__(
        self,
        model_root: Path,
        model: str = "auto",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
        language: str = "auto",
        verify_digest: bool = True,
    ) -> None:
        self.model_root = Path(model_root)
        self.requested_model = model
        self.requested_device = device
        self.requested_compute_type = compute_type
        self.beam_size = int(beam_size)
        self.language = language
        self.verify_digest = verify_digest

        self._model = None
        self._lock = threading.Lock()
        self.resolution: models.Resolution | None = None
        self.loaded_at: float | None = None
        self.last_used_at: float = 0.0
        self.integrity: str = "not checked"

    # -- state -----------------------------------------------------------

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self.resolution.model if self.resolution else self.requested_model

    @property
    def device(self) -> str:
        return self.resolution.device if self.resolution else self.requested_device

    def describe(self) -> dict[str, str]:
        return {
            "model": self.model_name,
            "device": self.device,
            "compute_type": (
                self.resolution.compute_type if self.resolution else self.requested_compute_type
            ),
            "loaded": str(self.loaded).lower(),
            "integrity": self.integrity,
        }

    # -- loading ---------------------------------------------------------

    async def ensure_loaded(self) -> None:
        if self._model is not None:
            return
        await asyncio.get_running_loop().run_in_executor(None, self._load)

    def _load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            resolution = models.resolve(
                self.requested_model, self.requested_device, self.requested_compute_type
            )
            spec = models.spec_for(resolution.model)
            directory = models.model_dir(self.model_root, resolution.model)

            if not models.is_downloaded(self.model_root, resolution.model):
                log.info(
                    "downloading model",
                    model=resolution.model,
                    size_mb=spec.approx_mb,
                    repo=spec.repo,
                )
                models.download(self.model_root, resolution.model)

            ok, detail = models.verify(
                self.model_root, resolution.model, enforce=self.verify_digest
            )
            self.integrity = detail
            if not ok and self.verify_digest:  # pragma: no cover - verify raises
                raise Fault(
                    code=FaultCode.MODEL_DIGEST_MISMATCH,
                    message=detail,
                    remedy=f"dictator models remove {resolution.model}",
                )

            if resolution.device == "cuda":
                # cuDNN must be resolvable before ctranslate2 looks for its
                # symbols; a missing one aborts the process mid-decode rather
                # than raising (see dictatord.asr.cuda).
                cuda.preload()
                status = cuda.verify(str(directory))
                if not status.usable:
                    log.warning(
                        "CUDA is not usable; falling back to the CPU",
                        reason=status.reason,
                        remedy=cuda.remedy(),
                    )
                    resolution = models.Resolution(
                        model=resolution.model,
                        device="cpu",
                        compute_type=models.resolve_compute_type(
                            self.requested_compute_type, "cpu"
                        ),
                        reason=f"CUDA unusable: {status.reason}",
                    )
                else:
                    log.debug("CUDA verified", reason=status.reason)

            started = time.monotonic()
            try:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    str(directory),
                    device=resolution.device,
                    compute_type=resolution.compute_type,
                )
            except Exception as exc:
                raise Fault(
                    code=FaultCode.MODEL_LOAD_FAILED,
                    message=f"could not load {resolution.model} on {resolution.device}: {exc}",
                    remedy=(
                        "Try the CPU: dictator config set model.device cpu. "
                        "If CUDA libraries are missing, install them or use a smaller model."
                    ),
                ) from exc

            self.resolution = resolution
            self.loaded_at = time.time()
            self.last_used_at = time.monotonic()
            log.info(
                "model loaded",
                model=resolution.model,
                device=resolution.device,
                compute_type=resolution.compute_type,
                seconds=round(time.monotonic() - started, 2),
                integrity=detail,
            )

    async def unload(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._unload)

    def _unload(self) -> None:
        with self._lock:
            if self._model is None:
                return
            self._model = None
            self.loaded_at = None
            log.info("model unloaded")
        import gc

        gc.collect()

    async def switch(
        self,
        model: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ) -> models.Resolution:
        """Change the model in place.

        The new model is validated before the old one is dropped, so a bad
        choice leaves a working daemon rather than an unusable one.
        """
        if model is not None and model != "auto":
            models.spec_for(model)

        previous = (self.requested_model, self.requested_device, self.requested_compute_type)
        if model is not None:
            self.requested_model = model
        if device is not None:
            self.requested_device = device
        if compute_type is not None:
            self.requested_compute_type = compute_type

        try:
            resolution = models.resolve(
                self.requested_model, self.requested_device, self.requested_compute_type
            )
        except Fault:
            (self.requested_model, self.requested_device, self.requested_compute_type) = previous
            raise

        if self.resolution == resolution and self.loaded:
            return resolution

        await self.unload()
        try:
            await self.ensure_loaded()
        except Fault:
            (self.requested_model, self.requested_device, self.requested_compute_type) = previous
            raise
        return self.resolution

    async def maybe_unload_idle(self, idle_seconds: int) -> bool:
        if not idle_seconds or not self.loaded:
            return False
        if time.monotonic() - self.last_used_at < idle_seconds:
            return False
        await self.unload()
        return True

    # -- decoding --------------------------------------------------------

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        *,
        prompt: str = "",
        partial: bool = False,
    ) -> Transcript:
        await self.ensure_loaded()
        return await asyncio.get_running_loop().run_in_executor(
            None, self._transcribe, audio, sample_rate, prompt, partial
        )

    def _transcribe(
        self, audio: np.ndarray, sample_rate: int, prompt: str, partial: bool
    ) -> Transcript:
        if audio.size == 0:
            return Transcript(text="")

        started = time.monotonic()
        self.last_used_at = started
        data = np.asarray(audio, dtype=np.float32).reshape(-1)

        try:
            segments, info = self._model.transcribe(
                data,
                language=None if self.language == "auto" else self.language,
                # Partials are speculative and re-decoded constantly; a greedy
                # pass keeps them inside the cadence budget.
                beam_size=1 if partial else self.beam_size,
                initial_prompt=prompt or None,
                vad_filter=False,
                condition_on_previous_text=False,
                without_timestamps=partial,
            )
            collected = []
            texts = []
            logprobs = []
            for segment in segments:
                texts.append(segment.text)
                logprobs.append(getattr(segment, "avg_logprob", -1.0))
                collected.append(
                    {
                        "start": float(getattr(segment, "start", 0.0)),
                        "end": float(getattr(segment, "end", 0.0)),
                        "text": segment.text,
                        "avg_logprob": float(getattr(segment, "avg_logprob", -1.0)),
                    }
                )
        except Exception as exc:
            raise Fault(
                code=FaultCode.DECODE_FAILED,
                message=f"transcription failed: {exc}",
                remedy="Run 'dictator doctor'. If this persists, try a smaller model.",
            ) from exc

        text = "".join(texts).strip()
        confidence = (
            confidence_from_logprob(sum(logprobs) / len(logprobs)) if logprobs else 0.0
        )
        return Transcript(
            text=text,
            language=getattr(info, "language", "") or "",
            confidence=confidence,
            duration_s=data.size / float(sample_rate),
            decode_s=time.monotonic() - started,
            segments=collected,
        )
