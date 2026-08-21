"""The daemon: everything that must be warm, stateful, or consented.

Holds the resident model, the open audio stream, and the platform sessions —
the three things that independently force a long-lived process (v2.md §4.1).
Every client is a subscriber to the D-Bus contract in :mod:`dictatord.service`.
"""
from __future__ import annotations

import asyncio
import signal
import time
from pathlib import Path

from . import config as config_module
from .asr.engine import Engine
from .consent import ConsentLedger, Decision
from .asr.stream import Partial, StreamingDecoder
from .asr import models as model_catalog
from .audio import devices as device_catalog
from .audio.capture import Capture, LevelFrame
from .audio.vad import EnergyVad
from .delivery.deliver import Deliverer
from .errors import Fault, FaultCode
from .logging import get_logger
from .memory.lexicon import Lexicon
from .metrics import Metrics
from .memory.store import TranscriptStore
from .platform import registry
from .platform.appid import app_id
from .platform.base import ShortcutEvent
from .platform.chords import Chord, ChordError, parse_optional, validate_usable
from .session import Mode, Session, SessionManager, State

log = get_logger(__name__)

#: Shortcut ids the daemon knows about, and how each is described to the user.
SHORTCUT_DESCRIPTIONS = {
    "dictate": "Start or stop dictation (tap to toggle, hold to talk)",
    "dictate_terminal": "Dictate into a terminal",
    "cancel": "Discard the dictation in progress",
}


class Daemon:
    def __init__(self, cfg: config_module.Config) -> None:
        self.config = cfg
        self.started_at = time.time()
        self._shutdown = asyncio.Event()
        self.metrics = Metrics()
        #: Set while an utterance is being transcribed or delivered, so
        #: shutdown can wait for it instead of discarding the user's words.
        self._in_flight: asyncio.Event = asyncio.Event()
        self._in_flight.set()

        self.capture = Capture(
            sample_rate=cfg["audio.sample_rate"],
            preroll_ms=cfg["audio.preroll_ms"],
        )
        self.engine = Engine(
            model_root=config_module.models_dir(),
            model=cfg["model.name"],
            device=cfg["model.device"],
            compute_type=cfg["model.compute_type"],
            beam_size=cfg["model.beam_size"],
            language=cfg["model.language"],
            verify_digest=cfg["model.verify_digest"],
        )
        self.vad = (
            EnergyVad(
                cfg["audio.sample_rate"],
                threshold=cfg["vad.threshold"],
                silence_ms=cfg["vad.silence_ms"],
                min_speech_ms=cfg["vad.min_speech_ms"],
            )
            if cfg["vad.enabled"]
            else None
        )
        self.session_manager = SessionManager(
            self.capture,
            hold_threshold_ms=cfg["shortcuts.hold_threshold_ms"],
            max_utterance_s=cfg["audio.max_utterance_s"],
            vad=self.vad,
            on_state=self._on_state,
            on_finished=self._on_session_finished,
        )
        self.store = TranscriptStore(
            config_module.data_dir() / "transcripts.db",
            redact_patterns=cfg["memory.redact_patterns"],
        )
        self.lexicon = Lexicon(
            config_module.data_dir() / "lexicon.json",
            max_prompt_terms=cfg["lexicon.max_prompt_terms"],
        )
        self.consent = ConsentLedger(
            config_module.state_dir() / "consent.json"
        ).load()

        self.platform: registry.PlatformSelection | None = None
        self.deliverer: Deliverer | None = None
        self.streamer: StreamingDecoder | None = None
        self.interface = None
        self.bus = None
        self._pending_profile = ""
        self._idle_task: asyncio.Task | None = None
        self._consent_task: asyncio.Task | None = None
        #: Whether the consent-requiring setup completed. Reported by GetState
        #: so 'dictator status' can explain a half-ready daemon.
        self.shortcuts_ready = False
        self.injection_ready = False

    # ------------------------------------------------------------------
    # startup
    # ------------------------------------------------------------------

    async def start(self) -> None:
        cfg = self.config

        if cfg["memory.enabled"]:
            self.store.open()
            removed = self.store.prune(cfg["memory.retain_days"])
            if removed:
                log.info("retention applied", removed=removed)
        if cfg["lexicon.enabled"]:
            self.lexicon.load()

        self.platform = await registry.select(
            shortcut_preference=cfg["shortcuts.backend"],
            token_path=config_module.state_dir() / "portal-token.json",
        )

        if self.platform.injection is not None:
            self.deliverer = Deliverer(
                self.platform.injection,
                mode=cfg["delivery.mode"],
                use_clipboard=cfg["delivery.clipboard"],
                restore_clipboard=cfg["delivery.restore_clipboard"],
                restore_delay_ms=cfg["delivery.restore_delay_ms"],
                default_profile=cfg["delivery.default_profile"],
                clipboard_only_apps=tuple(cfg["delivery.clipboard_only_apps"]),
                trailing_space=cfg["delivery.trailing_space"],
            )

        # Hold-to-talk is only meaningful if the backend reports key release.
        self.session_manager.supports_release = self.platform.supports_hold

        await self._start_capture()

        if cfg["streaming.enabled"]:
            self.streamer = StreamingDecoder(
                self.engine,
                cfg["audio.sample_rate"],
                interval_ms=cfg["streaming.interval_ms"],
                min_audio_ms=cfg["streaming.min_audio_ms"],
                on_partial=self._on_partial,
            )

        if cfg["model.keep_resident"]:
            asyncio.create_task(self._preload())
        if cfg["model.idle_unload_s"]:
            self._idle_task = asyncio.create_task(self._idle_watch())

        log.info(
            "daemon ready",
            shortcuts=self.platform.shortcuts.name if self.platform.shortcuts else "none",
            injection=self.platform.injection.name if self.platform.injection else "none",
            hold_to_talk=self.platform.supports_hold,
        )

    async def _acquire_consent(self) -> None:
        """Set up everything that may block on a user consent prompt.

        Deliberately not awaited during startup. The portal shows a dialog and
        will happily wait minutes for an answer; blocking on that before the
        service is published would make ``dictator status`` and ``doctor``
        unusable at exactly the moment the user needs them to explain what is
        being asked of them.
        """
        if self.platform is None:
            return

        await self._acquire("shortcuts", self._start_shortcuts)
        await self._acquire("injection", self._start_injection)

    async def _acquire(self, key: str, action) -> None:
        """Run one consent-requiring step, at most once per answer.

        A backend that needs no consent is simply attempted. One that does is
        attempted only if the user has not already answered: a decline, or a
        prompt left unanswered, is remembered. Re-asking on every start turns a
        restart into a stream of dialogs the user must dismiss, which is worse
        than the missing feature.
        """
        capability = (
            self.platform.shortcut_capability if key == "shortcuts"
            else self.platform.injection_capability
        )
        needs_consent = bool(capability and capability.requires_consent)

        if needs_consent and not self.consent.should_ask(key):
            reason = self.consent.why_not_asking(key)
            if self.consent.get(key).decision is Decision.GRANTED:
                # Consent persists in the portal itself; re-running is cheap
                # and silent once granted.
                pass
            else:
                log.info(
                    "not asking for permission again",
                    permission=key,
                    reason=reason,
                    remedy="dictator grant",
                )
                return

        try:
            ok = await action()
        except Fault as fault:
            self._report(fault)
            if needs_consent:
                self.consent.record(key, Decision.IGNORED
                                    if "did not answer" in fault.message
                                    else Decision.DECLINED, fault.message)
            return
        if needs_consent:
            self.consent.record(
                key, Decision.GRANTED if ok else Decision.DECLINED
            )

    async def _start_shortcuts(self) -> bool:
        if self.platform.shortcuts is None:
            return False
        await self.platform.shortcuts.start(self._on_shortcut)
        self.shortcuts_ready = await self._bind_shortcuts()
        if not self.shortcuts_ready:
            log.warning(
                "no global shortcut is bound; dictation still works via "
                "'dictator toggle'"
            )
        return self.shortcuts_ready

    async def _start_injection(self) -> bool:
        if self.platform.injection is None:
            return False
        await self.platform.injection.start()
        self.injection_ready = True
        return True

    async def _preload(self) -> None:
        try:
            await self.engine.ensure_loaded()
        except Fault as fault:
            self._report(fault)

    async def _start_capture(self) -> None:
        try:
            await self.capture.start(
                self.config["audio.device"],
                on_level=self._on_level,
                on_audio=self.session_manager.feed,
                on_lost=self._on_device_lost,
            )
        except Fault as fault:
            # No microphone is a normal state to boot into; the daemon stays up
            # so 'dictator devices' and 'doctor' still work.
            self._report(fault)
            log.warning("starting without audio capture")

    async def _bind_shortcuts(self) -> bool:
        cfg = self.config
        wanted: dict[str, Chord] = {}
        for shortcut_id in ("dictate", "dictate_terminal", "cancel"):
            try:
                chord = parse_optional(cfg[f"shortcuts.{shortcut_id}"])
            except ChordError as exc:
                self._report(
                    Fault(
                        code=FaultCode.SHORTCUT_BIND_FAILED,
                        message=f"shortcuts.{shortcut_id} is not a valid chord: {exc}",
                        remedy=f"Fix it: dictator keys set {shortcut_id} <chord>",
                    )
                )
                continue
            if chord is None:
                continue
            try:
                validate_usable(chord)
            except ChordError as exc:
                self._report(
                    Fault(
                        code=FaultCode.SHORTCUT_BIND_FAILED,
                        message=str(exc),
                        remedy=f"Pick another chord: dictator keys set {shortcut_id} <chord>",
                    )
                )
                continue
            wanted[shortcut_id] = chord

        if not wanted:
            return False
        try:
            result = await self.platform.shortcuts.bind(wanted, SHORTCUT_DESCRIPTIONS)
        except Fault as fault:
            self._report(fault)
            return False
        for shortcut_id, reason in result.rejected.items():
            self._report(
                Fault(
                    code=FaultCode.SHORTCUT_BIND_FAILED,
                    message=f"{shortcut_id} ({wanted[shortcut_id]}) was not bound: {reason}",
                    remedy=f"Pick another chord: dictator keys set {shortcut_id} <chord>",
                )
            )
        return bool(result.bound)

    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------

    def _on_shortcut(self, shortcut_id: str, event: ShortcutEvent) -> None:
        asyncio.create_task(self._handle_shortcut(shortcut_id, event))

    async def _handle_shortcut(self, shortcut_id: str, event: ShortcutEvent) -> None:
        try:
            if shortcut_id == "cancel":
                if event is ShortcutEvent.PRESSED:
                    await self.cancel()
                return
            override = "terminal" if shortcut_id == "dictate_terminal" else ""
            await self.session_manager.on_shortcut(shortcut_id, event, override)
        except Fault as fault:
            self._report(fault)
        except Exception as exc:  # pragma: no cover - never lose the listener
            log.error("shortcut handling failed", error=str(exc))

    def _on_state(self, state: State, detail: dict) -> None:
        if self.interface is not None:
            from .service import _sv

            self.interface.StateChanged(state.value, _sv(detail))
        if state is State.LISTENING:
            self.metrics.sessions_started += 1
        if state is State.LISTENING and self.streamer is not None:
            session = self.session_manager.session
            if session is not None and not self.streamer.running:
                prompt = self.lexicon.prompt() if self.config["lexicon.enabled"] else ""
                self.streamer.start(session, prompt)

    def _on_level(self, frame: LevelFrame) -> None:
        if self.interface is not None:
            self.interface.Level(*frame.as_tuple())

    async def _on_partial(self, partial: Partial) -> None:
        self.metrics.partials_emitted += 1
        if self.interface is not None:
            self.interface.Partial(partial.session_id, partial.text, partial.stable_chars)

    def _on_device_lost(self, name: str) -> None:
        self.metrics.device_losses += 1
        asyncio.create_task(self._handle_device_lost(name))

    async def _handle_device_lost(self, name: str) -> None:
        policy = self.config["audio.on_device_lost"]
        fault = Fault(
            code=FaultCode.DEVICE_LOST,
            message=f"the input device {name!r} disappeared",
            remedy="Reconnect it, or choose another: dictator devices",
        )
        self._report(fault)
        if policy != "fallback":
            return
        log.info("falling back to the default input device")
        try:
            await self.capture.stop()
            await self.capture.start(
                "",
                on_level=self._on_level,
                on_audio=self.session_manager.feed,
                on_lost=self._on_device_lost,
            )
        except Fault as inner:
            self._report(inner)

    # ------------------------------------------------------------------
    # the utterance pipeline
    # ------------------------------------------------------------------

    async def _on_session_finished(self, session: Session) -> None:
        self._in_flight.clear()
        try:
            with self.metrics.time(self.metrics.end_to_end_ms):
                await self._transcribe_and_deliver(session)
        except Fault as fault:
            self._report(fault)
        except Exception as exc:  # pragma: no cover
            log.error("utterance pipeline failed", error=str(exc))
        finally:
            self.session_manager.finish()
            self._in_flight.set()

    async def _transcribe_and_deliver(self, session: Session) -> None:
        sample_rate = self.config["audio.sample_rate"]
        if self.streamer is not None:
            await self.streamer.stop()

        prompt = self.lexicon.prompt() if self.config["lexicon.enabled"] else ""
        with self.metrics.time(self.metrics.decode_ms):
            result = await self.engine.transcribe(session.audio(), sample_rate, prompt=prompt)
        self.metrics.utterance_s.observe(result.duration_s)

        text = self.lexicon.apply(result.text) if self.config["lexicon.enabled"] else result.text
        text = text.strip()

        if not text:
            self.metrics.sessions_empty += 1
            log.info("nothing recognised", id=session.id,
                     seconds=round(session.duration_s(sample_rate), 2))
            return

        self.metrics.confidence.observe(result.confidence)

        log.info(
            "transcribed",
            id=session.id,
            chars=len(text),
            confidence=round(result.confidence, 2),
            audio_s=round(result.duration_s, 2),
            decode_s=round(result.decode_s, 2),
        )
        if self.interface is not None:
            self.interface.Final(session.id, text, result.confidence)

        entry = None
        if self.config["memory.enabled"]:
            entry = self.store.add(
                text,
                duration_s=result.duration_s,
                confidence=result.confidence,
                model=self.engine.model_name,
                language=result.language,
            )

        if self.deliverer is None:
            return

        self.session_manager._set_state(State.DELIVERING, session=session.id)
        with self.metrics.time(self.metrics.delivery_ms):
            delivery = await self.deliverer.deliver(
                text, profile_override=session.profile_override
            )
        self.metrics.count_delivery(delivery.method, delivery.ok)
        if delivery.ok:
            self.metrics.sessions_delivered += 1
        if entry is not None:
            self.store.mark_delivered(
                entry.id, delivery.method, delivery.app_id, delivery.ok
            )
        if self.interface is not None:
            self.interface.Delivered(
                session.id, delivery.method, delivery.app_id, delivery.ok
            )
        log.info(
            "delivered",
            id=session.id,
            method=delivery.method,
            profile=delivery.profile,
            app=delivery.app_id or "unknown",
            ok=delivery.ok,
        )

    # ------------------------------------------------------------------
    # D-Bus surface
    # ------------------------------------------------------------------

    async def toggle(self, options: dict) -> int:
        profile = str(options.get("profile", "") or "")
        if self.session_manager.is_active:
            session = await self.session_manager.stop()
            return session.id if session else 0
        session = await self.session_manager.start(Mode.TOGGLE, profile_override=profile)
        return session.id

    async def push_begin(self, options: dict) -> int:
        profile = str(options.get("profile", "") or "")
        if self.session_manager.is_active:
            return self.session_manager.session.id
        session = await self.session_manager.start(Mode.HOLD, profile_override=profile)
        return session.id

    async def push_end(self) -> int:
        session = await self.session_manager.stop()
        return session.id if session else 0

    async def cancel(self) -> bool:
        if self.streamer is not None:
            await self.streamer.stop()
        cancelled = await self.session_manager.cancel()
        if cancelled:
            self.metrics.sessions_cancelled += 1
        return cancelled

    async def redeliver(self, entry_id: int, options: dict) -> bool:
        if not self.config["memory.enabled"]:
            raise Fault(
                code=FaultCode.STORE_UNAVAILABLE,
                message="transcript memory is disabled, so there is nothing to redeliver",
                remedy="Enable it: dictator config set memory.enabled true",
            )
        entry = self.store.get(entry_id) if entry_id else self.store.last()
        if entry is None:
            raise Fault(
                code=FaultCode.STORE_UNAVAILABLE,
                message=f"no transcript with id {entry_id}",
                remedy="List what is stored: dictator history",
            )
        if self.deliverer is None:
            raise Fault(
                code=FaultCode.NO_INJECTION_BACKEND,
                message="no injection backend, so text cannot be delivered",
                remedy="Run 'dictator doctor' to see what each backend reported.",
            )
        result = await self.deliverer.deliver(
            entry.text, profile_override=str(options.get("profile", "") or "")
        )
        return result.ok

    async def set_device(self, name: str) -> str:
        await self.capture.stop()
        try:
            device = await self.capture.start(
                name,
                on_level=self._on_level,
                on_audio=self.session_manager.feed,
                on_lost=self._on_device_lost,
            )
        except Fault:
            # Put the previous device back so a bad choice does not leave the
            # daemon deaf.
            await self.capture.start(
                self.config["audio.device"],
                on_level=self._on_level,
                on_audio=self.session_manager.feed,
                on_lost=self._on_device_lost,
            )
            raise
        config_module.save_user({"audio.device": device.name if device else ""})
        self.config.values["audio.device"] = device.name if device else ""
        return device.name if device else ""

    def list_devices(self) -> list:
        try:
            devices = device_catalog.enumerate_devices()
        except Fault:
            return []
        active = self.capture.device.name if self.capture.device else ""
        return [
            [d.name, d.description, d.name == active, True] for d in devices
        ]

    async def set_model(self, name: str, options: dict) -> dict:
        resolution = await self.engine.switch(
            model=name or None,
            device=options.get("device"),
            compute_type=options.get("compute_type"),
        )
        updates = {"model.name": name} if name else {}
        if options.get("device"):
            updates["model.device"] = options["device"]
        if options.get("compute_type"):
            updates["model.compute_type"] = options["compute_type"]
        if updates:
            config_module.save_user(updates)
            self.config.values.update(updates)
        return {
            "model": resolution.model,
            "device": resolution.device,
            "compute_type": resolution.compute_type,
        }

    def list_models(self) -> list:
        root = config_module.models_dir()
        current = self.engine.model_name
        return [
            [
                spec.name,
                spec.note,
                model_catalog.is_downloaded(root, spec.name),
                spec.name == current,
                spec.parameters,
            ]
            for spec in model_catalog.CATALOG
        ]

    def search(self, query: str, limit: int) -> list[dict]:
        if not self.config["memory.enabled"]:
            return []
        entries = self.store.search(query, limit or 20)
        return [e.as_dict() for e in entries]

    async def set_shortcut(self, shortcut_id: str, chord_text: str) -> dict:
        if shortcut_id not in SHORTCUT_DESCRIPTIONS:
            raise Fault(
                code=FaultCode.SHORTCUT_BIND_FAILED,
                message=f"unknown shortcut {shortcut_id!r}",
                remedy=f"Known shortcuts: {', '.join(SHORTCUT_DESCRIPTIONS)}",
            )
        chord = parse_optional(chord_text)
        if chord is not None:
            validate_usable(chord)
        key = f"shortcuts.{shortcut_id}"
        config_module.save_user({key: str(chord) if chord else ""})
        self.config.values[key] = str(chord) if chord else ""
        if self.platform and self.platform.shortcuts:
            await self._bind_shortcuts()
        return {"shortcut": shortcut_id, "chord": str(chord) if chord else ""}

    def list_shortcuts(self) -> list:
        bound = (
            self.platform.shortcuts.bound()
            if self.platform and self.platform.shortcuts
            else {}
        )
        rows = []
        for shortcut_id, description in SHORTCUT_DESCRIPTIONS.items():
            configured = self.config.get(f"shortcuts.{shortcut_id}", "") or ""
            actual = str(bound.get(shortcut_id, "")) or ("" if configured else "")
            rows.append([shortcut_id, configured or "(unbound)", description])
        return rows

    def state_snapshot(self) -> dict:
        device = self.capture.device
        snapshot = {
            "state": self.session_manager.state.value,
            "uptime_s": int(time.time() - self.started_at),
            "device": device.name if device else "",
            "device_description": device.description if device else "",
            "capturing": self.capture.running,
            "hold_to_talk": self.platform.supports_hold if self.platform else False,
            "transcripts": self.store.count() if self.config["memory.enabled"] else 0,
            "lexicon_terms": len(self.lexicon.terms),
            "app_id": app_id(),
            "health": self.metrics.health()[0],
            "shortcuts_ready": self.shortcuts_ready,
            "consent_shortcuts": self.consent.get("shortcuts").decision.value,
            "consent_injection": self.consent.get("injection").decision.value,
            "injection_ready": self.injection_ready,
        }
        engine = self.engine.describe()
        snapshot.update(
            {
                "model": engine["model"],
                "model_device": engine["device"],
                "model_compute_type": engine["compute_type"],
                "model_loaded": engine["loaded"],
                "model_integrity": engine["integrity"],
            }
        )
        if self.platform:
            snapshot.update(self.platform.describe())
        return snapshot

    def health(self) -> dict:
        """Readiness and liveness in one answer.

        'starting' is distinct from 'degraded' on purpose: a daemon still
        waiting for the user to approve a consent prompt is not broken, and a
        monitor that restarts it would only re-ask the question.
        """
        status, problems = self.metrics.health()
        ready = self.capture.running and (
            self.shortcuts_ready or self.platform is None
            or self.platform.shortcuts is None
            or self.platform.shortcuts.name == "none"
        )
        if not ready and self.metrics.sessions_started == 0:
            status, problems = "starting", (problems or ["waiting for setup to complete"])
        return {
            "status": status,
            "ready": ready,
            "problems": "; ".join(problems),
            "uptime_s": int(self.metrics.uptime_s),
        }

    async def reload(self) -> dict:
        cfg = config_module.load()
        self.config = cfg
        self.session_manager.hold_threshold = cfg["shortcuts.hold_threshold_ms"] / 1000.0
        self.session_manager.max_utterance_s = cfg["audio.max_utterance_s"]
        if self.deliverer is not None:
            self.deliverer.mode = cfg["delivery.mode"]
            self.deliverer.default_profile = cfg["delivery.default_profile"]
            self.deliverer.trailing_space = cfg["delivery.trailing_space"]
            self.deliverer.restore_clipboard = cfg["delivery.restore_clipboard"]
        if self.platform and self.platform.shortcuts:
            await self._bind_shortcuts()
        log.info("configuration reloaded", files=len(cfg.loaded_files))
        return {"reloaded": "true", "files": len(cfg.loaded_files)}

    async def request_shutdown(self) -> None:
        self._shutdown.set()

    # ------------------------------------------------------------------
    # housekeeping
    # ------------------------------------------------------------------

    async def _idle_watch(self) -> None:
        seconds = self.config["model.idle_unload_s"]
        while not self._shutdown.is_set():
            await asyncio.sleep(min(60, seconds))
            if self.session_manager.state is State.IDLE:
                await self.engine.maybe_unload_idle(seconds)

    def _report(self, fault: Fault) -> None:
        self.metrics.count_fault(fault.code.value)
        log.error(fault.message, code=fault.code.value, remedy=fault.remedy)
        if self.interface is not None:
            self.interface.FaultOccurred(*fault.as_signal())

    async def run(self) -> None:
        from .service import publish

        await self.start()
        # Publish before asking for consent, so clients can always reach us.
        self.bus, self.interface = await publish(self)
        self._consent_task = asyncio.create_task(self._acquire_consent())

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:  # pragma: no cover - non-unix
                pass

        await self._shutdown.wait()
        await self._drain()
        await self.shutdown()

    async def _drain(self, timeout: float = 20.0) -> None:
        """Let an utterance already being transcribed finish.

        A SIGTERM arriving mid-decode would otherwise throw away words the user
        has already spoken — the one loss they cannot recover by retrying,
        because the audio is gone with the process.
        """
        if self._in_flight.is_set() and not self.session_manager.is_active:
            return
        if self.session_manager.is_active:
            log.info("stopping the utterance in progress before shutting down")
            try:
                await self.session_manager.stop()
            except Exception as exc:  # pragma: no cover
                log.error("could not stop the active session", error=str(exc))
        try:
            await asyncio.wait_for(self._in_flight.wait(), timeout)
            log.info("in-flight utterance completed")
        except asyncio.TimeoutError:
            log.warning(
                "an utterance was still being processed at shutdown; it is lost",
                waited_s=timeout,
            )

    async def shutdown(self) -> None:
        log.info("shutting down")
        if self._idle_task is not None:
            self._idle_task.cancel()
        if self._consent_task is not None and not self._consent_task.done():
            self._consent_task.cancel()
        if self.streamer is not None:
            await self.streamer.stop()
        if self.deliverer is not None:
            await self.deliverer.close()
        await self.capture.stop()
        if self.platform:
            if self.platform.shortcuts is not None:
                await self.platform.shortcuts.stop()
            if self.platform.injection is not None:
                await self.platform.injection.stop()
        if self.config["lexicon.enabled"]:
            self.lexicon.save()
        self.store.close()
        if self.bus is not None:
            self.bus.disconnect()
        log.info("stopped")
