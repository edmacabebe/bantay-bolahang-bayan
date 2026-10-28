from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, time
from statistics import fmean
from types import MappingProxyType
from zoneinfo import ZoneInfo

from .domain import DrawRecord
from .features import compute_features
from .games import GameSpec
from .methods import Candidate, CandidateMethod, derive_seed


MANILA = ZoneInfo("Asia/Manila")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    min_predictions: int = 200
    min_alert_predictions: int = 30
    random_strategies: int = 10_000
    alert_percentile: float = 0.85
    family_alpha: float = 0.01
    family_hypotheses: int = 25
    training_predictions: int = 100


@dataclass(frozen=True, slots=True)
class BacktestOutcome:
    draw_id: str
    target_draw_date: str
    winning_numbers: tuple[int, ...]
    candidate: Candidate
    matched: int


@dataclass(frozen=True, slots=True)
class MethodBacktestResult:
    method_version: str
    total_predictions: int
    alert_threshold: float
    outcomes: tuple[BacktestOutcome, ...]
    alert_outcomes: tuple[BacktestOutcome, ...]
    random_strategy_means: tuple[float, ...]
    random_lines_per_strategy: int
    p_value: float
    effect_size: float
    first_half_effect: float
    second_half_effect: float
    corrected_significant: bool
    frozen_before_evaluation: bool = True
    training_predictions: int = 0
    training_cutoff_draw_id: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestResult:
    game_code: str
    config: BacktestConfig
    methods: Mapping[str, MethodBacktestResult]


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return float("inf")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _random_seed(game_code: str, method_version: str) -> int:
    material = f"{game_code}|{method_version}|random-strategies-v1"
    return int(hashlib.sha256(material.encode()).hexdigest()[:16], 16)


def _holm_flags(
    p_values: Mapping[str, float], alpha: float, family_hypotheses: int
) -> dict[str, bool]:
    if family_hypotheses < len(p_values):
        raise ValueError("family_hypotheses cannot be smaller than tested methods")
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    flags = {name: False for name in p_values}
    for index, (name, p_value) in enumerate(ordered):
        threshold = alpha / (family_hypotheses - index)
        if p_value > threshold:
            break
        flags[name] = True
    return flags


def _method_summary(
    game: GameSpec,
    method_version: str,
    outcomes: tuple[BacktestOutcome, ...],
    config: BacktestConfig,
) -> MethodBacktestResult:
    training_count = min(config.training_predictions, len(outcomes))
    training = outcomes[:training_count]
    evaluation = outcomes[training_count:]
    threshold = _percentile(
        [outcome.candidate.signal_score for outcome in training],
        config.alert_percentile,
    )
    alert_outcomes = tuple(
        outcome
        for outcome in evaluation
        if outcome.candidate.signal_score >= threshold
    )
    random_means: list[float] = []
    rng = random.Random(_random_seed(game.code, method_version))
    population = tuple(range(1, game.max_number + 1))
    for _ in range(config.random_strategies):
        matches = [
            len(
                set(rng.sample(population, 6))
                & set(outcome.winning_numbers)
            )
            for outcome in alert_outcomes
        ]
        random_means.append(fmean(matches) if matches else 0.0)
    observed = (
        fmean(outcome.matched for outcome in alert_outcomes)
        if alert_outcomes
        else 0.0
    )
    random_average = fmean(random_means) if random_means else 0.0
    p_value = (
        1
        + sum(random_mean >= observed for random_mean in random_means)
    ) / (1 + len(random_means))
    expected_random_matches = 36.0 / game.max_number
    midpoint = len(alert_outcomes) // 2
    first = alert_outcomes[:midpoint]
    second = alert_outcomes[midpoint:]
    first_effect = (
        fmean(outcome.matched for outcome in first) - expected_random_matches
        if first
        else 0.0
    )
    second_effect = (
        fmean(outcome.matched for outcome in second) - expected_random_matches
        if second
        else 0.0
    )
    return MethodBacktestResult(
        method_version=method_version,
        total_predictions=len(outcomes),
        alert_threshold=threshold,
        outcomes=outcomes,
        alert_outcomes=alert_outcomes,
        random_strategy_means=tuple(random_means),
        random_lines_per_strategy=len(alert_outcomes),
        p_value=p_value,
        effect_size=observed - random_average,
        first_half_effect=first_effect,
        second_half_effect=second_effect,
        corrected_significant=False,
        frozen_before_evaluation=(
            training_count == config.training_predictions
            and len(outcomes) > training_count
        ),
        training_predictions=training_count,
        training_cutoff_draw_id=(training[-1].draw_id if training else None),
    )


def walk_forward(
    game: GameSpec,
    draws: Sequence[DrawRecord],
    methods: Sequence[CandidateMethod],
    config: BacktestConfig,
) -> BacktestResult:
    ordered = tuple(
        sorted(
            (draw for draw in draws if draw.game_code == game.code),
            key=lambda draw: (draw.draw_date, draw.draw_time, draw.draw_id),
        )
    )
    outcomes_by_method: dict[str, list[BacktestOutcome]] = {
        method.method_version: [] for method in methods
    }
    for draw in ordered:
        cutoff = datetime.combine(draw.draw_date, time(7, 17), tzinfo=MANILA)
        snapshot = compute_features(ordered, game, cutoff)
        for method in methods:
            seed = derive_seed(
                game.code,
                draw.draw_date,
                method.method_version,
                cutoff,
            )
            candidate = method.generate(snapshot, game, seed)
            outcomes_by_method[method.method_version].append(
                BacktestOutcome(
                    draw_id=draw.draw_id,
                    target_draw_date=draw.draw_date.isoformat(),
                    winning_numbers=draw.sorted_numbers,
                    candidate=candidate,
                    matched=len(set(candidate.numbers) & set(draw.sorted_numbers)),
                )
            )
    summaries = {
        version: _method_summary(game, version, tuple(outcomes), config)
        for version, outcomes in outcomes_by_method.items()
    }
    flags = _holm_flags(
        {version: summary.p_value for version, summary in summaries.items()},
        config.family_alpha,
        config.family_hypotheses,
    )
    corrected = {
        version: replace(summary, corrected_significant=flags[version])
        for version, summary in summaries.items()
    }
    return BacktestResult(
        game_code=game.code,
        config=config,
        methods=MappingProxyType(corrected),
    )
