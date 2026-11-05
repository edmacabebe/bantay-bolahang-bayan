from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from lotto_signal.domain import DrawRecord, Prediction
from lotto_signal.reporting import performance_summary
from lotto_signal.store import RepositoryStore


MANILA = ZoneInfo("Asia/Manila")
AS_OF = date(2026, 11, 5)


def prediction(
    game_code: str,
    target_draw_date: date,
    numbers: tuple[int, ...] = (1, 2, 3, 4, 5, 6),
) -> Prediction:
    created_at = datetime.combine(
        target_draw_date,
        datetime.min.time(),
        tzinfo=MANILA,
    )
    return Prediction(
        prediction_id=(
            f"{game_code}-{target_draw_date.isoformat()}-ensemble_v1"
        ),
        game_code=game_code,
        target_draw_date=target_draw_date,
        method_version="ensemble_v1",
        numbers=numbers,
        raw_score=1.0,
        signal_score=1.0,
        seed=1,
        created_at=created_at,
        source_cutoff=created_at,
        feature_values={},
    )


def draw(
    game_code: str,
    draw_date: date,
    numbers: tuple[int, ...],
) -> DrawRecord:
    return DrawRecord(
        draw_id=f"{game_code}S{draw_date.strftime('%Y%m%d')}",
        game_code=game_code,
        draw_date=draw_date,
        draw_time="21:00:00+08:00",
        published_numbers=numbers,
        jackpot="10000000",
        total_winners=0,
        retrieved_at=datetime(2026, 11, 5, 7, 0, tzinfo=MANILA),
        source_url=(
            "https://lottomatik-backend.api-lottomatik.workers.dev/"
            "get-results"
        ),
    )


def test_performance_summary_uses_completed_lines_and_game_aware_baseline(
    tmp_path: Path,
) -> None:
    store = RepositoryStore(tmp_path)
    completed = (
        (
            prediction("LOTTO42", date(2026, 11, 3)),
            draw("LOTTO42", date(2026, 11, 3), (1, 10, 11, 12, 13, 14)),
        ),
        (
            prediction("ML45", date(2026, 11, 4)),
            draw("ML45", date(2026, 11, 4), (10, 11, 12, 13, 14, 15)),
        ),
        (
            prediction("GL55", date(2026, 11, 4)),
            draw("GL55", date(2026, 11, 4), (1, 2, 10, 11, 12, 13)),
        ),
        (
            prediction("UL58", date(2026, 10, 2)),
            draw("UL58", date(2026, 10, 2), (1, 2, 3, 10, 11, 12)),
        ),
    )
    for predicted, result in completed:
        store.append_prediction(predicted)
        store.merge_draws((result,))
    store.append_prediction(prediction("SL49", date(2026, 11, 5)))

    summary = performance_summary(store, AS_OF)

    assert summary["last_7_days"] == {
        "completed_lines": 3,
        "total_matches": 3,
        "total_predicted_numbers": 18,
        "average_matches_per_line": 1.0,
        "match_rate": 0.166667,
        "random_expected_average": 0.770563,
        "match_delta_vs_random": 0.229437,
        "score_distribution": {
            "0/6": 1,
            "1/6": 1,
            "2/6": 1,
            "3/6": 0,
            "4/6": 0,
            "5/6": 0,
            "6/6": 0,
        },
    }
    assert summary["last_30_days"] == summary["last_7_days"]
    assert summary["lifetime"] == {
        "completed_lines": 4,
        "total_matches": 6,
        "total_predicted_numbers": 24,
        "average_matches_per_line": 1.5,
        "match_rate": 0.25,
        "random_expected_average": 0.733094,
        "match_delta_vs_random": 0.766906,
        "score_distribution": {
            "0/6": 1,
            "1/6": 1,
            "2/6": 1,
            "3/6": 1,
            "4/6": 0,
            "5/6": 0,
            "6/6": 0,
        },
    }
    assert summary["tuning_guardrail"] == {
        "minimum_completed_lines": 30,
        "completed_lines": 4,
        "eligible_for_tuning_review": False,
        "automatic_tuning": False,
        "review_cycle": "weekly_walk_forward_audit",
    }


def test_performance_summary_empty_windows_are_null_not_zero(
    tmp_path: Path,
) -> None:
    summary = performance_summary(RepositoryStore(tmp_path), AS_OF)

    empty = {
        "completed_lines": 0,
        "total_matches": 0,
        "total_predicted_numbers": 0,
        "average_matches_per_line": None,
        "match_rate": None,
        "random_expected_average": None,
        "match_delta_vs_random": None,
        "score_distribution": {
            "0/6": 0,
            "1/6": 0,
            "2/6": 0,
            "3/6": 0,
            "4/6": 0,
            "5/6": 0,
            "6/6": 0,
        },
    }
    assert summary["last_7_days"] == empty
    assert summary["last_30_days"] == empty
    assert summary["lifetime"] == empty
    assert summary["tuning_guardrail"]["eligible_for_tuning_review"] is False
    assert summary["tuning_guardrail"]["automatic_tuning"] is False
