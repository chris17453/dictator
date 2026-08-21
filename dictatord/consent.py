"""Remembering what the user already answered.

Both portal permissions — binding a global shortcut, and typing into other
windows — are granted through a dialog. Asking is correct once. Asking on every
start is not: a daemon that restarts, or a user who is not ready to answer,
turns into a stream of popups they must dismiss.

So a decline, or an unanswered prompt, is recorded and *not* repeated. The
daemon runs in its degraded-but-useful state and says how to ask again. Only an
explicit `dictator grant` re-opens the question.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .logging import get_logger

log = get_logger(__name__)


class Decision(str, Enum):
    #: Never asked.
    UNASKED = "unasked"
    #: Asked and granted.
    GRANTED = "granted"
    #: Asked and refused.
    DECLINED = "declined"
    #: Asked, and the dialog was never answered.
    IGNORED = "ignored"
    #: Could not ask — the portal or backend was unavailable.
    UNAVAILABLE = "unavailable"

    @property
    def should_ask_again(self) -> bool:
        """Only ask when we have never had an answer, or could not ask at all."""
        return self in (Decision.UNASKED, Decision.UNAVAILABLE)


@dataclass
class Record:
    decision: Decision = Decision.UNASKED
    at: float = 0.0
    attempts: int = 0
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "at": self.at,
            "attempts": self.attempts,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        try:
            decision = Decision(data.get("decision", "unasked"))
        except ValueError:
            decision = Decision.UNASKED
        return cls(
            decision=decision,
            at=float(data.get("at", 0.0)),
            attempts=int(data.get("attempts", 0)),
            detail=str(data.get("detail", "")),
        )


@dataclass
class ConsentLedger:
    """What the user has said about each permission, persisted."""

    path: Path
    records: dict[str, Record] = field(default_factory=dict)

    #: Permissions we track. Keys are stable; do not rename them.
    KEYS = ("shortcuts", "injection")

    def load(self) -> "ConsentLedger":
        if not self.path.is_file():
            return self
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            log.debug("consent ledger unreadable; treating every permission as unasked")
            return self
        for key, raw in (data.get("permissions") or {}).items():
            if isinstance(raw, dict):
                self.records[key] = Record.from_dict(raw)
        return self

    def save(self) -> None:
        payload = {
            "version": 1,
            "permissions": {k: r.as_dict() for k, r in self.records.items()},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            tmp.replace(self.path)
            self.path.chmod(0o600)
        except OSError as exc:  # pragma: no cover - disk dependent
            log.warning("could not save the consent ledger", error=str(exc))

    # -- queries ---------------------------------------------------------

    def get(self, key: str) -> Record:
        return self.records.get(key, Record())

    def should_ask(self, key: str) -> bool:
        return self.get(key).decision.should_ask_again

    def why_not_asking(self, key: str) -> str:
        record = self.get(key)
        if record.decision is Decision.DECLINED:
            return "you declined this permission"
        if record.decision is Decision.IGNORED:
            return "the prompt was not answered last time"
        if record.decision is Decision.GRANTED:
            return "already granted"
        return ""

    # -- updates ---------------------------------------------------------

    def record(self, key: str, decision: Decision, detail: str = "") -> None:
        previous = self.get(key)
        self.records[key] = Record(
            decision=decision,
            at=time.time(),
            attempts=previous.attempts + 1,
            detail=detail,
        )
        self.save()
        log.info("consent recorded", permission=key, decision=decision.value)

    def reset(self, key: str | None = None) -> None:
        """Re-open the question, for `dictator grant`."""
        if key is None:
            self.records.clear()
        else:
            self.records.pop(key, None)
        self.save()

    def summary(self) -> dict[str, str]:
        return {key: self.get(key).decision.value for key in self.KEYS}
