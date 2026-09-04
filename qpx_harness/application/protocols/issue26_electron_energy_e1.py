"""Declarative protocol adapter for Issue #26 E1 electron-energy control."""
from __future__ import annotations

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
        raise ValueError("issue26-electron-energy-e1 owns its canonical R4-QF1 case")
    qpx = spec.execution.get("qpx")
    timeout = float(spec.execution.get("timeout_seconds", 180.0))
    if timeout <= 0.0:
        raise ValueError("execution.timeout_seconds must be positive")
    from experiments.Issue26_electron_energy.E1_zero_source.run import run_e1_zero_source

    return int(
        run_e1_zero_source(
            qpx=qpx if isinstance(qpx, (str, Path)) else None,
            results_root=_results_root(spec, qpx),
            timeout=timeout,
            parameters=spec.parameters,
        )
    )


__all__ = ["run_protocol"]
