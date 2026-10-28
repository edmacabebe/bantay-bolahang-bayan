from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from itertools import combinations
from statistics import median, pstdev
from typing import Protocol

from .features import FeatureSnapshot
from .games import GameSpec


BASELINE_SAMPLES = 10_000
Selector = Callable[[FeatureSnapshot, GameSpec, random.Random], tuple[int, ...]]
Scorer = Callable[[tuple[int, ...], FeatureSnapshot, GameSpec], float]
PreparedScorer = Callable[[tuple[int, ...]], float]
ScorerFactory = Callable[[FeatureSnapshot, GameSpec], PreparedScorer]


@dataclass(frozen=True, slots=True)
class Candidate:
    game_code: str
    method_version: str
    numbers: tuple[int, ...]
    raw_score: float
    signal_score: float
    seed: int


class CandidateMethod(Protocol):
    method_version: str

    def generate(
        self, snapshot: FeatureSnapshot, game: GameSpec, seed: int
    ) -> Candidate: ...


def derive_seed(
    game_code: str,
    target_draw_date: date,
    method_version: str,
    source_cutoff: datetime,
) -> int:
    material = "|".join(
        (
            game_code,
            target_draw_date.isoformat(),
            method_version,
            source_cutoff.isoformat(),
        )
    )
    return int(hashlib.sha256(material.encode()).hexdigest()[:16], 16)


@dataclass(frozen=True, slots=True)
class ScoredMethod:
    method_version: str
    selector: Selector
    scorer: Scorer
    scorer_factory: ScorerFactory | None = None

    def generate(
        self, snapshot: FeatureSnapshot, game: GameSpec, seed: int
    ) -> Candidate:
        selection_rng = random.Random(seed)
        numbers = tuple(sorted(self.selector(snapshot, game, selection_rng)))
        if len(numbers) != 6 or len(set(numbers)) != 6:
            raise ValueError(f"{self.method_version} produced an invalid combination")
        if numbers[0] < 1 or numbers[-1] > game.max_number:
            raise ValueError(f"{self.method_version} produced out-of-range numbers")
        prepared_score = (
            self.scorer_factory(snapshot, game)
            if self.scorer_factory is not None
            else lambda values: self.scorer(values, snapshot, game)
        )
        raw_score = prepared_score(numbers)
        baseline_rng = random.Random(seed ^ 0xA5A5A5A5A5A5A5A5)
        population = tuple(range(1, game.max_number + 1))
        baseline_scores = [
            prepared_score(tuple(sorted(baseline_rng.sample(population, 6))))
            for _ in range(BASELINE_SAMPLES)
        ]
        spread = pstdev(baseline_scores)
        signal_score = 0.0 if spread == 0 else (raw_score - median(baseline_scores)) / spread
        return Candidate(
            game_code=game.code,
            method_version=self.method_version,
            numbers=numbers,
            raw_score=raw_score,
            signal_score=signal_score,
            seed=seed,
        )


def _window(snapshot: FeatureSnapshot, days: int = 365) -> Mapping[str, object]:
    return snapshot.values["windows"][str(days)]


def _frequency_weights(snapshot: FeatureSnapshot, game: GameSpec) -> dict[int, float]:
    weights = {number: 0.0 for number in range(1, game.max_number + 1)}
    for days, window_weight in ((30, 0.5), (90, 0.3), (365, 0.2)):
        window = _window(snapshot, days)
        draw_count = int(window["draw_count"])
        denominator = max(draw_count, 1)
        frequency = window["frequency"]
        for number in weights:
            weights[number] += window_weight * int(frequency[str(number)]) / denominator
    return weights


def _gap_weights(snapshot: FeatureSnapshot, game: GameSpec) -> dict[int, float]:
    gaps = snapshot.values["gaps"]
    return {
        number: math.log1p(int(gaps[str(number)]))
        for number in range(1, game.max_number + 1)
    }


def _pair_weights(snapshot: FeatureSnapshot, game: GameSpec) -> dict[int, float]:
    weights = {number: 0.0 for number in range(1, game.max_number + 1)}
    for pair, count in _window(snapshot)["pair_support"].items():
        left, right = (int(value) for value in pair.split("-"))
        weights[left] += float(count)
        weights[right] += float(count)
    return weights


def _rank_selector(weight_getter: Callable[[FeatureSnapshot, GameSpec], dict[int, float]]) -> Selector:
    def select(
        snapshot: FeatureSnapshot, game: GameSpec, rng: random.Random
    ) -> tuple[int, ...]:
        weights = weight_getter(snapshot, game)
        ranked = sorted(
            weights,
            key=lambda number: (-weights[number], rng.random(), number),
        )
        return tuple(sorted(ranked[:6]))

    return select


def _frequency_score(
    numbers: tuple[int, ...], snapshot: FeatureSnapshot, game: GameSpec
) -> float:
    weights = _frequency_weights(snapshot, game)
    return sum(weights[number] for number in numbers)


def _prepare_frequency(snapshot: FeatureSnapshot, game: GameSpec) -> PreparedScorer:
    weights = _frequency_weights(snapshot, game)
    return lambda numbers: sum(weights[number] for number in numbers)


def _gap_score(
    numbers: tuple[int, ...], snapshot: FeatureSnapshot, game: GameSpec
) -> float:
    weights = _gap_weights(snapshot, game)
    return sum(weights[number] for number in numbers)


def _prepare_gap(snapshot: FeatureSnapshot, game: GameSpec) -> PreparedScorer:
    weights = _gap_weights(snapshot, game)
    return lambda numbers: sum(weights[number] for number in numbers)


def _pair_score(
    numbers: tuple[int, ...], snapshot: FeatureSnapshot, game: GameSpec
) -> float:
    support = _window(snapshot)["pair_support"]
    return sum(
        float(support.get(f"{left}-{right}", 0))
        for left, right in combinations(numbers, 2)
    )


def _prepare_pair(snapshot: FeatureSnapshot, game: GameSpec) -> PreparedScorer:
    support = _window(snapshot)["pair_support"]

    def score(numbers: tuple[int, ...]) -> float:
        return sum(
            float(support.get(f"{left}-{right}", 0))
            for left, right in combinations(numbers, 2)
        )

    return score


def _modal_composition(counts: Mapping[str, int], default: str) -> tuple[int, int]:
    if not counts:
        return tuple(int(value) for value in default.split("-"))  # type: ignore[return-value]
    key = min(counts, key=lambda item: (-int(counts[item]), item))
    return tuple(int(value) for value in key.split("-"))  # type: ignore[return-value]


def _balanced_score(
    numbers: tuple[int, ...], snapshot: FeatureSnapshot, game: GameSpec
) -> float:
    window = _window(snapshot)
    target_odd, _ = _modal_composition(window["odd_even_counts"], "3-3")
    target_low, _ = _modal_composition(window["low_high_counts"], "3-3")
    target_sum = window["sum"]["mean"]
    target_spread = window["spread"]["mean"]
    if target_sum is None:
        target_sum = 3 * (game.max_number + 1)
    if target_spread is None:
        target_spread = game.max_number * 0.7
    odd = sum(number % 2 for number in numbers)
    low = sum(number <= game.max_number // 2 for number in numbers)
    total = sum(numbers)
    spread = max(numbers) - min(numbers)
    consecutive = sum(
        right - left == 1 for left, right in zip(numbers, numbers[1:])
    )
    return -(
        abs(odd - target_odd)
        + abs(low - target_low)
        + abs(total - float(target_sum)) / game.max_number
        + abs(spread - float(target_spread)) / game.max_number
        + max(0, consecutive - 2) * 0.25
    )


def _prepare_balanced(snapshot: FeatureSnapshot, game: GameSpec) -> PreparedScorer:
    window = _window(snapshot)
    target_odd, _ = _modal_composition(window["odd_even_counts"], "3-3")
    target_low, _ = _modal_composition(window["low_high_counts"], "3-3")
    target_sum = window["sum"]["mean"]
    target_spread = window["spread"]["mean"]
    if target_sum is None:
        target_sum = 3 * (game.max_number + 1)
    if target_spread is None:
        target_spread = game.max_number * 0.7

    def score(numbers: tuple[int, ...]) -> float:
        odd = sum(number % 2 for number in numbers)
        low = sum(number <= game.max_number // 2 for number in numbers)
        total = sum(numbers)
        spread = max(numbers) - min(numbers)
        consecutive = sum(
            right - left == 1 for left, right in zip(numbers, numbers[1:])
        )
        return -(
            abs(odd - target_odd)
            + abs(low - target_low)
            + abs(total - float(target_sum)) / game.max_number
            + abs(spread - float(target_spread)) / game.max_number
            + max(0, consecutive - 2) * 0.25
        )

    return score


def _random_search_selector(
    scorer_factory: ScorerFactory, samples: int = 2_000
) -> Selector:
    def select(
        snapshot: FeatureSnapshot, game: GameSpec, rng: random.Random
    ) -> tuple[int, ...]:
        population = tuple(range(1, game.max_number + 1))
        scorer = scorer_factory(snapshot, game)
        best: tuple[int, ...] | None = None
        best_score = float("-inf")
        for _ in range(samples):
            candidate = tuple(sorted(rng.sample(population, 6)))
            score = scorer(candidate)
            if score > best_score or (score == best_score and (best is None or candidate < best)):
                best = candidate
                best_score = score
        if best is None:
            raise AssertionError("random search produced no candidate")
        return best

    return select


def _ensemble_score(
    numbers: tuple[int, ...], snapshot: FeatureSnapshot, game: GameSpec
) -> float:
    frequency = _frequency_score(numbers, snapshot, game)
    gap = _gap_score(numbers, snapshot, game) / 10.0
    pair = _pair_score(numbers, snapshot, game) / 10.0
    balanced = _balanced_score(numbers, snapshot, game)
    return frequency + gap + pair + balanced


def _prepare_ensemble(snapshot: FeatureSnapshot, game: GameSpec) -> PreparedScorer:
    frequency = _prepare_frequency(snapshot, game)
    gap = _prepare_gap(snapshot, game)
    pair = _prepare_pair(snapshot, game)
    balanced = _prepare_balanced(snapshot, game)
    return lambda numbers: (
        frequency(numbers)
        + gap(numbers) / 10.0
        + pair(numbers) / 10.0
        + balanced(numbers)
    )


def _uniform_selector(
    snapshot: FeatureSnapshot, game: GameSpec, rng: random.Random
) -> tuple[int, ...]:
    return tuple(sorted(rng.sample(range(1, game.max_number + 1), 6)))


def _zero_score(
    numbers: tuple[int, ...], snapshot: FeatureSnapshot, game: GameSpec
) -> float:
    return 0.0


METHODS: Mapping[str, CandidateMethod] = {
    "frequency_v1": ScoredMethod(
        "frequency_v1",
        _rank_selector(_frequency_weights),
        _frequency_score,
        _prepare_frequency,
    ),
    "gap_v1": ScoredMethod(
        "gap_v1", _rank_selector(_gap_weights), _gap_score, _prepare_gap
    ),
    "pair_v1": ScoredMethod(
        "pair_v1", _random_search_selector(_prepare_pair), _pair_score, _prepare_pair
    ),
    "balanced_v1": ScoredMethod(
        "balanced_v1",
        _random_search_selector(_prepare_balanced),
        _balanced_score,
        _prepare_balanced,
    ),
    "ensemble_v1": ScoredMethod(
        "ensemble_v1",
        _random_search_selector(_prepare_ensemble),
        _ensemble_score,
        _prepare_ensemble,
    ),
    "uniform_random_v1": ScoredMethod(
        "uniform_random_v1", _uniform_selector, _zero_score
    ),
}
