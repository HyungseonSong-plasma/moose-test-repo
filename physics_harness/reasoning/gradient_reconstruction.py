"""Generic constant-state reasoning for gradient-reconstruction evidence."""
from __future__ import annotations

from typing import Any

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from qpx_harness.analysis.diagnostic_metrics import DiagnosticMetricSpec
from .diagnosis import DiagnosisReport
from .evaluator import evaluate_diagnostic_rules
from .rules import MetricPredicate, ReasoningRule, RuleSet


class ReconstructionTolerances(BaseModel):
    """Validated absolute tolerances for constant-state reconstruction checks."""

    model_config = ConfigDict(frozen=True)

    face_value_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_vector_abs: float = Field(default=1.0e-14, ge=0.0)
    surface_closure_abs: float = Field(default=1.0e-14, ge=0.0)
    gradient_match_abs: float = Field(default=1.0e-12, ge=0.0)
    runtime_gradient_abs: float = Field(default=1.0e-12, ge=0.0)


def build_constant_state_metrics() -> dict[str, DiagnosticMetricSpec]:
    return {
        "face_value_delta": DiagnosticMetricSpec(
            metric_id="face_value_delta", source="face", column="field_face_delta",
            report_key="max_abs_field_face_delta", entity_kind="face", x_col="face_x", y_col="face_y",
        ),
        "surface_vector_delta": DiagnosticMetricSpec(
            metric_id="surface_vector_delta", source="face", column="surface_delta_norm",
            report_key="max_surface_delta_norm", entity_kind="face", x_col="face_x", y_col="face_y",
        ),
        "surface_closure": DiagnosticMetricSpec(
            metric_id="surface_closure", source="cell", column="surface_closure_norm",
            report_key="max_surface_closure_norm", entity_kind="cell", x_col="cell_x", y_col="cell_y",
        ),
        "gradient_reconstruction_delta": DiagnosticMetricSpec(
            metric_id="gradient_reconstruction_delta", source="cell", column="gradient_delta_norm",
            report_key="max_gradient_delta_norm", entity_kind="cell", x_col="cell_x", y_col="cell_y",
        ),
        "runtime_gradient": DiagnosticMetricSpec(
            metric_id="runtime_gradient", source="cell", column="runtime_grad_norm",
            report_key="max_runtime_grad_norm", entity_kind="cell", x_col="cell_x", y_col="cell_y",
        ),
        "reconstructed_gradient": DiagnosticMetricSpec(
            metric_id="reconstructed_gradient", source="cell", column="reconstructed_grad_norm",
            report_key="max_reconstructed_grad_norm",
        ),
    }


def build_constant_state_ruleset(
    *,
    method: str,
    tolerances: ReconstructionTolerances | None = None,
) -> RuleSet:
    tol = tolerances or ReconstructionTolerances()
    rules = [
        ReasoningRule(
            rule_id="face_value_reconstruction", owner_class="FACE_VALUE_RECONSTRUCTION",
            status="ISOLATED_OWNER_CLASS", decision_label="face value reconstruction", priority=10,
            all_of=(MetricPredicate("face_value_delta", "gt", tol.face_value_abs),),
            location_metric_id="face_value_delta",
        ),
        ReasoningRule(
            rule_id="surface_vector_construction", owner_class="SURFACE_VECTOR_CONSTRUCTION",
            status="ISOLATED_OWNER_CLASS", decision_label="surface vector construction", priority=20,
            all_of=(MetricPredicate("surface_vector_delta", "gt", tol.surface_vector_abs),),
            location_metric_id="surface_vector_delta",
        ),
        ReasoningRule(
            rule_id="rz_surface_geometry_closure", owner_class="RZ_SURFACE_GEOMETRY_CLOSURE",
            status="FAVORED", decision_label="RZ surface/volume closure", priority=30,
            all_of=(MetricPredicate("surface_closure", "gt", tol.surface_closure_abs),),
            location_metric_id="surface_closure",
        ),
        ReasoningRule(
            rule_id="missing_runtime_arithmetic_path", owner_class="MISSING_MOOSE_ARITHMETIC_PATH",
            status="UNRESOLVED", decision_label="runtime-vs-reconstruction arithmetic path", priority=40,
            all_of=(MetricPredicate("gradient_reconstruction_delta", "gt", tol.gradient_match_abs),),
            location_metric_id="gradient_reconstruction_delta",
        ),
    ]
    if method == "green_gauss":
        rules.append(
            ReasoningRule(
                rule_id="green_gauss_constant_preservation",
                owner_class="FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION",
                status="ISOLATED_OWNER_CLASS", decision_label="Green-Gauss constant preservation", priority=50,
                all_of=(MetricPredicate("runtime_gradient", "gt", tol.runtime_gradient_abs),),
                location_metric_id="runtime_gradient",
            )
        )
    return RuleSet(rules=tuple(rules), pass_status="CONSTANT_STATE_PASS")


def summarize_constant_state_report(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    method: str,
    tolerances: ReconstructionTolerances | None = None,
    top_k_failures: int = 5,
) -> DiagnosisReport:
    return evaluate_diagnostic_rules(
        {"face": face, "cell": cell},
        build_constant_state_metrics(),
        build_constant_state_ruleset(method=method, tolerances=tolerances),
        top_k_failures=top_k_failures,
    )


def summarize_constant_state(
    face: pl.DataFrame,
    cell: pl.DataFrame,
    *,
    method: str,
    tolerances: ReconstructionTolerances | None = None,
    top_k_failures: int = 5,
) -> dict[str, Any]:
    report = summarize_constant_state_report(
        face, cell, method=method, tolerances=tolerances, top_k_failures=top_k_failures
    )
    return {
        "status": report.status,
        "primary_owner_class": report.primary_owner_class,
        "selected_rule_id": report.selected_rule_id,
        "metrics": dict(report.metrics),
        "failing_locations": [
            {
                "entity_kind": item.entity_kind, "metric": item.metric,
                "elem_id": item.elem_id, "face_id": item.face_id,
                "centroid": item.centroid, "error_value": item.error_value,
                "run_id": item.run_id, "case_id": item.case_id,
            }
            for item in report.failing_locations
        ],
        "reconstruction_method": method,
        "rz_specific_status": "REQUIRES_SPATIAL_COMPONENT_AGREEMENT",
        "decision_order": list(report.decision_order),
        "solver_status": report.solver_status,
        "z3_model": report.backend_model,
    }


__all__ = [
    "ReconstructionTolerances",
    "build_constant_state_metrics", "build_constant_state_ruleset",
    "summarize_constant_state", "summarize_constant_state_report",
]
