# Issue #493 P3 — timeout diagnosis and main-reconciled recovery

## Ground truth (2026-11-10; Repository CI run #1471)

GitHub Actions run `42817563443` on original PR #498
(`2537465328e0cc9f1d240cc89e1f29899650628a`) executed
**both** S6-417 and S6-941 lanes. Each lane successfully completed public
P0 validation, historical 400 W mesh preparation, fresh P1 native PhysicsApp
build, P1 identity recording and **B/old-template P2 native `--check-input`**.

Both **B full native P3 solves timed out at 8,100 seconds**. Neither arm
produced a proven, complete 461-frame 0–100 µs result within the budget,
and the fail-closed B→C execution rule correctly prevented C from running.
This is an **execution budget failure (P3=HOLD)**, not verified scientific
instability, solver divergence, or wrong input. Raw full solver logs were
intentionally not uploaded, so the last step and iteration progress
of run #1471 **cannot be reconstructed** from its sanitized artifact.

Additional historical report defects:
- `exit_code=127` on timeout was the script's uninitialized sentinel,
  **not a Docker or solver exit code**.
- Aggregate `P2=HOLD` meant C had not been attempted; **B/P2 was PASS**.
  The v2 status now records both per-arm and aggregate truth.

## Main-base reconciliation

This remediation branch starts from **main**
`b1467fe9de797869f8bc43629bb532a96018d741`, after the merge of
Physics option-first Continuity changes and former PR #491. Original
PR #498 was based on much older `99858c47aa261f6325e08e01f022a6dc4f391d57`
and its workflow diverged, so the code is reintroduced from the current
main rather than blindly merging its old `ci.yml` job.

**Do not silently substitute a new physics executable.** The S6 research
candidate remains pinned to reviewed exact SHA
`bebaf47a33ff5ee1d6b933d9691bf48f5ec0f947` and pinned historical
source `29d1acc6ef7969908b86719e4b95c73a1565136d`. This is the
same candidate tested in #1471; it is **not** validation of the newer
main's Continuity changes. A new-HEAD native/science evaluation requires
a separately approved provenance and P1/P2 restart.

## Safeguards introduced

- `p3_diagnostics.py` monitors actual native job stdout on the host and
  emits **only bounded numerical telemetry** (reported MOOSE step/time,
  elapsed wall time, CPU and memory samples). An unrecognized log format
  remains `null`: no synthetic progress or fabricated convergence data.
  Raw solver logs, Exodus and CSV remain in restricted ephemeral space.
- Timeout now reports `exit_code: null`, `termination: TIMEOUT` and the
  actual budget. All failed P3 runs remain HOLD/FAIL and stop before C.
  Aggregate P2/P3 includes explicit passed/not-run arms.
- `--mode diagnostic` runs **B only** with the unchanged full-460-step
  input and a **1–900 second** sampling budget (default 600); it
  **never establishes P3 PASS** and does not start C. An intentional
  diagnostic budget expiry is not misclassified as native solve failure.
- `--mode full --authorize-full-p3` is an explicit second gate for
  real B→C 460-step computations. Each arm retains the 8,100-second
  maximum until progress evidence justifies a budget adjustment. No
  automatic repeated 2.25-hour run was added to ordinary CI.
- P0/P1 identity/P2 --check-input, exact OCI, rate hashes, source pins,
  research energy domain, binary rehashes and SCIENCE_HOLD are unchanged.

## Controlled next diagnostic

On a reviewed, trusted host with the exact prepared historical checkout,
candidate built by the existing Native P1 harness, P1 identity JSON and
public rates/decks, run one lane at a time (for example 417 first):

```bash
python3 experiments/Issue493_s6_boltzmann/public_p3_run.py \
  --mode diagnostic --case 417 --timeout-seconds 600 \
  --control /prepared/control --historical /prepared/historical \
  --candidate /prepared/pinned-candidate \
  --p1-evidence /restricted/issue493-p1-provenance.json \
  --output /restricted/new-diagnostic-attempt-417
```

Inspect the emitted `PUBLIC_P3_HEARTBEAT` numeric records and the
`non_sensitive_p3_status.json` for progress/time/memory. With no
observed step, report **progress UNKNOWN** and inspect raw native logs
*only inside the restricted host* to distinguish startup deadlock,
nonlinear convergence, table-domain or I/O issues. Do not infer
timestep numbers from wall time alone.

Only after this evidence can a separately reviewed execution decide
whether to improve resources, fix an actual solver issue, or change
timeout settings. No reduction of 460 steps, no table extrapolation,
no private rate files, and no science acceptance. P4 remains NOT_RUN,
SCIENCE_HOLD.
