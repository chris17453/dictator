"""Fault taxonomy.

Every failure surfaced to a client carries a machine-readable code and a human
remedy. A fault the daemon cannot phrase as a remedy is a defect in the daemon,
not a message for the user to decipher (v2.md G-19).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FaultCode(str, Enum):
    """Stable, machine-readable fault identifiers. Never renumber these."""

    # platform
    NO_SESSION = "platform.no_session"
    NO_SHORTCUT_BACKEND = "platform.no_shortcut_backend"
    NO_INJECTION_BACKEND = "platform.no_injection_backend"
    SHORTCUT_TAKEN = "platform.shortcut_taken"
    SHORTCUT_BIND_FAILED = "platform.shortcut_bind_failed"
    PORTAL_UNAVAILABLE = "platform.portal_unavailable"
    PORTAL_DENIED = "platform.portal_denied"
    INJECTION_FAILED = "platform.injection_failed"

    # audio
    NO_DEVICE = "audio.no_device"
    DEVICE_LOST = "audio.device_lost"
    DEVICE_BUSY = "audio.device_busy"
    STREAM_FAILED = "audio.stream_failed"

    # asr
    MODEL_NOT_FOUND = "asr.model_not_found"
    MODEL_LOAD_FAILED = "asr.model_load_failed"
    MODEL_DIGEST_MISMATCH = "asr.model_digest_mismatch"
    MODEL_DOWNLOAD_FAILED = "asr.model_download_failed"
    DECODE_FAILED = "asr.decode_failed"

    # memory
    STORE_UNAVAILABLE = "memory.store_unavailable"
    STORE_CORRUPT = "memory.store_corrupt"

    # config
    CONFIG_INVALID = "config.invalid"
    CONFIG_UNWRITABLE = "config.unwritable"

    # session
    BUSY = "session.busy"
    NOT_RECORDING = "session.not_recording"

    INTERNAL = "internal"


@dataclass(frozen=True)
class Fault(Exception):
    """A failure with a remedy attached.

    ``remedy`` is a directive addressed to the user. It must say what to do,
    not restate what went wrong.
    """

    code: FaultCode
    message: str
    remedy: str = ""
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code.value}] {self.message}"

    def as_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "remedy": self.remedy,
            "detail": {k: str(v) for k, v in self.detail.items()},
        }

    def as_signal(self) -> tuple[str, str, str]:
        """The (code, message, remedy) triple carried by the D-Bus Fault signal."""
        return self.code.value, self.message, self.remedy


def internal(message: str, **detail) -> Fault:
    """Wrap an unexpected condition without inventing a remedy for it."""
    return Fault(
        code=FaultCode.INTERNAL,
        message=message,
        remedy="Report this with the output of: dictator doctor --verbose",
        detail=detail,
    )
