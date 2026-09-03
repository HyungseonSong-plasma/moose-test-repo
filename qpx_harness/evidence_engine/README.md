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
python -m pip install -r requirements-evidence-engine.txt
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
  -> Polars face reconstruction
  -> Polars cell Green-Gauss reconstruction
  -> Parquet evidence
  -> DuckDB materialization/query
  -> conservative diagnosis

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
- separation of MOOSE-truth surface vectors from independently reconstructed
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

The local smoke test validates the analysis engine only. A real MOOSE/QPX runtime
probe must eventually emit the canonical face telemetry columns, including:

```text
run_id, case_id, elem_id, face_id
cell_x, cell_y
face_x, face_y
normal_x, normal_y
face_area, coord_factor
moose_surface_x, moose_surface_y
n_cell, n_face
cell_volume, radial_coordinate
qpx_grad_x, qpx_grad_y
```

MOOSE-emitted values are runtime truth. The engine keeps independently
reconstructed values in separate columns and never overwrites that truth.
