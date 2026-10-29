from __future__ import annotations

import importlib
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


MANILA = ZoneInfo("Asia/Manila")
NOW = datetime(2026, 10, 29, 8, 7, tzinfo=MANILA)


def watchdog_module():
    try:
        return importlib.import_module("lotto_signal.watchdog")
    except ImportError:
        pytest.fail("lotto_signal.watchdog is not implemented")


def write_heartbeats(root: Path, payload: object) -> None:
    path = root / "state/heartbeats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload)
    else:
        path.write_text(json.dumps(payload))


def test_watchdog_schedule_maps_to_mode_and_operational_date(
    tmp_path: Path,
) -> None:
    module = watchdog_module()

    expected = (
        ("7 8 * * *", NOW, "morning", date(2026, 10, 29)),
        ("7 9 * * *", NOW.replace(hour=9), "morning", date(2026, 10, 29)),
        ("7 23 * * *", NOW.replace(hour=23), "evening", date(2026, 10, 29)),
        ("7 0 * * *", NOW.replace(hour=0), "evening", date(2026, 10, 28)),
    )
    for schedule, run_at, mode, operational_day in expected:
        decision = module.watchdog_decision(tmp_path, schedule, run_at)
        target = (mode, operational_day)
        assert (decision.mode, decision.operational_date) == target


def test_matching_heartbeat_is_noop(tmp_path: Path) -> None:
    module = watchdog_module()
    write_heartbeats(
        tmp_path,
        {
            "morning": {
                "operational_date": "2026-10-29",
                "finished_at": NOW.isoformat(),
                "status": "historical_fallback",
            }
        },
    )

    decision = module.watchdog_decision(tmp_path, "7 8 * * *", NOW)

    assert decision.dispatch is False
    assert decision.reason == "heartbeat present"


def test_delayed_evening_watchdog_uses_scheduled_day_across_midnight(
    tmp_path: Path,
) -> None:
    module = watchdog_module()
    delayed_at = NOW.replace(hour=0)
    write_heartbeats(
        tmp_path,
        {
            "evening": {
                "operational_date": "2026-10-28",
                "finished_at": delayed_at.isoformat(),
                "status": "ok",
            }
        },
    )

    decision = module.watchdog_decision(tmp_path, "7 23 * * *", delayed_at)

    assert decision.operational_date == date(2026, 10, 28)
    assert decision.dispatch is False


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-json",
        [],
        {
            "evening": {
                "operational_date": "2026-10-29",
                "finished_at": NOW.isoformat(),
                "status": "ok",
            }
        },
        {
            "morning": {
                "operational_date": "2026-10-28",
                "finished_at": NOW.isoformat(),
                "status": "ok",
            }
        },
        {
            "morning": {
                "operational_date": "2026-10-30",
                "finished_at": NOW.isoformat(),
                "status": "ok",
            }
        },
    ],
    ids=("missing", "malformed", "non-object", "wrong-mode", "prior", "future"),
)
def test_unusable_heartbeat_dispatches(tmp_path: Path, payload: object) -> None:
    module = watchdog_module()
    if payload is not None:
        write_heartbeats(tmp_path, payload)

    decision = module.watchdog_decision(tmp_path, "7 8 * * *", NOW)

    assert decision.dispatch is True
    assert decision.reason == "heartbeat missing"


def test_watchdog_cli_writes_github_outputs(tmp_path: Path) -> None:
    module = watchdog_module()
    output = tmp_path / "github-output"

    result = module.main(
        [
            "--root",
            str(tmp_path),
            "--schedule",
            "7 8 * * *",
            "--now",
            NOW.isoformat(),
            "--github-output",
            str(output),
        ]
    )

    assert result == 0
    assert output.read_text().splitlines() == [
        "dispatch=true",
        "mode=morning",
        "operational_date=2026-10-29",
        "reason=heartbeat missing",
    ]


@pytest.mark.parametrize(
    ("schedule", "now"),
    [
        ("unknown", NOW.isoformat()),
        ("7 8 * * *", "2026-10-29T08:07:00"),
    ],
)
def test_watchdog_cli_rejects_unknown_schedule_and_naive_time(
    tmp_path: Path,
    schedule: str,
    now: str,
) -> None:
    module = watchdog_module()

    assert module.main(
        ["--root", str(tmp_path), "--schedule", schedule, "--now", now]
    ) == 2
