"""Pure preliminary classification for Issue31 EVR1 runtime evidence."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _status(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    return result.get("validation", {}).get("status")


def _wall(pair: dict[str, Any], mode: str = "benchmark") -> float | None:
    result = pair.get(mode)
    value = result.get("performance", {}).get("wall_seconds") if result else None
    return float(value) if isinstance(value, (int, float)) else None


def preliminary_classification(
    transport: dict[str, Any],
    monolithic: dict[str, Any],
    transport_physics: dict[str, Any] | None,
    monolithic_physics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify the accepted EVR1 runtime outcomes without changing the experiment."""
    if _status(transport.get("benchmark")) != "P2_PASS_P3_PASS":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "transport-only known-good control did not complete",
        }
    if transport_physics is None or transport_physics.get("status") != "PASS":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "transport-only runtime completed but physics checker failed",
        }

    mono_status = _status(monolithic.get("benchmark"))
    if mono_status == "HARNESS_OR_CONSTRUCTION_FAIL":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": "monolithic Q0 failed P2/construction",
        }
    if mono_status == "RUNTIME_FAIL_OR_NONCONVERGENCE":
        log = Path(monolithic["root"]) / "benchmark" / "p3_run.log"
        text = log.read_text(errors="replace") if log.is_file() else ""
        if re.search(r"DIVERGED|did not converge|Nonlinear solve.*fail", text, re.IGNORECASE):
            return {
                "class": "MONOLITHIC_NONLINEAR_CONVERGENCE_FAIL",
                "reason": "monolithic Q0 reached runtime but nonlinear solve did not converge",
            }
        return {
            "class": "MONOLITHIC_RUNTIME_FAIL",
            "reason": "monolithic Q0 failed at runtime without a proven convergence signature",
        }
    if mono_status != "P2_PASS_P3_PASS":
        return {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "reason": f"monolithic benchmark status is {mono_status!r}",
        }
    if monolithic_physics is None or monolithic_physics.get("status") != "PASS":
        return {
            "class": "PHYSICS_CHECK_FAIL",
            "reason": "monolithic Q0 runtime completed but physics checker failed",
        }

    investigation = monolithic.get("investigation") or {}
    classification = investigation.get("classification", {})
    bottleneck = classification.get("bottleneck_class")
    if bottleneck in {"PC_FACTORIZATION", "LINEAR_SOLVE"}:
        label = "MONOLITHIC_LINEAR_ALGEBRA_BOUND_CANDIDATE"
    elif bottleneck in {"APPLICATION_EVALUATION", "JACOBIAN_AD"}:
        label = "MONOLITHIC_APPLICATION_OR_JACOBIAN_BOUND_CANDIDATE"
    else:
        label = "MONOLITHIC_VIABILITY_REVIEW"

    t_wall = _wall(transport)
    m_wall = _wall(monolithic)
    ratio = m_wall / t_wall if t_wall and m_wall is not None else None
    return {
        "class": label,
        "reason": "monolithic one-step completed; final viability requires evidence review",
        "transport_benchmark_wall_seconds": t_wall,
        "monolithic_benchmark_wall_seconds": m_wall,
        "monolithic_to_transport_wall_ratio": ratio,
        "bottleneck": classification,
    }
