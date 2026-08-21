"""Global shortcuts through xdg-desktop-portal.

The compositor owns the grab, which is why the chord works regardless of which
application has focus — "survives focus change" is satisfied structurally
rather than defended against (v2.md §4.2).

Crucially the portal reports ``Deactivated`` as well as ``Activated``, so
hold-to-talk needs no separate mechanism.
"""
from __future__ import annotations

import asyncio
from typing import Any

from dbus_next import Variant
from dbus_next.introspection import Node

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .base import BindResult, Capability, ShortcutBackend, ShortcutCallback, ShortcutEvent
from .chords import Chord
from .appid import app_id
from .portal import BUS_NAME, PortalConnection, unique_token
from . import portal_xml

log = get_logger(__name__)


class PortalShortcuts(ShortcutBackend):
    name = "portal"

    def __init__(self, connection: PortalConnection | None = None) -> None:
        self._portal = connection or PortalConnection()
        self._owns_connection = connection is None
        self._session: str | None = None
        self._callback: ShortcutCallback | None = None
        self._bound: dict[str, Chord] = {}
        self._iface = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # -- probe -----------------------------------------------------------

    @classmethod
    async def probe(cls) -> Capability:
        portal = PortalConnection()
        try:
            version = await portal.version("GlobalShortcuts")
            if version <= 0:
                return Capability(
                    name=cls.name,
                    available=False,
                    reason="portal does not implement org.freedesktop.portal.GlobalShortcuts",
                )
            return Capability(
                name=cls.name,
                available=True,
                supports_release=True,
                requires_consent=True,
                trust="compositor-mediated; the user grants and can revoke the binding",
                detail=f"GlobalShortcuts v{version}",
                rank=100,
            )
        except Fault as fault:
            return Capability(name=cls.name, available=False, reason=fault.message)
        finally:
            await portal.disconnect()

    # -- lifecycle -------------------------------------------------------

    async def start(self, callback: ShortcutCallback) -> None:
        if self._session is not None:
            self._callback = callback
            return
        self._callback = callback
        self._loop = asyncio.get_running_loop()
        self._iface = await self._portal.interface("GlobalShortcuts")

        self._iface.on_activated(self._on_activated)
        self._iface.on_deactivated(self._on_deactivated)

        response = await self._portal.call(
            "GlobalShortcuts",
            "CreateSession",
            options={"session_handle_token": Variant("s", unique_token("session"))},
        )
        if not response.ok:
            raise Fault(
                code=FaultCode.PORTAL_DENIED,
                message=f"portal refused to create a shortcuts session (code {response.code})",
                remedy="Grant the shortcut permission when your desktop prompts, then run: dictator restart",
            )
        self._session = response.results.get("session_handle")
        if not self._session:
            raise Fault(
                code=FaultCode.PORTAL_UNAVAILABLE,
                message="portal created a shortcuts session but returned no handle",
                remedy="Update xdg-desktop-portal, then run: dictator doctor",
            )
        log.info("portal shortcuts session created", session=self._session)

    async def bind(
        self, shortcuts: dict[str, Chord], descriptions: dict[str, str]
    ) -> BindResult:
        if self._session is None:
            raise Fault(
                code=FaultCode.SHORTCUT_BIND_FAILED,
                message="bind() called before start()",
                remedy="Report this with the output of: dictator doctor --verbose",
            )

        payload: list[list[Any]] = []
        for shortcut_id, chord in shortcuts.items():
            payload.append(
                [
                    shortcut_id,
                    {
                        "description": Variant(
                            "s", descriptions.get(shortcut_id, shortcut_id)
                        ),
                        "preferred_trigger": Variant("s", chord.to_portal()),
                    },
                ]
            )

        response = await self._portal.call(
            "GlobalShortcuts", "BindShortcuts", self._session, payload, "", timeout=120.0
        )
        if not response.ok:
            raise Fault(
                code=FaultCode.PORTAL_DENIED,
                message=f"the shortcut binding was declined (code {response.code})",
                remedy=self._decline_remedy(),
                detail={"app_id": app_id() or "(none)"},
            )

        result = BindResult()
        granted = {entry[0] for entry in response.results.get("shortcuts", []) or []}
        for shortcut_id, chord in shortcuts.items():
            if not granted or shortcut_id in granted:
                result.bound[shortcut_id] = chord
            else:
                result.rejected[shortcut_id] = "the desktop did not grant this shortcut"
        self._bound = dict(result.bound)

        # What the compositor actually assigned may differ from what we asked
        # for; the user can rebind in their desktop settings and we must report
        # the truth rather than our preference.
        for entry in response.results.get("shortcuts", []) or []:
            trigger = (entry[1] or {}).get("trigger_description", "")
            if trigger:
                log.info("shortcut bound", id=entry[0], trigger=trigger)
        return result

    async def stop(self) -> None:
        if self._iface is not None:
            try:
                self._iface.off_activated(self._on_activated)
                self._iface.off_deactivated(self._on_deactivated)
            except Exception:  # pragma: no cover - best effort detach
                pass
            self._iface = None
        if self._session is not None:
            await self._close_session(self._session)
            self._session = None
        self._bound.clear()
        if self._owns_connection:
            await self._portal.disconnect()

    async def _close_session(self, handle: str) -> None:
        try:
            obj = self._portal.bus.get_proxy_object(
                BUS_NAME, handle, Node.parse(portal_xml.SESSION)
            )
            await obj.get_interface("org.freedesktop.portal.Session").call_close()
        except Exception as exc:  # pragma: no cover - session may already be gone
            log.debug("closing portal session failed", error=str(exc))

    # -- signal handling -------------------------------------------------

    def _on_activated(self, session: str, shortcut_id: str, timestamp: int, options: dict) -> None:
        self._dispatch(session, shortcut_id, ShortcutEvent.PRESSED)

    def _on_deactivated(self, session: str, shortcut_id: str, timestamp: int, options: dict) -> None:
        self._dispatch(session, shortcut_id, ShortcutEvent.RELEASED)

    def _dispatch(self, session: str, shortcut_id: str, event: ShortcutEvent) -> None:
        if session != self._session or self._callback is None:
            return
        log.debug("shortcut event", id=shortcut_id, event=event.value)
        self._callback(shortcut_id, event)

    @staticmethod
    def _decline_remedy() -> str:
        """Explain the decline, distinguishing the two very different causes."""
        if app_id():
            return (
                "Approve the shortcut when your desktop asks. If you dismissed the "
                "prompt, run: dictator restart"
            )
        return (
            "GNOME refuses shortcut requests from applications it cannot identify, "
            "and this process has no application id. Install the service properly "
            "so it runs under its own systemd unit: dictator setup --install. "
            "Until then, dictation still works via 'dictator toggle'."
        )

    def bound(self) -> dict[str, Chord]:
        return dict(self._bound)
