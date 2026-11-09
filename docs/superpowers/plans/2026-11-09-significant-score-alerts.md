# Significant Score Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Notify the Codex chat only when a completed lotto prediction scores at least 2/6 while retaining every score in GitHub.

**Architecture:** Extend scorecard publication with a deterministic `significant_score` event containing qualifying entries and rolling evidence. Update the Codex monitor contract to consume that event and silently advance over ordinary scorecards.

**Tech Stack:** Python 3.12, pytest, repository JSON/JSONL state, GitHub Actions, Codex scheduled prompt.

**Spec:** `docs/superpowers/specs/2026-11-09-significant-score-alerts-design.md`

## Global Constraints

- Alert threshold is `matched_count >= 2`.
- All scorecards and outcomes remain stored in GitHub.
- Events are content-addressed and unchanged replay is idempotent.
- Do not describe overlap as a prize, win, predictive edge, or high-probability signal.
- No external notification channel and no automatic tuning.

## Review Focus

- Pending, 0/6, and 1/6 entries must not qualify (Task 1 tests).
- Multiple 2/6+ entries on one date must form one event without losing per-game detail (Task 1 tests).
- Unchanged replay must not append a duplicate event (Task 1 tests).
- Official correction crossing from below to at/above threshold must create a new significant event (Task 1 tests).
- The Codex cursor must advance over suppressed daily scorecards so they are not reconsidered forever (Task 2 contract test).

---

### Task 1: Deterministic significant-score event

**Files:**
- Modify: `src/lotto_signal/workflow.py`
- Modify: `tests/test_workflow.py`

**Interfaces:**
- Consumes: `_scorecard_payload`, `_scorecard_events`, `_event`, `_incident_id`.
- Produces: event kind `significant_score` with `threshold`, `target_draw_date`, `qualifying_entries`, `performance`, and `disclaimer`.

- [ ] Write failing workflow tests for 1/6 suppression, 2/6 emission, multi-game grouping, unchanged replay, and correction threshold crossing.
- [ ] Run the focused tests and confirm failures because `significant_score` is not emitted.
- [ ] Implement minimal significant-event derivation in `_scorecard_events` with threshold `2` and content-addressed identity.
- [ ] Run workflow tests and confirm they pass.
- [ ] Commit as `feat: emit significant score alerts`.

### Task 2: Codex delivery contract and operations guidance

**Files:**
- Modify: `codex/monitor-prompt.md`
- Modify: `docs/operations.md`
- Modify: `tests/test_monitor_contract.py`

**Interfaces:**
- Consumes: `significant_score` event payload from Task 1.
- Produces: Codex-only notification behavior for 2/6+ and silence for ordinary scorecards.

- [ ] Write failing contract assertions for the event kind, threshold, cursor advancement, lower-score silence, report fields, and odds disclaimer.
- [ ] Run contract tests and confirm failures against the old always-report scorecard instructions.
- [ ] Update the prompt and operations guide with the approved behavior and cost posture.
- [ ] Run contract tests and then the full suite.
- [ ] Commit as `docs: notify only on significant scores`.

### Task 3: Review and live verification

**Files:**
- Verify all changed files and generated state.

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: reviewed `main` and a successful live cloud run.

- [ ] Run the full suite and `git diff --check`.
- [ ] Request one whole-branch read-only review focused on threshold boundaries, corrections, deduplication, and notification safety.
- [ ] Fix Critical or Important findings with RED→GREEN coverage.
- [ ] Publish to `main`, dispatch one cloud evening or backfill run, and require success.
- [ ] Verify event order, unique IDs, ordinary scorecard retention, and significant-event behavior.
