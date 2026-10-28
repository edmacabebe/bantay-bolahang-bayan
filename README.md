# PCSO Lotto Signal Monitor

An open-source research project for collecting official Philippine Charity Sweepstakes Office six-number lotto results and evaluating frozen combination-selection methods against equal-budget random baselines.

## Important disclaimer

This project is experimental. It does not improve the mathematical jackpot odds of a valid lottery combination, guarantee a win, provide gambling advice, or provide financial advice. It never purchases tickets or recommends a stake.

Implementation follows the design in `docs/superpowers/specs/2026-10-28-pcso-lotto-signal-monitor-design.md`.

## Cloud operation

The repository includes a GitHub Actions runner for official-result collection at 7:17 AM and 10:17 PM in `Asia/Manila`. The data pipeline is deterministic Python and makes no AI model calls. It commits only auditable files under `data/`, `state/`, and `alerts/`.

Standard GitHub-hosted runners are free for public repositories under GitHub's current allowance. Production research-signal events remain disabled in `config/runtime.json` during the initial live-collection and shadow-evaluation period.
