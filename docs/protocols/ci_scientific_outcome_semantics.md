# CI Scientific Outcome Semantics

**Status:** canonical procedure  
**Purpose:** prevent valid diagnostic experiments from appearing as broken CI merely because a scientific hypothesis was rejected.

## Core rule

CI process failure and scientific rejection are different axes.

```text
CI red  = trustworthy evidence was not produced.
CI green = trustworthy evidence was produced.
```

A converged, analyzable diagnostic that rejects a hypothesis is valid evidence and should normally exit zero.

## Evidence validity

`evidence_valid = false` and nonzero process exit are reserved for cases such as:

```text
HARNESS_OR_CONSTRUCTION_FAIL
VALIDATOR_SELFTEST_FAIL
ENVIRONMENT_OR_BUILD_FAIL
SOLVER_CONVERGENCE_FAIL
ANALYSIS_FAIL
missing/corrupt expected evidence
```

These mean the declared scientific experiment was not successfully observed.

## Scientific outcome

When evidence is valid, record the scientific conclusion separately, for example:

```text
REFERENCE_RESIDUAL_CONFIRMED
HYPOTHESIS_SUPPORTED_STRONG
HYPOTHESIS_SUPPORTED_PARTIAL
HYPOTHESIS_NOT_SUPPORTED
NEGATIVE_CONTROL_CONFIRMED
PHYSICS_MODEL_FAIL
BATCH_PASS
```

`PHYSICS_MODEL_FAIL` is a scientific decision class, not automatically a CI/process failure for diagnostic campaigns.

## Promotion exception

A production-promotion or release gate may intentionally require a specific scientific outcome. Such a gate must be a separate explicit promotion job. Do not overload the evidence-generation job exit code to represent both evidence validity and production acceptance.

## Required summary fields

New diagnostic runners should emit:

```json
{
  "ci_status": "PASS|FAIL",
  "evidence_valid": true,
  "scientific_outcome": "...",
  "scientific_gates": {},
  "status": "PASS"
}
```

On evidence-generation failure, use the canonical failure class in `status`, set `evidence_valid=false`, and return nonzero.

## Required self-tests

A runner adopting this policy must prove at P0 that:

```text
valid + hypothesis supported       -> exit 0
valid + hypothesis rejected        -> exit 0
valid + expected negative control  -> exit 0
invalid construction evidence      -> exit nonzero
invalid solver/runtime evidence    -> exit nonzero
```

When converting a recurring historical false-red pattern, include at least one archived valid scientific rejection as a regression input and prove it becomes CI-success without changing its scientific conclusion.
