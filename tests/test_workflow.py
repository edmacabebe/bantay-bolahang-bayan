from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

import lotto_signal.workflow as workflow_module
from lotto_signal.backtest import BacktestConfig, BacktestResult
from lotto_signal.domain import DrawRecord, Prediction
from lotto_signal.features import FeatureSnapshot
from lotto_signal.gate import GateDecision
from lotto_signal.games import GAMES, GameSpec
from lotto_signal.methods import Candidate
from lotto_signal.pcso import PcsoSourceError
from lotto_signal.store import RepositoryStore
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


def stale_latest() -> tuple[DrawRecord, ...]:
    return tuple(
        record
        for record in healthy_latest()
        if record.game_code not in {"LOTTO42", "SL49", "UL58"}
    )


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


def test_monitor_attempts_record_and_preserve_mode_heartbeats(
    tmp_path: Path,
) -> None:
    morning = NOW
    evening = NOW.replace(hour=22, minute=17)
    current_results = tuple(
        draw(code, evening.date())
        for code, game in GAMES.items()
        if evening.date().weekday() in game.draw_weekdays
    )

    run_morning(context(tmp_path, FakePcso(), now=morning))
    run_evening(
        context(tmp_path, FakePcso(latest=current_results), now=evening)
    )

    heartbeats = json.loads((tmp_path / "state/heartbeats.json").read_text())
    assert heartbeats["morning"] == {
        "operational_date": "2026-10-28",
        "finished_at": morning.isoformat(),
        "status": "ok",
    }
    assert heartbeats["evening"] == {
        "operational_date": "2026-10-28",
        "finished_at": evening.isoformat(),
        "status": "ok",
    }


def test_pending_and_source_error_attempts_record_heartbeats(
    tmp_path: Path,
) -> None:
    evening = NOW.replace(hour=22, minute=17)

    pending = run_evening(context(tmp_path / "pending", FakePcso(), now=evening))
    run_morning(context(tmp_path / "errors", FakePcso(fail=True), now=NOW))
    run_evening(
        context(tmp_path / "errors", FakePcso(fail=True), now=evening)
    )

    pending_heartbeats = json.loads(
        (tmp_path / "pending/state/heartbeats.json").read_text()
    )
    error_heartbeats = json.loads(
        (tmp_path / "errors/state/heartbeats.json").read_text()
    )
    assert pending.status == "pending_source"
    assert pending_heartbeats["evening"]["status"] == "pending_source"
    assert error_heartbeats["morning"]["status"] == "source_error"
    assert error_heartbeats["evening"]["status"] == "source_error"


def test_evening_operational_date_uses_noon_boundary() -> None:
    try:
        from lotto_signal.heartbeat import operational_date
    except ImportError:
        import pytest

        pytest.fail("operational_date is not implemented")

    at_0300 = NOW.replace(day=29, hour=3, minute=0)
    at_noon = at_0300.replace(hour=12)

    assert operational_date("evening", at_0300) == date(2026, 10, 28)
    assert operational_date("evening", at_noon) == date(2026, 10, 29)


def test_evening_marks_delayed_results_pending_without_notifying(tmp_path: Path) -> None:
    evening = NOW.replace(hour=22, minute=17)

    report = run_evening(context(tmp_path, FakePcso(), now=evening))

    assert report.status == "pending_source"
    assert report.source_fresh is False
    assert report.event_ids == ()


def test_midnight_evening_recovery_checks_prior_operational_date(
    tmp_path: Path,
) -> None:
    recovered_at = NOW.replace(day=29, hour=0, minute=7)
    prior_day = date(2026, 10, 28)
    prior_results = tuple(
        draw(code, prior_day)
        for code, game in GAMES.items()
        if prior_day.weekday() in game.draw_weekdays
    )

    report = run_evening(
        context(tmp_path, FakePcso(latest=prior_results), now=recovered_at)
    )

    heartbeat = json.loads(
        (tmp_path / "state/heartbeats.json").read_text()
    )["evening"]
    assert report.status == "ok"
    assert report.source_fresh is True
    assert heartbeat["operational_date"] == "2026-10-28"


def test_pending_source_retries_preserve_first_incident_time(tmp_path: Path) -> None:
    evening = NOW.replace(hour=22, minute=17)

    run_evening(context(tmp_path, FakePcso(), now=evening))
    run_evening(
        context(tmp_path, FakePcso(), now=evening + timedelta(hours=1))
    )

    state = json.loads((tmp_path / "state/last_run.json").read_text())
    assert state["incident_started_at"] == evening.isoformat()


def test_first_source_failure_starts_at_failure_not_previous_success(
    tmp_path: Path,
) -> None:
    run_morning(context(tmp_path, FakePcso(), now=NOW))
    failure_at = NOW.replace(hour=22, minute=17)

    run_evening(context(tmp_path, FakePcso(fail=True), now=failure_at))

    state = json.loads((tmp_path / "state/last_run.json").read_text())
    assert state["incident_started_at"] == failure_at.isoformat()


def test_morning_transport_failure_after_pending_evening_is_actionable(
    tmp_path: Path,
) -> None:
    evening = NOW.replace(hour=22, minute=17)
    run_evening(context(tmp_path, FakePcso(), now=evening))

    morning = run_morning(
        context(
            tmp_path,
            FakePcso(fail=True),
            now=evening + timedelta(hours=9),
        )
    )

    assert morning.status == "source_error"
    assert len(morning.event_ids) == 1
    assert inspect_events(tmp_path, None)[0].kind == "action_required"


def test_first_collection_failure_is_silent_and_repeat_emits_once(
    tmp_path: Path,
) -> None:
    failing = FakePcso(fail=True)

    first = run_evening(context(tmp_path, failing))
    second = run_evening(context(tmp_path, failing, now=NOW + timedelta(days=1)))
    duplicate = run_evening(context(tmp_path, failing, now=NOW + timedelta(days=1)))
    next_day = run_evening(context(tmp_path, failing, now=NOW + timedelta(days=2)))

    assert first.status == second.status == duplicate.status == next_day.status == "source_error"
    assert first.event_ids == ()
    assert len(second.event_ids) == 1
    assert duplicate.event_ids == second.event_ids
    assert next_day.event_ids == second.event_ids
    assert len(inspect_events(tmp_path, None)) == 1


def test_missing_previous_results_generate_historical_fallback(
    tmp_path: Path,
) -> None:
    report = run_morning(context(tmp_path, FakePcso(latest=stale_latest())))

    decisions = json.loads((tmp_path / "state/gate_decisions.json").read_text())
    heartbeats = json.loads((tmp_path / "state/heartbeats.json").read_text())
    events = inspect_events(tmp_path, None)
    assert report.status == "historical_fallback"
    assert report.source_fresh is False
    assert report.prediction_games == ("GL55", "ML45")
    assert decisions["historical_fallback"] is True
    assert decisions["missing_expected_games"] == ["LOTTO42", "SL49", "UL58"]
    assert decisions["production_alerts_suppressed"] is True
    assert heartbeats["morning"]["status"] == "historical_fallback"
    assert [event.kind for event in events] == ["action_required"]
    assert events[0].payload["historical_combinations_generated"] is True
    assert events[0].payload["production_alerts_suppressed"] is True


def test_historical_fallback_retry_is_idempotent(tmp_path: Path) -> None:
    pcso = FakePcso(latest=stale_latest())
    first = run_morning(context(tmp_path, pcso))
    prediction_bytes = {
        code: (tmp_path / f"data/predictions/{code}.jsonl").read_bytes()
        for code in ("GL55", "ML45")
    }

    retry = run_morning(context(tmp_path, pcso, now=NOW + timedelta(hours=2)))

    assert first.predictions_written == 2
    assert retry.predictions_written == 0
    assert retry.event_ids == first.event_ids
    assert {
        code: (tmp_path / f"data/predictions/{code}.jsonl").read_bytes()
        for code in ("GL55", "ML45")
    } == prediction_bytes


def test_historical_fallback_suppresses_eligible_production_signal(
    tmp_path: Path,
) -> None:
    report = run_morning(
        context(
            tmp_path,
            FakePcso(latest=stale_latest()),
            eligible=True,
            production=True,
        )
    )

    decisions = json.loads((tmp_path / "state/gate_decisions.json").read_text())
    assert report.status == "historical_fallback"
    assert {event.kind for event in inspect_events(tmp_path, None)} == {
        "action_required"
    }
    assert decisions["production_alerts_suppressed"] is True


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


def test_evening_scores_prediction_once_and_versions_corrected_outcome(
    tmp_path: Path,
) -> None:
    latest = healthy_latest()
    result = next(record for record in latest if record.game_code == "LOTTO42")
    RepositoryStore(tmp_path).append_prediction(
        Prediction(
            prediction_id=f"LOTTO42-{result.draw_date.isoformat()}-ensemble_v1",
            game_code="LOTTO42",
            target_draw_date=result.draw_date,
            method_version="ensemble_v1",
            numbers=(1, 2, 3, 4, 5, 6),
            raw_score=1.0,
            signal_score=1.0,
            seed=1,
            created_at=NOW - timedelta(days=1),
            source_cutoff=NOW - timedelta(days=1),
            feature_values={},
        )
    )

    first = run_evening(context(tmp_path, FakePcso(latest=latest)))
    duplicate = run_evening(context(tmp_path, FakePcso(latest=latest)))
    corrected = tuple(
        draw(record.game_code, record.draw_date, offset=1)
        if record.game_code == "LOTTO42"
        else record
        for record in latest
    )
    revised = run_evening(
        context(tmp_path, FakePcso(latest=corrected), now=NOW + timedelta(hours=1))
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "data/outcomes/LOTTO42.jsonl").read_text().splitlines()
    ]
    assert first.outcomes_written == 1
    assert duplicate.outcomes_written == 0
    assert revised.outcomes_written == 1
    assert [row["matched"] for row in rows] == [6, 5]
    assert rows[0]["draw_fingerprint"] != rows[1]["draw_fingerprint"]


def test_duplicate_morning_is_idempotent_and_predictions_are_immutable(
    tmp_path: Path,
) -> None:
    run_morning(context(tmp_path, FakePcso()))
    first_content = (tmp_path / "data/predictions/ML45.jsonl").read_text()

    duplicate = run_morning(
        context(tmp_path, FakePcso(), now=NOW + timedelta(hours=2))
    )

    assert duplicate.predictions_written == 0
    assert (tmp_path / "data/predictions/ML45.jsonl").read_text() == first_content


def test_same_day_retry_reuses_primary_prediction_if_selected_method_changes(
    tmp_path: Path,
) -> None:
    first = run_morning(context(tmp_path, FakePcso()))
    changed_context = RunContext(
        root=tmp_path,
        pcso=FakePcso(),
        now=NOW + timedelta(hours=2),
        runtime=RuntimeConfig(
            production_research_signals=False,
            shadow_started_on=date(2026, 10, 28),
        ),
        methods=(FixedMethod(method_version="frequency_v1"),),
        analyze=analyzer(False),
    )

    retry = run_morning(changed_context)

    assert first.predictions_written == 2
    assert retry.predictions_written == 0
    for game_code in ("GL55", "ML45"):
        rows = (
            tmp_path / f"data/predictions/{game_code}.jsonl"
        ).read_text().splitlines()
        assert len(rows) == 1
        assert json.loads(rows[0])["method_version"] == "ensemble_v1"


def test_production_signal_emits_once_but_no_signal_emits_nothing(
    tmp_path: Path,
) -> None:
    quiet = run_morning(context(tmp_path / "quiet", FakePcso(), production=True))
    signal_context = context(
        tmp_path / "signal", FakePcso(), eligible=True, production=True
    )
    signaled = run_morning(signal_context)
    duplicate = run_morning(
        context(
            tmp_path / "signal",
            FakePcso(),
            eligible=True,
            production=True,
            now=NOW + timedelta(hours=2),
        )
    )

    assert quiet.event_ids == ()
    assert len(signaled.event_ids) == 2
    assert duplicate.event_ids == signaled.event_ids
    assert {event.kind for event in inspect_events(tmp_path / "signal", None)} == {
        "research_signal"
    }
    assert {
        event.payload["source_cutoff"]
        for event in inspect_events(tmp_path / "signal", None)
    } == {NOW.isoformat()}


def test_shadow_mode_suppresses_signal_event_but_records_decision(
    tmp_path: Path,
) -> None:
    report = run_morning(context(tmp_path, FakePcso(), eligible=True, production=False))

    assert report.event_ids == ()
    decisions = json.loads((tmp_path / "state/gate_decisions.json").read_text())
    assert decisions["mode"] == "shadow"
    assert decisions["historical_fallback"] is False
    assert decisions["missing_expected_games"] == []
    assert decisions["production_alerts_suppressed"] is False
    assert {item["eligible"] for item in decisions["decisions"]} == {True}
    assert all("validation" in item for item in decisions["decisions"])


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


def test_default_audit_parallelizes_the_five_independent_games(
    tmp_path: Path, monkeypatch
) -> None:
    executor_sizes: list[int] = []

    class InlineExecutor:
        def __init__(self, max_workers: int) -> None:
            executor_sizes.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def map(self, function, items):
            return [function(item) for item in items]

    def empty_backtest(game, draws, methods, config):
        return BacktestResult(
            game_code=game.code,
            config=BacktestConfig(),
            methods=MappingProxyType({}),
        )

    monkeypatch.setattr(workflow_module, "ProcessPoolExecutor", InlineExecutor)
    monkeypatch.setattr(workflow_module, "walk_forward", empty_backtest)

    run_audit(RunContext(root=tmp_path, pcso=FakePcso(), now=NOW))

    assert executor_sizes == [5]


def test_live_gate_uses_global_audit_decision_and_current_data_integrity(
    tmp_path: Path,
) -> None:
    game = GAMES["ML45"]
    draws = (draw("ML45", date(2026, 10, 26)),)
    current = Candidate(
        game_code="ML45",
        method_version="ensemble_v1",
        numbers=(1, 2, 3, 4, 5, 6),
        raw_score=2.0,
        signal_score=2.0,
        seed=1,
    )
    evidence = {
        "total_predictions": 250,
        "alert_predictions": 40,
        "alert_threshold": 1.5,
        "p_value": 0.0001,
        "corrected_significant": False,
        "effect_size": 0.4,
        "first_half_effect": 0.3,
        "second_half_effect": 0.25,
        "frozen_before_evaluation": True,
        "random_strategies": 10_000,
        "random_lines_per_strategy": 40,
    }
    members = workflow_module._family_members()
    audit = {
        "family_id": workflow_module.EXPERIMENT_FAMILY_ID,
        "family_hypotheses": 25,
        "family_members": list(members),
        "family_digest": workflow_module._family_digest(members),
        "draw_manifests": {"ML45": workflow_module._draw_manifest(draws)},
        "validation_reports": {
            code: {"resolved": True, "issues": []} for code in GAMES
        },
        "evidence": {member: dict(evidence) for member in members},
        "gate_checks": {member: {"audited": True} for member in members},
    }
    audit["evidence"]["ML45:ensemble_v1"] = evidence
    (tmp_path / "state").mkdir()
    (tmp_path / "state/audit.json").write_text(json.dumps(audit))

    locally_tempting = workflow_module._decision_from_audit(
        tmp_path, game, draws, current
    )
    assert locally_tempting.eligible is False
    assert locally_tempting.checks["corrected_significance"] is False

    evidence["corrected_significant"] = True
    audit["draw_manifests"]["ML45"]["prefix_digest"] = "outdated"
    (tmp_path / "state/audit.json").write_text(json.dumps(audit))
    changed_data = workflow_module._decision_from_audit(tmp_path, game, draws, current)
    assert changed_data.eligible is False
    assert changed_data.checks["data_resolved"] is False

    audit["draw_manifests"]["ML45"] = workflow_module._draw_manifest(draws)
    (tmp_path / "state/audit.json").write_text(json.dumps(audit))
    passing = workflow_module._decision_from_audit(tmp_path, game, draws, current)
    assert passing.eligible is True
    assert passing.total_predictions == 250
    assert passing.alert_predictions == 40

    later_draws = draws + (draw("ML45", date(2026, 10, 28), suffix=2),)
    appended = workflow_module._decision_from_audit(
        tmp_path, game, later_draws, current
    )
    assert appended.checks["data_resolved"] is True

    del audit["evidence"][members[0]]
    (tmp_path / "state/audit.json").write_text(json.dumps(audit))
    partial_family = workflow_module._decision_from_audit(
        tmp_path, game, draws, current
    )
    assert partial_family.eligible is False
    assert partial_family.checks["corrected_significance"] is False


def test_weekly_audit_detects_newly_passing_and_lost_gate_posture() -> None:
    failed = {"LOTTO42:ensemble_v1": {"sample": True, "significant": False}}
    passed = {"LOTTO42:ensemble_v1": {"sample": True, "significant": True}}

    gained = workflow_module._gate_transitions(failed, passed)
    lost = workflow_module._gate_transitions(passed, failed)

    assert gained == (("LOTTO42:ensemble_v1", "newly_passing"),)
    assert lost == (("LOTTO42:ensemble_v1", "lost_signal"),)
    assert workflow_module._gate_transitions({}, passed) == (
        ("LOTTO42:ensemble_v1", "newly_passing"),
    )


def test_validation_detects_missing_scheduled_draw_inside_audited_range() -> None:
    game = GAMES["ML45"]
    draws = (
        draw("ML45", date(2026, 10, 26), suffix=1),
        draw("ML45", date(2026, 10, 30), suffix=2),
    )

    assert "missing scheduled draw: 2026-10-28" in workflow_module._validation_issues(
        game, draws
    )


def test_live_method_selection_can_choose_any_passing_experimental_method(
    tmp_path: Path,
) -> None:
    members = workflow_module._family_members()
    checks = {member: {"passes": False} for member in members}
    checks["ML45:frequency_v1"] = {"passes": True}
    evidence = {
        member: {"p_value": 1.0, "effect_size": 0.0} for member in members
    }
    evidence["ML45:frequency_v1"] = {"p_value": 0.0001, "effect_size": 0.4}
    audit = {
        "family_id": workflow_module.EXPERIMENT_FAMILY_ID,
        "family_hypotheses": 25,
        "family_members": list(members),
        "family_digest": workflow_module._family_digest(members),
        "evidence": evidence,
        "gate_checks": checks,
    }
    (tmp_path / "state").mkdir()
    (tmp_path / "state/audit.json").write_text(json.dumps(audit))
    run_context = RunContext(root=tmp_path, pcso=FakePcso(), now=NOW)

    selected = workflow_module._primary_method(run_context, GAMES["ML45"])

    assert selected.method_version == "frequency_v1"
