# PCSO Lotto Signal Monitor

An open-source research project for collecting official Philippine Charity Sweepstakes Office six-number lotto results and evaluating frozen combination-selection methods against equal-budget random baselines.

## Important disclaimer

This project is experimental. It does not improve the mathematical jackpot odds of a valid lottery combination, guarantee a win, provide gambling advice, or provide financial advice. It never purchases tickets or recommends a stake.

Implementation follows the design in `docs/superpowers/specs/2026-10-28-pcso-lotto-signal-monitor-design.md`.

## Cloud operation

The repository includes a GitHub Actions runner for official-result collection at 7:17 AM and 10:17 PM in `Asia/Manila`. The data pipeline is deterministic Python and makes no AI model calls. It commits only auditable files under `data/`, `state/`, and `alerts/`.

Standard GitHub-hosted runners are free for public repositories under GitHub's current allowance. Production research-signal events remain disabled in `config/runtime.json` during the initial live-collection and shadow-evaluation period.

See `docs/operations.md` for manual runs, incident handling, rollout gates, and the Codex-only scheduled monitor. The ready-to-paste monitor instructions are in `codex/monitor-prompt.md`.

## Initial official-history result

The initial backfill contains 2,141 official draws across all five games (427–429 per game). Two clean full-family replays produced identical prediction, backtest, and gate digests. None of the 25 predeclared game-method hypotheses passed the Holm-corrected evidence gate, so the current correct output is **no research signal**.

For scale, a single line has jackpot odds of 1 in 5,245,786 for 6/42; 1 in 8,145,060 for 6/45; 1 in 13,983,816 for 6/49; 1 in 28,989,675 for 6/55; and 1 in 40,475,358 for 6/58. Playing one line in every draw of all five games is approximately a 1 in 750,556 chance of at least one jackpot over one week, or 1 in 187,639 over four weeks. Selection patterns do not improve those mathematical odds.
