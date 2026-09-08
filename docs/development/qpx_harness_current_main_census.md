# QPX Harness Current-Main Architecture Census

Issue: #126
Branch: `issue-126-qpx-harness-refactor`
Baseline: current `main` at branch creation, after #120

## Purpose

This census is the Phase-0 prerequisite for the QPX Harness refactor plan. It identifies the current declarative experiment flow, assigns semantic ownership, and records where #116, #117, and #118 should operate without creating overlapping abstractions.

The tutorial model is used only as a traceability check:

```text
qpx -e <experiment.json>
    -> declaration
    -> validation
    -> protocol selection
    -> protocol execution
    -> evidence / analysis / diagnosis
    -> result / provenance
```

It is not authority to move responsibilities across existing semantic boundaries.

---

## 1. Canonical user-facing entrypoints

Current CLI ownership is in `qpx_harness/cli/app.py`.

The two canonical gateways are:

```text
python qpx -i <internal-target>
python qpx -e <experiment.json>
```

Ownership classification:

| Surface | Owner | Meaning |
|---|---|---|
| `-i`, `--internal` | CLI / Validation routing | repository and harness internal validation |
| `-e`, `--experiment` | CLI -> Application | declarative scientific experiment gateway |
| legacy positional commands | Compatibility | migration compatibility; not architecture-defining |

Current `-e` flow is already thin:

```text
CLI
  -> qpx_harness.application.run_experiment(path)
  -> load_experiment_spec(path)
  -> validate_experiment_spec(spec)
  -> resolve_protocol(spec.protocol)
  -> runner(spec)
```

This is the canonical high-level application path to preserve.

---

## 2. Experiment declaration ownership

`qpx_harness/application/experiment_spec.py` owns the generic declarative schema.

Current generic fields are:

```text
schema_version
experiment_id
protocol
execution
parameters
outputs
case_source
```

Ownership:

```text
ExperimentSpec parsing and structural validation = Application
Protocol-specific meaning of parameters/outputs = Protocol
Runtime/process interpretation of mechanical execution values = Execution when reusable
```

`ExperimentSpec` must remain protocol-neutral.

---

## 3. Protocol registry census

A baseline mismatch was found during Phase 0.

Issues #116-#118 describe four current registered operator-facing workflows:

```text
r3-electron-master-diagnostic
r3-electron-scaling-counterfactual
r3-fv-internal-completion
r4-qf2-local-charge-relaxation
```

The current registry now contains eight registered protocols:

```text
issue26-electron-energy-e1
issue26-electron-energy-e2a
issue26-electron-energy-chain
issue27-surface-reaction-controlled-wall
r3-electron-master-diagnostic
r3-electron-scaling-counterfactual
r3-fv-internal-completion
r4-qf2-local-charge-relaxation
```

Therefore #116-#118 must not assume that the four-protocol list is a complete current-main registry census.

For refactor purposes, the registry is the authoritative current code surface. The older four-protocol set remains an important historical baseline, but all eight registered protocols must be considered when deciding whether a mechanical concern is genuinely reusable.

---

## 4. Current ownership map

### CLI

Owns:

```text
argument routing
help text
canonical gateway selection
legacy compatibility dispatch
```

Must not own:

```text
scientific case selection
scientific thresholds
physics interpretation
protocol-specific result logic
```

### Application

Owns:

```text
ExperimentSpec loading
structural validation
protocol registration and resolution
generic orchestration from declaration to protocol runner
```

The current `experiment_service.py` is already small and should remain small.

### Protocol

Owns:

```text
scientific case ownership
protocol-specific parameter meaning
scientific sequencing
acceptance/stopping policy
protocol-specific runner selection
scientific interpretation
```

### Execution

Owns reusable mechanical behavior only:

```text
executable resolution and validation
QPX process invocation
timeout and return-code capture
workspace/run-root mechanics where semantics are genuinely common
mechanical log/result capture
```

This is #116 territory.

### Evidence

Owns:

```text
source-faithful parse
normalization
persistence
```

### Analysis

Owns:

```text
quantitative derivation
aggregation
numerical transforms derived from evidence
```

### Diagnose

Owns:

```text
threshold application
classification
interpretation
```

Evidence/Analysis compatibility retirement is #117 territory.

### Provenance

Target ownership:

```text
stable run identity
protocol identity
source revision
executable identity
input identity
categorized artifact references
```

This is #118 territory. The provenance envelope should reference artifacts rather than embed their payload schemas.

---

## 5. Confirmed duplication candidates for #116

The protocol adapters show repeated mechanical configuration patterns.

### Candidate A — default results root resolution

Repeated pattern in:

```text
r3-electron-scaling-counterfactual
r4-qf2-local-charge-relaxation
issue26-electron-energy-e1
issue26-electron-energy-e2a
issue27-surface-reaction-controlled-wall
```

Common logic:

```text
if execution.results_root configured:
    resolve relative to experiment spec
else:
    resolve executable
    use <qpx-parent>/temp/results
```

This is a strong #116 candidate because it is mechanical and already depends on `qpx_harness.execution.runtime.resolve_executable`.

Before consolidation, the remaining registered protocols must be checked for equivalent semantics.

### Candidate B — timeout parsing/validation

Repeated adapter behavior:

```text
float(execution.get("timeout_seconds", default))
require timeout > 0
```

The defaults vary by protocol, so only parsing/validation is a likely reusable primitive. The scientific/default policy should remain with the protocol unless a current-main census proves the default itself is mechanical and uniform.

### Candidate C — optional path resolution

`r3-electron-master-diagnostic` and `r3-fv-internal-completion` both duplicate `_optional_path(...)` for execution-owned paths such as `results_root` and `error_ledger`.

This may belong in Application or Execution depending on whether the helper remains purely `ExperimentSpec` path interpretation or becomes runtime/workspace policy.

Do not create a general helper until all live consumers are classified.

### Candidate D — low-level QPX invocation

The R3 master diagnostic already uses:

```text
resolve_executable
validate_executable
run_qpx
```

for P2, P3, and Jacobian probes.

This confirms that reusable mechanical invocation already has an Execution owner. #116 should prefer extending these existing owners rather than introducing a universal experiment lifecycle.

---

## 6. Protocol behavior that must not be generalized into Execution

Examples observed in current protocol/application surfaces:

```text
R3 master diagnostic owns its predeclared diagnostic matrix.
R3 scaling counterfactual owns its bounded N0/N1/N2 matrix.
R3 FV internal completion owns its canonical case matrix.
R4 QF2 owns its canonical QF2 case.
Issue #26 protocols own their electron-energy control cases.
Issue #27 selects controlled wall scientific behavior from wall_model.
```

These are protocol/scientific responsibilities.

Especially for Issue #27, `wall_model` selects among multiple scientifically distinct wall-control runners. This dispatch must remain protocol-owned rather than being flattened into generic Execution.

---

## 7. #117 census requirement

No #117 implementation change should be made from this document alone.

Required next census:

```text
prepare_face_evidence
build_cell_evidence
write_evidence_bundle
```

Search every current-main caller/reference and classify each as:

```text
Application
Analysis
Validation
Protocol
Compatibility/Historical
Documentation-only
```

Only after active callers are migrated may the compatibility facade and dependency-guard exception be removed.

---

## 8. #118 census requirement

Current protocols still use protocol-specific run identity/artifact layouts.

For example, R3 master diagnostic creates a collision-safe run directory and writes an `identity.json` containing experiment/run/executable identity plus protocol-specific fields.

This is evidence that stable provenance information exists but is currently protocol-owned and schema-specific.

#118 should census each registered current protocol for:

```text
run_id source
experiment/protocol identity
source revision
executable path/hash
input identity
execution artifact refs
evidence artifact refs
analysis artifact refs
diagnosis artifact refs
protocol-owned artifact refs
```

The future canonical RunEnvelope should reference these artifacts without re-owning their payloads.

---

## 9. Updated implementation sequence

Because the actual registry has moved beyond the four-protocol baseline, the safe sequence is:

```text
Phase 0 — #126
Complete registry/ownership census across all 8 current registered protocols.

Phase 1 — #116
Consolidate only mechanical duplication proven equivalent by the census.

Phase 2 — #117
Migrate live Evidence compatibility consumers and retire facades.

Phase 3 — #118
Introduce/adapt stable current-main provenance and migrate active protocols incrementally.

Phase 4 — #126
Perform only remaining thin CLI/Application integration cleanup.

Phase 5 — #126
Verify that the tutorial mental model is traceable through the implementation.
```

#117 can proceed independently where its caller census shows no dependency on #116.

---

## 10. Phase-0 status

Completed in this first pass:

```text
[PASS] canonical CLI entrypoint ownership identified
[PASS] ExperimentSpec/Application ownership identified
[PASS] registry inspected
[PASS] baseline drift detected: 4 documented -> 8 registered
[PASS] initial #116 duplication candidates identified
[PASS] protocol-vs-Execution boundary reaffirmed
[PASS] #117 and #118 census requirements recorded
```

Still required before Phase 0 is closed:

```text
[ ] inspect remaining Issue #26 chain adapter in detail
[ ] inspect all eight protocol runner implementations for duplicated mechanics
[ ] complete Evidence compatibility caller census for #117 handoff
[ ] complete per-protocol provenance/artifact census for #118 handoff
[ ] classify each registered protocol as active operator-facing, bounded development, or compatibility/history
[ ] update #116-#118 baselines if the current-main classification proves their four-protocol assumption stale
```

No production code should be refactored under #126 until this census is complete enough to prevent duplicate ownership.
