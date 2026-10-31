# Central CI error database — Oxygen24 (2026-10-31)

This directory is the **single curated, version-controlled error knowledge base** for the observed MOOSE Oxygen24 work to date, including 400 W / 1000 W and the 2 ns → 4 ns checkpoint/restart development. It is **separate from the scientific reference baseline** and is **not merged to main**.

## Files

- [`catalog.json`](catalog.json): **canonical persistent database source**. Each underlying incident has a stable `OXY-ERR-NNN` ID and one root-cause/status record. Each failed CI job has a separate occurrence linked by `incident_id`, `run_id`, `job_id`, exact commit SHA, step, diagnostic excerpt and log URL.
- [`ci_errors.py`](ci_errors.py): standard-library SQLite materializer, integrity checks and incremental GitHub Actions ingestion.
- `ci_errors.sqlite` **generated artifact**, not the versioned source. The file can be downloaded from the DB-build Actions run or generated locally.

## Generate and query

From the repository checkout:

```bash
python3 ops/ci_error_db/ci_errors.py stats
python3 ops/ci_error_db/ci_errors.py build --output /tmp/moose_oxygen24_ci_errors.sqlite

python3 - <<'PY'
import sqlite3
with sqlite3.connect('/tmp/moose_oxygen24_ci_errors.sqlite') as db:
    for row in db.execute('SELECT id, title, status, occurrences FROM incident_overview ORDER BY id'):
        print(row)
    for row in db.execute('SELECT run_id, power_w, step, evidence_excerpt FROM occurrences WHERE incident_id=?', ('OXY-ERR-004',)):
        print(row)
PY
```

There are **two linked tables**: `incidents` (deduplicated root causes) and `occurrences` (actual failed jobs). The `incident_overview` SQL view includes number of occurrences, unique affected runs and first/last observation time.

## Incremental collection of new CI errors

Use a GitHub token with read-only Actions access, **never place the token in the catalog**:

```bash
export GITHUB_TOKEN=...  # CI read-only Actions token, injected securely
python3 ops/ci_error_db/ci_errors.py ingest --run-id 41193613390
# or scan the 25 most recent finished failed runs (default):
python3 ops/ci_error_db/ci_errors.py ingest --recent 25
python3 ops/ci_error_db/ci_errors.py build --output /tmp/moose_oxygen24_ci_errors.sqlite
```

Ingestion is idempotent at `job_id` level, skips unfinished/successful jobs, creates a new `unclassified` incident for unknown signatures, and saves only sanitized small diagnostic snippets, never complete raw logs. **New entries require human triage** before root causes or fixed status can be claimed. A successful short smoke does not validate 100 µs chemistry.

## Status meanings

- `verified_fixed`: later CI passed **the relevant failure stage**; it does **not** mean the entire simulation succeeded.
- `fix_pending_verification`: a fix commit exists; a genuine passing continuation is still needed.
- `open`: no confirmed repair; includes the 100 µs wall-time budget failure.
- `unverified`: insufficient evidence to claim the issue was resolved.

`confidence=observed_only` explicitly means only the symptom was confirmed.

## Collection boundary

The seeded version covers **13 distinct incidents and 24 observed failed jobs** from specified 2026-10-30/31 Oxygen24/restart workflows. It is **not** a claim that all historical errors in the repository have been collected. The GitHub repository has thousands of Actions runs; an explicit broader ingest would be a separate scope.

The most recent restart experiment, [run #41193613390](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41193613390), was still running when the first snapshot was seeded and **must not be marked as failing or passing before terminal evidence**.

## Safety and privacy

Store IDs, normalized excerpts and link references only; do not commit private collision/rate tables, private tokens, full environment dumps or unredacted multi-megabyte raw logs. For detailed diagnosis, follow each occurrence's run/job URL and inspect GitHub's original log.
