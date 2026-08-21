"""Shared xdg-desktop-portal plumbing.

Portal methods do not return results directly. They return a Request object
path, and the answer arrives later as a ``Response`` signal on that path. This
module hides that dance so the backends read like ordinary async calls.
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.introspection import Node

from ..errors import Fault, FaultCode
from ..logging import get_logger
from . import portal_xml

log = get_logger(__name__)

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"

#: Portal response codes.
SUCCESS, CANCELLED, ENDED = 0, 1, 2

_TOKEN_COUNTER = 0


def unique_token(prefix: str = "dictator") -> str:
    global _TOKEN_COUNTER
    _TOKEN_COUNTER += 1
    return f"{prefix}_{os.getpid()}_{_TOKEN_COUNTER}"


def sender_token(unique_name: str) -> str:
    """The bus name fragment the portal uses when composing request paths."""
    return re.sub(r"[^A-Za-z0-9_]", "_", unique_name.lstrip(":"))


def unwrap(value: Any) -> Any:
    """Recursively strip :class:`Variant` wrappers from a portal reply."""
    if isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {k: unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [unwrap(v) for v in value]
    return value


@dataclass
class PortalResponse:
    code: int
    results: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.code == SUCCESS


class PortalConnection:
    """A session-bus connection with portal interface proxies."""

    def __init__(self) -> None:
        self.bus: MessageBus | None = None
        self._interfaces: dict[str, Any] = {}

    async def connect(self) -> None:
        if self.bus is not None:
            return
        try:
            self.bus = await MessageBus().connect()
        except Exception as exc:
            raise Fault(
                code=FaultCode.PORTAL_UNAVAILABLE,
                message=f"cannot reach the session bus: {exc}",
                remedy=(
                    "Check that DBUS_SESSION_BUS_ADDRESS is set and a session bus is "
                    "running. Inside a container, pass the bus socket through."
                ),
            ) from exc

    async def interface(self, name: str):
        """Return a proxy for ``org.freedesktop.portal.<name>``.

        Built from our own pinned XML rather than live introspection; see
        :mod:`dictatord.platform.portal_xml` for why.
        """
        await self.connect()
        full = f"org.freedesktop.portal.{name}"
        if full not in self._interfaces:
            xml = portal_xml.BY_NAME.get(name)
            if xml is None:
                raise internal_portal(f"no pinned XML for portal interface {name!r}")
            obj = self.bus.get_proxy_object(BUS_NAME, OBJECT_PATH, Node.parse(xml))
            self._interfaces[full] = obj.get_interface(full)
        return self._interfaces[full]

    async def has_interface(self, name: str) -> bool:
        """Whether the running portal actually implements the interface.

        Presence of a proxy proves nothing — the proxy is built from our XML.
        The version property is read to force a real round trip.
        """
        return await self.version(name) > 0

    async def version(self, name: str) -> int:
        try:
            iface = await self.interface(name)
            return int(await iface.get_version())
        except Exception:
            return 0

    async def call(
        self,
        interface_name: str,
        method: str,
        *args,
        options: dict[str, Variant] | None = None,
        timeout: float = 30.0,
    ) -> PortalResponse:
        """Invoke a portal method and await its Response signal.

        The handle_token is injected into ``options`` and the Response
        subscription is armed *before* the call, so a fast portal cannot answer
        before we are listening.
        """
        await self.connect()
        iface = await self.interface(interface_name)

        options = dict(options or {})
        token = unique_token()
        options["handle_token"] = Variant("s", token)

        expected = (
            f"/org/freedesktop/portal/desktop/request/"
            f"{sender_token(self.bus.unique_name)}/{token}"
        )
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        request_obj = self.bus.get_proxy_object(
            BUS_NAME, expected, Node.parse(portal_xml.REQUEST)
        )
        request_iface = request_obj.get_interface(REQUEST_IFACE)

        def on_response(code: int, results: dict) -> None:
            if not future.done():
                future.set_result(PortalResponse(int(code), unwrap(results)))

        request_iface.on_response(on_response)
        try:
            handler = getattr(iface, f"call_{_snake(method)}")
            returned = await handler(*args, options)
            if returned and returned != expected:
                log.debug(
                    "portal returned a different request path than predicted",
                    predicted=expected,
                    actual=returned,
                )
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            raise Fault(
                code=FaultCode.PORTAL_UNAVAILABLE,
                message=f"{interface_name}.{method} did not answer within {timeout:g}s",
                remedy="Check that xdg-desktop-portal is running: systemctl --user status xdg-desktop-portal",
            ) from exc
        finally:
            try:
                request_iface.off_response(on_response)
            except Exception:  # pragma: no cover - best effort detach
                pass

    async def disconnect(self) -> None:
        if self.bus is not None:
            self.bus.disconnect()
            self.bus = None
            self._interfaces.clear()


def internal_portal(message: str) -> Fault:
    return Fault(
        code=FaultCode.PORTAL_UNAVAILABLE,
        message=message,
        remedy="Report this with the output of: dictator doctor --verbose",
    )


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
