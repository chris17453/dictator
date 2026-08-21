"""``dictator keys`` — view and change keyboard shortcuts."""
from __future__ import annotations

import argparse
import asyncio

from dictatord import config as cfg
from dictatord.daemon import SHORTCUT_DESCRIPTIONS
from dictatord.errors import Fault, FaultCode
from dictatord.platform.chords import Chord, ChordError, parse_optional, validate_usable

from .. import format as fmt
from ..client import is_running
from ..client import run as client_run


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator keys", description="View and change keyboard shortcuts."
    )
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("list", help="Show every shortcut.")

    setter = sub.add_parser("set", help="Change a shortcut.")
    setter.add_argument("shortcut", choices=sorted(SHORTCUT_DESCRIPTIONS))
    setter.add_argument("chord", help='For example: "Super+d". Use "" to unbind.')

    unset = sub.add_parser("unset", help="Unbind a shortcut.")
    unset.add_argument("shortcut", choices=sorted(SHORTCUT_DESCRIPTIONS))

    check = sub.add_parser("check", help="Validate a chord without binding it.")
    check.add_argument("chord")

    sub.add_parser("conflicts", help="Show chords the desktop has already taken.")

    args = parser.parse_args(argv)
    action = args.action or "list"

    if action == "list":
        return _list()
    if action == "set":
        return _set(args.shortcut, args.chord)
    if action == "unset":
        return _set(args.shortcut, "")
    if action == "check":
        return _check(args.chord)
    if action == "conflicts":
        return _conflicts()
    parser.print_help()
    return 2


def _list() -> int:
    config = cfg.load()
    rows = []
    for shortcut_id, description in SHORTCUT_DESCRIPTIONS.items():
        raw = config.get(f"shortcuts.{shortcut_id}", "") or ""
        chord = fmt.bold(str(Chord.parse(raw))) if raw else fmt.dim("(unbound)")
        rows.append([shortcut_id, chord, description])
    print(fmt.table(rows, headers=("shortcut", "chord", "what it does")))
    print()
    threshold = config["shortcuts.hold_threshold_ms"]
    print(fmt.dim(
        f"  Tap the dictate chord to toggle; hold it longer than {threshold} ms "
        f"to dictate only while held."
    ))
    return 0


def _set(shortcut_id: str, chord_text: str) -> int:
    chord = None
    if chord_text.strip():
        try:
            chord = Chord.parse(chord_text)
            validate_usable(chord)
        except ChordError as exc:
            raise Fault(
                code=FaultCode.SHORTCUT_BIND_FAILED,
                message=str(exc),
                remedy='Chords look like "Super+d" or "Ctrl+Shift+Space".',
            ) from exc
        taken = _taken_by_desktop(chord)
        if taken:
            print(fmt.yellow(f"{fmt.WARN} {chord} is already used by the desktop for: {taken}"))
            print(fmt.dim("  binding it anyway; the desktop will usually win"))

    key = f"shortcuts.{shortcut_id}"
    cfg.save_user({key: str(chord) if chord else ""})
    if chord:
        print(f"{fmt.OK} {shortcut_id} = {fmt.bold(str(chord))}")
    else:
        print(f"{fmt.OK} {shortcut_id} unbound")

    try:
        if asyncio.run(is_running()):
            client_run(lambda c: c.set_shortcut(shortcut_id, str(chord) if chord else ""))
            print(fmt.dim("  rebound in the running daemon"))
        else:
            print(fmt.dim("  takes effect when the daemon starts"))
    except Fault as fault:
        print(fmt.yellow(f"  {fault.message}"))
        if fault.remedy:
            print(fmt.dim(f"  {fault.remedy}"))
    return 0


def _check(chord_text: str) -> int:
    try:
        chord = Chord.parse(chord_text)
        validate_usable(chord)
    except ChordError as exc:
        print(fmt.fault("chord.invalid", str(exc), 'Chords look like "Super+d".'))
        return 1
    print(f"{fmt.OK} {fmt.bold(str(chord))} is a valid chord")
    print(fmt.kv([
        ("portal", chord.to_portal()),
        ("gnome", chord.to_gsettings()),
    ]))
    taken = _taken_by_desktop(chord)
    if taken:
        print(fmt.yellow(f"{fmt.WARN} already used by the desktop for: {taken}"))
        return 1
    print(f"{fmt.OK} not claimed by any desktop shortcut")
    return 0


def _desktop_bindings() -> dict[str, str]:
    """Every chord GNOME has bound, mapped to the action that owns it."""
    import shutil
    import subprocess

    if shutil.which("gsettings") is None:
        return {}
    schemas = (
        "org.gnome.desktop.wm.keybindings",
        "org.gnome.shell.keybindings",
        "org.gnome.settings-daemon.plugins.media-keys",
        "org.gnome.mutter.keybindings",
    )
    bindings: dict[str, str] = {}
    for schema in schemas:
        try:
            result = subprocess.run(
                ["gsettings", "list-recursively", schema],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            _schema, key, value = parts
            for token in _extract_chords(value):
                bindings.setdefault(token, key)
    return bindings


def _extract_chords(value: str) -> list[str]:
    import re

    return [m for m in re.findall(r"'(<[^']*>[^']*)'", value)]


def _taken_by_desktop(chord: Chord) -> str:
    """Return the desktop action that owns this chord, if any."""
    wanted = _normalise(chord.to_gsettings())
    for raw, action in _desktop_bindings().items():
        try:
            if _normalise(Chord.parse(raw).to_gsettings()) == wanted:
                return action
        except ChordError:
            continue
    return ""


def _normalise(text: str) -> str:
    return text.replace("<Primary>", "<Ctrl>").replace("<Control>", "<Ctrl>").lower()


def _conflicts() -> int:
    bindings = _desktop_bindings()
    if not bindings:
        print("could not read the desktop's shortcuts (is this GNOME?)")
        return 0
    config = cfg.load()
    ours = {}
    for shortcut_id in SHORTCUT_DESCRIPTIONS:
        raw = config.get(f"shortcuts.{shortcut_id}", "") or ""
        chord = parse_optional(raw)
        if chord:
            ours[shortcut_id] = chord

    clashes = []
    for shortcut_id, chord in ours.items():
        action = _taken_by_desktop(chord)
        if action:
            clashes.append([shortcut_id, str(chord), action])

    if clashes:
        print(fmt.table(clashes, headers=("our shortcut", "chord", "desktop uses it for")))
        print()
        print(fmt.yellow("  Pick a different chord: dictator keys set <shortcut> <chord>"))
        return 1

    print(f"{fmt.OK} none of our shortcuts clash with the desktop's "
          f"({len(bindings)} desktop bindings checked)")
    return 0
