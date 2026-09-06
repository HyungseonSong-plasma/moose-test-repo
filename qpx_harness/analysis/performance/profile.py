"""Backend-neutral performance bottleneck analysis over adapter-decoded facts.

The public ``analyze`` compatibility entry still accepts evidence paths during
WB3, but all raw PETSc/MOOSE decoding is delegated to the external adapters.
Bottleneck policy and ratios remain owned here.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qpx_harness.adapters.moose.performance.profile import perfgraph_jacobian_self
from qpx_harness.adapters.petsc.performance import (
    EVENT_FUNCTION_EVAL,
    EVENT_JACOBIAN_EVAL,
    EVENT_KSP_SOLVE,
    EVENT_LU_NUMERIC,
    EVENT_LU_SYMBOLIC,
    EVENT_MATRIX_ASSEMBLY_END,
    EVENT_PC_SETUP,
    EVENT_SNES_SOLVE,
    event_time,
    load_events,
)


def _metric(metrics: dict, stem: str, prefix: str | None) -> str | None:
    candidates = []
    if prefix:
        candidates.append(f"{prefix}_{stem}")
    candidates.extend((f"qpxh_{stem}", f"r32_{stem}", stem))
    for key in candidates:
        if metrics.get(key) not in (None, ""):
            return metrics[key]
    return None


def analyze_decoded(
    summary: dict,
    events: dict[str, dict[str, float]],
    perf_jacobian: dict[str, float] | None = None,
    *,
    metric_prefix: str | None = None,
) -> dict:
    """Classify performance using already-decoded timing facts."""
    if summary.get("p2_returncode") != 0:
        return {
            "classification": summary.get("classification", "HARNESS_OR_CONSTRUCTION_FAIL"),
            "interpretable_performance": False,
            "reason": "P2 did not pass.",
        }
    if summary.get("p3_returncode") != 0:
        return {
            "classification": "RUNTIME_FAIL_OR_NONCONVERGENCE",
            "interpretable_performance": False,
            "reason": "P3 did not complete successfully.",
        }

    snes = event_time(events, EVENT_SNES_SOLVE)
    jacobian = event_time(events, EVENT_JACOBIAN_EVAL)
    residual = event_time(events, EVENT_FUNCTION_EVAL)
    pc_setup = event_time(events, EVENT_PC_SETUP)
    linear_solve = event_time(events, EVENT_KSP_SOLVE)
    lu_numeric = event_time(events, EVENT_LU_NUMERIC)
    lu_symbolic = event_time(events, EVENT_LU_SYMBOLIC)
    matrix_assembly = event_time(events, EVENT_MATRIX_ASSEMBLY_END)

    denominator = snes if snes > 0 else float(summary.get("wall_seconds") or 0)
    ratios = {
        "jacobian_vs_snes": jacobian / denominator if denominator else None,
        "residual_vs_snes": residual / denominator if denominator else None,
        "pc_setup_vs_snes": pc_setup / denominator if denominator else None,
        "linear_solve_vs_snes": linear_solve / denominator if denominator else None,
        "matrix_assembly_vs_snes": matrix_assembly / denominator if denominator else None,
    }

    candidates = {
        "JACOBIAN_EVALUATION_DOMINANT": jacobian,
        "DIRECT_FACTORIZATION_DOMINANT": pc_setup,
        "LINEAR_SOLVE_DOMINANT": linear_solve,
        "RESIDUAL_EVALUATION_DOMINANT": residual,
    }
    dominant, dominant_time = max(candidates.items(), key=lambda item: item[1])
    if not denominator or dominant_time / denominator < 0.35:
        dominant = "MIXED_PERFORMANCE_COST"

    secondary: list[str] = []
    if denominator:
        if pc_setup / denominator >= 0.20 and dominant != "DIRECT_FACTORIZATION_DOMINANT":
            secondary.append("DIRECT_FACTORIZATION_SIGNIFICANT")
        if residual / denominator >= 0.15 and dominant != "RESIDUAL_EVALUATION_DOMINANT":
            secondary.append("RESIDUAL_EVALUATION_SIGNIFICANT")

    metrics = summary.get("last_metrics_row") or {}

    def as_int(stem: str):
        value = _metric(metrics, stem, metric_prefix)
        return int(float(value)) if value is not None else None

    return {
        "classification": dominant,
        "secondary": secondary,
        "interpretable_performance": True,
        "label": summary.get("label"),
        "wall_seconds": summary.get("wall_seconds"),
        "dofs": as_int("num_dofs"),
        "nonlinear_iterations": as_int("nonlinear_iterations"),
        "linear_iterations": as_int("linear_iterations"),
        "residual_evaluations": as_int("residual_evaluations"),
        "petsc_seconds": {
            "snes_solve": snes,
            "jacobian_eval": jacobian,
            "residual_eval": residual,
            "pc_setup": pc_setup,
            "lu_numeric": lu_numeric,
            "lu_symbolic": lu_symbolic,
            "linear_solve": linear_solve,
            "matrix_assembly_end": matrix_assembly,
        },
        "ratios": ratios,
        "perfgraph_jacobian_self": perf_jacobian,
    }


def analyze(
    summary_path: Path,
    petsc_path: Path,
    perf_path: Path | None = None,
    *,
    metric_prefix: str | None = None,
) -> dict:
    """Compatibility entry: adapters decode raw files, analysis owns policy only."""
    summary = json.loads(summary_path.read_text())
    return analyze_decoded(
        summary,
        load_events(petsc_path),
        perfgraph_jacobian_self(perf_path),
        metric_prefix=metric_prefix,
    )


def self_test() -> int:
    try:
        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            summary = {
                "p2_returncode": 0,
                "p3_returncode": 0,
                "label": "synthetic",
                "wall_seconds": 10.0,
                "last_metrics_row": {
                    "qpxh_num_dofs": "42",
                    "qpxh_nonlinear_iterations": "2",
                    "qpxh_linear_iterations": "3",
                    "qpxh_residual_evaluations": "4",
                },
            }
            events = {
                EVENT_SNES_SOLVE: {"count": 1.0, "time": 10.0},
                EVENT_JACOBIAN_EVAL: {"count": 2.0, "time": 6.0},
                EVENT_FUNCTION_EVAL: {"count": 4.0, "time": 1.0},
                EVENT_PC_SETUP: {"count": 2.0, "time": 1.0},
                EVENT_KSP_SOLVE: {"count": 3.0, "time": 1.0},
            }
            perf = {"calls": 2.0, "self_seconds": 5.5, "avg_seconds": 2.75, "percent_application": 55.0}
            result = analyze_decoded(summary, events, perf)
            if result.get("classification") != "JACOBIAN_EVALUATION_DOMINANT" or result.get("dofs") != 42:
                raise AssertionError(result)
            failed = dict(summary)
            failed["p2_returncode"] = 1
            if analyze_decoded(failed, events).get("interpretable_performance") is not False:
                raise AssertionError("P2 failure mutation was accepted")
    except Exception as exc:
        print(f"QPX_PROFILE_ANALYSIS_SELFTEST: FAIL: {exc}")
        return 1
    print("QPX_PROFILE_ANALYSIS_SELFTEST: PASS")
    return 0


__all__ = ["analyze", "analyze_decoded", "self_test"]
