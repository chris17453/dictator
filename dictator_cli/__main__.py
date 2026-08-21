"""``dictator`` — the command-line client.

A thin subscriber to the daemon's D-Bus contract, plus the few things that are
genuinely local: configuration files, model files, and installation.
"""
from __future__ import annotations

import argparse
import sys

from dictatord.errors import Fault
from dictatord.logging import configure
from dictatord.version import __version__

from . import format as fmt
from .commands import (
    config_cmd,
    devices_cmd,
    doctor_cmd,
    history_cmd,
    keys_cmd,
    lexicon_cmd,
    models_cmd,
    service_cmd,
    session_cmd,
    stats_cmd,
    watch_cmd,
)

COMMANDS = {
    # dictation
    "toggle": session_cmd.toggle,
    "start": session_cmd.start,
    "stop": session_cmd.stop,
    "push": session_cmd.push,
    "cancel": session_cmd.cancel,
    "again": session_cmd.again,
    # inspection
    "status": session_cmd.status,
    "doctor": doctor_cmd.run,
    "stats": stats_cmd.stats,
    "health": stats_cmd.health,
    "meter": watch_cmd.meter,
    "watch": watch_cmd.watch,
    # configuration
    "config": config_cmd.run,
    "keys": keys_cmd.run,
    "devices": devices_cmd.run,
    "models": models_cmd.run,
    "lexicon": lexicon_cmd.run,
    # memory
    "history": history_cmd.history,
    "search": history_cmd.search,
    # service control
    "setup": service_cmd.setup,
    "grant": service_cmd.grant,
    "daemon": service_cmd.daemon,
    "restart": service_cmd.restart,
    "quit": service_cmd.quit_daemon,
    "reload": service_cmd.reload,
}

USAGE = """dictator — speech to text, without a window

  dictation
    toggle              start dictating, or stop and deliver
    start / stop        explicit control, for scripts
    push                dictate while this command runs (hold-to-talk)
    cancel              discard what is being dictated
    again               deliver the last transcript again

  inspection
    status              what the daemon is doing right now
    doctor              check every dependency and say what to fix
    stats               counters and measured latency percentiles
    health              one-line verdict for monitoring (exit code)
    meter               live input levels in the terminal
    watch               live transcription as you speak

  configuration
    config              view and change settings
    keys                view and change keyboard shortcuts
    devices             list and choose the microphone
    models              list, download, and switch speech models
    lexicon             words the recogniser should know

  memory
    history             recent transcripts
    search TEXT         find a past transcript

  service
    setup               install the service and shortcuts
    grant               ask again for a declined permission
    daemon              run the daemon in the foreground
    restart / quit      control a running daemon
    reload              re-read configuration without restarting

Run 'dictator COMMAND --help' for detail on any command.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dictator", add_help=False, usage=argparse.SUPPRESS
    )
    parser.add_argument("command", nargs="?", default=None)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parser.add_argument("-h", "--help", action="store_true", dest="want_help")
    parser.add_argument("-V", "--version", action="store_true", dest="want_version")
    parser.add_argument("--debug", action="store_true", help="Verbose logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)

    configure("debug" if args.debug else "warning")

    if args.want_version:
        print(f"dictator {__version__}")
        return 0

    command = args.command
    if command is None or (args.want_help and command is None):
        print(USAGE)
        return 0

    handler = COMMANDS.get(command)
    if handler is None:
        matches = [name for name in COMMANDS if name.startswith(command)]
        if len(matches) == 1:
            handler = COMMANDS[matches[0]]
        else:
            print(f"{fmt.BAD} unknown command: {command}", file=sys.stderr)
            if matches:
                print(f"  did you mean: {', '.join(sorted(matches))}", file=sys.stderr)
            else:
                print("  run 'dictator' to see what is available", file=sys.stderr)
            return 2

    rest = [a for a in args.args if a != "--debug"]
    if args.want_help:
        rest = rest + ["--help"]

    try:
        return handler(rest) or 0
    except Fault as fault:
        print(fmt.fault(fault.code.value, fault.message, fault.remedy), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:  # pragma: no cover - piping into head, etc.
        return 0


if __name__ == "__main__":
    sys.exit(main())
