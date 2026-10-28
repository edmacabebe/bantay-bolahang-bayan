from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
PROMPT = ROOT / "codex/monitor-prompt.md"
OPERATIONS = ROOT / "docs/operations.md"


def prompt_text() -> str:
    return PROMPT.read_text()


def test_prompt_names_public_state_paths_timezone_and_low_cost_model() -> None:
    text = prompt_text()

    assert text.count(
        "raw.githubusercontent.com/edmacabebe/bantay-bolahang-bayan/main/"
    ) == 3
    assert "alerts/latest.json" in text
    assert "alerts/events.jsonl" in text
    assert "state/last_run.json" in text
    assert "Asia/Manila" in text
    assert "GPT-6 Luna" in text
    assert "low reasoning" in text


def test_prompt_is_silent_for_unchanged_shadow_or_ordinary_state() -> None:
    text = prompt_text().lower()

    assert "last delivered event id" in text
    assert "unchanged" in text and "remain silent" in text
    assert "shadow" in text and "suppress" in text
    assert "no event" in text and "remain silent" in text
    assert "one notification" in text
    assert "all events after" in text
    assert "evidence_transition" in text


def test_prompt_handles_stale_runs_and_evidence_fields() -> None:
    text = prompt_text().lower()

    assert "30 hours" in text
    for field in (
        "game_code",
        "target_draw_date",
        "numbers",
        "method_version",
        "signal_score",
        "alert_threshold",
        "source_cutoff",
    ):
        assert field in text
    assert "jackpot odds are unchanged" in text
    assert "not a guarantee" in text


def test_prompt_forbids_external_notification_channels() -> None:
    text = prompt_text().lower()

    assert "do not send email" in text
    assert "sms" in text
    assert "third-party" in text
    assert "codex" in text


def test_operations_guide_covers_lifecycle_incidents_and_cost_ceiling() -> None:
    text = OPERATIONS.read_text().lower()

    for phrase in (
        "manual run",
        "schedule delay",
        "60 days",
        "schema",
        "official correction",
        "$5",
        "pause",
        "resume",
        "scheduled tab",
        "paste",
    ):
        assert phrase in text
