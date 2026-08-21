"""Input injection on Wayland via the RemoteDesktop portal.

The session is created with ``persist_mode=2`` and a restore token saved to
disk, so consent is granted once and survives a restart. If the token is
rejected the user is prompted again rather than the daemon failing (v2.md K-1).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dbus_next import Variant
from dbus_next.introspection import Node

from ..errors import Fault, FaultCode
from ..logging import get_logger
from . import portal_xml
from .base import Capability, InjectionBackend
from .chords import Chord
from .clipboard import Clipboard, NullClipboard
from .keysyms import MODIFIER_KEYSYMS, char_to_keysym, key_to_keysym
from .portal import BUS_NAME, PortalConnection, unique_token

log = get_logger(__name__)

DEVICE_KEYBOARD = 1
PERSIST_PERSISTENT = 2

RELEASED, PRESSED = 0, 1


class PortalInjection(InjectionBackend):
    name = "portal"

    def __init__(
        self,
        clipboard: Clipboard | None = None,
        token_path: Path | None = None,
        connection: PortalConnection | None = None,
        key_delay_ms: float = 2.0,
    ) -> None:
        self._portal = connection or PortalConnection()
        self._owns_connection = connection is None
        self._clipboard = clipboard or NullClipboard()
        self._token_path = token_path
        self._session: str | None = None
        self._iface = None
        self._key_delay = key_delay_ms / 1000.0

    # -- probe -----------------------------------------------------------

    @classmethod
    async def probe(cls) -> Capability:
        portal = PortalConnection()
        try:
            version = await portal.version("RemoteDesktop")
            if version <= 0:
                return Capability(
                    name=cls.name,
                    available=False,
                    reason="portal does not implement org.freedesktop.portal.RemoteDesktop",
                )
            return Capability(
                name=cls.name,
                available=True,
                supports_focus_query=False,
                requires_consent=True,
                trust="portal-mediated; consent is granted once and revocable by the user",
                detail=f"RemoteDesktop v{version}",
                rank=100,
            )
        except Fault as fault:
            return Capability(name=cls.name, available=False, reason=fault.message)
        finally:
            await portal.disconnect()

    # -- restore token ---------------------------------------------------

    def _read_token(self) -> str | None:
        if self._token_path is None or not self._token_path.is_file():
            return None
        try:
            return json.loads(self._token_path.read_text()).get("restore_token") or None
        except (OSError, ValueError):
            return None

    def _write_token(self, token: str | None) -> None:
        if self._token_path is None or not token:
            return
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(json.dumps({"restore_token": token}))
            self._token_path.chmod(0o600)
        except OSError as exc:  # pragma: no cover - disk dependent
            log.warning("could not save the portal restore token", error=str(exc))

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if self._session is not None:
            return
        self._iface = await self._portal.interface("RemoteDesktop")

        response = await self._portal.call(
            "RemoteDesktop",
            "CreateSession",
            options={"session_handle_token": Variant("s", unique_token("rd"))},
        )
        if not response.ok:
            raise self._denied(response.code, "create a remote-desktop session")
        session = response.results.get("session_handle")
        if not session:
            raise Fault(
                code=FaultCode.PORTAL_UNAVAILABLE,
                message="portal created a remote-desktop session but returned no handle",
                remedy="Update xdg-desktop-portal, then run: dictator doctor",
            )

        select_options: dict[str, Variant] = {
            "types": Variant("u", DEVICE_KEYBOARD),
            "persist_mode": Variant("u", PERSIST_PERSISTENT),
        }
        token = self._read_token()
        if token:
            select_options["restore_token"] = Variant("s", token)
            log.debug("reusing a saved portal restore token")

        response = await self._portal.call(
            "RemoteDesktop", "SelectDevices", session, options=select_options
        )
        if not response.ok:
            raise self._denied(response.code, "select the keyboard device")

        response = await self._portal.call(
            "RemoteDesktop", "Start", session, "", timeout=120.0
        )
        if not response.ok:
            if token:
                # A stale token is the likely cause; drop it and let the next
                # start prompt cleanly rather than failing forever.
                log.warning("saved restore token was rejected; discarding it")
                self._write_token("")
            raise self._denied(response.code, "start the remote-desktop session")

        new_token = response.results.get("restore_token")
        if new_token:
            self._write_token(new_token)
            log.info("portal consent persisted; restarts will not prompt again")

        self._session = session
        log.info("portal injection ready", session=session)

    def _denied(self, code: int, what: str) -> Fault:
        return Fault(
            code=FaultCode.PORTAL_DENIED,
            message=f"the desktop declined to {what} (code {code})",
            remedy=(
                "Approve the 'Remote Desktop' prompt so text can be typed into other "
                "applications. Without it, set delivery.mode = \"clipboard\" to have "
                "transcripts copied instead: dictator config set delivery.mode clipboard"
            ),
        )

    async def stop(self) -> None:
        if self._session is not None:
            try:
                obj = self._portal.bus.get_proxy_object(
                    BUS_NAME, self._session, Node.parse(portal_xml.SESSION)
                )
                await obj.get_interface("org.freedesktop.portal.Session").call_close()
            except Exception as exc:  # pragma: no cover - may already be gone
                log.debug("closing the remote-desktop session failed", error=str(exc))
            self._session = None
        await self._clipboard.stop()
        if self._owns_connection:
            await self._portal.disconnect()

    # -- clipboard -------------------------------------------------------

    async def set_clipboard(self, text: str) -> None:
        await self._clipboard.set_text(text)

    async def get_clipboard(self) -> str | None:
        return await self._clipboard.get_text()

    # -- injection -------------------------------------------------------

    def _require_session(self) -> str:
        if self._session is None:
            raise Fault(
                code=FaultCode.INJECTION_FAILED,
                message="no remote-desktop session; input cannot be synthesised",
                remedy="Run 'dictator restart' and approve the Remote Desktop prompt.",
            )
        return self._session

    async def _key(self, keysym: int, state: int) -> None:
        session = self._require_session()
        try:
            await self._iface.call_notify_keyboard_keysym(session, {}, keysym, state)
        except Exception as exc:
            raise Fault(
                code=FaultCode.INJECTION_FAILED,
                message=f"the portal refused a key event: {exc}",
                remedy="Run 'dictator restart' and approve the Remote Desktop prompt.",
            ) from exc

    async def send_chord(self, chord: Chord) -> None:
        modifiers = [MODIFIER_KEYSYMS[m] for m in chord.modifiers if m in MODIFIER_KEYSYMS]
        key = key_to_keysym(chord.key)
        for keysym in modifiers:
            await self._key(keysym, PRESSED)
        await self._key(key, PRESSED)
        await asyncio.sleep(self._key_delay)
        await self._key(key, RELEASED)
        for keysym in reversed(modifiers):
            await self._key(keysym, RELEASED)

    async def type_text(self, text: str) -> None:
        for char in text:
            keysym = char_to_keysym(char)
            await self._key(keysym, PRESSED)
            await self._key(keysym, RELEASED)
            if self._key_delay:
                await asyncio.sleep(self._key_delay)

    async def focused_app_id(self) -> str | None:
        """Not obtainable on Wayland through any standard interface.

        Verified rather than assumed: ``xdotool getactivewindow`` aborts under
        XWayland and ``_NET_ACTIVE_WINDOW`` names only the XWayland stub. The
        caller falls back to the configured default profile (v2.md §5.4).
        """
        return None
