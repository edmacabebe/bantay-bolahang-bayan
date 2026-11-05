# Evidence-First Daily Reporting Design

## Intent

Restore dependable daily operation after the official LottoMatik proxy endpoint changed, and turn each completed prediction into a timestamped, auditable score report. The reports should help evaluate the selection method without implying that recent matches change jackpot odds or justify spending.

## Goals

- Collect from the current official LottoMatik backend while preserving strict schema validation.
- Generate scheduled historical-data guesses from the latest verified local history when morning collection fails, with production signals suppressed.
- Timestamp every Codex report in Asia/Manila.
- Score every completed line as `n/6`, list the exact matches, missed predicted numbers, and winning numbers not selected.
- Include method provenance, source cutoff, rolling 7-day, 30-day, and lifetime performance, score distributions, and a game-aware random-match benchmark.
- Backfill delayed official results and corrected results into scorecards and outcome history.
- Keep algorithm changes behind the existing weekly walk-forward audit and a minimum completed-line sample; never adapt from a single draw.

## Non-goals and anti-goals

- Do not claim higher winning probability, recommend a stake, buy a ticket, or call a number overlap a prize.
- Do not weaken validation, silently accept secondary-source results, or overwrite official history.
- Do not automatically tune method weights from daily outcomes.
- Do not emit repeated notifications for unchanged scorecard content.

## Constraints

- Python 3.12, existing `httpx` dependency, repository JSON/JSONL state, and public GitHub Actions remain the runtime.
- All five configured six-number games remain monitored; predictions are produced only for games scheduled on the target date.
- Official data remains authoritative. Historical fallback may create experimental guesses but cannot enable production research signals.
- Metrics must be deterministic and content-addressable. Report timestamps come from the event's timezone-aware `created_at`, not from a volatile field inside the scorecard payload.

## Approaches considered

### Evidence-first reporting — selected

Repair the official endpoint, retain strict collection and correction handling, add source-error historical fallback, and publish detailed deterministic scorecards with rolling random-baseline comparisons. This gives useful evaluation evidence while resisting daily overfitting.

### Score-only reporting

Publish only `n/6` and exact matches. This is simpler but does not provide enough provenance or longer-window evidence to guide method review.

### Daily adaptive tuning

Reweight the method after every draw. This reacts quickly but would chase noise in an extremely sparse random process, so it is explicitly rejected.

## Design

`PcsoClient` will use the official backend host currently referenced by the LottoMatik site. Morning source failures will continue through the existing prediction path using stored verified draws, produce a distinct historical-fallback status, suppress production signals, and retain the actionable source incident.

A focused reporting module will calculate completed prediction/draw pairs and deterministic performance windows. Each completed scorecard entry will contain prediction provenance, `n/6`, matching numbers, missed predicted numbers, winning numbers not selected, match rate, and the expected number overlap for one random line in that game. Pending entries will use `null` for result-dependent metrics, never zero.

Each scorecard will include rolling 7-day, 30-day, and lifetime summaries: completed lines, total and average matches, total predicted balls, match rate, game-weighted random expectation, difference from that expectation, and the full 0/6 through 6/6 distribution. A tuning guardrail will state the minimum sample and that method changes remain manual and audit-gated.

The Codex monitor will begin every notification with `Report timestamp: <Asia/Manila time>` using the event timestamp. Completed scorecard messages will show the detailed entry metrics and rolling summary. The report will explicitly distinguish number overlap from prizes and probabilities.

## Acceptance criteria

- The current official backend passes the existing normalization tests for latest and history response shapes.
- A morning transport/HTTP failure still creates immutable guesses for that day's scheduled games from cached verified history and records a source-error historical-fallback heartbeat.
- Pending scorecards never report zero matches.
- Completed scorecards show exact `n/6`, matched, missed, and unselected winning numbers plus provenance and benchmark fields.
- Seven-day, 30-day, and lifetime metrics are deterministic, revision-aware, and tested at empty and mixed-game boundaries.
- Backfill and audit score newly completed predictions and refresh affected scorecards.
- Every Codex report includes a PHT timestamp.
- The full test suite and a live cloud backfill/morning smoke run pass before release.
