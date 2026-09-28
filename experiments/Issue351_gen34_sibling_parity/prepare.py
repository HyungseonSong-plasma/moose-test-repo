#!/usr/bin/env python3
"""Transform the already-qualified PlasmaClosures Gen34 lane into frozen-heavy sibling Gummel.

Baseline input must come from Issue337 plasma_closures full-horizon generation at
qualification head c9726d45e912f2476958d580c88e3421b5d4868b. Closure construction,
physics kernels, BCs, clocks, band-5 response and output policy remain unchanged;
only the MultiApp topology is refactored.
"""
from __future__ import annotations
import argparse
import shutil
import re
from pathlib import Path


def remove_block(text: str, header: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        raise RuntimeError(f"missing block {header}")
    depth = 0
    end = None
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]") and stripped != "[]":
            depth += 1
        elif stripped == "[]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f"unterminated block {header}")
    return "".join(lines[:start] + lines[end:])


def remove_subblock(text: str, name: str) -> str:
    return remove_block(text, f"[{name}]")


def insert_before(text: str, marker: str, payload: str) -> str:
    if text.count(marker) != 1:
        raise RuntimeError(f"marker count for {marker!r}: {text.count(marker)}")
    return text.replace(marker, payload.rstrip() + "\n\n" + marker, 1)


def transform_parent(src: str) -> str:
    old_multi = """[MultiApps]
  [electron]
    type = TransientMultiApp
    input_files = 'fast_sub.i'
    execute_on = TIMESTEP_END
    sub_cycling = true
    output_sub_cycles = true
    print_sub_cycles = false
  []
[]
"""
    new_multi = """[MultiApps]
  [gummel_driver]
    type = TransientMultiApp
    input_files = 'gummel_driver.i'
    execute_on = TIMESTEP_END
    sub_cycling = true
    output_sub_cycles = true
    print_sub_cycles = false
  []
[]
"""
    if src.count(old_multi) != 1:
        raise RuntimeError("parent MultiApps anchor changed")
    src = src.replace(old_multi, new_multi, 1)
    src = src.replace("to_multi_app = electron", "to_multi_app = gummel_driver", 1)
    src = src.replace("from_multi_app = electron", "from_multi_app = gummel_driver", 1)
    return src


def transform_electron(src: str) -> str:
    # The accepted migrated lane already owns electron PlasmaClosures.  Move
    # only its Gummel orchestration into the dedicated driver.
    src = remove_block(src, "[GummelIteration]")

    drop = {
        "fixed_point_algorithm",
        "transformed_variables",
        "multiapp_fixed_point_convergence",
        "fixed_point_min_its",
        "fixed_point_max_its",
        "fixed_point_rel_tol",
        "fixed_point_abs_tol",
        "accept_on_max_fixed_point_iteration",
    }
    lines = []
    for line in src.splitlines(keepends=True):
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in drop:
            continue
        lines.append(line)
    return "".join(lines)


def transform_poisson(src: str) -> str:
    # Charge PlasmaClosures and band-5 Poisson response were already qualified;
    # topology migration must not alter them.
    return src


def _executioner_value(text: str, key: str) -> str:
    m = re.search(rf"^  {re.escape(key)}\\s*=\\s*(.+?)\\s*$", text, re.MULTILINE)
    if not m:
        raise RuntimeError(f"missing Executioner parameter {key}")
    return m.group(1)


def driver_input(electron_src: str) -> str:
    clock = {
        key: _executioner_value(electron_src, key)
        for key in ("dt", "dtmin", "dtmax", "end_time", "num_steps", "timestep_tolerance")
    }
    return f"""[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 20
  xmin = 0.0
  xmax = 0.01
[]

[Problem]
  solve = false
  kernel_coverage_check = false
[]

[AuxVariables]
  [w_O2p_h]
    type = MooseVariableFVReal
    initial_condition = 3.8523381586724929e-05
  []
  [w_Om_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [w_Op_h]
    type = MooseVariableFVReal
    initial_condition = 0.001
  []
  [potential_from_poisson]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [electron_density_out]
    type = MooseVariableFVReal
    initial_condition = 10000000000000000
  []
  [mean_energy_out]
    type = MooseVariableFVReal
    initial_condition = 5.73276
  []
  [fp_phi_anchor_diag]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[FunctorMaterials]
  [fp_delta_phi_abs]
    type = ADParsedFunctorMaterial
    property_name = fp_delta_phi_abs
    functor_names = 'potential_from_poisson fp_phi_anchor_diag'
    functor_symbols = 'phi phi0'
    expression = 'abs(phi-phi0)'
  []
[]

[GummelIteration]
  [electron_poisson]
    electron_multiapp = electron
    electron_input_file = electron_sub.i
    poisson_multiapp = poisson
    poisson_input_file = poisson_sub.i

    electron_density_variable = log_e
    poisson_electron_density_variable = log_e_frozen
    electron_to_poisson_source_variables = 'n_epsilon'
    electron_to_poisson_variables = 'n_epsilon_frozen'

    poisson_potential_variable = potential_plasma
    electron_potential_variable = potential_from_poisson
    potential_transfer_mode = through_parent
    parent_potential_variable = potential_from_poisson

    parent_to_electron_source_variables = 'w_O2p_h w_Om_h w_Op_h'
    parent_to_electron_variables = 'w_O2p_h w_Om_h w_Op_h'

    parent_to_poisson_source_variables = 'w_O2p_h w_Om_h w_Op_h potential_from_poisson'
    parent_to_poisson_variables = 'w_O2p_frozen w_Om_frozen w_Op_frozen phi_anchor_frozen'

    electron_to_parent_source_variables = 'electron_density_out mean_energy_out'
    electron_to_parent_variables = 'electron_density_out mean_energy_out'

    poisson_to_parent_source_variables = 'phi_anchor_frozen'
    poisson_to_parent_variables = 'fp_phi_anchor_diag'

    poisson_transformed_variables = 'potential_plasma'
    relaxation_factor = 0.45000000000000001
    no_restore = true

    manage_convergence = true
    convergence_name = gummel_delta_phi
    delta_phi_postprocessor = fp_delta_phi_max
    delta_phi_abs_tol = 9.9999999999999995e-07
  []
[]

[Postprocessors]
  [fp_delta_phi_max]
    type = ADElementExtremeFunctorValue
    functor = fp_delta_phi_abs
    value_type = max
    execute_on = 'MULTIAPP_FIXED_POINT_CONVERGENCE'
  []
  [fixed_point_iterations]
    type = NumFixedPointIterations
    execute_on = 'TIMESTEP_END'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  dt = {clock["dt"]}
  dtmin = {clock["dtmin"]}
  dtmax = {clock["dtmax"]}
  end_time = {clock["end_time"]}
  num_steps = {clock["num_steps"]}
  timestep_tolerance = {clock["timestep_tolerance"]}

  fixed_point_algorithm = 'steffensen'
  transformed_variables = 'potential_from_poisson'
  multiapp_fixed_point_convergence = gummel_delta_phi
  fixed_point_min_its = 2
  fixed_point_max_its = 3000
  fixed_point_rel_tol = 1.0e-8
  fixed_point_abs_tol = 1.0e-12
  accept_on_max_fixed_point_iteration = false
[]

[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
[]
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    src = a.oracle_dir
    out = a.out
    if out.exists():
        shutil.rmtree(out)
    legacy = out / "legacy"
    sibling = out / "sibling"
    shutil.copytree(src, legacy)
    sibling.mkdir(parents=True)

    (sibling / "input.i").write_text(transform_parent((src / "input.i").read_text()))
    (sibling / "electron_sub.i").write_text(transform_electron((src / "fast_sub.i").read_text()))
    (sibling / "poisson_sub.i").write_text(transform_poisson((src / "poisson_sub.i").read_text()))
    (sibling / "gummel_driver.i").write_text(driver_input((src / "fast_sub.i").read_text()))
    for data in ("electron_moments.txt", "o2_elastic.txt", "transport_data.txt", "case.json"):
        shutil.copy2(src / data, sibling / data)

    parent = (sibling / "input.i").read_text()
    driver = (sibling / "gummel_driver.i").read_text()
    electron = (sibling / "electron_sub.i").read_text()
    poisson = (sibling / "poisson_sub.i").read_text()

    assert "[PlasmaClosures]" in parent
    assert "create_heavy_transport = true" in parent
    assert "input_files = 'gummel_driver.i'" in parent
    assert "sub_cycling = true" in parent
    assert "[PlasmaClosures]" in electron
    assert "create_electron_closure = true" in electron
    assert "[GummelIteration]" not in electron
    assert "potential_transfer_mode = through_parent" in driver
    assert "transformed_variables = 'potential_from_poisson'" in driver
    assert "delta_phi_abs_tol = 9.9999999999999995e-07" in driver
    assert "[PlasmaClosures]" in poisson
    assert "create_charge_density = true" in poisson
    assert "type = FVElectronResponseBandedCorrection" in poisson
    print("GEN34_SIBLING_PREPARE: PASS")


if __name__ == "__main__":
    main()
