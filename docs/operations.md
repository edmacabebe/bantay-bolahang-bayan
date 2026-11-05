# Operations guide

## What runs where

GitHub Actions runs deterministic collection and analysis at 7:17 AM and 10:17 PM in `Asia/Manila`. A Codex scheduled task checks the compact public state at 7:47 AM and 10:47 PM. Because both are cloud jobs, the Mac does not need to be awake.

The official OpenAI Scheduled-task workflow is to run and refine a task once in a regular chat, then ask for a recurring schedule in the same chat. The Scheduled tab shows the next run and history and provides edit, pause, resume, and delete controls: <https://developers.openai.com/training/walkthroughs/scheduled-tasks>.

If this Codex session cannot create a schedule directly, open the Scheduled tab and paste the full contents of `codex/monitor-prompt.md` into this same existing chat. Set the two daily `Asia/Manila` times and select cloud execution. The prompt keeps one-notification-per-event behavior through the existing chat context.

## Manual run

From GitHub, open Actions, choose **Bantay Bolahang Bayan monitor**, choose **Run workflow**, and select `morning`, `evening`, `audit`, or `backfill`. Locally, install with `python -m pip install -e '.[dev]'` and run `lotto-signal morning` or another mode from the repository root.

Always inspect the tests and the generated diff before accepting a manual state commit. Only `data/`, `state/`, and `alerts/` belong in an automated data commit.

## Schedule delay or inactivity

GitHub schedules are best-effort and may have a schedule delay. The Codex monitor treats `state/last_run.json` as stale after 30 hours and reports that condition once. Public-repository schedules may be disabled after 60 days without repository activity; re-enable the workflow in Actions and run `morning` manually.

Every completed morning or evening attempt also updates `state/heartbeats.json` with its operational date, completion time, and handled status. A morning attempt belongs to the current Manila calendar date. An evening attempt before noon belongs to the prior Manila calendar date; an evening attempt at noon or later belongs to the current date. This keeps a heavily delayed overnight job attached to the night it was intended to collect.

The **Bantay Bolahang Bayan watchdog** checks the morning heartbeat at 8:07 AM and 9:07 AM and the evening heartbeat at 11:07 PM and 12:07 AM, all in `Asia/Manila`. The midnight check looks for the prior evening's operational date. It dispatches the ordinary monitor workflow only when that heartbeat is absent; it never calculates combinations or writes state itself. A handled pending, fallback, or source-error heartbeat prevents an unlimited retry loop.

For manual recovery, inspect `state/heartbeats.json` and `state/last_run.json` first. If the expected operational date is absent, run the corresponding mode from GitHub Actions. If the heartbeat is present, do not start a blind duplicate; investigate the recorded status and its event instead.

## Source and schema incidents

The active official-results endpoint is `https://lottomatik-backend.api-lottomatik.workers.dev/get-results`. The former `lottomatik.pcso.gov.ph/api/backend/get-results` proxy began returning HTTP 404 in November 2026. Keep strict schema and game-code validation when changing endpoints; a successful HTTP response alone is not proof that the payload is valid official data.

The first official-source failure stays silent. A repeated failure creates an `action_required` event. A morning source failure uses status `historical_fallback_source_error`: the runner preserves the incident timestamp, generates the scheduled games from the latest locally verified history, and suppresses production research signals. Evening collection does not invent a result and retains its source-error behavior. If the PCSO JSON schema changes, do not overwrite history or loosen validation to force the run through. Preserve the response safely outside committed state, update a sanitized fixture and parser test, then release the parser fix.

An official correction is appended under `data/revisions/`; originals are never rewritten. Run `audit` after an official correction and review whether predictions, backtest outcomes, or a gate decision changed.

## Shadow and production lifecycle

`config/runtime.json` starts with production research signals disabled. Keep seven days of live collection and at least two additional weeks of shadow evaluation. Review missing results, official corrections, deterministic replay, false alarms, and actual recurring usage before changing `production_research_signals` to `true`.

When prior scheduled results are missing, the morning run uses `historical_fallback`: it still persists the day's scheduled-game combinations from the latest verified history, records the missing games, and suppresses every production research alert. Present such a combination only as a **historical-data guess**, never as high probability. Jackpot odds remain unchanged.

Each collection run also refreshes deterministic daily scorecards under `state/scorecards/` and publishes the latest one at `state/daily_scorecard.json`. The morning scorecard covers the previous Manila calendar day. A missing official result is reported as pending instead of being treated as zero matches. When a later run receives the result, it emits a completed `daily_scorecard` with predicted numbers, winning numbers, matched numbers, and the matched-ball count out of six. Corrected official results produce a new scorecard version through their changed content.

Every Codex notification begins with `Report timestamp` and converts the event's recorded time to `Asia/Manila`. A completed line reports its score as `n/6`, the exact matched numbers, missed predicted numbers, unpredicted winning numbers, method version, signal score, and source cutoff. This overlap is not a prize determination, and reporting it does not change the underlying jackpot odds.

The scorecard also reports 7-day, 30-day, and lifetime performance: completed lines, total and average matches, the complete 0/6 through 6/6 distribution, and the delta from the line-weighted random baseline. Pending draws are excluded. Corrected draws replace the active outcome rather than being counted twice.

Daily outcomes never trigger automatic algorithm changes. The tuning guardrail requires the configured minimum sample and a weekly walk-forward audit before a candidate method can be considered. This avoids tuning to a handful of recent random outcomes; promotion remains an explicit, evidence-based decision.

To pause collection, disable the GitHub workflow. To resume, enable it and run `morning`, then `audit`, manually. To pause the Codex monitor, use its control in the Scheduled tab; resume it only after the repository heartbeat is current.

## Cost controls

Public GitHub Actions is intended to keep the deterministic runner at no charge under the public-repository allowance. The Codex monitor prefers GPT-6 Luna at low reasoning when available, stays silent on unchanged state, and has a hard recurring budget policy of $5 per calendar month. Model availability, plan allowances, and prices can change, so check the account's actual usage before production enablement.

At 80% of the $5 ceiling, disable optional interpretation. At 100%, pause optional cost-incurring tasks and retain only deterministic GitHub processing until the next calendar month or an explicit operator decision.
