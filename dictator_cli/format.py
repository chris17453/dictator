"""Terminal formatting helpers.

Colour only when the stream is a terminal, so piped output stays parseable.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Iterable, Sequence

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _wrap(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(text: str) -> str:
    return _wrap("1", text)


def dim(text: str) -> str:
    return _wrap("2", text)


def green(text: str) -> str:
    return _wrap("32", text)


def yellow(text: str) -> str:
    return _wrap("33", text)


def red(text: str) -> str:
    return _wrap("31", text)


def cyan(text: str) -> str:
    return _wrap("36", text)


OK = green("✓")
WARN = yellow("!")
BAD = red("✗")


def status_mark(ok: bool, warn: bool = False) -> str:
    if warn:
        return WARN
    return OK if ok else BAD


def table(rows: Sequence[Sequence[str]], headers: Sequence[str] = ()) -> str:
    """A plain aligned table. No borders; they add nothing in a terminal."""
    data = [list(map(str, row)) for row in rows]
    if not data and not headers:
        return ""
    columns = len(headers) if headers else max(len(r) for r in data)
    widths = [0] * columns
    if headers:
        for i, head in enumerate(headers):
            widths[i] = len(str(head))
    for row in data:
        for i, cell in enumerate(row[:columns]):
            widths[i] = max(widths[i], len(_visible(cell)))

    lines = []
    if headers:
        lines.append(
            dim("  ".join(str(h).upper().ljust(widths[i]) for i, h in enumerate(headers)))
        )
    for row in data:
        cells = []
        for i in range(columns):
            cell = row[i] if i < len(row) else ""
            pad = widths[i] - len(_visible(cell))
            cells.append(cell + " " * max(0, pad))
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)


def _visible(text: str) -> str:
    """Length as rendered, ignoring ANSI escapes."""
    import re

    return re.sub(r"\033\[[0-9;]*m", "", str(text))


def kv(pairs: Iterable[tuple[str, str]], indent: str = "  ") -> str:
    pairs = list(pairs)
    if not pairs:
        return ""
    width = max(len(k) for k, _ in pairs)
    return "\n".join(f"{indent}{dim(k.ljust(width))}  {v}" for k, v in pairs)


def duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def ago(timestamp: float) -> str:
    return duration(max(0.0, time.time() - timestamp)) + " ago"


def size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


_BLOCKS = " ▁▂▃▄▅▆▇█"


def meter_bar(level: float, width: int = 30) -> str:
    """A horizontal VU bar, green through amber to red."""
    level = max(0.0, min(1.0, level))
    filled = int(level * width)
    bar = ""
    for i in range(width):
        if i >= filled:
            bar += dim("·")
        elif i > width * 0.85:
            bar += red("█")
        elif i > width * 0.6:
            bar += yellow("█")
        else:
            bar += green("█")
    return bar


def spectrum(bands: Sequence[float]) -> str:
    """Bands rendered as block characters, one per band."""
    out = ""
    for band in bands:
        index = int(max(0.0, min(1.0, band)) * (len(_BLOCKS) - 1))
        out += _BLOCKS[index]
    return out


def fault(code: str, message: str, remedy: str) -> str:
    lines = [f"{BAD} {message}", dim(f"  code: {code}")]
    if remedy:
        lines.append(f"  {cyan('remedy:')} {remedy}")
    return "\n".join(lines)
