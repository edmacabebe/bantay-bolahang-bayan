from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .domain import (
    DrawRecord,
    DrawRevision,
    MonitorEvent,
    Prediction,
    PredictionOutcome,
)
from .games import GAMES


@dataclass(frozen=True, slots=True)
class MergeResult:
    inserted: int = 0
    unchanged: int = 0
    revised: int = 0
    revised_draw_ids: tuple[str, ...] = ()
    revision_ids: tuple[str, ...] = ()


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content)
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rendered = "".join(f"{_canonical(row)}\n" for row in rows)
    _atomic_write(path, rendered)


def _draw_from_dict(payload: dict[str, Any]) -> DrawRecord:
    return DrawRecord(
        draw_id=payload["draw_id"],
        game_code=payload["game_code"],
        draw_date=date.fromisoformat(payload["draw_date"]),
        draw_time=payload["draw_time"],
        published_numbers=tuple(payload["published_numbers"]),
        jackpot=payload["jackpot"],
        total_winners=int(payload["total_winners"]),
        retrieved_at=datetime.fromisoformat(payload["retrieved_at"]),
        source_url=payload["source_url"],
    )


def _prediction_from_dict(payload: dict[str, Any]) -> Prediction:
    return Prediction(
        prediction_id=payload["prediction_id"],
        game_code=payload["game_code"],
        target_draw_date=date.fromisoformat(payload["target_draw_date"]),
        method_version=payload["method_version"],
        numbers=tuple(payload["numbers"]),
        raw_score=float(payload["raw_score"]),
        signal_score=float(payload["signal_score"]),
        seed=int(payload["seed"]),
        created_at=datetime.fromisoformat(payload["created_at"]),
        source_cutoff=datetime.fromisoformat(payload["source_cutoff"]),
        feature_values=payload["feature_values"],
    )


class RepositoryStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _draw_path(self, game_code: str) -> Path:
        return self.root / "data" / "draws" / f"{game_code}.jsonl"

    def _revision_path(self, game_code: str) -> Path:
        return self.root / "data" / "revisions" / f"{game_code}.jsonl"

    def _prediction_path(self, game_code: str) -> Path:
        return self.root / "data" / "predictions" / f"{game_code}.jsonl"

    def _outcome_path(self, game_code: str) -> Path:
        return self.root / "data" / "outcomes" / f"{game_code}.jsonl"

    def merge_draws(self, records: Iterable[DrawRecord]) -> MergeResult:
        grouped: dict[str, list[DrawRecord]] = {}
        for record in records:
            grouped.setdefault(record.game_code, []).append(record)
        inserted = unchanged = revised = 0
        revised_draw_ids: list[str] = []
        revision_ids: list[str] = []
        for game_code, incoming in grouped.items():
            original_rows = _read_jsonl(self._draw_path(game_code))
            originals = {
                row["draw_id"]: _draw_from_dict(row) for row in original_rows
            }
            revision_rows = _read_jsonl(self._revision_path(game_code))
            current = dict(originals)
            for row in revision_rows:
                replacement = _draw_from_dict(row["replacement"])
                current[replacement.draw_id] = replacement
            date_to_id = {
                record.draw_date: record.draw_id for record in current.values()
            }
            for record in incoming:
                same_date_id = date_to_id.get(record.draw_date)
                if same_date_id is not None and same_date_id != record.draw_id:
                    raise ValueError(
                        f"duplicate game/date: {game_code} "
                        f"{record.draw_date.isoformat()} has IDs "
                        f"{same_date_id} and {record.draw_id}"
                    )
                existing = current.get(record.draw_id)
                if existing is None:
                    originals[record.draw_id] = record
                    current[record.draw_id] = record
                    inserted += 1
                    date_to_id[record.draw_date] = record.draw_id
                elif existing.fingerprint == record.fingerprint:
                    unchanged += 1
                else:
                    revision = DrawRevision(
                        revision_id=(
                            f"{record.draw_id}:{len(revision_rows) + 1:06d}:"
                            f"{record.fingerprint}"
                        ),
                        draw_id=record.draw_id,
                        observed_at=record.retrieved_at,
                        previous_fingerprint=existing.fingerprint,
                        replacement=record,
                    )
                    revision_rows.append(revision.to_dict())
                    revised += 1
                    revised_draw_ids.append(record.draw_id)
                    revision_ids.append(revision.revision_id)
                    current[record.draw_id] = record
            original_values = sorted(
                originals.values(),
                key=lambda item: (item.draw_date, item.draw_time, item.draw_id),
            )
            _write_jsonl(
                self._draw_path(game_code),
                (record.to_dict() for record in original_values),
            )
            if revision_rows:
                _write_jsonl(self._revision_path(game_code), revision_rows)
        return MergeResult(
            inserted,
            unchanged,
            revised,
            tuple(sorted(set(revised_draw_ids))),
            tuple(sorted(set(revision_ids))),
        )

    def load_draws(
        self, game_code: str, before: datetime | None = None
    ) -> tuple[DrawRecord, ...]:
        if game_code not in GAMES:
            raise ValueError(f"unknown game: {game_code}")
        current = {
            row["draw_id"]: _draw_from_dict(row)
            for row in _read_jsonl(self._draw_path(game_code))
        }
        for row in _read_jsonl(self._revision_path(game_code)):
            replacement = _draw_from_dict(row["replacement"])
            current[replacement.draw_id] = replacement
        records = sorted(
            current.values(), key=lambda item: (item.draw_date, item.draw_time, item.draw_id)
        )
        if before is not None:
            if before.tzinfo is None or before.utcoffset() is None:
                raise ValueError("before must be timezone-aware")
            records = [
                record
                for record in records
                if datetime.fromisoformat(
                    f"{record.draw_date.isoformat()}T{record.draw_time}"
                )
                < before
            ]
        return tuple(records)

    def append_prediction(self, prediction: Prediction) -> bool:
        path = self._prediction_path(prediction.game_code)
        rows = _read_jsonl(path)
        same_target = [
            row
            for row in rows
            if row["target_draw_date"] == prediction.target_draw_date.isoformat()
        ]
        if any(
            row["prediction_id"] != prediction.prediction_id
            for row in same_target
        ):
            raise ValueError(
                "primary prediction already exists for "
                f"{prediction.game_code} {prediction.target_draw_date.isoformat()}"
            )
        existing = {
            row["prediction_id"]: row for row in rows
        }.get(prediction.prediction_id)
        rendered = prediction.to_dict()
        if existing is not None:
            if _canonical(existing) != _canonical(rendered):
                raise ValueError(
                    f"immutable prediction conflict: {prediction.prediction_id}"
                )
            return False
        rows.append(rendered)
        rows.sort(
            key=lambda row: (
                row["target_draw_date"],
                row["created_at"],
                row["prediction_id"],
            )
        )
        _write_jsonl(path, rows)
        return True

    def load_prediction(
        self, game_code: str, prediction_id: str
    ) -> Prediction | None:
        if game_code not in GAMES:
            raise ValueError(f"unknown game: {game_code}")
        for row in _read_jsonl(self._prediction_path(game_code)):
            if row["prediction_id"] == prediction_id:
                return _prediction_from_dict(row)
        return None

    def load_prediction_for_target(
        self, game_code: str, target_draw_date: date
    ) -> Prediction | None:
        if game_code not in GAMES:
            raise ValueError(f"unknown game: {game_code}")
        matches = [
            _prediction_from_dict(row)
            for row in _read_jsonl(self._prediction_path(game_code))
            if row["target_draw_date"] == target_draw_date.isoformat()
        ]
        if len(matches) > 1:
            raise ValueError(
                "multiple primary predictions for "
                f"{game_code} {target_draw_date.isoformat()}"
            )
        return matches[0] if matches else None

    def score_completed_predictions(self, scored_at: datetime) -> int:
        if scored_at.tzinfo is None or scored_at.utcoffset() is None:
            raise ValueError("scored_at must be timezone-aware")
        written = 0
        for game_code in GAMES:
            draws_by_date: dict[date, list[DrawRecord]] = {}
            for draw in self.load_draws(game_code):
                draws_by_date.setdefault(draw.draw_date, []).append(draw)
            path = self._outcome_path(game_code)
            rows = _read_jsonl(path)
            existing_ids = {row["outcome_id"] for row in rows}
            for prediction_row in _read_jsonl(self._prediction_path(game_code)):
                prediction = _prediction_from_dict(prediction_row)
                matching_draws = draws_by_date.get(prediction.target_draw_date, [])
                if len(matching_draws) != 1:
                    continue
                draw = matching_draws[0]
                outcome_id = ":".join(
                    (prediction.prediction_id, draw.draw_id, draw.fingerprint)
                )
                if outcome_id in existing_ids:
                    continue
                outcome = PredictionOutcome(
                    outcome_id=outcome_id,
                    prediction_id=prediction.prediction_id,
                    game_code=game_code,
                    target_draw_date=prediction.target_draw_date,
                    draw_id=draw.draw_id,
                    draw_fingerprint=draw.fingerprint,
                    predicted_numbers=prediction.numbers,
                    winning_numbers=draw.sorted_numbers,
                    matched=len(set(prediction.numbers) & set(draw.sorted_numbers)),
                    scored_at=scored_at,
                )
                rows.append(outcome.to_dict())
                existing_ids.add(outcome_id)
                written += 1
            if rows:
                rows.sort(
                    key=lambda row: (
                        row["target_draw_date"],
                        row["prediction_id"],
                        row["draw_fingerprint"],
                    )
                )
                _write_jsonl(path, rows)
        return written

    def write_event(self, event: MonitorEvent) -> bool:
        events_path = self.root / "alerts" / "events.jsonl"
        rows = _read_jsonl(events_path)
        rendered = event.to_dict()
        existing = {row["event_id"]: row for row in rows}.get(event.event_id)
        if existing is not None:
            existing_meaning = {
                key: value for key, value in existing.items() if key != "created_at"
            }
            rendered_meaning = {
                key: value for key, value in rendered.items() if key != "created_at"
            }
            if _canonical(existing_meaning) != _canonical(rendered_meaning):
                raise ValueError(f"event ID conflict: {event.event_id}")
            return False
        rows.append(rendered)
        rows.sort(key=lambda row: (row["created_at"], row["event_id"]))
        _write_jsonl(events_path, rows)
        _atomic_write(self.root / "alerts" / "latest.json", f"{_canonical(rendered)}\n")
        return True

    def build_sqlite(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        if temporary.exists():
            temporary.unlink()
        with sqlite3.connect(temporary) as connection:
            connection.executescript(
                """
                CREATE TABLE draws (
                    draw_id TEXT PRIMARY KEY,
                    game_code TEXT NOT NULL,
                    draw_date TEXT NOT NULL,
                    draw_time TEXT NOT NULL,
                    numbers_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL
                );
                CREATE TABLE predictions (
                    prediction_id TEXT PRIMARY KEY,
                    game_code TEXT NOT NULL,
                    target_draw_date TEXT NOT NULL,
                    numbers_json TEXT NOT NULL,
                    method_version TEXT NOT NULL
                );
                CREATE TABLE draw_revisions (
                    revision_id TEXT PRIMARY KEY,
                    draw_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    previous_fingerprint TEXT NOT NULL,
                    replacement_fingerprint TEXT NOT NULL
                );
                CREATE TABLE prediction_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    prediction_id TEXT NOT NULL,
                    game_code TEXT NOT NULL,
                    target_draw_date TEXT NOT NULL,
                    draw_id TEXT NOT NULL,
                    draw_fingerprint TEXT NOT NULL,
                    matched INTEGER NOT NULL,
                    scored_at TEXT NOT NULL
                );
                """
            )
            for game_code in GAMES:
                for record in self.load_draws(game_code):
                    connection.execute(
                        "INSERT INTO draws VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            record.draw_id,
                            record.game_code,
                            record.draw_date.isoformat(),
                            record.draw_time,
                            json.dumps(
                                record.published_numbers, separators=(",", ":")
                            ),
                            record.fingerprint,
                        ),
                    )
                for row in _read_jsonl(self._prediction_path(game_code)):
                    prediction = _prediction_from_dict(row)
                    connection.execute(
                        "INSERT INTO predictions VALUES (?, ?, ?, ?, ?)",
                        (
                            prediction.prediction_id,
                            prediction.game_code,
                            prediction.target_draw_date.isoformat(),
                            json.dumps(prediction.numbers, separators=(",", ":")),
                            prediction.method_version,
                        ),
                    )
                for row in _read_jsonl(self._revision_path(game_code)):
                    connection.execute(
                        "INSERT INTO draw_revisions VALUES (?, ?, ?, ?, ?)",
                        (
                            row["revision_id"],
                            row["draw_id"],
                            row["observed_at"],
                            row["previous_fingerprint"],
                            row["replacement"]["fingerprint"],
                        ),
                    )
                for row in _read_jsonl(self._outcome_path(game_code)):
                    connection.execute(
                        "INSERT INTO prediction_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["outcome_id"],
                            row["prediction_id"],
                            row["game_code"],
                            row["target_draw_date"],
                            row["draw_id"],
                            row["draw_fingerprint"],
                            int(row["matched"]),
                            row["scored_at"],
                        ),
                    )
        temporary.replace(path)
