"""``dictator stats`` and ``dictator health`` — what the daemon has measured.

v2.md §7 states acceptance targets as percentiles. This is where you find out
whether they are being met on your machine rather than in a claim.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from dictatord.errors import Fault
from dictatord.metrics import flatten

from .. import format as fmt
from ..client import run as client_run


def stats(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator stats",
        description="Counters and latency percentiles measured by the daemon.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument("--prometheus", action="store_true",
                        help="Prometheus text exposition format.")
    args = parser.parse_args(argv)

    snapshot = client_run(lambda c: c.metrics())

    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0
    if args.prometheus:
        for name, value in flatten(snapshot):
            print(f"{name} {value:g}")
        return 0

    status = snapshot.get("health", "unknown")
    colour = fmt.green if status == "healthy" else fmt.yellow
    uptime = fmt.duration(float(snapshot.get("uptime_s", 0)))
    print(f"{fmt.bold('health')}  {colour(status)}  {fmt.dim('up ' + uptime)}")
    for problem in snapshot.get("problems", []):
        print(f"  {fmt.WARN} {problem}")
    print()

    counters = snapshot.get("counters", {})
    print(fmt.bold("sessions"))
    print(fmt.kv([
        ("started", str(counters.get("sessions_started", 0))),
        ("delivered", str(counters.get("sessions_delivered", 0))),
        ("cancelled", str(counters.get("sessions_cancelled", 0))),
        ("nothing heard", str(counters.get("sessions_empty", 0))),
    ]))

    deliveries = snapshot.get("deliveries", {})
    if deliveries:
        print()
        print(fmt.bold("delivery"))
        rows = []
        for method, count in sorted(deliveries.items()):
            failed = method.endswith(":failed")
            label = fmt.red(method) if failed else method
            rows.append([label, str(count)])
        print(fmt.table(rows))

    faults = snapshot.get("faults", {})
    if faults:
        print()
        print(fmt.bold("faults"))
        rows = [[fmt.yellow(code), str(count)]
                for code, count in sorted(faults.items(), key=lambda kv: -kv[1])]
        print(fmt.table(rows))

    print()
    print(fmt.bold("latency"))
    rows = []
    for name, values in snapshot.get("latency", {}).items():
        if not values.get("count"):
            rows.append([name, fmt.dim("no samples"), "", "", "", ""])
            continue
        rows.append([
            name,
            str(values["count"]),
            f"{values['p50']:g}",
            f"{values['p95']:g}",
            f"{values['p99']:g}",
            f"{values['max']:g} {values.get('unit','ms')}",
        ])
    print(fmt.table(rows, headers=("", "n", "p50", "p95", "p99", "max")))

    print()
    print(fmt.bold("against the acceptance targets"))
    print(_targets_table(snapshot))
    return 0


def _targets_table(snapshot: dict) -> str:
    """Recompute the v2.md budgets from the reported percentiles."""
    budgets = [
        ("partial latency", "partial", 500.0),
        ("delivery latency", "delivery", 700.0),
        ("end-to-end", "end_to_end", 1200.0),
    ]
    rows = []
    for label, key, budget in budgets:
        values = snapshot.get("latency", {}).get(key, {})
        count = values.get("count", 0)
        if count < 5:
            rows.append([
                label, fmt.dim("unknown"), fmt.dim(f"{count} sample(s)"),
                fmt.dim(f"budget {budget:g} ms"),
            ])
            continue
        measured = values.get("p95", 0)
        ok = measured <= budget
        rows.append([
            label,
            fmt.OK if ok else fmt.BAD,
            f"p95 {measured:g} ms",
            fmt.dim(f"budget {budget:g} ms"),
        ])
    return fmt.table(rows)


def health(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dictator health",
        description="One-line verdict for monitoring. Exits non-zero when degraded.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = client_run(lambda c: c.health())
    except Fault as fault:
        if args.json:
            print(json.dumps({"status": "down", "problems": fault.message}))
        else:
            print(f"{fmt.BAD} down — {fault.message}")
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = result.get("status", "unknown")
        mark = {"healthy": fmt.OK, "starting": fmt.WARN}.get(status, fmt.BAD)
        line = f"{mark} {status}"
        if result.get("problems"):
            line += f" — {result['problems']}"
        print(line)
    # A monitor needs the exit code, not the prose: 0 healthy, 1 degraded,
    # 2 down. 'starting' is 0, because restarting it would not help.
    return {"healthy": 0, "starting": 0}.get(result.get("status"), 1)
