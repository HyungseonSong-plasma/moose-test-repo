#!/usr/bin/env python3
"""Promote the validated 100 ns cover-only pilot to the accepted 15 us staged time grid."""
from __future__ import annotations

import argparse
from pathlib import Path

OLD_EXECUTIONER = """[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = 1.0e-9
  num_steps = 100
  end_time = 1.0e-7
  line_search = bt
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  nl_max_its = 100
  l_tol = 1e-10
  l_max_its = 20
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = false
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
  petsc_options_value = 'preonly lu NONZERO'
[]"""


def accepted_time_sequence() -> list[float]:
    times = [0.0]
    times.extend(i * 1.0e-9 for i in range(1, 101))
    t = times[-1]
    times.extend(t + i * 1.0e-8 for i in range(1, 91))
    t = times[-1]
    times.extend(t + i * 1.0e-7 for i in range(1, 91))
    t = times[-1]
    times.extend(t + i * 1.0e-6 for i in range(1, 6))
    if len(times) != 286 or abs(times[-1] - 1.5e-5) > 1.0e-18:
        raise RuntimeError("accepted 15 us time sequence construction failed")
    return times


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    if text.count(OLD_EXECUTIONER) != 1:
        raise RuntimeError("expected exactly one validated 100 ns Executioner block")

    times = accepted_time_sequence()
    seq = " ".join(format(t, ".17g") for t in times)
    new_executioner = f"""[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  end_time = 1.5e-5
  [TimeStepper]
    type = TimeSequenceStepper
    time_sequence = '{seq}'
  []
  line_search = bt
  nl_rel_tol = 1e-8
  nl_abs_tol = 1e-10
  nl_max_its = 100
  l_tol = 1e-10
  l_max_its = 20
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = false
  petsc_options = '-snes_converged_reason -ksp_converged_reason'
  petsc_options_iname = '-ksp_type -pc_type -pc_factor_shift_type'
  petsc_options_value = 'preonly lu NONZERO'
[]"""

    args.input.write_text(text.replace(OLD_EXECUTIONER, new_executioner, 1), encoding="utf-8")
    print(
        "COVER_15US_PROMOTION_PASS "
        f"time_points={len(times)} solves={len(times)-1} final_time_s={times[-1]:.16g}"
    )


if __name__ == "__main__":
    main()
