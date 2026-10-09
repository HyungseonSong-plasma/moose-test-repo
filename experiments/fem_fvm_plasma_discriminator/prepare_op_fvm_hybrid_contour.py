#!/usr/bin/env python3
"""Issue #331 Stage A: add solved O+ FV drift-diffusion to the qualified #378 O2+/O- baseline."""
from pathlib import Path
import math

import prepare_cases as base
import prepare_om_fvm_hybrid_contour as om

NOP0 = base.NE0
NM0 = om.NM0
NI0_BALANCED = base.NE0 + NM0 - NOP0
if NI0_BALANCED <= 0.0:
    raise RuntimeError("balanced O2+ initial density must remain positive")

COP0 = NOP0 / base.NA
CI0_BALANCED = NI0_BALANCED / base.NA
LOG_NOP0 = math.log(COP0)
LOG_NI0_BALANCED = math.log(CI0_BALANCED)

OP_MU = base.ION_MU
OP_D = base.ION_D
OP_MOLAR_MASS = 0.016


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def build_case() -> str:
    text = om.build_case()

    old_vars = f"""  [log_ni]\n    type = MooseVariableFVReal\n    initial_condition = {om.LOG_NI0_NEUTRAL:.17g}\n    block = plasma\n  []\n  [log_nm]\n    type = MooseVariableFVReal\n    initial_condition = {om.LOG_NM0:.17g}\n    block = plasma\n  []\n"""
    new_vars = f"""  [log_ni]\n    type = MooseVariableFVReal\n    initial_condition = {LOG_NI0_BALANCED:.17g}\n    block = plasma\n  []\n  [log_nm]\n    type = MooseVariableFVReal\n    initial_condition = {om.LOG_NM0:.17g}\n    block = plasma\n  []\n  [log_nop]\n    type = MooseVariableFVReal\n    initial_condition = {LOG_NOP0:.17g}\n    block = plasma\n  []\n"""
    text = replace_once(text, old_vars, new_vars, "balanced O2+/O-/O+ variables")

    old_names = (
        "    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion "
        "negative_ion_mobility negative_ion_diffusion carrier_one relative_permittivity'\n"
    )
    new_names = (
        "    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion "
        "negative_ion_mobility negative_ion_diffusion atomic_positive_ion_mobility "
        "atomic_positive_ion_diffusion carrier_one relative_permittivity'\n"
    )
    text = replace_once(text, old_names, new_names, "O+ constant material names")

    old_values = (
        f"    prop_values = '{base.PRESSURE:.12g} {base.TG:.12g} {base.ION_MU:.12g} "
        f"{base.ION_D:.17g} {om.OM_MU:.12g} {om.OM_D:.17g} 1.0 1.0'\n"
    )
    new_values = (
        f"    prop_values = '{base.PRESSURE:.12g} {base.TG:.12g} {base.ION_MU:.12g} "
        f"{base.ION_D:.17g} {om.OM_MU:.12g} {om.OM_D:.17g} "
        f"{OP_MU:.12g} {OP_D:.17g} 1.0 1.0'\n"
    )
    text = replace_once(text, old_values, new_values, "O+ constant material values")

    old_nm_density = """  [negative_ion_physical_density]\n    type = ADParsedFunctorMaterial\n    property_name = n_m_physical\n    functor_names = 'negative_ion_molar_density'\n    functor_symbols = 'cm'\n    expression = '6.02214076e23*cm'\n    block = plasma\n  []\n"""
    new_density = old_nm_density + """  [atomic_positive_ion_molar_density]\n    type = ADParsedFunctorMaterial\n    property_name = atomic_positive_ion_molar_density\n    functor_names = 'log_nop'\n    functor_symbols = 'u'\n    expression = 'exp(u)'\n    block = plasma\n  []\n  [atomic_positive_ion_physical_density]\n    type = ADParsedFunctorMaterial\n    property_name = n_op_physical\n    functor_names = 'atomic_positive_ion_molar_density'\n    functor_symbols = 'cop'\n    expression = '6.02214076e23*cop'\n    block = plasma\n  []\n"""
    text = replace_once(text, old_nm_density, new_density, "O+ density materials")

    old_charge = """  [charge_number_density]\n    type = ADParsedFunctorMaterial\n    property_name = charge_number_density\n    functor_names = 'n_i_physical n_e_physical n_m_physical'\n    functor_symbols = 'ni ne nm'\n    expression = 'ni-ne-nm'\n    block = plasma\n  []\n"""
    new_charge = """  [charge_number_density]\n    type = ADParsedFunctorMaterial\n    property_name = charge_number_density\n    functor_names = 'n_i_physical n_op_physical n_e_physical n_m_physical'\n    functor_symbols = 'ni nop ne nm'\n    expression = 'ni+nop-ne-nm'\n    block = plasma\n  []\n"""
    text = replace_once(text, old_charge, new_charge, "Poisson charge with O+")

    op_wall = f"""  [atomic_positive_ion_wall_flux]\n    type = PhysicsIonWallFluxMaterial\n    property_prefix = atomic_positive_\n    use_element_gradient_for_potential = true\n    ion_number_density = n_op_physical\n    potential = potential\n    mobility = atomic_positive_ion_mobility\n    gas_temperature = T_g_fixed\n    charge_number = 1\n    molar_mass = {OP_MOLAR_MASS:.17g}\n    sticking = 1.0\n    ion_temperature_eV = 0.0\n    migration_gate_smoothing_width = 1.0e-3\n    block = plasma\n  []\n"""
    text = replace_once(text, "\n[]\n\n[Kernels]\n", "\n" + op_wall + "[]\n\n[Kernels]\n", "FunctorMaterials closing block")

    op_kernels = f"""  [nop_time]\n    type = PhysicsFVLogMolarElectronTimeDerivative\n    variable = log_nop\n    block = plasma\n  []\n  [nop_diffusion]\n    type = PhysicsFVLogMolarElectronDiffusion\n    variable = log_nop\n    coeff = atomic_positive_ion_diffusion\n    block = plasma\n  []\n  [nop_drift]\n    type = PhysicsFVLogMolarElectrostaticDrift\n    variable = log_nop\n    potential = potential\n    mobility = atomic_positive_ion_mobility\n    carrier = carrier_one\n    charge_number = 1\n    advected_interp_method = upwind\n    use_element_gradient_for_potential = true\n    boundaries_to_avoid = '{base.GROUND}'\n    block = plasma\n  []\n"""
    text = replace_once(text, "\n[]\n\n[BCs]\n", "\n" + op_kernels + "[]\n\n[BCs]\n", "FVKernels closing block")

    op_bc = f"""  [atomic_positive_ion_wall]\n    type = FVFunctorNeumannBC\n    variable = log_nop\n    functor = atomic_positive_ion_wall_number_flux\n    factor = {-base.INV_NA:.17g}\n    boundary = '{base.GROUND}'\n  []\n"""
    text = replace_once(text, "\n[]\n\n[Postprocessors]\n", "\n" + op_bc + "[]\n\n[Postprocessors]\n", "FVBCs closing block")

    op_pp = """  [nop_min]\n    type = ADElementExtremeFunctorValue\n    functor = n_op_physical\n    value_type = min\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [nop_max]\n    type = ADElementExtremeFunctorValue\n    functor = n_op_physical\n    value_type = max\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"""
    text = replace_once(text, "\n[]\n[Executioner]\n", "\n" + op_pp + "[]\n[Executioner]\n", "Postprocessors closing block")
    return text


def validate_contract(text: str) -> None:
    if NI0_BALANCED + NOP0 != base.NE0 + NM0:
        raise RuntimeError("analytic initial charge neutrality changed")

    ne = math.exp(base.LOG_NE0) * base.NA
    nm = math.exp(om.LOG_NM0) * base.NA
    ni = math.exp(LOG_NI0_BALANCED) * base.NA
    nop = math.exp(LOG_NOP0) * base.NA
    residual = ni + nop - ne - nm
    scale = max(abs(ni) + abs(nop), abs(ne) + abs(nm), 1.0)
    if abs(residual) > 1.0e-12 * scale:
        raise RuntimeError(f"reconstructed initial neutrality residual too large: {residual:.17g} m^-3")

    for token in ["[log_nop]", "expression = 'ni+nop-ne-nm'", "property_prefix = atomic_positive_", "functor = atomic_positive_ion_wall_number_flux", "molar_mass = 0.016"]:
        if token not in text:
            raise RuntimeError(f"missing O+ contract token: {token}")

    o2p_drift = text.split("[ni_drift]", 1)[1].split("  []", 1)[0]
    om_drift = text.split("[nm_drift]", 1)[1].split("  []", 1)[0]
    op_drift = text.split("[nop_drift]", 1)[1].split("  []", 1)[0]
    if "charge_number = 1" not in o2p_drift:
        raise RuntimeError("O2+ drift charge sign changed")
    if "charge_number = -1" not in om_drift:
        raise RuntimeError("O- drift charge sign changed")
    if "charge_number = 1" not in op_drift:
        raise RuntimeError("O+ drift must use charge_number=+1")

    wall = text.split("[atomic_positive_ion_wall_flux]", 1)[1].split("  []", 1)[0]
    if "charge_number = 1" not in wall:
        raise RuntimeError("O+ wall migration must use charge_number=+1")
    if "exp(" in wall or "exponential" in wall.lower():
        raise RuntimeError("O+ wall flux must remain exp-free")
    if text.count("variable = log_nop") < 4:
        raise RuntimeError("O+ is not wired through variable + transport + wall")


if __name__ == "__main__":
    text = build_case()
    validate_contract(text)
    out = Path(base.HERE) / "ion_om_op_fvm_hybrid_contour_dt1ns_300steps.i"
    out.write_text(text, encoding="utf-8")

    ne = math.exp(base.LOG_NE0) * base.NA
    nm = math.exp(om.LOG_NM0) * base.NA
    ni = math.exp(LOG_NI0_BALANCED) * base.NA
    nop = math.exp(LOG_NOP0) * base.NA
    residual = ni + nop - ne - nm
    print(f"wrote {out}")
    print("hybrid discretization: ne=FEM, O2+=FVM, O-=FVM, O+=FVM, electron energy=FEM, potential=FEM")
    print(f"initial densities [m^-3]: ne={base.NE0:.17g}, O-={NM0:.17g}, O2+={NI0_BALANCED:.17g}, O+={NOP0:.17g}")
    print(f"reconstructed initial neutrality residual [m^-3]: {residual:.17g}")
    print("drift signs: O2+=+1, O-=-1, O+=+1")
    print("O+ wall: exp-free thermal sticking + outward signed migration")
    print("O+ mobility/diffusion are provisional Stage-A values matching the #378 charged baseline")
