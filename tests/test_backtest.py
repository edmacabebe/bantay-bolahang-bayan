from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from lotto_signal.backtest import BacktestConfig, walk_forward
from lotto_signal.domain import DrawRecord
from lotto_signal.features import FeatureSnapshot
from lotto_signal.games import GAMES, GameSpec
from lotto_signal.methods import Candidate


def make_draw(index: int, numbers: tuple[int, ...] = (1, 2, 3, 4, 5, 6)) -> DrawRecord:
    day = date(2025, 1, 1) + timedelta(days=index * 2)
    return DrawRecord(
        draw_id=f"LOTTO42S{index:07d}",
        game_code="LOTTO42",
        draw_date=day,
        draw_time="21:00:00+08:00",
        published_numbers=numbers,
        jackpot="10000000",
        total_winners=0,
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_url="fixture",
    )


@dataclass
class FixedMethod:
    method_version: str = "fixed_v1"
    seen_draw_counts: list[int] = field(default_factory=list)

    def generate(
        self, snapshot: FeatureSnapshot, game: GameSpec, seed: int
    ) -> Candidate:
        self.seen_draw_counts.append(snapshot.draw_count)
        return Candidate(
            game_code=game.code,
            method_version=self.method_version,
            numbers=(1, 2, 3, 4, 5, 6),
            raw_score=float(snapshot.draw_count),
            signal_score=float(snapshot.draw_count),
            seed=seed,
        )


def small_config() -> BacktestConfig:
    return BacktestConfig(
        min_predictions=4,
        min_alert_predictions=2,
        random_strategies=100,
        alert_percentile=0.85,
        family_alpha=0.01,
    )


def test_default_backtest_config_freezes_the_full_25_hypothesis_family() -> None:
    assert BacktestConfig().family_hypotheses == 25


def test_walk_forward_uses_only_strictly_prior_draws_and_scores_matches() -> None:
    method = FixedMethod()
    draws = [make_draw(index) for index in range(8)]

    result = walk_forward(GAMES["LOTTO42"], draws, [method], small_config())
    summary = result.methods["fixed_v1"]

    assert method.seen_draw_counts == list(range(8))
    assert [outcome.matched for outcome in summary.outcomes] == [6] * 8
    assert summary.total_predictions == 8
    assert len(summary.random_strategy_means) == 100
    assert all(value <= 6 for value in summary.random_strategy_means)


def test_walk_forward_is_reproducible_with_equal_one_line_random_budgets() -> None:
    draws = [make_draw(index) for index in range(10)]

    first = walk_forward(GAMES["LOTTO42"], draws, [FixedMethod()], small_config())
    second = walk_forward(GAMES["LOTTO42"], draws, [FixedMethod()], small_config())

    assert first == second
    summary = first.methods["fixed_v1"]
    assert summary.random_lines_per_strategy == len(summary.alert_outcomes)


def test_mutating_future_draw_cannot_change_earlier_backtest_outcomes() -> None:
    original = [make_draw(index) for index in range(10)]
    changed = original[:-1] + [make_draw(9, (7, 8, 9, 10, 11, 12))]

    first = walk_forward(GAMES["LOTTO42"], original, [FixedMethod()], small_config())
    second = walk_forward(GAMES["LOTTO42"], changed, [FixedMethod()], small_config())

    assert first.methods["fixed_v1"].outcomes[:-1] == second.methods["fixed_v1"].outcomes[:-1]
    assert first.methods["fixed_v1"].outcomes[-1].matched == 6
    assert second.methods["fixed_v1"].outcomes[-1].matched == 0
