# Issue #59 — Recipe Census and Compatibility Baseline

**Status:** implementation baseline prepared  
**Work ID:** `qpx-experiment-spec-recipe-census`  
**Parent capability:** #58 `Declarative Experiment Architecture v1`  
**Scientific/runtime state:** frozen; refactor EVR budget consumed = 0

## Purpose

Freeze the pre-migration recipe surface before ExperimentSpec v1 implementation begins.

This issue does **not** migrate production recipes. It records the exact production recipe identities, classifies every top-level symbol, and discovers current import/consumer dependencies so later JSON/spec extraction cannot silently drop compatibility obligations.

## Frozen production recipe set

| Recipe | Git blob SHA |
|---|---|
| `recipes/issue31_coupling.py` | `abf6679266c5f8d7cf53019743f44b6a78052f45` |
| `recipes/issue43_coupling_diagnostic.py` | `a57d2e1531b91f33ce7eb8a71a4e161193844dde` |
| `recipes/issue43_fast_relaxation.py` | `459a641a51358a030c81354decff585c48137c54` |
| `recipes/issue45_first_linear.py` | `0c787e4867cc4555ec7d6bfcb6a0b63768994ca3` |
| `recipes/issue45_inventory_constraint.py` | `f5b41b5f740ce78734c9c9410ba9b5c1c67a9751` |
| `recipes/issue46_fd_reference.py` | `96111bb968aa946e28565b412dfcd52b59d1ecaf` |
| `recipes/issue46_jacobian_localization.py` | `258955359c99b8ceeffe9d5d7320cea27ae37651` |

The executable census computes Git blob SHA locally and fails on any identity drift.

## Responsibility taxonomy

Every top-level recipe symbol is assigned exactly one primary responsibility:

```text
DATA
DECLARATIVE_TRANSFORM
ALGORITHM
RUNTIME
CHARACTERIZATION
```

The machine-readable records additionally carry:

```text
current symbol consumers
module importers
issue/case specificity
ExperimentSpec v1 readiness: YES | PARTIAL | NO
candidate target owner
compatibility requirement
scientific/runtime sensitivity
```

Unclassified top-level functions or unexpected classes are hard failures. New recipe files are also a hard failure until the census is deliberately revised.

## Architectural findings frozen by the census

### Issue43 coupling diagnostic

This is the #58 pilot because its function surface is purely declarative:

```text
_ensure_debug_block      -> DECLARATIVE_TRANSFORM / v1 YES
instrument_input         -> DECLARATIVE_TRANSFORM / v1 YES
```

Known consumer baseline includes `qpx_harness/issue43_coupling/structure.py`.

### Issue31 coupling

The recipe mixes three responsibilities:

```text
transport/input construction -> DECLARATIVE_TRANSFORM
runtime CSV selection        -> RUNTIME
physics / EVR classification -> ALGORITHM
```

Known module consumers include both Issue31 EVR1 and EVR2 runtime owners.

### Issue43 fast relaxation

The recipe contains substantial MOOSE construction plus runtime CSV loading and relaxation/classification algorithms. It is therefore not a candidate for blind JSON conversion; later readiness work must separate declarative construction from Python analysis/runtime responsibilities.

### Issue45 first-linear

`instrument_first_linear` is declarative and v1-ready. Jacobian interpretation, nonlinear/linear termination analysis, and the first-linear discriminator remain Python algorithms. The census records direct consumers in the Issue45 and Issue46 harnesses.

### Issue45 inventory constraint

The recipe combines constrained-input construction with structure audits and runtime-pair interpretation. The executable consumer scan determines whether any production owner still imports this historical recipe after the Issue45 owner decomposition; zero importers are reported as an **orphan candidate**, not automatically deleted.

### Issue46 Jacobian localization

The recipe's small function surface is declarative and v1-ready: PETSc diagnostic-option changes plus DOFMap output insertion. The current Issue46 localization/FD-reference runtime consumers are compatibility obligations.

### Issue46 FD reference

The recipe contains four distinct categories:

```text
historical/reference constants                    -> DATA
historical mechanism fixtures                     -> CHARACTERIZATION
PETSc/DOFMap/Jacobian/termination interpretation  -> ALGORITHM
diagnostic PETSc input mutations                  -> DECLARATIVE_TRANSFORM
```

Generic-capability candidates are explicitly identified for Jacobian analysis, nonlinear/termination facts, provenance, and localization. Issue-specific classification remains Python until a genuine reusable owner is proven.

## Machine-checkable artifacts

```text
tests/Issue59_recipe_census/inventory.py
tests/Issue59_recipe_census/final_guard.py
```

`inventory.py` derives the census from AST and scans current Python consumers under `qpx_harness/`, `scripts/`, and `tests/`.

`final_guard.py` requires:

```text
exact seven-recipe set
exact frozen Git blob identities
complete symbol classification
known consumer subset detection
Issue43 pilot declarative/v1 readiness
census negative self-tests
refactor EVR = 0
```

No QPX executable, P2, P3, or scientific EVR is required for this baseline issue.

## Validation

From the latest GitHub ZIP, repository root:

```bash
python3 tests/Issue59_recipe_census/final_guard.py
```

Expected terminal marker:

```text
ISSUE59_FINAL_GUARD: PASS
```

This is a diagnostics-only command and does not edit repository sources.

## Downstream release condition

Issue #60 may move from `BLOCKED` to `READY` only after the Issue59 final guard passes against the frozen recipe baseline and #59 is accepted/closed.
