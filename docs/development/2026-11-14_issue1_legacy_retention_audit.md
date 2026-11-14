# Issue #1 — retirement dependency and evidence-retention audit

**Decision:** `KEEP_ALL_ISSUE1_SOURCE_ASSETS / DELETE_HOLD`  
**Inspection scope:** read-only census of the Issue #1 experiment directory, its repository-local references, and the existing narrow dependency-decoupling branch.  
**Base main:** `f6c4072c34143e3fb42bc9841eeac92eb138b058` (2026-11-14).  
**Working branch before this record:** `66fc12365e189aaf82ab300265ddcb9d5aeeac6e`.  
**Physics P2/P3:** NOT_RUN. This is an asset/reference audit, **not** scientific compatibility acceptance.

## Important distinction

The current source-ownership pytest and the two historical H3/H5 scripts no longer read directly
from `experiments/Issue1_reactor_o2plus_integration/` on this branch:

- `tests/test_issue402_retired_charge_poisson_ownership.py` checks current source ownership rather than reading the historical `self_consistent_2d.i`.
- `.github/scripts/issue197_h3_migration_audit.py` now stages `tests/fixtures/issue1_legacy_consumers/issue197_h3/`.
- `.github/scripts/issue199_h5_known_charge.py` now stages `tests/fixtures/issue1_legacy_consumers/issue199_h5/`.

Both new fixture input blobs match the respective frozen historical input blobs exactly:
`9906040c450e28b3f1de8628c3936cf3ad1dec74` (#197) and
`5b20df8337828f74d40b122d2745310d46aa1b71` (#199).
New pytest guards test that identity and the path rewiring. This source-level proof does not
replace P2/P3 execution; the staging source path changes and archived `test.json` is not copied
into the standalone diagnostic fixture.

## Complete Issue #1 experiment census (14 Git blobs)

| Item | Files | Category | Current disposition |
| --- | ---: | --- | --- |
| `check_migration_state.py`, `check_reactor_o2plus.py` | 2 | Shared historical scientific checkers | **KEEP**; six manifests reference one of them via `../` |
| `correction_on/` | 2: `.i`, `test.json` | Conservation-positive canonical test | **KEEP** |
| `full_exact_phi_ic/` | 2: `.i`, `test.json` | M5/2D exact-potential historical control | **KEEP** |
| `full_zero_phi_ic/` | 2: `.i`, `test.json` | Zero-potential initialization/convergence control | **KEEP** |
| `self_consistent_2d/` | 2: `.i`, `test.json` | Fully coupled species/charge/Poisson/drift test | **KEEP** |
| `migration_only_exact_phi_ic/` | 2: `.i`, `test.json` | Migration-direction control; #197 **input-only** snapshot copied | **KEEP** until canonical-case disposition |
| `poisson_analytic/` | 2: `.i`, `test.json` | Analytic Poisson control; #199 **input-only** snapshot copied | **KEEP** until canonical-case disposition |

No tracked `*.csv`, `*.exo`, `*.log` or other generated output artifacts occur
inside the Issue #1 directory at this exact revision. There are no currently approved
**safe-to-delete** tracked files from this 14-file set.

## Dynamic discovery matters even without a literal path reference

All six `test.json` manifests declare `"type": "canonical"` and point to local
inputs and the two shared checkers. The Physics regression discovery code
`physics_harness/execution/workspace.py::discover_manifests` recursively discovers
`test.json` files under an operator-supplied test root; the corresponding
`physics_harness/adapters/moose/regression.py::cli_run_all` supports
`--tests-root`. Its default root is `tests/`, not `experiments/`, so these
historical cases are **not** automatically proven to be default-CI runtime cases.
However, explicitly targeted historical suite discovery would silently lose six
canonical entries if the directory were deleted.

Both checker files are live local assets of those six manifests, even though current
default pytest does not run Physics P3. Raw `QPX*` names are historical provenance;
the current Physics executable is not claimed to accept them without a checked bridge.

## Other retention / downstream contracts

- `docs/incidents/reactor_o2plus_integration_closure.md`: **KEEP** as issue closeout,
  tested numerical invariants, validation error history and residual-floor evidence.
- `docs/development/2026-11-12_issue402_ddmaterial_charge_flux_consumer_trace.md`:
  documentary reference to historical Issue #1 FV `FVCoupledForce` Poisson wiring;
  **keep reference or update intentionally** if the canonical experiment path changes.
- `archive/Issue35_workspace_migration/r35_m1_stage_report.json`: immutable path/lineage
  provenance; **KEEP** even if a future migration changes current paths.
- `physics_app/src/fvkernels/PhysicsFVElectrostaticDrift.C`,
  `PhysicsFVHeavyMassElectromigrationCorrection.C`, and
  `physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C`:
  currently registered Physics implementations; **not retirement candidates**.
- `#402` S6 scientific parity/production acceptance remains independent and on
  `SCIENCE_HOLD`. No Issue #1 static refactor can authorize a scientific cutover.

## Deletion gate (not yet satisfied)

1. Confirm all six historical `test.json` cases have an explicit **preserve/archive/retire**
   disposition, with checker and input provenance retained and reviewable.
2. Re-audit literal paths **and recursive `test.json` discovery** on exact target HEAD.
   Don't count the two standalone H3/H5 input snapshots as replacement for the complete
   canonical test suite.
3. Run the new fixture-integrity pytest, current Issue #402 static guard and relevant
   Repository CI. Track P0 separately from P2/P3.
4. If claiming that the current diagnostic or native scientific path is preserved,
   execute its owner-approved P2 and representative P3; require independent physical
   invariants rather than inferring success from matching bytes or passing pytest.
5. Only after these gates, propose a separate narrowly reviewed deletion with exact
   file identities. Do not combine this change with removal of Physics C++ owners.

**Current outcome:** two direct diagnostic path dependencies decoupled; six canonical
experiment manifests and two shared checkers retained; no deletion authorized.
