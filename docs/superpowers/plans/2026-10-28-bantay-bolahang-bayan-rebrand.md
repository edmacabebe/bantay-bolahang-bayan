# Bantay Bolahang Bayan Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the public project and GitHub repository as Bantay Bolahang Bayan without changing runtime, statistical, or audit behavior.

**Architecture:** Update only public identity surfaces and canonical repository URLs while retaining `lotto_signal`, `lotto-signal`, stored record identifiers, and audit-family identifiers. Rename the GitHub repository only after the local change is tested and pushed, then verify redirects, raw-state URLs, workflow execution, and the existing release.

**Tech Stack:** Python 3.12, pytest, Git, GitHub CLI, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-10-28-bantay-bolahang-bayan-rebrand-design.md`

## Global Constraints

- The canonical repository is `edmacabebe/bantay-bolahang-bayan`.
- Preserve the Python package `lotto_signal` and CLI command `lotto-signal`.
- Preserve all data formats, audit family IDs, predictions, events, and Git history.
- Keep the research purpose and no-guarantee disclaimer explicit.
- Keep `config/runtime.json` production research signals disabled.

## Review Focus

- A stale old raw-content URL in the Codex prompt must not break notifications; assert all three URLs use the new slug.
- Package metadata must change without breaking the `lotto-signal` entry point; install and run the full tests.
- The collector must identify the new canonical project without implying PCSO affiliation; assert its user-agent name and URL.
- The GitHub rename must preserve `main`, Actions schedules, tags, releases, and old-URL redirects; verify each after the rename.
- No statistical identifier or committed evidence file may change; inspect the diff and audit digests before publishing.

---

### Task 1: Rebrand local identity surfaces

**Files:**
- Create: `tests/test_branding.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `src/lotto_signal/pcso.py`
- Modify: `tests/test_pcso.py`
- Modify: `codex/monitor-prompt.md`
- Modify: `tests/test_monitor_contract.py`
- Modify: `.github/workflows/lotto-monitor.yml`
- Modify: `docs/operations.md`
- Modify: `docs/superpowers/specs/2026-10-28-pcso-lotto-signal-monitor-design.md`
- Modify: `docs/superpowers/plans/2026-10-28-pcso-lotto-signal-monitor.md`
- Add: `docs/superpowers/specs/2026-10-28-bantay-bolahang-bayan-rebrand-design.md`
- Add: `docs/superpowers/plans/2026-10-28-bantay-bolahang-bayan-rebrand.md`

**Interfaces:**
- Consumes: Existing package metadata, monitor prompt, GitHub workflow, and collector constants.
- Produces: Public brand `Bantay Bolahang Bayan`, distribution name `bantay-bolahang-bayan`, canonical URL `https://github.com/edmacabebe/bantay-bolahang-bayan`, unchanged `lotto-signal` command.

- [ ] **Step 1: Write the failing branding contract**

Create `tests/test_branding.py` to assert the README title, `pyproject.toml` project name, unchanged CLI entry point, new collector user-agent, new GitHub workflow display name, and absence of `edmacabebe/pcso-lotto-signal-monitor` from active text surfaces. Extend the monitor-contract test to assert all raw URLs contain `edmacabebe/bantay-bolahang-bayan`.

- [ ] **Step 2: Run the branding tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_branding.py tests/test_monitor_contract.py tests/test_pcso.py`

Expected: FAIL because current identity surfaces still use the old name and URL.

- [ ] **Step 3: Update identity surfaces**

Use `Bantay Bolahang Bayan` for human-facing titles, `bantay-bolahang-bayan` for distribution/user-agent identity, and the new GitHub URL everywhere. Keep descriptions explicit about PCSO-results statistical research and keep imports, commands, evidence, and runtime configuration unchanged.

- [ ] **Step 4: Verify local behavior and evidence preservation**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m compileall -q src tests && git diff --check`

Expected: all tests pass; compilation and diff checks are silent. Confirm the three audit digests in `state/audit.json` and `production_research_signals: false` are unchanged.

- [ ] **Step 5: Commit and push the local rebrand**

```bash
git add README.md pyproject.toml src/lotto_signal/pcso.py tests/test_pcso.py tests/test_branding.py codex/monitor-prompt.md tests/test_monitor_contract.py .github/workflows/lotto-monitor.yml docs/operations.md docs/superpowers/specs docs/superpowers/plans
git commit -m "chore: rebrand as Bantay Bolahang Bayan"
git push origin main
```

### Task 2: Rename and verify the public repository

**Files:**
- Modify: GitHub repository metadata, local `origin`, and existing `v0.1.0` release presentation.

**Interfaces:**
- Consumes: Tested and pushed Task 1 commit on `main`.
- Produces: Public repository `edmacabebe/bantay-bolahang-bayan` with preserved workflow, release, tag, redirects, and cloud state.

- [ ] **Step 1: Rename the GitHub repository and update metadata**

Rename `edmacabebe/pcso-lotto-signal-monitor` to `edmacabebe/bantay-bolahang-bayan`, set a transparent research description, and retitle the existing release without changing its tag or target commit.

- [ ] **Step 2: Update and verify the local remote**

Set `origin` to `https://github.com/edmacabebe/bantay-bolahang-bayan.git`, fetch it, and assert `origin/main` matches local `main`.

- [ ] **Step 3: Verify public compatibility surfaces**

Verify the new repository is public and MIT-licensed; the old repository URL redirects; the three new raw-state URLs resolve; `v0.1.0` still exists; and the scheduled workflow retains both Manila-time schedules.

- [ ] **Step 4: Run and inspect a cloud smoke test**

Dispatch the renamed workflow in `morning` mode, wait for completion, and require a successful conclusion. Confirm it runs the full tests and safely writes zero predictions when the official source is stale.

- [ ] **Step 5: Synchronize and perform final verification**

Fast-forward any auditable cloud-state commit, then run `.venv/bin/python -m pytest -q`, `git diff --check`, and `git status --short`. Confirm production signals remain disabled and report the new repository and release URLs.
