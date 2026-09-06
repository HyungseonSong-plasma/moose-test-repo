"""Backend-neutral bottleneck analysis of decoded performance facts."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qpx_harness.adapters.moose.performance.profile import jacobian_self_time
from qpx_harness.adapters.petsc.performance import decode_timing_facts


def _metric(metrics: dict, stem: str, prefix: str | None) -> str | None:
    candidates = [f"{prefix}_{stem}"] if prefix else []
    candidates.extend((f"qpxh_{stem}", f"r32_{stem}", stem))
    for key in candidates:
        if metrics.get(key) not in (None, ""):
            return metrics[key]
    return None


def analyze_facts(
    summary: dict,
    timings: dict[str, float],
    perf_jacobian: dict[str, float] | None = None,
    *,
    metric_prefix: str | None = None,
) -> dict:
    """Classify already-decoded performance facts without external-format knowledge."""
    if summary.get("p2_returncode") != 0:
        return {"classification": summary.get("classification", "HARNESS_OR_CONSTRUCTION_FAIL"), "interpretable_performance": False, "reason": "P2 did not pass."}
    if summary.get("p3_returncode") != 0:
        return {"classification": "RUNTIME_FAIL_OR_NONCONVERGENCE", "interpretable_performance": False, "reason": "P3 did not complete successfully."}

    snes = timings.get("snes_solve", 0.0)
    jacobian = timings.get("jacobian_eval", 0.0)
    residual = timings.get("residual_eval", 0.0)
    pc_setup = timings.get("pc_setup", 0.0)
    linear_solve = timings.get("linear_solve", 0.0)
    matrix_assembly = timings.get("matrix_assembly_end", 0.0)
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
        if pc_setup / denominator >= 0.20 and dominant != "DIRECT_FACTORIZATION_DOMINANT": secondary.append("DIRECT_FACTORIZATION_SIGNIFICANT")
        if residual / denominator >= 0.15 and dominant != "RESIDUAL_EVALUATION_DOMINANT": secondary.append("RESIDUAL_EVALUATION_SIGNIFICANT")
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
        "petsc_seconds": dict(timings),
        "ratios": ratios,
        "perfgraph_jacobian_self": perf_jacobian,
    }


def analyze(summary_path: Path, petsc_path: Path, perf_path: Path | None = None, *, metric_prefix: str | None = None) -> dict:
    """Compatibility use-case wrapper; raw decoding is delegated to adapter owners."""
    return analyze_facts(
        json.loads(summary_path.read_text()),
        decode_timing_facts(petsc_path),
        jacobian_self_time(perf_path),
        metric_prefix=metric_prefix,
    )


def self_test() -> int:
    try:
        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name); summary = root / "summary.json"; petsc = root / "petsc.csv"; perf = root / "perfgraph.log"
            summary.write_text(json.dumps({"p2_returncode": 0, "p3_returncode": 0, "label": "synthetic", "wall_seconds": 10.0, "last_metrics_row": {"qpxh_num_dofs": "42", "qpxh_nonlinear_iterations": "2", "qpxh_linear_iterations": "3", "qpxh_residual_evaluations": "4"}}))
            petsc.write_text("Event Name,Rank,Count,Time\nSNESSolve,0,1,10\nSNESJacobianEval,0,2,6\nSNESFunctionEval,0,4,1\nPCSetUp,0,2,1\nKSPSolve,0,3,1\n")
            perf.write_text("| NonlinearSystemBase::computeJacobianInternal | 2 | 5.5 | 2.75 | 55 |\n")
            result = analyze(summary, petsc, perf)
            if result.get("classification") != "JACOBIAN_EVALUATION_DOMINANT" or result.get("dofs") != 42: raise AssertionError(result)
            if result.get("perfgraph_jacobian_self", {}).get("self_seconds") != 5.5: raise AssertionError("MOOSE decoder contract drift")
            failed = json.loads(summary.read_text()); failed["p2_returncode"] = 1; summary.write_text(json.dumps(failed))
            if analyze(summary, petsc).get("interpretable_performance") is not False: raise AssertionError("P2 failure mutation was accepted")
    except Exception as exc:
        print(f"QPX_PROFILE_ANALYSIS_SELFTEST: FAIL: {exc}"); return 1
    print("QPX_PROFILE_ANALYSIS_SELFTEST: PASS"); return 0


__all__ = ["analyze", "analyze_facts", "self_test"]
