"""MOOSE-specific performance profile configuration and raw timing decoding."""
from __future__ import annotations

import csv
import re
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


def write_overlay(path: Path, metrics_base: Path, *, prefix: str = "qpxh", nl_max_its: int | None = None, abort_on_solve_fail: bool = False) -> str:
    bounded = build_bounded_executioner_overlay(nl_max_its=nl_max_its, abort_on_solve_fail=abort_on_solve_fail)
    path.write_text(f"""# Generated QPX profiling overlay.
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

{bounded}""")
    return bounded


def find_metrics_csv(metrics_base: Path) -> Path | None:
    direct = Path(str(metrics_base) + ".csv")
    if direct.is_file():
        return direct
    matches = sorted(metrics_base.parent.glob(metrics_base.name + "*.csv"))
    return matches[0] if matches else None


def read_last_metrics_row(csv_path: Path | None) -> dict[str, str] | None:
    if csv_path is None or not csv_path.is_file():
        return None
    try:
        with csv_path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return None
    return rows[-1] if rows else None


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
        "calls": float(calls), "self_seconds": float(self_s),
        "avg_seconds": float(avg_s), "percent_application": float(percent),
    }

__all__ = ["build_bounded_executioner_overlay", "find_metrics_csv", "perfgraph_jacobian_self", "read_last_metrics_row", "write_overlay"]
