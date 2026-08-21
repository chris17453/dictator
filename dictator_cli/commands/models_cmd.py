"""``dictator models`` — list, download, and switch speech models."""
from __future__ import annotations

import argparse
import asyncio

from dictatord import config as cfg
from dictatord.asr import models
from dictatord.errors import Fault, FaultCode

from .. import format as fmt
from ..client import is_running
from ..client import run as client_run


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator models", description="List, download, and switch speech models."
    )
    sub = parser.add_subparsers(dest="action")

    listing = sub.add_parser("list", help="Every model, with what is on disk.")
    listing.add_argument("--all", action="store_true", help="Include English-only variants.")

    setter = sub.add_parser("set", help="Switch to a model, downloading it if needed.")
    setter.add_argument("name")
    setter.add_argument("--device", choices=("auto", "cuda", "cpu"))
    setter.add_argument("--compute-type",
                        choices=("auto", "int8", "int8_float16", "float16", "float32"))

    download = sub.add_parser("download", help="Fetch a model without switching to it.")
    download.add_argument("name")

    remove = sub.add_parser("remove", help="Delete a model from disk.")
    remove.add_argument("name")

    trust = sub.add_parser("trust", help="Record the current weights as the expected ones.")
    trust.add_argument("name")

    sub.add_parser("current", help="Which model is in use.")

    args = parser.parse_args(argv)
    action = args.action or "list"

    if action == "list":
        return _list(getattr(args, "all", False))
    if action == "set":
        return _set(args.name, args.device, args.compute_type)
    if action == "download":
        return _download(args.name)
    if action == "remove":
        return _remove(args.name)
    if action == "trust":
        return _trust(args.name)
    if action == "current":
        return _current()
    parser.print_help()
    return 2


def _resolved_default() -> models.Resolution:
    config = cfg.load()
    return models.resolve(
        config["model.name"], config["model.device"], config["model.compute_type"]
    )


def _list(show_all: bool) -> int:
    root = cfg.models_dir()
    try:
        active = _active_model()
    except Fault:
        active = _resolved_default().model

    rows = []
    for spec in models.CATALOG:
        if not show_all and spec.is_english_only:
            continue
        downloaded = models.is_downloaded(root, spec.name)
        marker = fmt.green("●") if spec.name == active else " "
        on_disk = fmt.size(models.disk_usage(root, spec.name)) if downloaded else fmt.dim(f"~{spec.approx_mb} MB")
        rows.append([
            marker,
            fmt.bold(spec.name) if spec.name == active else spec.name,
            spec.parameters,
            on_disk,
            fmt.OK if downloaded else fmt.dim("—"),
            spec.note,
        ])
    print(fmt.table(rows, headers=("", "model", "params", "size", "local", "notes")))
    print()
    if not show_all:
        print(fmt.dim("  --all also lists the English-only variants"))
    print(fmt.dim(f"  stored in {root}"))
    return 0


def _active_model() -> str:
    if not asyncio.run(is_running()):
        raise Fault(
            code=FaultCode.INTERNAL, message="daemon not running", remedy=""
        )
    state = client_run(lambda c: c.state())
    return state.get("model", "")


def _set(name: str, device: str | None, compute_type: str | None) -> int:
    if name != "auto":
        models.spec_for(name)

    root = cfg.models_dir()
    if name != "auto" and not models.is_downloaded(root, name):
        spec = models.spec_for(name)
        print(f"downloading {fmt.bold(name)} (~{spec.approx_mb} MB) from {spec.repo}…")
        models.download(root, name)
        print(f"{fmt.OK} downloaded")

    updates = {"model.name": name}
    if device:
        updates["model.device"] = device
    if compute_type:
        updates["model.compute_type"] = compute_type
    cfg.save_user(updates)

    if asyncio.run(is_running()):
        try:
            result = client_run(
                lambda c: c.set_model(name, device=device or "", compute_type=compute_type or "")
            )
            print(f"{fmt.OK} now using {fmt.bold(result['model'])} on {result['device']} "
                  f"({result['compute_type']})")
            return 0
        except Fault as fault:
            print(fmt.fault(fault.code.value, fault.message, fault.remedy))
            return 1

    resolution = _resolved_default()
    print(f"{fmt.OK} model set to {fmt.bold(resolution.model)} on {resolution.device} "
          f"({resolution.compute_type})")
    print(fmt.dim("  takes effect when the daemon starts"))
    return 0


def _download(name: str) -> int:
    spec = models.spec_for(name)
    root = cfg.models_dir()
    if models.is_downloaded(root, name):
        print(f"{fmt.OK} {name} is already downloaded "
              f"({fmt.size(models.disk_usage(root, name))})")
        return 0
    print(f"downloading {fmt.bold(name)} (~{spec.approx_mb} MB) from {spec.repo}…")
    models.download(root, name)
    print(f"{fmt.OK} {name} downloaded ({fmt.size(models.disk_usage(root, name))})")
    return 0


def _remove(name: str) -> int:
    root = cfg.models_dir()
    models.spec_for(name)
    if not models.is_downloaded(root, name):
        print(f"{name} is not downloaded")
        return 0
    freed = models.disk_usage(root, name)
    models.remove(root, name)
    print(f"{fmt.OK} removed {name}, freeing {fmt.size(freed)}")
    return 0


def _trust(name: str) -> int:
    root = cfg.models_dir()
    models.spec_for(name)
    if not models.is_downloaded(root, name):
        raise Fault(
            code=FaultCode.MODEL_NOT_FOUND,
            message=f"{name} is not downloaded, so there is nothing to trust",
            remedy=f"Download it first: dictator models download {name}",
        )
    digest = models.trust(root, name)
    print(f"{fmt.OK} recorded the current weights for {name}")
    print(fmt.dim(f"  sha256:{digest}"))
    return 0


def _current() -> int:
    try:
        state = client_run(lambda c: c.state())
        print(fmt.kv([
            ("model", state.get("model", "?")),
            ("device", state.get("model_device", "?")),
            ("compute type", state.get("model_compute_type", "?")),
            ("loaded", state.get("model_loaded", "?")),
            ("integrity", state.get("model_integrity", "?")),
        ]))
        return 0
    except Fault:
        resolution = _resolved_default()
        print(fmt.kv([
            ("model", resolution.model),
            ("device", resolution.device),
            ("compute type", resolution.compute_type),
            ("why", resolution.reason),
        ]))
        print(fmt.dim("\n  the daemon is not running; this is what it would choose"))
        return 0
