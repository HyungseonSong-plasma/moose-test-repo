#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEVEL_MATRIX = HERE / "prepare_full_monolithic_log_simplex_level_matrix.py"
TOTAL_TIME = 1.0e-10  # 0.1 ns
Q_SCCM = 20.0
OUTLET_PRESSURE_PA = 1.33322  # 10 mTorr
PURE_O2_MOLAR_MASS = 0.032
NON_O2_INLET_SPECIES = ("O2s", "O2p", "O", "Om", "Op", "Os")
ION_WALL_BOUNDARIES = (
    "plasma_electrode plasma_metal plasma_right plasma_cover "
    "plasma_wafer plasma_focus_ring"
)

CASES = {
    "dt0p1ns_1step": (1.0e-10, 1),
    "dt0p01ns_10steps": (1.0e-11, 10),
}


def load_level_matrix_module():
    spec = importlib.util.spec_from_file_location("level_matrix", LEVEL_MATRIX)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Level-4 matrix generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section_bounds(text: str, section: str) -> tuple[int, int]:
    start = text.find(f"[{section}]\n")
    if start < 0:
        raise RuntimeError(f"missing [{section}] section")
    candidates = []
    for name in (
        "Problem",
        "GlobalParams",
        "UserObjects",
        "Variables",
        "AuxVariables",
        "AuxKernels",
        "Functions",
        "FunctorMaterials",
        "FVKernels",
        "FVBCs",
        "Postprocessors",
        "Executioner",
        "Preconditioning",
        "Outputs",
        "Debug",
    ):
        pos = text.find(f"\n[{name}]\n", start + 1)
        if pos > start:
            candidates.append(pos)
    return start, min(candidates) if candidates else len(text)


def append_to_section(text: str, section: str, payload: str) -> str:
    start, end = section_bounds(text, section)
    body = text[start:end]
    close = body.rfind("[]")
    if close < 0:
        raise RuntimeError(f"unterminated [{section}] section")
    body = body[:close] + payload.rstrip() + "\n" + body[close:]
    return text[:start] + body + text[end:]


def child_bounds(text: str, name: str) -> tuple[int, int]:
    marker = f"  [{name}]\n"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"missing child block [{name}]")
    end = text.find("  []\n", start + len(marker))
    if end < 0:
        raise RuntimeError(f"unterminated child block [{name}]")
    return start, end + len("  []\n")


def child_block(text: str, name: str) -> str:
    start, end = child_bounds(text, name)
    return text[start:end]


def set_child_parameter(text: str, name: str, parameter: str, value: str) -> str:
    start, end = child_bounds(text, name)
    body = text[start:end]
    pattern = re.compile(rf"(?m)^    {re.escape(parameter)}\s*=.*$")
    matches = list(pattern.finditer(body))
    line = f"    {parameter} = {value}"
    if len(matches) > 1:
        raise RuntimeError(f"[{name}] has multiple {parameter} parameters")
    if matches:
        body = pattern.sub(line, body, count=1)
    else:
        close = body.rfind("  []")
        if close < 0:
            raise RuntimeError(f"unterminated child block [{name}]")
        body = body[:close] + line + "\n" + body[close:]
    return text[:start] + body + text[end:]


def set_child_boundary(text: str, name: str, boundaries: str) -> str:
    return set_child_parameter(text, name, "boundary", f"'{boundaries}'")


def set_top_scalar(text: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(name)}\s*=.*$")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one top-level scalar {name}, found {len(matches)}")
    return pattern.sub(f"{name} = {value}", text, count=1)


def executioner_bounds(text: str) -> tuple[int, int]:
    return section_bounds(text, "Executioner")


def set_top_level_parameter(section: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^  {re.escape(name)}\s*=.*$")
    matches = list(pattern.finditer(section))
    if len(matches) > 1:
        raise RuntimeError(f"multiple top-level Executioner parameters named {name}")
    line = f"  {name} = {value}"
    if matches:
        return pattern.sub(line, section, count=1)

    close = section.rfind("[]")
    if close < 0:
        raise RuntimeError("unterminated [Executioner] section")
    return section[:close] + line + "\n" + section[close:]


def remove_unreferenced_parameter(text: str, name: str) -> str:
    """Remove one top-level scalar definition only when no references remain."""
    definition = re.compile(rf"(?m)^{re.escape(name)}\s*=.*\n")
    matches = list(definition.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one definition for {name}, found {len(matches)}")

    candidate = definition.sub("", text, count=1)
    if re.search(rf"\b{re.escape(name)}\b", candidate):
        raise RuntimeError(f"refusing to remove still-referenced parameter {name}")
    return candidate


def set_flow_and_pure_o2_inlet(text: str) -> str:
    """Apply 20 sccm to total mixture mass flow and make the inlet pure O2."""
    text = set_top_scalar(text, "Q_sccm", f"{Q_SCCM:.1f}")
    text = set_top_scalar(text, "outlet_pressure", f"{OUTLET_PRESSURE_PA:.5f}")
    text = set_top_scalar(text, "M_inlet", f"{PURE_O2_MOLAR_MASS:.3f}")

    # The total mixture mass-flux BC uses inlet_mdot_value.  Setting all solved
    # non-O2 scalar inflow rates to zero leaves the constrained/reference O2
    # species carrying 100% of the specified total mass inflow.
    for species in NON_O2_INLET_SPECIES:
        pattern = re.compile(rf"(?m)^inlet_mdot_{re.escape(species)}_value\s*=.*$")
        if len(pattern.findall(text)) != 1:
            raise RuntimeError(f"expected exactly one inlet mass-flux definition for {species}")
        text = pattern.sub(f"inlet_mdot_{species}_value = 0.0", text, count=1)

    # Startup composition is already folded into the generated variable initial
    # conditions.  Remove only symbolic inlet-composition parameters that have
    # become unused after the pure-O2 feed conversion.
    for species in NON_O2_INLET_SPECIES:
        text = remove_unreferenced_parameter(text, f"Yin_{species}")

    return text


def configure_ion_wall_physics(text: str) -> str:
    """Use the electron-sheath wall set for ion surface reaction + migration."""
    wall_literal = f"'{ION_WALL_BOUNDARIES}'"

    # Promote the inherited O2+ wall material from migration-only to the full
    # surface-neutralization + migration model.  declare_suffix isolates its
    # functors from the O+ and O- wall materials added below.
    for parameter, value in (
        ("ion_number_density", "n_O2p_monolithic"),
        ("potential", "potential"),
        ("sticking", "1.0"),
        ("migration_gate_smoothing_width", "1.0e-3"),
        ("declare_suffix", "O2p"),
    ):
        text = set_child_parameter(text, "O2p_wall_flux_feedback", parameter, value)

    text = set_child_parameter(
        text, "O2p_migration_wall_loss", "variable", "eta_O2p"
    )
    text = set_child_boundary(text, "O2p_migration_wall_loss", ION_WALL_BOUNDARIES)
    text = set_child_parameter(
        text,
        "O2p_migration_wall_loss",
        "functor",
        "ion_migration_mass_flux_O2p",
    )
    text = set_child_parameter(text, "O2p_migration_wall_loss", "factor", "-1.0")
    text = set_child_boundary(
        text, "O2p_migration_mass_loss_rate", ION_WALL_BOUNDARIES
    )

    extra_materials = """
  [Op_wall_flux_monolithic]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_Op_monolithic
    potential = potential
    mobility = mu_Op
    gas_temperature = T_g
    charge_number = 1
    molar_mass = 0.016
    sticking = 1.0
    migration_gate_smoothing_width = 1.0e-3
    declare_suffix = Op
    block = plasma
  []
  [Om_wall_flux_monolithic]
    type = PhysicsIonWallFluxMaterial
    ion_number_density = n_Om_monolithic
    potential = potential
    mobility = mu_Om
    gas_temperature = T_g
    charge_number = -1
    molar_mass = 0.016
    sticking = 1.0
    migration_gate_smoothing_width = 1.0e-3
    declare_suffix = Om
    block = plasma
  []
  [ion_O_return_wall_material]
    type = ADParsedFunctorMaterial
    property_name = ion_O_return_mass_flux_inward
    functor_names = 'ion_surface_mass_flux_Op ion_migration_mass_flux_Op ion_surface_mass_flux_Om ion_migration_mass_flux_Om'
    functor_symbols = 'sop mop som mom'
    expression = 'sop+mop+som+mom'
    block = plasma
  []
"""
    text = append_to_section(text, "FunctorMaterials", extra_materials)

    extra_bcs = f"""
  [O2p_surface_wall_loss]
    type = FVFunctorNeumannBC
    variable = eta_O2p
    boundary = {wall_literal}
    functor = ion_surface_mass_flux_O2p
    factor = -1.0
  []
  [Op_surface_wall_loss]
    type = FVFunctorNeumannBC
    variable = eta_Op
    boundary = {wall_literal}
    functor = ion_surface_mass_flux_Op
    factor = -1.0
  []
  [Op_migration_wall_loss]
    type = FVFunctorNeumannBC
    variable = eta_Op
    boundary = {wall_literal}
    functor = ion_migration_mass_flux_Op
    factor = -1.0
  []
  [Om_surface_wall_loss]
    type = FVFunctorNeumannBC
    variable = eta_Om
    boundary = {wall_literal}
    functor = ion_surface_mass_flux_Om
    factor = -1.0
  []
  [Om_migration_wall_loss]
    type = FVFunctorNeumannBC
    variable = eta_Om
    boundary = {wall_literal}
    functor = ion_migration_mass_flux_Om
    factor = -1.0
  []
  [O_ion_neutralization_return]
    type = FVFunctorNeumannBC
    variable = eta_O
    boundary = {wall_literal}
    functor = ion_O_return_mass_flux_inward
    factor = 1.0
  []
"""
    text = append_to_section(text, "FVBCs", extra_bcs)

    extra_pps = f"""
  [O2p_surface_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = {wall_literal}
    fvbcs = 'O2p_surface_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_surface_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = {wall_literal}
    fvbcs = 'Op_surface_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Op_migration_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = {wall_literal}
    fvbcs = 'Op_migration_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_surface_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = {wall_literal}
    fvbcs = 'Om_surface_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Om_migration_mass_loss_rate]
    type = SideFVFluxBCIntegral
    boundary = {wall_literal}
    fvbcs = 'Om_migration_wall_loss'
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [O_ion_neutralization_return_rate]
    type = SideFVFluxBCIntegral
    boundary = {wall_literal}
    fvbcs = 'O_ion_neutralization_return'
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    text = append_to_section(text, "Postprocessors", extra_pps)

    return text


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)
    dt, num_steps = CASES[case]

    module = load_level_matrix_module()
    base = module.build(4)
    text = base.read_text(encoding="utf-8")

    text = set_flow_and_pure_o2_inlet(text)
    text = configure_ion_wall_physics(text)

    start, end = executioner_bounds(text)
    section = text[start:end]
    for name, value in (
        ("dt", f"{dt:.17g}"),
        ("dtmin", f"{dt:.17g}"),
        ("dtmax", f"{dt:.17g}"),
        ("end_time", f"{TOTAL_TIME:.17g}"),
        ("num_steps", str(num_steps)),
    ):
        section = set_top_level_parameter(section, name, value)
    text = text[:start] + section + text[end:]

    required = (
        "splitting = 'heavy fast'",
        "splitting = 'electron poisson'",
        "splitting_type = multiplicative",
        "type = PhysicsFVLogMolarElectrostaticDrift",
        "type = PhysicsFVElectronEnergyJouleHeating",
        "type = PhysicsFVElectronGroundedSheathCollectionBC",
        "property_name = charge_number_density",
        "pc_hypre_type",
        "boomeramg",
        f"Q_sccm = {Q_SCCM:.1f}",
        f"outlet_pressure = {OUTLET_PRESSURE_PA:.5f}",
        f"M_inlet = {PURE_O2_MOLAR_MASS:.3f}",
        f"boundary = '{ION_WALL_BOUNDARIES}'",
        "functor = ion_surface_mass_flux_O2p",
        "functor = ion_migration_mass_flux_O2p",
        "functor = ion_surface_mass_flux_Op",
        "functor = ion_migration_mass_flux_Op",
        "functor = ion_surface_mass_flux_Om",
        "functor = ion_migration_mass_flux_Om",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"L4 final contract missing: {token}")

    # Ion wall collection must match the production electron sheath set exactly.
    electron_sheath = child_block(text, "electron_sheath_loss")
    expected_electron_boundary = f"    boundary = '{ION_WALL_BOUNDARIES}'"
    if expected_electron_boundary not in electron_sheath:
        raise RuntimeError("ion wall set no longer matches electron sheath boundary set")

    # Inlet/outlet are gas-flow/open species boundaries, not ion wall boundaries.
    for name in (
        "O2p_surface_wall_loss",
        "O2p_migration_wall_loss",
        "Op_surface_wall_loss",
        "Op_migration_wall_loss",
        "Om_surface_wall_loss",
        "Om_migration_wall_loss",
    ):
        body = child_block(text, name)
        if "inlet" in body or "outlet" in body:
            raise RuntimeError(f"{name} incorrectly includes inlet/outlet")

    for species in NON_O2_INLET_SPECIES:
        expected = f"inlet_mdot_{species}_value = 0.0"
        if expected not in text:
            raise RuntimeError(f"pure-O2 inlet contract missing: {expected}")
        if re.search(rf"(?m)^Yin_{re.escape(species)}\s*=", text):
            raise RuntimeError(f"unused pure-O2 inlet parameter survived: Yin_{species}")

    start, end = executioner_bounds(text)
    exec_section = text[start:end]
    expected_lines = (
        f"  dt = {dt:.17g}",
        f"  dtmin = {dt:.17g}",
        f"  dtmax = {dt:.17g}",
        f"  end_time = {TOTAL_TIME:.17g}",
        f"  num_steps = {num_steps}",
    )
    for expected in expected_lines:
        if expected not in exec_section:
            raise RuntimeError(f"time contract missing from [Executioner]: {expected}")

    if "[Preconditioning]" in text:
        pre = text[text.find("[Preconditioning]"):]
        if re.search(r"(?m)^  (dt|dtmin|dtmax|end_time|num_steps)\s*=", pre):
            raise RuntimeError("time-control parameter leaked outside [Executioner]")

    out = HERE / f"full_monolithic_l4_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(
        f"case={case} dt={dt:.17g} dtmin={dt:.17g} dtmax={dt:.17g} "
        f"num_steps={num_steps} total_time={TOTAL_TIME:.17g}"
    )
    print(f"total inlet flow = {Q_SCCM:.1f} sccm, pure O2")
    print(f"outlet pressure = {OUTLET_PRESSURE_PA:.5f} Pa (10 mTorr)")
    print("all solved non-O2 inlet scalar mass fluxes = 0")
    print(f"ion surface + migration wall boundaries = {ION_WALL_BOUNDARIES}")
    print("inlet/outlet excluded from ion wall collection")
    print("solver not run; generator only")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
