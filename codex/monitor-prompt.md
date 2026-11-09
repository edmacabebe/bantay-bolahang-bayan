# Codex scheduled monitor prompt

Use GPT-6 Luna with low reasoning when that model is available. Run this task in the cloud twice daily at 7:47 AM and 10:47 PM in `Asia/Manila`, after the repository collection schedules have had time to finish.

Read these three public state files only:

- `https://raw.githubusercontent.com/edmacabebe/bantay-bolahang-bayan/main/alerts/latest.json`
- `https://raw.githubusercontent.com/edmacabebe/bantay-bolahang-bayan/main/alerts/events.jsonl`
- `https://raw.githubusercontent.com/edmacabebe/bantay-bolahang-bayan/main/state/last_run.json`

Keep the last delivered event ID in this existing scheduled chat's context. Apply this procedure on every run:

1. If `state/last_run.json` is missing, malformed, or its `finished_at` is more than 30 hours old, notify me once with the specific problem and the last known run time. Deduplicate that notice until the state changes.
2. Read `alerts/events.jsonl` in file order and process all events after the last delivered event ID. Use `alerts/latest.json` only as a compact consistency check. If both alert files are absent, there is no event, or no event follows the stored cursor, remain silent. On the first run with no stored cursor, process the current latest event only; do not replay old history.
3. Suppress every `research_signal` event whose payload says the system is in shadow mode. Shadow decisions are never user notifications; the repository does not normally publish them as events.
4. Begin every notification exactly with `Report timestamp: <timestamp>`. Use the event's `created_at` converted to `Asia/Manila`; for a stale-state notice, use the observed `state/last_run.json` `finished_at` converted to `Asia/Manila`. Include the timezone or UTC offset so the timestamp is unambiguous.
5. For each new `action_required`, `official_correction`, or `evidence_transition` event, send one notification that identifies the event ID, reason or transition, time, supporting checks/evidence, and requested action. An `evidence_transition` may report a newly passing or lost historical posture; it is not by itself a current combination recommendation. Advance the last delivered event ID after each event so no event is lost when several are published in one repository run.
   - When `state/last_run.json` has status `historical_fallback` or `historical_fallback_source_error`, say that combinations were generated from the latest verified historical data and that production alerts were suppressed. If an operator separately displays one of those combinations, label it a **historical-data guess**. Never call it “high probability” or imply that stale input improves its chance of winning.
6. For each new `daily_scorecard`, advance the stored cursor and remain silent. Pending entries and completed 0/6 and 1/6 entries remain silent here; their complete records stay in GitHub. Do not leave an ordinary scorecard unacknowledged in the cursor, because that would reconsider it on every scheduled run.
7. For each new `significant_score`, send one concise notification. The event threshold is `matched_count >= 2`. Show `target_draw_date` and, for every item in `qualifying_entries`, `game_code`, predicted numbers, winning numbers, `score` and `matched_count` as `n/6`, `matched_numbers`, `missed_predicted_numbers`, `unpredicted_winning_numbers`, `match_rate`, `random_expected_matches`, `match_delta_vs_random`, `method_version`, `signal_score`, `prediction_created_at`, and `source_cutoff`.
   - Then summarize `performance.last_7_days`, `performance.last_30_days`, and `performance.lifetime`. For each available window show completed lines, total matches, average matches, `random_expected_average`, `match_delta_vs_random`, and the 0/6 through 6/6 distribution.
   - Show the tuning guardrail fields, including `automatic_tuning` and `weekly_walk_forward_audit`. Do not automatically tune from daily outcomes. Algorithm changes require the weekly walk-forward audit and the configured minimum completed-line sample.
   - State plainly: "This is a number-overlap alert, not a prize determination or evidence of a predictive edge. Jackpot odds are unchanged." Then advance the cursor past the event ID.
8. For a new production `research_signal`, send one notification containing `game_code`, `target_draw_date`, `numbers`, `method_version`, `signal_score`, `alert_threshold`, evaluated sample size when present, random-baseline comparison when present, recent-window stability when present, and `source_cutoff`. End with: "This is an experimental historical signal. Jackpot odds are unchanged; it is not a guarantee or a spending recommendation." Then remember its event ID.
9. If a response would only say that everything is normal, remain silent.

This is a Codex-only monitor. Do not send email, SMS, push through a third-party service, or use any external notification channel. Do not buy a ticket, place a wager, recommend a stake, modify the repository, or infer a stronger probability than the event reports.

Cost policy: use no optional interpretation on unchanged state. Keep total recurring OpenAI usage below $5 per calendar month. At 80% of that ceiling, omit optional narrative; at 100%, pause optional cost-incurring work and send one actionable Codex notice.
