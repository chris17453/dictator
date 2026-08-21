"""Clipboard access, per display server.

Ownership differs in a way worth knowing: on X11 a selection is held by a live
client, so the daemon must stay running to serve paste requests. Both
implementations therefore hold the text themselves rather than handing it off
and hoping (v2.md §5.3).
"""
from __future__ import annotations

import abc
import asyncio
import shutil
import threading
from typing import Any

from ..logging import get_logger

log = get_logger(__name__)


class Clipboard(abc.ABC):
    name = "abstract"

    @classmethod
    @abc.abstractmethod
    def available(cls) -> tuple[bool, str]:
        """(usable, reason-if-not)."""

    @abc.abstractmethod
    async def set_text(self, text: str) -> None: ...

    @abc.abstractmethod
    async def get_text(self) -> str | None: ...

    async def stop(self) -> None:
        return None


class WlClipboard(Clipboard):
    """Wayland, via wl-clipboard.

    ``wl-copy`` forks a helper that owns the selection until it is replaced,
    which is exactly the semantics we want and avoids holding a Wayland
    connection open ourselves.
    """

    name = "wl-clipboard"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        if shutil.which("wl-copy") is None:
            return False, "wl-copy not found (install wl-clipboard)"
        return True, ""

    async def set_text(self, text: str) -> None:
        process = await asyncio.create_subprocess_exec(
            "wl-copy",
            "--type",
            "text/plain;charset=utf-8",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate(text.encode("utf-8"))
        if process.returncode != 0:
            raise RuntimeError(
                f"wl-copy failed ({process.returncode}): {stderr.decode(errors='replace').strip()}"
            )

    async def get_text(self) -> str | None:
        if shutil.which("wl-paste") is None:
            return None
        process = await asyncio.create_subprocess_exec(
            "wl-paste",
            "--no-newline",
            "--type",
            "text/plain",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            # An empty clipboard is an error exit for wl-paste, not a failure.
            return None
        return stdout.decode("utf-8", errors="replace")


class X11Clipboard(Clipboard):
    """X11, owning CLIPBOARD and PRIMARY natively.

    Implemented against Xlib rather than shelling out to xclip so the daemon
    has no runtime dependency the packaging cannot guarantee. A dedicated
    thread serves SelectionRequest events for as long as we own the selection.
    """

    name = "x11-selection"

    def __init__(self) -> None:
        self._display = None
        self._window = None
        self._text: bytes = b""
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._atoms: dict[str, int] = {}
        self._lock = threading.Lock()

    @classmethod
    def available(cls) -> tuple[bool, str]:
        try:
            from Xlib import display

            conn = display.Display()
            conn.close()
            return True, ""
        except Exception as exc:
            return False, f"cannot open the X display: {exc}"

    def _ensure(self) -> None:
        if self._display is not None:
            return
        from Xlib import X, display

        self._display = display.Display()
        screen = self._display.screen()
        self._window = screen.root.create_window(
            0, 0, 1, 1, 0, screen.root_depth, X.InputOutput, X.CopyFromParent
        )
        for name in (
            "CLIPBOARD",
            "PRIMARY",
            "TARGETS",
            "UTF8_STRING",
            "TEXT",
            "STRING",
            "text/plain;charset=utf-8",
            "text/plain",
        ):
            self._atoms[name] = self._display.get_atom(name)
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._serve, name="x11-clipboard", daemon=True
        )
        self._thread.start()

    async def set_text(self, text: str) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._set_text_sync, text)

    def _set_text_sync(self, text: str) -> None:
        from Xlib import X

        self._ensure()
        with self._lock:
            self._text = text.encode("utf-8")
        for selection in ("CLIPBOARD", "PRIMARY"):
            self._window.set_selection_owner(self._atoms[selection], X.CurrentTime)
        self._display.flush()

    async def get_text(self) -> str | None:
        return await asyncio.get_running_loop().run_in_executor(None, self._get_text_sync)

    def _get_text_sync(self) -> str | None:
        from Xlib import X

        self._ensure()
        clipboard = self._atoms["CLIPBOARD"]
        owner = self._display.get_selection_owner(clipboard)
        if owner == X.NONE:
            return None
        if owner.id == self._window.id:
            with self._lock:
                return self._text.decode("utf-8", errors="replace")

        target_property = self._display.get_atom("DICTATOR_PASTE")
        self._window.convert_selection(
            clipboard, self._atoms["UTF8_STRING"], target_property, X.CurrentTime
        )
        self._display.flush()

        import time

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if not self._display.pending_events():
                time.sleep(0.01)
                continue
            event = self._display.next_event()
            if getattr(event, "type", None) != X.SelectionNotify:
                continue
            if event.property == X.NONE:
                return None
            reply = self._window.get_full_property(target_property, X.AnyPropertyType)
            if reply is None:
                return None
            value = reply.value
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value)
        return None

    def _serve(self) -> None:
        """Answer SelectionRequest while we own the selection."""
        from Xlib import X
        from Xlib.protocol import event as xevent

        import select as _select
        import time

        while not self._stopping.is_set():
            try:
                if not self._display.pending_events():
                    ready, _, _ = _select.select([self._display.fileno()], [], [], 0.2)
                    if not ready:
                        continue
                event = self._display.next_event()
                if getattr(event, "type", None) != X.SelectionRequest:
                    continue
                self._answer(event, X, xevent)
            except Exception as exc:  # pragma: no cover - server dependent
                if not self._stopping.is_set():
                    log.debug("x11 clipboard server error", error=str(exc))
                    time.sleep(0.05)

    def _answer(self, event, X, xevent) -> None:
        prop = event.property if event.property != X.NONE else event.target
        target = event.target
        with self._lock:
            payload = self._text

        text_targets = {
            self._atoms["UTF8_STRING"],
            self._atoms["STRING"],
            self._atoms["TEXT"],
            self._atoms["text/plain;charset=utf-8"],
            self._atoms["text/plain"],
        }

        if target == self._atoms["TARGETS"]:
            event.requestor.change_property(
                prop, self._display.get_atom("ATOM"), 32, sorted(text_targets | {self._atoms["TARGETS"]})
            )
        elif target in text_targets:
            event.requestor.change_property(prop, target, 8, payload)
        else:
            prop = X.NONE

        notify = xevent.SelectionNotify(
            time=event.time,
            requestor=event.requestor,
            selection=event.selection,
            target=event.target,
            property=prop,
        )
        event.requestor.send_event(notify, event_mask=0)
        self._display.flush()

    async def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._display is not None:
            try:
                self._display.close()
            except Exception:  # pragma: no cover
                pass
            self._display = None


class NullClipboard(Clipboard):
    """Used headlessly, so the pipeline still runs and tests stay honest."""

    name = "none"

    def __init__(self) -> None:
        self._text: str | None = None

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return True, ""

    async def set_text(self, text: str) -> None:
        self._text = text

    async def get_text(self) -> str | None:
        return self._text


def for_session(session_type: str) -> Clipboard:
    """Pick the clipboard implementation for a detected session type."""
    if session_type == "wayland":
        ok, _ = WlClipboard.available()
        if ok:
            return WlClipboard()
        log.warning("wl-clipboard missing; clipboard delivery will be unavailable")
        return NullClipboard()
    if session_type == "x11":
        ok, reason = X11Clipboard.available()
        if ok:
            return X11Clipboard()
        log.warning("x11 clipboard unavailable", reason=reason)
        return NullClipboard()
    return NullClipboard()
