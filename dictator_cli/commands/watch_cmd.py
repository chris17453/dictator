"""``dictator meter`` and ``dictator watch`` — live views in the terminal.

Both are pure subscribers to signals the daemon emits anyway. That is the point
of the design: a level check or a look at live transcription needs no graphical
session at all (v2.md §4.5).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from dictatord.errors import Fault

from .. import format as fmt
from ..client import Client, call


def meter(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator meter", description="Live input levels. Ctrl-C to stop."
    )
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--plain", action="store_true", help="One line per update, no redraw.")
    args = parser.parse_args(argv)

    async def watch_levels(client: Client) -> int:
        state = await client.state()
        if state.get("capturing", "False") != "True":
            print(fmt.yellow(f"{fmt.WARN} the daemon is not capturing audio"))
            print(fmt.dim("  check the microphone: dictator devices"))

        stop = asyncio.Event()
        peak_hold = {"value": 0.0}

        def on_level(peak: float, rms: float, clipping: bool, bands) -> None:
            peak_hold["value"] = max(peak, peak_hold["value"] * 0.95)
            bar = fmt.meter_bar(rms, args.width)
            spec = fmt.spectrum(bands)
            clip = fmt.red(" CLIP") if clipping else ""
            line = (
                f"{bar} {fmt.dim('rms')} {rms:5.3f} "
                f"{fmt.dim('peak')} {peak_hold['value']:5.3f} {spec}{clip}"
            )
            if args.plain:
                print(line, flush=True)
            else:
                sys.stdout.write("\r\033[K" + line)
                sys.stdout.flush()

        client.on_level(on_level)
        print(fmt.dim("listening for levels — Ctrl-C to stop"))
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass
        return 0

    try:
        return asyncio.run(call(watch_levels))
    except KeyboardInterrupt:
        print()
        return 0


def watch(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator watch",
        description="Live transcription as you speak. Ctrl-C to stop.",
    )
    parser.add_argument("--levels", action="store_true", help="Also show the input level.")
    args = parser.parse_args(argv)

    async def watch_all(client: Client) -> int:
        stop = asyncio.Event()

        def on_state(state: str, detail) -> None:
            colour = fmt.green if state == "listening" else fmt.dim
            sys.stdout.write("\r\033[K")
            print(colour(f"— {state} —"), flush=True)

        def on_partial(session_id: int, text: str, stable_chars: int) -> None:
            # Stable text is settled; the tail may still be revised, so it is
            # dimmed rather than presented as final.
            settled = text[:stable_chars]
            tail = text[stable_chars:]
            sys.stdout.write("\r\033[K" + settled + fmt.dim(tail))
            sys.stdout.flush()

        def on_final(session_id: int, text: str, confidence: float) -> None:
            sys.stdout.write("\r\033[K")
            mark = fmt.green("●") if confidence >= 0.7 else fmt.yellow("●")
            print(f"{mark} {text}  {fmt.dim(f'({confidence:.0%})')}", flush=True)

        def on_delivered(session_id: int, method: str, app_id: str, ok: bool) -> None:
            target = app_id or "the focused window"
            note = f"{method} → {target}" if ok else f"{method} failed"
            print(fmt.dim(f"  {note}"), flush=True)

        def on_fault(code: str, message: str, remedy: str) -> None:
            sys.stdout.write("\r\033[K")
            print(fmt.fault(code, message, remedy), flush=True)

        client.on_state_changed(on_state)
        client.on_partial(on_partial)
        client.on_final(on_final)
        client.on_delivered(on_delivered)
        client.on_fault(on_fault)

        if args.levels:
            def on_level(peak: float, rms: float, clipping: bool, bands) -> None:
                sys.stdout.write("\r\033[K" + fmt.meter_bar(rms, 24))
                sys.stdout.flush()

            client.on_level(on_level)

        state = await client.state()
        print(fmt.dim(f"watching — {state.get('model','?')} on "
                      f"{state.get('model_device','?')} — Ctrl-C to stop"))
        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass
        return 0

    try:
        return asyncio.run(call(watch_all))
    except KeyboardInterrupt:
        print()
        return 0
