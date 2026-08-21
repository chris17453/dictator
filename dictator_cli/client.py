"""D-Bus client for the daemon.

The CLI is an ordinary client with no privileged access; everything it does
goes through the published contract (v2.md §6).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from dictatord.errors import Fault, FaultCode
from dictatord.service import BUS_NAME, INTERFACE, OBJECT_PATH

_INTROSPECTION = None


class NotRunning(Fault):
    pass


def not_running() -> Fault:
    return Fault(
        code=FaultCode.STORE_UNAVAILABLE,
        message="the dictator daemon is not running",
        remedy="Start it: dictator start   (or: systemctl --user start dictator)",
    )


def plain(value: Any) -> Any:
    if isinstance(value, Variant):
        return plain(value.value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


class Client:
    """Async client. Use via :func:`call` for one-shot commands."""

    def __init__(self) -> None:
        self.bus: MessageBus | None = None
        self.interface = None

    async def connect(self) -> "Client":
        try:
            self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        except Exception as exc:
            raise Fault(
                code=FaultCode.INTERNAL,
                message=f"cannot reach the session bus: {exc}",
                remedy="Check DBUS_SESSION_BUS_ADDRESS is set.",
            ) from exc
        try:
            introspection = await asyncio.wait_for(
                self.bus.introspect(BUS_NAME, OBJECT_PATH), timeout=5.0
            )
        except Exception as exc:
            self.bus.disconnect()
            raise not_running() from exc
        obj = self.bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
        self.interface = obj.get_interface(INTERFACE)
        return self

    async def close(self) -> None:
        if self.bus is not None:
            self.bus.disconnect()
            self.bus = None

    # -- convenience wrappers -------------------------------------------

    async def state(self) -> dict:
        return plain(await self.interface.call_get_state())

    async def toggle(self, profile: str = "") -> tuple[int, bool]:
        """Returns (session id, whether dictation is now listening)."""
        options = {"profile": Variant("s", profile)} if profile else {}
        session_id, listening = await self.interface.call_toggle(options)
        return int(session_id), bool(listening)

    async def push_begin(self, profile: str = "") -> int:
        options = {"profile": Variant("s", profile)} if profile else {}
        return await self.interface.call_push_begin(options)

    async def push_end(self) -> int:
        return await self.interface.call_push_end()

    async def cancel(self) -> bool:
        return await self.interface.call_cancel()

    async def redeliver(self, entry_id: int = 0, profile: str = "") -> bool:
        options = {"profile": Variant("s", profile)} if profile else {}
        return await self.interface.call_redeliver(entry_id, options)

    async def list_devices(self) -> list:
        return plain(await self.interface.call_list_devices())

    async def set_device(self, name: str) -> str:
        return await self.interface.call_set_device(name)

    async def list_models(self) -> list:
        return plain(await self.interface.call_list_models())

    async def set_model(self, name: str, **options) -> dict:
        variants = {k: Variant("s", str(v)) for k, v in options.items() if v}
        return plain(await self.interface.call_set_model(name, variants))

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        return json.loads(await self.interface.call_search(query, limit))

    async def list_shortcuts(self) -> list:
        return plain(await self.interface.call_list_shortcuts())

    async def set_shortcut(self, shortcut_id: str, chord: str) -> dict:
        return plain(await self.interface.call_set_shortcut(shortcut_id, chord))

    async def metrics(self) -> dict:
        import json as _json

        return _json.loads(await self.interface.call_get_metrics())

    async def health(self) -> dict:
        return plain(await self.interface.call_get_health())

    async def reload(self) -> dict:
        return plain(await self.interface.call_reload())

    async def quit(self) -> None:
        await self.interface.call_quit()

    # -- signals ---------------------------------------------------------

    def on_state_changed(self, handler) -> None:
        self.interface.on_state_changed(handler)

    def on_partial(self, handler) -> None:
        self.interface.on_partial(handler)

    def on_final(self, handler) -> None:
        self.interface.on_final(handler)

    def on_level(self, handler) -> None:
        self.interface.on_level(handler)

    def on_delivered(self, handler) -> None:
        self.interface.on_delivered(handler)

    def on_fault(self, handler) -> None:
        self.interface.on_fault_occurred(handler)


async def call(coroutine_factory):
    """Connect, run one operation, disconnect."""
    client = await Client().connect()
    try:
        return await coroutine_factory(client)
    finally:
        await client.close()


def run(coroutine_factory):
    return asyncio.run(call(coroutine_factory))


async def is_running() -> bool:
    try:
        client = await Client().connect()
    except Fault:
        return False
    await client.close()
    return True
