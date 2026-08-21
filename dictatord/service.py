"""The D-Bus service contract.

This interface is the product's real API and the boundary every test targets.
The CLI and any UI are ordinary clients with no privileged access (v2.md §6).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import functools

from dbus_next import BusType, DBusError, Variant
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


#: The D-Bus surface is a trust boundary: any process on the session bus can
#: call it. Bounds are enforced here rather than deep in the daemon, where an
#: oversized argument would already have been copied around.
MAX_TEXT = 64 * 1024
MAX_QUERY = 1024
MAX_LIMIT = 1000
MAX_NAME = 256


ERROR_PREFIX = "com.watkinslabs.Dictator1.Error"


def translates_faults(fn):
    """Turn a Fault into a proper D-Bus error.

    Without this, dbus-next serialises the Python traceback into the reply,
    which hands every process on the session bus our file paths and internals
    for what is usually just bad input.
    """

    @functools.wraps(fn)
    async def async_wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Fault as fault:
            raise _as_dbus_error(fault) from None

    @functools.wraps(fn)
    def sync_wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Fault as fault:
            raise _as_dbus_error(fault) from None

    import inspect

    return async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper


def _as_dbus_error(fault: Fault) -> DBusError:
    # The remedy travels with the message: a client that only shows the error
    # string still tells the user what to do about it.
    text = fault.message + (f" — {fault.remedy}" if fault.remedy else "")
    suffix = "".join(part.capitalize() for part in fault.code.value.split("."))
    return DBusError(f"{ERROR_PREFIX}.{suffix}", text)


def _bounded(value: str, limit: int, what: str) -> str:
    if not isinstance(value, str):
        raise Fault(
            code=FaultCode.INTERNAL,
            message=f"{what} must be text",
            remedy="This is a client bug; report it.",
        )
    if len(value) > limit:
        raise Fault(
            code=FaultCode.INTERNAL,
            message=f"{what} is longer than the {limit} character limit",
            remedy="Shorten it.",
        )
    # Control characters have no business in a name, a query, or a chord, and
    # they corrupt terminal output when echoed back in a fault message.
    if any(ord(c) < 32 and c not in "\t\n" for c in value):
        raise Fault(
            code=FaultCode.INTERNAL,
            message=f"{what} contains control characters",
            remedy="Remove them.",
        )
    return value


def _bounded_limit(value: int) -> int:
    return max(1, min(int(value or 20), MAX_LIMIT))


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
    @translates_faults
    async def Toggle(self, options: "a{sv}") -> "u":  # noqa: F821
        return await self._daemon.toggle(_plain(options))

    @method()
    @translates_faults
    async def PushBegin(self, options: "a{sv}") -> "u":  # noqa: F821
        return await self._daemon.push_begin(_plain(options))

    @method()
    @translates_faults
    async def PushEnd(self) -> "u":  # noqa: F821
        return await self._daemon.push_end()

    @method()
    @translates_faults
    async def Cancel(self) -> "b":  # noqa: F821
        return await self._daemon.cancel()

    @method()
    @translates_faults
    async def Redeliver(self, entry_id: "u", options: "a{sv}") -> "b":  # noqa: F821
        return await self._daemon.redeliver(int(entry_id), _plain(options))

    @method()
    @translates_faults
    async def SetDevice(self, name: "s") -> "s":  # noqa: F821
        return await self._daemon.set_device(_bounded(name, MAX_NAME, "the device name"))

    @method()
    @translates_faults
    def ListDevices(self) -> "a(ssbb)":  # noqa: F821
        return self._daemon.list_devices()

    @method()
    @translates_faults
    async def SetModel(self, name: "s", options: "a{sv}") -> "a{sv}":  # noqa: F821
        return _sv(await self._daemon.set_model(
            _bounded(name, MAX_NAME, "the model name"), _plain(options)
        ))

    @method()
    @translates_faults
    def ListModels(self) -> "a(ssbbs)":  # noqa: F821
        return self._daemon.list_models()

    @method()
    @translates_faults
    def Search(self, query: "s", limit: "u") -> "s":  # noqa: F821
        return json.dumps(self._daemon.search(
            _bounded(query, MAX_QUERY, "the search query"), _bounded_limit(limit)
        ))

    @method()
    @translates_faults
    def GetState(self) -> "a{sv}":  # noqa: F821
        return _sv(self._daemon.state_snapshot())

    @method()
    @translates_faults
    def GetMetrics(self) -> "s":  # noqa: F821
        """Counters, latency percentiles, and a health verdict, as JSON."""
        snapshot = self._daemon.metrics.snapshot()
        # Overlay the daemon's own verdict so 'stats' and 'health' can never
        # disagree: the daemon knows about consent still being pending, which
        # the raw counters cannot.
        verdict = self._daemon.health()
        snapshot["health"] = verdict["status"]
        if verdict.get("problems"):
            snapshot["problems"] = verdict["problems"].split("; ")
        return json.dumps(snapshot)

    @method()
    @translates_faults
    def GetHealth(self) -> "a{sv}":  # noqa: F821
        """A blunt verdict for monitoring: healthy, degraded, or starting."""
        return _sv(self._daemon.health())

    @method()
    @translates_faults
    async def Reload(self) -> "a{sv}":  # noqa: F821
        return _sv(await self._daemon.reload())

    @method()
    @translates_faults
    async def SetShortcut(self, shortcut_id: "s", chord: "s") -> "a{sv}":  # noqa: F821
        return _sv(await self._daemon.set_shortcut(
            _bounded(shortcut_id, MAX_NAME, "the shortcut name"),
            _bounded(chord, MAX_NAME, "the chord"),
        ))

    @method()
    @translates_faults
    def ListShortcuts(self) -> "a(sss)":  # noqa: F821
        return self._daemon.list_shortcuts()

    @method()
    @translates_faults
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
