# Issue53 staged validation queue

**Work ID:** `qpx-stats-builder-decomposition`  
**Issue:** #53  
**Protocol:** `docs/protocols/coding.md` / CODE-13  
**Status:** ACTIVE / D1 PASS / D2 PASS / D3 PASS / D4+D5 OWNERS STAGED / LOCAL OWNER DIAGNOSTIC READY

## Local execution contract

Local workspaces are disposable ZIP snapshots of the GitHub canonical repository.
Local commands are diagnostics only.

```text
NO local git commands
NO local cp/rm/mv commands
NO local source mutation commands
```

Repository mutations are performed against GitHub canonical state separately.
Local evidence is used only to validate the current downloaded snapshot.

## Accepted decomposition progression

```text
baseline stats_builder.py: 942 LOC
embedded self_test:         198 LOC

D1 Efficiency extraction:  836 LOC / PASS
D2 Convergence extraction: 653 LOC / PASS
D3 Accuracy extraction:    432 LOC / PASS
```

D3 user-local evidence:

```text
ISSUE53_STRUCTURAL_GUARD_D3: PASS
ISSUE53_STRUCTURAL_GUARD_LOC: 432
QPX_ACCURACY_STATS_MAPPING_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_STATS_MAPPING_SELFTEST: PASS
ISSUE45_FIRST_LINEAR_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_STATS_MAPPING_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS
ISSUE46_JAC_LOCALIZATION_RUNTIME_SELFTEST: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
ISSUE53_DECOMPOSITION_INVENTORY: PASS
ISSUE53_STATS_BUILDER_LOC: 432
ISSUE53_STATS_BUILDER_SELFTEST_LOC: 198
ISSUE53_DECOMPOSITION_STAGE: D3_ACCURACY_EXTRACTED
```

Canonical D3 commit:

```text
aba07b9d01b2d7887a085fd7c7268d00e10ca118
refactor(issue53): extract AccuracyStats owner
```

## D4 — Common/Environment owner staging

Additive owner:

```text
qpx_harness/analysis/common.py
```

Commit:

```text
ba7a0e09364f20c4fa5af37e7295b4d89a84f4d8
refactor(issue53): stage CommonStats analysis owner
```

The staged owner owns:

```text
build_problem_stats
build_environment_stats
_runtime_return_code
build_common_stats
build_runtime_common_stats
```

Shared coercion remains owned by `qpx_harness/analysis/_coerce.py`.
`stats_builder.py` still contains the current Common implementation until the staged owner passes local diagnostics.

## D5 — embedded self-test owner staging

Additive characterization owner:

```text
qpx_harness/analysis/stats_builder_characterization.py
```

Commit:

```text
cc8f50422285bc672bd99e417b26ebd1882769d0
test(issue53): stage stats_builder characterization owner
```

The characterization owner preserves the existing marker:

```text
QPX_STATS_BUILDER_SELFTEST
```

It imports `stats_builder` public facade symbols lazily inside `self_test()` so a later facade re-export does not create a module-import cycle.

## D4/D5 structural guards

Commit:

```text
34d8271c20aba87cedca4fee23f878fff44925b4
test(issue53): extend structural guard through Common and self-test cuts
```

The gates are intentionally sequential:

```text
D4 -> Common implementation absent locally + Common public symbols re-exported
      composition builders and embedded self_test must still remain

D5 -> Common remains external + embedded self_test absent
      self_test re-exported from stats_builder_characterization
      composition builders remain local
```

Do not combine D4 and D5 into one destructive cut.

## Current local owner diagnostic gate

Run on a freshly downloaded GitHub ZIP snapshot. Diagnostics only:

```bash
python3 -m py_compile qpx_harness/analysis/common.py
python3 -m qpx_harness.analysis.common
python3 -m qpx_harness.analysis.stats_builder_characterization
python3 -m qpx_harness.analysis.stats_builder
python3 scripts/qpx.py self-test
python3 tests/Issue53_stats_builder_decomposition/inventory.py
```

Required evidence:

```text
QPX_COMMON_STATS_MAPPING_SELFTEST: PASS
QPX_STATS_BUILDER_SELFTEST: PASS
QPX_HARNESS_SELFTEST: PASS
ISSUE53_DECOMPOSITION_INVENTORY: PASS
ISSUE53_STATS_BUILDER_LOC: 432
ISSUE53_DECOMPOSITION_STAGE: D3_ACCURACY_EXTRACTED
```

If the staged owners pass, proceed autonomously:

```text
D4 Common extraction on GitHub canonical
 -> D4 structural read-back
 -> local diagnostics only

then, only after D4 PASS:

D5 embedded self_test extraction on GitHub canonical
 -> D5 structural read-back
 -> local diagnostics only
```

## Remaining target

After D4 and D5:

```text
stats_builder.py = thin public composition facade
focused Common/Efficiency/Convergence/Accuracy owners
stable public builder and self-test symbols
```

Final Issue53 acceptance remains architecture-driven rather than an arbitrary line target. The original visible goal is approximately `120-200 LOC`; a smaller facade is acceptable when caused by clean ownership extraction rather than semantic compression.
