# PCSO Lotto Signal Monitor — Design

Date: 2026-10-28  
Status: Draft for approval

## Intent

Build a local, reproducible analytics pipeline that collects official Philippine Charity Sweepstakes Office (PCSO) results for all five six-number lotto games, evaluates pre-declared combination-selection methods against equal-budget random baselines, and sends a Codex-only notification only when a strict out-of-sample evidence threshold is met.

The system is a research and monitoring tool. It must not describe a draw day or combination as likely to win merely because recent numbers form an interesting pattern. For a fair lottery, every valid combination has the same jackpot probability on every draw.

## Scope

Games in scope:

- Lotto 6/42
- Mega Lotto 6/45
- Super Lotto 6/49
- Grand Lotto 6/55
- Ultra Lotto 6/58

The system processes only games scheduled for a given date. It produces one primary hypothetical combination per game and draw so that its historical evaluation is comparable with one random line per game and draw. It does not purchase tickets or recommend a stake.

## Goals

- Collect and preserve official draw results with source and retrieval metadata.
- Backfill enough history for meaningful walk-forward evaluation.
- Compute deterministic, reviewable features and candidate combinations.
- Prevent future-data leakage and retrospective rule changes.
- Compare each method with equal-budget randomized baselines.
- Notify in Codex only when a strict, pre-declared statistical gate passes.
- Stay quiet when there is no signal.
- Keep recurring model and web-search costs low.
- Make every prediction and later outcome auditable.

## Non-goals

- Claim that historical patterns can predict an independently drawn lottery.
- Guarantee wins, imply certainty, or label ordinary fluctuations as an edge.
- Purchase tickets, manage money, or recommend increasing a gambling budget.
- Send email, SMS, chat-app, or push notifications outside Codex.
- Build a public website or full dashboard in the first version.
- Continuously tune rules against the same evaluation data.

## Anti-goals

The project is considered unsuccessful if it:

- Uses future draw data when constructing or selecting an earlier prediction.
- Compares a multi-line strategy with a single random line.
- Alerts because a pattern looks persuasive without passing the evidence gate.
- hides failed predictions or changes a historical prediction after the draw;
- confuses a relative model score with an absolute probability of winning;
- emits routine daily messages when nothing actionable changed.

## Constraints and assumptions

- Primary source: the official PCSO/LottoMatik results surface.
- Time zone: `Asia/Manila`.
- Evening collection check: 10:00 PM Manila time.
- Catch-up and verification check: 7:00 AM Manila time for the previous draw day.
- Weekly method audit: Monday after the 7:00 AM verification.
- Notifications appear in Codex only.
- The local folder is currently empty and is not a Git repository.
- Execution location: GitHub Actions in a public open-source repository, so the user's Mac may remain off.
- Repository name: `pcso-lotto-signal-monitor`; license: MIT.
- The official site may publish late, correct results, change markup, or temporarily block automated access; the collector must fail safely and preserve evidence.
- Minimum before signal activation: 200 walk-forward evaluated draws for the specific game. Historical collection targets all reliably available official results, with three years preferred and one year as an initial backfill milestone.

## Approaches considered

### 1. Local analytics pipeline plus Codex automation — selected

Store results and predictions locally, calculate statistics in deterministic code, and use Codex for scheduled orchestration, interpretation, and notifications. This provides the best auditability, reproducibility, and cost control.

### 2. Prompt-only Codex automation

Have Codex revisit PCSO and reason over recent results on every run without a dedicated local engine. This is quicker to start but makes continuity, rigorous backtesting, and leakage prevention weaker.

### 3. Full dashboard and database application

Add a user interface, charts, experiment management, and richer reporting. This may be useful after a signal has demonstrated value, but it adds cost and complexity before the core hypothesis is validated.

## System design

### 1. Data collection

The collector retrieves official results and normalizes each record into:

- game identifier;
- draw date and scheduled day;
- numbers in published order;
- sorted-number representation for set-based analysis;
- jackpot or prize metadata when available;
- source URL;
- first-seen and last-verified timestamps;
- content fingerprint;
- record status: provisional, verified, corrected, or missing.

New results are idempotently inserted. A later official change creates a correction record rather than silently overwriting history. Raw source evidence or a compact source snapshot is retained when permitted and practical.

The collector validates number count, range, uniqueness, date, game schedule, and duplicate records. A malformed or ambiguous result is quarantined and excluded from analysis.

The production evidence gate uses official PCSO-confirmed records. Reputable secondary sources may be used to discover older records and reconcile gaps, but their records remain separately labeled and cannot activate production alerts unless they are corroborated by an official archive. If the official surface has no stable machine-readable endpoint, browser-based retrieval is allowed; the system must not bypass access controls or anti-automation restrictions.

### 2. Cloud-compatible storage

Append-only, reviewable text records committed to the Git repository are the cloud source of truth. A SQLite database is rebuilt as a derived local cache for constraints, queries, and simulations. This avoids depending on ephemeral GitHub runner disks and keeps open-source changes auditable without accumulating opaque binary database diffs.

The repository stores normalized draw and prediction records as versioned JSON Lines or CSV files, plus compact state and alert files. Each workflow run uses a concurrency lock, pulls the latest default branch before calculating, validates the append, and pushes with a lease. Conflicting updates fail safely and retry rather than overwriting data.

The derived SQLite cache uses these logical tables:

- `draws`
- `draw_revisions`
- `predictions`
- `prediction_outcomes`
- `method_versions`
- `backtest_runs`
- `automation_runs`

Predictions are immutable after their scheduled cutoff. Each prediction records the exact method version, feature values, candidate combination, creation time, eligible draw, and source-data cutoff.

No credential, API key, personal identifier, or private notification content is committed to the public repository.

### 3. Feature engine

Initial features are deliberately simple and declared before evaluation:

- rolling number frequencies;
- draws-since-last-seen gaps;
- pair and triple co-occurrence with minimum-support controls;
- odd/even and low/high composition;
- sum and spread distributions;
- consecutive-number count;
- decade or range occupancy;
- overlap with the immediately preceding draw;
- agreement or disagreement across 30-, 90-, and 365-day windows.

Features that have insufficient sample support are ignored. The engine must not use draw order as a physical-machine signal unless the official publication order is proven to preserve ball order consistently.

### 4. Candidate methods

Version 1 evaluates several frozen methods independently:

- frequency-weighted;
- gap-weighted;
- pair-supported;
- distribution-balanced;
- ensemble rank combining the prior methods;
- uniform-random control.

Each method emits one unique valid combination per eligible draw. Ties are resolved by a seeded, recorded rule so that reruns are reproducible. Methods may be retired or replaced only through a new version evaluated on a fresh holdout period.

### 5. Walk-forward backtesting

For each historical draw, the system trains or calculates features using only records strictly before that draw, emits the prediction, then scores it after revealing the result.

Primary outcome metrics:

- number of matched balls;
- rate of 2+, 3+, 4+, 5+, and 6 matches;
- mean match count;
- calibration of the system's relative signal score;
- stability across non-overlapping time windows.

Every method is compared with at least 10,000 seeded random strategies using exactly one line per eligible draw. Comparisons are performed separately by game. Multiple-method and repeated-testing effects must be controlled so that adding more experiments cannot manufacture significance.

The pre-declared version-1 protocol is:

- The primary metric is mean matched balls per prediction on alert-eligible draw days.
- A method's daily signal score is the normalized margin between its chosen combination and the median score of 10,000 seeded, uniformly sampled valid combinations evaluated with the same frozen scoring function and same pre-draw features.
- The first 100 chronological predictions per game-method version are the immutable training period. A later draw is alert-eligible when its score meets or exceeds the method's 85th-percentile training threshold. The training cutoff and threshold are persisted and never move when future draws are appended.
- A method needs at least 200 total walk-forward predictions and at least 30 alert-eligible evaluation predictions for that game.
- Significance is a one-sided seeded randomization test against equal-budget random lines on the same eligible draw dates.
- Holm-Bonferroni correction controls family-wise error at 0.01 across all game-method hypotheses in the versioned experiment family.
- Alert-eligible evaluation predictions are split chronologically into two non-overlapping halves, each containing at least 15 predictions. Both halves must show a positive effect versus random, and the newer half must retain at least 50% of the full-period effect size.
- Secondary metrics, including 3+ match rate, are descriptive and cannot independently activate an alert.

Any change to these definitions creates a new method family and requires a fresh holdout period; it cannot be applied retroactively to rescue a failed experiment.

### 6. Strict notification gate

A game may emit a research-signal notification only when all of the following are true:

1. At least 200 walk-forward draws and at least 30 alert-eligible evaluation draws have been evaluated for that game.
2. The selected method was frozen before the current evaluation window.
3. Its pre-declared primary metric passes the one-sided randomization test after Holm-Bonferroni correction at family-wise alpha 0.01.
4. The direction of the effect is positive in both chronological halves of the alert-eligible evaluation predictions.
5. The newer half retains at least 50% of the full-period effect size.
6. Data validation passes with no unresolved missing, corrected, or ambiguous draw affecting the evaluation.
7. Today's method score meets the frozen 85th-percentile alert threshold.

Passing the gate does not change the mathematical jackpot odds of the emitted combination. The notification must say that it is an experimental historical signal, not a reliable prediction.

If no method passes, the run is silent. A collection failure is also silent on the first occurrence; Codex notifies only after the catch-up check also fails, an official correction changes an evaluated record, or user action is required.

### 7. Codex notification content

Each alert contains:

- game and target draw date;
- the one primary hypothetical combination;
- method name and immutable version;
- signal score and threshold;
- evaluated sample size;
- comparison with the equal-budget random distribution;
- recent-window stability result;
- source-data cutoff time;
- an explicit statement that jackpot odds remain unchanged and the result is not a guarantee or spending recommendation.

No-signal days produce no user-facing message.

### 8. Cloud execution and scheduling

- A GitHub Actions workflow runs on a standard GitHub-hosted Linux runner with least-privilege `contents: write` permission and no third-party secrets.
- The workflow is manually runnable with `workflow_dispatch` and scheduled with the IANA timezone `Asia/Manila`.
- Jobs use minute 17 rather than the top of the hour to reduce peak-time schedule delays.
- **10:17 PM daily:** ingest newly posted results and score completed predictions. This run does not issue a prediction for a draw that has already occurred.
- **7:17 AM daily:** verify the previous night's data, retry delayed results, process corrections, and create immutable predictions for games scheduled that evening. The source-data cutoff is the recorded workflow start time; qualifying research-signal state is written only after all validations pass.
- **Monday after verification:** recompute the weekly audit, refresh backtest summaries, and detect model degradation. Notify only on a newly passing signal, loss of a previously passing signal, a correction with material impact, or required user action.

If required prior data remains missing during the morning run, the affected prediction is withheld rather than built from an ambiguous cutoff, and an actionable failure state is written for Codex.

GitHub Actions scheduled runs may be delayed or dropped under platform load and public-repository schedules can be disabled after 60 days without repository activity. The pipeline records a heartbeat in repository state, daily result commits normally keep the repository active, and the Codex monitor alerts when the latest successful run is stale.

### 9. Codex-only notifications

GitHub Actions performs collection, validation, deterministic analysis, and backtesting without an AI model. It writes public machine-readable state only when there is a newly qualifying signal, a materially changed signal, a repeated collection failure, a stale workflow, or required user action.

A Codex cloud scheduled task reads only those compact repository state files and remains silent when their event identifiers are unchanged. It uses the least-expensive available model that can reliably perform the check, with GPT-6 Luna low as the preferred option. This task is the only notification surface; the repository workflow does not send email, SMS, or third-party messages.

### 10. Model and cost policy

- Daily collection, statistical calculations, simulations, and thresholds: deterministic code on GitHub Actions, with no model call.
- Codex state-file monitor: GPT-6 Luna at low reasoning when available.
- Weekly review and concise interpretation: GPT-6.1 Sol at medium reasoning only when an event requires interpretation; otherwise no weekly narrative is produced.
- GPT-6 Astra: manual escalation only for difficult investigations; not part of the recurring loop.

Standard GitHub-hosted Actions runners are expected to cost USD 0 for this public repository under current GitHub pricing. The recurring OpenAI metered-usage ceiling is USD 5 per calendar month, or the equivalent measured plan usage when direct dollar metering is unavailable. At 80% of the ceiling, optional Sol interpretation is disabled. At 100%, cost-incurring optional runs pause and Codex sends one actionable notice; deterministic GitHub processing may continue. The system never upgrades itself to Astra.

Before scheduling, the implementation checks which named models and automation features are available on the account. If Luna is unavailable, it uses the least-expensive available model that passes the extraction fixtures. If Sol is unavailable, the weekly narrative is omitted; statistical evaluation remains deterministic.

The Codex monitor receives compact computed state rather than full raw history. Cached stable instructions are reused where supported. The initial expected API-equivalent recurring OpenAI cost remains roughly USD 0.60–2.00 per month, subject to actual tokens, connected-app calls, retries, plan allowance, and pricing changes.

## Failure and recovery behavior

- Late result: mark pending and retry during the 7:17 AM workflow.
- Markup or endpoint change: quarantine the parse, keep prior data intact, and notify after verification also fails.
- Official correction: append a revision, recompute affected outcomes and backtests, and report if the gate changes.
- Duplicate run: idempotency keys prevent duplicate results or predictions.
- Partial write: use a database transaction and roll back the incomplete run.
- Network or runner failure: retain committed deterministic work, record the failed step, and retry at the next scheduled check.
- Cost anomaly: stop optional interpretation and notify if a configurable monthly budget ceiling is approached.

## Verification and acceptance criteria

Before scheduling production runs:

- Unit tests cover normalization, validation, feature cutoffs, seeded generation, and scoring.
- Fixture-based collector tests cover normal, late, malformed, duplicate, and corrected results.
- Leakage tests prove that changing a future draw cannot alter an earlier prediction.
- Backtest tests compare equal numbers of candidate and random lines.
- A replay of known history is deterministic.
- A dry run creates no notification on an ordinary no-signal day.
- A synthetic passing case creates the required Codex alert.
- A first collection failure stays quiet; a repeated failure after catch-up produces one actionable notice.
- Estimated recurring usage is measured during the dry-run period.

## Rollout

1. Build and test the collector, repository state format, and derived schema.
2. Run a seven-day live collection spike without predictions or notifications.
3. Backfill official history and validate it.
4. Freeze version-1 methods and run walk-forward backtests.
5. Keep the notification gate in shadow mode for at least two weeks.
6. Review false alarms, missing data, and actual cost.
7. Enable Codex-only research-signal notifications if acceptance criteria pass.

## Decisions made by the builder

The builder may choose implementation language, libraries, internal module boundaries, and exact schema details, provided the result remains deterministic, testable, inexpensive, and compatible with GitHub Actions plus Codex monitoring. A small Python application with standard-library-first dependencies, append-only text records, and a derived SQLite cache is the expected default because it fits the workload and minimizes operational overhead.

