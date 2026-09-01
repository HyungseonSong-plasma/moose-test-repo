"""Stats mapping for the Issue45 first-linear diagnostic."""
from __future__ import annotations

from typing import Any


def build_first_linear_stats(
    case_id: str,
    *,
    runtime: dict[str, Any],
    decision: dict[str, Any],
) -> Any:
    """Map existing first-linear facts into Stats without changing producer contracts."""

    from ..analysis.metrics.accuracy import build_jacobian_accuracy_stats
    from ..analysis.stats_builder import (
        build_convergence_stats,
        build_runtime_simulation_stats,
    )

    first_linear = decision.get("first_linear")
    core = decision.get("core")
    jacobian = decision.get("jacobian")
    ksp_identity = decision.get("ksp_identity")
    true_residuals = decision.get("true_residuals")

    convergence = build_convergence_stats(
        linear_terminations=(first_linear,) if isinstance(first_linear, dict) else (),
        ksp_view=ksp_identity if isinstance(ksp_identity, dict) else None,
        true_residuals=true_residuals if isinstance(true_residuals, list) else (),
        variable_residual_blocks=(
            core.get("variable_residuals", ()) if isinstance(core, dict) else ()
        ),
        scaling_factor_blocks=(
            core.get("automatic_scaling_factors", ())
            if isinstance(core, dict)
            else ()
        ),
    )
    accuracy = build_jacobian_accuracy_stats(
        jacobian if isinstance(jacobian, dict) else None
    )
    return build_runtime_simulation_stats(
        runtime,
        case_id=case_id,
        convergence=convergence,
        accuracy=accuracy,
    )
