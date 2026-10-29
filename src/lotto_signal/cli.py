from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .pcso import PcsoClient
from .workflow import (
    RunContext,
    inspect_events,
    run_audit,
    run_backfill,
    run_evening,
    run_morning,
)


MANILA = ZoneInfo("Asia/Manila")
HANDLED_STATUSES = frozenset(
    {
        "ok",
        "pending_source",
        "stale_source",
        "source_error",
        "historical_fallback",
    }
)


def report_exit_code(status: str) -> int:
    return 0 if status in HANDLED_STATUSES else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lotto-signal",
        description="Collect and evaluate official PCSO lotto results.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("backfill", "evening", "morning", "audit"):
        subcommands.add_parser(command)
    inspect = subcommands.add_parser("inspect-events")
    inspect.add_argument("--after", dest="after_event_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "inspect-events":
        events = inspect_events(root, args.after_event_id)
        print(json.dumps([event.to_dict() for event in events], sort_keys=True))
        return 0

    runners = {
        "backfill": run_backfill,
        "evening": run_evening,
        "morning": run_morning,
        "audit": run_audit,
    }
    with httpx.Client() as client:
        context = RunContext(
            root=root,
            pcso=PcsoClient(client),
            now=datetime.now(MANILA),
        )
        report = runners[args.command](context)
    print(json.dumps(asdict(report), sort_keys=True))
    return report_exit_code(report.status)


if __name__ == "__main__":
    raise SystemExit(main())
