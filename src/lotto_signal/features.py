from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations
from statistics import fmean
from types import MappingProxyType
from typing import Any

from .domain import DrawRecord
from .games import GameSpec


WINDOW_DAYS = (30, 90, 365)


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    game_code: str
    as_of: datetime
    draw_count: int
    values: Mapping[str, Any]


def _draw_datetime(draw: DrawRecord) -> datetime:
    return datetime.fromisoformat(f"{draw.draw_date.isoformat()}T{draw.draw_time}")


def _summary(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(values), "max": max(values), "mean": fmean(values)}


def _window_features(
    draws: Sequence[DrawRecord], game: GameSpec
) -> dict[str, Any]:
    frequencies = Counter(
        number for draw in draws for number in draw.published_numbers
    )
    pair_counts: Counter[tuple[int, int]] = Counter()
    triple_counts: Counter[tuple[int, int, int]] = Counter()
    odd_even_counts: Counter[str] = Counter()
    low_high_counts: Counter[str] = Counter()
    consecutive_counts: Counter[str] = Counter()
    sums: list[int] = []
    spreads: list[int] = []
    low_ceiling = game.max_number // 2
    for draw in draws:
        ordered = draw.sorted_numbers
        pair_counts.update(combinations(ordered, 2))
        triple_counts.update(combinations(ordered, 3))
        odd = sum(number % 2 for number in ordered)
        low = sum(number <= low_ceiling for number in ordered)
        odd_even_counts[f"{odd}-{6 - odd}"] += 1
        low_high_counts[f"{low}-{6 - low}"] += 1
        consecutive = sum(
            right - left == 1 for left, right in zip(ordered, ordered[1:])
        )
        consecutive_counts[str(consecutive)] += 1
        sums.append(sum(ordered))
        spreads.append(ordered[-1] - ordered[0])
    overlap_counts: Counter[str] = Counter()
    for previous, current in zip(draws, draws[1:]):
        overlap_counts[str(len(set(previous.sorted_numbers) & set(current.sorted_numbers)))] += 1
    return {
        "draw_count": len(draws),
        "frequency": {
            str(number): frequencies[number]
            for number in range(1, game.max_number + 1)
        },
        "pair_support": {
            f"{left}-{right}": count
            for (left, right), count in sorted(pair_counts.items())
            if count >= 2
        },
        "triple_support": {
            "-".join(map(str, triple)): count
            for triple, count in sorted(triple_counts.items())
            if count >= 2
        },
        "odd_even_counts": dict(sorted(odd_even_counts.items())),
        "low_high_counts": dict(sorted(low_high_counts.items())),
        "sum": _summary(sums),
        "spread": _summary(spreads),
        "consecutive_pair_counts": dict(sorted(consecutive_counts.items())),
        "preceding_overlap_counts": dict(sorted(overlap_counts.items())),
    }


def compute_features(
    draws: Sequence[DrawRecord], game: GameSpec, as_of: datetime
) -> FeatureSnapshot:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    prior = sorted(
        (
            draw
            for draw in draws
            if draw.game_code == game.code and _draw_datetime(draw) < as_of
        ),
        key=lambda draw: (_draw_datetime(draw), draw.draw_id),
    )
    windows: dict[str, Any] = {}
    for days in WINDOW_DAYS:
        cutoff = as_of - timedelta(days=days)
        included = [draw for draw in prior if _draw_datetime(draw) >= cutoff]
        windows[str(days)] = _window_features(included, game)
    gaps: dict[str, int] = {}
    newest_first = list(reversed(prior))
    for number in range(1, game.max_number + 1):
        gap = next(
            (
                index
                for index, draw in enumerate(newest_first)
                if number in draw.published_numbers
            ),
            len(prior) + 1,
        )
        gaps[str(number)] = gap
    values: dict[str, Any] = {
        "windows": windows,
        "gaps": gaps,
        "latest_numbers": list(prior[-1].published_numbers) if prior else [],
    }
    return FeatureSnapshot(
        game_code=game.code,
        as_of=as_of,
        draw_count=len(prior),
        values=MappingProxyType(values),
    )
