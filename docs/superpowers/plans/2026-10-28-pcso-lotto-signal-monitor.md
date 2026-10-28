# PCSO Lotto Signal Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish an MIT-licensed Python service that collects all five PCSO six-number lotto games, runs leakage-safe deterministic backtests in free public GitHub Actions, and exposes only strictly gated events to a silent Codex cloud monitor.

**Architecture:** GitHub Actions calls official PCSO JSON endpoints and commits append-only, reviewable records to the public repository. Python code rebuilds a local SQLite cache for analysis, emits immutable predictions, evaluates frozen methods against seeded equal-budget random baselines, and writes compact event state; a separate Codex scheduled task reads that state and notifies only on a new event identifier.

**Tech Stack:** Python 3.12, `httpx`, standard-library `sqlite3`, `pytest`, GitHub Actions, JSON Lines, MIT License

**Spec:** `docs/superpowers/specs/2026-10-28-pcso-lotto-signal-monitor-design.md`

## Global Constraints

- Monitor `LOTTO42`, `ML45`, `SL49`, `GL55`, and `UL58` separately.
- Use `Asia/Manila` for schedules and draw-date decisions.
- Use official PCSO/LottoMatik data for the production evidence gate.
- Emit one primary hypothetical combination per eligible game and draw; never purchase tickets or recommend stakes.
- Predictions become immutable at their recorded pre-draw source-data cutoff.
- Require 200 walk-forward predictions and 30 alert-eligible predictions before any game can pass the gate.
- Use the frozen version-1 protocol, 10,000 seeded random strategies, Holm-Bonferroni family-wise alpha `0.01`, and the frozen 85th-percentile daily threshold.
- Remain silent on unchanged state and first collection failures.
- Use no model calls in GitHub Actions; never auto-upgrade to GPT-6 Astra.
- Keep OpenAI metered usage below USD 5 per calendar month.
- Commit no credentials, private identifiers, or private notification content.
- Publish as `pcso-lotto-signal-monitor` under the MIT License.

## Review Focus

- The official history response currently places a draw identifier in `lottery`; normalization must use the requested game code and validate the identifier prefix.
- A corrected official draw with the same ID must append a revision and recompute dependent outcomes without rewriting the original observation.
- Concurrent or retried GitHub runs must not duplicate records, predictions, events, or overwrite a newer branch head.
- A stale official endpoint or delayed scheduled run must produce no prediction from ambiguous data and must surface one actionable event only after the retry policy is exhausted.
- Changing any future draw must not change an earlier feature snapshot, candidate, random seed, backtest result, or gate decision.

---

### Task 1: Repository foundation and domain contracts

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `src/lotto_signal/__init__.py`
- Create: `src/lotto_signal/games.py`
- Create: `src/lotto_signal/domain.py`
- Test: `tests/test_domain.py`

**Interfaces:**
- Produces: `GameSpec(code: str, name: str, max_number: int, draw_weekdays: frozenset[int])`
- Produces: `GAMES: Mapping[str, GameSpec]`
- Produces: immutable `DrawRecord`, `DrawRevision`, `Prediction`, and `MonitorEvent` dataclasses with JSON-safe `to_dict()` methods.

- [ ] **Step 1: Initialize Git and write failing domain tests**

Run `git init -b main`, then test that all five game codes, number ceilings, and official weekday schedules are exact; valid draw records preserve published order plus sorted values; invalid count, duplicates, out-of-range numbers, naive timestamps, and unknown games raise `ValueError`.

- [ ] **Step 2: Run the domain tests and verify failure**

Run: `python -m pytest tests/test_domain.py -v`  
Expected: FAIL because `lotto_signal.games` and `lotto_signal.domain` do not exist.

- [ ] **Step 3: Add packaging, domain types, MIT license, README disclaimer, and ignore rules**

Require Python `>=3.12`; declare `httpx>=0.28,<0.29` and a `dev` extra with `pytest>=8,<9` plus `PyYAML>=6,<7`. The README must say the project is experimental, does not improve mathematical jackpot odds, and does not provide gambling or financial advice.

- [ ] **Step 4: Run the domain tests**

Run: `python -m pip install -e '.[dev]' && python -m pytest tests/test_domain.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore LICENSE README.md src/lotto_signal tests/test_domain.py
git commit -m "chore: establish lotto monitor domain"
```

### Task 2: Official PCSO client and normalization

**Files:**
- Create: `src/lotto_signal/pcso.py`
- Create: `tests/fixtures/pcso/latest.json`
- Create: `tests/fixtures/pcso/history_page.json`
- Test: `tests/test_pcso.py`

**Interfaces:**
- Consumes: `GAMES`, `DrawRecord`
- Produces: `HistoryPage(page: int, per_page: int, total: int, total_pages: int, items: tuple[DrawRecord, ...])`
- Produces: `PcsoClient(client: httpx.Client, base_url: str = "https://lottomatik.pcso.gov.ph/api/backend")`
- Produces: `PcsoClient.fetch_latest(retrieved_at: datetime) -> tuple[DrawRecord, ...]`
- Produces: `PcsoClient.fetch_history_page(game_code: str, page: int, per_page: int, retrieved_at: datetime) -> HistoryPage`
- Produces: `PcsoClient.iter_history(game_code: str, retrieved_at: datetime, per_page: int = 100) -> Iterator[DrawRecord]`

- [ ] **Step 1: Save sanitized fixtures and write failing client tests**

Cover `/get-results` and `/get-game-history`; assert requested `LOTTO42` overrides the history payload's erroneous `lottery: LOTTO42S...`, page traversal stops at `totalPages`, non-200 responses raise `PcsoSourceError`, and malformed results are rejected.

- [ ] **Step 2: Run the client tests and verify failure**

Run: `python -m pytest tests/test_pcso.py -v`  
Expected: FAIL because `lotto_signal.pcso` does not exist.

- [ ] **Step 3: Implement the injected HTTP client and normalizers**

Use exact endpoints `/get-results` and `/get-game-history`; set finite connect/read timeouts and an identifying open-source user agent; retry only transient `429` and `5xx` responses with bounded backoff.

- [ ] **Step 4: Run the client tests**

Run: `python -m pytest tests/test_pcso.py -v`  
Expected: PASS, including the malformed, stale-schema, and history-identifier cases.

- [ ] **Step 5: Commit**

```bash
git add src/lotto_signal/pcso.py tests/fixtures/pcso tests/test_pcso.py
git commit -m "feat: collect official PCSO results"
```

### Task 3: Append-only repository state and derived SQLite cache

**Files:**
- Create: `src/lotto_signal/store.py`
- Create: `data/draws/.gitkeep`
- Create: `data/revisions/.gitkeep`
- Create: `data/predictions/.gitkeep`
- Create: `state/.gitkeep`
- Create: `alerts/.gitkeep`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `DrawRecord`, `DrawRevision`, `Prediction`, `MonitorEvent`
- Produces: `RepositoryStore(root: Path)`
- Produces: `RepositoryStore.merge_draws(records: Iterable[DrawRecord]) -> MergeResult`
- Produces: `RepositoryStore.load_draws(game_code: str, before: datetime | None = None) -> tuple[DrawRecord, ...]`
- Produces: `RepositoryStore.append_prediction(prediction: Prediction) -> bool`
- Produces: `RepositoryStore.write_event(event: MonitorEvent) -> bool`
- Produces: `RepositoryStore.build_sqlite(path: Path) -> None`

- [ ] **Step 1: Write failing persistence tests**

Assert chronological canonical JSON Lines, idempotent duplicate merges, append-only corrections, immutable prediction conflicts, atomic writes, one event per event ID, `before` cutoff filtering, and equivalent derived SQLite rows.

- [ ] **Step 2: Run the store tests and verify failure**

Run: `python -m pytest tests/test_store.py -v`  
Expected: FAIL because `lotto_signal.store` does not exist.

- [ ] **Step 3: Implement `RepositoryStore`**

Write through a same-directory temporary file followed by `Path.replace`; retain the first official observation, append revisions separately, and expose corrected current values only through a deterministic projection.

- [ ] **Step 4: Run store tests**

Run: `python -m pytest tests/test_store.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lotto_signal/store.py data state alerts tests/test_store.py
git commit -m "feat: persist auditable lotto history"
```

### Task 4: Leakage-safe features and deterministic candidate methods

**Files:**
- Create: `src/lotto_signal/features.py`
- Create: `src/lotto_signal/methods.py`
- Test: `tests/test_features.py`
- Test: `tests/test_methods.py`

**Interfaces:**
- Consumes: `GameSpec`, `DrawRecord`
- Produces: `FeatureSnapshot(game_code: str, as_of: datetime, draw_count: int, values: Mapping[str, object])`
- Produces: `compute_features(draws: Sequence[DrawRecord], game: GameSpec, as_of: datetime) -> FeatureSnapshot`
- Produces: `Candidate(game_code: str, method_version: str, numbers: tuple[int, ...], raw_score: float, signal_score: float, seed: int)`
- Produces: `CandidateMethod` protocol with `generate(snapshot: FeatureSnapshot, game: GameSpec, seed: int) -> Candidate`
- Produces: frozen methods `frequency_v1`, `gap_v1`, `pair_v1`, `balanced_v1`, `ensemble_v1`, and `uniform_random_v1`.

- [ ] **Step 1: Write failing feature tests**

Assert exact 30/90/365-window counts, gap calculations, pair support, composition, sums, spreads, consecutive counts, preceding-draw overlap, insufficient-support omission, and complete exclusion of records at or after `as_of`.

- [ ] **Step 2: Run feature tests and verify failure**

Run: `python -m pytest tests/test_features.py -v`  
Expected: FAIL because `lotto_signal.features` does not exist.

- [ ] **Step 3: Implement `compute_features`**

Keep feature names and JSON shapes stable because predictions persist their feature snapshot.

- [ ] **Step 4: Run feature tests**

Run: `python -m pytest tests/test_features.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing method tests**

Assert six unique in-range numbers, reproducibility from seed, method-version stability, deterministic tie breaking, score calculation against 10,000 seeded uniform combinations, and a future-draw mutation leaving earlier candidates unchanged.

- [ ] **Step 6: Run method tests and verify failure**

Run: `python -m pytest tests/test_methods.py -v`  
Expected: FAIL because `lotto_signal.methods` does not exist.

- [ ] **Step 7: Implement the six frozen version-1 methods**

Use stable SHA-256-derived integer seeds from game, target draw date, method version, and source cutoff; never use process-randomized `hash()`.

- [ ] **Step 8: Run feature and method tests**

Run: `python -m pytest tests/test_features.py tests/test_methods.py -v`  
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/lotto_signal/features.py src/lotto_signal/methods.py tests/test_features.py tests/test_methods.py
git commit -m "feat: generate deterministic lotto candidates"
```

### Task 5: Walk-forward backtest and strict evidence gate

**Files:**
- Create: `src/lotto_signal/backtest.py`
- Create: `src/lotto_signal/gate.py`
- Test: `tests/test_backtest.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `CandidateMethod`, `DrawRecord`, `FeatureSnapshot`
- Produces: `BacktestConfig(min_predictions=200, min_alert_predictions=30, random_strategies=10_000, alert_percentile=0.85, family_alpha=0.01)`
- Produces: `walk_forward(game: GameSpec, draws: Sequence[DrawRecord], methods: Sequence[CandidateMethod], config: BacktestConfig) -> BacktestResult`
- Produces: `holm_bonferroni(p_values: Mapping[str, float], alpha: float) -> Mapping[str, bool]`
- Produces: `evaluate_gate(result: BacktestResult, current: Candidate, unresolved_data: bool) -> GateDecision`

- [ ] **Step 1: Write failing walk-forward tests**

Assert strictly prior inputs, equal one-line budgets, exact match scoring, stable seeded random baselines, repeatable results, and unchanged earlier outcomes after altering a future draw.

- [ ] **Step 2: Run backtest tests and verify failure**

Run: `python -m pytest tests/test_backtest.py -v`  
Expected: FAIL because `lotto_signal.backtest` does not exist.

- [ ] **Step 3: Implement walk-forward evaluation**

Return per-method predictions, matched-ball counts, alert-eligible rows, randomization p-values, effect sizes, and chronological halves; avoid retaining 10,000 full prediction histories when aggregate counters suffice.

- [ ] **Step 4: Run backtest tests**

Run: `python -m pytest tests/test_backtest.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing gate tests**

Cover each independent gate condition, Holm-Bonferroni across 25 hypotheses, both-half positivity, 50% recent-effect retention, unresolved corrections, the frozen 85th-percentile threshold, and a synthetic fully passing case.

- [ ] **Step 6: Run gate tests and verify failure**

Run: `python -m pytest tests/test_gate.py -v`  
Expected: FAIL because `lotto_signal.gate` does not exist.

- [ ] **Step 7: Implement correction and gate evaluation**

Secondary metrics remain descriptive and cannot activate a decision.

- [ ] **Step 8: Run the statistical tests twice**

Run: `python -m pytest tests/test_backtest.py tests/test_gate.py -v && python -m pytest tests/test_backtest.py tests/test_gate.py -v`  
Expected: both runs PASS with identical recorded digests.

- [ ] **Step 9: Commit**

```bash
git add src/lotto_signal/backtest.py src/lotto_signal/gate.py tests/test_backtest.py tests/test_gate.py
git commit -m "feat: enforce strict lotto evidence gate"
```

### Task 6: Idempotent morning, evening, backfill, and audit workflows

**Files:**
- Create: `src/lotto_signal/workflow.py`
- Create: `src/lotto_signal/cli.py`
- Create: `tests/test_workflow.py`
- Create: `config/runtime.json`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `PcsoClient`, `RepositoryStore`, `walk_forward`, `evaluate_gate`
- Produces: console entry point `lotto-signal`
- Produces: `run_backfill(context: RunContext) -> RunReport`
- Produces: `run_evening(context: RunContext) -> RunReport`
- Produces: `run_morning(context: RunContext) -> RunReport`
- Produces: `run_audit(context: RunContext) -> RunReport`
- Produces: `inspect_events(root: Path, after_event_id: str | None) -> tuple[MonitorEvent, ...]`

- [ ] **Step 1: Write failing workflow tests**

Cover ordinary silent runs, first failure silence, repeated failure event, stale source event, corrected-draw recomputation, scheduled-game selection, prediction immutability, no-signal event suppression, synthetic signal output, Monday audit, duplicate invocation idempotency, and shadow mode suppressing production research-signal events while retaining auditable decisions.

- [ ] **Step 2: Run workflow tests and verify failure**

Run: `python -m pytest tests/test_workflow.py -v`  
Expected: FAIL because `lotto_signal.workflow` does not exist.

- [ ] **Step 3: Implement orchestration and CLI commands**

Expose `backfill`, `evening`, `morning`, `audit`, and `inspect-events --after EVENT_ID`; every mutating command writes `state/last_run.json` with run ID, start, finish, source freshness, mode, status, and content digest. Read `config/runtime.json` with production research-signal notifications disabled by default and a recorded shadow-mode start date.

- [ ] **Step 4: Run workflow and full tests**

Run: `python -m pytest -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml config/runtime.json src/lotto_signal/workflow.py src/lotto_signal/cli.py tests/test_workflow.py
git commit -m "feat: orchestrate scheduled lotto monitoring"
```

### Task 7: GitHub Actions cloud runner and safe state commits

**Files:**
- Create: `.github/workflows/lotto-monitor.yml`
- Create: `scripts/commit-state.sh`
- Create: `tests/test_workflow_config.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `lotto-signal evening`, `lotto-signal morning`, `lotto-signal audit`
- Produces: manual input `mode` with values `morning`, `evening`, `audit`, `backfill`
- Produces: schedules `17 22 * * *` and `17 7 * * *` in `Asia/Manila`

- [ ] **Step 1: Write failing workflow-configuration tests**

Parse the YAML and assert public-runner compatibility, Python 3.12, `contents: write`, no other write permission, timezone-aware schedules, concurrency cancellation disabled, test-before-run ordering, manual dispatch modes, and no secret references.

- [ ] **Step 2: Run the configuration test and verify failure**

Run: `python -m pytest tests/test_workflow_config.py -v`  
Expected: FAIL because the workflow does not exist.

- [ ] **Step 3: Implement the workflow and guarded commit script**

The script stages only `data/`, `state/`, and `alerts/`; exits successfully on no changes; pulls with rebase before push; retries a rejected non-fast-forward push once; and never stages arbitrary untracked files.

- [ ] **Step 4: Run configuration and shell-syntax checks**

Run: `python -m pytest tests/test_workflow_config.py -v && bash -n scripts/commit-state.sh`  
Expected: PASS and no shell diagnostics.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/lotto-monitor.yml scripts/commit-state.sh tests/test_workflow_config.py README.md
git commit -m "ci: run lotto monitor in GitHub Actions"
```

### Task 8: Codex event monitor and operator documentation

**Files:**
- Create: `codex/monitor-prompt.md`
- Create: `docs/operations.md`
- Create: `tests/test_monitor_contract.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: public `alerts/latest.json` and `state/last_run.json`
- Produces: a self-contained Codex schedule prompt that stores the last delivered event ID in its existing-session context.

- [ ] **Step 1: Write the failing monitor-contract tests**

Assert the prompt names the repository paths, `Asia/Manila`, Luna-low preference, unchanged-state silence, stale-run threshold, one-notification-per-event behavior, shadow-mode suppression, evidence fields, unchanged-odds disclaimer, and prohibition on email/SMS/third-party notifications.

- [ ] **Step 2: Run the monitor-contract tests and verify failure**

Run: `python -m pytest tests/test_monitor_contract.py -v`  
Expected: FAIL because the prompt and operations guide do not exist.

- [ ] **Step 3: Write the Codex prompt and operations runbook**

Document manual runs, schedule delays, 60-day inactivity behavior, source-schema incidents, correction handling, cost ceiling, pausing, resuming, and the fact that the current Codex tool surface may require the user to paste the prepared prompt into Scheduled once.

- [ ] **Step 4: Run contract and full tests**

Run: `python -m pytest tests/test_monitor_contract.py -v && python -m pytest -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codex/monitor-prompt.md docs/operations.md tests/test_monitor_contract.py README.md
git commit -m "docs: define silent Codex notifications"
```

### Task 9: Live backfill, reproducibility check, and public release

**Files:**
- Modify: `data/draws/*.jsonl`
- Modify: `state/last_run.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: all prior commands and tests.
- Produces: public repository `edmacabebe/pcso-lotto-signal-monitor` unless the authenticated GitHub owner differs and the user selects another owner.

- [ ] **Step 1: Authenticate GitHub without exposing credentials**

Run: `gh auth login -h github.com -p https -w`  
Expected: browser authentication succeeds and `gh auth status` reports an active account.

- [ ] **Step 2: Run the live official-source backfill**

Run: `lotto-signal backfill`  
Expected: each game has at least 200 validated official draws, all content digests are recorded, and no production signal is emitted during backfill.

- [ ] **Step 3: Verify deterministic replay**

Run the audit twice from clean derived caches and compare digests.  
Expected: identical prediction, backtest, and gate digests.

- [ ] **Step 4: Run final local verification**

Run: `python -m pytest -v`  
Expected: PASS with no skipped leakage, gate, workflow, or configuration tests.

- [ ] **Step 5: Commit the validated initial dataset**

```bash
git add data state README.md
git commit -m "data: seed official PCSO history"
```

- [ ] **Step 6: Create and push the public repository**

Run: `gh repo create pcso-lotto-signal-monitor --public --source . --remote origin --push --description "Auditable PCSO lotto pattern research with strict random-baseline backtesting"`  
Expected: the repository is public, defaults to `main`, displays the MIT license and disclaimer, and contains no secrets.

- [ ] **Step 7: Trigger and verify one manual cloud run**

Run: `gh workflow run lotto-monitor.yml -f mode=morning` followed by `gh run watch --exit-status`.  
Expected: tests pass, the workflow completes, state changes are committed only when needed, and no routine user notification is sent.

- [ ] **Step 8: Configure the Codex cloud monitor**

Use `codex/monitor-prompt.md` in an existing-session scheduled task after the public URL is known.  
Expected: a dry check of unchanged state stays silent; a fixture action-required event produces exactly one Codex notification; shadow research signals remain suppressed; no external notification channel is used.

- [ ] **Step 9: Complete the live collection and shadow gates**

Keep production research-signal notifications disabled for seven days of live collection and at least two additional weeks of shadow evaluation. Review missing draws, corrections, schedule reliability, false alarms, deterministic digests, and measured cost; enable production signals in `config/runtime.json` only when every acceptance criterion in the spec passes.

- [ ] **Step 10: Tag the initial release**

```bash
git tag -a v0.1.0 -m "Initial research monitor release"
git push origin v0.1.0
```

Expected: public release tag points to the fully verified commit.

