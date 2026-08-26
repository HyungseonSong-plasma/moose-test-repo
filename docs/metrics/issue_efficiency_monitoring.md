# Issue Efficiency Monitoring

**Status:** baseline + ongoing monitoring record  
**Created:** 2026-08-26  
**Scope:** executed MOOSE/QPX technical issues with usable issue-local Validator metrics  
**Canonical metric definitions:** `docs/protocols/metrics_closure.md`

## Inclusion rule

Include technical issues that have actual execution history and a usable metric block. Exclude:
- governance/cancelled placeholders explicitly marked as excluded from engineering metrics;
- PLANNED issues with `WCC=0`;
- issues whose body explicitly states that current metrics are non-canonical pending reconciliation.

Current baseline sample: **#1, #2, #8, #13**.

#14 is excluded from the baseline because its closed body states that the prior synthetic `EVR=1 / RWR=0` block is not canonical final accounting and that #20 owns reconciliation.

## Baseline snapshot — 2026-08-26

| Issue | Complexity | State | WCC | T-WCC | RVR | EVR | DBR | RWR | CLR | FBR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| #1 Reactor-scale O2+ charged-heavy integration | C3 | CLOSED | 9 | 7 | n/a | 5 | 1 | 3 | 0 | yes |
| #2 Electron bulk drift integration | C3 | PAUSED | 7 | 7 | 2 reconstructed | 5 | 2 | 1 | 0 | no |
| #8 Charged heavy-species mixture diffusion + Poisson coupling | C4 | CLOSED — DECOMPOSED_PARENT | 8 | 8 | 0 | 7 | 1 | 3 | 0 | yes |
| #13 Oxygen heavy-species transport database | C3 | ACTIVE | 15 | 13 | 3 reconstructed | 10 | 2 | 6 | 0 | yes |

### Aggregate statistics

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

### Exploratory relationships

Pearson correlations over the four-issue sample:

- `corr(WCC, EVR) = 0.893`
- `corr(EVR, RWR) = 0.907`
- `corr(WCC, RWR) = 0.956`

These are descriptive only. With `n=4`, they are not sufficient for causal or inferential claims.

## Two-paragraph baseline report

Across the four technical issues with usable execution metrics (#1, #2, #8, #13), the average work item consumed 9.75 WCC, 8.75 T-WCC, 6.75 EVR, 1.50 DBR, and 3.25 RWR. About 89.7% of all recorded interaction rounds were technical rather than governance/clarification rounds, FBR was achieved in three of four issues, and CLR remained zero. The dominant efficiency problem is therefore not clarification overhead but repeated external execution: every sampled issue exceeded the nominal three-EVR target. #13 is currently the highest-cost observation at WCC=15, EVR=10, and RWR=6.

The strongest exploratory signal is that rework and external validation cost move together: WCC-EVR, EVR-RWR, and WCC-RWR correlations are approximately 0.89, 0.91, and 0.96 respectively. The sample is too small to establish causality, but the pattern is consistent with harness/checker/configuration defects amplifying both user-local reruns and total interaction cost. The operational hypothesis to monitor prospectively is therefore that stronger P0 mutation/self-tests, known-good controls, earlier decomposition of broad C4 work, and `RWR -> 0` will reduce downstream EVR and WCC without weakening closure quality. RVR effectiveness should not yet be inferred because the available RVR values are incomplete/reconstructed.

## Monitoring hypotheses

Track these prospectively as new issues acquire canonical final metrics:

1. Does lower `RWR` predict lower `EVR` and `WCC`?
2. Do bounded C1-C3 successor issues outperform broad/decomposed C4 issues on `EVR`, `DBR`, and `RWR`?
3. Does targeted RVR investment associate with reduced downstream `EVR/DBR/RWR`?
4. Does FBR improve after stronger pre-mortem, mutation, and known-good batching?
5. Do post-#20 issues approach the project targets `EVR <= 3`, `DBR <= 2`, `RWR = 0` while preserving closure-quality gates?

## Update policy

Append a dated snapshot only when a technical issue obtains new usable/canonical metrics or when an existing metric is materially reconciled. Do not count PLANNED `WCC=0` issues as zero-cost observations. Preserve prior snapshots so trend analysis can distinguish historical process behavior from later improvements.
