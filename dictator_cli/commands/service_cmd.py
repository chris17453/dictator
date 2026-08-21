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
import glob
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
# These belong to the unit, not the service; systemd ignores them under
# [Service] and the daemon would restart forever.
StartLimitBurst=5
StartLimitIntervalSec=60

[Service]
Type=simple
ExecStart={_executable()}
Restart=on-failure
RestartSec=2
Slice=app.slice
# The portal reads our identity from this unit's name; changing it breaks
# global shortcuts on GNOME.
Environment=PYTHONUNBUFFERED=1
# Let an utterance already being transcribed finish before we are killed.
TimeoutStopSec=30
KillSignal=SIGTERM

# --- sandboxing -------------------------------------------------------
# This process listens to a microphone and can type into other windows, so
# it is worth confining. Audio, the session bus, and the portal must still
# work, which is what rules out the stricter options below each line.
NoNewPrivileges=yes
PrivateTmp=yes
# Transcripts and the portal token are private to the user.
UMask=0077
ProtectSystem=strict
ProtectHome=read-only
# Our own state must stay writable despite ProtectSystem=strict. The leading
# dash keeps a missing directory from failing the mount namespace outright.
ReadWritePaths=-%h/.local/share/dictator
ReadWritePaths=-%h/.local/state/dictator
ReadWritePaths=-%h/.config/dictator
ReadWritePaths=-%h/.cache/huggingface
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
ProtectProc=invisible
RestrictSUIDSGID=yes
RestrictRealtime=no
RestrictNamespaces=yes
LockPersonality=yes
RemoveIPC=yes
# PrivateDevices=yes would remove /dev/snd and the GPU; both are needed.
DeviceAllow=char-alsa rw
DeviceAllow=/dev/nvidiactl rw
DeviceAllow=/dev/nvidia0 rw
DeviceAllow=/dev/nvidia-uvm rw
# AF_UNIX for the bus and PipeWire; INET only for model downloads.
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM
SystemCallArchitectures=native
# Whisper on a GPU is memory-hungry; this is a runaway guard, not a target.
MemoryMax=8G

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
    parser.add_argument("--no-portal", action="store_true",
                        help="Grant direct device access so nothing ever prompts. Needs sudo.")
    parser.add_argument("--revoke-device-access", action="store_true",
                        help="Undo --no-portal.")
    args = parser.parse_args(argv)

    if args.uninstall:
        return _uninstall()
    if args.revoke_device_access:
        return _revoke_devices()
    if args.no_portal:
        return _grant_devices()
    if args.install:
        return _install(args.force)
    return _explain()


def _evdev_install_hints() -> list[str]:
    """Package-manager commands for this distribution, best first.

    Building the C extension needs headers and a compiler; the distribution
    package needs neither, so it is the better answer nearly everywhere.
    """
    import shutil

    if shutil.which("dnf"):
        return ["sudo dnf install python3-evdev"]
    if shutil.which("apt-get"):
        return ["sudo apt install python3-evdev"]
    if shutil.which("pacman"):
        return ["sudo pacman -S python-evdev"]
    if shutil.which("zypper"):
        return ["sudo zypper install python3-evdev"]
    return ["pip install evdev  (needs a compiler and Python headers)"]


UDEV_RULE_PATH = "/etc/udev/rules.d/70-dictator.rules"

def _udev_rule(user: str, setfacl: str) -> str:
    """The udev rule, naming the user who ran setup.

    Three approaches were considered and two rejected:

    * ``TAG+="uaccess"`` grants only to a session attached to a seat. A remote
      session has no seat, so it grants nothing.
    * ``GROUP="input"`` alone works, but group membership only reaches
      processes started after a fresh login — so a keyboard plugged in today
      would not work until the user logged out and back in.

    An explicit ACL applies immediately and to devices that appear later,
    which is what a daemon needs. It names one user, which is the honest
    trade for a rule that lives in /etc.
    """
    return f"""# dictator - prompt-free input access for {user}.
#
# Reading /dev/input/event* is a keylogging capability; writing /dev/uinput is
# an input-injection one. Remove this file to revoke both:
#   dictator setup --revoke-device-access
KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660", \
  OPTIONS+="static_node=uinput", RUN+="{setfacl} -m u:{user}:rw /dev/uinput"
KERNEL=="event*", SUBSYSTEM=="input", GROUP="input", MODE="0660", \
  RUN+="{setfacl} -m u:{user}:rw $env{{DEVNAME}}"
"""


def _grant_devices() -> int:
    """Give the daemon direct input access, so no portal prompt is ever needed."""
    import getpass

    user = getpass.getuser()

    print(fmt.bold("What this grants, and what it costs"))
    print()
    print("  Reading /dev/input/event*  a keylogging capability")
    print("  Writing /dev/uinput        an input-injection capability")
    print()
    print("  Any process running as you gains both. That is the same power an")
    print("  X11 client has by default, and what ydotool and similar tools")
    print("  require. In exchange, nothing ever prompts and hold-to-talk works.")
    print()

    try:
        import evdev  # noqa: F401
    except ImportError:
        print(f"{fmt.BAD} the evdev package is not installed, so these backends "
              f"cannot be used")
        print()
        print("  evdev is a C extension, which is why it is optional. Your")
        print("  distribution almost certainly packages it already, which avoids")
        print("  needing a compiler at all:")
        print()
        for command in _evdev_install_hints():
            print(f"    {fmt.bold(command)}")
        print()
        print(fmt.dim("  or build it: pip install 'the-dictator[no-portal]'"))
        print(fmt.dim("  granting device access without it would achieve nothing"))
        return 1

    if shutil.which("sudo") is None:
        print(f"{fmt.BAD} sudo is not available; run these as root yourself:")
        print(fmt.dim(f"  printf '%s' '{UDEV_RULE}' > {UDEV_RULE_PATH}"))
        print(fmt.dim(f"  udevadm control --reload-rules && udevadm trigger"))
        print(fmt.dim(f"  usermod -aG input {user}"))
        return 1

    setfacl = shutil.which("setfacl") or "/usr/bin/setfacl"
    if not os.path.exists(setfacl):
        print(f"{fmt.BAD} setfacl is missing; install acl: sudo dnf install acl")
        return 1

    steps = [
        (["sudo", "tee", UDEV_RULE_PATH], "install the udev rule",
         _udev_rule(user, setfacl)),
        (["sudo", "udevadm", "control", "--reload-rules"], "reload udev rules", None),
        (["sudo", "udevadm", "trigger", "--subsystem-match=input",
          "--subsystem-match=misc"], "apply them to existing devices", None),
        (["sudo", "usermod", "-aG", "input", user], f"add {user} to the input group", None),
    ]
    for command, what, stdin in steps:
        result = subprocess.run(command, input=stdin, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{fmt.BAD} could not {what}: {result.stderr.strip()}")
            return 1
        print(f"{fmt.OK} {what}")

    # The rule covers devices that appear from now on. Existing ones were
    # created before it existed, so grant those directly.
    granted = 0
    for path in ["/dev/uinput", *glob.glob("/dev/input/event*")]:
        if subprocess.run(["sudo", "setfacl", "-m", f"u:{user}:rw", path],
                          capture_output=True).returncode == 0:
            granted += 1
    if granted:
        print(f"{fmt.OK} granted this session access to {granted} device(s)")

    ok_uinput = os.access("/dev/uinput", os.W_OK)
    readable = sum(1 for p in glob.glob("/dev/input/event*") if os.access(p, os.R_OK))
    print()
    print(fmt.kv([
        ("/dev/uinput", fmt.OK + " writable" if ok_uinput else fmt.BAD + " not writable"),
        ("input devices", f"{readable} readable"),
    ]))
    if not ok_uinput or not readable:
        print()
        print(fmt.yellow(f"{fmt.WARN} log out and back in for group membership to take effect"))
        return 1

    print()
    print(f"{fmt.OK} the daemon will now use the evdev and uinput backends")
    print(fmt.dim("  restart it to pick them up: dictator restart"))
    return 0


def _revoke_devices() -> int:
    import getpass

    user = getpass.getuser()
    if shutil.which("sudo") is None:
        print(f"{fmt.BAD} sudo is not available")
        return 1
    subprocess.run(["sudo", "rm", "-f", UDEV_RULE_PATH], capture_output=True)
    subprocess.run(["sudo", "gpasswd", "-d", user, "input"], capture_output=True)
    subprocess.run(["sudo", "udevadm", "control", "--reload-rules"], capture_output=True)
    subprocess.run(["sudo", "udevadm", "trigger", "--subsystem-match=input",
                    "--subsystem-match=misc"], capture_output=True)
    print(f"{fmt.OK} device access revoked; the daemon will fall back to the portal")
    print(fmt.dim("  log out and back in to drop the group from running sessions"))
    return 0


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

    # The unit confines itself with ProtectSystem=strict, so the directories it
    # is allowed to write must exist before systemd builds the namespace.
    for directory in (cfg.data_dir(), cfg.state_dir(), cfg.models_dir(),
                      cfg.user_config_path().parent):
        directory.mkdir(parents=True, exist_ok=True)

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


def grant(argv: list[str]) -> int:
    """Re-ask for a permission the user previously declined or ignored."""
    parser = argparse.ArgumentParser(
        prog="dictator grant",
        description="Ask again for a permission that was declined or left unanswered.",
    )
    parser.add_argument("permission", nargs="?", default="all",
                        choices=["all", "shortcuts", "injection"])
    args = parser.parse_args(argv)

    from dictatord.consent import ConsentLedger

    ledger = ConsentLedger(cfg.state_dir() / "consent.json").load()
    before = ledger.summary()
    ledger.reset(None if args.permission == "all" else args.permission)

    print(f"{fmt.OK} will ask again for: "
          f"{'both permissions' if args.permission == 'all' else args.permission}")
    for key, decision in before.items():
        if decision != "unasked":
            print(fmt.dim(f"  {key} was {decision}"))
    print()
    print(f"  Restart to trigger the prompt: {fmt.bold('dictator restart')}")
    print(fmt.dim("  Or avoid prompts entirely: dictator setup --no-portal"))
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
