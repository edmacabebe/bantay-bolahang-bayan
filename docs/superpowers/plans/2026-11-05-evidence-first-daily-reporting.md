# Evidence-First Daily Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore daily official collection and publish timestamped, evidence-first `n/6` score reports with rolling random-baseline metrics.

**Architecture:** Point the strict PCSO client at the current official LottoMatik worker and let morning collection failures continue through a cached-history fallback. Add a focused reporting module that derives revision-aware metrics from immutable predictions and active official draws, then embed those metrics in content-addressed scorecard events and the Codex notification contract.

**Tech Stack:** Python 3.12, `httpx`, JSON/JSONL repository state, `pytest`, GitHub Actions, Codex scheduled monitor.

**Spec:** `docs/superpowers/specs/2026-11-05-evidence-first-daily-reporting-design.md`

## Global Constraints

- Monitor all five configured six-number games and predict only games scheduled for the target date.
- Official LottoMatik data is authoritative; preserve strict schema, game, schedule, number, and correction validation.
- Historical fallback suppresses production research signals and must be labeled **historical-data guess**.
- Pending results use `null`, never zero, for result-dependent metrics.
- Report timestamps use timezone-aware event `created_at` rendered in `Asia/Manila`; timestamps do not enter content-addressed scorecard payloads.
- Daily outcomes provide evaluation evidence only; method changes remain manual and weekly-audit-gated.

## Review Focus

- Official proxy returns 404 while the current official worker succeeds: collection uses the worker without weakening validation (Task 1 tests).
- First and repeated morning source failures: cached-history predictions remain idempotent, incident events dedupe, and production signals stay suppressed (Task 1 tests).
- No completed lines in a rolling window: averages and deltas are `null`, distribution remains complete, and no divide-by-zero occurs (Task 2 tests).
- Mixed games have different random overlap expectations: the aggregate benchmark is line-weighted, not based on one game's number ceiling (Task 2 tests).
- Official corrections and delayed history: active replacement draws change scorecard metrics and create one new content version without duplicating unchanged events (Task 3 tests).

---

### Task 1: Official source recovery and source-error historical fallback

**Files:**
- Modify: `src/lotto_signal/pcso.py`
- Modify: `src/lotto_signal/workflow.py`
- Modify: `tests/test_pcso.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Consumes: existing `PcsoClient`, `RunContext`, `RepositoryStore`, `_scheduled_games`, `_finish`, and source-incident event behavior.
- Produces: `DEFAULT_BASE_URL = "https://lottomatik-backend.api-lottomatik.workers.dev"`; morning status `historical_fallback_source_error`; cached-history predictions with production signals suppressed after collection errors.

- [ ] **Step 1: Write failing source-host and fallback tests**

Add `test_default_client_uses_current_official_lottomatik_worker` asserting the default request host and `/get-results` path. Add `test_morning_source_error_generates_cached_historical_predictions` asserting scheduled games, immutable predictions, `historical_fallback_source_error`, `source_fresh is False`, source incident preservation, heartbeat status, and no `research_signal`. Add a duplicate-run assertion proving prediction and event idempotency.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_pcso.py::test_default_client_uses_current_official_lottomatik_worker tests/test_workflow.py::test_morning_source_error_generates_cached_historical_predictions -v`

Expected: FAIL because the default host is the retired proxy and `run_morning` returns before prediction generation.

- [ ] **Step 3: Implement the minimal source and fallback changes**

Update `DEFAULT_BASE_URL`. Refactor morning collection so a `PcsoSourceError` supplies no new records but continues with stored draws, a source-error incident, fallback prediction generation, and production suppression. Preserve ordinary stale-source behavior and keep evening failure semantics unchanged.

- [ ] **Step 4: Run source and workflow tests GREEN**

Run: `.venv/bin/python -m pytest tests/test_pcso.py tests/test_workflow.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lotto_signal/pcso.py src/lotto_signal/workflow.py tests/test_pcso.py tests/test_workflow.py
git commit -m "fix: recover daily guesses during source outages"
```

### Task 2: Deterministic performance metrics

**Files:**
- Create: `src/lotto_signal/reporting.py`
- Create: `tests/test_reporting.py`
- Modify: `src/lotto_signal/store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Consumes: `Prediction`, active `DrawRecord` projections, `GAMES`, and repository prediction/draw paths.
- Produces: `RepositoryStore.load_predictions(game_code: str) -> tuple[Prediction, ...]`; `performance_summary(store: RepositoryStore, as_of: date) -> dict[str, Any]` with `last_7_days`, `last_30_days`, `lifetime`, and `tuning_guardrail`.

- [ ] **Step 1: Write failing repository and metric tests**

Add a store test for chronological typed prediction loading. In `tests/test_reporting.py`, seed mixed-game completed and pending predictions and assert each window's `completed_lines`, `total_matches`, `total_predicted_numbers`, `average_matches_per_line`, `match_rate`, line-weighted `random_expected_average`, `match_delta_vs_random`, and complete `0/6`…`6/6` distribution. Assert empty windows use `null` averages/deltas. Assert `tuning_guardrail` requires 30 completed lines and keeps `automatic_tuning` false.

- [ ] **Step 2: Run metric tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_store.py::test_load_predictions_returns_typed_chronological_rows tests/test_reporting.py -v`

Expected: FAIL because the store API and reporting module do not exist.

- [ ] **Step 3: Implement store loading and reporting functions**

Use active corrected draw projections and one primary prediction per game/date. Calculate random expected matches per line as `36 / game.max_number`; round published floating metrics to six decimals. Use calendar windows inclusive of `as_of` and keep the lifetime window unbounded.

- [ ] **Step 4: Run metric and store tests GREEN**

Run: `.venv/bin/python -m pytest tests/test_store.py tests/test_reporting.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lotto_signal/reporting.py src/lotto_signal/store.py tests/test_reporting.py tests/test_store.py
git commit -m "feat: calculate rolling prediction performance"
```

### Task 3: Rich scorecards, delayed results, and corrections

**Files:**
- Modify: `src/lotto_signal/workflow.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Consumes: `performance_summary(...)`, `RepositoryStore.load_predictions(...)`, prediction metadata, and active official draws.
- Produces: enriched `daily_scorecard` entries and rolling performance payload; outcome scoring from morning, evening, backfill, and audit collection modes.

- [ ] **Step 1: Write failing enriched-scorecard tests**

Extend pending and completed scorecard tests. Pending entries assert `score: "pending"` and `null` result-dependent values. Completed entries assert `score: "3/6"`, matched numbers, missed predicted numbers, unselected winning numbers, match rate, random expectation/delta, method version, signal score, prediction creation time, and source cutoff. Assert the scorecard carries the three performance windows and tuning guardrail.

- [ ] **Step 2: Write failing delayed/correction outcome tests**

Extend the backfill/audit test to assert `outcomes_written`, updated rolling metrics, a changed scorecard event after correction, and no duplicate event for unchanged replay.

- [ ] **Step 3: Run workflow tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`

Expected: FAIL on missing enriched fields, performance summary, and backfill/audit outcome counts.

- [ ] **Step 4: Implement enriched scorecards and collection scoring**

Add deterministic entry fields from the spec, attach `performance_summary(store, target_draw_date)` to each scorecard, and call `score_completed_predictions(context.now)` after merges in all four collection modes. Keep event IDs content-addressed from semantic payload only.

- [ ] **Step 5: Run workflow tests GREEN**

Run: `.venv/bin/python -m pytest tests/test_workflow.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lotto_signal/workflow.py tests/test_workflow.py
git commit -m "feat: publish evidence-first daily scorecards"
```

### Task 4: Timestamped Codex reporting and operations contract

**Files:**
- Modify: `codex/monitor-prompt.md`
- Modify: `docs/operations.md`
- Modify: `tests/test_monitor_contract.py`
- Add: `docs/superpowers/specs/2026-11-05-evidence-first-daily-reporting-design.md`
- Add: `docs/superpowers/plans/2026-11-05-evidence-first-daily-reporting.md`

**Interfaces:**
- Consumes: `daily_scorecard` payload and event `created_at` from Tasks 1–3.
- Produces: every user-facing monitor notification begins with a PHT report timestamp and completed comparisons show the approved metrics and guardrails.

- [ ] **Step 1: Write failing monitor-contract tests**

Assert the prompt requires `Report timestamp`, `Asia/Manila`, `score` as `n/6`, matched/missed/unselected numbers, 7-day/30-day/lifetime summaries, random baseline, source cutoff, and no automatic daily tuning. Assert operations documents the current official worker and source-error fallback.

- [ ] **Step 2: Run contract tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_monitor_contract.py -v`

Expected: FAIL because timestamp and rich-metric instructions are absent.

- [ ] **Step 3: Update prompt and operations documentation**

Require timestamps on actionable, scorecard, and production-signal notifications. Keep unchanged-state silence and one-notification-per-event behavior. Explain that scores count shared balls, not prizes or probability changes, and that tuning remains weekly-audit-gated.

- [ ] **Step 4: Run contract tests GREEN**

Run: `.venv/bin/python -m pytest tests/test_monitor_contract.py -v`

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass with zero failures.

- [ ] **Step 6: Commit**

```bash
git add codex/monitor-prompt.md docs/operations.md tests/test_monitor_contract.py docs/superpowers/specs/2026-11-05-evidence-first-daily-reporting-design.md docs/superpowers/plans/2026-11-05-evidence-first-daily-reporting.md
git commit -m "docs: define timestamped evidence reports"
```

### Task 5: Review, deploy, and backfill live state

**Files:**
- Verify all changed files and generated repository state.

**Interfaces:**
- Consumes: completed Tasks 1–4.
- Produces: reviewed `main`, successful cloud backfill and morning runs, completed historical scorecards, current-day historical-data guesses, and a timestamped user report.

- [ ] **Step 1: Run clean full verification and diff checks**

Run: `.venv/bin/python -m pytest -q`

Run: `git diff --check`

Expected: all tests pass; no whitespace errors.

- [ ] **Step 2: Request whole-branch code review**

Review source-failure incident continuity, prediction immutability, metric math, correction versioning, event deduplication, and notification safety. Resolve all Critical and Important findings and rerun the full suite.

- [ ] **Step 3: Publish reviewed commits to `main`**

Fetch `origin/main`, reconcile any automated state commits without dropping them, then fast-forward/push the reviewed feature.

- [ ] **Step 4: Run cloud backfill and morning recovery**

Dispatch `backfill` first so November 1–4 official results score existing guesses, then dispatch `morning` so the current scheduled games receive historical-data guesses even if collection regresses. Require successful workflow conclusions.

- [ ] **Step 5: Verify committed live artifacts**

Fetch cloud state and inspect `state/last_run.json`, `state/heartbeats.json`, `state/daily_scorecard.json`, all affected `state/scorecards/*.json`, outcome JSONL, and event order. Confirm every completed line has `n/6`, exact matches, rolling summaries, provenance, and no duplicate unchanged events.

- [ ] **Step 6: Deliver timestamped report**

Report the exact PHT timestamp, run links, today's scheduled historical-data guesses, scored backlog, rolling metrics versus random expectation, source status, and the statement that number overlap does not change jackpot odds.
