"""``dictator config`` — view and change settings."""
from __future__ import annotations

import argparse

from dictatord import config as cfg
from dictatord.errors import Fault, FaultCode

from .. import format as fmt
from ..client import Client, call, is_running
from ..client import run as client_run


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator config", description="View and change settings."
    )
    sub = parser.add_subparsers(dest="action")

    listing = sub.add_parser("list", help="Every setting, its value, and where it came from.")
    listing.add_argument("prefix", nargs="?", default="", help="Only settings starting with this.")
    listing.add_argument("--changed", action="store_true", help="Only settings that differ from the default.")

    get = sub.add_parser("get", help="One setting's value.")
    get.add_argument("key")

    setter = sub.add_parser("set", help="Change a setting.")
    setter.add_argument("key")
    setter.add_argument("value")

    reset = sub.add_parser("reset", help="Return a setting to its default.")
    reset.add_argument("key")

    sub.add_parser("path", help="Where the configuration files are.")
    sub.add_parser("sample", help="Print a fully commented configuration file.")
    sub.add_parser("edit", help="Open the user configuration in $EDITOR.")

    args = parser.parse_args(argv)
    action = args.action or "list"

    if action == "list":
        return _list(getattr(args, "prefix", ""), getattr(args, "changed", False))
    if action == "get":
        return _get(args.key)
    if action == "set":
        return _set(args.key, args.value)
    if action == "reset":
        return _reset(args.key)
    if action == "path":
        return _path()
    if action == "sample":
        print(cfg.sample_toml(), end="")
        return 0
    if action == "edit":
        return _edit()
    parser.print_help()
    return 2


def _load() -> cfg.Config:
    return cfg.load()


def _list(prefix: str, changed_only: bool) -> int:
    config = _load()
    rows = []
    for field in cfg.SCHEMA:
        if prefix and not field.path.startswith(prefix):
            continue
        value = config[field.path]
        source = config.source(field.path)
        is_default = value == field.default
        if changed_only and is_default:
            continue
        rendered = _render(value)
        origin = fmt.dim("default") if is_default else fmt.cyan(source.split(":", 1)[0])
        rows.append([field.path, rendered, origin])
    if not rows:
        print("nothing matches" if prefix else "every setting is at its default")
        return 0
    print(fmt.table(rows, headers=("setting", "value", "from")))
    return 0


def _render(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else fmt.dim("(empty)")
    if value == "":
        return fmt.dim("(unset)")
    return str(value)


def _get(key: str) -> int:
    config = _load()
    if key not in cfg.BY_PATH:
        raise Fault(
            code=FaultCode.CONFIG_INVALID,
            message=f"unknown setting: {key}",
            remedy="List them: dictator config list",
        )
    print(_render(config[key]))
    return 0


def _set(key: str, raw: str) -> int:
    try:
        value = cfg.parse_value(key, raw)
    except cfg.ValidationError as exc:
        field = cfg.BY_PATH.get(key)
        remedy = "List settings: dictator config list"
        if field and field.choices:
            remedy = f"Valid values: {', '.join(str(c) for c in field.choices)}"
        raise Fault(code=FaultCode.CONFIG_INVALID, message=str(exc), remedy=remedy) from exc

    path = cfg.save_user({key: value})
    field = cfg.BY_PATH[key]
    if value == field.default:
        print(f"{fmt.OK} {key} reset to its default ({_render(value)})")
    else:
        print(f"{fmt.OK} {key} = {_render(value)}")
    print(fmt.dim(f"  written to {path}"))
    _nudge_reload(key)
    return 0


def _reset(key: str) -> int:
    if key not in cfg.BY_PATH:
        raise Fault(
            code=FaultCode.CONFIG_INVALID,
            message=f"unknown setting: {key}",
            remedy="List them: dictator config list",
        )
    cfg.save_user({key: cfg.BY_PATH[key].default})
    print(f"{fmt.OK} {key} reset to {_render(cfg.BY_PATH[key].default)}")
    _nudge_reload(key)
    return 0


def _nudge_reload(key: str) -> None:
    """Apply the change live where we can, and say so where we cannot."""
    import asyncio

    try:
        running = asyncio.run(is_running())
    except Exception:
        running = False
    if not running:
        return
    try:
        client_run(lambda c: c.reload())
        print(fmt.dim("  the running daemon reloaded its configuration"))
    except Fault:
        print(fmt.yellow("  restart the daemon to apply: dictator restart"))


def _path() -> int:
    user = cfg.user_config_path()
    site = cfg.site_config_path()
    print(fmt.kv([
        ("user", f"{user} {'' if user.is_file() else fmt.dim('(not created yet)')}"),
        ("site", f"{site} {'' if site.is_file() else fmt.dim('(not present)')}"),
        ("data", str(cfg.data_dir())),
        ("state", str(cfg.state_dir())),
        ("models", str(cfg.models_dir())),
    ]))
    return 0


def _edit() -> int:
    import os
    import subprocess

    path = cfg.user_config_path()
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cfg.sample_toml())
        path.chmod(0o600)
        print(fmt.dim(f"created {path}"))

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    try:
        subprocess.run([editor, str(path)], check=False)
    except OSError as exc:
        raise Fault(
            code=FaultCode.CONFIG_UNWRITABLE,
            message=f"could not launch {editor}: {exc}",
            remedy=f"Set $EDITOR, or edit {path} directly.",
        ) from exc

    try:
        cfg.load()
    except Fault as fault:
        print(fmt.fault(fault.code.value, fault.message, fault.remedy))
        return 1
    print(f"{fmt.OK} configuration is valid")
    _nudge_reload("")
    return 0
