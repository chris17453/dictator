"""Durable transcript memory: SQLite in WAL mode with an FTS5 index.

Replaces an in-memory list serialised opportunistically into a JSON file at the
repository root (G-20). Schema migrations start at version one, because the
first migration is always the one nobody planned for.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..errors import Fault, FaultCode
from ..logging import get_logger

log = get_logger(__name__)

SCHEMA_VERSION = 1


@dataclass
class Entry:
    id: int
    text: str
    created_at: float
    duration_s: float = 0.0
    confidence: float = 0.0
    model: str = ""
    language: str = ""
    app_id: str = ""
    delivery: str = ""
    delivered: bool = False
    redacted: bool = False
    audio_path: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "created_at": self.created_at,
            "duration_s": self.duration_s,
            "confidence": self.confidence,
            "model": self.model,
            "language": self.language,
            "app_id": self.app_id,
            "delivery": self.delivery,
            "delivered": self.delivered,
            "redacted": self.redacted,
        }


def _row_to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        text=row["text"],
        created_at=row["created_at"],
        duration_s=row["duration_s"],
        confidence=row["confidence"],
        model=row["model"],
        language=row["language"],
        app_id=row["app_id"],
        delivery=row["delivery"],
        delivered=bool(row["delivered"]),
        redacted=bool(row["redacted"]),
        audio_path=row["audio_path"] or "",
    )


class TranscriptStore:
    """Every utterance, searchable, with a retention policy that deletes."""

    def __init__(self, path: Path, redact_patterns: Iterable[str] = ()) -> None:
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None
        self._fts = False
        self.redact_patterns = [re.compile(p) for p in redact_patterns if p]

    # -- lifecycle -------------------------------------------------------

    def open(self) -> None:
        if self._connection is not None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                str(self.path), check_same_thread=False, isolation_level=None
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as exc:
            raise Fault(
                code=FaultCode.STORE_UNAVAILABLE,
                message=f"could not open the transcript store at {self.path}: {exc}",
                remedy=f"Check permissions on {self.path.parent}, or set memory.enabled = false.",
            ) from exc

        self._connection = connection
        self._migrate()
        try:
            self.path.chmod(0o600)
        except OSError:  # pragma: no cover - filesystem dependent
            pass

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _migrate(self) -> None:
        connection = self._require()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            self._fts = self._has_fts()
            return

        if version == 0:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS transcripts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    text        TEXT    NOT NULL,
                    created_at  REAL    NOT NULL,
                    duration_s  REAL    NOT NULL DEFAULT 0,
                    confidence  REAL    NOT NULL DEFAULT 0,
                    model       TEXT    NOT NULL DEFAULT '',
                    language    TEXT    NOT NULL DEFAULT '',
                    app_id      TEXT    NOT NULL DEFAULT '',
                    delivery    TEXT    NOT NULL DEFAULT '',
                    delivered   INTEGER NOT NULL DEFAULT 0,
                    redacted    INTEGER NOT NULL DEFAULT 0,
                    audio_path  TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_transcripts_created
                    ON transcripts(created_at DESC);
                """
            )
            self._create_fts()
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            log.info("transcript store initialised", path=str(self.path))

    def _create_fts(self) -> None:
        connection = self._require()
        try:
            connection.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts
                    USING fts5(text, content='transcripts', content_rowid='id');
                CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
                    INSERT INTO transcripts_fts(rowid, text) VALUES (new.id, new.text);
                END;
                CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
                    INSERT INTO transcripts_fts(transcripts_fts, rowid, text)
                        VALUES ('delete', old.id, old.text);
                END;
                CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
                    INSERT INTO transcripts_fts(transcripts_fts, rowid, text)
                        VALUES ('delete', old.id, old.text);
                    INSERT INTO transcripts_fts(rowid, text) VALUES (new.id, new.text);
                END;
                """
            )
            self._fts = True
        except sqlite3.Error as exc:
            # FTS5 is compiled in almost everywhere, but not universally.
            # Search degrades to LIKE rather than the store failing.
            self._fts = False
            log.warning("FTS5 unavailable; search will use a slower scan",
                        error=str(exc))

    def _has_fts(self) -> bool:
        connection = self._require()
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts_fts'"
        ).fetchone()
        return row is not None

    def _require(self) -> sqlite3.Connection:
        if self._connection is None:
            raise Fault(
                code=FaultCode.STORE_UNAVAILABLE,
                message="the transcript store is not open",
                remedy="Report this with the output of: dictator doctor --verbose",
            )
        return self._connection

    # -- redaction -------------------------------------------------------

    def redact(self, text: str) -> tuple[str, bool]:
        """Apply redaction rules. The delivered text is never altered."""
        redacted = text
        changed = False
        for pattern in self.redact_patterns:
            redacted, count = pattern.subn("[redacted]", redacted)
            changed = changed or count > 0
        return redacted, changed

    # -- writing ---------------------------------------------------------

    def add(
        self,
        text: str,
        *,
        duration_s: float = 0.0,
        confidence: float = 0.0,
        model: str = "",
        language: str = "",
        app_id: str = "",
        delivery: str = "",
        delivered: bool = False,
        audio_path: str = "",
        created_at: float | None = None,
    ) -> Entry:
        connection = self._require()
        stored, was_redacted = self.redact(text)
        created = created_at if created_at is not None else time.time()
        cursor = connection.execute(
            """
            INSERT INTO transcripts
                (text, created_at, duration_s, confidence, model, language,
                 app_id, delivery, delivered, redacted, audio_path)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                stored,
                created,
                duration_s,
                confidence,
                model,
                language,
                app_id,
                delivery,
                int(delivered),
                int(was_redacted),
                audio_path or None,
            ),
        )
        return Entry(
            id=cursor.lastrowid,
            text=stored,
            created_at=created,
            duration_s=duration_s,
            confidence=confidence,
            model=model,
            language=language,
            app_id=app_id,
            delivery=delivery,
            delivered=delivered,
            redacted=was_redacted,
            audio_path=audio_path,
        )

    def mark_delivered(self, entry_id: int, method: str, app_id: str, ok: bool) -> None:
        self._require().execute(
            "UPDATE transcripts SET delivered=?, delivery=?, app_id=? WHERE id=?",
            (int(ok), method, app_id, entry_id),
        )

    # -- reading ---------------------------------------------------------

    def get(self, entry_id: int) -> Entry | None:
        row = self._require().execute(
            "SELECT * FROM transcripts WHERE id=?", (entry_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def recent(self, limit: int = 20) -> list[Entry]:
        rows = self._require().execute(
            "SELECT * FROM transcripts ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def last(self) -> Entry | None:
        entries = self.recent(1)
        return entries[0] if entries else None

    def search(self, query: str, limit: int = 20) -> list[Entry]:
        connection = self._require()
        query = query.strip()
        if not query:
            return self.recent(limit)

        if self._fts:
            try:
                rows = connection.execute(
                    """
                    SELECT t.* FROM transcripts_fts f
                    JOIN transcripts t ON t.id = f.rowid
                    WHERE transcripts_fts MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (self._fts_query(query), int(limit)),
                ).fetchall()
                return [_row_to_entry(r) for r in rows]
            except sqlite3.Error as exc:
                log.debug("FTS query failed; falling back to scan", error=str(exc))

        rows = connection.execute(
            "SELECT * FROM transcripts WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{query}%", int(limit)),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    @staticmethod
    def _fts_query(query: str) -> str:
        """Quote user input so punctuation cannot become FTS syntax."""
        terms = re.findall(r"\w+", query)
        if not terms:
            return '""'
        return " ".join(f'"{t}"' for t in terms)

    def count(self) -> int:
        return int(self._require().execute("SELECT COUNT(*) FROM transcripts").fetchone()[0])

    def size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            if candidate.is_file():
                total += candidate.stat().st_size
        return total

    # -- retention -------------------------------------------------------

    def prune(self, older_than_days: int) -> int:
        """Delete transcripts past the retention horizon. 0 means keep all."""
        if not older_than_days:
            return 0
        cutoff = time.time() - older_than_days * 86400
        connection = self._require()
        audio = connection.execute(
            "SELECT audio_path FROM transcripts WHERE created_at < ? AND audio_path IS NOT NULL",
            (cutoff,),
        ).fetchall()
        cursor = connection.execute("DELETE FROM transcripts WHERE created_at < ?", (cutoff,))
        for row in audio:
            try:
                Path(row["audio_path"]).unlink(missing_ok=True)
            except OSError:  # pragma: no cover
                pass
        removed = cursor.rowcount or 0
        if removed:
            connection.execute("VACUUM")
            log.info("pruned old transcripts", removed=removed, older_than_days=older_than_days)
        return removed

    def clear(self) -> int:
        connection = self._require()
        count = self.count()
        connection.execute("DELETE FROM transcripts")
        connection.execute("VACUUM")
        return count

    def export(self) -> list[dict]:
        return [entry.as_dict() for entry in self.recent(limit=1_000_000)]
