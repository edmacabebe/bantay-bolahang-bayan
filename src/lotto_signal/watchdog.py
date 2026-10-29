from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .heartbeat import heartbeat_matches


MANILA = ZoneInfo("Asia/Manila")
SCHEDULE_TARGETS = {
    "7 8 * * *": ("morning", 8, 7, 0),
    "7 9 * * *": ("morning", 9, 7, 0),
    "7 23 * * *": ("evening", 23, 7, 0),
    "7 0 * * *": ("evening", 0, 7, -1),
}


@dataclass(frozen=True, slots=True)
class WatchdogDecision:
    mode: str
    operational_date: date
    dispatch: bool
    reason: str


def watchdog_decision(
    root: Path,
    schedule: str,
    now: datetime,
) -> WatchdogDecision:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("watchdog time must be timezone-aware")
    if schedule not in SCHEDULE_TARGETS:
        raise ValueError(f"unsupported watchdog schedule: {schedule}")
    mode, scheduled_hour, scheduled_minute, offset = SCHEDULE_TARGETS[schedule]
    local_now = now.astimezone(MANILA)
    scheduled_day = local_now.date()
    if (local_now.hour, local_now.minute) < (scheduled_hour, scheduled_minute):
        scheduled_day -= timedelta(days=1)
    expected_date = scheduled_day + timedelta(days=offset)
    matched = heartbeat_matches(root, mode, expected_date)
    return WatchdogDecision(
        mode=mode,
        operational_date=expected_date,
        dispatch=not matched,
        reason="heartbeat present" if matched else "heartbeat missing",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lotto-watchdog",
        description="Dispatch a missed monitor run from repository heartbeats.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--now")
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        now = datetime.fromisoformat(args.now) if args.now else datetime.now(MANILA)
        decision = watchdog_decision(args.root.resolve(), args.schedule, now)
    except ValueError as error:
        print(json.dumps({"error": str(error)}, sort_keys=True))
        return 2

    payload = {
        "dispatch": decision.dispatch,
        "mode": decision.mode,
        "operational_date": decision.operational_date.isoformat(),
        "reason": decision.reason,
    }
    if args.github_output is not None:
        with args.github_output.open("a") as output:
            output.write(f"dispatch={str(decision.dispatch).lower()}\n")
            output.write(f"mode={decision.mode}\n")
            output.write(f"operational_date={decision.operational_date.isoformat()}\n")
            output.write(f"reason={decision.reason}\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
