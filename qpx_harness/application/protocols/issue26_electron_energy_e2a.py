"""Declarative protocol adapter for Issue #26 E2a energy diffusion control."""
from __future__ import annotations

from pathlib import Path

from qpx_harness.application.execution_options import experiment_results_root, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentControl


def run_protocol(spec: ExperimentControl) -> int:
    if spec.case_source is not None:
        raise ValueError("issue26-electron-energy-e2a owns its canonical R4-QF1 case")
    qpx = spec.execution.get("qpx")
    timeout = positive_timeout(spec, default=180.0)
    from experiments.Issue26_electron_energy.E2a_controlled_diffusion.run import (
        run_e2a_controlled_diffusion,
    )

    return int(
        run_e2a_controlled_diffusion(
            qpx=qpx if isinstance(qpx, (str, Path)) else None,
            results_root=experiment_results_root(spec, qpx),
            timeout=timeout,
            parameters=spec.parameters,
        )
    )


__all__ = ["run_protocol"]
