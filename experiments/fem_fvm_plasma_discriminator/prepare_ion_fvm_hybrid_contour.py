#!/usr/bin/env python3
from pathlib import Path
import prepare_cases as base
import prepare_full_fem_contour_mesh as full_fem

HYBRID_NSTEPS = 300
HYBRID_END_TIME = base.DT * HYBRID_NSTEPS


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def build_case() -> str:
    # Start from the validated contour-mesh full-FEM case, including the
    # thermal-only electron particle/energy wall BCs.
    text = full_fem.build_case()

    # O2+ becomes cell-centered FV; electron density, electron energy and
    # electrostatic potential remain P1 FEM variables.
    old_var = f"""  [log_ni]\n    family = LAGRANGE\n    order = FIRST\n    initial_condition = {base.LOG_NI0:.17g}\n    block = plasma\n  []\n"""
    new_var = f"""  [log_ni]\n    type = MooseVariableFVReal\n    initial_condition = {base.LOG_NI0:.17g}\n    block = plasma\n  []\n"""
    text = replace_once(text, old_var, new_var, "log_ni variable block")

    old_ni_kernels = """  [ni_time]\n    type = PhysicsFEMLogMolarTimeDerivative\n    variable = log_ni\n    block = plasma\n  []\n  [ni_transport]\n    type = PhysicsFEMLogMolarDriftDiffusion\n    variable = log_ni\n    potential = potential\n    mobility = ion_mobility\n    diffusion = ion_diffusion\n    charge_number = 1\n    block = plasma\n  []\n"""
    text = replace_once(text, old_ni_kernels, "", "FEM ion kernels")

    fv_kernels = f"""
[FVKernels]
  [ni_time]
    type = PhysicsFVLogMolarElectronTimeDerivative
    variable = log_ni
    block = plasma
  []
  [ni_diffusion]
    type = PhysicsFVLogMolarElectronDiffusion
    variable = log_ni
    coeff = ion_diffusion
    block = plasma
  []
  [ni_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_ni
    potential = potential
    mobility = ion_mobility
    carrier = carrier_one
    charge_number = 1
    advected_interp_method = upwind
    use_element_gradient_for_potential = true
    boundaries_to_avoid = '{base.GROUND}'
    block = plasma
  []
[]

"""
    text = replace_once(text, "\n[BCs]\n", "\n" + fv_kernels + "[BCs]\n", "BC section insertion point")

    # The shared ion wall-flux material also needs an element gradient when
    # potential is a continuous FEM variable; FaceArg gradients are not
    # implemented for that functor type.
    old_wall_material = """  [ion_wall_flux]\n    type = PhysicsIonWallFluxMaterial\n"""
    new_wall_material = """  [ion_wall_flux]\n    type = PhysicsIonWallFluxMaterial\n    use_element_gradient_for_potential = true\n"""
    text = replace_once(text, old_wall_material, new_wall_material, "ion wall material")

    old_ion_bc = f"""  [ion_wall]\n    type = PhysicsFEMLogMolarIonWallBC\n    variable = log_ni\n    potential = potential\n    mobility = {base.ION_MU:.17g}\n    gas_temperature = {base.TG:.17g}\n    molar_mass = 0.032\n    charge_number = 1\n    sticking = 1.0\n    migration_gate_smoothing_width = 1.0e-3\n    boundary = '{base.GROUND}'\n  []\n"""
    text = replace_once(text, old_ion_bc, "", "FEM ion wall BC")

    fv_bc = f"""
[FVBCs]
  [ion_wall]
    type = FVFunctorNeumannBC
    variable = log_ni
    functor = ion_wall_number_flux
    factor = {-base.INV_NA:.17g}
    boundary = '{base.GROUND}'
  []
[]

"""
    text = replace_once(text, "\n[Postprocessors]\n", "\n" + fv_bc + "[Postprocessors]\n", "postprocessor insertion point")

    # Extend the validated 1 ns case from 100 to 300 steps. Keeping the
    # trajectory in a single Exodus file makes the 100 ns / 300 ns comparison
    # exact on the same mixed FE/FV discretization and mesh.
    old_time = f"""  dt = {base.DT:.17g}\n  num_steps = {base.NSTEPS}\n  end_time = {base.END_TIME:.17g}\n"""
    new_time = f"""  dt = {base.DT:.17g}\n  num_steps = {HYBRID_NSTEPS}\n  end_time = {HYBRID_END_TIME:.17g}\n"""
    text = replace_once(text, old_time, new_time, "Executioner time settings")

    return text


if __name__ == "__main__":
    out = Path(base.HERE) / "ion_fvm_hybrid_contour_dt1ns_300steps.i"
    out.write_text(build_case(), encoding="utf-8")
    print(f"wrote {out}")
    print("hybrid discretization: ne=FEM, O2+=FVM, electron energy=FEM, potential=FEM")
    print("FV ion drift reconstructs FE potential gradient from adjacent elements")
    print("FV ion wall migration uses the sided adjacent-element FE potential gradient")
    print("FV ion density enters existing charge/Poisson functor chain directly")
    print("ion drift interpolation: upwind")
    print("electron particle/energy wall BCs: thermal-only, unchanged from contour FEM baseline")
    print(f"dt={base.DT} s; steps={HYBRID_NSTEPS}; end_time={HYBRID_END_TIME} s")
