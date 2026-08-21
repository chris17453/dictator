"""Capability probe and backend selection.

The whole point of G-00's remedy: the platform decision is made once, here,
against the detected session, and recorded so ``GetState`` and ``doctor`` can
report which path is live rather than guessing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import Fault, FaultCode
from ..logging import get_logger
from .base import Capability, InjectionBackend, ShortcutBackend
from .clipboard import for_session
from .detect import Session, SessionType, detect

log = get_logger(__name__)


@dataclass
class PlatformSelection:
    session: Session
    shortcuts: ShortcutBackend | None
    injection: InjectionBackend | None
    shortcut_capability: Capability | None
    injection_capability: Capability | None
    clipboard_name: str = "none"
    considered: list[Capability] = field(default_factory=list)

    @property
    def supports_hold(self) -> bool:
        cap = self.shortcut_capability
        return bool(cap and cap.available and cap.supports_release)

    @property
    def supports_focus_query(self) -> bool:
        cap = self.injection_capability
        return bool(cap and cap.available and cap.supports_focus_query)

    def describe(self) -> dict[str, str]:
        return {
            "session": self.session.type.value,
            "session_evidence": self.session.evidence,
            "desktop": self.session.desktop,
            "shortcut_backend": self.shortcuts.name if self.shortcuts else "none",
            "injection_backend": self.injection.name if self.injection else "none",
            "clipboard": self.clipboard_name,
            "supports_hold": str(self.supports_hold).lower(),
            "supports_focus_query": str(self.supports_focus_query).lower(),
            "trust": (
                self.injection_capability.trust
                if self.injection_capability and self.injection_capability.trust
                else "unknown"
            ),
        }


async def _shortcut_candidates(session: Session, preference: str):
    """Backends worth probing for this session, best first."""
    from .null_backends import NullShortcuts

    candidates: list[type[ShortcutBackend]] = []
    if preference == "none":
        return [NullShortcuts]

    # evdev first when it is usable: it never prompts, and it reports key
    # release, so hold-to-talk works. The portal is preferred only when evdev
    # has no permission, because the portal's guarantee is consent, not
    # capability.
    if preference in ("auto", "evdev"):
        from .evdev_shortcuts import EvdevShortcuts

        candidates.append(EvdevShortcuts)
    if preference in ("auto", "portal") and session.type is not SessionType.HEADLESS:
        from .portal_shortcuts import PortalShortcuts

        candidates.append(PortalShortcuts)
    if preference in ("auto", "x11") and session.is_x11:
        from .x11_shortcuts import X11Shortcuts

        candidates.append(X11Shortcuts)
    if preference == "x11" and not session.is_x11:
        # Explicit request on a non-X11 session: honour it, and let the probe
        # produce the real reason it cannot work.
        from .x11_shortcuts import X11Shortcuts

        candidates.append(X11Shortcuts)

    candidates.append(NullShortcuts)
    return candidates


async def _injection_candidates(session: Session):
    from .null_backends import NullInjection

    candidates: list[type[InjectionBackend]] = []
    if session.type is not SessionType.HEADLESS:
        # Same reasoning as shortcuts: no prompt beats a prompt when the
        # permission is already granted at the device level.
        from .uinput_injection import UinputInjection

        candidates.append(UinputInjection)
    if session.is_wayland:
        from .portal_injection import PortalInjection

        candidates.append(PortalInjection)
    elif session.is_x11:
        from .x11_injection import X11Injection

        candidates.append(X11Injection)
    candidates.append(NullInjection)
    return candidates


async def probe_all(session: Session | None = None) -> list[Capability]:
    """Probe every backend that could conceivably apply. Used by ``doctor``."""
    session = session or detect()
    results: list[Capability] = []

    from .null_backends import NullInjection, NullShortcuts

    shortcut_classes: list[type] = []
    injection_classes: list[type] = []
    try:
        from .portal_shortcuts import PortalShortcuts
        from .portal_injection import PortalInjection

        shortcut_classes.append(PortalShortcuts)
        injection_classes.append(PortalInjection)
    except Exception as exc:  # pragma: no cover - import guard
        log.debug("portal backends unavailable for probing", error=str(exc))
    try:
        from .evdev_shortcuts import EvdevShortcuts
        from .uinput_injection import UinputInjection

        shortcut_classes.append(EvdevShortcuts)
        injection_classes.append(UinputInjection)
    except Exception as exc:  # pragma: no cover - import guard
        log.debug("evdev backends unavailable for probing", error=str(exc))
    try:
        from .x11_shortcuts import X11Shortcuts
        from .x11_injection import X11Injection

        shortcut_classes.append(X11Shortcuts)
        injection_classes.append(X11Injection)
    except Exception as exc:  # pragma: no cover - import guard
        log.debug("x11 backends unavailable for probing", error=str(exc))

    for cls in shortcut_classes + injection_classes + [NullShortcuts, NullInjection]:
        try:
            results.append(await cls.probe())
        except Exception as exc:
            results.append(
                Capability(name=getattr(cls, "name", cls.__name__),
                           available=False, reason=str(exc))
            )
    return results


async def select(
    *,
    session: Session | None = None,
    shortcut_preference: str = "auto",
    token_path=None,
) -> PlatformSelection:
    """Probe and instantiate the best backend pair for this session."""
    session = session or detect()
    log.info(
        "session detected",
        type=session.type.value,
        evidence=session.evidence,
        desktop=session.desktop or "unknown",
    )

    considered: list[Capability] = []

    shortcuts: ShortcutBackend | None = None
    shortcut_capability: Capability | None = None
    for cls in await _shortcut_candidates(session, shortcut_preference):
        capability = await cls.probe()
        considered.append(capability)
        if capability.available:
            shortcuts = cls()
            shortcut_capability = capability
            break
        log.debug("shortcut backend unusable", backend=capability.name,
                  reason=capability.reason)

    clipboard = for_session(session.type.value)

    injection: InjectionBackend | None = None
    injection_capability: Capability | None = None
    for cls in await _injection_candidates(session):
        capability = await cls.probe()
        considered.append(capability)
        if capability.available:
            kwargs = {"clipboard": clipboard}
            if cls.__name__ == "PortalInjection":
                kwargs["token_path"] = token_path
            injection = cls(**kwargs)
            injection_capability = capability
            break
        log.debug("injection backend unusable", backend=capability.name,
                  reason=capability.reason)

    selection = PlatformSelection(
        session=session,
        shortcuts=shortcuts,
        injection=injection,
        shortcut_capability=shortcut_capability,
        injection_capability=injection_capability,
        clipboard_name=clipboard.name,
        considered=considered,
    )

    log.info(
        "platform selected",
        shortcuts=selection.shortcuts.name if selection.shortcuts else "none",
        injection=selection.injection.name if selection.injection else "none",
        clipboard=clipboard.name,
        hold_to_talk=selection.supports_hold,
    )
    if shortcut_capability and not shortcut_capability.supports_release:
        log.warning(
            "the selected shortcut backend cannot report key release; "
            "hold-to-talk is disabled and the chord will toggle only"
        )
    return selection


def require_shortcuts(selection: PlatformSelection) -> ShortcutBackend:
    if selection.shortcuts is None:
        raise Fault(
            code=FaultCode.NO_SHORTCUT_BACKEND,
            message="no usable way to bind a global shortcut on this session",
            remedy="Run 'dictator doctor' to see what each backend reported.",
        )
    return selection.shortcuts
