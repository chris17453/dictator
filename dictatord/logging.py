"""Structured logging.

Human-readable on a TTY, JSON lines when redirected or when running under
systemd. One logger tree rooted at ``dictator`` so the daemon and the CLI share
configuration without fighting over the root logger.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

ROOT = "dictator"

_RESERVED = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with arbitrary structured extras preserved."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Terse, aligned, colourised when the stream is a TTY."""

    COLORS = {
        "DEBUG": "\033[38;5;244m",
        "INFO": "\033[38;5;39m",
        "WARNING": "\033[38;5;214m",
        "ERROR": "\033[38;5;203m",
        "CRITICAL": "\033[1;38;5;203m",
    }
    RESET = "\033[0m"

    def __init__(self, color: bool = True) -> None:
        super().__init__()
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        name = record.name
        if name.startswith(ROOT + "."):
            name = name[len(ROOT) + 1 :]
        level = record.levelname[:4]
        if self.color:
            tint = self.COLORS.get(record.levelname, "")
            level = f"{tint}{level}{self.RESET}"
        line = f"{ts} {level} {name:<22} {record.getMessage()}"
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _RESERVED and not k.startswith("_")
        }
        if extras:
            line += "  " + " ".join(f"{k}={v}" for k, v in extras.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class StructuredLogger(logging.Logger):
    """A logger whose methods accept arbitrary keyword context.

    ``log.info("bound", id="dictate", trigger="Super+d")`` rather than
    ``log.info("bound", extra={"id": ...})``. The keywords survive into the
    JSON formatter as top-level fields and into the console formatter as
    ``key=value`` pairs.
    """

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False,
             stacklevel=1, **context):
        if context:
            merged = dict(extra or {})
            for key, value in context.items():
                # Never let context shadow a LogRecord attribute; that raises
                # deep inside logging and loses the message entirely.
                merged[f"ctx_{key}" if key in _RESERVED else key] = value
            extra = merged
        super()._log(level, msg, args, exc_info=exc_info, extra=extra,
                     stack_info=stack_info, stacklevel=stacklevel + 1)


logging.setLoggerClass(StructuredLogger)


def _under_systemd() -> bool:
    return bool(os.environ.get("INVOCATION_ID") or os.environ.get("JOURNAL_STREAM"))


def configure(level: str = "info", json_output: bool | None = None) -> None:
    """Install handlers on the ``dictator`` logger tree. Idempotent."""
    logger = logging.getLogger(ROOT)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    stream = sys.stderr
    if json_output is None:
        json_output = _under_systemd() or not stream.isatty()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        JsonFormatter() if json_output else ConsoleFormatter(color=stream.isatty())
    )
    logger.addHandler(handler)
    _quiet_libraries(level)


def _quiet_libraries(level: str) -> None:
    """Keep third-party chatter off the user's terminal.

    dbus-next logs to the *root* logger, and reports harmless races on
    disconnect ("add match request failed", "a message handler threw an
    exception on shutdown"). Those are not actionable and must not appear
    when someone runs `dictator config set`. Our own tree does not propagate
    to root, so raising root's level silences libraries without touching us.
    """
    verbose = level.lower() == "debug"
    root = logging.getLogger()
    if not root.handlers:
        # Give root a sink so "no handlers" warnings never surface either.
        root.addHandler(logging.NullHandler())
    root.setLevel(logging.DEBUG if verbose else logging.CRITICAL)
    for name in ("dbus_next", "dbus_next.message_bus", "asyncio"):
        logging.getLogger(name).setLevel(
            logging.DEBUG if verbose else logging.CRITICAL
        )


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the ``dictator`` tree.

    Accepts ``__name__``; the module's own package prefix is stripped so log
    lines read ``platform.registry`` rather than ``dictatord.platform.registry``.
    """
    for prefix in ("dictatord.", "dictator_cli."):
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    if name in ("__main__", "dictatord", "dictator_cli"):
        name = "main"
    return logging.getLogger(f"{ROOT}.{name}")
