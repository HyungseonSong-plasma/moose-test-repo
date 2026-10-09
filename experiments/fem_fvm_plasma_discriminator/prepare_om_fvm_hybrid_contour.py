#!/usr/bin/env python3
"""Add solved O- FV drift-diffusion to the validated contour hybrid baseline."""
from pathlib import Path
import math

import prepare_cases as base
import prepare_ion_fvm_hybrid_contour as hybrid

# Keep the new charged species on the same initial number-density scale as the
# existing electron/O2+ discriminator while enforcing exact charge neutrality:
#     n_O2+ = n_e + n_O-
NM0 = base.NE0
NI0_NEUTRAL = base.NE0 + NM0
CM0 = NM0 / base.NA
CI0_NEUTRAL = NI0_NEUTRAL / base.NA
LOG_NM0 = math.log(CM0)
LOG_NI0_NEUTRAL = math.log(CI0_NEUTRAL)

# Bounded first baseline: keep the same mobility magnitude / Einstein-consistent
# diffusion coefficient as the existing O2+ discriminator. The signed charge,
# not the mobility sign, reverses electrostatic migration for O-.
OM_MU = base.ION_MU
OM_D = base.ION_D
OM_MOLAR_MASS = 0.016


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def build_case() -> str:
    text = hybrid.build_case()

    # O2+ remains FV but its IC is raised so the newly introduced O- does not
    # inject a spurious initial space charge. O- uses the same log-molar state
    # representation and FV discretization family.
    old_ni = f"""  [log_ni]\n    type = MooseVariableFVReal\n    initial_condition = {base.LOG_NI0:.17g}\n    block = plasma\n  []\n"""
    new_ni_nm = f"""  [log_ni]\n    type = MooseVariableFVReal\n    initial_condition = {LOG_NI0_NEUTRAL:.17g}\n    block = plasma\n  []\n  [log_nm]\n    type = MooseVariableFVReal\n    initial_condition = {LOG_NM0:.17g}\n    block = plasma\n  []\n"""
    text = replace_once(text, old_ni, new_ni_nm, "neutrality-adjusted O2+/O- variables")

    old_names = (
        "    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion "
        "carrier_one relative_permittivity'\n"
    )
    new_names = (
        "    prop_names = 'p_fixed T_g_fixed ion_mobility ion_diffusion "
        "negative_ion_mobility negative_ion_diffusion carrier_one relative_permittivity'\n"
    )
    text = replace_once(text, old_names, new_names, "constant material names")

    old_values = (
        f"    prop_values = '{base.PRESSURE:.12g} {base.TG:.12g} {base.ION_MU:.12g} "
        f"{base.ION_D:.17g} 1.0 1.0'\n"
    )
    new_values = (
        f"    prop_values = '{base.PRESSURE:.12g} {base.TG:.12g} {base.ION_MU:.12g} "
        f"{base.ION_D:.17g} {OM_MU:.12g} {OM_D:.17g} 1.0 1.0'\n"
    )
    text = replace_once(text, old_values, new_values, "constant material values")

    old_ion_density = """  [ion_physical_density]\n    type = ADParsedFunctorMaterial\n    property_name = n_i_physical\n    functor_names = 'ion_molar_density'\n    functor_symbols = 'ci'\n    expression = '6.02214076e23*ci'\n    block = plasma\n  []\n"""
    new_ion_density = old_ion_density + """  [negative_ion_molar_density]\n    type = ADParsedFunctorMaterial\n    property_name = negative_ion_molar_density\n    functor_names = 'log_nm'\n    functor_symbols = 'u'\n    expression = 'exp(u)'\n    block = plasma\n  []\n  [negative_ion_physical_density]\n    type = ADParsedFunctorMaterial\n    property_name = n_m_physical\n    functor_names = 'negative_ion_molar_density'\n    functor_symbols = 'cm'\n    expression = '6.02214076e23*cm'\n    block = plasma\n  []\n"""
    text = replace_once(text, old_ion_density, new_ion_density, "O- density materials")

    old_charge = """  [charge_number_density]\n    type = ADParsedFunctorMaterial\n    property_name = charge_number_density\n    functor_names = 'n_i_physical n_e_physical'\n    functor_symbols = 'ni ne'\n    expression = 'ni-ne'\n    block = plasma\n  []\n"""
    new_charge = """  [charge_number_density]\n    type = ADParsedFunctorMaterial\n    property_name = charge_number_density\n    functor_names = 'n_i_physical n_e_physical n_m_physical'\n    functor_symbols = 'ni ne nm'\n    expression = 'ni-ne-nm'\n    block = plasma\n  []\n"""
    text = replace_once(text, old_charge, new_charge, "Poisson charge with O-")

    # Reuse the existing charged-wall implementation with a distinct namespace.
    # The surface contribution is gamma*(1/4)*n*v_th and migration is the
    # outward positive part of z*E.n. There is deliberately no exponential wall
    # factor. The default empty prefix keeps the existing O2+ names unchanged.
    negative_wall = f"""  [negative_ion_wall_flux]\n    type = PhysicsIonWallFluxMaterial\n    property_prefix = negative_\n    use_element_gradient_for_potential = true\n    ion_number_density = n_m_physical\n    potential = potential\n    mobility = negative_ion_mobility\n    gas_temperature = T_g_fixed\n    charge_number = -1\n    molar_mass = {OM_MOLAR_MASS:.17g}\n    sticking = 1.0\n    ion_temperature_eV = 0.0\n    migration_gate_smoothing_width = 1.0e-3\n    block = plasma\n  []\n"""
    text = replace_once(
        text,
        "\n[]\n\n[Kernels]\n",
        "\n" + negative_wall + "[]\n\n[Kernels]\n",
        "FunctorMaterials closing block",
    )

    negative_kernels = f"""  [nm_time]\n    type = PhysicsFVLogMolarElectronTimeDerivative\n    variable = log_nm\n    block = plasma\n  []\n  [nm_diffusion]\n    type = PhysicsFVLogMolarElectronDiffusion\n    variable = log_nm\n    coeff = negative_ion_diffusion\n    block = plasma\n  []\n  [nm_drift]\n    type = PhysicsFVLogMolarElectrostaticDrift\n    variable = log_nm\n    potential = potential\n    mobility = negative_ion_mobility\n    carrier = carrier_one\n    charge_number = -1\n    advected_interp_method = upwind\n    use_element_gradient_for_potential = true\n    boundaries_to_avoid = '{base.GROUND}'\n    block = plasma\n  []\n"""
    text = replace_once(
        text,
        "\n[]\n\n[BCs]\n",
        "\n" + negative_kernels + "[]\n\n[BCs]\n",
        "FVKernels closing block",
    )

    negative_bc = f"""  [negative_ion_wall]\n    type = FVFunctorNeumannBC\n    variable = log_nm\n    functor = negative_ion_wall_number_flux\n    factor = {-base.INV_NA:.17g}\n    boundary = '{base.GROUND}'\n  []\n"""
    text = replace_once(
        text,
        "\n[]\n\n[Postprocessors]\n",
        "\n" + negative_bc + "[]\n\n[Postprocessors]\n",
        "FVBCs closing block",
    )

    negative_pp = """  [nm_min]\n    type = ADElementExtremeFunctorValue\n    functor = n_m_physical\n    value_type = min\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [nm_max]\n    type = ADElementExtremeFunctorValue\n    functor = n_m_physical\n    value_type = max\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [charge_number_min]\n    type = ADElementExtremeFunctorValue\n    functor = charge_number_density\n    value_type = min\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n  [charge_number_max]\n    type = ADElementExtremeFunctorValue\n    functor = charge_number_density\n    value_type = max\n    block = plasma\n    execute_on = 'INITIAL TIMESTEP_END'\n  []\n"""
    # COMMON_PP and EXEC are concatenated directly in prepare_cases.py, so the
    # Postprocessors closing marker is followed by [Executioner] with one newline.
    text = replace_once(
        text,
        "\n[]\n[Executioner]\n",
        "\n" + negative_pp + "[]\n[Executioner]\n",
        "Postprocessors closing block",
    )

    return text


def validate_contract(text: str) -> None:
    if NI0_NEUTRAL != base.NE0 + NM0:
        raise RuntimeError("initial neutrality arithmetic changed")

    # Check the actual log-molar states that MOOSE reconstructs, not only the
    # analytic constants used to form them.
    ne_reconstructed = math.exp(base.LOG_NE0) * base.NA
    nm_reconstructed = math.exp(LOG_NM0) * base.NA
    ni_reconstructed = math.exp(LOG_NI0_NEUTRAL) * base.NA
    neutrality_residual = ni_reconstructed - ne_reconstructed - nm_reconstructed
    neutrality_scale = max(abs(ni_reconstructed), 1.0)
    if abs(neutrality_residual) > 1.0e-12 * neutrality_scale:
        raise RuntimeError(
            f"reconstructed initial neutrality residual too large: {neutrality_residual:.17g} m^-3"
        )

    required = [
        "[log_nm]",
        "expression = 'ni-ne-nm'",
        "property_prefix = negative_",
        "functor = negative_ion_wall_number_flux",
        "type = PhysicsIonWallFluxMaterial",
        "molar_mass = 0.016",
    ]
    for token in required:
        if token not in text:
            raise RuntimeError(f"missing O- contract token: {token}")

    positive_drift = text.split("[ni_drift]", 1)[1].split("  []", 1)[0]
    negative_drift = text.split("[nm_drift]", 1)[1].split("  []", 1)[0]
    if "charge_number = 1" not in positive_drift:
        raise RuntimeError("O2+ drift charge sign changed")
    if "charge_number = -1" not in negative_drift:
        raise RuntimeError("O- drift must use charge_number=-1")

    wall = text.split("[negative_ion_wall_flux]", 1)[1].split("  []", 1)[0]
    if "charge_number = -1" not in wall:
        raise RuntimeError("O- wall migration must use charge_number=-1")
    if "exp(" in wall or "exponential" in wall.lower():
        raise RuntimeError("O- wall flux must remain exp-free")
    if text.count("variable = log_nm") < 4:
        raise RuntimeError("O- is not wired through variable + transport + wall")


if __name__ == "__main__":
    text = build_case()
    validate_contract(text)
    out = Path(base.HERE) / "ion_om_fvm_hybrid_contour_dt1ns_300steps.i"
    out.write_text(text, encoding="utf-8")
    ne_reconstructed = math.exp(base.LOG_NE0) * base.NA
    nm_reconstructed = math.exp(LOG_NM0) * base.NA
    ni_reconstructed = math.exp(LOG_NI0_NEUTRAL) * base.NA
    residual = ni_reconstructed - ne_reconstructed - nm_reconstructed
    print(f"wrote {out}")
    print("hybrid discretization: ne=FEM, O2+=FVM, O-=FVM, electron energy=FEM, potential=FEM")
    print(f"initial densities [m^-3]: ne={base.NE0:.17g}, O-={NM0:.17g}, O2+={NI0_NEUTRAL:.17g}")
    print(f"reconstructed initial neutrality residual [m^-3]: {residual:.17g}")
    print("O- drift charge_number=-1; O2+ drift charge_number=+1")
    print("O- wall: exp-free thermal sticking + outward signed migration")
