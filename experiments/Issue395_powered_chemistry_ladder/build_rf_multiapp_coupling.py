#!/usr/bin/env python3
"""Build Issue #395 single-execution plasma<->Maxwell MultiApp coupling.

Parent: transient plasma + EI02 elastic.
Child: fresh FullSolveMultiApp frequency-domain Maxwell solve at each TIMESTEP_BEGIN.
No external probe, rollback, checkpoint/recover, or per-step process restart is used.
RF starts at half of the validated 1000 W calibration (coil amplitude scaled by sqrt(0.5));
accepted-step PID feedback then drives the parent plasma absorbed power toward 1000 W.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
T6 = ROOT / "experiments" / "Issue376_maxwell_plasma_rf_transfer"
sys.path.insert(0, str(T6))
import build_t6_overlays_v2 as v2  # noqa: E402

BASELINE_1000W_DRIVE = 7.49559809637885
SOFT_START_POWER_FRACTION = 0.5
INITIAL_DRIVE = BASELINE_1000W_DRIVE * math.sqrt(SOFT_START_POWER_FRACTION)


def remove_top_section(text: str, header: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
    if start is None:
        raise RuntimeError(f"missing section {header}")
    depth = 0
    end = None
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if s.startswith("[") and s.endswith("]") and s != "[]":
            depth += 1
        elif s == "[]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f"unterminated section {header}")
    return "".join(lines[:start] + lines[end:])


def remove_named_block(text: str, name: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.strip() == f"[{name}]"), None)
    if start is None:
        raise RuntimeError(f"missing block {name}")
    depth = 0
    end = None
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if s.startswith("[") and s.endswith("]") and s != "[]":
            depth += 1
        elif s == "[]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f"unterminated block {name}")
    return "".join(lines[:start] + lines[end:])


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, found {n}")
    return text.replace(old, new, 1)


def build_parent(x: list[float], mu_n: list[float], child_path: str, target_w: float, kp: float) -> str:
    text = v2.plasma_overlay(x, mu_n)
    text = replace_once(
        text,
        "maxwell_solution_file_t6 = 'results_t6/seed/maxwell.e'\n",
        "",
        "external Maxwell file parameter",
    )
    text = replace_once(text, "source_enable_t6 = 0.0\n", "source_enable_t6 = 1.0\n", "RF activation")
    text = remove_top_section(text, "[UserObjects]")
    text = remove_named_block(text, "map_E_real_t6")
    text = remove_named_block(text, "map_E_imag_t6")

    pp_insert = f"""[Postprocessors]
  [rf_drive_scale_t6]
    type = Receiver
    default = {INITIAL_DRIVE:.17g}
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [P_abs_maxwell_t6]
    type = Receiver
    default = {target_w:.17g}
    execute_on = 'INITIAL TIMESTEP_BEGIN TIMESTEP_END'
  []
"""
    text = replace_once(text, "[Postprocessors]\n", pp_insert, "parent receiver postprocessors")

    coupling = f"""
[MultiApps]
  [maxwell_t6]
    type = FullSolveMultiApp
    input_files = '{child_path}'
    cli_args = 'Outputs/exodus=false;Outputs/csv=false'
    execute_on = TIMESTEP_BEGIN
    no_restore = true
  []
[]

[Transfers]
  [drive_to_maxwell_t6]
    type = MultiAppPostprocessorTransfer
    to_multi_app = maxwell_t6
    from_postprocessor = rf_drive_scale_t6
    to_postprocessor = rf_drive_scale_child
    execute_on = SAME_AS_MULTIAPP
  []
  [ne_to_maxwell_t6]
    type = MultiAppGeneralFieldShapeEvaluationTransfer
    to_multi_app = maxwell_t6
    source_variable = electron_density_rf_state_t6
    variable = electron_density_state_t6
    from_blocks = plasma
    to_blocks = plasma
    execute_on = SAME_AS_MULTIAPP
  []
  [mean_en_to_maxwell_t6]
    type = MultiAppGeneralFieldShapeEvaluationTransfer
    to_multi_app = maxwell_t6
    source_variable = mean_energy_rf_state_t6
    variable = mean_energy_state_t6
    from_blocks = plasma
    to_blocks = plasma
    execute_on = SAME_AS_MULTIAPP
  []
  [pressure_to_maxwell_t6]
    type = MultiAppGeneralFieldShapeEvaluationTransfer
    to_multi_app = maxwell_t6
    source_variable = pressure_rf_state_t6
    variable = pressure_state_t6
    from_blocks = plasma
    to_blocks = plasma
    execute_on = SAME_AS_MULTIAPP
  []
  [E_real_from_maxwell_t6]
    type = MultiAppGeneralFieldShapeEvaluationTransfer
    from_multi_app = maxwell_t6
    source_variable = E_real
    variable = E_real_rf_t6
    from_blocks = plasma
    to_blocks = plasma
    execute_on = SAME_AS_MULTIAPP
  []
  [E_imag_from_maxwell_t6]
    type = MultiAppGeneralFieldShapeEvaluationTransfer
    from_multi_app = maxwell_t6
    source_variable = E_imag
    variable = E_imag_rf_t6
    from_blocks = plasma
    to_blocks = plasma
    execute_on = SAME_AS_MULTIAPP
  []
  [P_abs_from_maxwell_t6]
    type = MultiAppPostprocessorTransfer
    from_multi_app = maxwell_t6
    from_postprocessor = P_abs
    to_postprocessor = P_abs_maxwell_t6
    reduction_type = average
    execute_on = SAME_AS_MULTIAPP
  []
[]

[Controls]
  [rf_drive_pid_t6]
    type = PIDTransientControl
    postprocessor = P_rf_raw_W_t6
    target = {target_w:.17g}
    parameter_pp = rf_drive_scale_t6
    K_integral = 0
    K_proportional = {kp:.17g}
    K_derivative = 0
    minimum_output_value = 3.0
    maximum_output_value = 12.0
    execute_on = TIMESTEP_END
  []
[]

"""
    text = replace_once(text, "[Outputs]\n", coupling + "[Outputs]\n", "parent MultiApp coupling")

    forbidden = ("maxwell_solution_file_t6", "SolutionUserObject", "map_E_real_t6", "map_E_imag_t6")
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"external-file coupling remains in parent: {token}")
    for token in ("FullSolveMultiApp", "P_abs_from_maxwell_t6", "rf_drive_pid_t6", "postprocessor = P_rf_raw_W_t6"):
        if token not in text:
            raise RuntimeError(f"parent MultiApp coupling missing {token}")
    return text


def build_child(x: list[float], mu_n: list[float]) -> str:
    text = v2.maxwell_overlay(x, mu_n)
    text = replace_once(
        text,
        "plasma_solution_file_t6 = 'results_t6/bootstrap/state100ns.e'\n",
        "",
        "external plasma file parameter",
    )
    text = remove_top_section(text, "[UserObjects]")
    text = remove_top_section(text, "[AuxKernels]")
    text = replace_once(
        text,
        "  [electron_density_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n",
        "  [electron_density_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n    initial_condition = 1.0e15\n  []\n",
        "child electron-density safe initial value",
    )
    text = replace_once(
        text,
        "  [mean_energy_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n  []\n",
        "  [mean_energy_state_t6]\n    family = LAGRANGE\n    order = FIRST\n    block = plasma\n    initial_condition = 4.0\n  []\n",
        "child mean-energy safe initial value",
    )
    text = replace_once(
        text,
        "  [pressure_state_t6]\n    family = MONOMIAL\n    order = CONSTANT\n    block = plasma\n  []\n",
        "  [pressure_state_t6]\n    family = MONOMIAL\n    order = CONSTANT\n    block = plasma\n    initial_condition = 1.3322\n  []\n",
        "child pressure safe initial value",
    )

    child_patch = f"""
[Postprocessors]
  [rf_drive_scale_child]
    type = Receiver
    default = {INITIAL_DRIVE:.17g}
  []
[]

[Kernels]
  [coil1_current]
    postprocessor = rf_drive_scale_child
  []
  [coil2_current]
    postprocessor = rf_drive_scale_child
  []
  [coil3_current]
    postprocessor = rf_drive_scale_child
  []
[]
"""
    text += child_patch
    for token in ("plasma_solution_file_t6", "SolutionUserObject", "SolutionAux"):
        if token in text:
            raise RuntimeError(f"external-file coupling remains in child: {token}")
    for token in ("electron_density_state_t6", "mean_energy_state_t6", "pressure_state_t6", "rf_drive_scale_child"):
        if token not in text:
            raise RuntimeError(f"child transfer target missing {token}")
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--parent-overlay", type=Path, required=True)
    ap.add_argument("--child-overlay", type=Path, required=True)
    ap.add_argument("--child-input", type=Path, required=True)
    ap.add_argument("--target-w", type=float, default=1000.0)
    ap.add_argument("--kp", type=float, default=-5.0e-4)
    a = ap.parse_args()
    if a.target_w <= 0:
        raise RuntimeError("target power must be positive")
    if a.kp >= 0:
        raise RuntimeError("Kp must be negative")

    x, mu_n = v2.v1.table(a.table)
    child_path = a.child_input.name
    a.parent_overlay.write_text(build_parent(x, mu_n, child_path, a.target_w, a.kp), encoding="utf-8")
    a.child_overlay.write_text(build_child(x, mu_n), encoding="utf-8")
    wrapper = (
        "!include ../Issue202_maxwell_scalar_fem_m0/rf_power.i\n"
        f"!include {a.child_overlay.name}\n"
    )
    a.child_input.write_text(wrapper, encoding="utf-8")
    print(
        "ISSUE395_RF_MULTIAPP_BUILD_PASS "
        f"target_W={a.target_w:.9g} Kp={a.kp:.9g} initial_drive={INITIAL_DRIVE:.15g} "
        f"soft_start_power_fraction={SOFT_START_POWER_FRACTION:.9g} feedback_sensor=P_rf_raw_W_t6 "
        "parent=transient_plasma child=FullSolveMultiApp_Maxwell "
        "probe=false rollback=false recover=false external_solution_file=false"
    )


if __name__ == "__main__":
    main()
