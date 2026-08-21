"""``dictator doctor`` — check every dependency and say what to fix.

This exists specifically because the previous system's most damaging property
was that it failed silently and then misdiagnosed itself, telling users to join
the ``input`` group when the real problem was that an X11 library cannot see
Wayland input at all (G-08).

Every check reports pass, fail, or warning — and every failure carries a remedy
that is a command you can run.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import ssl
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dictatord import config as cfg
from dictatord.asr import models
from dictatord.errors import Fault
from dictatord.platform import registry
from dictatord.platform.appid import DESKTOP_ID, app_id
from dictatord.platform.detect import SessionType, detect

from .. import format as fmt
from ..client import is_running
from ..client import run as client_run


#: The name of the function v1 installed process-wide to disable certificate
#: checking (G-15). Named here only so its presence can be detected.
_BYPASS_FUNCTION = "_create_unverified_context"  # tls-audit-allow: detection only


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    remedy: str = ""
    warn: bool = False
    extra: list[str] = field(default_factory=list)


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator doctor",
        description="Check every dependency and say what to fix.",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Include everything that was probed, not just the outcome.")
    args = parser.parse_args(argv)

    checks = asyncio.run(_collect(args.verbose))

    width = max(len(c.name) for c in checks)
    failures = 0
    warnings = 0
    for check in checks:
        mark = fmt.status_mark(check.ok, check.warn)
        dots = fmt.dim("." * max(2, width - len(check.name) + 2))
        print(f"  {mark} {check.name} {dots} {check.detail}")
        for line in check.extra:
            print(f"      {fmt.dim(line)}")
        if check.remedy:
            print(f"      {fmt.cyan('remedy:')} {check.remedy}")
        if not check.ok and not check.warn:
            failures += 1
        elif check.warn:
            warnings += 1

    print()
    if failures:
        print(f"{fmt.BAD} {failures} problem(s) need attention"
              + (f", {warnings} warning(s)" if warnings else ""))
        return 1
    if warnings:
        print(f"{fmt.WARN} everything essential works, {warnings} thing(s) worth knowing")
        return 0
    print(f"{fmt.OK} everything checks out")
    return 0


async def _collect(verbose: bool) -> list[Check]:
    checks: list[Check] = []
    config = _config_check(checks)
    session = _session_check(checks)
    daemon_state = await _daemon_state()
    _appid_check(checks, session, daemon_state)
    await _backend_checks(checks, session, config, verbose)
    _tools_check(checks, session)
    _tls_check(checks)
    _model_check(checks, config)
    _audio_check(checks, config)
    _memory_check(checks, config)
    _daemon_check(checks, daemon_state)
    return checks


def _config_check(checks: list[Check]):
    try:
        config = cfg.load()
    except Fault as fault:
        checks.append(Check("configuration", False, fault.message, fault.remedy))
        return cfg.defaults()
    files = [str(p) for p in config.loaded_files]
    checks.append(Check(
        "configuration", True,
        f"{len(cfg.SCHEMA)} settings"
        + (f", {len(files)} file(s)" if files else ", all defaults"),
        extra=files,
    ))
    return config


def _session_check(checks: list[Check]):
    session = detect()
    if session.type is SessionType.HEADLESS:
        checks.append(Check(
            "display session", True,
            "headless — no shortcuts or typing, clipboard only",
            warn=True,
            extra=[session.evidence],
        ))
    else:
        checks.append(Check(
            "display session", True,
            f"{session.type.value}" + (f" ({session.desktop})" if session.desktop else ""),
            extra=[session.evidence] if session.evidence else [],
        ))
    return session


async def _daemon_state() -> dict | None:
    """The running daemon's own view, or None when it is not running."""
    from ..client import Client

    try:
        client = await Client().connect()
    except Fault:
        return None
    try:
        return await client.state()
    except Fault:
        return None
    finally:
        await client.close()


def _appid_check(checks: list[Check], session, daemon_state: dict | None) -> None:
    if not session.is_wayland:
        return
    # The identity that matters is the daemon's, not this command's. A CLI run
    # from a shell never has one, and reporting that would be a false alarm.
    if daemon_state is not None:
        identity = daemon_state.get("app_id", "")
        if identity:
            checks.append(Check("application identity", True, f"{identity} (daemon)"))
            return
        checks.append(Check(
            "application identity", False,
            "the daemon is running without an application identity",
            remedy="Start it through systemd so it gets one: dictator setup --install",
        ))
        return
    identity = app_id()
    if identity:
        checks.append(Check("application identity", True, identity))
        return
    installed = (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "systemd" / "user" / f"app-{DESKTOP_ID}.service"
    ).is_file()
    checks.append(Check(
        "application identity", False,
        "none — GNOME will refuse to bind global shortcuts",
        remedy=(
            "dictator setup --install"
            if not installed
            else "the unit is installed; start via systemd: dictator restart"
        ),
        extra=[
            "The portal identifies applications by their systemd unit.",
            "A process started from a shell has no unit, so no identity.",
        ],
    ))


async def _backend_checks(checks: list[Check], session, config, verbose: bool) -> None:
    try:
        selection = await registry.select(
            shortcut_preference=config["shortcuts.backend"]
        )
    except Fault as fault:
        checks.append(Check("platform backends", False, fault.message, fault.remedy))
        return

    shortcut = selection.shortcut_capability
    if selection.shortcuts is None or shortcut is None:
        checks.append(Check(
            "shortcut backend", False, "none available",
            remedy="Use 'dictator toggle' from a shortcut you bind yourself.",
        ))
    else:
        hold = shortcut.supports_release
        checks.append(Check(
            "shortcut backend", selection.shortcuts.name != "none",
            f"{selection.shortcuts.name} — {shortcut.detail}",
            warn=selection.shortcuts.name == "none",
            remedy="" if hold else "This backend cannot do hold-to-talk; the chord toggles only.",
            extra=[f"trust: {shortcut.trust}"] if verbose and shortcut.trust else [],
        ))

    injection = selection.injection_capability
    if selection.injection is None or injection is None:
        checks.append(Check(
            "injection backend", False, "none available",
            remedy="Transcripts can still be copied: dictator config set delivery.mode clipboard",
        ))
    else:
        is_null = selection.injection.name == "none"
        checks.append(Check(
            "injection backend", not is_null,
            f"{selection.injection.name} — {injection.detail}",
            warn=is_null,
            extra=[f"trust: {injection.trust}"] if verbose and injection.trust else [],
        ))

    checks.append(Check(
        "focused-app detection", selection.supports_focus_query,
        "available (paste profiles are automatic)" if selection.supports_focus_query
        else "not available on Wayland — the default paste profile is used",
        warn=not selection.supports_focus_query,
        remedy="" if selection.supports_focus_query else
        'Bind a second chord for terminals: dictator keys set dictate_terminal "Super+Shift+d"',
    ))

    if verbose:
        for capability in selection.considered:
            checks.append(Check(
                f"  probed {capability.name}", capability.available,
                capability.detail or capability.reason,
                warn=not capability.available,
            ))


def _tools_check(checks: list[Check], session) -> None:
    if session.is_wayland:
        found = shutil.which("wl-copy")
        checks.append(Check(
            "clipboard tool", bool(found),
            found or "wl-copy not found",
            remedy="" if found else "Install it: sudo dnf install wl-clipboard",
        ))


def _tls_check(checks: list[Check]) -> None:
    """The old system disabled certificate verification globally (G-15)."""
    context = ssl.create_default_context()
    ok = context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    default = ssl._create_default_https_context
    bypassed = getattr(default, "__name__", "") == _BYPASS_FUNCTION
    checks.append(Check(
        "tls verification", ok and not bypassed,
        "enabled" if ok and not bypassed else "DISABLED — model downloads are not authenticated",
        remedy="" if ok and not bypassed else
        "Do not disable verification. Fix the trust store: sudo dnf install ca-certificates",
    ))


def _model_check(checks: list[Check], config) -> None:
    root = cfg.models_dir()
    try:
        resolution = models.resolve(
            config["model.name"], config["model.device"], config["model.compute_type"]
        )
    except Fault as fault:
        checks.append(Check("speech model", False, fault.message, fault.remedy))
        return

    downloaded = models.is_downloaded(root, resolution.model)
    detail = f"{resolution.model} on {resolution.device} ({resolution.compute_type})"
    checks.append(Check(
        "speech model", True, detail,
        extra=[resolution.reason] if resolution.reason else [],
    ))
    checks.append(Check(
        "model weights", downloaded,
        f"{fmt.size(models.disk_usage(root, resolution.model))} in {root}" if downloaded
        else "not downloaded yet",
        warn=not downloaded,
        remedy="" if downloaded else
        f"It downloads on first use, or fetch it now: dictator models download {resolution.model}",
    ))
    if downloaded and config["model.verify_digest"]:
        try:
            _ok, detail = models.verify(root, resolution.model, enforce=False)
            checks.append(Check("model integrity", _ok, detail,
                                remedy="" if _ok else
                                f"dictator models remove {resolution.model}"))
        except Fault as fault:
            checks.append(Check("model integrity", False, fault.message, fault.remedy))


def _audio_check(checks: list[Check], config) -> None:
    from dictatord.audio import devices as device_catalog

    # Ask whether a capture source actually exists, rather than trusting the
    # aggregate device PortAudio advertises regardless.
    diagnosis = device_catalog.diagnose()
    if not diagnosis.ok:
        checks.append(Check(
            "microphone", False, diagnosis.summary,
            remedy=diagnosis.remedy,
            warn=diagnosis.is_warning,
            extra=(
                ["Everything else works; only capture is missing."]
                if diagnosis.is_warning else []
            ),
        ))
        return

    try:
        found = device_catalog.enumerate_devices()
    except Fault as fault:
        checks.append(Check("audio devices", False, fault.message, fault.remedy))
        return

    wanted = config["audio.device"]
    if wanted:
        match = device_catalog.find_by_name(wanted)
        checks.append(Check(
            "microphone", match is not None,
            match.description if match else f"{wanted!r} is configured but not present",
            remedy="" if match else "Choose another: dictator devices",
        ))
    else:
        real = [d for d in found if not device_catalog.is_aggregate(d)]
        default = next((d for d in real if d.is_default), real[0] if real else found[0])
        checks.append(Check("microphone", True, f"{default.description} (system default)"))
    checks.append(Check(
        "audio devices", True,
        f"{diagnosis.real_sources} capture source(s), {len(found)} device entries",
    ))


def _memory_check(checks: list[Check], config) -> None:
    if not config["memory.enabled"]:
        checks.append(Check("transcript memory", True, "disabled by configuration", warn=True))
        return
    path = cfg.data_dir() / "transcripts.db"
    if not path.is_file():
        checks.append(Check("transcript memory", True, "not created yet"))
        return
    from dictatord.memory.store import TranscriptStore

    try:
        store = TranscriptStore(path)
        store.open()
        count, size = store.count(), store.size_bytes()
        store.close()
    except Fault as fault:
        checks.append(Check("transcript memory", False, fault.message, fault.remedy))
        return

    large = size > 500 * 1024 * 1024
    checks.append(Check(
        "transcript memory", True,
        f"{count:,} transcripts, {fmt.size(size)}",
        warn=large,
        remedy="" if not large else
        f"dictator config set memory.retain_days 180",
    ))


def _daemon_check(checks: list[Check], state: dict | None) -> None:
    if state is None:
        checks.append(Check(
            "daemon", False, "not running",
            remedy="dictator setup --install",
        ))
        return

    checks.append(Check(
        "daemon", True,
        f"running, {fmt.duration(float(state.get('uptime_s', 0)))}, state={state.get('state','?')}",
    ))
    shortcuts_ready = state.get("shortcuts_ready", "False") == "True"
    checks.append(Check(
        "shortcuts bound", shortcuts_ready,
        "bound and listening" if shortcuts_ready else "not bound",
        remedy="" if shortcuts_ready else
        "Approve the shortcut prompt, or see 'application identity' above.",
    ))
    injection_ready = state.get("injection_ready", "False") == "True"
    checks.append(Check(
        "typing permission", injection_ready,
        "granted" if injection_ready else "not granted — transcripts are copied only",
        warn=not injection_ready,
        remedy="" if injection_ready else
        "Approve the Remote Desktop prompt, then: dictator restart",
    ))
