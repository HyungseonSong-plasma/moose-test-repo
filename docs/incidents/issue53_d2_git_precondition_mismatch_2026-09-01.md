# Issue53 D2 local Git precondition mismatch — 2026-09-01

**Status:** repaired / recorded  
**Affected work:** #53 `qpx-stats-builder-decomposition`  
**Affected harness:** `tests/Issue53_stats_builder_decomposition/apply_d2.py`

## Incident

The first D2 migrator preflight required the user's local checkout to report the repository branch `refactor/qpx-harness-generality` through Git and also inspected Git dirty-tree state.

The user does not use Git in the local execution environment. The migrator therefore returned:

```text
ISSUE53_D2_MIGRATOR: FAIL (wrong branch: expected 'refactor/qpx-harness-generality', got 'main')
ISSUE53_D2_DRYRUN_RC: 1
ISSUE53_D2_GATE: HOLD_DRYRUN
```

No D2 production mutation occurred because the check failed before apply.

## Root cause

**Execution-environment contract mismatch introduced by the migration harness.**

Repository branch identity is relevant to remote repository mutations performed through the GitHub connector, but it is not a valid mandatory precondition for this user's local QPX execution environment. The harness incorrectly coupled local structural migration safety to a Git workflow that the user does not use.

## Impact

- no production file was changed by the failed dry-run;
- D2 remained safely blocked;
- one avoidable user-local validation round was consumed;
- the failure was harness/environment-contract related, not a physics or Stats semantic failure.

## Repair

Commit:

```text
7f36b149c54f921c918defe5f1a557889bfea8e0
  fix(issue53): make D2 migrator git-independent
```

The D2 migrator now uses the accepted D1 structural fingerprint instead of Git state:

```text
stats_builder.py LOC == 836
Efficiency local implementation absent
Efficiency facade re-export present
all five Convergence local owner functions present
Convergence facade re-export absent
Common / Accuracy / composition functions present
Python AST parses successfully
```

Apply remains atomic through temporary-file parse, replace, post-check, and automatic rollback on failure.

## Learning classification

Primary MET-20 status: `ENVIRONMENT_ESCAPE`.

The structural migration logic was sound, but a Git-specific local-environment assumption incorrectly blocked the applicable execution environment.

Applicable pack: `IMPLEMENT / VALIDATE`  
Detection stage: user-local dry-run preflight  
EPR required: `no`  
Primary remediation decision: `HARDEN_ENVIRONMENT_IDENTITY` — local migration gates must depend only on environment capabilities that are actually part of the declared user-local execution contract.
