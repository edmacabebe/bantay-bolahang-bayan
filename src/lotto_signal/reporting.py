from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .games import GAMES
from .store import RepositoryStore


MINIMUM_TUNING_LINES = 30


@dataclass(frozen=True, slots=True)
class _CompletedLine:
    target_draw_date: date
    matched: int
    random_expected_matches: float


def _completed_lines(
    store: RepositoryStore,
    as_of: date,
) -> tuple[_CompletedLine, ...]:
    completed: list[_CompletedLine] = []
    for game_code, game in GAMES.items():
        draws_by_date = {
            draw.draw_date: draw for draw in store.load_draws(game_code)
        }
        for prediction in store.load_predictions(game_code):
            if prediction.target_draw_date > as_of:
                continue
            draw = draws_by_date.get(prediction.target_draw_date)
            if draw is None:
                continue
            completed.append(
                _CompletedLine(
                    target_draw_date=prediction.target_draw_date,
                    matched=len(
                        set(prediction.numbers) & set(draw.sorted_numbers)
                    ),
                    random_expected_matches=36 / game.max_number,
                )
            )
    return tuple(
        sorted(
            completed,
            key=lambda item: (
                item.target_draw_date,
                item.random_expected_matches,
            ),
        )
    )


def _window(
    completed: tuple[_CompletedLine, ...],
    since: date | None,
) -> dict[str, Any]:
    selected = tuple(
        line
        for line in completed
        if since is None or line.target_draw_date >= since
    )
    completed_lines = len(selected)
    total_matches = sum(line.matched for line in selected)
    distribution = {
        f"{matched}/6": sum(line.matched == matched for line in selected)
        for matched in range(7)
    }
    if completed_lines == 0:
        average_matches = None
        match_rate = None
        random_expected_average = None
        match_delta = None
    else:
        average_matches = round(total_matches / completed_lines, 6)
        match_rate = round(total_matches / (6 * completed_lines), 6)
        random_expected_average = round(
            sum(line.random_expected_matches for line in selected)
            / completed_lines,
            6,
        )
        match_delta = round(
            average_matches - random_expected_average,
            6,
        )
    return {
        "completed_lines": completed_lines,
        "total_matches": total_matches,
        "total_predicted_numbers": completed_lines * 6,
        "average_matches_per_line": average_matches,
        "match_rate": match_rate,
        "random_expected_average": random_expected_average,
        "match_delta_vs_random": match_delta,
        "score_distribution": distribution,
    }


def performance_summary(
    store: RepositoryStore,
    as_of: date,
) -> dict[str, Any]:
    completed = _completed_lines(store, as_of)
    lifetime = _window(completed, None)
    return {
        "last_7_days": _window(completed, as_of - timedelta(days=6)),
        "last_30_days": _window(completed, as_of - timedelta(days=29)),
        "lifetime": lifetime,
        "tuning_guardrail": {
            "minimum_completed_lines": MINIMUM_TUNING_LINES,
            "completed_lines": lifetime["completed_lines"],
            "eligible_for_tuning_review": (
                lifetime["completed_lines"] >= MINIMUM_TUNING_LINES
            ),
            "automatic_tuning": False,
            "review_cycle": "weekly_walk_forward_audit",
        },
    }
