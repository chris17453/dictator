"""The D-Bus service contract.

This interface is the product's real API and the boundary every test targets.
The CLI and any UI are ordinary clients with no privileged access (v2.md §6).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

from .errors import Fault, FaultCode
from .logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from .daemon import Daemon

log = get_logger(__name__)

BUS_NAME = "com.watkinslabs.Dictator1"
OBJECT_PATH = "/com/watkinslabs/Dictator1"
INTERFACE = "com.watkinslabs.Dictator1"


def _sv(mapping: dict) -> dict[str, Variant]:
    """Render a plain dict as a{sv} with everything stringified.

    Uniform typing keeps the contract stable: clients parse strings, and adding
    a field never changes a signature.
    """
    return {str(k): Variant("s", "" if v is None else str(v)) for k, v in mapping.items()}


class DictatorInterface(ServiceInterface):
    def __init__(self, daemon: "Daemon") -> None:
        super().__init__(INTERFACE)
        self._daemon = daemon

    # -- methods ---------------------------------------------------------

    @method()
    async def Toggle(self, options: "a{sv}") -> "u":  # noqa: F821
        return await self._daemon.toggle(_plain(options))

    @method()
    async def PushBegin(self, options: "a{sv}") -> "u":  # noqa: F821
        return await self._daemon.push_begin(_plain(options))

    @method()
    async def PushEnd(self) -> "u":  # noqa: F821
        return await self._daemon.push_end()

    @method()
    async def Cancel(self) -> "b":  # noqa: F821
        return await self._daemon.cancel()

    @method()
    async def Redeliver(self, entry_id: "u", options: "a{sv}") -> "b":  # noqa: F821
        return await self._daemon.redeliver(int(entry_id), _plain(options))

    @method()
    async def SetDevice(self, name: "s") -> "s":  # noqa: F821
        return await self._daemon.set_device(name)

    @method()
    def ListDevices(self) -> "a(ssbb)":  # noqa: F821
        return self._daemon.list_devices()

    @method()
    async def SetModel(self, name: "s", options: "a{sv}") -> "a{sv}":  # noqa: F821
        return _sv(await self._daemon.set_model(name, _plain(options)))

    @method()
    def ListModels(self) -> "a(ssbbs)":  # noqa: F821
        return self._daemon.list_models()

    @method()
    def Search(self, query: "s", limit: "u") -> "s":  # noqa: F821
        return json.dumps(self._daemon.search(query, int(limit)))

    @method()
    def GetState(self) -> "a{sv}":  # noqa: F821
        return _sv(self._daemon.state_snapshot())

    @method()
    async def Reload(self) -> "a{sv}":  # noqa: F821
        return _sv(await self._daemon.reload())

    @method()
    async def SetShortcut(self, shortcut_id: "s", chord: "s") -> "a{sv}":  # noqa: F821
        return _sv(await self._daemon.set_shortcut(shortcut_id, chord))

    @method()
    def ListShortcuts(self) -> "a(sss)":  # noqa: F821
        return self._daemon.list_shortcuts()

    @method()
    async def Quit(self) -> "":  # noqa: F722
        await self._daemon.request_shutdown()

    # -- signals ---------------------------------------------------------

    @signal()
    def StateChanged(self, state: "s", detail: "a{sv}") -> "sa{sv}":  # noqa: F821
        return [state, detail]

    @signal()
    def Partial(self, session_id: "u", text: "s", stable_chars: "u") -> "usu":  # noqa: F821
        return [session_id, text, stable_chars]

    @signal()
    def Final(self, session_id: "u", text: "s", confidence: "d") -> "usd":  # noqa: F821
        return [session_id, text, confidence]

    @signal()
    def Level(self, peak: "d", rms: "d", clipping: "b", bands: "ad") -> "ddbad":  # noqa: F821
        return [peak, rms, clipping, bands]

    @signal()
    def Delivered(
        self, session_id: "u", method_used: "s", app_id: "s", ok: "b"  # noqa: F821
    ) -> "ussb":  # noqa: F821
        return [session_id, method_used, app_id, ok]

    @signal()
    def FaultOccurred(self, code: "s", message: "s", remedy: "s") -> "sss":  # noqa: F821
        return [code, message, remedy]

    # -- properties ------------------------------------------------------

    @dbus_property(access=PropertyAccess.READ)
    def State(self) -> "s":  # noqa: F821
        return self._daemon.session_manager.state.value

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "s":  # noqa: F821
        from .version import __version__

        return __version__

    @dbus_property(access=PropertyAccess.READ)
    def Model(self) -> "s":  # noqa: F821
        return self._daemon.engine.model_name

    @dbus_property(access=PropertyAccess.READ)
    def Device(self) -> "s":  # noqa: F821
        device = self._daemon.capture.device
        return device.name if device else ""

    @dbus_property(access=PropertyAccess.READ)
    def ShortcutBackend(self) -> "s":  # noqa: F821
        selection = self._daemon.platform
        return selection.shortcuts.name if selection and selection.shortcuts else "none"

    @dbus_property(access=PropertyAccess.READ)
    def InjectionBackend(self) -> "s":  # noqa: F821
        selection = self._daemon.platform
        return selection.injection.name if selection and selection.injection else "none"


def _plain(options: dict) -> dict:
    out = {}
    for key, value in (options or {}).items():
        out[key] = value.value if isinstance(value, Variant) else value
    return out


async def publish(daemon: "Daemon") -> tuple[MessageBus, DictatorInterface]:
    """Claim the well-known name and export the interface."""
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    interface = DictatorInterface(daemon)
    bus.export(OBJECT_PATH, interface)

    reply = await bus.request_name(BUS_NAME)
    from dbus_next.constants import RequestNameReply

    if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
        bus.disconnect()
        raise Fault(
            code=FaultCode.BUSY,
            message=f"another process already owns {BUS_NAME}",
            remedy="A dictator daemon is already running. Use 'dictator status', or stop it with 'dictator quit'.",
        )
    log.info("service published", name=BUS_NAME, path=OBJECT_PATH)
    return bus, interface
