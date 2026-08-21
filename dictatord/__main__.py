"""Daemon entry point: ``dictatord``."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import config as config_module
from .errors import Fault
from .logging import configure, get_logger

log = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dictatord",
        description="Dictator daemon. Normally started by systemd, not by hand.",
    )
    parser.add_argument("--config", type=Path, action="append", default=[],
                        help="Additional configuration file (repeatable).")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="Override one setting for this run (repeatable).")
    parser.add_argument("--log-level", choices=("debug", "info", "warning", "error"))
    parser.add_argument("--json-logs", action="store_true",
                        help="Force JSON log output.")
    parser.add_argument("--no-user-config", action="store_true",
                        help="Ignore the user configuration file.")
    return parser


def _overrides(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects KEY=VALUE, got: {pair}")
        key, _, value = pair.partition("=")
        out[key.strip()] = config_module.parse_value(key.strip(), value)
    return out


async def _run(cfg) -> int:
    from .daemon import Daemon

    daemon = Daemon(cfg)
    try:
        await daemon.run()
    except Fault as fault:
        log.error(fault.message, code=fault.code.value, remedy=fault.remedy)
        try:
            await daemon.shutdown()
        except Exception:  # pragma: no cover - already failing
            pass
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure(args.log_level or "info", json_output=args.json_logs or None)

    try:
        cfg = config_module.load(
            extra_files=args.config,
            overrides=_overrides(args.set),
            use_user=not args.no_user_config,
        )
    except Fault as fault:
        log.error(fault.message, code=fault.code.value, remedy=fault.remedy)
        return 2

    if args.log_level is None:
        configure(cfg["log.level"], json_output=cfg["log.json"] or None)

    from .version import __version__

    log.info("starting dictator", version=__version__)
    try:
        return asyncio.run(_run(cfg))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
