"""Dictation control and status."""
from __future__ import annotations

import argparse
import asyncio

from dictatord.errors import Fault

from .. import format as fmt
from ..client import Client, call, run


def toggle(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dictator toggle",
                                     description="Start dictating, or stop and deliver.")
    parser.add_argument("--profile", default="", metavar="NAME",
                        help="Delivery profile: standard, terminal, clipboard-only.")
    args = parser.parse_args(argv)

    session_id = run(lambda c: c.toggle(args.profile))
    print("listening" if session_id else "stopped")
    return 0


def start(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dictator start",
                                     description="Start dictating. Does nothing if already listening.")
    parser.add_argument("--profile", default="", metavar="NAME")
    args = parser.parse_args(argv)
    session_id = run(lambda c: c.push_begin(args.profile))
    print(f"listening (session {session_id})")
    return 0


def stop(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="dictator stop",
                            description="Stop dictating and deliver.").parse_args(argv)
    session_id = run(lambda c: c.push_end())
    print("stopped" if session_id else "was not listening")
    return 0


def cancel(argv: list[str]) -> int:
    argparse.ArgumentParser(prog="dictator cancel",
                            description="Discard the dictation in progress.").parse_args(argv)
    cancelled = run(lambda c: c.cancel())
    print("discarded" if cancelled else "nothing in progress")
    return 0


def again(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dictator again",
                                     description="Deliver a stored transcript again.")
    parser.add_argument("id", nargs="?", type=int, default=0,
                        help="Transcript id; defaults to the most recent.")
    parser.add_argument("--profile", default="", metavar="NAME")
    args = parser.parse_args(argv)
    ok = run(lambda c: c.redeliver(args.id, args.profile))
    print("delivered" if ok else "delivery failed; the text is on the clipboard")
    return 0 if ok else 1


def push(argv: list[str]) -> int:
    """Hold-to-talk for scripts: record for as long as this command runs."""
    parser = argparse.ArgumentParser(
        prog="dictator push",
        description="Dictate while this command runs. Stops on Ctrl-C or after --seconds.",
    )
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="Stop automatically after this long.")
    parser.add_argument("--profile", default="", metavar="NAME")
    args = parser.parse_args(argv)

    async def hold(client: Client) -> int:
        await client.push_begin(args.profile)
        print("listening — press Ctrl-C to stop", flush=True)
        try:
            if args.seconds:
                await asyncio.sleep(args.seconds)
            else:
                await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await client.push_end()
        print("stopped")
        return 0

    try:
        return asyncio.run(call(hold))
    except KeyboardInterrupt:
        # Make sure the daemon is not left recording if we were interrupted
        # between connect and the handler's own cleanup.
        try:
            run(lambda c: c.push_end())
        except Fault:
            pass
        return 0


def status(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="dictator status",
                                     description="What the daemon is doing right now.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    args = parser.parse_args(argv)

    state = run(lambda c: c.state())

    if args.json:
        import json

        print(json.dumps(state, indent=2, sort_keys=True))
        return 0

    listening = state.get("state") == "listening"
    print(f"{fmt.bold('state')}      {fmt.green(state.get('state','?')) if listening else state.get('state','?')}")
    print()
    print(fmt.kv([
        ("session", f"{state.get('session','?')} ({state.get('desktop') or 'unknown desktop'})"),
        ("shortcuts", _backend_line(state, "shortcut_backend", "shortcuts_ready")),
        ("injection", _backend_line(state, "injection_backend", "injection_ready")),
        ("clipboard", state.get("clipboard", "?")),
        ("hold to talk", state.get("hold_to_talk", "?")),
    ]))
    print()
    print(fmt.kv([
        ("model", f"{state.get('model','?')} on {state.get('model_device','?')}"
                  f" ({state.get('model_compute_type','?')})"),
        ("loaded", state.get("model_loaded", "?")),
        ("integrity", state.get("model_integrity", "?")),
    ]))
    print()
    device = state.get("device") or "(none)"
    capturing = state.get("capturing", "False") == "True"
    print(fmt.kv([
        ("microphone", f"{device} {'' if capturing else fmt.yellow('- not capturing')}"),
        ("transcripts", state.get("transcripts", "0")),
        ("lexicon", f"{state.get('lexicon_terms','0')} terms"),
        ("uptime", fmt.duration(float(state.get("uptime_s", 0)))),
    ]))
    return 0


def _backend_line(state: dict, key: str, ready_key: str) -> str:
    name = state.get(key, "none")
    ready = state.get(ready_key, "False") == "True"
    if name == "none":
        return fmt.yellow("none")
    return f"{name} {'' if ready else fmt.yellow('- not active, see: dictator doctor')}"
