from __future__ import annotations

from datetime import date, datetime, timezone

from lotto_signal.domain import DrawRecord
from lotto_signal.features import compute_features
from lotto_signal.games import GAMES
from lotto_signal.methods import (
    METHODS,
    Candidate,
    ScoredMethod,
    derive_seed,
)


AS_OF = datetime(2026, 10, 20, 0, tzinfo=timezone.utc)


def draw(draw_id: str, day: date, numbers: tuple[int, ...]) -> DrawRecord:
    return DrawRecord(
        draw_id=draw_id,
        game_code="LOTTO42",
        draw_date=day,
        draw_time="21:00:00+08:00",
        published_numbers=numbers,
        jackpot="10000000",
        total_winners=0,
        retrieved_at=AS_OF,
        source_url="fixture",
    )


def snapshot():
    draws = [
        draw("d1", date(2026, 8, 1), (1, 2, 3, 4, 5, 6)),
        draw("d2", date(2026, 9, 1), (1, 2, 7, 8, 9, 10)),
        draw("d3", date(2026, 10, 1), (1, 2, 11, 12, 13, 14)),
        draw("d4", date(2026, 10, 10), (1, 2, 15, 16, 17, 18)),
    ]
    return compute_features(draws, GAMES["LOTTO42"], AS_OF)


def test_stable_seed_uses_sha256_inputs_not_process_hash() -> None:
    seed = derive_seed(
        "LOTTO42",
        date(2026, 10, 22),
        "ensemble_v1",
        datetime(2026, 10, 21, 23, 17, tzinfo=timezone.utc),
    )

    assert seed == 17374293626765608278


def test_all_frozen_methods_return_reproducible_valid_candidates() -> None:
    feature_snapshot = snapshot()
    assert set(METHODS) == {
        "frequency_v1",
        "gap_v1",
        "pair_v1",
        "balanced_v1",
        "ensemble_v1",
        "uniform_random_v1",
    }

    for version, method in METHODS.items():
        first = method.generate(feature_snapshot, GAMES["LOTTO42"], seed=12345)
        second = method.generate(feature_snapshot, GAMES["LOTTO42"], seed=12345)
        assert first == second
        assert first.method_version == version
        assert len(first.numbers) == len(set(first.numbers)) == 6
        assert min(first.numbers) >= 1
        assert max(first.numbers) <= 42


def test_scored_method_compares_candidate_with_exactly_10000_uniform_lines() -> None:
    score_calls = 0

    def score(numbers: tuple[int, ...], _snapshot, _game) -> float:
        nonlocal score_calls
        score_calls += 1
        return float(sum(numbers))

    method = ScoredMethod(
        "counted_v1",
        selector=lambda _snapshot, _game, _rng: (1, 2, 3, 4, 5, 6),
        scorer=score,
    )

    result = method.generate(snapshot(), GAMES["LOTTO42"], seed=9)

    assert isinstance(result, Candidate)
    assert score_calls == 10_001


def test_seeded_tie_breaking_is_repeatable() -> None:
    empty = compute_features([], GAMES["LOTTO42"], AS_OF)

    first = METHODS["frequency_v1"].generate(empty, GAMES["LOTTO42"], seed=77)
    second = METHODS["frequency_v1"].generate(empty, GAMES["LOTTO42"], seed=77)

    assert first == second


def test_future_draw_mutation_cannot_change_earlier_candidate() -> None:
    base = [draw("past", date(2026, 10, 10), (1, 2, 3, 4, 5, 6))]
    future_a = draw("future", date(2026, 10, 21), (7, 8, 9, 10, 11, 12))
    future_b = draw("future", date(2026, 10, 21), (31, 32, 33, 34, 35, 36))
    method = METHODS["ensemble_v1"]

    candidate_a = method.generate(
        compute_features(base + [future_a], GAMES["LOTTO42"], AS_OF),
        GAMES["LOTTO42"],
        seed=88,
    )
    candidate_b = method.generate(
        compute_features(base + [future_b], GAMES["LOTTO42"], AS_OF),
        GAMES["LOTTO42"],
        seed=88,
    )

    assert candidate_a == candidate_b
