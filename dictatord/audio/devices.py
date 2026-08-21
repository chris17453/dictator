"""Input device enumeration, addressed by stable name.

Devices are identified by name, never by the positional index that shifts
whenever something is plugged in — the cause of G-14.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..errors import Fault, FaultCode
from ..logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class AudioDiagnosis:
    """Whether audio capture can actually work, and what to do if not.

    PortAudio on a PipeWire host advertises aggregate devices named "pipewire"
    and "default" whether or not a single microphone exists behind them. Taking
    their presence as proof of a working microphone reports a healthy tick over
    a session that cannot hear anything — which is exactly the silent-failure
    behaviour this rewrite exists to remove (G-08).
    """

    ok: bool
    summary: str
    remedy: str = ""
    real_sources: int = 0
    remote_session: bool = False

    @property
    def is_warning(self) -> bool:
        """A remote session without redirection is a setup gap, not a defect."""
        return not self.ok and self.remote_session


@dataclass(frozen=True)
class Device:
    """One input device.

    ``name`` is the stable identifier used in config and on the command line;
    ``index`` is the ephemeral PortAudio index, resolved fresh every time.
    """

    name: str
    description: str
    index: int
    channels: int
    sample_rate: float
    is_default: bool = False

    def matches(self, query: str) -> bool:
        query = query.strip().lower()
        if not query:
            return False
        return (
            query == self.name.lower()
            or query in self.description.lower()
            or query in self.name.lower()
        )


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "device"


def _pipewire_sources() -> list[tuple[str, str]]:
    """(name, description) for every PipeWire/PulseAudio source.

    PortAudio on a PipeWire host usually collapses every real microphone into
    one ``pipewire`` device, which is useless to choose from. The sound server
    is the authority on what devices exist, so we ask it directly and use
    PortAudio only to open the stream.
    """
    import shutil
    import subprocess

    if shutil.which("pactl") is None:
        return []
    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sources"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        log.debug("pactl source enumeration failed", error=str(exc))
        return []
    if result.returncode != 0:
        return []

    sources: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        name = fields[1].strip()
        if not name or name.endswith(".monitor"):
            # Monitors are loopbacks of output, never what a user means by
            # "microphone".
            continue
        sources.append((name, name))
    return sources


def enumerate_devices() -> list[Device]:
    """All input-capable devices currently present."""
    try:
        import sounddevice as sd
    except Exception as exc:  # pragma: no cover - import guard
        raise Fault(
            code=FaultCode.NO_DEVICE,
            message=f"sounddevice is not usable: {exc}",
            remedy="Install PortAudio and the sounddevice package.",
        ) from exc

    try:
        raw = sd.query_devices()
        try:
            default_index = sd.default.device[0]
        except (TypeError, IndexError):
            default_index = None
    except Exception as exc:
        raise Fault(
            code=FaultCode.NO_DEVICE,
            message=f"could not enumerate audio devices: {exc}",
            remedy="Check that PipeWire or PulseAudio is running: systemctl --user status pipewire",
        ) from exc

    seen: dict[str, int] = {}
    devices: list[Device] = []
    portaudio_by_slug: dict[str, int] = {}
    for index, info in enumerate(raw):
        if int(info.get("max_input_channels", 0)) <= 0:
            continue
        description = str(info.get("name", f"device {index}")).strip()
        base = _slug(description)
        # Two cards can report the same name; disambiguate deterministically.
        count = seen.get(base, 0)
        seen[base] = count + 1
        name = base if count == 0 else f"{base}-{count + 1}"
        portaudio_by_slug.setdefault(base, index)
        devices.append(
            Device(
                name=name,
                description=description,
                index=index,
                channels=int(info.get("max_input_channels", 1)),
                sample_rate=float(info.get("default_samplerate", 48000.0)),
                is_default=(index == default_index),
            )
        )

    # Where the sound server knows about real microphones that PortAudio has
    # collapsed into an aggregate device, present the real ones and open them
    # through the aggregate.
    aggregate = next(
        (d for d in devices if d.name in ("pipewire", "pulse", "default")), None
    )
    if aggregate is not None:
        for source_name, source_description in _pipewire_sources():
            slug = _slug(source_name)
            if any(d.name == slug for d in devices):
                continue
            devices.append(
                Device(
                    name=slug,
                    description=source_description,
                    index=portaudio_by_slug.get(slug, aggregate.index),
                    channels=1,
                    sample_rate=aggregate.sample_rate,
                    is_default=False,
                )
            )
    return devices


#: PortAudio names that route to the sound server rather than to hardware.
AGGREGATE_NAMES = frozenset({"pipewire", "pulse", "default", "sysdefault"})


def is_aggregate(device: "Device") -> bool:
    return device.name in AGGREGATE_NAMES


def _session_is_remote() -> bool:
    """Whether this login session has no local seat.

    A remote session reaches no local sound card, so its microphone must be
    redirected by the remote-desktop protocol rather than found on the host.
    """
    import shutil
    import subprocess

    session_id = os.environ.get("XDG_SESSION_ID")
    if shutil.which("loginctl") is None:
        return False
    try:
        result = subprocess.run(
            ["loginctl", "show-session", session_id or "auto", "-p", "Remote", "-p", "Seat"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    values = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    return values.get("Remote") == "yes" or not values.get("Seat", "").strip()


def diagnose() -> AudioDiagnosis:
    """Report whether a real capture source exists, not merely a device entry."""
    sources = _pipewire_sources()
    remote = _session_is_remote()

    if sources:
        return AudioDiagnosis(
            ok=True,
            summary=f"{len(sources)} capture source(s)",
            real_sources=len(sources),
            remote_session=remote,
        )

    try:
        devices = enumerate_devices()
    except Fault:
        devices = []
    hardware = [d for d in devices if not is_aggregate(d)]
    if hardware:
        # No sound server, but PortAudio sees real hardware directly.
        return AudioDiagnosis(
            ok=True,
            summary=f"{len(hardware)} device(s) via PortAudio",
            real_sources=len(hardware),
            remote_session=remote,
        )

    if remote:
        return AudioDiagnosis(
            ok=False,
            summary="none — this is a remote session with no microphone redirected",
            remedy=(
                "Enable microphone redirection in your remote-desktop client "
                "(FreeRDP: /microphone; Remmina: Redirect microphone; Windows "
                "mstsc: Remote audio > Record from this computer). Or run "
                "dictator on the machine the microphone is plugged into — its "
                "keystrokes reach this session through the client anyway."
            ),
            remote_session=True,
        )

    return AudioDiagnosis(
        ok=False,
        summary="none — no capture source exists",
        remedy=(
            "Connect a microphone, then check the sound server is running: "
            "systemctl --user status pipewire"
        ),
    )


def resolve(query: str | None) -> Device | None:
    """Find a device by stable name or fuzzy description match.

    Returns None when ``query`` is empty, meaning "use the system default" —
    which is a valid, deliberate choice, not a failure.
    """
    devices = enumerate_devices()
    if not devices:
        raise Fault(
            code=FaultCode.NO_DEVICE,
            message="no audio input devices are present",
            remedy="Connect a microphone, then run: dictator devices",
        )

    if not query or not query.strip():
        for device in devices:
            if device.is_default:
                return device
        return devices[0]

    exact = [d for d in devices if d.name.lower() == query.strip().lower()]
    if exact:
        return exact[0]

    fuzzy = [d for d in devices if d.matches(query)]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        names = ", ".join(d.name for d in fuzzy)
        raise Fault(
            code=FaultCode.NO_DEVICE,
            message=f"{query!r} matches more than one device: {names}",
            remedy=f"Use the exact name: dictator devices set {fuzzy[0].name}",
        )

    available = ", ".join(d.name for d in devices)
    raise Fault(
        code=FaultCode.NO_DEVICE,
        message=f"no input device matches {query!r}",
        remedy=f"Choose one of: {available}",
    )


def find_by_name(name: str) -> Device | None:
    """Non-raising lookup, for checking whether a device is still present."""
    try:
        for device in enumerate_devices():
            if device.name.lower() == name.lower():
                return device
    except Fault:
        return None
    return None
