# Codex scheduled monitor prompt

Use GPT-6 Luna with low reasoning when that model is available. Run this task in the cloud twice daily at 7:47 AM and 10:47 PM in `Asia/Manila`, after the repository collection schedules have had time to finish.

Read these two public JSON files only:

- `https://raw.githubusercontent.com/edmacabebe/pcso-lotto-signal-monitor/main/alerts/latest.json`
- `https://raw.githubusercontent.com/edmacabebe/pcso-lotto-signal-monitor/main/state/last_run.json`

Keep the last delivered event ID in this existing scheduled chat's context. Apply this procedure on every run:

1. If `state/last_run.json` is missing, malformed, or its `finished_at` is more than 30 hours old, notify me once with the specific problem and the last known run time. Deduplicate that notice until the state changes.
2. If `alerts/latest.json` is absent, there is no event, or its event ID is unchanged from the last delivered event ID, remain silent.
3. Suppress every `research_signal` event whose payload says the system is in shadow mode. Shadow decisions are never user notifications; the repository does not normally publish them as events.
4. For a new `action_required` or `official_correction` event, send one notification that identifies the event ID, reason, time, and requested action. Then remember its event ID.
5. For a new production `research_signal`, send one notification containing `game_code`, `target_draw_date`, `numbers`, `method_version`, `signal_score`, `alert_threshold`, evaluated sample size when present, random-baseline comparison when present, recent-window stability when present, and `source_cutoff`. End with: "This is an experimental historical signal. Jackpot odds are unchanged; it is not a guarantee or a spending recommendation." Then remember its event ID.
6. If a response would only say that everything is normal, remain silent.

This is a Codex-only monitor. Do not send email, SMS, push through a third-party service, or use any external notification channel. Do not buy a ticket, place a wager, recommend a stake, modify the repository, or infer a stronger probability than the event reports.

Cost policy: use no optional interpretation on unchanged state. Keep total recurring OpenAI usage below $5 per calendar month. At 80% of that ceiling, omit optional narrative; at 100%, pause optional cost-incurring work and send one actionable Codex notice.
