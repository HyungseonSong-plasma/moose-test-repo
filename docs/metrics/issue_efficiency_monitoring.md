# Issue Efficiency Monitoring

**Status:** baseline + ongoing monitoring record  
**Created:** 2026-08-26  
**Scope:** executed MOOSE/QPX technical issues with usable issue-local Validator metrics  
**Canonical metric definitions:** `docs/protocols/metrics_closure.md`

## Inclusion rule

Include technical issues that have actual execution history and a usable metric block. Exclude:
- governance/cancelled placeholders explicitly marked as excluded from engineering metrics;
- PLANNED issues with `WCC=0`;
- issues whose body explicitly states that current metrics are non-canonical pending reconciliation;
- `DECOMPOSED_PARENT` issues from technically-completed efficiency comparisons unless decomposition efficiency is the analysis target.

## Baseline snapshot — 2026-08-26

Historical baseline sample: **#1, #2, #8, #13**.

| Issue | Complexity | State | WCC | T-WCC | RVR | EVR | DBR | RWR | CLR | FBR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| #1 Reactor-scale O2+ charged-heavy integration | C3 | CLOSED | 9 | 7 | n/a | 5 | 1 | 3 | 0 | yes |
| #2 Electron bulk drift integration | C3 | PAUSED | 7 | 7 | 2 reconstructed | 5 | 2 | 1 | 0 | no |
| #8 Charged heavy-species mixture diffusion + Poisson coupling | C4 | CLOSED — DECOMPOSED_PARENT | 8 | 8 | 0 | 7 | 1 | 3 | 0 | yes |
| #13 Oxygen heavy-species transport database | C3 | ACTIVE | 15 | 13 | 3 reconstructed | 10 | 2 | 6 | 0 | yes |

### Baseline aggregate statistics

- Sample size: `n=4`
- Total WCC: `39`
- Total T-WCC: `35`
- Technical-round share: `35/39 = 89.74%`
- Mean WCC: `9.75`
- Mean T-WCC: `8.75`
- Mean EVR: `6.75`
- Mean DBR: `1.50`
- Mean RWR: `3.25`
- FBR: `3/4 = 75%`
- CLR: `0` for all sampled issues
- Every sampled issue exceeded the nominal `EVR <= 3` target.

Baseline Pearson correlations over the four-issue sample:
- `corr(WCC, EVR) = 0.893`
- `corr(EVR, RWR) = 0.907`
- `corr(WCC, RWR) = 0.956`

These are descriptive only. With `n=4`, they are not sufficient for causal or inferential claims.

## Post-review snapshot — 2026-08-27

#20 is the first bounded closure package executed after the #14 process review and protocol hardening.

| Issue | Complexity | State | WCC | T-WCC | RVR | EVR | DBR | RWR | CLR | FBR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| #20 Canonical regression promotion + closure accounting | C2 | CLOSED | 4 | 4 | 0 | 2 | 0 | 0 | 0 | yes |

Execution history:
- EVR #1 reached P2 and failed with `ADFParser::JITCompile() failed`; user later confirmed the required conda environment had not been activated.
- The unchanged bundle was rerun after `conda activate` and returned `REGRESSION TOTAL: 9 PASS: 9 FAIL: 0`.
- The first failure is classified `ENVIRONMENT_OR_BUILD_FAIL`, not assistant-side harness rework, so `RWR=0`.
- #20 met the prospective target `EVR <= 3`, `DBR <= 2`, `RWR = 0`.

The post-review sample is still too small for comparative inference, but #20 is directionally consistent with the intended improvement: a bounded C2 closure package completed in two external result returns with no assistant-caused rework. The remaining process lesson is to make environment activation/JIT readiness an explicit P1/P2 preflight so that environment-only failures do not consume EVR.

## Historical #14 reconciliation note

#14 is a `DECOMPOSED_PARENT` and remains excluded from technically-completed efficiency comparison. Its downstream closure review reconstructed `EVR=10` and `RWR=4` from explicit historical execution/rework evidence; that high-cost history motivated the added batch, live-accounting, stop/re-audit, observation-path, discrete-identity, temporal-self-test, and environment-preflight rules.

## #13 closure note

#13 keeps its previously recorded issue-local metrics (`WCC=15`, `T-WCC=13`, `RVR=3 reconstructed`, `EVR=10`, `DBR=2`, `RWR=6`, `CLR=0`, `FBR=yes`). Its final R6 downstream gate is satisfied by #20's promoted 9/9 canonical regression; no #20 execution rounds are copied into #13 metrics under issue-local accounting.

## Monitoring hypotheses

Track these prospectively as new issues acquire canonical final metrics:

1. Does lower `RWR` predict lower `EVR` and `WCC`?
2. Do bounded C1-C3 successor issues outperform broad/decomposed C4 issues on `EVR`, `DBR`, and `RWR`?
3. Does targeted RVR investment associate with reduced downstream `EVR/DBR/RWR`?
4. Does FBR improve after stronger pre-mortem, mutation, known-good batching, and environment preflight?
5. Do post-#20 issues approach the project targets `EVR <= 3`, `DBR <= 2`, `RWR = 0` while preserving closure-quality gates?

## Update policy

Append a dated snapshot only when a technical issue obtains new usable/canonical metrics or when an existing metric is materially reconciled. Do not count PLANNED `WCC=0` issues as zero-cost observations. Preserve prior snapshots so trend analysis can distinguish historical process behavior from later improvements.