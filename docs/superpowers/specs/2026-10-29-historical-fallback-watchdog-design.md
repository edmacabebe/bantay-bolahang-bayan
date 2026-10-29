# Historical Fallback and Missed-Schedule Watchdog Design

## Intent

Keep Bantay Bolahang Bayan useful when PCSO has not published the previous
night's expected results, and automatically recover when GitHub does not create
a scheduled morning or evening run.

## Selected approach

Use a **safe historical fallback plus a conditional GitHub watchdog**.

When morning collection succeeds but expected prior results are missing, the
pipeline will still generate and persist the day's immutable combinations from
the latest verified historical cutoff. The run will remain explicitly stale,
retain its actionable missing-result event, identify the affected games and
date, and record that the combinations used historical fallback data.
Production `research_signal` events are forbidden for such a run even if a
statistical decision would otherwise be eligible.

Each morning and evening attempt will also update a small per-mode heartbeat in
`state/heartbeats.json`, including the operational date, completion time, and
status. A separate lightweight GitHub Actions watchdog will check those
heartbeats at redundant backup times. It will dispatch the ordinary monitor
workflow only when the expected heartbeat is absent; ordinary retries remain
idempotent.

## Watchdog schedule

- Morning checks: 8:07 AM and 9:07 AM in `Asia/Manila` for that calendar day's
  morning heartbeat.
- Evening checks: 11:07 PM for that calendar day's evening heartbeat and
  12:07 AM for the prior calendar day's evening heartbeat.
- The watchdog only dispatches the existing `morning` or `evening` workflow; it
  never calculates combinations itself and never edits data directly.
- GitHub schedules are best-effort, so two checks are used for each operational
  window. The existing 7:17 AM and 10:17 PM schedules remain primary.

## Operational-date rules

- A morning attempt belongs to its current Manila calendar date.
- An evening attempt before noon belongs to the prior Manila calendar date;
  an evening attempt at or after noon belongs to the current date. This keeps a
  heavily delayed 10:17 PM job attached to the night it was meant to collect.
- A heartbeat records that the run was attempted, including handled stale or
  source-error outcomes. Collection errors continue to use the existing
  incident escalation policy rather than causing an unlimited dispatch loop.

## Alternatives considered

- Allowing production alerts from incomplete data was rejected because a
  missing draw can distort features and evidence.
- Backup cron entries that blindly rerun the full monitor were rejected because
  they create unnecessary duplicate jobs and do not distinguish a missed run
  from a completed stale run.
- A Codex-only watchdog was rejected because the repository scheduler must
  recover independently of Codex availability, account usage, or a Mac.

## Data and notification contract

- Add handled status `historical_fallback` with `source_fresh: false`.
- Persist combinations and gate-decision evidence exactly as on an ordinary
  morning run, adding `historical_fallback`, `missing_expected_games`, and
  `production_alerts_suppressed` metadata.
- Continue emitting one deduplicated `action_required` stale-source event. Its
  payload states that historical combinations were generated but production
  alerts were suppressed.
- The Codex monitor may report that action-required event, but it must not
  describe a historical-fallback combination as a higher-probability signal.
- Preserve existing prediction IDs, audit-family IDs, thresholds, data files,
  and production-disabled configuration.

## Success criteria

- A stale morning fixture writes predictions for every game scheduled that day,
  records `historical_fallback`, remains source-stale, and emits no production
  research signal even under an otherwise eligible injected decision.
- Repeating the stale morning run is idempotent.
- Successful, stale, and source-error morning/evening attempts update the
  correct operational-date heartbeat.
- Watchdog checks dispatch only when the relevant heartbeat is missing and are
  no-ops after it appears.
- Local tests and a cloud smoke test pass; production signals remain disabled.
