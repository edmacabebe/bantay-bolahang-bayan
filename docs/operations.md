# Operations guide

## What runs where

GitHub Actions runs deterministic collection and analysis at 7:17 AM and 10:17 PM in `Asia/Manila`. A Codex scheduled task checks the compact public state at 7:47 AM and 10:47 PM. Because both are cloud jobs, the Mac does not need to be awake.

The official OpenAI Scheduled-task workflow is to run and refine a task once in a regular chat, then ask for a recurring schedule in the same chat. The Scheduled tab shows the next run and history and provides edit, pause, resume, and delete controls: <https://developers.openai.com/training/walkthroughs/scheduled-tasks>.

If this Codex session cannot create a schedule directly, open the Scheduled tab and paste the full contents of `codex/monitor-prompt.md` into this same existing chat. Set the two daily `Asia/Manila` times and select cloud execution. The prompt keeps one-notification-per-event behavior through the existing chat context.

## Manual run

From GitHub, open Actions, choose **Lotto monitor**, choose **Run workflow**, and select `morning`, `evening`, `audit`, or `backfill`. Locally, install with `python -m pip install -e '.[dev]'` and run `lotto-signal morning` or another mode from the repository root.

Always inspect the tests and the generated diff before accepting a manual state commit. Only `data/`, `state/`, and `alerts/` belong in an automated data commit.

## Schedule delay or inactivity

GitHub schedules are best-effort and may have a schedule delay. The Codex monitor treats `state/last_run.json` as stale after 30 hours and reports that condition once. Public-repository schedules may be disabled after 60 days without repository activity; re-enable the workflow in Actions and run `morning` manually.

## Source and schema incidents

The first official-source failure stays silent. A repeated failure creates an `action_required` event. If the PCSO JSON schema changes, do not overwrite history or loosen validation to force the run through. Preserve the response safely outside committed state, update a sanitized fixture and parser test, then release the parser fix.

An official correction is appended under `data/revisions/`; originals are never rewritten. Run `audit` after an official correction and review whether predictions, backtest outcomes, or a gate decision changed.

## Shadow and production lifecycle

`config/runtime.json` starts with production research signals disabled. Keep seven days of live collection and at least two additional weeks of shadow evaluation. Review missing results, official corrections, deterministic replay, false alarms, and actual recurring usage before changing `production_research_signals` to `true`.

To pause collection, disable the GitHub workflow. To resume, enable it and run `morning`, then `audit`, manually. To pause the Codex monitor, use its control in the Scheduled tab; resume it only after the repository heartbeat is current.

## Cost controls

Public GitHub Actions is intended to keep the deterministic runner at no charge under the public-repository allowance. The Codex monitor prefers GPT-6 Luna at low reasoning when available, stays silent on unchanged state, and has a hard recurring budget policy of $5 per calendar month. Model availability, plan allowances, and prices can change, so check the account's actual usage before production enablement.

At 80% of the $5 ceiling, disable optional interpretation. At 100%, pause optional cost-incurring tasks and retain only deterministic GitHub processing until the next calendar month or an explicit operator decision.
