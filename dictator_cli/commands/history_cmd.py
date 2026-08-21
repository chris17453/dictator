"""``dictator history`` and ``dictator search`` — transcript memory."""
from __future__ import annotations

import argparse
import asyncio
import json

from dictatord import config as cfg
from dictatord.errors import Fault
from dictatord.memory.store import TranscriptStore

from .. import format as fmt
from ..client import is_running
from ..client import run as client_run


def _entries(query: str, limit: int) -> list[dict]:
    """Prefer the daemon; fall back to reading the store directly.

    Reading the file works because SQLite in WAL mode supports concurrent
    readers, so 'dictator history' is useful even when the daemon is down.
    """
    try:
        if asyncio.run(is_running()):
            return client_run(lambda c: c.search(query, limit))
    except Fault:
        pass
    store = TranscriptStore(cfg.data_dir() / "transcripts.db")
    store.open()
    try:
        found = store.search(query, limit) if query else store.recent(limit)
        return [e.as_dict() for e in found]
    finally:
        store.close()


def _render(entries: list[dict], as_json: bool, full: bool) -> int:
    if as_json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("nothing stored yet")
        return 0

    rows = []
    for entry in entries:
        text = entry["text"]
        if not full and len(text) > 68:
            text = text[:65] + "…"
        confidence = entry.get("confidence", 0.0)
        mark = fmt.green("●") if confidence >= 0.7 else (
            fmt.yellow("●") if confidence >= 0.45 else fmt.red("●")
        )
        rows.append([
            fmt.dim(str(entry["id"])),
            mark,
            fmt.dim(fmt.ago(entry["created_at"])),
            text,
        ])
    print(fmt.table(rows, headers=("id", "", "when", "transcript")))
    print()
    print(fmt.dim("  deliver one again:  dictator again <id>"))
    return 0


def history(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator history", description="Recent transcripts."
    )
    parser.add_argument("-n", "--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--full", action="store_true", help="Do not truncate long text.")
    args = parser.parse_args(argv)
    return _render(_entries("", args.limit), args.json, args.full)


def search(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator search", description="Find a past transcript."
    )
    parser.add_argument("query", nargs="+")
    parser.add_argument("-n", "--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    return _render(_entries(" ".join(args.query), args.limit), args.json, args.full)
