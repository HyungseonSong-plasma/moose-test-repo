"""Deterministic PETSc/MOOSE performance-evidence analysis."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


def load_petsc_events(path: Path) -> dict[str, dict[str, float]]:
    events: dict[str, dict[str, float]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("Rank") not in (None, "", "0"):
                continue
            name = row.get("Event Name", "")
            if not name:
                continue
            try:
                events[name] = {
                    "count": float(row.get("Count") or 0),
                    "time": float(row.get("Time") or 0),
                }
            except ValueError:
                continue
    return events


def perfgraph_jacobian_self(path: Path | None) -> dict[str, float] | None:
    if path is None or not path.is_file():
        return None
    text = path.read_text(errors="replace")
    pattern = re.compile(
        r"^\|\s*NonlinearSystemBase::computeJacobianInternal\s*"
        r"\|\s*(\d+)\s*\|\s*([0-9.eE+-]+)\s*\|\s*([0-9.eE+-]+)\s*"
        r"\|\s*([0-9.eE+-]+)\s*\|",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        return None
    calls, self_s, avg_s, percent = max(matches, key=lambda match: float(match[1]))
    return {
        "calls": float(calls),
        "self_seconds": float(self_s),
        "avg_seconds": float(avg_s),
        "percent_application": float(percent),
    }


def event_time(events: dict[str, dict[str, float]], name: str) -> float:
    return events.get(name, {}).get("time", 0.0)


def _metric(metrics: dict, stem: str, prefix: str | None) -> str | None:
    candidates = []
    if prefix:
        candidates.append(f"{prefix}_{stem}")
    candidates.extend((f"qpxh_{stem}", f"r32_{stem}", stem))
    for key in candidates:
        if metrics.get(key) not in (None, ""):
            return metrics[key]
    return None


def analyze(
    summary_path: Path,
    petsc_path: Path,
    perf_path: Path | None = None,
    *,
    metric_prefix: str | None = None,
) -> dict:
    summary = json.loads(summary_path.read_text())
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

    events = load_petsc_events(petsc_path)
    snes = event_time(events, "SNESSolve")
    jacobian = event_time(events, "SNESJacobianEval")
    residual = event_time(events, "SNESFunctionEval")
    pc_setup = event_time(events, "PCSetUp")
    linear_solve = event_time(events, "KSPSolve")
    lu_numeric = event_time(events, "MatLUFactorNum")
    lu_symbolic = event_time(events, "MatLUFactorSym")
    matrix_assembly = event_time(events, "MatAssemblyEnd")
    perf_jacobian = perfgraph_jacobian_self(perf_path)

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
