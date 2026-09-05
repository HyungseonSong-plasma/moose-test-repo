"""Declarative protocol adapter for Issue #27 controlled wall reactions."""
from __future__ import annotations

from pathlib import Path

from qpx_harness.application.execution_options import experiment_results_root, positive_timeout
from qpx_harness.application.experiment_spec import ExperimentControl


def run_protocol(spec: ExperimentControl) -> int:
    if spec.case_source is not None:
        raise ValueError(
            "issue27-surface-reaction-controlled-wall owns its canonical controlled case"
        )
    qpx = spec.execution.get("qpx")
    timeout = positive_timeout(spec, default=120.0)

    wall_model = str(spec.parameters.get("wall_model", "prescribed"))
    if wall_model == "prescribed":
        from experiments.Issue27_surface_reactions.controlled_wall.run import run_controlled_wall
        runner = run_controlled_wall
    elif wall_model == "sticking":
        from experiments.Issue27_surface_reactions.controlled_wall.sticking import run_sticking_wall
        runner = run_sticking_wall
    elif wall_model == "sticking_all_walls":
        from experiments.Issue27_surface_reactions.controlled_wall.multiwall import run_multiwall_sticking
        runner = run_multiwall_sticking
    elif wall_model == "om_prescribed_control":
        from experiments.Issue27_surface_reactions.controlled_wall.om import run_om_wall_control
        runner = run_om_wall_control
    elif wall_model == "positive_ion_prescribed_control":
        from experiments.Issue27_surface_reactions.controlled_wall.positive import run_positive_ion_wall_control
        runner = run_positive_ion_wall_control
    elif wall_model == "excited_neutral_sticking_control":
        from experiments.Issue27_surface_reactions.controlled_wall.excited import run_excited_neutral_wall_control
        runner = run_excited_neutral_wall_control
    elif wall_model == "combined_comsol_wall_control":
        from experiments.Issue27_surface_reactions.controlled_wall.combined import run_combined_comsol_wall_control
        runner = run_combined_comsol_wall_control
    elif wall_model == "comsol_electron_thermal_wall_control":
        from experiments.Issue27_surface_reactions.controlled_wall.electron_wall_stable import run_comsol_electron_thermal_wall_control
        runner = run_comsol_electron_thermal_wall_control
    elif wall_model == "finite_see_control":
        from experiments.Issue27_surface_reactions.controlled_wall.see import run_finite_see_control
        runner = run_finite_see_control
    elif wall_model == "charged_prescribed_ledger":
        from experiments.Issue27_surface_reactions.controlled_wall.charged import run_charged_wall_ledger
        runner = run_charged_wall_ledger
    else:
        raise ValueError(
            "issue27-surface-reaction-controlled-wall supports wall_model in "
            "{'prescribed', 'sticking', 'sticking_all_walls', "
            "'om_prescribed_control', 'positive_ion_prescribed_control', "
            "'excited_neutral_sticking_control', 'combined_comsol_wall_control', "
            "'comsol_electron_thermal_wall_control', 'finite_see_control', "
            "'charged_prescribed_ledger'}"
        )

    return int(
        runner(
            qpx=qpx if isinstance(qpx, (str, Path)) else None,
            results_root=experiment_results_root(spec, qpx),
            timeout=timeout,
            parameters=spec.parameters,
        )
    )


__all__ = ["run_protocol"]
