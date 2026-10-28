from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

from .games import DRAW_DATE_EXCEPTIONS, GAMES


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _validate_numbers(game_code: str, numbers: tuple[int, ...]) -> None:
    game = GAMES.get(game_code)
    if game is None:
        raise ValueError(f"unknown game: {game_code}")
    if len(numbers) != 6:
        raise ValueError("a draw must contain six numbers")
    if len(set(numbers)) != 6:
        raise ValueError("draw numbers must be unique")
    if any(number < 1 or number > game.max_number for number in numbers):
        raise ValueError(f"draw numbers must be in 1..{game.max_number}")


@dataclass(frozen=True, slots=True)
class DrawRecord:
    draw_id: str
    game_code: str
    draw_date: date
    draw_time: str
    published_numbers: tuple[int, ...]
    jackpot: str
    total_winners: int
    retrieved_at: datetime
    source_url: str
    sorted_numbers: tuple[int, ...] = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_numbers(self.game_code, self.published_numbers)
        _aware(self.retrieved_at, "retrieved_at")
        try:
            draw_at = datetime.fromisoformat(
                f"{self.draw_date.isoformat()}T{self.draw_time}"
            )
        except ValueError as error:
            raise ValueError("draw_time must be an ISO-8601 time") from error
        if draw_at.tzinfo is None or draw_at.utcoffset() is None:
            raise ValueError("draw_time must include a timezone")
        game = GAMES[self.game_code]
        if (
            self.draw_date.weekday() not in game.draw_weekdays
            and self.draw_date not in DRAW_DATE_EXCEPTIONS[self.game_code]
        ):
            raise ValueError("draw_date is not a scheduled weekday")
        if not self.draw_id:
            raise ValueError("draw_id is required")
        if self.total_winners < 0:
            raise ValueError("total_winners cannot be negative")
        sorted_numbers = tuple(sorted(self.published_numbers))
        object.__setattr__(self, "sorted_numbers", sorted_numbers)
        fingerprint_payload = {
            "draw_id": self.draw_id,
            "game_code": self.game_code,
            "draw_date": self.draw_date.isoformat(),
            "draw_time": self.draw_time,
            "published_numbers": list(self.published_numbers),
            "jackpot": self.jackpot,
            "total_winners": self.total_winners,
        }
        canonical = json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))
        object.__setattr__(self, "fingerprint", hashlib.sha256(canonical.encode()).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        return {
            "draw_id": self.draw_id,
            "game_code": self.game_code,
            "draw_date": self.draw_date.isoformat(),
            "draw_time": self.draw_time,
            "published_numbers": list(self.published_numbers),
            "sorted_numbers": list(self.sorted_numbers),
            "jackpot": self.jackpot,
            "total_winners": self.total_winners,
            "retrieved_at": self.retrieved_at.isoformat(),
            "source_url": self.source_url,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class DrawRevision:
    revision_id: str
    draw_id: str
    observed_at: datetime
    previous_fingerprint: str
    replacement: DrawRecord

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "draw_id": self.draw_id,
            "observed_at": self.observed_at.isoformat(),
            "previous_fingerprint": self.previous_fingerprint,
            "replacement": self.replacement.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Prediction:
    prediction_id: str
    game_code: str
    target_draw_date: date
    method_version: str
    numbers: tuple[int, ...]
    raw_score: float
    signal_score: float
    seed: int
    created_at: datetime
    source_cutoff: datetime
    feature_values: Mapping[str, Any]

    def __post_init__(self) -> None:
        _validate_numbers(self.game_code, self.numbers)
        _aware(self.created_at, "created_at")
        _aware(self.source_cutoff, "source_cutoff")

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "game_code": self.game_code,
            "target_draw_date": self.target_draw_date.isoformat(),
            "method_version": self.method_version,
            "numbers": list(self.numbers),
            "raw_score": self.raw_score,
            "signal_score": self.signal_score,
            "seed": self.seed,
            "created_at": self.created_at.isoformat(),
            "source_cutoff": self.source_cutoff.isoformat(),
            "feature_values": _json_safe(self.feature_values),
        }


@dataclass(frozen=True, slots=True)
class PredictionOutcome:
    outcome_id: str
    prediction_id: str
    game_code: str
    target_draw_date: date
    draw_id: str
    draw_fingerprint: str
    predicted_numbers: tuple[int, ...]
    winning_numbers: tuple[int, ...]
    matched: int
    scored_at: datetime

    def __post_init__(self) -> None:
        _validate_numbers(self.game_code, self.predicted_numbers)
        _validate_numbers(self.game_code, self.winning_numbers)
        _aware(self.scored_at, "scored_at")
        if self.matched != len(
            set(self.predicted_numbers) & set(self.winning_numbers)
        ):
            raise ValueError("matched count does not match outcome numbers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "prediction_id": self.prediction_id,
            "game_code": self.game_code,
            "target_draw_date": self.target_draw_date.isoformat(),
            "draw_id": self.draw_id,
            "draw_fingerprint": self.draw_fingerprint,
            "predicted_numbers": list(self.predicted_numbers),
            "winning_numbers": list(self.winning_numbers),
            "matched": self.matched,
            "scored_at": self.scored_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class MonitorEvent:
    event_id: str
    kind: str
    created_at: datetime
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        _aware(self.created_at, "created_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "created_at": self.created_at.isoformat(),
            "payload": _json_safe(self.payload),
        }
