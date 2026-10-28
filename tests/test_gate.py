from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from lotto_signal.backtest import (
    BacktestConfig,
    BacktestResult,
    MethodBacktestResult,
)
from lotto_signal.gate import evaluate_gate, holm_bonferroni
from lotto_signal.methods import Candidate


def candidate(score: float = 2.0) -> Candidate:
    return Candidate(
        game_code="LOTTO42",
        method_version="frequency_v1",
        numbers=(1, 2, 3, 4, 5, 6),
        raw_score=10.0,
        signal_score=score,
        seed=123,
    )


def passing_summary() -> MethodBacktestResult:
    return MethodBacktestResult(
        method_version="frequency_v1",
        total_predictions=200,
        alert_threshold=1.5,
        outcomes=(),
        alert_outcomes=(None,) * 30,  # type: ignore[arg-type]
        random_strategy_means=(0.8,) * 10_000,
        random_lines_per_strategy=30,
        p_value=0.0001,
        effect_size=0.4,
        first_half_effect=0.3,
        second_half_effect=0.25,
        corrected_significant=True,
        frozen_before_evaluation=True,
    )


def result_with(summary: MethodBacktestResult) -> BacktestResult:
    return BacktestResult(
        game_code="LOTTO42",
        config=BacktestConfig(),
        methods=MappingProxyType({summary.method_version: summary}),
    )


def test_holm_bonferroni_controls_all_25_game_method_hypotheses() -> None:
    p_values = {f"hypothesis-{index:02d}": 0.5 for index in range(25)}
    p_values["hypothesis-00"] = 0.0003
    p_values["hypothesis-01"] = 0.0005

    decisions = holm_bonferroni(p_values, alpha=0.01)

    assert decisions["hypothesis-00"] is True
    assert decisions["hypothesis-01"] is False
    assert sum(decisions.values()) == 1


@pytest.mark.parametrize(
    ("changed", "failed_check"),
    [
        ({"total_predictions": 199}, "minimum_predictions"),
        ({"alert_outcomes": (None,) * 29}, "minimum_alert_predictions"),
        ({"frozen_before_evaluation": False}, "method_frozen"),
        ({"corrected_significant": False}, "corrected_significance"),
        ({"first_half_effect": 0.0}, "positive_first_half"),
        ({"second_half_effect": 0.0}, "positive_second_half"),
        ({"second_half_effect": 0.19}, "recent_effect_retention"),
    ],
)
def test_each_statistical_gate_condition_is_independently_required(
    changed: dict[str, object], failed_check: str
) -> None:
    summary = replace(passing_summary(), **changed)

    decision = evaluate_gate(result_with(summary), candidate(), unresolved_data=False)

    assert decision.eligible is False
    assert decision.checks[failed_check] is False


def test_unresolved_data_and_current_frozen_threshold_block_signal() -> None:
    result = result_with(passing_summary())

    unresolved = evaluate_gate(result, candidate(), unresolved_data=True)
    below_threshold = evaluate_gate(result, candidate(1.49), unresolved_data=False)

    assert unresolved.eligible is False
    assert unresolved.checks["data_resolved"] is False
    assert below_threshold.eligible is False
    assert below_threshold.checks["current_score_threshold"] is False


def test_fully_passing_synthetic_case_is_eligible() -> None:
    decision = evaluate_gate(
        result_with(passing_summary()),
        candidate(1.5),
        unresolved_data=False,
    )

    assert decision.eligible is True
    assert decision.method_version == "frequency_v1"
    assert decision.signal_score == 1.5
    assert decision.alert_threshold == 1.5
    assert all(decision.checks.values())


def test_unknown_or_cross_game_candidate_is_rejected() -> None:
    result = result_with(passing_summary())

    with pytest.raises(ValueError, match="method"):
        evaluate_gate(result, replace(candidate(), method_version="unknown_v1"), False)
    with pytest.raises(ValueError, match="game"):
        evaluate_gate(result, replace(candidate(), game_code="ML45"), False)
