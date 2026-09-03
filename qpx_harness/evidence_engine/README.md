# QPX numerical evidence engine

Reusable Polars + DuckDB diagnostic engine for face/cell numerical evidence.

The engine is intentionally separated from QPX execution. Local validation does
not require a QPX executable or a MOOSE build.

## Local setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install 'pytest>=8,<9' -r requirements-evidence-engine.txt
```

The repository CI also installs these dependencies and runs the same Python test
suite.

## One-command local smoke test

```bash
python -m qpx_harness.evidence_engine.local_smoke
```

Expected compact output:

```text
EVIDENCE_ENGINE_LOCAL_SMOKE: PASS
  symmetry_axis=Y radial_coordinate=X radial_component=0
  baseline=CONSTANT_STATE_PASS perturbed_owner=SURFACE_VECTOR_CONSTRUCTION
```

This test exercises the full stack without QPX:

```text
synthetic exact RZ face telemetry
  -> schema normalization
  -> Polars face reconstruction
  -> Polars cell Green-Gauss reconstruction
  -> Parquet evidence
  -> DuckDB materialization/query
  -> registry-driven diagnosis

synthetic surface-vector perturbation
  -> same pipeline
  -> SURFACE_VECTOR_CONSTRUCTION
```

The analytical RZ contract used by the smoke test is:

```text
symmetry / axial axis = Y
radial coordinate     = X
radial component      = 0
```

## Architecture

The extensibility boundary is split into independent contracts:

```text
external telemetry
  -> Core schema                # stable identity/topology/spatial roles only
  -> Diagnostic schema plugin   # Green-Gauss, flux, Jacobian, transport, ...
  -> Polars transforms          # derived evidence columns
  -> DiagnosisRuleRegistry      # metric aggregation + ordered owner rules
  -> DiagnosisReport
```

Schema normalization and diagnosis policy are deliberately independent. A new
telemetry quantity does not automatically become a diagnosis rule, and a new
rule does not require hard-coding a new `if/elif` branch in `diagnose.py`.

## Core schema versus diagnostic plugins

`CoreColumnRole` is intentionally small. It contains only roles that are stable
across numerical diagnostics:

```text
run_id, case_id

elem_id, face_id

cell_x, cell_y
face_x, face_y
```

It does **not** contain Green-Gauss/RZ quantities such as normals, face area,
coordinate factors, surface vectors, scalar field values, volumes, radial
coordinates, or runtime gradients. Those quantities live in the
`GREEN_GAUSS_FACE_CONTRACT` plugin.

`ColumnRole` remains as a backward-compatible import alias for `CoreColumnRole`,
but it is no longer a registry of every quantity the engine may ever diagnose.

The built-in contracts are:

```python
from qpx_harness.evidence_engine import (
    CORE_FACE_CONTRACT,
    GREEN_GAUSS_FACE_CONTRACT,
)
```

`DEFAULT_FACE_CONTRACT` currently aliases `GREEN_GAUSS_FACE_CONTRACT` for
existing callers.

## Solver-agnostic Green-Gauss canonical names

The Green-Gauss plugin normalizes application-specific telemetry into generic
numerical roles before transforms run.

Canonical plugin quantities include:

```text
normal_x, normal_y
face_area
coord_factor
runtime_surface_x, runtime_surface_y
field_cell, field_face
cell_volume
radial_coordinate
runtime_grad_x, runtime_grad_y
```

Existing MOOSE/QPX names remain accepted as aliases. For example:

```text
moose_surface_x  -> runtime_surface_x
moose_surface_y  -> runtime_surface_y
n_cell           -> field_cell
n_face           -> field_face
qpx_grad_x       -> runtime_grad_x
qpx_grad_y       -> runtime_grad_y
```

This keeps source provenance in the input contract while preventing the
canonical evidence model from being tied to one application or one diagnosed
field. The same Green-Gauss transform can therefore diagnose electron density,
pressure, temperature, or another scalar field as long as the probe maps its
cell/face values to `field_cell` and `field_face`.

## Dynamic schema contracts

External probes do not have to emit exact canonical names. Each
`DynamicSchemaContract` resolves a conservative set of aliases into its canonical
namespace before Polars transformations run.

For example, `cell_id`, `x_C`, `x_f`, `nx`, `S_x`, `V_rz`, and `grad_x` can be
normalized to `elem_id`, `cell_x`, `face_x`, `normal_x`, `runtime_surface_x`,
`cell_volume`, and `runtime_grad_x` respectively by the Green-Gauss plugin.

The resolver does **not** silently choose when both a canonical name and one of
its aliases are present. Multiple matching sources for one physical role are a
contract error because their values may disagree.

New diagnostic quantities can be added without editing an enum or the transform
core:

```python
from qpx_harness.evidence_engine import GREEN_GAUSS_FACE_CONTRACT, ColumnSpec

contract = GREEN_GAUSS_FACE_CONTRACT.extend({
    "electron_temperature": ColumnSpec(
        canonical="electron_temperature",
        aliases=("Te_eV", "mean_energy_eV"),
        required=False,
    ),
    "electron_diffusivity": ColumnSpec(
        canonical="electron_diffusivity",
        aliases=("D_e",),
        required=False,
    ),
})
```

Then pass the contract directly to the transform path:

```python
from qpx_harness.evidence_engine import prepare_face_evidence, build_cell_evidence

face = prepare_face_evidence(raw, schema_contract=contract)
cell = build_cell_evidence(raw, radial_component=0, schema_contract=contract)
```

Extra columns are preserved by default. This is intentional: future diagnosis
layers can consume newly added parameters without changing the existing
Green-Gauss reconstruction code. `normalize_and_project(...,
preserve_extra_columns=False)` is available when a canonical-only projection is
required.

The built-in aliases are intentionally conservative. Very generic source names
such as `density`, `area`, or `volume` should be added only in a probe-specific
contract where their physical meaning is unambiguous.

## Dynamic diagnosis registry

`diagnose.py` does not own a hard-coded `if/elif` cascade. Diagnosis is driven by
two declarative objects:

- `DiagnosticMetricSpec`: which source frame/column supplies a scalar evidence
  metric, its report key, and optional face/cell localization metadata;
- `DiagnosisRule`: threshold, owner class, status, decision label, and priority.

`DiagnosisRuleRegistry` validates that metric ids, report keys, rule ids, and
priorities are deterministic. `evaluate_diagnosis_registry()` computes all
registered absolute-max metrics and applies the first triggered rule in priority
order.

The canonical Green-Gauss behavior is a factory:

```python
from qpx_harness.evidence_engine import build_constant_state_registry

registry = build_constant_state_registry()
```

The built-in registry consumes solver-agnostic evidence columns such as
`field_face_delta` and `runtime_grad_norm`. The existing
`summarize_constant_state()` API uses this registry internally, so campaign
callers keep the same dictionary interface.

### Add a new spatial diagnostic

Suppose a transform or telemetry importer provides a cell column named
`electron_diffusivity_error`. No change to `diagnose.py` is required:

```python
from qpx_harness.evidence_engine import (
    DiagnosticMetricSpec,
    DiagnosisRule,
    build_constant_state_registry,
    evaluate_diagnosis_registry,
)

registry = build_constant_state_registry().extend(
    metrics={
        "electron_diffusivity_error": DiagnosticMetricSpec(
            metric_id="electron_diffusivity_error",
            source="cell",
            column="electron_diffusivity_error",
            report_key="max_electron_diffusivity_error",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        )
    },
    rules=(
        DiagnosisRule(
            rule_id="electron_diffusivity_consistency",
            metric_id="electron_diffusivity_error",
            threshold=1.0e-4,
            owner_class="ELECTRON_DIFFUSIVITY_CONSISTENCY",
            status="ISOLATED_OWNER_CLASS",
            decision_label="electron diffusivity consistency",
            priority=5,
        ),
    ),
)

report = evaluate_diagnosis_registry(
    {"face": face, "cell": cell},
    registry,
)
```

Lower numeric priority executes earlier. This allows a probe-specific owner rule
to be inserted before or after the built-in Green-Gauss decision layers without
editing the evaluator.

### Add a non-spatial diagnostic source

The source key is not restricted to `face` or `cell`. For example, a Jacobian
campaign can supply a separate frame:

```python
metric = DiagnosticMetricSpec(
    metric_id="jacobian_relative_error",
    source="jacobian",
    column="relative_error",
    report_key="max_jacobian_relative_error",
)
```

With `entity_kind=None`, the owner decision is still produced but no artificial
cell location is fabricated. This is useful for run-level, matrix-level, or
campaign-level diagnostics.

At present registered metrics use absolute maximum aggregation. More complex
statistics should be derived upstream into an evidence column, then registered.
This keeps the decision engine deterministic and prevents hidden numerical logic
inside owner classification.

## Preserve artifacts for inspection

```bash
rm -rf local_evidence_smoke
python -m qpx_harness.evidence_engine.local_smoke \
  --output local_evidence_smoke
```

Artifacts:

```text
local_evidence_smoke/
  summary.json
  evidence.duckdb
  baseline/
    face_evidence.parquet
    cell_evidence.parquet
  perturbed/
    face_evidence.parquet
    cell_evidence.parquet
```

Print the complete machine-readable result:

```bash
python -m qpx_harness.evidence_engine.local_smoke --json
```

## Run the focused regression tests

```bash
python -m pytest -q tests/characterization/test_evidence_engine.py
```

The focused tests verify:

- exact constant-state RZ cancellation;
- core-role confinement to identity/topology/spatial coordinates;
- Green-Gauss plugin separation from the core contract;
- solver-specific aliases normalized into generic canonical quantities;
- extension with a new schema quantity without transform changes;
- rejection of duplicate canonical/alias sources;
- registry extension with a new electron-diffusivity owner rule;
- arbitrary non-spatial source frames such as Jacobian evidence;
- deterministic rule validation and priority ordering;
- separation of runtime-truth surface vectors from independently reconstructed
  `normal * face_area * coord_factor` values;
- surface-vector fault routing before any RZ-specific attribution;
- Parquet persistence;
- DuckDB queries;
- the full local smoke runner and preserved artifacts.

## Inspect the local DuckDB database from Python

After running with `--output`:

```bash
python - <<'PY'
from qpx_harness.evidence_engine import EvidenceStore

with EvidenceStore('local_evidence_smoke/evidence.duckdb') as store:
    print(store.query('SELECT * FROM perturbed_cell_evidence'))
    print(store.worst_cells(
        table='perturbed_cell_evidence',
        metric='gradient_delta_norm',
        limit=10,
    ))
PY
```

## Runtime integration contract

A real MOOSE/QPX runtime probe may emit source-specific names or already-canonical
names. The Green-Gauss plugin ultimately requires these canonical physical roles:

```text
run_id, case_id, elem_id, face_id
cell_x, cell_y
face_x, face_y
normal_x, normal_y
face_area, coord_factor
runtime_surface_x, runtime_surface_y
field_cell, field_face
cell_volume, radial_coordinate
runtime_grad_x, runtime_grad_y
```

MOOSE-emitted values remain runtime truth, but they are normalized into generic
canonical roles before analysis. Independently reconstructed values stay in
separate columns and never overwrite runtime truth.
