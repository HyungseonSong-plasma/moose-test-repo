#!/usr/bin/env python3
"""Issue #331 Stage-B v4: add constraint-consistent surface reaction coupling.

Keeps the Stage-B v3 transport architecture unchanged:
- O2+, O-, O+ remain independent log-molar FV drift-diffusion states.
- Neutral O2/O2*/O/O* remain a Q-1 flow/species mixture with constrained O2.

Surface chemistry:
  O   -> 0.5 O2   (s=0.2)
  O2* -> O2       (s=1.0)
  O*  -> 0.5 O2   (s=0.2)
  O2+ -> O2       (s=1.0)
  O-  -> O        (s=1.0)
  O+  -> O        (s=1.0)

Ion transport BC scope is deliberately unchanged, including inlet/outlet.
Reaction-product coupling is applied only on the physical plasma-wall set.
"""
from pathlib import Path

import prepare_op_neutral_flow_staged_15us as v1
import prepare_op_neutral_flow_staged_15us_v3 as v3

R_GAS = 8.31446
PI = 3.14159265358979323846
M_O2 = 0.032
M_O = 0.016

WALLS = (
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
WALL_LIST = "'" + " ".join(WALLS) + "'"
ION_BC_SCOPE = (
    "inlet outlet plasma_electrode plasma_metal plasma_right "
    "plasma_cover plasma_wafer plasma_focus_ring"
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def neutral_flux_expression(sticking: float, molar_mass: float, w: str) -> str:
    return (
        f"{sticking:.17g}*0.25*sqrt(8.0*{R_GAS:.17g}*tg/"
        f"({PI:.17g}*{molar_mass:.17g}))*rho*{w}"
    )


def add_surface_coupling(text: str) -> str:
    material_blocks = f"""
  [stageb4_O_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = stageb4_O_surface_mass_flux
    functor_names = 'rho_neutral w_O T_g_fixed'
    functor_symbols = 'rho w tg'
    expression = '{neutral_flux_expression(0.2, M_O, "w")}'
    block = plasma
  []
  [stageb4_O2s_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = stageb4_O2s_surface_mass_flux
    functor_names = 'rho_neutral w_O2s T_g_fixed'
    functor_symbols = 'rho w tg'
    expression = '{neutral_flux_expression(1.0, M_O2, "w")}'
    block = plasma
  []
  [stageb4_Os_surface_flux]
    type = ADParsedFunctorMaterial
    property_name = stageb4_Os_surface_mass_flux
    functor_names = 'rho_neutral w_Os T_g_fixed'
    functor_symbols = 'rho w tg'
    expression = '{neutral_flux_expression(0.2, M_O, "w")}'
    block = plasma
  []

  [stageb4_ion_neutral_total]
    type = ADParsedFunctorMaterial
    property_name = stageb4_ion_neutral_total_mass_flux
    functor_names = 'ion_wall_mass_flux negative_ion_wall_mass_flux atomic_positive_ion_wall_mass_flux'
    functor_symbols = 'o2p om op'
    expression = 'o2p+om+op'
    block = plasma
  []
  [stageb4_ion_O_return_material]
    type = ADParsedFunctorMaterial
    property_name = stageb4_ion_O_return_mass_flux
    functor_names = 'negative_ion_wall_mass_flux atomic_positive_ion_wall_mass_flux'
    functor_symbols = 'om op'
    expression = 'om+op'
    block = plasma
  []
"""
    text = replace_once(
        text,
        "\n[]\n\n[Kernels]\n",
        material_blocks + "\n[]\n\n[Kernels]\n",
        "FunctorMaterials -> Kernels boundary",
    )

    bc_blocks = f"""
  [stageb4_O_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = {WALL_LIST}
    functor = stageb4_O_surface_mass_flux
    factor = -1.0
  []
  [stageb4_O2s_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_O2s
    boundary = {WALL_LIST}
    functor = stageb4_O2s_surface_mass_flux
    factor = -1.0
  []
  [stageb4_Os_surface_loss]
    type = FVFunctorNeumannBC
    variable = w_Os
    boundary = {WALL_LIST}
    functor = stageb4_Os_surface_mass_flux
    factor = -1.0
  []

  [stageb4_ion_total_mass_return]
    type = FVFunctorNeumannBC
    variable = p
    boundary = {WALL_LIST}
    functor = stageb4_ion_neutral_total_mass_flux
    factor = 1.0
  []

  [stageb4_ion_O_return]
    type = FVFunctorNeumannBC
    variable = w_O
    boundary = {WALL_LIST}
    functor = stageb4_ion_O_return_mass_flux
    factor = 1.0
  []
"""
    text = replace_once(
        text,
        "\n[]\n\n[Postprocessors]\n",
        bc_blocks + "\n[]\n\n[Postprocessors]\n",
        "FVBCs -> Postprocessors boundary",
    )

    pp_blocks = f"""
  [stageb4_O_surface_loss_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = stageb4_O_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_O2s_surface_loss_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = stageb4_O2s_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_Os_surface_loss_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = stageb4_Os_surface_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_O2p_wall_mass_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = ion_wall_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_Om_wall_mass_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = negative_ion_wall_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_Op_wall_mass_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = atomic_positive_ion_wall_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_ion_total_neutral_return_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = stageb4_ion_neutral_total_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [stageb4_ion_O_return_rate]
    type = ADSideIntegralFunctorPostprocessor
    boundary = {WALL_LIST}
    functor = stageb4_ion_O_return_mass_flux
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""
    text = replace_once(
        text,
        "\n[]\n[Executioner]\n",
        pp_blocks + "\n[]\n[Executioner]\n",
        "Postprocessors -> Executioner boundary",
    )
    return text


def validate_surface_contract(text: str) -> None:
    v1.validate_generated_contract(text)
    v3.validate_section_ownership(text)

    for bc in ("[ion_wall]", "[negative_ion_wall]", "[atomic_positive_ion_wall]"):
        section = text.split(bc, 1)[1].split("  []", 1)[0]
        expected = f"boundary = '{ION_BC_SCOPE}'"
        if expected not in section:
            raise RuntimeError(f"ion BC scope changed for {bc}")

    required = (
        "[stageb4_O_surface_loss]",
        "[stageb4_O2s_surface_loss]",
        "[stageb4_Os_surface_loss]",
        "[stageb4_ion_total_mass_return]",
        "[stageb4_ion_O_return]",
        "expression = 'o2p+om+op'",
        "expression = 'om+op'",
        "factor = -1.0",
        "factor = 1.0",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"missing Stage-B v4 surface-coupling token: {token}")

    if "[w_O2]" in text:
        raise RuntimeError("independent w_O2 variable introduced")
    if text.count("expression = '1.0-s-o-a'") != 1:
        raise RuntimeError("neutral O2 Q-1 constraint changed")

    for name in (
        "[stageb4_O_surface_loss]",
        "[stageb4_O2s_surface_loss]",
        "[stageb4_Os_surface_loss]",
        "[stageb4_ion_total_mass_return]",
        "[stageb4_ion_O_return]",
    ):
        section = text.split(name, 1)[1].split("  []", 1)[0]
        if f"boundary = {WALL_LIST}" not in section:
            raise RuntimeError(f"reaction scope changed for {name}")
        if "inlet" in section or "outlet" in section:
            raise RuntimeError(f"reaction product coupling leaked to inlet/outlet for {name}")


def main() -> None:
    v1.replace_once = v3.section_aware_replace_once
    text = v1.build_case()
    text = add_surface_coupling(text)
    validate_surface_contract(text)

    out = Path(v1.base.HERE) / f"{v1.CASE_NAME}.i"
    out.write_text(text, encoding="utf-8")

    print(f"wrote {out}")
    print("stageb4_surface_reactions=O->0.5O2,O2*->O2,O*->0.5O2,O2+->O2,O-->O,O+->O")
    print("neutral_sticking=O:0.2,O2*:1.0,O*:0.2")
    print("ion_sticking=O2+:1.0,O-:1.0,O+:1.0 (existing PhysicsIonWallFluxMaterial)")
    print(f"reaction_wall_scope={' '.join(WALLS)}")
    print(f"ion_loss_bc_scope={ION_BC_SCOPE}")
    print("constraint_coupling=total ion neutral mass -> p residual; O-/O+ mass -> w_O; O2+ remainder -> constrained O2")
    print("neutral_surface_products=implicit constrained O2 with zero total-neutral-mass source")
    print("time_schedule=1nsx100+10nsx90+100nsx90+1000nsx5=15us")


if __name__ == "__main__":
    main()
