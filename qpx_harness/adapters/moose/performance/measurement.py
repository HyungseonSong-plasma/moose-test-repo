"""MOOSE-specific performance measurement overlay construction."""
from __future__ import annotations

from pathlib import Path


def _quote_hit_path(path: Path) -> str:
    text = str(path)
    if "'" in text:
        raise ValueError(f"output path contains unsupported single quote: {path}")
    return f"'{text}'"


def build_bounded_executioner_overlay(*, nl_max_its: int | None = None, abort_on_solve_fail: bool = False) -> str:
    if nl_max_its is not None and nl_max_its <= 0:
        raise ValueError("nl_max_its must be a positive integer")
    if nl_max_its is None and not abort_on_solve_fail:
        return ""
    lines = ["[Executioner]"]
    if nl_max_its is not None:
        lines.append(f"  nl_max_its = {nl_max_its}")
    if abort_on_solve_fail:
        lines.append("  abort_on_solve_fail = true")
    lines.append("[]")
    return "\n".join(lines) + "\n"


def write_profile_overlay(path: Path, metrics_base: Path, *, prefix: str = "qpxh", nl_max_its: int | None = None, abort_on_solve_fail: bool = False) -> str:
    """Write MOOSE HIT diagnostics for a bounded profile without physics changes."""
    bounded = build_bounded_executioner_overlay(nl_max_its=nl_max_its, abort_on_solve_fail=abort_on_solve_fail)
    path.write_text(
        f"""# Generated QPX profiling overlay.
# Diagnostics only: no physics, dt, tolerance, or solver-type changes.
# Optional bounded Executioner settings only limit diagnostic work.

[Postprocessors]
  [{prefix}_num_dofs]
    type = NumDOFs
    system = NL
    execute_on = 'initial timestep_end'
  []
  [{prefix}_nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = timestep_end
  []
  [{prefix}_linear_iterations]
    type = NumLinearIterations
    execute_on = timestep_end
  []
  [{prefix}_residual_evaluations]
    type = NumResidualEvaluations
    execute_on = timestep_end
  []
[]

[Outputs]
  [{prefix}_perfgraph]
    type = PerfGraphOutput
    execute_on = final
    level = 3
    heaviest_branch = true
    heaviest_sections = 40
  []
  [{prefix}_metrics]
    type = CSV
    file_base = {_quote_hit_path(metrics_base)}
    show = '{prefix}_num_dofs {prefix}_nonlinear_iterations {prefix}_linear_iterations {prefix}_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]

{bounded}"""
    )
    return bounded


def write_measurement_overlay(path: Path, *, metrics_base: Path, perfgraph_base: Path | None, prefix: str = "qpxperf") -> None:
    """Write the MOOSE measurement overlay used by the generic measurement runner."""
    if perfgraph_base is not None:
        outputs = f"""
[Reporters]
  [{prefix}_perf_graph]
    type = PerfGraphReporter
    execute_on = FINAL
  []
[]

[Outputs]
  [{prefix}_perf_json]
    type = JSON
    execute_on = FINAL
    file_base = {_quote_hit_path(perfgraph_base)}
  []
  [{prefix}_metrics]
    type = CSV
    file_base = {_quote_hit_path(metrics_base)}
    show = '{prefix}_num_dofs {prefix}_nonlinear_iterations {prefix}_linear_iterations {prefix}_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]
"""
    else:
        outputs = f"""
[Outputs]
  [{prefix}_metrics]
    type = CSV
    file_base = {_quote_hit_path(metrics_base)}
    show = '{prefix}_num_dofs {prefix}_nonlinear_iterations {prefix}_linear_iterations {prefix}_residual_evaluations'
    execute_on = 'initial timestep_end'
  []
[]
"""
    path.write_text(f"""# Generated QPX performance measurement overlay.
# Diagnostics only: no physics coefficient, dt, tolerance, BC, or solver change.

[Postprocessors]
  [{prefix}_num_dofs]
    type = NumDOFs
    system = NL
    execute_on = 'initial timestep_end'
  []
  [{prefix}_nonlinear_iterations]
    type = NumNonlinearIterations
    execute_on = timestep_end
  []
  [{prefix}_linear_iterations]
    type = NumLinearIterations
    execute_on = timestep_end
  []
  [{prefix}_residual_evaluations]
    type = NumResidualEvaluations
    execute_on = timestep_end
  []
[]
{outputs}""")


__all__ = ["build_bounded_executioner_overlay", "write_measurement_overlay", "write_profile_overlay"]
