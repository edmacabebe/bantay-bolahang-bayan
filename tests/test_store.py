from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from lotto_signal.domain import DrawRecord, MonitorEvent, Prediction
from lotto_signal.store import RepositoryStore


def draw(
    draw_id: str,
    draw_date: date,
    numbers: tuple[int, ...],
    *,
    retrieved_hour: int = 1,
    jackpot: str = "10000000",
) -> DrawRecord:
    return DrawRecord(
        draw_id=draw_id,
        game_code="LOTTO42",
        draw_date=draw_date,
        draw_time="21:00:00+08:00",
        published_numbers=numbers,
        jackpot=jackpot,
        total_winners=0,
        retrieved_at=datetime(2026, 10, 20, retrieved_hour, tzinfo=timezone.utc),
        source_url="https://lottomatik.pcso.gov.ph/api/backend/get-results",
    )


def prediction(*, numbers: tuple[int, ...] = (1, 8, 17, 23, 31, 42)) -> Prediction:
    return Prediction(
        prediction_id="LOTTO42-2026-10-22-ensemble_v1",
        game_code="LOTTO42",
        target_draw_date=date(2026, 10, 22),
        method_version="ensemble_v1",
        numbers=numbers,
        raw_score=2.5,
        signal_score=1.4,
        seed=42,
        created_at=datetime(2026, 10, 22, 0, tzinfo=timezone.utc),
        source_cutoff=datetime(2026, 10, 21, 23, 17, tzinfo=timezone.utc),
        feature_values={"draw_count": 200},
    )


def test_merge_writes_chronological_canonical_jsonl_and_is_idempotent(
    tmp_path: Path,
) -> None:
    store = RepositoryStore(tmp_path)
    later = draw("LOTTO42S0002", date(2026, 10, 15), (1, 2, 3, 4, 5, 6))
    earlier = draw("LOTTO42S0001", date(2026, 10, 13), (7, 8, 9, 10, 11, 12))

    result = store.merge_draws([later, earlier])
    duplicate = store.merge_draws([earlier])

    assert (result.inserted, result.unchanged, result.revised) == (2, 0, 0)
    assert (duplicate.inserted, duplicate.unchanged, duplicate.revised) == (0, 1, 0)
    lines = (tmp_path / "data/draws/LOTTO42.jsonl").read_text().splitlines()
    assert [json.loads(line)["draw_id"] for line in lines] == [
        "LOTTO42S0001",
        "LOTTO42S0002",
    ]
    assert all(line == json.dumps(json.loads(line), sort_keys=True, separators=(",", ":")) for line in lines)
    assert not list(tmp_path.rglob("*.tmp"))


def test_correction_appends_revision_and_projects_latest_value(tmp_path: Path) -> None:
    store = RepositoryStore(tmp_path)
    original = draw("LOTTO42S0001", date(2026, 10, 13), (1, 2, 3, 4, 5, 6))
    corrected = draw(
        "LOTTO42S0001",
        date(2026, 10, 13),
        (1, 2, 3, 4, 5, 7),
        retrieved_hour=2,
    )

    store.merge_draws([original])
    result = store.merge_draws([corrected])

    assert result.revised == 1
    original_line = json.loads(
        (tmp_path / "data/draws/LOTTO42.jsonl").read_text().strip()
    )
    assert original_line["fingerprint"] == original.fingerprint
    revision_lines = (
        tmp_path / "data/revisions/LOTTO42.jsonl"
    ).read_text().splitlines()
    assert len(revision_lines) == 1
    assert store.load_draws("LOTTO42")[0].fingerprint == corrected.fingerprint


def test_load_draws_before_cutoff_excludes_same_or_later_draw(tmp_path: Path) -> None:
    store = RepositoryStore(tmp_path)
    first = draw("LOTTO42S0001", date(2026, 10, 13), (1, 2, 3, 4, 5, 6))
    second = draw("LOTTO42S0002", date(2026, 10, 15), (7, 8, 9, 10, 11, 12))
    store.merge_draws([first, second])

    loaded = store.load_draws(
        "LOTTO42", before=datetime.fromisoformat("2026-10-15T21:00:00+08:00")
    )

    assert [record.draw_id for record in loaded] == ["LOTTO42S0001"]


def test_prediction_is_immutable_and_duplicate_is_idempotent(tmp_path: Path) -> None:
    store = RepositoryStore(tmp_path)
    original = prediction()

    assert store.append_prediction(original) is True
    assert store.append_prediction(original) is False
    with pytest.raises(ValueError, match="immutable prediction conflict"):
        store.append_prediction(prediction(numbers=(2, 8, 17, 23, 31, 42)))


def test_event_id_is_written_once_and_latest_is_replaced_atomically(
    tmp_path: Path,
) -> None:
    store = RepositoryStore(tmp_path)
    event = MonitorEvent(
        event_id="evt-1",
        kind="action_required",
        created_at=datetime(2026, 10, 20, 3, tzinfo=timezone.utc),
        payload={"reason": "source stale"},
    )

    assert store.write_event(event) is True
    assert store.write_event(event) is False
    assert json.loads((tmp_path / "alerts/latest.json").read_text())["event_id"] == "evt-1"
    assert len((tmp_path / "alerts/events.jsonl").read_text().splitlines()) == 1
    assert not list(tmp_path.rglob("*.tmp"))


def test_sqlite_cache_matches_corrected_projection(tmp_path: Path) -> None:
    store = RepositoryStore(tmp_path)
    original = draw("LOTTO42S0001", date(2026, 10, 13), (1, 2, 3, 4, 5, 6))
    corrected = draw(
        "LOTTO42S0001",
        date(2026, 10, 13),
        (1, 2, 3, 4, 5, 7),
        retrieved_hour=2,
    )
    store.merge_draws([original, corrected])
    store.append_prediction(prediction())

    cache = tmp_path / "cache.sqlite3"
    store.build_sqlite(cache)

    with sqlite3.connect(cache) as connection:
        draw_row = connection.execute(
            "SELECT fingerprint, numbers_json FROM draws"
        ).fetchone()
        prediction_count = connection.execute(
            "SELECT COUNT(*) FROM predictions"
        ).fetchone()[0]
    assert draw_row == (corrected.fingerprint, "[1,2,3,4,5,7]")
    assert prediction_count == 1
