# Historical Fallback and Missed-Schedule Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate clearly labeled historical-data combinations when the prior PCSO draw is missing, and automatically recover a missed GitHub morning or evening schedule without duplicate processing.

**Architecture:** The existing deterministic morning pipeline will continue past its stale-source check, persist the day's scheduled-game combinations and gate evidence, and suppress every production signal for that run. A shared heartbeat module will give both the monitor and a separate lightweight GitHub watchdog one operational-date contract; the watchdog will only dispatch the existing monitor workflow when the expected heartbeat is absent.

**Tech Stack:** Python 3.12, pytest, JSON/JSONL repository state, GitHub Actions, GitHub CLI

**Spec:** `docs/superpowers/specs/2026-10-29-historical-fallback-watchdog-design.md`

## Global Constraints

- Keep production research signals disabled in `config/runtime.json`.
- Preserve existing prediction IDs, audit-family IDs, thresholds, data files, and immutable prediction behavior.
- A historical fallback must use status `historical_fallback` and `source_fresh: false`.
- A historical fallback may emit its deduplicated `action_required` event, but it must never emit a production `research_signal` event.
- Monitor all five configured games, while generating a combination only for each game scheduled on the target day.
- Keep the existing 7:17 AM and 10:17 PM `Asia/Manila` collection schedules as the primary jobs.
- The watchdog must never calculate combinations or edit repository state directly.
- Do not describe a historical-fallback combination as higher probability; jackpot odds remain unchanged.

## Review Focus

- A missing, malformed, or non-object `state/heartbeats.json` must cause a safe watchdog dispatch, covered in Task 3.
- A heartbeat for the wrong mode, wrong operational date, or a future date must not satisfy the current check, covered in Task 3.
- The evening operational-date boundary must map times before noon to the prior Manila date and noon or later to the current date, covered in Task 1.
- Repeating a stale morning run must not change an existing prediction or duplicate its actionable event, covered in Task 2.
- An otherwise eligible, production-enabled decision must still be suppressed during historical fallback, covered in Task 2.

---

### Task 1: Per-mode operational heartbeats

**Files:**
- Create: `src/lotto_signal/heartbeat.py`
- Modify: `src/lotto_signal/workflow.py:195-242`
- Test: `tests/test_workflow.py:133-216`

**Interfaces:**
- Consumes: timezone-aware `datetime`, repository root, run mode, and final run status from `_finish(...)`.
- Produces: `operational_date(mode: str, now: datetime) -> date`, `record_heartbeat(root: Path, mode: str, now: datetime, status: str) -> None`, and `heartbeat_matches(root: Path, mode: str, expected_date: date) -> bool` in `heartbeat.py`.
- Produces: `state/heartbeats.json` with top-level `morning` and/or `evening` entries containing exactly `operational_date`, `finished_at`, and `status`.

- [ ] **Step 1: Write failing heartbeat and operational-date tests**

  Add `test_monitor_attempts_record_and_preserve_mode_heartbeats`, covering a successful morning, successful evening, pending evening, and morning/evening source errors. Its key assertions are:

  ```python
  assert heartbeats["morning"] == {
      "operational_date": morning.date().isoformat(),
      "finished_at": morning.isoformat(),
      "status": expected_morning_status,
  }
  assert heartbeats["evening"] == {
      "operational_date": expected_evening_date.isoformat(),
      "finished_at": evening.isoformat(),
      "status": expected_evening_status,
  }
  ```

  Add `test_evening_operational_date_uses_noon_boundary`:

  ```python
  assert operational_date("evening", at_0300) == at_0300.date() - timedelta(days=1)
  assert operational_date("evening", at_noon) == at_noon.date()
  ```

- [ ] **Step 2: Run the focused tests and verify they fail**

  Run: `python -m pytest tests/test_workflow.py -k 'heartbeat or operational_date' -v`

  Expected: FAIL because `state/heartbeats.json` and the operational-date helper do not exist.

- [ ] **Step 3: Implement the heartbeat contract**

  Implement the three declared functions in `src/lotto_signal/heartbeat.py`. Treat absent, malformed, or non-object heartbeat content as empty; write updates atomically; require timezone-aware times; and leave non-target mode entries intact. Call `record_heartbeat(...)` from `_finish(...)` only for `morning` and `evening`, so handled source errors are attempts but `audit` and `backfill` are not.

- [ ] **Step 4: Run focused and existing workflow tests**

  Run: `python -m pytest tests/test_workflow.py -v`

  Expected: all workflow tests PASS.

- [ ] **Step 5: Commit the heartbeat deliverable**

  ```bash
  git add src/lotto_signal/heartbeat.py src/lotto_signal/workflow.py tests/test_workflow.py
  git commit -m "feat: record monitor heartbeats"
  ```

### Task 2: Safe historical fallback combinations

**Files:**
- Modify: `src/lotto_signal/workflow.py:616-779`
- Modify: `src/lotto_signal/cli.py:24-26`
- Modify: `tests/test_workflow.py:219-233,301-382`
- Modify: `tests/test_cli.py:1-11`

**Interfaces:**
- Consumes: Task 1's `record_heartbeat(...)` through the existing `_finish(...)` path.
- Produces: a handled `RunReport(status="historical_fallback", source_fresh=False, ...)` with immutable predictions for every game scheduled on the target date.
- Produces: root metadata in `state/gate_decisions.json`: `historical_fallback: bool`, `missing_expected_games: list[str]`, and `production_alerts_suppressed: bool`.
- Produces: one deduplicated stale-source `action_required` payload stating that historical combinations were generated and production alerts were suppressed.

- [ ] **Step 1: Replace the stale-withholding test with failing fallback contract tests**

  Add `test_missing_previous_results_generate_historical_fallback` with these key assertions:

  ```python
  assert report.status == "historical_fallback"
  assert report.source_fresh is False
  assert report.prediction_games == ("GL55", "ML45")
  assert decisions["historical_fallback"] is True
  assert decisions["missing_expected_games"] == ["LOTTO42", "SL49", "UL58"]
  assert decisions["production_alerts_suppressed"] is True
  assert heartbeats["morning"]["status"] == "historical_fallback"
  assert [event.kind for event in inspect_events(tmp_path, None)] == ["action_required"]
  assert event.payload["historical_combinations_generated"] is True
  assert event.payload["production_alerts_suppressed"] is True
  ```

  Add `test_historical_fallback_retry_is_idempotent`, retaining the first prediction-file bytes and event IDs and asserting the retry writes zero predictions and changes neither.

- [ ] **Step 2: Add a failing production-suppression test and CLI status test**

  Add `test_historical_fallback_suppresses_eligible_production_signal`:

  ```python
  assert report.status == "historical_fallback"
  assert {event.kind for event in inspect_events(tmp_path, None)} == {"action_required"}
  assert decisions["production_alerts_suppressed"] is True
  ```

  Extend the ordinary shadow test to assert the three metadata fields are `False`, `[]`, and `False`. Extend `test_handled_operational_states_allow_cloud_state_commit` with `assert report_exit_code("historical_fallback") == 0`.

- [ ] **Step 3: Run the new tests and verify they fail**

  Run: `python -m pytest tests/test_workflow.py -k 'fallback or stale' tests/test_cli.py -v`

  Expected: FAIL because the morning pipeline still returns before prediction generation and the CLI does not handle `historical_fallback`.

- [ ] **Step 4: Continue the existing morning pipeline in fallback mode**

  Replace the early stale return with a `historical_fallback` flag, enrich the deduplicated event payload, generate/reuse ordinary immutable predictions, add the declared gate metadata, guard production event emission with `not historical_fallback`, and select final status/freshness from the flag. Add `historical_fallback` to `HANDLED_STATUSES`.

- [ ] **Step 5: Run workflow and CLI tests**

  Run: `python -m pytest tests/test_workflow.py tests/test_cli.py -v`

  Expected: all selected tests PASS, including immutable retries and fresh-run production behavior.

- [ ] **Step 6: Commit the fallback deliverable**

  ```bash
  git add src/lotto_signal/workflow.py src/lotto_signal/cli.py tests/test_workflow.py tests/test_cli.py
  git commit -m "feat: generate safe historical fallbacks"
  ```

### Task 3: Conditional GitHub watchdog

**Files:**
- Create: `src/lotto_signal/watchdog.py`
- Create: `.github/workflows/lotto-watchdog.yml`
- Create: `tests/test_watchdog.py`
- Modify: `tests/test_workflow_config.py:1-62`

**Interfaces:**
- Consumes: Task 1's `heartbeat_matches(root: Path, mode: str, expected_date: date) -> bool`.
- Produces: `WatchdogDecision(mode: str, operational_date: date, dispatch: bool, reason: str)`, `watchdog_decision(root: Path, schedule: str, now: datetime) -> WatchdogDecision`, and `main(argv: list[str] | None = None) -> int`.
- Produces: GitHub step outputs `dispatch`, `mode`, `operational_date`, and `reason` when invoked with `--github-output "$GITHUB_OUTPUT"`.
- Produces: a read-only watchdog workflow that dispatches `.github/workflows/lotto-monitor.yml` with `mode=morning|evening` only when `dispatch == true`.

- [ ] **Step 1: Write failing unit tests for all watchdog time slots**

  Add `test_watchdog_schedule_maps_to_mode_and_operational_date`:

  ```python
  assert target("7 8 * * *") == ("morning", today)
  assert target("7 9 * * *") == ("morning", today)
  assert target("7 23 * * *") == ("evening", today)
  assert target("7 0 * * *") == ("evening", today - timedelta(days=1))
  ```

  Add `test_matching_heartbeat_is_noop` with `assert decision.dispatch is False`. Parameterize `test_unusable_heartbeat_dispatches` over missing, malformed, non-object, wrong-mode, prior-date, and future-date files and assert `decision.dispatch is True` for each.

- [ ] **Step 2: Write failing workflow contract tests**

  Add `test_watchdog_workflow_is_read_only_and_conditionally_dispatches_monitor` with these key assertions:

  ```python
  assert schedules == {
      ("7 8 * * *", "Asia/Manila"),
      ("7 9 * * *", "Asia/Manila"),
      ("7 23 * * *", "Asia/Manila"),
      ("7 0 * * *", "Asia/Manila"),
  }
  assert workflow["permissions"] == {"contents": "read", "actions": "write"}
  assert "PYTHONPATH=src python -m lotto_signal.watchdog" in text
  assert "gh workflow run lotto-monitor.yml" in text
  assert "commit-state.sh" not in text
  assert "lotto-signal morning" not in text
  ```

- [ ] **Step 3: Run the watchdog tests and verify they fail**

  Run: `python -m pytest tests/test_watchdog.py tests/test_workflow_config.py -v`

  Expected: FAIL because the watchdog module and workflow do not exist.

- [ ] **Step 4: Implement deterministic watchdog decisions and GitHub outputs**

  Implement the declared dataclass/functions using a fixed schedule map and `Asia/Manila`; reject unknown schedules and naive `--now` values with a nonzero exit. The CLI reads repository state only and appends the declared values to the provided GitHub output path.

- [ ] **Step 5: Add the lightweight watchdog workflow**

  Configure the four backup schedules and a single job that checks out the repository, sets up Python 3.12, runs the module directly from `src`, and uses the repository token to dispatch the existing monitor only on a missing heartbeat. Do not install project dependencies, run analysis, or commit files in this workflow.

- [ ] **Step 6: Run watchdog and workflow tests**

  Run: `python -m pytest tests/test_watchdog.py tests/test_workflow_config.py -v`

  Expected: all selected tests PASS.

- [ ] **Step 7: Commit the watchdog deliverable**

  ```bash
  git add src/lotto_signal/watchdog.py .github/workflows/lotto-watchdog.yml tests/test_watchdog.py tests/test_workflow_config.py
  git commit -m "feat: recover missed monitor schedules"
  ```

### Task 4: User-facing safeguards and cloud rollout

**Files:**
- Modify: `codex/monitor-prompt.md`
- Modify: `docs/operations.md`
- Modify: `tests/test_monitor_contract.py`
- Verify: `config/runtime.json`
- Verify after cloud run: `state/last_run.json`, `state/heartbeats.json`, `state/gate_decisions.json`, `data/predictions/*.jsonl`, and `alerts/events.jsonl`

**Interfaces:**
- Consumes: Tasks 1-3's state schema, status, and workflows.
- Produces: operator instructions and Codex copy rules that call fallback output a historical-data guess, never a higher-probability signal.
- Produces: a pushed release and a successful manual morning cloud smoke run whose persisted combinations can be reported to the user.

- [ ] **Step 1: Write failing documentation contract tests**

  Extend the prompt contract with:

  ```python
  assert "historical_fallback" in prompt
  assert "historical-data guess" in prompt
  assert "never call" in prompt and "high probability" in prompt
  assert "production alerts were suppressed" in prompt
  ```

  Extend the operations contract to require `state/heartbeats.json`, the before-noon prior-evening rule, and the strings `8:07 AM`, `9:07 AM`, `11:07 PM`, and `12:07 AM`.

- [ ] **Step 2: Run the contract tests and verify they fail**

  Run: `python -m pytest tests/test_monitor_contract.py -v`

  Expected: FAIL because the new status and watchdog operations are not documented.

- [ ] **Step 3: Update the prompt and operations guide**

  Add the tested historical-fallback language, heartbeat schema, schedule recovery behavior, and manual recovery inspection steps. Preserve the existing Codex-only notification and $5 monthly ceiling policies.

- [ ] **Step 4: Run the complete local verification suite**

  Run: `python -m pytest -v`

  Expected: all tests PASS.

  Run: `PYTHONPATH=src python -m lotto_signal.watchdog --root . --schedule '7 8 * * *' --now '2026-10-29T08:07:00+08:00'`

  Expected: valid JSON decision output and exit code 0.

  Run: `python -c 'import json; assert json.load(open("config/runtime.json"))["production_research_signals"] is False'`

  Expected: exit code 0.

- [ ] **Step 5: Commit the safeguards and plan artifacts**

  ```bash
  git add codex/monitor-prompt.md docs/operations.md tests/test_monitor_contract.py docs/superpowers/specs/2026-10-29-historical-fallback-watchdog-design.md docs/superpowers/plans/2026-10-29-historical-fallback-watchdog.md
  git commit -m "docs: explain fallback and watchdog operations"
  ```

- [ ] **Step 6: Integrate the latest cloud-generated state and push**

  Run: `git fetch origin && git rebase origin/main`

  Expected: local feature commits replay cleanly over the latest automated data commit.

  Run: `git push origin main`

  Expected: the public `main` branch contains the feature, watchdog, tests, and docs.

- [ ] **Step 7: Trigger and verify the cloud smoke run**

  Run: `gh workflow run lotto-monitor.yml --ref main -f mode=morning`

  Then obtain the new run ID, wait for completion, and inspect its conclusion and logs.

  Expected: tests pass, the monitor exits successfully with `ok` or `historical_fallback`, and auditable state is committed.

- [ ] **Step 8: Verify and report the persisted historical guesses**

  Fetch and fast-forward/rebase the cloud state commit, then assert the relevant `state/heartbeats.json` entry matches the target operational date; if the run is fallback, assert `source_fresh` is false, gate metadata names the missing games, only the stale `action_required` event was emitted, and production signals remain off. Read each prediction for the target date and report the scheduled games' six-number combinations with the explicit label “historical-data guess”; explain that the other monitored games have no draw that day.

