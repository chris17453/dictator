"""``dictator devices`` — list and choose the microphone."""
from __future__ import annotations

import argparse
import asyncio

from dictatord import config as cfg
from dictatord.audio import devices
from dictatord.errors import Fault

from .. import format as fmt
from ..client import is_running
from ..client import run as client_run


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator devices", description="List and choose the microphone."
    )
    sub = parser.add_subparsers(dest="action")

    sub.add_parser("list", help="Every input device.")

    setter = sub.add_parser("set", help="Use a device. Matches on name or description.")
    setter.add_argument("query")

    sub.add_parser("cycle", help="Move to the next device. Bindable to a shortcut.")
    sub.add_parser("default", help="Go back to the system default device.")

    args = parser.parse_args(argv)
    action = args.action or "list"

    if action == "list":
        return _list()
    if action == "set":
        return _set(args.query)
    if action == "cycle":
        return _cycle()
    if action == "default":
        return _set("")
    parser.print_help()
    return 2


def _active() -> str:
    try:
        if asyncio.run(is_running()):
            return client_run(lambda c: c.state()).get("device", "")
    except Fault:
        pass
    return cfg.load()["audio.device"]


def _list() -> int:
    found = devices.enumerate_devices()
    if not found:
        print("no input devices are present")
        print(fmt.dim("  connect a microphone, then run this again"))
        return 1

    active = _active()
    rows = []
    for device in found:
        marker = fmt.green("●") if device.name == active else " "
        tags = []
        if device.is_default:
            tags.append(fmt.dim("system default"))
        rows.append([
            marker,
            fmt.bold(device.name) if device.name == active else device.name,
            device.description[:44],
            f"{device.channels}ch",
            " ".join(tags),
        ])
    print(fmt.table(rows, headers=("", "name", "description", "", "")))
    if not active:
        print()
        print(fmt.dim("  no device chosen; the system default is used"))
    return 0


def _set(query: str) -> int:
    device = devices.resolve(query) if query else None
    name = device.name if device else ""

    if asyncio.run(is_running()):
        chosen = client_run(lambda c: c.set_device(name))
        print(f"{fmt.OK} now using {fmt.bold(chosen or 'the system default')}")
        return 0

    cfg.save_user({"audio.device": name})
    print(f"{fmt.OK} device set to {fmt.bold(name or 'the system default')}")
    print(fmt.dim("  takes effect when the daemon starts"))
    return 0


def _cycle() -> int:
    found = devices.enumerate_devices()
    if len(found) < 2:
        print("only one input device; nothing to cycle to")
        return 0
    active = _active()
    names = [d.name for d in found]
    try:
        index = names.index(active)
    except ValueError:
        index = -1
    return _set(names[(index + 1) % len(names)])
