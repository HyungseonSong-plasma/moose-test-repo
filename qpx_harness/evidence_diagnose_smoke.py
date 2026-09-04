"""Local integration smoke for the canonical Evidence -> Analysis -> Diagnose pipeline.

Usage:
    python -m qpx_harness.evidence_diagnose_smoke
    python -m qpx_harness.evidence_diagnose_smoke --output local_evidence_smoke
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from qpx_harness.application.green_gauss_workflow import (
    build_cell_evidence,
    prepare_face_evidence,
    write_evidence_bundle,
)
from qpx_harness.diagnose import EvidenceTolerances, summarize_constant_state
from qpx_harness.evidence import EvidenceStore, rz_constant_square_face_rows


def _run_at(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)

    baseline_raw = rz_constant_square_face_rows(
        run_id="local-smoke-baseline",
        case_id="exact-constant-rz",
    )
    baseline_face = prepare_face_evidence(baseline_raw)
    baseline_cell = build_cell_evidence(baseline_face, radial_component=0)
    baseline_diagnosis = summarize_constant_state(baseline_face, baseline_cell)
    baseline_paths = write_evidence_bundle(
        baseline_raw,
        root / "baseline",
        radial_component=0,
    )

    perturbed_raw = rz_constant_square_face_rows(
        run_id="local-smoke-perturbed",
        case_id="surface-vector-perturbation",
        perturb_surface_x=1.0e-9,
    )
    perturbed_face = prepare_face_evidence(perturbed_raw)
    perturbed_cell = build_cell_evidence(perturbed_face, radial_component=0)
    perturbed_diagnosis = summarize_constant_state(
        perturbed_face,
        perturbed_cell,
        tolerances=EvidenceTolerances(surface_vector_abs=1.0e-12),
    )
    perturbed_paths = write_evidence_bundle(
        perturbed_raw,
        root / "perturbed",
        radial_component=0,
    )

    database_path = root / "evidence.duckdb"
    with EvidenceStore(database_path) as store:
        store.ingest_parquet("baseline_face_evidence", baseline_paths["face_evidence"])
        store.ingest_parquet("baseline_cell_evidence", baseline_paths["cell_evidence"])
        store.ingest_parquet("perturbed_face_evidence", perturbed_paths["face_evidence"])
        store.ingest_parquet("perturbed_cell_evidence", perturbed_paths["cell_evidence"])

        row_counts = store.query(
            """
            SELECT
              (SELECT count(*) FROM baseline_face_evidence) AS baseline_faces,
              (SELECT count(*) FROM baseline_cell_evidence) AS baseline_cells,
              (SELECT count(*) FROM perturbed_face_evidence) AS perturbed_faces,
              (SELECT count(*) FROM perturbed_cell_evidence) AS perturbed_cells
            """
        ).row(0, named=True)
        worst = store.worst_cells(
            table="perturbed_cell_evidence",
            metric="gradient_delta_norm",
            limit=1,
        )
        worst_cell = worst.row(0, named=True) if worst.height else None

    checks = {
        "baseline_constant_state_pass": baseline_diagnosis["status"] == "CONSTANT_STATE_PASS",
        "baseline_owner_is_null": baseline_diagnosis["primary_owner_class"] is None,
        "perturbation_is_surface_vector": (
            perturbed_diagnosis["primary_owner_class"] == "SURFACE_VECTOR_CONSTRUCTION"
        ),
        "duckdb_face_counts": (
            row_counts["baseline_faces"] == 4 and row_counts["perturbed_faces"] == 4
        ),
        "duckdb_cell_counts": (
            row_counts["baseline_cells"] == 1 and row_counts["perturbed_cells"] == 1
        ),
        "worst_cell_available": worst_cell is not None,
    }
    passed = all(checks.values())

    summary = {
        "status": "PASS" if passed else "FAIL",
        "contract": {
            "symmetry_axis": "Y",
            "radial_coordinate": "X",
            "radial_component": 0,
        },
        "checks": checks,
        "baseline_diagnosis": baseline_diagnosis,
        "perturbed_diagnosis": perturbed_diagnosis,
        "row_counts": row_counts,
        "worst_perturbed_cell": worst_cell,
        "artifacts": {
            "baseline": baseline_paths,
            "perturbed": perturbed_paths,
            "duckdb": str(database_path),
        },
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def run_smoke(output: Path | None = None) -> dict[str, Any]:
    if output is not None:
        output = output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        return _run_at(output)

    with tempfile.TemporaryDirectory(prefix="qpx_evidence_diagnose_smoke_") as temp:
        return _run_at(Path(temp))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        summary = run_smoke(args.output)
    except Exception as exc:
        print(f"EVIDENCE_DIAGNOSE_LOCAL_SMOKE: FAIL ({type(exc).__name__}: {exc})")
        return 1

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"EVIDENCE_DIAGNOSE_LOCAL_SMOKE: {summary['status']}")
        print("  symmetry_axis=Y radial_coordinate=X radial_component=0")
        print(
            "  baseline="
            f"{summary['baseline_diagnosis']['status']} "
            "perturbed_owner="
            f"{summary['perturbed_diagnosis']['primary_owner_class']}"
        )
        if args.output is not None:
            print(f"  artifacts={args.output.resolve()}")

    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_smoke"]
