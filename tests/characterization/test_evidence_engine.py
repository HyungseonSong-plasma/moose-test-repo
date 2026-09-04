import polars as pl
import pytest
from pydantic import ValidationError

from qpx_harness.application.green_gauss_workflow import (
    build_cell_evidence,
    prepare_face_evidence,
    write_evidence_bundle,
)
from qpx_harness.diagnose import (
    DiagnosticMetricSpec,
    DiagnosisReport,
    DiagnosisRule,
    DiagnosisRuleRegistry,
    EvidenceTolerances,
    MetricPredicate,
    Z3DiagnosisEngine,
    Z3OwnerRule,
    Z3RuleSet,
    build_constant_state_registry,
    build_constant_state_ruleset,
    evaluate_diagnosis_registry,
    summarize_constant_state,
    summarize_constant_state_report,
)
from qpx_harness.evidence import (
    CORE_FACE_CONTRACT,
    DEFAULT_FACE_CONTRACT,
    GREEN_GAUSS_FACE_CONTRACT,
    ColumnSpec,
    CoreColumnRole,
    EvidenceStore,
    normalize_and_project,
    rz_constant_square_face_rows,
)
from qpx_harness.validation.evidence_diagnose_smoke import run_smoke


def test_polars_reconstructs_exact_rz_constant_state_contract():
    raw = rz_constant_square_face_rows()
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0)

    assert face.select(pl.col("surface_delta_norm").max()).item() == 0.0
    assert face.select(pl.col("field_face_delta").abs().max()).item() == 0.0
    assert cell["face_count"][0] == 4
    assert abs(cell["pre_rz_grad_x"][0] - 2.0) < 1.0e-14
    assert abs(cell["rz_correction_x"][0] - 2.0) < 1.0e-14
    assert abs(cell["reconstructed_grad_x"][0]) < 1.0e-14
    assert abs(cell["reconstructed_grad_y"][0]) < 1.0e-14
    assert abs(cell["surface_closure_norm"][0]) < 1.0e-14

    diagnosis = summarize_constant_state(face, cell)
    assert diagnosis["status"] == "CONSTANT_STATE_PASS"
    assert diagnosis["primary_owner_class"] is None
    assert diagnosis["selected_rule_id"] is None
    assert diagnosis["solver_status"] == "SATISFIED"
    assert diagnosis["failing_locations"] == []


def test_polars_surface_vector_perturbation_is_classified():
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0)
    diagnosis = summarize_constant_state(
        face,
        cell,
        tolerances=EvidenceTolerances(surface_vector_abs=1.0e-12),
    )
    assert diagnosis["status"] == "CONSTANT_STATE_FAIL"
    assert diagnosis["primary_owner_class"] == "SURFACE_VECTOR_CONSTRUCTION"


def test_evidence_store_ingests_and_queries_canonical_parquet(tmp_path):
    raw = rz_constant_square_face_rows()
    paths = write_evidence_bundle(raw, tmp_path / "bundle", radial_component=0)
    with EvidenceStore(tmp_path / "evidence.duckdb") as store:
        store.ingest_parquet("face", paths["face_evidence"])
        store.ingest_parquet("cell", paths["cell_evidence"])
        assert store.query("select count(*) as n from face").row(0, named=True)["n"] == 4
        assert store.query("select count(*) as n from cell").row(0, named=True)["n"] == 1


def test_local_smoke_runs_through_validation_owner(tmp_path):
    summary = run_smoke(tmp_path / "smoke")
    assert summary["status"] == "PASS"


def test_dynamic_schema_contract_rejects_missing_required_columns():
    with pytest.raises(ValidationError):
        ColumnSpec(name="", role=CoreColumnRole.FACT)


def test_normalize_and_project_core_contract():
    raw = rz_constant_square_face_rows()
    normalized = normalize_and_project(raw, CORE_FACE_CONTRACT)
    assert normalized.height == 4
    assert set(CORE_FACE_CONTRACT.required_names).issubset(normalized.columns)


def test_default_and_green_gauss_contracts_are_available():
    assert DEFAULT_FACE_CONTRACT.name
    assert GREEN_GAUSS_FACE_CONTRACT.name


def test_constant_state_registry_and_ruleset_construct():
    registry = build_constant_state_registry()
    ruleset = build_constant_state_ruleset()
    assert isinstance(registry, DiagnosisRuleRegistry)
    assert isinstance(ruleset, Z3RuleSet)


def test_report_shapes_are_typed():
    raw = rz_constant_square_face_rows()
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0)
    report = summarize_constant_state_report(face, cell)
    assert isinstance(report, DiagnosisReport)


def test_registry_evaluation_accepts_metric_specs():
    registry = DiagnosisRuleRegistry(
        rules=(
            DiagnosisRule(
                rule_id="positive",
                owner_class="TEST",
                predicates=(MetricPredicate(metric="x", op=">", threshold=0.0),),
            ),
        ),
        metrics=(DiagnosticMetricSpec(name="x"),),
    )
    result = evaluate_diagnosis_registry(registry, {"x": 1.0})
    assert result["primary_owner_class"] == "TEST"


def test_z3_engine_accepts_owner_rules():
    engine = Z3DiagnosisEngine(
        Z3RuleSet(
            rules=(
                Z3OwnerRule(
                    rule_id="positive",
                    owner_class="TEST",
                    predicates=(MetricPredicate(metric="x", op=">", threshold=0.0),),
                ),
            )
        )
    )
    result = engine.evaluate({"x": 1.0})
    assert result["primary_owner_class"] == "TEST"
