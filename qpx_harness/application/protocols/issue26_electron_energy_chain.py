"""Declarative protocol adapter for Issue #26 E2b-E5 energy chain."""
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
        raise ValueError("issue26-electron-energy-chain owns its canonical R4/A8 cases")
    qpx = spec.execution.get("qpx")
    timeout = float(spec.execution.get("timeout_seconds", 240.0))
    if timeout <= 0.0:
        raise ValueError("execution.timeout_seconds must be positive")

    from experiments.Issue26_electron_energy.E2b_E5_chain.run import run_energy_chain

    return int(
        run_energy_chain(
            qpx=qpx if isinstance(qpx, (str, Path)) else None,
            results_root=_results_root(spec, qpx),
            timeout=timeout,
            parameters=spec.parameters,
        )
    )


__all__ = ["run_protocol"]
