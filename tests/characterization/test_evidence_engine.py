import math

import polars as pl

from qpx_harness.evidence_engine import (
    EvidenceStore,
    EvidenceTolerances,
    build_cell_evidence,
    prepare_face_evidence,
    summarize_constant_state,
    write_evidence_bundle,
)


def _rz_square_face_rows(*, perturb_surface_x: float = 0.0) -> pl.DataFrame:
    """One unit-area RZ cell with symmetry axis Y and radial coordinate X."""
    n0 = 3.0
    cell_x = 1.5
    cell_y = 0.5
    volume = 2.0 * math.pi * cell_x
    rows = [
        # face_id, face_x, face_y, nx, ny, coord, Sx, Sy
        (0, 1.0, 0.5, -1.0, 0.0, 2.0 * math.pi * 1.0, -2.0 * math.pi, 0.0),
        (1, 2.0, 0.5, 1.0, 0.0, 2.0 * math.pi * 2.0, 4.0 * math.pi, 0.0),
        (2, 1.5, 0.0, 0.0, -1.0, 2.0 * math.pi * 1.5, 0.0, -3.0 * math.pi),
        (3, 1.5, 1.0, 0.0, 1.0, 2.0 * math.pi * 1.5, 0.0, 3.0 * math.pi),
    ]
    data = []
    for face_id, face_x, face_y, nx, ny, coord, sx, sy in rows:
        data.append(
            {
                "run_id": "run-1",
                "case_id": "constant-rz",
                "elem_id": 10,
                "face_id": face_id,
                "cell_x": cell_x,
                "cell_y": cell_y,
                "face_x": face_x,
                "face_y": face_y,
                "normal_x": nx,
                "normal_y": ny,
                "face_area": 1.0,
                "coord_factor": coord,
                "moose_surface_x": sx + (perturb_surface_x if face_id == 1 else 0.0),
                "moose_surface_y": sy,
                "n_cell": n0,
                "n_face": n0,
                "cell_volume": volume,
                "radial_coordinate": cell_x,
                "qpx_grad_x": 0.0,
                "qpx_grad_y": 0.0,
            }
        )
    return pl.DataFrame(data)


def test_polars_reconstructs_exact_rz_constant_state_contract():
    raw = _rz_square_face_rows()
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0)

    assert face.select(pl.col("surface_delta_norm").max()).item() == 0.0
    assert face.select(pl.col("n_face_delta").abs().max()).item() == 0.0
    assert cell["face_count"][0] == 4
    assert abs(cell["pre_rz_grad_x"][0] - 2.0) < 1.0e-14
    assert abs(cell["rz_correction_x"][0] - 2.0) < 1.0e-14
    assert abs(cell["reconstructed_grad_x"][0]) < 1.0e-14
    assert abs(cell["reconstructed_grad_y"][0]) < 1.0e-14
    assert abs(cell["surface_closure_norm"][0]) < 1.0e-14

    diagnosis = summarize_constant_state(face, cell)
    assert diagnosis["status"] == "CONSTANT_STATE_PASS"
    assert diagnosis["primary_owner_class"] is None


def test_surface_vector_perturbation_isolated_before_rz_attribution():
    raw = _rz_square_face_rows(perturb_surface_x=1.0e-9)
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0)
    diagnosis = summarize_constant_state(
        face,
        cell,
        tolerances=EvidenceTolerances(surface_vector_abs=1.0e-12),
    )
    assert diagnosis["primary_owner_class"] == "SURFACE_VECTOR_CONSTRUCTION"
    assert diagnosis["status"] == "ISOLATED_OWNER_CLASS"
    assert diagnosis["rz_specific_status"] == "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"


def test_parquet_bundle_and_duckdb_queries(tmp_path):
    raw = _rz_square_face_rows(perturb_surface_x=1.0e-9)
    paths = write_evidence_bundle(raw, tmp_path / "bundle", radial_component=0)

    with EvidenceStore(tmp_path / "evidence.duckdb") as store:
        store.ingest_parquet("face_evidence", paths["face_evidence"])
        store.ingest_parquet("cell_evidence", paths["cell_evidence"])
        worst = store.worst_cells(limit=1)
        assert worst.height == 1
        assert worst["elem_id"][0] == 10
        count = store.query("SELECT count(*) AS n FROM face_evidence")
        assert count["n"][0] == 4
