#!/usr/bin/env python3
"""Issue #306: heavy-charge motion discriminator built directly on Sequence 12.

Matrix:
  heavy = frozen / released
  chi_e = 1 / 10 / 20
  chi_h = 40
  heavy cycles = 2
  common final time = 80 initial dielectric-relaxation times

The fast child is rendered from the accepted Issue #253 Sequence-12 template
without changing its electron/Poisson/energy/Joule/O2-elastic physics.  The
released parent adds the previously accepted 1D heavy-flow BC topology plus
current Physics heavy transport, charged drift, and heavy mass-frame
electromigration correction.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.Issue253_g1_gummel_dt_release import prepare

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SOURCE253 = REPO / "experiments/Issue253_g1_gummel_dt_release"
GENERATED = ROOT / "generated"
RESULTS = ROOT / "results"
BUILD_BASE_REF = "ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"

CHI_H = 40.0
HEAVY_CYCLES = 2
FINAL_TAU = CHI_H * HEAVY_CYCLES
ENERGY_REFERENCE_EV = 5.73276
P_GAS_PA = 0.66661
TG_K = 300.0
Q_SCCM = 20.0
M_INLET = 0.032
VM_STD = 0.0224136
MDOT = Q_SCCM * 1.0e-6 / 60.0 * M_INLET / VM_STD
E_OVER_KB = 11604.518121550082

CASES = tuple(
    {"name": f"{mode}_chi{int(chi)}", "mode": mode, "chi": chi,
     "fp_max": {1.0: 100, 10.0: 300, 20.0: 600}[chi]}
    for mode in ("frozen", "released")
    for chi in (1.0, 10.0, 20.0)
)
CASE_NAMES = tuple(str(case["name"]) for case in CASES)

ELECTRON_MOMENTS = REPO / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
ELASTIC_DATA = REPO / "physics_app/data/electron_impact/o2_elastic.txt"
HEAVY_TRANSPORT_DATA = REPO / "experiments/Issue91_real_qvt_r3/r3_e0/transport_data.txt"

SOLVED_HEAVY = ("w_O2s", "w_O2p", "w_O", "w_Om", "w_Op", "w_Os")
CHARGED = {
    "w_O2p": ("D_mix_O2p", "mu_O2p", 1),
    "w_Om": ("D_mix_Om", "mu_Om", -1),
    "w_Op": ("D_mix_Op", "mu_Op", 1),
}


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _docker(script: str) -> None:
    _run(["docker", "pull", BUILD_BASE_REF])
    _run([
        "docker", "run", "--rm", "--entrypoint", "/bin/bash", "--user", "0:0",
        "--workdir", "/workspace", "-v", f"{REPO}:/workspace", BUILD_BASE_REF,
        "-lc", script,
    ])


def _silence_poisson(text: str) -> str:
    old = """[Outputs]
  csv = true
  exodus = true
  execute_on = 'INITIAL FINAL'
[]
"""
    new = """[Outputs]
  console = false
[]
"""
    if text.count(old) != 1:
        raise RuntimeError("Poisson Outputs block changed")
    return text.replace(old, new, 1)


def _set_fast_file_base(text: str) -> str:
    old = """[Outputs]
  [step_csv]
"""
    new = """[Outputs]
  file_base = fast_sub
  [step_csv]
"""
    if text.count(old) != 1:
        raise RuntimeError("Sequence-12 Outputs block changed")
    return text.replace(old, new, 1)


def _params(spec: dict[str, object]) -> dict[str, object]:
    tau = prepare.tau_epsilon()
    chi = float(spec["chi"])
    dt_e = chi * tau
    dt_h = CHI_H * tau
    end_time = FINAL_TAU * tau
    fast_steps = int(round(FINAL_TAU / chi))
    per_heavy = int(round(CHI_H / chi))
    if not math.isclose(dt_e * fast_steps, end_time, rel_tol=1e-14, abs_tol=1e-30):
        raise RuntimeError(f"{spec['name']}: fast horizon mismatch")
    if not math.isclose(dt_h * HEAVY_CYCLES, end_time, rel_tol=1e-14, abs_tol=1e-30):
        raise RuntimeError(f"{spec['name']}: heavy horizon mismatch")
    if not math.isclose(CHI_H / chi, per_heavy, rel_tol=0.0, abs_tol=1e-14):
        raise RuntimeError(f"{spec['name']}: non-integer subcycle ratio")
    return {
        "name": str(spec["name"]),
        "mode": str(spec["mode"]),
        "chi_e": chi,
        "chi_h": CHI_H,
        "tau_epsilon_initial_s": tau,
        "dt_e_s": dt_e,
        "dt_h_s": dt_h,
        "end_time_s": end_time,
        "end_time_tau_epsilon_initial": FINAL_TAU,
        "heavy_cycles": HEAVY_CYCLES,
        "fast_steps_total": fast_steps,
        "fast_steps_per_heavy_cycle": per_heavy,
        "fp_max": int(spec["fp_max"]),
        "relaxation_factor": 1.0 / (1.0 + chi),
    }


def _common_initial() -> dict[str, float]:
    return {
        "log_ce0": math.log(prepare.NE0 / prepare.NA),
        "w_O2p0": prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA),
        "w_Om0": 0.001,
        "w_Op0": 0.001,
    }


def _fast_child(p: dict[str, object]) -> str:
    template = (SOURCE253 / "elastic12_template.i").read_text(encoding="utf-8")
    init = _common_initial()
    text = prepare._render(
        template,
        {
            "LOG_CE": f"{init['log_ce0']:.17g}",
            "W_O2P": f"{init['w_O2p0']:.17g}",
            "NE0": f"{prepare.NE0:.17g}",
            "JOULE_FACTOR": "1.0",
            "ELASTIC_FACTOR": "1.0",
            "RELAXATION_FACTOR": f"{float(p['relaxation_factor']):.17g}",
            "DT": f"{float(p['dt_e_s']):.17g}",
            "END_TIME": f"{float(p['end_time_s']):.17g}",
            "STEPS": str(p["fast_steps_total"]),
            "FP_MAX": str(p["fp_max"]),
            "TIMESTEP_TOL": f"{max(float(p['dt_e_s']) * 1.0e-8, 1.0e-30):.17g}",
        },
    )
    return _set_fast_file_base(text)


def _poisson_child() -> str:
    init = _common_initial()
    template = (SOURCE253 / "poisson_template.i").read_text(encoding="utf-8")
    return _silence_poisson(prepare._render(
        template,
        {"LOG_CE": f"{init['log_ce0']:.17g}", "W_O2P": f"{init['w_O2p0']:.17g}"},
    ))


def _shared_parent_tail(p: dict[str, object], extra_postprocessors: str = "") -> str:
    return f"""
[MultiApps]
  [electron]
    type = TransientMultiApp
    input_files = 'fast_sub.i'
    execute_on = TIMESTEP_END
    sub_cycling = true
    output_sub_cycles = true
    print_sub_cycles = false
  []
[]

[Transfers]
  [heavy_to_fast]
    type = MultiAppCopyTransfer
    to_multi_app = electron
    source_variable = 'w_O2p w_Om w_Op'
    variable = 'w_O2p_h w_Om_h w_Op_h'
    execute_on = SAME_AS_MULTIAPP
  []
  [fast_to_parent]
    type = MultiAppCopyTransfer
    from_multi_app = electron
    source_variable = 'potential_from_poisson electron_density_out mean_energy_out'
    variable = 'potential_fast electron_density_fast mean_energy_fast'
    execute_on = SAME_AS_MULTIAPP
  []
[]

[Postprocessors]
{extra_postprocessors}
  [heavy_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = heavy_charge_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [net_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = net_charge_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_avg]
    type = ElementAverageFunctorPostprocessor
    functor = potential_fast
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_fast
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_fast
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [electron_density_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_density_fast
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [mean_energy_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_energy_fast
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_O2p_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Om_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_Op_avg]
    type = ElementAverageFunctorPostprocessor
    functor = w_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]

[VectorPostprocessors]
  [parent_profile]
    type = ElementValueSampler
    variable = 'w_O2p w_Om w_Op potential_fast electron_density_fast mean_energy_fast heavy_charge_out net_charge_out'
    sort_by = id
    execute_on = 'FINAL'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {float(p['dt_h_s']):.17g}
  dtmin = {float(p['dt_h_s']):.17g}
  dtmax = {float(p['dt_h_s']):.17g}
  end_time = {float(p['end_time_s']):.17g}
  num_steps = {HEAVY_CYCLES}
  timestep_tolerance = {max(float(p['dt_h_s']) * 1.0e-8, 1.0e-30):.17g}
  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-13
  nl_max_its = 80
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = false
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]

[Outputs]
  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
    new_row_tolerance = 1.0e-30
  []
  [final_csv]
    type = CSV
    execute_on = 'FINAL'
  []
  [final_exodus]
    type = Exodus
    execute_on = 'FINAL'
  []
[]
"""


def _charge_materials() -> str:
    return f"""
[FunctorMaterials]
  [charge_state]
    type = ADParsedFunctorMaterial
    property_name = heavy_charge_density
    functor_names = 'w_O2p w_Om w_Op'
    functor_symbols = 'o2p om op'
    expression = '{prepare.E_CHARGE:.17g}*{prepare.RHO:.17g}*{prepare.NA:.17g}*(o2p/0.032-om/0.016+op/0.016)'
  []
  [net_charge_state]
    type = ADParsedFunctorMaterial
    property_name = net_charge_density
    functor_names = 'heavy_charge_density electron_density_fast'
    functor_symbols = 'qh ne'
    expression = 'qh-{prepare.E_CHARGE:.17g}*ne'
  []
[]

[AuxKernels]
  [heavy_charge_copy]
    type = FunctorAux
    variable = heavy_charge_out
    functor = heavy_charge_density
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
  [net_charge_copy]
    type = FunctorAux
    variable = net_charge_out
    functor = net_charge_density
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
[]
"""


def _frozen_parent(p: dict[str, object]) -> str:
    init = _common_initial()
    return f"""# Issue #306 frozen-heavy A/B control.
# Same nested fast child and same heavy synchronization times as released mode.

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 20
  xmin = 0.0
  xmax = 0.01
[]

[Problem]
  kernel_coverage_check = false
  solve = false
[]

[AuxVariables]
  [w_O2s]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [w_O2p]
    type = MooseVariableFVReal
    initial_condition = {init['w_O2p0']:.17g}
  []
  [w_O]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [w_Om]
    type = MooseVariableFVReal
    initial_condition = {init['w_Om0']:.17g}
  []
  [w_Op]
    type = MooseVariableFVReal
    initial_condition = {init['w_Op0']:.17g}
  []
  [w_Os]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [potential_fast]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [electron_density_fast]
    type = MooseVariableFVReal
    initial_condition = {prepare.NE0:.17g}
  []
  [mean_energy_fast]
    type = MooseVariableFVReal
    initial_condition = {ENERGY_REFERENCE_EV:.17g}
  []
  [heavy_charge_out]
    type = MooseVariableFVReal
  []
  [net_charge_out]
    type = MooseVariableFVReal
  []
[]

{_charge_materials()}
{_shared_parent_tail(p)}
"""


def _released_parent(p: dict[str, object]) -> str:
    init = _common_initial()
    heavy_blocks = []
    for idx, species in enumerate(SOLVED_HEAVY, start=1):
        dname = {
            "w_O2s": "D_mix_O2s", "w_O2p": "D_mix_O2p", "w_O": "D_mix_O",
            "w_Om": "D_mix_Om", "w_Op": "D_mix_Op", "w_Os": "D_mix_Os",
        }[species]
        short = species.replace("w_", "")
        extra = ""
        if species in CHARGED:
            _, mu, charge = CHARGED[species]
            extra = f"""
  [{short}_electrostatic_drift]
    type = PhysicsFVElectrostaticDrift
    variable = {species}
    potential = potential_fast
    mobility = {mu}
    carrier = rho_const
    charge_number = {charge}
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
"""
        heavy_blocks.append(f"""
  [{short}_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = {species}
    rho = rho_const
  []
  [{short}_advection]
    type = PhysicsFVMassFractionAdvection
    variable = {species}
    rho = rho_const
  []
  [{short}_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = {species}
    rho = rho_const
    diffusivity = {dname}
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []
{extra}
  [{short}_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = {species}
    potential = potential_fast
    rho = rho_const
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []
""")
    kernels = "".join(heavy_blocks)
    species_bcs = "".join(
        f"""
  [inlet_{s.replace('w_', '')}]
    type = WCNSFVScalarFluxBC
    variable = {s}
    boundary = right
    passive_scalar = {s}
    scalar_flux_pp = inlet_mdot_{s.replace('w_', '')}
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
"""
        for s in SOLVED_HEAVY
    )
    receivers = "".join(
        f"""
  [inlet_mdot_{s.replace('w_', '')}]
    type = Receiver
    default = 0
  []
"""
        for s in SOLVED_HEAVY
    )
    flow_postprocessors = f"""
  [inlet_area]
    type = AreaPostprocessor
    boundary = right
    execute_on = INITIAL
  []
  [inlet_mdot]
    type = Receiver
    default = {MDOT:.17g}
  []
{receivers}
  [outlet_p_avg]
    type = SideAverageFunctorPostprocessor
    boundary = left
    functor = p
    restrict_to_functors_domain = true
    execute_on = 'INITIAL TIMESTEP_END'
  []
"""

    return f"""# Issue #306 released-heavy parent.
# BC topology is inherited from the accepted #234 1D heavy-flow discriminator:
# right 20 sccm pure-O2 inlet, left absolute-pressure outlet.
# The pressure value is held at the Sequence-12 gas state (0.66661 Pa) so the
# fast physics state is not changed while heavy motion is released.

[Mesh]
  type = GeneratedMesh
  dim = 1
  nx = 20
  xmin = 0.0
  xmax = 0.01
[]

[Problem]
  kernel_coverage_check = false
[]

[GlobalParams]
  rhie_chow_user_object = rc
  advected_interp_method = upwind
  velocity_interp_method = rc
[]

[UserObjects]
  [rc]
    type = INSFVRhieChowInterpolator
    u = u
    pressure = p
  []
[]

[Variables]
  [u]
    type = INSFVVelocityVariable
    initial_condition = 0.0
  []
  [p]
    type = INSFVPressureVariable
    initial_condition = {P_GAS_PA:.17g}
  []
  [w_O2s]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [w_O2p]
    type = MooseVariableFVReal
    initial_condition = {init['w_O2p0']:.17g}
  []
  [w_O]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [w_Om]
    type = MooseVariableFVReal
    initial_condition = {init['w_Om0']:.17g}
  []
  [w_Op]
    type = MooseVariableFVReal
    initial_condition = {init['w_Op0']:.17g}
  []
  [w_Os]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[AuxVariables]
  [potential_fast]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
  [electron_density_fast]
    type = MooseVariableFVReal
    initial_condition = {prepare.NE0:.17g}
  []
  [mean_energy_fast]
    type = MooseVariableFVReal
    initial_condition = {ENERGY_REFERENCE_EV:.17g}
  []
  [heavy_charge_out]
    type = MooseVariableFVReal
  []
  [net_charge_out]
    type = MooseVariableFVReal
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'T_g p_gas rho_const mu_flow'
    prop_values = '{TG_K:.17g} {P_GAS_PA:.17g} {prepare.RHO:.17g} 2.0e-5'
  []
  [electron_temperature_state]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_K
    functor_names = 'mean_energy_fast'
    functor_symbols = 'mean_ev'
    expression = '{(2.0 / 3.0) * E_OVER_KB:.17g}*mean_ev'
  []
  [O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2
    functor_names = 'w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 's1 s2 s3 s4 s5 s6'
    expression = '1.0-s1-s2-s3-s4-s5-s6'
  []
  [mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_mix
    functor_names = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'm0 m1 m2 m3 m4 m5 m6'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.032+m3/0.016+m4/0.016+m5/0.016+m6/0.016)'
  []
  [heavy_transport]
    type = PhysicsThermalDiffusionMaterial
    temperature = T_g
    pressure = p_gas
    electron_temperature = electron_temperature_K
    electron_number_density = electron_density_fast
    transport_data_file = transport_data.txt
    species = 'O2 O2s O2p O Om Op Os'
    mass_fractions = 'w_O2 w_O2s w_O2p w_O w_Om w_Op w_Os'
    D_mix_names = 'D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os'
    D_T_names = 'D_T_O2 D_T_O2s D_T_O2p D_T_O D_T_Om D_T_Op D_T_Os'
    kT_names = 'kT_O2 kT_O2s kT_O2p kT_O kT_Om kT_Op kT_Os'
  []
  [mobility_O2p]
    type = ADParsedFunctorMaterial
    property_name = mu_O2p
    functor_names = 'D_mix_O2p T_g'
    functor_symbols = 'd t'
    expression = '{E_OVER_KB:.17g}*d/t'
  []
  [mobility_Om]
    type = ADParsedFunctorMaterial
    property_name = mu_Om
    functor_names = 'D_mix_Om T_g'
    functor_symbols = 'd t'
    expression = '{E_OVER_KB:.17g}*d/t'
  []
  [mobility_Op]
    type = ADParsedFunctorMaterial
    property_name = mu_Op
    functor_names = 'D_mix_Op T_g'
    functor_symbols = 'd t'
    expression = '{E_OVER_KB:.17g}*d/t'
  []
  [charge_state]
    type = ADParsedFunctorMaterial
    property_name = heavy_charge_density
    functor_names = 'w_O2p w_Om w_Op'
    functor_symbols = 'o2p om op'
    expression = '{prepare.E_CHARGE:.17g}*{prepare.RHO:.17g}*{prepare.NA:.17g}*(o2p/0.032-om/0.016+op/0.016)'
  []
  [net_charge_state]
    type = ADParsedFunctorMaterial
    property_name = net_charge_density
    functor_names = 'heavy_charge_density electron_density_fast'
    functor_symbols = 'qh ne'
    expression = 'qh-{prepare.E_CHARGE:.17g}*ne'
  []
[]

[FVKernels]
  [mass]
    type = INSFVMassAdvection
    variable = p
    rho = rho_const
  []
  [u_advection]
    type = INSFVMomentumAdvection
    variable = u
    rho = rho_const
    momentum_component = x
  []
  [u_diffusion]
    type = INSFVMomentumDiffusion
    variable = u
    mu = mu_flow
    momentum_component = x
  []
  [u_pressure]
    type = INSFVMomentumPressure
    variable = u
    pressure = p
    momentum_component = x
  []
{kernels}
[]

[FVBCs]
  [inlet_mass]
    type = WCNSFVMassFluxBC
    variable = p
    boundary = right
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    direction = '-1 0 0'
  []
  [inlet_u]
    type = WCNSFVMomentumFluxBC
    variable = u
    boundary = right
    mdot_pp = inlet_mdot
    area_pp = inlet_area
    rho = rho_const
    vel_x = u
    momentum_component = x
    direction = '-1 0 0'
  []
{species_bcs}
  [outlet_p]
    type = INSFVOutletPressureBC
    variable = p
    boundary = left
    function = {P_GAS_PA:.17g}
  []
[]

[AuxKernels]
  [heavy_charge_copy]
    type = FunctorAux
    variable = heavy_charge_out
    functor = heavy_charge_density
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
  [net_charge_copy]
    type = FunctorAux
    variable = net_charge_out
    functor = net_charge_density
    execute_on = 'INITIAL TIMESTEP_END FINAL'
  []
[]

{_shared_parent_tail(p, flow_postprocessors)}
"""


def build(clean: bool = True) -> list[dict[str, object]]:
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)
    poisson = _poisson_child()
    built: list[dict[str, object]] = []
    fast_by_chi: dict[float, str] = {}

    for spec in CASES:
        p = _params(spec)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)
        fast = _fast_child(p)
        parent = _frozen_parent(p) if p["mode"] == "frozen" else _released_parent(p)
        (case_dir / "input.i").write_text(parent, encoding="utf-8")
        (case_dir / "fast_sub.i").write_text(fast, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(ELECTRON_MOMENTS, case_dir / "electron_moments.txt")
        shutil.copy2(ELASTIC_DATA, case_dir / "o2_elastic.txt")
        shutil.copy2(HEAVY_TRANSPORT_DATA, case_dir / "transport_data.txt")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        chi = float(p["chi_e"])
        if chi in fast_by_chi and fast_by_chi[chi] != fast:
            raise RuntimeError(f"fast child changed between heavy modes for chi={chi}")
        fast_by_chi[chi] = fast
        built.append(p)

    (GENERATED / "matrix.json").write_text(
        json.dumps({
            "issue": 306,
            "sequence": 1,
            "objective": "A/B heavy frozen vs released at equal T=80 tau",
            "chi_h": CHI_H,
            "heavy_cycles": HEAVY_CYCLES,
            "total_time_tau": FINAL_TAU,
            "fast_physics": "Issue253 Sequence12 unchanged",
            "heavy_bc_topology": "right 20 sccm pure-O2 inlet; left absolute-pressure outlet",
            "heavy_pressure_Pa": P_GAS_PA,
            "chemistry": False,
            "rf_heating": False,
            "cases": built,
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    by = {str(x["name"]): x for x in built}
    if set(by) != set(CASE_NAMES):
        raise RuntimeError("case set mismatch")
    for chi in (1.0, 10.0, 20.0):
        f = by[f"frozen_chi{int(chi)}"]
        r = by[f"released_chi{int(chi)}"]
        assert f["dt_e_s"] == r["dt_e_s"]
        assert f["end_time_s"] == r["end_time_s"]
        assert f["fast_steps_per_heavy_cycle"] == int(CHI_H / chi)
        frozen_fast = (GENERATED / str(f["name"]) / "fast_sub.i").read_text()
        released_fast = (GENERATED / str(r["name"]) / "fast_sub.i").read_text()
        assert frozen_fast == released_fast
        assert "PhysicsFVElectronEnergyJouleHeating" in frozen_fast
        assert "PhysicsFVElectronEnergyWallFluxBC" in frozen_fast
        assert "elastic_loss_applied" in frozen_fast
        assert "w_O2p_h" in frozen_fast and "w_Om_h" in frozen_fast and "w_Op_h" in frozen_fast
        assert "end_time = " + f"{float(f['end_time_s']):.17g}" in frozen_fast

        frozen_parent = (GENERATED / str(f["name"]) / "input.i").read_text()
        released_parent = (GENERATED / str(r["name"]) / "input.i").read_text()
        assert "solve = false" in frozen_parent
        assert "PhysicsFVConservativeMassFractionTimeDerivative" not in frozen_parent
        assert released_parent.count("type = PhysicsFVConservativeMassFractionTimeDerivative") == 6
        assert released_parent.count("type = PhysicsFVMassFractionAdvection") == 6
        assert released_parent.count("type = PhysicsFVMixtureAveragedDiffusion") == 6
        assert released_parent.count("type = PhysicsFVElectrostaticDrift") == 3
        assert released_parent.count("type = PhysicsFVHeavyMassElectromigrationCorrection") == 6
        assert "boundary = right" in released_parent and "type = WCNSFVMassFluxBC" in released_parent
        assert "boundary = left" in released_parent and "type = INSFVOutletPressureBC" in released_parent
        assert "boundaries_to_avoid = 'left right'" in released_parent
        for text in (frozen_parent, released_parent):
            assert "type = TransientMultiApp" in text
            assert "execute_on = TIMESTEP_END" in text
            assert "sub_cycling = true" in text
            assert "source_variable = 'w_O2p w_Om w_Op'" in text
            assert "variable = 'w_O2p_h w_Om_h w_Op_h'" in text
            assert "@@" not in text

    return {
        "status": "PASS",
        "issue": 306,
        "tau_epsilon_initial_s": prepare.tau_epsilon(),
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_time_tau": FINAL_TAU,
        "matrix": built,
        "control": "same nested fast child for frozen/released at each chi",
    }


def p0() -> None:
    summary = static_contract()
    print("ISSUE306_HEAVY_RELEASE_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = "; ".join(
        "python3 /workspace/bin/physics.py preflight "
        f"/workspace/{ROOT.relative_to(REPO)}/generated/{name}/input.i"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; " + commands
    )
    _docker(script)
    print("ISSUE306_HEAVY_RELEASE_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    rel = ROOT.relative_to(REPO)
    checks = "; ".join(
        f"cd /workspace/{rel}/generated/{name} && "
        "/workspace/physics_app/physics-opt --check-input -i input.i "
        f"> /workspace/{rel}/results/{name}_p2.log 2>&1"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        f"mkdir -p /workspace/{rel}/results; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + checks
    )
    _docker(script)
    print("ISSUE306_HEAVY_RELEASE_P2: PASS")


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _profile(case_dir: Path) -> list[dict[str, float]]:
    candidates: list[tuple[int, Path]] = []
    for path in case_dir.glob("input_final_csv_parent_profile_*.csv"):
        m = re.search(r"_([0-9]+)\.csv$", path.name)
        if m:
            candidates.append((int(m.group(1)), path))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: no parent final profile")
    _, path = max(candidates)
    out: list[dict[str, float]] = []
    for row in _rows(path):
        out.append({
            "x": float(row["x"]),
            "w_O2p": float(row["w_O2p"]),
            "w_Om": float(row["w_Om"]),
            "w_Op": float(row["w_Op"]),
            "potential": float(row["potential_fast"]),
            "electron_density": float(row["electron_density_fast"]),
            "mean_energy_eV": float(row["mean_energy_fast"]),
            "heavy_charge_C_m3": float(row["heavy_charge_out"]),
            "net_charge_C_m3": float(row["net_charge_out"]),
        })
    out.sort(key=lambda x: x["x"])
    return out


def inner_run(case_name: str) -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / case_name
    log = RESULTS / f"{case_name}_runtime.log"
    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app/physics-opt"), "-i", "input.i"],
            cwd=case_dir, stdout=handle, stderr=subprocess.STDOUT, check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{case_name}_returncode.txt").write_text(f"{completed.returncode}\n")
    (RESULTS / f"{case_name}_elapsed_seconds.txt").write_text(f"{elapsed:.9f}\n")
    return 0


def analyze_case(case_name: str) -> tuple[dict[str, object], int]:
    p = json.loads((GENERATED / case_name / "case.json").read_text())
    rc = int((RESULTS / f"{case_name}_returncode.txt").read_text().strip())
    elapsed = float((RESULTS / f"{case_name}_elapsed_seconds.txt").read_text().strip())
    rows = _rows(GENERATED / case_name / "input_step_csv.csv")
    result: dict[str, object] = {
        "case": case_name, "mode": p["mode"], "chi_e": p["chi_e"], "chi_h": p["chi_h"],
        "dt_e_s": p["dt_e_s"], "dt_h_s": p["dt_h_s"],
        "heavy_cycles_requested": p["heavy_cycles"],
        "fast_steps_per_heavy_cycle": p["fast_steps_per_heavy_cycle"],
        "elapsed_seconds": elapsed, "returncode": rc,
    }
    if rc != 0:
        result.update(classification="RUNTIME_FAILURE", evidence_valid=False)
        return result, 2
    if len(rows) != HEAVY_CYCLES + 1:
        result.update(
            classification="HEAVY_STEP_HISTORY_MISMATCH", evidence_valid=False,
            parent_rows=len(rows),
        )
        return result, 2
    final = rows[-1]
    if not math.isclose(float(final["time"]), float(p["end_time_s"]), rel_tol=1e-10, abs_tol=1e-24):
        result.update(classification="INCOMPLETE_HORIZON", evidence_valid=False)
        return result, 2
    profile = _profile(GENERATED / case_name)
    if not profile:
        result.update(classification="MISSING_FINAL_PROFILE", evidence_valid=False)
        return result, 2
    dx = 0.01 / len(profile)
    phi_values = [row["potential"] for row in profile]
    result.update({
        "classification": "CASE_CONVERGED",
        "evidence_valid": True,
        "final_time_s": float(final["time"]),
        "final_phi_avg_V": sum(phi_values) / len(phi_values),
        "final_phi_min_V": min(phi_values),
        "final_phi_max_V": max(phi_values),
        "final_heavy_charge_integral_C_m2": sum(
            row["heavy_charge_C_m3"] * dx for row in profile
        ),
        "final_net_charge_integral_C_m2": sum(
            row["net_charge_C_m3"] * dx for row in profile
        ),
        "final_electron_density_avg_m3": sum(
            row["electron_density"] for row in profile
        ) / len(profile),
        "final_mean_energy_avg_eV": sum(
            row["mean_energy_eV"] for row in profile
        ) / len(profile),
        "final_w_O2p_avg": sum(row["w_O2p"] for row in profile) / len(profile),
        "final_w_Om_avg": sum(row["w_Om"] for row in profile) / len(profile),
        "final_w_Op_avg": sum(row["w_Op"] for row in profile) / len(profile),
        "final_profile": profile,
    })
    return result, 0


def run_case(case_name: str) -> None:
    if not (REPO / "physics_app/physics-opt").exists():
        raise SystemExit("physics-opt missing")
    rel = ROOT.relative_to(REPO)
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        f"python3 /workspace/{rel}/control.py --inner-run {case_name}"
    )
    _docker(script)
    result, code = analyze_case(case_name)
    (RESULTS / f"{case_name}_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE306_HEAVY_RELEASE_CASE:", case_name, result["classification"])
    print(json.dumps(result, indent=2, sort_keys=True))
    if code:
        raise SystemExit(code)


def p3() -> None:
    build()
    rel = ROOT.relative_to(REPO)
    inner = "; ".join(
        f"python3 /workspace/{rel}/control.py --inner-run {name}"
        for name in CASE_NAMES
    )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        + inner
    )
    _docker(script)

    invalid: list[str] = []
    for name in CASE_NAMES:
        result, code = analyze_case(name)
        (RESULTS / f"{name}_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print("ISSUE306_HEAVY_RELEASE_CASE:", name, result["classification"])
        if code:
            invalid.append(name)

    summary = aggregate(RESULTS)
    (RESULTS / "issue306_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE306_HEAVY_RELEASE_P3:", summary["classification"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    if invalid or not bool(summary.get("evidence_valid")):
        raise SystemExit(2)


def _profile_error(a: list[dict[str, float]], b: list[dict[str, float]], key: str) -> float:
    scale = max(max(abs(x[key]) for x in a), 1.0e-30)
    return max(abs(x[key] - y[key]) for x, y in zip(a, b, strict=True)) / scale


def _offset_shape(a: list[dict[str, float]], b: list[dict[str, float]]) -> dict[str, float]:
    delta = [y["potential"] - x["potential"] for x, y in zip(a, b, strict=True)]
    mean_shift = sum(delta) / len(delta)
    centered = [d - mean_shift for d in delta]
    swing = max(x["potential"] for x in a) - min(x["potential"] for x in a)
    shape = max(abs(x) for x in centered) / max(abs(swing), 1.0e-30)
    ea = [-(a[i+1]["potential"]-a[i]["potential"])/(a[i+1]["x"]-a[i]["x"]) for i in range(len(a)-1)]
    eb = [-(b[i+1]["potential"]-b[i]["potential"])/(b[i+1]["x"]-b[i]["x"]) for i in range(len(b)-1)]
    eerr = max(abs(x-y) for x,y in zip(ea,eb, strict=True)) / max(max(abs(x) for x in ea), 1.0e-30)
    return {
        "mean_potential_shift_V": mean_shift,
        "offset_removed_shape_over_reference_swing": shape,
        "electric_field_einf": eerr,
    }


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text())
        if str(item.get("case")) in CASE_NAMES:
            found[str(item["case"])] = item
    missing = [x for x in CASE_NAMES if x not in found]
    if missing:
        raise RuntimeError(f"missing result(s): {missing}")
    if not all(bool(found[x].get("evidence_valid")) for x in CASE_NAMES):
        return {
            "issue": 306, "sequence": 1, "classification": "INVALID_EVIDENCE",
            "evidence_valid": False, "cases": found,
        }

    mode_comparisons: dict[str, object] = {}
    for mode in ("frozen", "released"):
        anchor = found[f"{mode}_chi1"]
        ap = anchor["final_profile"]
        for chi in (10, 20):
            name = f"{mode}_chi{chi}"
            item = found[name]
            pp = item["final_profile"]
            mode_comparisons[f"{name}_vs_{mode}_chi1"] = {
                "electron_density_einf": _profile_error(ap, pp, "electron_density"),
                "mean_energy_einf": _profile_error(ap, pp, "mean_energy_eV"),
                "raw_potential_einf": _profile_error(ap, pp, "potential"),
                "net_charge_einf": _profile_error(ap, pp, "net_charge_C_m3"),
                **_offset_shape(ap, pp),
            }

    contraction: dict[str, object] = {}
    for chi in (10, 20):
        f = mode_comparisons[f"frozen_chi{chi}_vs_frozen_chi1"]
        r = mode_comparisons[f"released_chi{chi}_vs_released_chi1"]
        fshift = abs(float(f["mean_potential_shift_V"]))
        rshift = abs(float(r["mean_potential_shift_V"]))
        contraction[f"chi{chi}"] = {
            "frozen_offset_V": f["mean_potential_shift_V"],
            "released_offset_V": r["mean_potential_shift_V"],
            "offset_magnitude_ratio_released_over_frozen": rshift / max(fshift, 1.0e-30),
            "offset_contraction_fraction": 1.0 - rshift / max(fshift, 1.0e-30),
        }

    return {
        "issue": 306,
        "sequence": 1,
        "classification": "HEAVY_RELEASE_2CYCLE_EVIDENCE_COMPLETE",
        "evidence_valid": True,
        "chi_h": CHI_H,
        "heavy_cycles": HEAVY_CYCLES,
        "total_time_tau": FINAL_TAU,
        "cases": found,
        "mode_comparisons": mode_comparisons,
        "offset_contraction": contraction,
        "terminal_interpretation": "UNSET_EVIDENCE_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2", "p3"))
    parser.add_argument("--case", choices=CASE_NAMES)
    parser.add_argument("--inner-run", choices=CASE_NAMES)
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.inner_run:
        return inner_run(args.inner_run)
    if args.case:
        run_case(args.case)
        return 0
    if args.aggregate:
        root = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
        if not root:
            raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
        summary = aggregate(Path(root))
        (RESULTS / "issue306_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        print("ISSUE306_HEAVY_RELEASE_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2, "p3": p3}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
