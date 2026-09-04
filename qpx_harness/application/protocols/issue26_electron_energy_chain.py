"""Declarative protocol adapter for Issue #26 E2b-E5 energy chain."""
from __future__ import annotations

from pathlib import Path

from qpx_harness.application.execution_options import experiment_results_root, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentSpec


def run_protocol(spec: ExperimentSpec) -> int:
    if spec.case_source is not None:
        raise ValueError("issue26-electron-energy-chain owns its canonical R4/A8 cases")
    qpx = spec.execution.get("qpx")
    timeout = positive_timeout(spec, default=240.0)

    from experiments.Issue26_electron_energy.E2b_E5_chain.run import run_energy_chain

    return int(
        run_energy_chain(
            qpx=qpx if isinstance(qpx, (str, Path)) else None,
            results_root=experiment_results_root(spec, qpx),
            timeout=timeout,
            parameters=spec.parameters,
        )
    )


__all__ = ["run_protocol"]
