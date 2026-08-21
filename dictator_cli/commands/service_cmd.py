"""``dictator setup`` and daemon lifecycle.

``setup --install`` is not a convenience on GNOME. The portal derives an
application identity from the systemd unit in the process's cgroup, and GNOME
refuses shortcut requests from applications it cannot identify. Installing the
unit and the desktop entry is what makes global shortcuts possible at all
(see :mod:`dictatord.platform.appid`).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dictatord import config as cfg
from dictatord.errors import Fault, FaultCode
from dictatord.platform.appid import DESKTOP_ID, app_id

from .. import format as fmt
from ..client import is_running
from ..client import run as client_run

UNIT_NAME = f"app-{DESKTOP_ID}.service"


def _unit_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"


def _desktop_dir() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"


def _executable() -> str:
    """The command systemd should run, preferring an installed entry point."""
    found = shutil.which("dictatord")
    if found:
        return found
    return f"{sys.executable} -m dictatord"


def _unit_text() -> str:
    return f"""[Unit]
Description=Dictator speech-to-text service
Documentation=https://github.com/chris17453/dictator
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart={_executable()}
Restart=on-failure
RestartSec=2
# Give a crashing daemon room to be restarted, but stop flapping forever.
StartLimitBurst=5
StartLimitIntervalSec=60
Slice=app.slice
# The portal reads our identity from this unit's name; changing it breaks
# global shortcuts on GNOME.
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
"""


def _desktop_text() -> str:
    return f"""[Desktop Entry]
Type=Application
Name=Dictator
GenericName=Dictation
Comment=Speech-to-text dictation service
Exec=dictator toggle
Icon=audio-input-microphone
Terminal=false
Categories=Utility;Accessibility;
Keywords=dictation;speech;voice;transcription;
NoDisplay=true
X-GNOME-UsesNotifications=true
"""


def setup(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator setup",
        description="Install the service so global shortcuts can work.",
    )
    parser.add_argument("--install", action="store_true",
                        help="Write the systemd unit and desktop entry, then start the service.")
    parser.add_argument("--uninstall", action="store_true",
                        help="Stop the service and remove what --install wrote.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args(argv)

    if args.uninstall:
        return _uninstall()
    if args.install:
        return _install(args.force)
    return _explain()


def _explain() -> int:
    unit = _unit_dir() / UNIT_NAME
    desktop = _desktop_dir() / f"{DESKTOP_ID}.desktop"
    identity = app_id()

    print(fmt.bold("What setup does, and why"))
    print()
    print("  Global shortcuts on GNOME require the portal to identify this")
    print("  application. It does that from the systemd unit the process runs")
    print("  under. Started from a shell there is no such unit, so GNOME")
    print("  refuses to bind any shortcut. Installing fixes that.")
    print()
    print(fmt.kv([
        ("systemd unit", f"{unit} {fmt.OK if unit.is_file() else fmt.dim('(not installed)')}"),
        ("desktop entry", f"{desktop} {fmt.OK if desktop.is_file() else fmt.dim('(not installed)')}"),
        ("this process", identity or fmt.yellow("no application identity")),
    ]))
    print()
    print(f"  Install with: {fmt.bold('dictator setup --install')}")
    return 0


def _install(force: bool) -> int:
    unit_dir, desktop_dir = _unit_dir(), _desktop_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)
    desktop_dir.mkdir(parents=True, exist_ok=True)

    unit = unit_dir / UNIT_NAME
    desktop = desktop_dir / f"{DESKTOP_ID}.desktop"

    for path, text in ((unit, _unit_text()), (desktop, _desktop_text())):
        if path.is_file() and not force and path.read_text() == text:
            print(f"{fmt.OK} {path.name} already up to date")
            continue
        path.write_text(text)
        print(f"{fmt.OK} wrote {path}")

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(desktop_dir)],
                       capture_output=True, check=False)

    if not shutil.which("systemctl"):
        print(fmt.yellow(f"{fmt.WARN} systemctl not found; start the daemon yourself: dictatord"))
        return 0

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", UNIT_NAME],
                   capture_output=True, check=False)
    result = subprocess.run(["systemctl", "--user", "restart", UNIT_NAME],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(fmt.yellow(f"{fmt.WARN} could not start the service: {result.stderr.strip()}"))
        print(fmt.dim(f"  check it with: systemctl --user status {UNIT_NAME}"))
        return 1

    print(f"{fmt.OK} service started and enabled at login")
    print()
    print(fmt.bold("One more step, and it needs you"))
    config = cfg.load()
    print(f"  Your desktop will ask to approve the {fmt.bold(config['shortcuts.dictate'])} "
          f"shortcut and,")
    print("  separately, to allow typing into other applications. Approve both.")
    print()
    print(f"  Then check it worked:  {fmt.bold('dictator doctor')}")
    return 0


def _uninstall() -> int:
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "stop", UNIT_NAME],
                       capture_output=True, check=False)
        subprocess.run(["systemctl", "--user", "disable", UNIT_NAME],
                       capture_output=True, check=False)
    removed = 0
    for path in (_unit_dir() / UNIT_NAME, _desktop_dir() / f"{DESKTOP_ID}.desktop"):
        if path.is_file():
            path.unlink()
            print(f"{fmt.OK} removed {path}")
            removed += 1
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    if not removed:
        print("nothing was installed")
    print(fmt.dim("  configuration and transcripts were left alone"))
    return 0


def daemon(argv: list[str]) -> int:
    """Run the daemon in the foreground, for debugging."""
    parser = argparse.ArgumentParser(
        prog="dictator daemon",
        description="Run the daemon in this terminal. Normally systemd does this.",
    )
    parser.add_argument("--log-level", choices=("debug", "info", "warning", "error"),
                        default="info")
    args, rest = parser.parse_known_args(argv)

    from dictatord.__main__ import main as daemon_main

    return daemon_main(["--log-level", args.log_level, *rest])


def restart(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="dictator restart",
                            description="Restart the daemon.").parse_args(argv)
    if shutil.which("systemctl"):
        unit_installed = (_unit_dir() / UNIT_NAME).is_file()
        if unit_installed:
            result = subprocess.run(["systemctl", "--user", "restart", UNIT_NAME],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                print(f"{fmt.OK} restarted")
                return 0
            print(fmt.yellow(f"{fmt.WARN} {result.stderr.strip()}"))

    try:
        client_run(lambda c: c.quit())
        print(f"{fmt.OK} asked the daemon to stop")
    except Fault:
        print("the daemon was not running")
    print(fmt.dim("  start it again with: dictator setup --install"))
    return 0


def quit_daemon(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="dictator quit",
                            description="Stop the daemon.").parse_args(argv)
    if shutil.which("systemctl") and (_unit_dir() / UNIT_NAME).is_file():
        subprocess.run(["systemctl", "--user", "stop", UNIT_NAME],
                       capture_output=True, check=False)
        print(f"{fmt.OK} stopped")
        return 0
    try:
        client_run(lambda c: c.quit())
    except Fault:
        print("the daemon was not running")
        return 0
    print(f"{fmt.OK} stopped")
    return 0


def reload(argv: list[str]) -> int:
    argparse.ArgumentParser(
        prog="dictator reload",
        description="Re-read configuration without restarting.",
    ).parse_args(argv)
    result = client_run(lambda c: c.reload())
    print(f"{fmt.OK} configuration reloaded ({result.get('files', '0')} file(s))")
    return 0
