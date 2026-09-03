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

The evidence requirements include Polars, DuckDB, Pydantic v2, and `z3-solver`.
The repository CI installs the same dependencies and runs the same Python tests.

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
  -> metric registry
  -> Z3 logical owner selection

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
  -> Polars transforms          # derived numerical evidence columns
  -> DiagnosticMetricSpec       # evidence aggregation contract
  -> externally supplied Z3RuleSet
  -> Z3DiagnosisEngine          # symbolic logical selection
  -> DiagnosisReport
```

Schema normalization, numerical transformation, metric aggregation, and logical
owner policy are deliberately independent.

The diagnosis implementation is modular:

```text
qpx_harness/evidence_engine/diagnosis/
  __init__.py       # stable public facade and summarize_* compatibility API
  models.py         # Pydantic ontology and injectable Z3 rule-set models
  evaluator.py      # Polars metric aggregation + failure localization
  presets.py        # Green-Gauss metric/rule factories only
  z3_engine.py      # generic SMT rule interpreter
```

`qpx_harness/evidence_engine/diagnose.py` is now only a backward-compatible shim.
New implementation must not accumulate there.

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

Extra columns are preserved by default so future diagnosis layers can consume
new quantities without changing the existing Green-Gauss reconstruction code.

## Metric registry and Z3 logical policy

`DiagnosticMetricSpec` defines where a scalar diagnostic metric comes from and
how it is reported/localized. `DiagnosisRuleRegistry` remains supported for
simple one-metric threshold callers, but the evaluator converts those rules into
Z3 rules and uses `Z3DiagnosisEngine` for canonical owner selection.

The Z3 policy is independently injectable through:

- `MetricPredicate`: one scalar comparison (`gt`, `ge`, `lt`, `le`, `eq`, `ne`);
- `Z3OwnerRule`: `all_of`, `any_of`, and `none_of` logical clauses, owner/status,
  priority, and optional localization metric;
- `Z3RuleSet`: ordered externally supplied policy set.

Missing metric values are a contract error. The Z3 engine never uses
`metric_values.get(name, 0.0)`, because missing telemetry must not turn into a
false PASS.

The built-in Green-Gauss factories are:

```python
from qpx_harness.evidence_engine import (
    build_constant_state_registry,
    build_constant_state_ruleset,
)

registry = build_constant_state_registry()
ruleset = build_constant_state_ruleset()
```

### Inject a composite physics rule

Suppose the evidence frame contains `electron_diffusivity_error`. Add its metric
to the registry, then supply an external Z3 rule that requires both a diffusivity
error and clean surface-vector construction:

```python
from qpx_harness.evidence_engine import (
    DiagnosticMetricSpec,
    MetricPredicate,
    Z3OwnerRule,
    build_constant_state_registry,
    build_constant_state_ruleset,
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
    }
)

ruleset = build_constant_state_ruleset().extend((
    Z3OwnerRule(
        rule_id="diffusivity_with_clean_geometry",
        owner_class="ELECTRON_DIFFUSIVITY_CONSISTENCY",
        status="ISOLATED_OWNER_CLASS",
        decision_label="electron diffusivity with clean geometry",
        priority=5,
        all_of=(
            MetricPredicate(
                metric_id="electron_diffusivity_error",
                operator="gt",
                threshold=1.0e-4,
            ),
            MetricPredicate(
                metric_id="surface_vector_delta",
                operator="le",
                threshold=1.0e-14,
            ),
        ),
        location_metric_id="electron_diffusivity_error",
    ),
))

report = evaluate_diagnosis_registry(
    {"face": face, "cell": cell},
    registry,
    z3_ruleset=ruleset,
)
```

Lower numeric priority wins when multiple candidate rules are simultaneously
true. The SMT model explicitly represents candidate rules, selected rules, and
the PASS state, enforcing exactly one selected owner or PASS.

### Non-spatial diagnostics

Metric sources are not restricted to `face` or `cell`. A Jacobian campaign can
register a separate `jacobian` frame. With `entity_kind=None`, the logical owner
is still selected but no artificial spatial location is fabricated.

Registered metrics currently use absolute-maximum aggregation. More complex
statistics should be derived upstream into explicit evidence columns so the
logical policy remains declarative and inspectable.

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

The focused tests verify exact RZ cancellation, schema/plugin separation, alias
normalization, dynamic metric extension, Z3 priority, composite logical rules,
missing-evidence fail-closed behavior, spatial failure localization, non-spatial
Jacobian evidence, Parquet persistence, DuckDB queries, and the complete local
smoke path.

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
