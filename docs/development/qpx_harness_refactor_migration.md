# QPX Harness Refactor Migration — Issues #116–#118 / #126

This document records the implementation disposition following the current-main census in `qpx_harness_current_main_census.md`.

## Registry drift discovered during census

The #116–#118 issue bodies were written against four registered operator-facing R3/R4 protocols. Current main now registers eight declarative protocols because Issue #26 and #27 experiment families have since entered the gateway.

The refactor therefore applies ownership rules to all eight registered protocols rather than silently treating the older four-protocol list as complete.

## #116 — reusable execution mechanics

Promoted reusable mechanics:

- `qpx_harness.execution.runtime.resolve_results_root` owns the mechanical default results-root convention relative to the resolved QPX executable.
- `qpx_harness.application.execution_options` owns composition of ExperimentSpec-relative execution configuration with Execution mechanics.
- Registered protocol adapters use the shared option parser where their semantics match.

Deliberately retained in protocols/experiment runners:

- case ordering and case matrices,
- wall-model dispatch,
- scientific gates and thresholds,
- P2/P3 scientific sequencing,
- Jacobian acceptance/diagnosis,
- scientific evidence interpretation.

No universal scientific runner was introduced.

## #117 — Evidence / Analysis compatibility retirement

The old `qpx_harness.evidence` Green-Gauss convenience facades were retired:

- `prepare_face_evidence`
- `build_cell_evidence`
- `write_evidence_bundle`

Canonical ownership is now explicit:

```text
Evidence.normalize_face_evidence
        ↓
Analysis.derive_face_quantities / derive_cell_quantities
        ↓
Application.green_gauss_workflow (cross-layer composition when needed)
        ↓
Diagnose
```

The local smoke and characterization tests were migrated to the downstream Application composition. The Evidence-to-Analysis dependency-guard exception was removed.

## #118 — current-main RunEnvelope

A current-main reference-only provenance model now exists under `qpx_harness.provenance`.

`RunEnvelope` records:

- stable run ID,
- experiment/protocol identity,
- source revision when available,
- executable identity,
- input identity,
- categorized references to execution/evidence/analysis/diagnosis/protocol artifacts.

It does not embed subsystem payloads.

R4-QF2 is the first current declarative workflow to emit `run_envelope.json`. This is intentional incremental adoption. Remaining registered workflows may adopt the same API when they are next touched; no historical workflow was promoted solely for provenance uniformity.

## #126 — integration disposition

The tutorial mental model remains traceable as:

```text
qpx -e experiment.json
    ↓
ExperimentSpec parse/validation
    ↓
protocol registry
    ↓
protocol adapter
    ↓
Execution / Evidence / Analysis / Diagnose owners
    ↓
RunEnvelope references
```

`qpx -i` remains repository/harness internal validation. `qpx -e` remains declarative scientific execution. Legacy commands remain compatibility surfaces rather than architectural owners.

## Validation policy

This migration changes architecture and provenance mechanics, not accepted scientific formulas, thresholds, inputs, or scientific acceptance semantics. QPX-free architecture/regression validation is therefore the primary closure gate. Scientific P3 should only be requested if validation demonstrates that a scientific acceptance surface was semantically changed.
