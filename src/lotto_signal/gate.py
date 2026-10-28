from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .backtest import BacktestResult
from .methods import Candidate


@dataclass(frozen=True, slots=True)
class GateDecision:
    eligible: bool
    game_code: str
    method_version: str
    signal_score: float
    alert_threshold: float
    checks: Mapping[str, bool]
    total_predictions: int = 0
    alert_predictions: int = 0
    p_value: float = 1.0
    effect_size: float = 0.0
    first_half_effect: float = 0.0
    second_half_effect: float = 0.0
    random_strategies: int = 0
    random_lines_per_strategy: int = 0


def holm_bonferroni(
    p_values: Mapping[str, float], alpha: float
) -> Mapping[str, bool]:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between zero and one")
    if any(not 0 <= value <= 1 for value in p_values.values()):
        raise ValueError("p-values must be between zero and one")

    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    decisions = {name: False for name in p_values}
    family_size = len(ordered)
    for index, (name, p_value) in enumerate(ordered):
        if p_value > alpha / (family_size - index):
            break
        decisions[name] = True
    return MappingProxyType(decisions)


def evaluate_gate(
    result: BacktestResult,
    current: Candidate,
    unresolved_data: bool,
) -> GateDecision:
    if current.game_code != result.game_code:
        raise ValueError("candidate game does not match backtest game")
    try:
        summary = result.methods[current.method_version]
    except KeyError as error:
        raise ValueError("candidate method is absent from backtest") from error

    checks = {
        "minimum_predictions": (
            summary.total_predictions >= result.config.min_predictions
        ),
        "minimum_alert_predictions": (
            len(summary.alert_outcomes) >= result.config.min_alert_predictions
        ),
        "method_frozen": summary.frozen_before_evaluation,
        "corrected_significance": summary.corrected_significant,
        "positive_first_half": summary.first_half_effect > 0,
        "positive_second_half": summary.second_half_effect > 0,
        "recent_effect_retention": (
            summary.effect_size > 0
            and summary.second_half_effect >= 0.5 * summary.effect_size
        ),
        "data_resolved": not unresolved_data,
        "current_score_threshold": (
            current.signal_score >= summary.alert_threshold
        ),
    }
    immutable_checks = MappingProxyType(checks)
    return GateDecision(
        eligible=all(checks.values()),
        game_code=result.game_code,
        method_version=current.method_version,
        signal_score=current.signal_score,
        alert_threshold=summary.alert_threshold,
        checks=immutable_checks,
        total_predictions=summary.total_predictions,
        alert_predictions=len(summary.alert_outcomes),
        p_value=summary.p_value,
        effect_size=summary.effect_size,
        first_half_effect=summary.first_half_effect,
        second_half_effect=summary.second_half_effect,
        random_strategies=len(summary.random_strategy_means),
        random_lines_per_strategy=summary.random_lines_per_strategy,
    )
