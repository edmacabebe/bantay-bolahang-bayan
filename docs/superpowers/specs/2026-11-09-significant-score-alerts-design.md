# Significant Score Alerts Design

## Intent

Keep the complete daily evaluation record in GitHub while sending a Codex chat notification only when at least one completed prediction overlaps the official draw by two or more numbers.

## Goals

- Emit a deterministic `significant_score` event for every newly completed or officially corrected line scoring at least `2/6`.
- Include the draw date, threshold, qualifying entries, exact matches, provenance, rolling performance, and the existing odds disclaimer.
- Keep every `daily_scorecard` and outcome unchanged in GitHub.
- Make unchanged replays idempotent and keep 0/6, 1/6, and pending scorecards silent in Codex.

## Non-goals and anti-goals

- Do not call a 2/6 overlap a prize, win, predictive edge, or high-probability signal.
- Do not delete or suppress ordinary scorecards from repository state.
- Do not change prediction generation, tuning, draw collection, or jackpot assumptions.

## Approaches

- **Deterministic repository event — selected.** The workflow derives a content-addressed `significant_score` event from the completed scorecard, and the Codex monitor notifies only for that event. This is auditable, replay-safe, and cheap.
- **Prompt-only filtering — rejected.** Codex could inspect every daily scorecard and decide whether to notify, but the threshold would be less explicit in repository history and harder to verify independently.
- **External push service — rejected.** It adds credentials, cost, and a notification channel outside the requested Codex-only design.

## Design

`_scorecard_events` continues to write and publish `daily_scorecard` events. For every scorecard entry whose `result_status` is `complete` and `matched_count >= 2`, it also emits one content-addressed `significant_score` event. The payload contains `threshold: 2`, `target_draw_date`, the qualifying entry or entries, the scorecard performance summary, and a disclaimer that overlap does not change jackpot odds.

The Codex monitor advances its cursor over ordinary `daily_scorecard` events without notifying. It sends a timestamped report for each new `significant_score`, including game, prediction, official numbers, score, exact matches, provenance, and rolling performance. Existing operational, correction, and production-signal notifications remain unchanged.

## Acceptance criteria

- A completed 1/6 line emits no `significant_score` event.
- A completed 2/6 or higher line emits exactly one deterministic `significant_score` event on unchanged replay.
- Multiple qualifying games for one date are grouped into one event.
- A correction that newly crosses the threshold creates a new event; ordinary scorecards remain append-only and complete.
- The monitor prompt explicitly suppresses pending, 0/6, and 1/6 scorecards and reports 2/6+ without prize or probability claims.
- The full test suite and one live cloud run pass before release.
