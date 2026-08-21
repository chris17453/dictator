"""Getting the transcript into the focused field.

Clipboard first, paste second, type last. Per-character injection is slow,
order-sensitive, and mangles anything outside the active keyboard layout, so
it is the fallback rather than the mechanism.

Both halves of the requirement are satisfied unconditionally: the clipboard
*is* the delivery mechanism, so the text is always there, and the paste is
what puts it in the field (v2.md §4.3, fixing G-05's either/or heuristic).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..errors import Fault, FaultCode
from ..logging import get_logger
from ..platform.base import InjectionBackend
from . import profiles
from .profiles import Profile

log = get_logger(__name__)


@dataclass
class DeliveryResult:
    ok: bool
    method: str
    app_id: str = ""
    profile: str = ""
    detail: str = ""


class Deliverer:
    """Applies the delivery policy to one transcript."""

    def __init__(
        self,
        injection: InjectionBackend,
        *,
        mode: str = "paste",
        use_clipboard: bool = True,
        restore_clipboard: bool = True,
        restore_delay_ms: int = 400,
        default_profile: str = "standard",
        clipboard_only_apps: tuple[str, ...] = (),
        trailing_space: bool = False,
    ) -> None:
        self.injection = injection
        self.mode = mode
        self.use_clipboard = use_clipboard
        self.restore_clipboard = restore_clipboard
        self.restore_delay = restore_delay_ms / 1000.0
        self.default_profile = default_profile
        self.clipboard_only_apps = tuple(clipboard_only_apps)
        self.trailing_space = trailing_space
        self._restore_task: asyncio.Task | None = None

    async def deliver(self, text: str, *, profile_override: str = "") -> DeliveryResult:
        if not text or not text.strip():
            return DeliveryResult(ok=False, method="none", detail="nothing to deliver")

        payload = text + (" " if self.trailing_space else "")

        app_id = ""
        try:
            app_id = (await self.injection.focused_app_id()) or ""
        except Exception as exc:  # pragma: no cover - backend dependent
            log.debug("focused application lookup failed", error=str(exc))

        if profile_override:
            profile = profiles.resolve(profile_override)
        else:
            profile = profiles.for_app(
                app_id or None,
                default=self.default_profile,
                clipboard_only_apps=self.clipboard_only_apps,
            )

        # Always place it on the clipboard first. Even if injection fails, the
        # user has the text.
        previous: str | None = None
        clipboard_ok = False
        if self.use_clipboard or self.mode in ("paste", "clipboard"):
            if self.restore_clipboard and self.mode == "paste":
                try:
                    previous = await self.injection.get_clipboard()
                except Exception as exc:
                    log.debug("could not read the clipboard to restore it", error=str(exc))
            try:
                await self.injection.set_clipboard(payload)
                clipboard_ok = True
            except Exception as exc:
                log.warning("clipboard write failed", error=str(exc))

        if self.mode == "clipboard" or not profile.synthesises_input:
            return DeliveryResult(
                ok=clipboard_ok,
                method="clipboard",
                app_id=app_id,
                profile=profile.name,
                detail="copied; no input synthesised",
            )

        if self.mode == "type":
            return await self._type(payload, app_id, profile, clipboard_ok)

        return await self._paste(payload, app_id, profile, previous, clipboard_ok)

    async def _paste(
        self,
        payload: str,
        app_id: str,
        profile: Profile,
        previous: str | None,
        clipboard_ok: bool,
    ) -> DeliveryResult:
        if not clipboard_ok:
            log.info("clipboard unavailable; typing instead of pasting")
            return await self._type(payload, app_id, profile, clipboard_ok)
        try:
            await self.injection.send_chord(profile.paste)
        except Fault as fault:
            log.warning("paste failed; the text is on the clipboard",
                        error=fault.message)
            return DeliveryResult(
                ok=clipboard_ok,
                method="clipboard",
                app_id=app_id,
                profile=profile.name,
                detail=f"paste failed: {fault.message}",
            )

        if self.restore_clipboard and previous is not None:
            self._schedule_restore(previous)

        return DeliveryResult(ok=True, method="paste", app_id=app_id, profile=profile.name)

    async def _type(
        self, payload: str, app_id: str, profile: Profile, clipboard_ok: bool
    ) -> DeliveryResult:
        try:
            await self.injection.type_text(payload)
        except Fault as fault:
            return DeliveryResult(
                ok=clipboard_ok,
                method="clipboard" if clipboard_ok else "none",
                app_id=app_id,
                profile=profile.name,
                detail=f"typing failed: {fault.message}",
            )
        return DeliveryResult(ok=True, method="type", app_id=app_id, profile=profile.name)

    def _schedule_restore(self, previous: str) -> None:
        """Put the user's clipboard back, after the paste has certainly landed."""
        if self._restore_task is not None and not self._restore_task.done():
            self._restore_task.cancel()

        async def restore() -> None:
            try:
                await asyncio.sleep(self.restore_delay)
                await self.injection.set_clipboard(previous)
                log.debug("clipboard restored")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("clipboard restore failed", error=str(exc))

        self._restore_task = asyncio.create_task(restore())

    async def close(self) -> None:
        if self._restore_task is not None and not self._restore_task.done():
            self._restore_task.cancel()
            try:
                await self._restore_task
            except (asyncio.CancelledError, Exception):
                pass
