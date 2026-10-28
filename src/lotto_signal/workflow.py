from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from .backtest import BacktestConfig, BacktestResult, walk_forward
from .domain import DrawRecord, MonitorEvent, Prediction
from .features import compute_features
from .gate import GateDecision, holm_bonferroni
from .games import GAMES, GameSpec
from .methods import METHODS, Candidate, CandidateMethod, derive_seed
from .pcso import PcsoSourceError
from .store import MergeResult, RepositoryStore


class PcsoSource(Protocol):
    def fetch_latest(self, retrieved_at: datetime) -> tuple[DrawRecord, ...]: ...

    def iter_history(
        self, game_code: str, retrieved_at: datetime, per_page: int = 100
    ): ...


Analyzer = Callable[
    [GameSpec, tuple[DrawRecord, ...], Candidate], GateDecision
]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    production_research_signals: bool = False
    shadow_started_on: date = date(2026, 10, 28)

    @classmethod
    def from_path(cls, path: Path) -> RuntimeConfig:
        payload = json.loads(path.read_text())
        return cls(
            production_research_signals=bool(
                payload.get("production_research_signals", False)
            ),
            shadow_started_on=date.fromisoformat(payload["shadow_started_on"]),
        )


@dataclass(frozen=True, slots=True)
class RunContext:
    root: Path
    pcso: PcsoSource
    now: datetime
    runtime: RuntimeConfig | None = None
    methods: tuple[CandidateMethod, ...] = tuple(
        method
        for version, method in METHODS.items()
        if version != "uniform_random_v1"
    )
    analyze: Analyzer | None = None

    def __post_init__(self) -> None:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("run time must be timezone-aware")
        if not self.methods:
            raise ValueError("at least one candidate method is required")


@dataclass(frozen=True, slots=True)
class RunReport:
    run_id: str
    mode: str
    status: str
    source_fresh: bool
    inserted: int = 0
    unchanged: int = 0
    revised: int = 0
    predictions_written: int = 0
    outcomes_written: int = 0
    prediction_games: tuple[str, ...] = ()
    event_ids: tuple[str, ...] = ()
    content_digest: str = ""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(f"{_canonical(payload)}\n")
    temporary.replace(path)


def _run_id(mode: str, now: datetime) -> str:
    material = f"{mode}|{now.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()[:20]


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _draw_digest(draws: Sequence[DrawRecord]) -> str:
    return _digest(
        [
            {
                "draw_id": draw.draw_id,
                "draw_date": draw.draw_date.isoformat(),
                "fingerprint": draw.fingerprint,
            }
            for draw in sorted(
                draws, key=lambda item: (item.draw_date, item.draw_time, item.draw_id)
            )
        ]
    )


def _runtime(context: RunContext) -> RuntimeConfig:
    if context.runtime is not None:
        return context.runtime
    path = context.root / "config" / "runtime.json"
    if path.exists():
        return RuntimeConfig.from_path(path)
    return RuntimeConfig()


def _previous_status(root: Path) -> str | None:
    path = root / "state" / "last_run.json"
    if not path.exists():
        return None
    try:
        return str(json.loads(path.read_text()).get("status"))
    except (OSError, ValueError, TypeError):
        return None


def _finish(
    context: RunContext,
    mode: str,
    status: str,
    source_fresh: bool,
    merge: MergeResult = MergeResult(),
    *,
    predictions_written: int = 0,
    outcomes_written: int = 0,
    prediction_games: Sequence[str] = (),
    event_ids: Sequence[str] = (),
) -> RunReport:
    run_id = _run_id(mode, context.now)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "started_at": context.now.isoformat(),
        "finished_at": context.now.isoformat(),
        "source_fresh": source_fresh,
        "status": status,
        "inserted": merge.inserted,
        "unchanged": merge.unchanged,
        "revised": merge.revised,
        "predictions_written": predictions_written,
        "outcomes_written": outcomes_written,
        "prediction_games": sorted(prediction_games),
        "event_ids": sorted(event_ids),
    }
    digest = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    payload["content_digest"] = digest
    _atomic_json(context.root / "state" / "last_run.json", payload)
    return RunReport(
        run_id=run_id,
        mode=mode,
        status=status,
        source_fresh=source_fresh,
        inserted=merge.inserted,
        unchanged=merge.unchanged,
        revised=merge.revised,
        predictions_written=predictions_written,
        outcomes_written=outcomes_written,
        prediction_games=tuple(sorted(prediction_games)),
        event_ids=tuple(sorted(event_ids)),
        content_digest=digest,
    )


def _event(
    context: RunContext,
    event_id: str,
    kind: str,
    payload: dict[str, Any],
) -> str:
    RepositoryStore(context.root).write_event(
        MonitorEvent(
            event_id=event_id,
            kind=kind,
            created_at=context.now,
            payload=payload,
        )
    )
    return event_id


def _incident_id(kind: str, payload: dict[str, Any]) -> str:
    return f"{kind}-{_digest(payload)[:16]}"


def _source_error(
    context: RunContext, mode: str, error: PcsoSourceError
) -> RunReport:
    was_failed = _previous_status(context.root) == "source_error"
    event_ids: list[str] = []
    if was_failed:
        event_ids.append(
            _event(
                context,
                "source-error-pcso-collection",
                "action_required",
                {"reason": "PCSO collection failed after retry", "detail": str(error)},
            )
        )
    return _finish(
        context,
        mode,
        "source_error",
        False,
        event_ids=event_ids,
    )


def _correction_event(
    context: RunContext, mode: str, merge: MergeResult
) -> tuple[str, ...]:
    if merge.revised == 0:
        return ()
    payload = {
        "draw_ids": list(merge.revised_draw_ids),
        "action": "dependent predictions and evidence must be recomputed",
    }
    event_id = _incident_id("official-correction", payload)
    return (
        _event(
            context,
            event_id,
            "official_correction",
            payload,
        ),
    )


def _scheduled_games(day: date) -> tuple[GameSpec, ...]:
    return tuple(game for game in GAMES.values() if day.weekday() in game.draw_weekdays)


def _missing_expected_games(
    records: Sequence[DrawRecord], now: datetime
) -> tuple[str, ...]:
    yesterday = now.date() - timedelta(days=1)
    return _missing_games_for_day(records, yesterday)


def _missing_games_for_day(
    records: Sequence[DrawRecord], day: date
) -> tuple[str, ...]:
    return tuple(
        game.code
        for game in _scheduled_games(day)
        if not any(
            record.game_code == game.code and record.draw_date == day
            for record in records
        )
    )


def _primary_method(context: RunContext) -> CandidateMethod:
    for method in context.methods:
        if method.method_version == "ensemble_v1":
            return method
    return context.methods[0]


def _validation_issues(
    game: GameSpec,
    draws: tuple[DrawRecord, ...],
) -> tuple[str, ...]:
    issues: list[str] = []
    dates: set[date] = set()
    for draw in draws:
        if draw.draw_date in dates:
            issues.append(f"duplicate draw date: {draw.draw_date.isoformat()}")
        dates.add(draw.draw_date)
        if draw.draw_date.weekday() not in game.draw_weekdays:
            issues.append(
                f"unexpected draw weekday: {draw.draw_date.isoformat()}"
            )
    return tuple(issues)


def _decision_from_audit(
    root: Path,
    game: GameSpec,
    draws: tuple[DrawRecord, ...],
    current: Candidate,
) -> GateDecision:
    audit_path = Path(root) / "state" / "audit.json"
    audit: dict[str, Any] = {}
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text())
        except (OSError, ValueError, TypeError):
            audit = {}
    hypothesis = f"{game.code}:{current.method_version}"
    evidence = audit.get("evidence", {}).get(hypothesis)
    if not isinstance(evidence, dict):
        evidence = {}
    validation = _validation_report(root, game, draws, audit)
    data_resolved = bool(validation["resolved"])
    effect_size = float(evidence.get("effect_size", 0.0))
    second_half_effect = float(evidence.get("second_half_effect", 0.0))
    threshold = float(evidence.get("alert_threshold", float("inf")))
    checks = {
        "minimum_predictions": (
            int(evidence.get("total_predictions", 0))
            >= BacktestConfig().min_predictions
        ),
        "minimum_alert_predictions": (
            int(evidence.get("alert_predictions", 0))
            >= BacktestConfig().min_alert_predictions
        ),
        "method_frozen": bool(evidence.get("frozen_before_evaluation", False)),
        "corrected_significance": bool(
            evidence.get("corrected_significant", False)
        ),
        "positive_first_half": float(evidence.get("first_half_effect", 0.0)) > 0,
        "positive_second_half": second_half_effect > 0,
        "recent_effect_retention": (
            effect_size > 0 and second_half_effect >= 0.5 * effect_size
        ),
        "data_resolved": data_resolved,
        "current_score_threshold": current.signal_score >= threshold,
    }
    return GateDecision(
        eligible=all(checks.values()),
        game_code=game.code,
        method_version=current.method_version,
        signal_score=current.signal_score,
        alert_threshold=threshold,
        checks=checks,
        total_predictions=int(evidence.get("total_predictions", 0)),
        alert_predictions=int(evidence.get("alert_predictions", 0)),
        p_value=float(evidence.get("p_value", 1.0)),
        effect_size=effect_size,
        first_half_effect=float(evidence.get("first_half_effect", 0.0)),
        second_half_effect=second_half_effect,
        random_strategies=int(evidence.get("random_strategies", 0)),
        random_lines_per_strategy=int(
            evidence.get("random_lines_per_strategy", 0)
        ),
    )


def _validation_report(
    root: Path,
    game: GameSpec,
    draws: tuple[DrawRecord, ...],
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if audit is None:
        audit_path = Path(root) / "state" / "audit.json"
        if audit_path.exists():
            try:
                audit = json.loads(audit_path.read_text())
            except (OSError, ValueError, TypeError):
                audit = {}
        else:
            audit = {}
    current_digest = _draw_digest(draws)
    expected_digest = audit.get("draw_digests", {}).get(game.code)
    issues = list(_validation_issues(game, draws))
    if not expected_digest:
        issues.append("no audited draw digest")
    elif expected_digest != current_digest:
        issues.append("draw history changed since audit")
    return {
        "resolved": not issues,
        "issues": issues,
        "current_draw_digest": current_digest,
        "audit_draw_digest": expected_digest,
    }


def _gate_transitions(
    previous: dict[str, dict[str, bool]],
    current: dict[str, dict[str, bool]],
) -> tuple[tuple[str, str], ...]:
    transitions: list[tuple[str, str]] = []
    for hypothesis in sorted(previous.keys() & current.keys()):
        was_passing = bool(previous[hypothesis]) and all(
            previous[hypothesis].values()
        )
        is_passing = bool(current[hypothesis]) and all(
            current[hypothesis].values()
        )
        if not was_passing and is_passing:
            transitions.append((hypothesis, "newly_passing"))
        elif was_passing and not is_passing:
            transitions.append((hypothesis, "lost_signal"))
    return tuple(transitions)


def _audit_game(
    item: tuple[str, tuple[DrawRecord, ...], tuple[str, ...]],
) -> tuple[str, BacktestResult]:
    code, draws, method_versions = item
    methods = tuple(METHODS[version] for version in method_versions)
    result = walk_forward(GAMES[code], draws, methods, BacktestConfig())
    return code, BacktestResult(
        game_code=result.game_code,
        config=result.config,
        methods=dict(result.methods),
    )


def run_backfill(context: RunContext) -> RunReport:
    store = RepositoryStore(context.root)
    records: list[DrawRecord] = []
    try:
        for game_code in GAMES:
            records.extend(context.pcso.iter_history(game_code, context.now, 100))
    except PcsoSourceError as error:
        return _source_error(context, "backfill", error)
    merge = store.merge_draws(records)
    correction_ids = _correction_event(context, "backfill", merge)
    return _finish(
        context,
        "backfill",
        "ok",
        True,
        merge,
        event_ids=correction_ids,
    )


def run_evening(context: RunContext) -> RunReport:
    store = RepositoryStore(context.root)
    try:
        records = context.pcso.fetch_latest(context.now)
    except PcsoSourceError as error:
        return _source_error(context, "evening", error)
    merge = store.merge_draws(records)
    outcomes_written = store.score_completed_predictions(context.now)
    correction_ids = _correction_event(context, "evening", merge)
    source_fresh = not _missing_games_for_day(records, context.now.date())
    return _finish(
        context,
        "evening",
        "ok" if source_fresh else "pending_source",
        source_fresh,
        merge,
        outcomes_written=outcomes_written,
        event_ids=correction_ids,
    )


def run_morning(context: RunContext) -> RunReport:
    store = RepositoryStore(context.root)
    try:
        records = context.pcso.fetch_latest(context.now)
    except PcsoSourceError as error:
        return _source_error(context, "morning", error)
    merge = store.merge_draws(records)
    outcomes_written = store.score_completed_predictions(context.now)
    event_ids = list(_correction_event(context, "morning", merge))
    missing_expected = _missing_expected_games(records, context.now)
    if missing_expected:
        payload = {
            "reason": "required prior scheduled PCSO result is missing",
            "games": list(missing_expected),
        }
        event_ids.append(
            _event(
                context,
                _incident_id("stale-source", payload),
                "action_required",
                payload,
            )
        )
        return _finish(
            context,
            "morning",
            "stale_source",
            False,
            merge,
            outcomes_written=outcomes_written,
            event_ids=event_ids,
        )

    runtime = _runtime(context)
    primary = _primary_method(context)
    predictions_written = 0
    prediction_games: list[str] = []
    decisions: list[dict[str, Any]] = []
    for game in _scheduled_games(context.now.date()):
        draws = store.load_draws(game.code, before=context.now)
        prediction_id = (
            f"{game.code}-{context.now.date().isoformat()}-"
            f"{primary.method_version}"
        )
        prediction = store.load_prediction(game.code, prediction_id)
        if prediction is None:
            snapshot = compute_features(draws, game, context.now)
            seed = derive_seed(
                game.code,
                context.now.date(),
                primary.method_version,
                context.now,
            )
            current = primary.generate(snapshot, game, seed)
            prediction = Prediction(
                prediction_id=prediction_id,
                game_code=game.code,
                target_draw_date=context.now.date(),
                method_version=current.method_version,
                numbers=current.numbers,
                raw_score=current.raw_score,
                signal_score=current.signal_score,
                seed=current.seed,
                created_at=context.now,
                source_cutoff=context.now,
                feature_values=snapshot.values,
            )
            predictions_written += int(store.append_prediction(prediction))
        else:
            current = Candidate(
                game_code=prediction.game_code,
                method_version=prediction.method_version,
                numbers=prediction.numbers,
                raw_score=prediction.raw_score,
                signal_score=prediction.signal_score,
                seed=prediction.seed,
            )
        prediction_games.append(game.code)
        decision = (
            context.analyze(game, draws, current)
            if context.analyze is not None
            else _decision_from_audit(context.root, game, draws, current)
        )
        decisions.append(
            {
                "game_code": game.code,
                "method_version": decision.method_version,
                "eligible": decision.eligible,
                "signal_score": decision.signal_score,
                "alert_threshold": decision.alert_threshold,
                "checks": dict(decision.checks),
                "total_predictions": decision.total_predictions,
                "alert_predictions": decision.alert_predictions,
                "p_value": decision.p_value,
                "effect_size": decision.effect_size,
                "first_half_effect": decision.first_half_effect,
                "second_half_effect": decision.second_half_effect,
                "random_strategies": decision.random_strategies,
                "random_lines_per_strategy": decision.random_lines_per_strategy,
                "validation": _validation_report(
                    context.root, game, draws
                ),
            }
        )
        if decision.eligible and runtime.production_research_signals:
            event_ids.append(
                _event(
                    context,
                    (
                        f"research-signal-{game.code}-"
                        f"{context.now.date().isoformat()}-{current.method_version}"
                    ),
                    "research_signal",
                    {
                        "game_code": game.code,
                        "target_draw_date": context.now.date().isoformat(),
                        "numbers": list(current.numbers),
                        "method_version": current.method_version,
                        "signal_score": current.signal_score,
                        "alert_threshold": decision.alert_threshold,
                        "total_predictions": decision.total_predictions,
                        "alert_predictions": decision.alert_predictions,
                        "p_value": decision.p_value,
                        "effect_size": decision.effect_size,
                        "first_half_effect": decision.first_half_effect,
                        "second_half_effect": decision.second_half_effect,
                        "random_strategies": decision.random_strategies,
                        "random_lines_per_strategy": (
                            decision.random_lines_per_strategy
                        ),
                        "source_cutoff": context.now.isoformat(),
                        "disclaimer": (
                            "Experimental historical signal only; jackpot odds are "
                            "unchanged and this is not a guarantee or spending advice."
                        ),
                    },
                )
            )

    _atomic_json(
        context.root / "state" / "gate_decisions.json",
        {
            "as_of": context.now.isoformat(),
            "mode": (
                "production" if runtime.production_research_signals else "shadow"
            ),
            "shadow_started_on": runtime.shadow_started_on.isoformat(),
            "decisions": decisions,
        },
    )
    return _finish(
        context,
        "morning",
        "ok",
        True,
        merge,
        predictions_written=predictions_written,
        outcomes_written=outcomes_written,
        prediction_games=prediction_games,
        event_ids=event_ids,
    )


def run_audit(context: RunContext) -> RunReport:
    store = RepositoryStore(context.root)
    audit_path = context.root / "state" / "audit.json"
    previous_audit: dict[str, Any] = {}
    if audit_path.exists():
        try:
            previous_audit = json.loads(audit_path.read_text())
        except (OSError, ValueError, TypeError):
            previous_audit = {}
    records: list[DrawRecord] = []
    try:
        for game_code in GAMES:
            records.extend(context.pcso.iter_history(game_code, context.now, 100))
    except PcsoSourceError as error:
        return _source_error(context, "audit", error)
    merge = store.merge_draws(records)
    event_ids = list(_correction_event(context, "audit", merge))
    experiment_methods = tuple(
        method
        for method in context.methods
        if method.method_version != "uniform_random_v1"
    )
    if not experiment_methods:
        experiment_methods = context.methods
    method_versions = tuple(method.method_version for method in experiment_methods)
    if all(version in METHODS for version in method_versions):
        audit_items = tuple(
            (code, store.load_draws(code), method_versions) for code in GAMES
        )
        with ProcessPoolExecutor(max_workers=len(audit_items)) as executor:
            results = dict(executor.map(_audit_game, audit_items))
    else:
        results = {
            code: walk_forward(
                game,
                store.load_draws(code),
                experiment_methods,
                BacktestConfig(),
            )
            for code, game in GAMES.items()
        }
    p_values = {
        f"{code}:{method_version}": summary.p_value
        for code, result in results.items()
        for method_version, summary in result.methods.items()
    }
    corrected = holm_bonferroni(p_values, BacktestConfig().family_alpha)
    evidence: dict[str, dict[str, Any]] = {}
    gate_checks: dict[str, dict[str, bool]] = {}
    for code, result in results.items():
        for method_version, summary in result.methods.items():
            hypothesis = f"{code}:{method_version}"
            evidence[hypothesis] = {
                "total_predictions": summary.total_predictions,
                "alert_predictions": len(summary.alert_outcomes),
                "alert_threshold": summary.alert_threshold,
                "p_value": summary.p_value,
                "corrected_significant": corrected[hypothesis],
                "effect_size": summary.effect_size,
                "first_half_effect": summary.first_half_effect,
                "second_half_effect": summary.second_half_effect,
                "frozen_before_evaluation": summary.frozen_before_evaluation,
                "training_predictions": summary.training_predictions,
                "training_cutoff_draw_id": summary.training_cutoff_draw_id,
                "random_strategies": len(summary.random_strategy_means),
                "random_lines_per_strategy": summary.random_lines_per_strategy,
            }
            gate_checks[hypothesis] = {
                "minimum_predictions": (
                    summary.total_predictions >= result.config.min_predictions
                ),
                "minimum_alert_predictions": (
                    len(summary.alert_outcomes)
                    >= result.config.min_alert_predictions
                ),
                "method_frozen": summary.frozen_before_evaluation,
                "corrected_significance": corrected[hypothesis],
                "positive_first_half": summary.first_half_effect > 0,
                "positive_second_half": summary.second_half_effect > 0,
                "recent_effect_retention": (
                    summary.effect_size > 0
                    and summary.second_half_effect >= 0.5 * summary.effect_size
                ),
            }
    prediction_rows = []
    for path in sorted((context.root / "data" / "predictions").glob("*.jsonl")):
        prediction_rows.extend(
            json.loads(line) for line in path.read_text().splitlines() if line
        )
    transitions = _gate_transitions(
        previous_audit.get("gate_checks", {}), gate_checks
    )
    if _runtime(context).production_research_signals:
        for hypothesis, transition in transitions:
            payload = {
                "hypothesis": hypothesis,
                "transition": transition,
                "gate_digest": _digest(gate_checks),
            }
            event_ids.append(
                _event(
                    context,
                    _incident_id("evidence-transition", payload),
                    "evidence_transition",
                    payload,
                )
            )
    _atomic_json(
        audit_path,
        {
            "as_of": context.now.isoformat(),
            "weekday": context.now.strftime("%A"),
            "games": {
                code: len(store.load_draws(code)) for code in GAMES
            },
            "draw_digests": {
                code: _draw_digest(store.load_draws(code)) for code in GAMES
            },
            "revisions": merge.revised,
            "family_hypotheses": len(p_values),
            "prediction_digest": _digest(prediction_rows),
            "backtest_digest": _digest(evidence),
            "gate_digest": _digest(gate_checks),
            "evidence": evidence,
            "gate_checks": gate_checks,
            "transitions": [
                {"hypothesis": hypothesis, "transition": transition}
                for hypothesis, transition in transitions
            ],
        },
    )
    return _finish(
        context,
        "audit",
        "ok",
        True,
        merge,
        event_ids=event_ids,
    )


def inspect_events(
    root: Path, after_event_id: str | None
) -> tuple[MonitorEvent, ...]:
    path = Path(root) / "alerts" / "events.jsonl"
    if not path.exists():
        return ()
    events: list[MonitorEvent] = []
    for line in path.read_text().splitlines():
        if not line:
            continue
        payload = json.loads(line)
        events.append(
            MonitorEvent(
                event_id=payload["event_id"],
                kind=payload["kind"],
                created_at=datetime.fromisoformat(payload["created_at"]),
                payload=payload["payload"],
            )
        )
    if after_event_id is None:
        return tuple(events)
    for index, event in enumerate(events):
        if event.event_id == after_event_id:
            return tuple(events[index + 1 :])
    return ()
