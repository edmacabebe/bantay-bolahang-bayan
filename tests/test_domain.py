from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from lotto_signal.domain import DrawRecord, MonitorEvent, Prediction
from lotto_signal.games import GAMES


def make_draw(**overrides: object) -> DrawRecord:
    values: dict[str, object] = {
        "draw_id": "LOTTO42S0000299",
        "game_code": "LOTTO42",
        "draw_date": date(2026, 10, 15),
        "draw_time": "21:00:00+08:00",
        "published_numbers": (28, 36, 11, 17, 35, 14),
        "jackpot": "10000000.00",
        "total_winners": 0,
        "retrieved_at": datetime(2026, 10, 16, 1, tzinfo=timezone.utc),
        "source_url": "https://lottomatik.pcso.gov.ph/api/backend/get-results",
    }
    values.update(overrides)
    return DrawRecord(**values)


def test_games_define_exact_pcso_six_number_schedules() -> None:
    assert {
        code: (game.max_number, game.draw_weekdays)
        for code, game in GAMES.items()
    } == {
        "LOTTO42": (42, frozenset({1, 3, 5})),
        "ML45": (45, frozenset({0, 2, 4})),
        "SL49": (49, frozenset({1, 3, 6})),
        "GL55": (55, frozenset({0, 2, 5})),
        "UL58": (58, frozenset({1, 4, 6})),
    }


def test_draw_preserves_published_order_and_derives_sorted_numbers() -> None:
    draw = make_draw()

    assert draw.published_numbers == (28, 36, 11, 17, 35, 14)
    assert draw.sorted_numbers == (11, 14, 17, 28, 35, 36)
    assert draw.to_dict() == {
        "draw_id": "LOTTO42S0000299",
        "game_code": "LOTTO42",
        "draw_date": "2026-10-15",
        "draw_time": "21:00:00+08:00",
        "published_numbers": [28, 36, 11, 17, 35, 14],
        "sorted_numbers": [11, 14, 17, 28, 35, 36],
        "jackpot": "10000000.00",
        "total_winners": 0,
        "retrieved_at": "2026-10-16T01:00:00+00:00",
        "source_url": "https://lottomatik.pcso.gov.ph/api/backend/get-results",
        "fingerprint": draw.fingerprint,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"published_numbers": (1, 2, 3, 4, 5)}, "six numbers"),
        ({"published_numbers": (1, 2, 3, 4, 5, 5)}, "unique"),
        ({"published_numbers": (1, 2, 3, 4, 5, 43)}, "1..42"),
        ({"retrieved_at": datetime(2026, 10, 16, 1)}, "timezone-aware"),
        ({"draw_time": "21:00:00"}, "draw_time must include a timezone"),
        ({"draw_time": "20:00:00+08:00"}, "official 9 PM Manila"),
        ({"draw_time": "21:00:00+00:00"}, "official 9 PM Manila"),
        ({"draw_date": date(2026, 10, 16)}, "scheduled weekday"),
        ({"game_code": "UNKNOWN"}, "unknown game"),
    ],
)
def test_draw_rejects_invalid_inputs(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        make_draw(**overrides)


def test_prediction_and_event_serialize_nested_values() -> None:
    prediction = Prediction(
        prediction_id="pred-1",
        game_code="LOTTO42",
        target_draw_date=date(2026, 10, 17),
        method_version="ensemble_v1",
        numbers=(1, 8, 17, 23, 31, 42),
        raw_score=2.25,
        signal_score=1.5,
        seed=123,
        created_at=datetime(2026, 10, 17, 0, tzinfo=timezone.utc),
        source_cutoff=datetime(2026, 10, 16, 23, 17, tzinfo=timezone.utc),
        feature_values={"window": 30, "numbers": (1, 8)},
    )
    event = MonitorEvent(
        event_id="evt-1",
        kind="research_signal",
        created_at=datetime(2026, 10, 17, 0, tzinfo=timezone.utc),
        payload={"prediction": prediction.to_dict()},
    )

    assert prediction.to_dict()["numbers"] == [1, 8, 17, 23, 31, 42]
    assert prediction.to_dict()["feature_values"]["numbers"] == [1, 8]
    assert event.to_dict()["payload"]["prediction"]["game_code"] == "LOTTO42"
