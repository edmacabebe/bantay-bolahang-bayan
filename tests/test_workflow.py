from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from lotto_signal.domain import DrawRecord
from lotto_signal.features import FeatureSnapshot
from lotto_signal.gate import GateDecision
from lotto_signal.games import GAMES, GameSpec
from lotto_signal.methods import Candidate
from lotto_signal.pcso import PcsoSourceError
from lotto_signal.workflow import (
    RunContext,
    RuntimeConfig,
    inspect_events,
    run_audit,
    run_evening,
    run_morning,
)


MANILA = ZoneInfo("Asia/Manila")
NOW = datetime(2026, 10, 28, 7, 17, tzinfo=MANILA)


def draw(game_code: str, day: date, suffix: int = 1, offset: int = 0) -> DrawRecord:
    maximum = GAMES[game_code].max_number
    numbers = tuple(((offset + index) % maximum) + 1 for index in range(6))
    return DrawRecord(
        draw_id=f"{game_code}S{suffix:07d}",
        game_code=game_code,
        draw_date=day,
        draw_time="21:00:00+08:00",
        published_numbers=numbers,
        jackpot="10000000",
        total_winners=0,
        retrieved_at=NOW,
        source_url="fixture",
    )


def healthy_latest() -> tuple[DrawRecord, ...]:
    yesterday = NOW.date() - timedelta(days=1)
    records: list[DrawRecord] = []
    for code, game in GAMES.items():
        day = yesterday
        while day.weekday() not in game.draw_weekdays:
            day -= timedelta(days=1)
        records.append(draw(code, day))
    return tuple(records)


@dataclass
class FakePcso:
    latest: tuple[DrawRecord, ...] = field(default_factory=healthy_latest)
    fail: bool = False
    history_calls: list[str] = field(default_factory=list)

    def fetch_latest(self, retrieved_at: datetime) -> tuple[DrawRecord, ...]:
        if self.fail:
            raise PcsoSourceError("fixture outage")
        return self.latest

    def iter_history(
        self, game_code: str, retrieved_at: datetime, per_page: int = 100
    ):
        self.history_calls.append(game_code)
        yield from (record for record in self.latest if record.game_code == game_code)


@dataclass(frozen=True)
class FixedMethod:
    method_version: str = "ensemble_v1"

    def generate(
        self, snapshot: FeatureSnapshot, game: GameSpec, seed: int
    ) -> Candidate:
        return Candidate(
            game_code=game.code,
            method_version=self.method_version,
            numbers=(1, 2, 3, 4, 5, 6),
            raw_score=2.0,
            signal_score=2.0,
            seed=seed,
        )


def analyzer(eligible: bool):
    def analyze(
        game: GameSpec, draws: tuple[DrawRecord, ...], current: Candidate
    ) -> GateDecision:
        checks = {"synthetic": eligible}
        return GateDecision(
            eligible=eligible,
            game_code=game.code,
            method_version=current.method_version,
            signal_score=current.signal_score,
            alert_threshold=1.5,
            checks=checks,
        )

    return analyze


def context(
    root: Path,
    pcso: FakePcso,
    *,
    eligible: bool = False,
    production: bool = False,
    now: datetime = NOW,
) -> RunContext:
    return RunContext(
        root=root,
        pcso=pcso,
        now=now,
        runtime=RuntimeConfig(
            production_research_signals=production,
            shadow_started_on=date(2026, 10, 28),
        ),
        methods=(FixedMethod(),),
        analyze=analyzer(eligible),
    )


def test_ordinary_morning_selects_only_scheduled_games_and_stays_silent(
    tmp_path: Path,
) -> None:
    report = run_morning(context(tmp_path, FakePcso()))

    assert report.status == "ok"
    assert report.source_fresh is True
    assert report.prediction_games == ("GL55", "ML45")
    assert report.event_ids == ()
    assert inspect_events(tmp_path, None) == ()
    state = json.loads((tmp_path / "state/last_run.json").read_text())
    assert state["mode"] == "morning"
    assert state["content_digest"]


def test_first_collection_failure_is_silent_and_repeat_emits_once(
    tmp_path: Path,
) -> None:
    failing = FakePcso(fail=True)

    first = run_evening(context(tmp_path, failing))
    second = run_evening(context(tmp_path, failing, now=NOW + timedelta(days=1)))
    duplicate = run_evening(context(tmp_path, failing, now=NOW + timedelta(days=1)))

    assert first.status == second.status == duplicate.status == "source_error"
    assert first.event_ids == ()
    assert len(second.event_ids) == 1
    assert duplicate.event_ids == second.event_ids
    assert len(inspect_events(tmp_path, None)) == 1


def test_missing_previous_scheduled_results_withholds_predictions_and_emits_stale_event(
    tmp_path: Path,
) -> None:
    stale = tuple(
        record
        for record in healthy_latest()
        if record.game_code not in {"LOTTO42", "SL49", "UL58"}
    )

    report = run_morning(context(tmp_path, FakePcso(latest=stale)))

    assert report.status == "stale_source"
    assert report.source_fresh is False
    assert report.prediction_games == ()
    assert inspect_events(tmp_path, None)[0].kind == "action_required"


def test_official_correction_is_append_only_and_triggers_recomputation_notice(
    tmp_path: Path,
) -> None:
    original = FakePcso()
    run_evening(context(tmp_path, original))
    corrected_records = tuple(
        draw(record.game_code, record.draw_date, offset=1)
        if record.game_code == "LOTTO42"
        else record
        for record in original.latest
    )

    report = run_evening(
        context(tmp_path, FakePcso(latest=corrected_records), now=NOW + timedelta(days=1))
    )

    assert report.revised == 1
    assert any(event.kind == "official_correction" for event in inspect_events(tmp_path, None))
    assert (tmp_path / "data/revisions/LOTTO42.jsonl").exists()


def test_duplicate_morning_is_idempotent_and_predictions_are_immutable(
    tmp_path: Path,
) -> None:
    run_morning(context(tmp_path, FakePcso()))
    first_content = (tmp_path / "data/predictions/ML45.jsonl").read_text()

    duplicate = run_morning(context(tmp_path, FakePcso()))

    assert duplicate.predictions_written == 0
    assert (tmp_path / "data/predictions/ML45.jsonl").read_text() == first_content


def test_production_signal_emits_once_but_no_signal_emits_nothing(
    tmp_path: Path,
) -> None:
    quiet = run_morning(context(tmp_path / "quiet", FakePcso(), production=True))
    signal_context = context(
        tmp_path / "signal", FakePcso(), eligible=True, production=True
    )
    signaled = run_morning(signal_context)
    duplicate = run_morning(signal_context)

    assert quiet.event_ids == ()
    assert len(signaled.event_ids) == 2
    assert duplicate.event_ids == signaled.event_ids
    assert {event.kind for event in inspect_events(tmp_path / "signal", None)} == {
        "research_signal"
    }


def test_shadow_mode_suppresses_signal_event_but_records_decision(
    tmp_path: Path,
) -> None:
    report = run_morning(context(tmp_path, FakePcso(), eligible=True, production=False))

    assert report.event_ids == ()
    decisions = json.loads((tmp_path / "state/gate_decisions.json").read_text())
    assert decisions["mode"] == "shadow"
    assert {item["eligible"] for item in decisions["decisions"]} == {True}


def test_monday_audit_backfills_all_games_and_event_cursor_filters(tmp_path: Path) -> None:
    monday = datetime(2026, 11, 2, 7, 17, tzinfo=MANILA)
    pcso = FakePcso()

    first = run_audit(context(tmp_path, pcso, now=monday))
    first_audit = json.loads((tmp_path / "state/audit.json").read_text())
    second = run_audit(context(tmp_path, pcso, now=monday))
    second_audit = json.loads((tmp_path / "state/audit.json").read_text())

    assert first.status == second.status == "ok"
    assert pcso.history_calls == list(GAMES) * 2
    assert second.inserted == 0
    assert inspect_events(tmp_path, "does-not-exist") == ()
    assert first_audit["family_hypotheses"] == 5
    assert first_audit["prediction_digest"] == second_audit["prediction_digest"]
    assert first_audit["backtest_digest"] == second_audit["backtest_digest"]
    assert first_audit["gate_digest"] == second_audit["gate_digest"]
