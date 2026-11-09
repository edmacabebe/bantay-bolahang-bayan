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


def test_prompt_labels_historical_fallback_without_probability_claims() -> None:
    text = prompt_text().lower()

    assert "historical_fallback" in text
    assert "historical-data guess" in text
    assert "never call" in text and "high probability" in text
    assert "production alerts were suppressed" in text


def test_prompt_notifies_only_for_significant_scores() -> None:
    text = prompt_text().lower()

    assert "daily_scorecard" in text
    assert "significant_score" in text
    assert "threshold" in text and "2" in text
    assert "advance" in text and "cursor" in text
    assert "pending" in text and "remain silent" in text
    assert "0/6" in text and "1/6" in text and "remain silent" in text
    assert "qualifying_entries" in text
    assert "predicted" in text and "winning" in text
    assert "matched_numbers" in text
    assert "matched_count" in text
    assert "n/6" in text
    assert "not a prize" in text
    assert "jackpot odds" in text


def test_prompt_timestamps_and_reports_evidence_first_metrics() -> None:
    text = prompt_text().lower()

    assert "report timestamp:" in text
    assert "created_at" in text
    assert "asia/manila" in text
    for field in (
        "score",
        "matched_numbers",
        "missed_predicted_numbers",
        "unpredicted_winning_numbers",
        "source_cutoff",
        "last_7_days",
        "last_30_days",
        "lifetime",
        "random_expected_average",
        "match_delta_vs_random",
        "automatic_tuning",
        "weekly_walk_forward_audit",
    ):
        assert field in text
    assert "do not automatically tune" in text


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
        "state/heartbeats.json",
        "before noon",
        "prior manila calendar date",
        "8:07 am",
        "9:07 am",
        "11:07 pm",
        "12:07 am",
        "lottomatik-backend.api-lottomatik.workers.dev",
        "historical_fallback_source_error",
        "report timestamp",
        "7-day",
        "30-day",
        "random baseline",
        "weekly walk-forward audit",
        "significant_score",
        "2/6",
        "0/6 and 1/6",
        "content-addressed",
    ):
        assert phrase in text
