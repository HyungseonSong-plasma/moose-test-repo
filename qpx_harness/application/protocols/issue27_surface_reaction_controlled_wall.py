"""Declarative protocol adapter for Issue #27 controlled wall reactions."""
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
        raise ValueError(
            "issue27-surface-reaction-controlled-wall owns its canonical controlled case"
        )
    qpx = spec.execution.get("qpx")
    timeout = float(spec.execution.get("timeout_seconds", 120.0))
    if timeout <= 0.0:
        raise ValueError("execution.timeout_seconds must be positive")

    wall_model = str(spec.parameters.get("wall_model", "prescribed"))
    if wall_model == "prescribed":
        from experiments.Issue27_surface_reactions.controlled_wall.run import (
            run_controlled_wall,
        )

        runner = run_controlled_wall
    elif wall_model == "sticking":
        from experiments.Issue27_surface_reactions.controlled_wall.sticking import (
            run_sticking_wall,
        )

        runner = run_sticking_wall
    elif wall_model == "sticking_all_walls":
        from experiments.Issue27_surface_reactions.controlled_wall.multiwall import (
            run_multiwall_sticking,
        )

        runner = run_multiwall_sticking
    elif wall_model == "om_prescribed_control":
        from experiments.Issue27_surface_reactions.controlled_wall.om import (
            run_om_wall_control,
        )

        runner = run_om_wall_control
    elif wall_model == "positive_ion_prescribed_control":
        from experiments.Issue27_surface_reactions.controlled_wall.positive import (
            run_positive_ion_wall_control,
        )

        runner = run_positive_ion_wall_control
    elif wall_model == "excited_neutral_sticking_control":
        from experiments.Issue27_surface_reactions.controlled_wall.excited import (
            run_excited_neutral_wall_control,
        )

        runner = run_excited_neutral_wall_control
    elif wall_model == "combined_comsol_wall_control":
        from experiments.Issue27_surface_reactions.controlled_wall.combined import (
            run_combined_comsol_wall_control,
        )

        runner = run_combined_comsol_wall_control
    elif wall_model == "comsol_electron_thermal_wall_control":
        from experiments.Issue27_surface_reactions.controlled_wall.electron_wall import (
            run_comsol_electron_thermal_wall_control,
        )

        runner = run_comsol_electron_thermal_wall_control
    elif wall_model == "charged_prescribed_ledger":
        from experiments.Issue27_surface_reactions.controlled_wall.charged import (
            run_charged_wall_ledger,
        )

        runner = run_charged_wall_ledger
    else:
        raise ValueError(
            "issue27-surface-reaction-controlled-wall supports wall_model in "
            "{'prescribed', 'sticking', 'sticking_all_walls', "
            "'om_prescribed_control', 'positive_ion_prescribed_control', "
            "'excited_neutral_sticking_control', 'combined_comsol_wall_control', "
            "'comsol_electron_thermal_wall_control', 'charged_prescribed_ledger'}"
        )

    return int(
        runner(
            qpx=qpx if isinstance(qpx, (str, Path)) else None,
            results_root=_results_root(spec, qpx),
            timeout=timeout,
            parameters=spec.parameters,
        )
    )


__all__ = ["run_protocol"]
