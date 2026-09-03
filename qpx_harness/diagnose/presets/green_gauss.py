"""Green-Gauss constant-state diagnosis preset."""
from __future__ import annotations

from ..models import (
    DiagnosticMetricSpec,
    DiagnosisRule,
    DiagnosisRuleRegistry,
    EvidenceTolerances,
    Z3RuleSet,
)
from ..z3_engine import ruleset_from_registry


def build_constant_state_registry(
    tolerances: EvidenceTolerances | None = None,
) -> DiagnosisRuleRegistry:
    tol = tolerances or EvidenceTolerances()
    metrics = {
        "face_value_delta": DiagnosticMetricSpec(
            metric_id="face_value_delta",
            source="face",
            column="field_face_delta",
            report_key="max_abs_field_face_delta",
            entity_kind="face",
            x_col="face_x",
            y_col="face_y",
        ),
        "surface_vector_delta": DiagnosticMetricSpec(
            metric_id="surface_vector_delta",
            source="face",
            column="surface_delta_norm",
            report_key="max_surface_delta_norm",
            entity_kind="face",
            x_col="face_x",
            y_col="face_y",
        ),
        "surface_closure": DiagnosticMetricSpec(
            metric_id="surface_closure",
            source="cell",
            column="surface_closure_norm",
            report_key="max_surface_closure_norm",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        ),
        "gradient_reconstruction_delta": DiagnosticMetricSpec(
            metric_id="gradient_reconstruction_delta",
            source="cell",
            column="gradient_delta_norm",
            report_key="max_gradient_delta_norm",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        ),
        "runtime_gradient": DiagnosticMetricSpec(
            metric_id="runtime_gradient",
            source="cell",
            column="runtime_grad_norm",
            report_key="max_runtime_grad_norm",
            entity_kind="cell",
            x_col="cell_x",
            y_col="cell_y",
        ),
        "reconstructed_gradient": DiagnosticMetricSpec(
            metric_id="reconstructed_gradient",
            source="cell",
            column="reconstructed_grad_norm",
            report_key="max_reconstructed_grad_norm",
        ),
    }
    rules = (
        DiagnosisRule(
            rule_id="face_value_reconstruction",
            metric_id="face_value_delta",
            threshold=tol.face_value_abs,
            owner_class="FACE_VALUE_RECONSTRUCTION",
            status="ISOLATED_OWNER_CLASS",
            decision_label="face value reconstruction",
            priority=10,
        ),
        DiagnosisRule(
            rule_id="surface_vector_construction",
            metric_id="surface_vector_delta",
            threshold=tol.surface_vector_abs,
            owner_class="SURFACE_VECTOR_CONSTRUCTION",
            status="ISOLATED_OWNER_CLASS",
            decision_label="surface vector construction",
            priority=20,
        ),
        DiagnosisRule(
            rule_id="rz_surface_geometry_closure",
            metric_id="surface_closure",
            threshold=tol.surface_closure_abs,
            owner_class="RZ_SURFACE_GEOMETRY_CLOSURE",
            status="FAVORED",
            decision_label="RZ surface/volume closure",
            priority=30,
        ),
        DiagnosisRule(
            rule_id="missing_runtime_arithmetic_path",
            metric_id="gradient_reconstruction_delta",
            threshold=tol.gradient_match_abs,
            owner_class="MISSING_MOOSE_ARITHMETIC_PATH",
            status="UNRESOLVED",
            decision_label="runtime-vs-reconstruction arithmetic path",
            priority=40,
        ),
        DiagnosisRule(
            rule_id="green_gauss_constant_preservation",
            metric_id="runtime_gradient",
            threshold=tol.qpx_gradient_abs,
            owner_class="FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION",
            status="ISOLATED_OWNER_CLASS",
            decision_label="Green-Gauss constant preservation",
            priority=50,
        ),
    )
    return DiagnosisRuleRegistry(metrics=metrics, rules=rules)


def build_constant_state_ruleset(
    tolerances: EvidenceTolerances | None = None,
) -> Z3RuleSet:
    return ruleset_from_registry(build_constant_state_registry(tolerances))


__all__ = ["build_constant_state_registry", "build_constant_state_ruleset"]
