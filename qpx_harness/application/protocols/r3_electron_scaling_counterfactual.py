"""Declarative adapter for the R3 electron-density scaling counterfactual."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from qpx_harness.application.experiment_spec import ExperimentSpec
from qpx_harness.execution.runtime import resolve_executable


def _results_root(spec: ExperimentSpec, qpx: object) -> Path:
    configured = spec.execution.get("results_root")
    if configured not in (None, ""):
        if not isinstance(configured, (str, Path)):
            raise ValueError("execution.results_root must be path-like")
        return spec.resolve_path(configured)
    executable = resolve_executable(qpx if isinstance(qpx, (str, Path)) else None)
    return executable.parent / "temp" / "results"


def run_protocol(spec: ExperimentSpec) -> int:
    if spec.case_source is not None:
        raise ValueError("r3-electron-scaling-counterfactual owns its bounded N0/N1/N2 matrix")
    qpx = spec.execution.get("qpx")
    args = Namespace(
        qpx=qpx,
        results_root=_results_root(spec, qpx),
        timeout=float(spec.execution.get("timeout_seconds", 120.0)),
    )
    if args.timeout <= 0:
        raise ValueError("timeout must be positive")
    from experiments.R3_electron_scaling_counterfactual.run import run
    return int(run(args))


__all__ = ["run_protocol"]
