from __future__ import annotations

from datetime import date, datetime, timezone

from lotto_signal.domain import DrawRecord
from lotto_signal.features import compute_features
from lotto_signal.games import GAMES


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


def history() -> list[DrawRecord]:
    return [
        draw("old", date(2026, 6, 11), (1, 11, 12, 13, 14, 15)),
        draw("middle", date(2026, 9, 10), (1, 2, 7, 8, 9, 10)),
        draw("latest", date(2026, 10, 10), (1, 2, 3, 4, 5, 6)),
    ]


def test_features_use_exact_day_windows_and_exclude_cutoff_or_future() -> None:
    future = draw("future", date(2026, 10, 22), (37, 38, 39, 40, 41, 42))

    snapshot = compute_features(history() + [future], GAMES["LOTTO42"], AS_OF)

    assert snapshot.draw_count == 3
    assert snapshot.values["windows"]["30"]["draw_count"] == 1
    assert snapshot.values["windows"]["90"]["draw_count"] == 2
    assert snapshot.values["windows"]["365"]["draw_count"] == 3
    assert snapshot.values["windows"]["365"]["frequency"]["42"] == 0
    assert snapshot.values["latest_numbers"] == [1, 2, 3, 4, 5, 6]


def test_features_compute_frequency_gaps_and_supported_pairs() -> None:
    snapshot = compute_features(history(), GAMES["LOTTO42"], AS_OF)

    window = snapshot.values["windows"]["365"]
    assert window["frequency"]["1"] == 3
    assert window["frequency"]["2"] == 2
    assert snapshot.values["gaps"]["1"] == 0
    assert snapshot.values["gaps"]["7"] == 1
    assert snapshot.values["gaps"]["11"] == 2
    assert snapshot.values["gaps"]["42"] == 4
    assert window["pair_support"]["1-2"] == 2
    assert "1-11" not in window["pair_support"]
    assert window["triple_support"] == {}


def test_features_compute_composition_sum_spread_consecutive_and_overlap() -> None:
    snapshot = compute_features(history(), GAMES["LOTTO42"], AS_OF)

    window_30 = snapshot.values["windows"]["30"]
    assert window_30["odd_even_counts"] == {"3-3": 1}
    assert window_30["low_high_counts"] == {"6-0": 1}
    assert window_30["sum"] == {"min": 21, "max": 21, "mean": 21.0}
    assert window_30["spread"] == {"min": 5, "max": 5, "mean": 5.0}
    assert window_30["consecutive_pair_counts"] == {"5": 1}
    assert window_30["preceding_overlap_counts"] == {}

    window_365 = snapshot.values["windows"]["365"]
    assert window_365["preceding_overlap_counts"] == {"1": 1, "2": 1}
