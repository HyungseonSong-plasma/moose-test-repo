import polars as pl

from qpx_harness.evidence_engine import (
    EvidenceStore,
    EvidenceTolerances,
    build_cell_evidence,
    prepare_face_evidence,
    summarize_constant_state,
    write_evidence_bundle,
)
from qpx_harness.evidence_engine.local_smoke import run_smoke
from qpx_harness.evidence_engine.synthetic import rz_constant_square_face_rows


def test_polars_reconstructs_exact_rz_constant_state_contract():
    raw = rz_constant_square_face_rows()
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
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
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
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
    paths = write_evidence_bundle(raw, tmp_path / "bundle", radial_component=0)

    with EvidenceStore(tmp_path / "evidence.duckdb") as store:
        store.ingest_parquet("face_evidence", paths["face_evidence"])
        store.ingest_parquet("cell_evidence", paths["cell_evidence"])
        worst = store.worst_cells(limit=1)
        assert worst.height == 1
        assert worst["elem_id"][0] == 10
        count = store.query("SELECT count(*) AS n FROM face_evidence")
        assert count["n"][0] == 4


def test_local_smoke_preserves_artifacts_and_exercises_full_stack(tmp_path):
    output = tmp_path / "local-smoke"
    summary = run_smoke(output)

    assert summary["status"] == "PASS"
    assert summary["contract"] == {
        "symmetry_axis": "Y",
        "radial_coordinate": "X",
        "radial_component": 0,
    }
    assert summary["baseline_diagnosis"]["status"] == "CONSTANT_STATE_PASS"
    assert (
        summary["perturbed_diagnosis"]["primary_owner_class"]
        == "SURFACE_VECTOR_CONSTRUCTION"
    )
    assert (output / "baseline" / "face_evidence.parquet").is_file()
    assert (output / "baseline" / "cell_evidence.parquet").is_file()
    assert (output / "perturbed" / "face_evidence.parquet").is_file()
    assert (output / "perturbed" / "cell_evidence.parquet").is_file()
    assert (output / "evidence.duckdb").is_file()
    assert (output / "summary.json").is_file()
