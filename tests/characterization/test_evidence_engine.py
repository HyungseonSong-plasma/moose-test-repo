import polars as pl
import pytest
from pydantic import ValidationError

from qpx_harness.evidence_engine import (
    CORE_FACE_CONTRACT,
    DEFAULT_FACE_CONTRACT,
    GREEN_GAUSS_FACE_CONTRACT,
    ColumnSpec,
    CoreColumnRole,
    DiagnosticMetricSpec,
    DiagnosisReport,
    DiagnosisRule,
    DiagnosisRuleRegistry,
    EvidenceStore,
    EvidenceTolerances,
    MetricPredicate,
    Z3DiagnosisEngine,
    Z3OwnerRule,
    Z3RuleSet,
    build_cell_evidence,
    build_constant_state_registry,
    build_constant_state_ruleset,
    evaluate_diagnosis_registry,
    normalize_and_project,
    prepare_face_evidence,
    summarize_constant_state,
    summarize_constant_state_report,
    write_evidence_bundle,
)
from qpx_harness.evidence_engine.local_smoke import run_smoke
from qpx_harness.evidence_engine.synthetic import rz_constant_square_face_rows


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
    assert DEFAULT_FACE_CONTRACT == GREEN_GAUSS_FACE_CONTRACT
    assert "runtime_surface_x" in GREEN_GAUSS_FACE_CONTRACT.required_columns
    assert "field_cell" in GREEN_GAUSS_FACE_CONTRACT.required_columns
    assert "runtime_grad_x" in GREEN_GAUSS_FACE_CONTRACT.required_columns


def test_default_schema_normalizes_safe_aliases_before_transform():
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

    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(raw, radial_component=0)

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
    contract = DEFAULT_FACE_CONTRACT.extend(
        {
            "electron_temperature": ColumnSpec(
                canonical="electron_temperature",
                aliases=("Te_eV", "mean_energy_eV"),
                required=False,
            )
        }
    )

    normalized = normalize_and_project(raw, contract)
    face = prepare_face_evidence(raw, schema_contract=contract)

    assert "electron_temperature" in normalized.columns
    assert "Te_eV" not in normalized.columns
    assert normalized["electron_temperature"][0] == pytest.approx(7.25)
    assert "electron_temperature" in face.columns


def test_schema_rejects_duplicate_canonical_and_alias_sources():
    raw = rz_constant_square_face_rows().with_columns(pl.col("elem_id").alias("cell_id"))

    with pytest.raises(ValueError, match="multiple matching columns"):
        prepare_face_evidence(raw)


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
    assert diagnosis["selected_rule_id"] == "surface_vector_construction"
    assert diagnosis["status"] == "ISOLATED_OWNER_CLASS"
    assert diagnosis["solver_status"] == "SATISFIED"
    assert diagnosis["rz_specific_status"] == "REQUIRES_SPATIAL_COMPONENT_AGREEMENT"

    failure = diagnosis["failing_locations"][0]
    assert failure["entity_kind"] == "face"
    assert failure["metric"] == "surface_delta_norm"
    assert failure["elem_id"] == 10
    assert failure["face_id"] == 1
    assert failure["centroid"] == (2.0, 0.5)
    assert failure["error_value"] == pytest.approx(1.0e-9)


def test_registry_extension_adds_new_owner_without_diagnose_code_changes():
    raw = rz_constant_square_face_rows()
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0).with_columns(
        pl.lit(2.5e-3).alias("electron_diffusivity_error")
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
        top_k_failures=3,
    )

    assert report.selected_rule_id == "electron_diffusivity_consistency"
    assert report.primary_owner_class == "ELECTRON_DIFFUSIVITY_CONSISTENCY"
    assert report.solver_status == "SATISFIED"
    assert report.metrics["max_electron_diffusivity_error"] == pytest.approx(2.5e-3)
    assert report.failing_locations[0].elem_id == 10
    assert report.failing_locations[0].metric == "electron_diffusivity_error"
    assert report.decision_order[0] == "electron diffusivity consistency"


def test_external_z3_ruleset_supports_composite_physics_logic():
    raw = rz_constant_square_face_rows()
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0).with_columns(
        pl.lit(2.5e-3).alias("electron_diffusivity_error")
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
    ruleset = build_constant_state_ruleset().extend(
        (
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
        )
    )

    report = evaluate_diagnosis_registry(
        {"face": face, "cell": cell},
        registry,
        z3_ruleset=ruleset,
    )

    assert report.selected_rule_id == "diffusivity_with_clean_geometry"
    assert report.primary_owner_class == "ELECTRON_DIFFUSIVITY_CONSISTENCY"
    assert report.solver_status == "SATISFIED"
    assert report.failing_locations[0].elem_id == 10


def test_z3_engine_missing_metric_is_contract_error_not_false_pass():
    ruleset = Z3RuleSet(
        rules=(
            Z3OwnerRule(
                rule_id="needs_two_metrics",
                owner_class="COMPOSITE_OWNER",
                status="UNRESOLVED",
                decision_label="composite owner",
                priority=10,
                all_of=(
                    MetricPredicate(metric_id="a", operator="gt", threshold=0.0),
                    MetricPredicate(metric_id="b", operator="gt", threshold=0.0),
                ),
            ),
        ),
        pass_status="PASS",
        rz_specific_status="NOT_APPLICABLE",
    )

    with pytest.raises(ValueError, match="missing required metric values: b"):
        Z3DiagnosisEngine(ruleset).diagnose({"a": 1.0})


def test_registry_supports_non_spatial_run_level_metric():
    registry = DiagnosisRuleRegistry(
        metrics={
            "jacobian_relative_error": DiagnosticMetricSpec(
                metric_id="jacobian_relative_error",
                source="jacobian",
                column="relative_error",
                report_key="max_jacobian_relative_error",
            )
        },
        rules=(
            DiagnosisRule(
                rule_id="jacobian_consistency",
                metric_id="jacobian_relative_error",
                threshold=1.0e-3,
                owner_class="JACOBIAN_CONSISTENCY",
                status="UNRESOLVED",
                decision_label="Jacobian consistency",
                priority=10,
            ),
        ),
        pass_status="JACOBIAN_PASS",
        rz_specific_status="NOT_APPLICABLE",
    )

    report = evaluate_diagnosis_registry(
        {"jacobian": pl.DataFrame({"relative_error": [0.0369]})},
        registry,
    )

    assert report.status == "UNRESOLVED"
    assert report.primary_owner_class == "JACOBIAN_CONSISTENCY"
    assert report.solver_status == "SATISFIED"
    assert report.failing_locations == []
    assert report.rz_specific_status == "NOT_APPLICABLE"


def test_registry_rejects_unknown_metric_and_duplicate_priority():
    metric = DiagnosticMetricSpec(
        metric_id="a",
        source="cell",
        column="a",
        report_key="max_a",
    )
    with pytest.raises(ValidationError, match="unknown metric"):
        DiagnosisRuleRegistry(
            metrics={"a": metric},
            rules=(
                DiagnosisRule(
                    rule_id="bad",
                    metric_id="missing",
                    threshold=0.0,
                    owner_class="BAD",
                    status="UNRESOLVED",
                    decision_label="bad",
                    priority=1,
                ),
            ),
        )

    with pytest.raises(ValidationError, match="priority"):
        DiagnosisRuleRegistry(
            metrics={"a": metric},
            rules=(
                DiagnosisRule(
                    rule_id="r1",
                    metric_id="a",
                    threshold=0.0,
                    owner_class="A",
                    status="UNRESOLVED",
                    decision_label="a1",
                    priority=1,
                ),
                DiagnosisRule(
                    rule_id="r2",
                    metric_id="a",
                    threshold=1.0,
                    owner_class="B",
                    status="UNRESOLVED",
                    decision_label="a2",
                    priority=1,
                ),
            ),
        )


def test_typed_report_and_tolerance_validation():
    raw = rz_constant_square_face_rows(perturb_surface_x=1.0e-9)
    face = prepare_face_evidence(raw)
    cell = build_cell_evidence(face, radial_component=0)

    report = summarize_constant_state_report(
        face,
        cell,
        tolerances=EvidenceTolerances(surface_vector_abs=1.0e-12),
    )
    assert isinstance(report, DiagnosisReport)
    assert report.primary_owner_class == "SURFACE_VECTOR_CONSTRUCTION"
    assert report.solver_status == "SATISFIED"
    assert report.failing_locations[0].face_id == 1

    with pytest.raises(ValidationError):
        EvidenceTolerances(surface_vector_abs=-1.0)


def test_missing_diagnostic_metric_is_contract_error_not_false_pass():
    raw = rz_constant_square_face_rows()
    face = prepare_face_evidence(raw).drop("surface_delta_norm")
    cell = build_cell_evidence(raw, radial_component=0)

    with pytest.raises(ValueError, match="surface_delta_norm"):
        summarize_constant_state(face, cell)


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
    assert summary["baseline_diagnosis"]["solver_status"] == "SATISFIED"
    assert (
        summary["perturbed_diagnosis"]["primary_owner_class"]
        == "SURFACE_VECTOR_CONSTRUCTION"
    )
    assert summary["perturbed_diagnosis"]["failing_locations"][0]["face_id"] == 1
    assert (output / "baseline" / "face_evidence.parquet").is_file()
    assert (output / "baseline" / "cell_evidence.parquet").is_file()
    assert (output / "perturbed" / "face_evidence.parquet").is_file()
    assert (output / "perturbed" / "cell_evidence.parquet").is_file()
    assert (output / "evidence.duckdb").is_file()
    assert (output / "summary.json").is_file()
