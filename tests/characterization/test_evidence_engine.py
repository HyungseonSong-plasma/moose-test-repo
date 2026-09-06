import polars as pl
import pytest
from pydantic import ValidationError

from qpx_harness.analysis.diagnostic_metrics import DiagnosticMetricSpec
from qpx_harness.application.gradient_reconstruction import (
    analyze_gradient_reconstruction,
    write_reconstruction_evidence_bundle,
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
from qpx_harness.reasoning import (
    DiagnosisReport,
    MetricPredicate,
    ReasoningRule,
    RuleSet,
    evaluate_diagnostic_rules,
)
from qpx_harness.reasoning.engines.z3 import evaluate_rules
from qpx_harness.reasoning.gradient_reconstruction import (
    ReconstructionTolerances,
    build_constant_state_metrics,
    build_constant_state_ruleset,
    summarize_constant_state,
    summarize_constant_state_report,
)
from qpx_harness.validation.evidence_diagnose_smoke import run_smoke

METHOD = "green_gauss"


def _analyze(raw):
    return analyze_gradient_reconstruction(raw, method=METHOD, radial_component=0)


def test_polars_reconstructs_exact_rz_constant_state_contract():
    raw = rz_constant_square_face_rows()
    face, cell = _analyze(raw)

    assert face.select(pl.col("surface_delta_norm").max()).item() == 0.0
    assert face.select(pl.col("field_face_delta").abs().max()).item() == 0.0
    assert cell["face_count"][0] == 4
    assert abs(cell["pre_rz_grad_x"][0] - 2.0) < 1.0e-14
    assert abs(cell["rz_correction_x"][0] - 2.0) < 1.0e-14
    assert abs(cell["reconstructed_grad_x"][0]) < 1.0e-14
    assert abs(cell["reconstructed_grad_y"][0]) < 1.0e-14
    assert abs(cell["surface_closure_norm"][0]) < 1.0e-14

    diagnosis = summarize_constant_state(face, cell, method=METHOD)
    assert diagnosis["status"] == "CONSTANT_STATE_PASS"
    assert diagnosis["primary_owner_class"] is None
    assert diagnosis["selected_rule_id"] is None
    assert diagnosis["solver_status"] == "SATISFIED"
    assert diagnosis["failing_locations"] == []
    assert diagnosis["reconstruction_method"] == METHOD


def test_core_column_role_is_limited_to_identity_topology_and_spatial_coordinates():
    assert {role.value for role in CoreColumnRole} == {
        "run_id",
        "case_id",
        "elem_id",
        "face_id",
        "cell_x",
        "cell_y",
        "face_x",
        "face_y",
    }
    assert set(CORE_FACE_CONTRACT.required_columns) == {
        "run_id",
        "case_id",
        "elem_id",
        "face_id",
        "cell_x",
        "cell_y",
        "face_x",
        "face_y",
    }
    assert DEFAULT_FACE_CONTRACT == CORE_FACE_CONTRACT
    assert DEFAULT_FACE_CONTRACT != GREEN_GAUSS_FACE_CONTRACT
    assert "runtime_surface_x" in GREEN_GAUSS_FACE_CONTRACT.required_columns
    assert "field_cell" in GREEN_GAUSS_FACE_CONTRACT.required_columns
    assert "runtime_grad_x" in GREEN_GAUSS_FACE_CONTRACT.required_columns


def test_green_gauss_contract_normalizes_safe_aliases_before_reconstruction():
    raw = rz_constant_square_face_rows().rename(
        {
            "elem_id": "cell_id",
            "face_id": "side_id",
            "cell_x": "x_C",
            "cell_y": "y_C",
            "face_x": "x_f",
            "face_y": "y_f",
            "normal_x": "nx",
            "normal_y": "ny",
            "moose_surface_x": "S_x",
            "moose_surface_y": "S_y",
            "cell_volume": "V_rz",
            "radial_coordinate": "radius",
            "qpx_grad_x": "grad_x",
            "qpx_grad_y": "grad_y",
        }
    )

    face, cell = _analyze(raw)
    assert "elem_id" in face.columns and "cell_id" not in face.columns
    assert "face_id" in face.columns and "side_id" not in face.columns
    assert "cell_x" in face.columns and "x_C" not in face.columns
    assert "runtime_surface_x" in face.columns and "S_x" not in face.columns
    assert "field_cell" in face.columns and "n_cell" not in face.columns
    assert "field_face" in face.columns and "n_face" not in face.columns
    assert "runtime_grad_x" in face.columns and "grad_x" not in face.columns
    assert cell["elem_id"][0] == 10
    assert abs(cell["reconstructed_grad_norm"][0]) < 1.0e-14
    assert abs(cell["runtime_grad_norm"][0]) < 1.0e-14


def test_core_contract_does_not_own_green_gauss_quantities():
    raw = rz_constant_square_face_rows()
    normalized = normalize_and_project(raw, CORE_FACE_CONTRACT)
    assert "run_id" in normalized.columns
    assert "elem_id" in normalized.columns
    assert "moose_surface_x" in normalized.columns
    assert "n_cell" in normalized.columns
    assert "qpx_grad_x" in normalized.columns
    assert "runtime_surface_x" not in normalized.columns
    assert "field_cell" not in normalized.columns
    assert "runtime_grad_x" not in normalized.columns


def test_schema_extension_adds_new_quantity_without_transform_changes():
    raw = rz_constant_square_face_rows().with_columns(pl.lit(7.25).alias("Te_eV"))
    contract = GREEN_GAUSS_FACE_CONTRACT.extend(
        {
            "electron_temperature": ColumnSpec(
                canonical="electron_temperature",
                aliases=("Te_eV", "mean_energy_eV"),
                required=False,
            )
        }
    )
    normalized = normalize_and_project(raw, contract)
    assert "electron_temperature" in normalized.columns
    assert "Te_eV" not in normalized.columns
    assert normalized["electron_temperature"][0] == pytest.approx(7.25)


def test_schema_rejects_duplicate_canonical_and_alias_sources():
    raw = rz_constant_square_face_rows().with_columns(pl.col("elem_id").alias("cell_id"))
    with pytest.raises(ValueError, match="multiple matching columns"):
        normalize_and_project(raw, GREEN_GAUSS_FACE_CONTRACT)


def test_reconstruction_method_must_be_explicit_and_supported():
    raw = rz_constant_square_face_rows()
    with pytest.raises(ValueError, match="unsupported gradient-reconstruction method"):
        analyze_gradient_reconstruction(raw, method="least_squares")


def test_surface_vector_perturbation_isolated_before_rz_attribution():
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
    face, cell = _analyze(raw)
    diagnosis = summarize_constant_state(
        face,
        cell,
        method=METHOD,
        tolerances=ReconstructionTolerances(surface_vector_abs=1.0e-12),
    )
    assert diagnosis["primary_owner_class"] == "SURFACE_VECTOR_CONSTRUCTION"
    assert diagnosis["selected_rule_id"] == "surface_vector_construction"
    assert diagnosis["status"] == "ISOLATED_OWNER_CLASS"
    failure = diagnosis["failing_locations"][0]
    assert failure["entity_kind"] == "face"
    assert failure["metric"] == "surface_delta_norm"
    assert failure["elem_id"] == 10
    assert failure["face_id"] == 1
    assert failure["centroid"] == (2.0, 0.5)
    assert failure["error_value"] == pytest.approx(1.0e-9)


def test_rule_extension_adds_new_owner_without_reasoning_code_changes():
    raw = rz_constant_square_face_rows()
    face, cell = _analyze(raw)
    cell = cell.with_columns(pl.lit(2.5e-3).alias("electron_diffusivity_error"))

    metrics = build_constant_state_metrics()
    metrics["electron_diffusivity_error"] = DiagnosticMetricSpec(
        metric_id="electron_diffusivity_error",
        source="cell",
        column="electron_diffusivity_error",
        report_key="max_electron_diffusivity_error",
        entity_kind="cell",
        x_col="cell_x",
        y_col="cell_y",
    )
    base_rules = build_constant_state_ruleset(method=METHOD)
    ruleset = RuleSet(
        rules=(
            ReasoningRule(
                rule_id="electron_diffusivity_consistency",
                owner_class="ELECTRON_DIFFUSIVITY_CONSISTENCY",
                status="ISOLATED_OWNER_CLASS",
                decision_label="electron diffusivity consistency",
                priority=5,
                all_of=(MetricPredicate("electron_diffusivity_error", "gt", 1.0e-4),),
                location_metric_id="electron_diffusivity_error",
            ),
            *base_rules.rules,
        ),
        pass_status=base_rules.pass_status,
    )
    report = evaluate_diagnostic_rules(
        {"face": face, "cell": cell}, metrics, ruleset, top_k_failures=3
    )
    assert report.selected_rule_id == "electron_diffusivity_consistency"
    assert report.primary_owner_class == "ELECTRON_DIFFUSIVITY_CONSISTENCY"
    assert dict(report.metrics)["max_electron_diffusivity_error"] == pytest.approx(2.5e-3)


def test_external_ruleset_supports_composite_physics_logic():
    raw = rz_constant_square_face_rows()
    face, cell = _analyze(raw)
    cell = cell.with_columns(pl.lit(2.5e-3).alias("electron_diffusivity_error"))
    metrics = build_constant_state_metrics()
    metrics["electron_diffusivity_error"] = DiagnosticMetricSpec(
        metric_id="electron_diffusivity_error",
        source="cell",
        column="electron_diffusivity_error",
        report_key="max_electron_diffusivity_error",
        entity_kind="cell",
        x_col="cell_x",
        y_col="cell_y",
    )
    base_rules = build_constant_state_ruleset(method=METHOD)
    ruleset = RuleSet(
        rules=(
            ReasoningRule(
                rule_id="diffusivity_with_clean_geometry",
                owner_class="ELECTRON_DIFFUSIVITY_CONSISTENCY",
                status="ISOLATED_OWNER_CLASS",
                decision_label="electron diffusivity with clean geometry",
                priority=5,
                all_of=(
                    MetricPredicate("electron_diffusivity_error", "gt", 1.0e-4),
                    MetricPredicate("surface_vector_delta", "le", 1.0e-14),
                ),
                location_metric_id="electron_diffusivity_error",
            ),
            *base_rules.rules,
        ),
        pass_status=base_rules.pass_status,
    )
    report = evaluate_diagnostic_rules({"face": face, "cell": cell}, metrics, ruleset)
    assert report.selected_rule_id == "diffusivity_with_clean_geometry"
    assert report.primary_owner_class == "ELECTRON_DIFFUSIVITY_CONSISTENCY"


def test_z3_backend_missing_metric_is_contract_error_not_false_pass():
    ruleset = RuleSet(
        rules=(
            ReasoningRule(
                rule_id="needs_two_metrics",
                owner_class="COMPOSITE_OWNER",
                status="UNRESOLVED",
                decision_label="composite owner",
                priority=10,
                all_of=(
                    MetricPredicate("a", "gt", 0.0),
                    MetricPredicate("b", "gt", 0.0),
                ),
            ),
        ),
        pass_status="PASS",
    )
    with pytest.raises(ValueError, match=r"missing metric\(s\) required by rule set: b"):
        evaluate_rules({"a": 1.0}, ruleset)


def test_reasoning_supports_non_spatial_run_level_metric():
    metrics = {
        "jacobian_relative_error": DiagnosticMetricSpec(
            metric_id="jacobian_relative_error",
            source="jacobian",
            column="relative_error",
            report_key="max_jacobian_relative_error",
        )
    }
    ruleset = RuleSet(
        rules=(
            ReasoningRule(
                rule_id="jacobian_consistency",
                owner_class="JACOBIAN_CONSISTENCY",
                status="UNRESOLVED",
                decision_label="Jacobian consistency",
                priority=10,
                all_of=(MetricPredicate("jacobian_relative_error", "gt", 1.0e-3),),
            ),
        ),
        pass_status="JACOBIAN_PASS",
    )
    report = evaluate_diagnostic_rules(
        {"jacobian": pl.DataFrame({"relative_error": [0.0369]})}, metrics, ruleset
    )
    assert report.status == "UNRESOLVED"
    assert report.primary_owner_class == "JACOBIAN_CONSISTENCY"
    assert report.failing_locations == ()


def test_typed_report_and_tolerance_validation():
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
    face, cell = _analyze(raw)
    report = summarize_constant_state_report(
        face,
        cell,
        method=METHOD,
        tolerances=ReconstructionTolerances(surface_vector_abs=1.0e-12),
    )
    assert isinstance(report, DiagnosisReport)
    assert report.primary_owner_class == "SURFACE_VECTOR_CONSTRUCTION"
    assert report.failing_locations[0].face_id == 1
    with pytest.raises(ValidationError):
        ReconstructionTolerances(surface_vector_abs=-1.0)


def test_missing_diagnostic_metric_is_contract_error_not_false_pass():
    raw = rz_constant_square_face_rows()
    face, cell = _analyze(raw)
    face = face.drop("surface_delta_norm")
    with pytest.raises(ValueError, match="surface_delta_norm"):
        summarize_constant_state(face, cell, method=METHOD)


def test_parquet_bundle_and_duckdb_queries(tmp_path):
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
    paths = write_reconstruction_evidence_bundle(
        raw, tmp_path / "bundle", method=METHOD, radial_component=0
    )
    with EvidenceStore(tmp_path / "evidence.duckdb") as store:
        store.ingest_parquet("face_evidence", paths["face_evidence"])
        store.ingest_parquet("cell_evidence", paths["cell_evidence"])
        counts = store.query(
            "SELECT (SELECT count(*) FROM face_evidence) AS faces, "
            "(SELECT count(*) FROM cell_evidence) AS cells"
        ).row(0, named=True)
        worst = store.worst_cells(
            table="cell_evidence", metric="gradient_delta_norm", limit=1
        )
    assert counts == {"faces": 4, "cells": 1}
    assert worst.height == 1


def test_local_evidence_analysis_reasoning_smoke(tmp_path):
    summary = run_smoke(tmp_path / "smoke")
    assert summary["status"] == "PASS"
    assert summary["contract"]["reconstruction_method"] == METHOD
    assert summary["baseline_diagnosis"]["status"] == "CONSTANT_STATE_PASS"
    assert summary["perturbed_diagnosis"]["primary_owner_class"] == "SURFACE_VECTOR_CONSTRUCTION"
