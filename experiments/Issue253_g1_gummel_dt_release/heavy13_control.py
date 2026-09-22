#!/usr/bin/env python3
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
GENERATED = ROOT / "generated_heavy13"
RESULTS = ROOT / "results_heavy13"
BUILD_BASE_REF = (
    "ghcr.io/hyungseonsong-plasma/physics-build-base@"
    "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
)

ENERGY_REFERENCE_EV = 5.73276
FINAL_TAU = 80.0
HEAVY_DT_TAU = 40.0
HEAVY_STEPS = 2
RHO = prepare.RHO
NA = prepare.NA
E_CHARGE = prepare.E_CHARGE
EPS0 = prepare.EPS0
TG = 300.0
P_GAS = 0.66661
E_OVER_KB = 11604.518121550082

HEAVY_SOLVED = ("O2s", "O2p", "O", "Om", "Op", "Os")
CHARGED = {
    "O2p": (1, 0.032),
    "Om": (-1, 0.016),
    "Op": (1, 0.016),
}
INITIAL_W = {
    "O2s": 0.0,
    "O2p": prepare.NE0 * prepare.M_O2P / (prepare.RHO * prepare.NA),
    "O": 0.0,
    "Om": 0.001,
    "Op": 0.001,
    "Os": 0.0,
}

CASE_SPECS = (
    {"name": "frozen_chi1", "mode": "frozen", "chi": 1.0, "fp_max": 100},
    {"name": "frozen_chi10", "mode": "frozen", "chi": 10.0, "fp_max": 300},
    {"name": "frozen_chi20", "mode": "frozen", "chi": 20.0, "fp_max": 600},
    {"name": "heavy_chi1", "mode": "released", "chi": 1.0, "fp_max": 100},
    {"name": "heavy_chi10", "mode": "released", "chi": 10.0, "fp_max": 300},
    {"name": "heavy_chi20", "mode": "released", "chi": 20.0, "fp_max": 600},
)
CASE_NAMES = tuple(str(x["name"]) for x in CASE_SPECS)

TRANSPORT_SOURCE = REPO / "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
HEAVY_TRANSPORT_SOURCE = REPO / "experiments/Issue91_real_qvt_r3/r3_e0/transport_data.txt"
ELASTIC_SOURCE = REPO / "physics_app/data/electron_impact/o2_elastic.txt"


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _docker(script: str) -> None:
    _run(["docker", "pull", BUILD_BASE_REF])
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            "--user",
            "0:0",
            "--workdir",
            "/workspace",
            "-v",
            f"{REPO}:/workspace",
            BUILD_BASE_REF,
            "-lc",
            script,
        ]
    )


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


def _augment_poisson(text: str) -> str:
    anchor = """  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    execute_on = 'INITIAL FINAL'
  []
[]
"""
    replacement = """  [phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_plasma
    value_type = max
    execute_on = 'INITIAL FINAL'
  []
  [gauss_flux_reduced]
    type = SideDiffusiveFluxIntegral
    variable = potential_plasma
    boundary = 'left right'
    functor_diffusivity = relative_permittivity
    execute_on = 'INITIAL FINAL'
  []
  [gauss_flux_charge]
    type = ScalePostprocessor
    value = gauss_flux_reduced
    scaling_factor = 8.8541878128e-12
    execute_on = 'INITIAL FINAL'
  []
[]
"""
    if text.count(anchor) != 1:
        raise RuntimeError("Poisson postprocessor anchor changed")
    return text.replace(anchor, replacement, 1)


def _augment_fast(text: str) -> str:
    transfer_anchor = """  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = potential_plasma
    variable = potential_from_poisson
    execute_on = SAME_AS_MULTIAPP
  []
[]
"""
    transfer_replacement = """  [phi_from_poisson]
    type = MultiAppCopyTransfer
    from_multi_app = poisson
    source_variable = potential_plasma
    variable = potential_from_poisson
    execute_on = SAME_AS_MULTIAPP
  []
  [charge_from_poisson]
    type = MultiAppPostprocessorTransfer
    from_multi_app = poisson
    from_postprocessor = charge_integral
    to_postprocessor = poisson_charge_C_m2
    reduction_type = average
    execute_on = SAME_AS_MULTIAPP
  []
  [gauss_from_poisson]
    type = MultiAppPostprocessorTransfer
    from_multi_app = poisson
    from_postprocessor = gauss_flux_charge
    to_postprocessor = poisson_gauss_charge_C_m2
    reduction_type = average
    execute_on = SAME_AS_MULTIAPP
  []
[]
"""
    if text.count(transfer_anchor) != 1:
        raise RuntimeError("fast transfer anchor changed")
    text = text.replace(transfer_anchor, transfer_replacement, 1)

    pp_anchor = """  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
[]
"""
    pp_replacement = """  [cumulative_fixed_point_iterations]
    type = CumulativeValuePostprocessor
    postprocessor = fixed_point_iterations
    execute_on = 'TIMESTEP_END'
  []
  [poisson_charge_C_m2]
    type = Receiver
    default = 0
    execute_on = 'INITIAL TIMESTEP_END TRANSFER'
  []
  [poisson_gauss_charge_C_m2]
    type = Receiver
    default = 0
    execute_on = 'INITIAL TIMESTEP_END TRANSFER'
  []
[]
"""
    if text.count(pp_anchor) != 1:
        raise RuntimeError("fast postprocessor anchor changed")
    text = text.replace(pp_anchor, pp_replacement, 1)

    text = text.replace(
        """  [step_csv]
    type = CSV
    execute_on = 'INITIAL TIMESTEP_END'
""",
        """  [step_csv]
    type = CSV
    file_base = fast_step
    execute_on = 'INITIAL TIMESTEP_END'
""",
        1,
    )
    text = text.replace(
        """  [final_csv]
    type = CSV
    execute_on = 'FINAL'
""",
        """  [final_csv]
    type = CSV
    file_base = fast_final
    execute_on = 'FINAL'
""",
        1,
    )
    text = text.replace(
        """  [final_exodus]
    type = Exodus
    execute_on = 'FINAL'
""",
        """  [final_exodus]
    type = Exodus
    file_base = fast_final_exodus
    execute_on = 'FINAL'
""",
        1,
    )
    return text


def _case_params(spec: dict[str, object]) -> dict[str, object]:
    tau = prepare.tau_epsilon()
    chi = float(spec["chi"])
    dt_fast = chi * tau
    dt_heavy = HEAVY_DT_TAU * tau
    end_time = FINAL_TAU * tau
    fast_steps = int(round(FINAL_TAU / chi))
    subcycles = int(round(HEAVY_DT_TAU / chi))
    if not math.isclose(dt_heavy * HEAVY_STEPS, end_time, rel_tol=1.0e-14, abs_tol=1.0e-30):
        raise RuntimeError("heavy dt does not hit common final time")
    if not math.isclose(dt_fast * fast_steps, end_time, rel_tol=1.0e-14, abs_tol=1.0e-30):
        raise RuntimeError(f"{spec['name']}: fast dt does not hit common final time")
    if not math.isclose(HEAVY_DT_TAU / chi, subcycles, rel_tol=0.0, abs_tol=1.0e-12):
        raise RuntimeError(f"{spec['name']}: non-integer heavy/fast subcycle ratio")
    return {
        "name": str(spec["name"]),
        "mode": str(spec["mode"]),
        "heavy_enabled": str(spec["mode"]) == "released",
        "heavy_factor": 1.0 if str(spec["mode"]) == "released" else 0.0,
        "chi_e": chi,
        "tau_epsilon_initial_s": tau,
        "dt_fast_s": dt_fast,
        "dt_heavy_s": dt_heavy,
        "end_time_s": end_time,
        "end_time_tau_epsilon_initial": FINAL_TAU,
        "heavy_dt_tau_epsilon_initial": HEAVY_DT_TAU,
        "heavy_steps": HEAVY_STEPS,
        "fast_steps": fast_steps,
        "fast_subcycles_per_heavy_step": subcycles,
        "fp_max": int(spec["fp_max"]),
        "relaxation_factor": 1.0 / (1.0 + chi),
        "heavy_scope": (
            "bulk N-1 oxygen heavy transport: transient mixture diffusion + "
            "charged drift + heavy mass-average electromigration correction; "
            "no heavy flow, chemistry, or wall reaction/loss"
        ),
    }


def _heavy_parent_input(p: dict[str, object]) -> str:
    w = INITIAL_W
    species_order = "O2 O2s O2p O Om Op Os"
    mass_fraction_order = "w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os"
    d_names = "D_mix_O2 D_mix_O2s D_mix_O2p D_mix_O D_mix_Om D_mix_Op D_mix_Os"
    dt = float(p["dt_heavy_s"])
    end_time = float(p["end_time_s"])
    heavy_factor = float(p["heavy_factor"])
    log_ce0 = math.log(prepare.NE0 / prepare.NA)

    variable_blocks = "\n".join(
        f"""  [w_{sp}]
    type = MooseVariableFVReal
    initial_condition = {w[sp]:.17g}
  []"""
        for sp in HEAVY_SOLVED
    )

    d_eff_blocks = "\n".join(
        f"""  [D_eff_{sp}]
    type = ADParsedFunctorMaterial
    property_name = D_eff_{sp}
    functor_names = 'D_mix_{sp} heavy_factor'
    functor_symbols = 'd fac'
    expression = 'fac*d'
  []"""
        for sp in HEAVY_SOLVED
    )

    density_blocks = "\n".join(
        f"""  [n_{sp}]
    type = ADParsedFunctorMaterial
    property_name = n_{sp}_m3
    functor_names = 'rho_const w_{sp}'
    functor_symbols = 'rho wf'
    expression = 'rho*wf*6.02214076e23/{mass:.17g}'
  []"""
        for sp, (_, mass) in CHARGED.items()
    )

    mobility_blocks = "\n".join(
        f"""  [mu_{sp}]
    type = ADParsedFunctorMaterial
    property_name = mu_{sp}
    functor_names = 'D_mix_{sp} T_g heavy_factor'
    functor_symbols = 'd tg fac'
    expression = 'fac*11604.518121550082*d/tg'
  []"""
        for sp in CHARGED
    )

    kernel_blocks: list[str] = []
    for sp in HEAVY_SOLVED:
        kernel_blocks.append(
            f"""  [{sp}_time]
    type = PhysicsFVConservativeMassFractionTimeDerivative
    variable = w_{sp}
    rho = rho_const
  []
  [{sp}_diffusion]
    type = PhysicsFVMixtureAveragedDiffusion
    variable = w_{sp}
    rho = rho_const
    diffusivity = D_eff_{sp}
    mean_molar_mass = Mn_mix
    include_molar_mass_gradient = true
  []"""
        )
    for sp, (charge, _) in CHARGED.items():
        kernel_blocks.append(
            f"""  [{sp}_electrostatic_drift]
    type = PhysicsFVElectrostaticDrift
    variable = w_{sp}
    potential = potential_fast
    mobility = mu_{sp}
    carrier = rho_const
    charge_number = {charge}
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []"""
        )
    for sp in HEAVY_SOLVED:
        kernel_blocks.append(
            f"""  [{sp}_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_{sp}
    potential = potential_fast
    rho = rho_const
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = 'left right'
  []"""
        )

    extreme_pp = "\n".join(
        f"""  [w_{sp}_min]
    type = ADElementExtremeFunctorValue
    functor = w_{sp}
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [w_{sp}_max]
    type = ADElementExtremeFunctorValue
    functor = w_{sp}
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []"""
        for sp in HEAVY_SOLVED
    )

    return f"""# Issue #253 Sequence 13: charged-heavy release parent.
# Exactly two heavy intervals, each 40 initial dielectric-relaxation times.
# Fast electron/Poisson/energy child subcycles at chi_e=1,10,20.
# Heavy factor is 0 for the frozen A control and 1 for the released B case.
# Heavy wall loss, heavy flow, and heavy chemistry remain OFF in this discriminator.

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

[Variables]
{variable_blocks}
[]

[AuxVariables]
  [log_e_fast]
    type = MooseVariableFVReal
    initial_condition = {log_ce0:.17g}
  []
  [n_epsilon_fast]
    type = MooseVariableFVReal
    initial_condition = 1.0
  []
  [potential_fast]
    type = MooseVariableFVReal
    initial_condition = 0.0
  []
[]

[FunctorMaterials]
  [constants]
    type = ADGenericFunctorMaterial
    prop_names = 'rho_const p_gas T_g heavy_factor'
    prop_values = '{RHO:.17g} {P_GAS:.17g} {TG:.17g} {heavy_factor:.17g}'
  []
  [w_O2_constraint_material]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 's1 s2 s3 s4 s5 s6'
    expression = '1.0-s1-s2-s3-s4-s5-s6'
  []
  [sum_w_material]
    type = ADParsedFunctorMaterial
    property_name = sum_w_functor
    functor_names = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'q0 q1 q2 q3 q4 q5 q6'
    expression = 'q0+q1+q2+q3+q4+q5+q6'
  []
  [mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_mix
    functor_names = 'w_O2_constraint w_O2s w_O2p w_O w_Om w_Op w_Os'
    functor_symbols = 'm0 m1 m2 m3 m4 m5 m6'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.032+m3/0.016+m4/0.016+m5/0.016+m6/0.016)'
  []
  [electron_density_parent]
    type = ADParsedFunctorMaterial
    property_name = electron_density_m3
    functor_names = 'log_e_fast'
    functor_symbols = 'loge'
    expression = '6.02214076e23*exp(loge)'
  []
  [electron_density_hat_parent]
    type = ADParsedFunctorMaterial
    property_name = electron_density_hat
    functor_names = 'electron_density_m3'
    functor_symbols = 'ne'
    expression = 'ne/1.0e16'
  []
  [mean_energy_parent]
    type = ADParsedFunctorMaterial
    property_name = mean_en_parent
    functor_names = 'n_epsilon_fast electron_density_hat'
    functor_symbols = 'epshat nehat'
    expression = '{ENERGY_REFERENCE_EV:.17g}*epshat/nehat'
  []
  [electron_temperature_parent]
    type = ADParsedFunctorMaterial
    property_name = electron_temperature_K
    functor_names = 'mean_en_parent'
    functor_symbols = 'meanE'
    expression = '(2.0/3.0)*11604.518121550082*meanE'
  []
  [heavy_transport]
    type = PhysicsThermalDiffusionMaterial
    temperature = T_g
    pressure = p_gas
    electron_temperature = electron_temperature_K
    electron_number_density = electron_density_m3
    transport_data_file = transport_data.txt
    species = '{species_order}'
    mass_fractions = '{mass_fraction_order}'
    D_mix_names = '{d_names}'
  []
{d_eff_blocks}
{mobility_blocks}
{density_blocks}
  [parent_charge]
    type = PhysicsPlasmaChargeDensityMaterial
    density = rho_const
    electron_density = electron_density_m3
    ion_ids = 'O2p Om Op'
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_molar_masses = '0.032 0.016 0.016'
    ion_charges = '1 -1 1'
  []
[]

[FVKernels]
{chr(10).join(kernel_blocks)}
[]

[MultiApps]
  [fast]
    type = TransientMultiApp
    input_files = fast_sub.i
    execute_on = TIMESTEP_END
    sub_cycling = true
    output_sub_cycles = true
    print_sub_cycles = false
  []
[]

[Transfers]
  [heavy_to_fast]
    type = MultiAppCopyTransfer
    to_multi_app = fast
    source_variable = 'w_O2p w_Om w_Op'
    variable = 'w_O2p_h w_Om_h w_Op_h'
    execute_on = SAME_AS_MULTIAPP
  []
  [fast_state_from_fast]
    type = MultiAppCopyTransfer
    from_multi_app = fast
    source_variable = 'log_e n_epsilon potential_from_poisson'
    variable = 'log_e_fast n_epsilon_fast potential_fast'
    execute_on = SAME_AS_MULTIAPP
  []
[]

[Postprocessors]
  [heavy_charge_integral_C_m2]
    type = ADElementIntegralFunctorPostprocessor
    functor = charge_density
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sum_w_min]
    type = ADElementExtremeFunctorValue
    functor = sum_w_functor
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [sum_w_max]
    type = ADElementExtremeFunctorValue
    functor = sum_w_functor
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_fast_min]
    type = ADElementExtremeFunctorValue
    functor = potential_fast
    value_type = min
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [potential_fast_max]
    type = ADElementExtremeFunctorValue
    functor = potential_fast
    value_type = max
    execute_on = 'INITIAL TIMESTEP_END'
  []
{extreme_pp}
[]

[VectorPostprocessors]
  [heavy_profile]
    type = ElementValueSampler
    variable = 'w_O2s w_O2p w_O w_Om w_Op w_Os potential_fast log_e_fast n_epsilon_fast'
    sort_by = id
    execute_on = 'FINAL'
  []
[]

[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {dt:.17g}
  dtmin = {dt:.17g}
  dtmax = {dt:.17g}
  end_time = {end_time:.17g}
  num_steps = {HEAVY_STEPS}
  timestep_tolerance = {max(dt * 1.0e-8, 1.0e-30):.17g}
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
  [parent_step]
    type = CSV
    file_base = parent_step
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [parent_final]
    type = CSV
    file_base = parent_final
    execute_on = 'FINAL'
  []
[]
"""


def build(clean: bool = True) -> list[dict[str, object]]:
    fast_template = (ROOT / "elastic12_template.i").read_text(encoding="utf-8")
    poisson_template = (ROOT / "poisson_template.i").read_text(encoding="utf-8")
    if clean and GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir(parents=True, exist_ok=True)

    log_ce0 = math.log(prepare.NE0 / prepare.NA)
    w_o2p0 = INITIAL_W["O2p"]
    built: list[dict[str, object]] = []

    for spec in CASE_SPECS:
        p = _case_params(spec)
        case_dir = GENERATED / str(p["name"])
        case_dir.mkdir(parents=True, exist_ok=True)

        fast = prepare._render(
            fast_template,
            {
                "LOG_CE": f"{log_ce0:.17g}",
                "W_O2P": f"{w_o2p0:.17g}",
                "NE0": f"{prepare.NE0:.17g}",
                "JOULE_FACTOR": "1.0",
                "ELASTIC_FACTOR": "1.0",
                "RELAXATION_FACTOR": f"{float(p['relaxation_factor']):.17g}",
                "DT": f"{float(p['dt_fast_s']):.17g}",
                "END_TIME": f"{float(p['end_time_s']):.17g}",
                "STEPS": str(p["fast_steps"]),
                "FP_MAX": str(p["fp_max"]),
                "TIMESTEP_TOL": f"{max(float(p['dt_fast_s']) * 1.0e-8, 1.0e-30):.17g}",
            },
        )
        fast = _augment_fast(fast)
        fast = fast.replace(
            "# Joule heating and O2 elastic energy exchange are ON; heavy evolution is frozen.",
            "# Joule heating and O2 elastic energy exchange are ON; heavy charge is supplied by the parent.",
            1,
        )
        fast = fast.replace(
            "# Sequence 12 compares chi=1,10,20 at equal T=100 initial dielectric-relaxation times.",
            "# Sequence 13 compares frozen/released heavy charge at equal T=80 initial dielectric-relaxation times.",
            1,
        )

        poisson = prepare._render(
            poisson_template,
            {"LOG_CE": f"{log_ce0:.17g}", "W_O2P": f"{w_o2p0:.17g}"},
        )
        poisson = _augment_poisson(poisson)
        poisson = _silence_poisson(poisson)

        (case_dir / "input.i").write_text(_heavy_parent_input(p), encoding="utf-8")
        (case_dir / "fast_sub.i").write_text(fast, encoding="utf-8")
        (case_dir / "poisson_sub.i").write_text(poisson, encoding="utf-8")
        shutil.copy2(TRANSPORT_SOURCE, case_dir / "electron_moments.txt")
        shutil.copy2(HEAVY_TRANSPORT_SOURCE, case_dir / "transport_data.txt")
        shutil.copy2(ELASTIC_SOURCE, case_dir / "o2_elastic.txt")
        (case_dir / "case.json").write_text(
            json.dumps(p, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        built.append(p)

    (GENERATED / "matrix.json").write_text(
        json.dumps(
            {
                "issue": 253,
                "sequence": 13,
                "objective": (
                    "A/B discriminator for chi-dependent potential offset: preserve the "
                    "Sequence-12 fast electron/Poisson/energy subsystem while releasing "
                    "bulk charged-heavy transport on dt_h=40 tau_epsilon"
                ),
                "equal_final_time": True,
                "total_time_tau_epsilon_initial": FINAL_TAU,
                "heavy_dt_tau_epsilon_initial": HEAVY_DT_TAU,
                "heavy_steps": HEAVY_STEPS,
                "heavy_wall_loss": "OFF",
                "heavy_flow": "OFF",
                "heavy_chemistry": "OFF",
                "cases": built,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return built


def static_contract() -> dict[str, object]:
    built = build()
    by_name = {str(x["name"]): x for x in built}
    assert len(by_name) == 6
    for chi in (1, 10, 20):
        frozen = by_name[f"frozen_chi{chi}"]
        heavy = by_name[f"heavy_chi{chi}"]
        assert frozen["heavy_enabled"] is False
        assert heavy["heavy_enabled"] is True
        assert frozen["fast_subcycles_per_heavy_step"] == int(HEAVY_DT_TAU / chi)
        assert heavy["fast_subcycles_per_heavy_step"] == int(HEAVY_DT_TAU / chi)
        assert frozen["heavy_steps"] == HEAVY_STEPS == heavy["heavy_steps"]
        assert math.isclose(
            float(frozen["end_time_s"]), float(heavy["end_time_s"]), rel_tol=0.0, abs_tol=0.0
        )

    for name, p in by_name.items():
        parent = (GENERATED / name / "input.i").read_text(encoding="utf-8")
        fast = (GENERATED / name / "fast_sub.i").read_text(encoding="utf-8")
        poisson = (GENERATED / name / "poisson_sub.i").read_text(encoding="utf-8")
        assert parent.count("PhysicsFVConservativeMassFractionTimeDerivative") == 6
        assert parent.count("PhysicsFVMixtureAveragedDiffusion") == 6
        assert parent.count("type = PhysicsFVElectrostaticDrift") == 3
        assert parent.count("PhysicsFVHeavyMassElectromigrationCorrection") == 6
        assert "type = TransientMultiApp" in parent
        assert "execute_on = TIMESTEP_END" in parent
        assert "sub_cycling = true" in parent
        assert "source_variable = 'w_O2p w_Om w_Op'" in parent
        assert "variable = 'w_O2p_h w_Om_h w_Op_h'" in parent
        assert f"prop_values = '{RHO:.17g} {P_GAS:.17g} {TG:.17g} {float(p['heavy_factor']):.17g}'" in parent
        assert "PhysicsFVLogMolarElectronTimeDerivative" in fast
        assert "PhysicsFVElectronEnergyJouleHeating" in fast
        assert "PhysicsElectronImpactRateMaterial" in fast
        assert "poisson_charge_C_m2" in fast and "poisson_gauss_charge_C_m2" in fast
        assert "w_O2p_h" in fast and "w_Om_h" in fast and "w_Op_h" in fast
        assert "gauss_flux_charge" in poisson
        assert "@@" not in parent and "@@" not in fast and "@@" not in poisson

    return {
        "status": "PASS",
        "issue": 253,
        "sequence": 13,
        "tau_epsilon_initial_s": prepare.tau_epsilon(),
        "total_time_tau_epsilon_initial": FINAL_TAU,
        "heavy_dt_tau_epsilon_initial": HEAVY_DT_TAU,
        "heavy_steps": HEAVY_STEPS,
        "cases": built,
        "scope": (
            "bulk heavy release only; wall loss/chemistry/flow remain frozen so this tests "
            "charge redistribution before any full heavy-wall closure claim"
        ),
    }


def p0() -> None:
    summary = static_contract()
    print("ISSUE253_G3_HEAVY13_P0: PASS")
    print(json.dumps(summary, indent=2, sort_keys=True))


def p1() -> None:
    build()
    commands = []
    for name in CASE_NAMES:
        rel = (GENERATED / name / "input.i").relative_to(REPO)
        commands.append(f"python3 /workspace/bin/physics.py preflight /workspace/{rel}")
    script = (
        "set -euo pipefail; source /environment; export PYTHONPATH=/workspace; "
        "uv pip install --system --python \"$(command -v python3)\" "
        "-r /workspace/requirements-evidence-engine.txt; "
        "python3 /workspace/bin/physics.py preflight --self-test; "
        + "; ".join(commands)
    )
    _docker(script)
    print("ISSUE253_G3_HEAVY13_P1: PASS")


def p2() -> None:
    if not GENERATED.exists():
        build()
    checks: list[str] = []
    for name in CASE_NAMES:
        case = f"/workspace/{GENERATED.relative_to(REPO)}/{name}"
        checks.append(
            f"cd {case} && /workspace/physics_app/physics-opt --check-input -i input.i "
            f"> /workspace/{RESULTS.relative_to(REPO)}/{name}_parent_p2.log 2>&1"
        )
        checks.append(
            f"cd {case} && /workspace/physics_app/physics-opt --check-input -i fast_sub.i "
            f"> /workspace/{RESULTS.relative_to(REPO)}/{name}_fast_p2.log 2>&1"
        )
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; "
        f"mkdir -p /workspace/{RESULTS.relative_to(REPO)}; "
        "make -C /workspace/physics_app -j2; test -x /workspace/physics_app/physics-opt; "
        + "; ".join(checks)
    )
    _docker(script)
    print("ISSUE253_G3_HEAVY13_P2: PASS")


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _latest_profile(case_dir: Path, token: str) -> list[dict[str, float]]:
    candidates: list[tuple[int, Path]] = []
    for path in case_dir.rglob(f"*{token}*.csv"):
        match = re.search(r"_([0-9]+)\.csv$", path.name)
        rank = int(match.group(1)) if match else 0
        if path.is_file() and path.stat().st_size > 0:
            candidates.append((rank, path))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: no profile matching {token}")
    _, path = max(candidates, key=lambda item: (item[0], item[1].stat().st_mtime_ns))
    rows = _rows(path)
    if not rows:
        raise RuntimeError(f"{case_dir.name}: empty profile {path}")
    out: list[dict[str, float]] = []
    for row in rows:
        item = {"x": float(row["x"])}
        for key, value in row.items():
            if key != "x" and value not in (None, ""):
                item[key] = float(value)
        out.append(item)
    out.sort(key=lambda item: item["x"])
    return out


def _find_csv(case_dir: Path, filename: str) -> Path:
    matches = [p for p in case_dir.rglob(filename) if p.is_file()]
    if not matches:
        raise RuntimeError(f"{case_dir.name}: missing {filename}")
    return max(matches, key=lambda p: p.stat().st_size)


def inner_run(case_name: str) -> int:
    if case_name not in CASE_NAMES:
        raise SystemExit(f"unknown case {case_name}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    case_dir = GENERATED / case_name
    log_path = RESULTS / f"{case_name}_runtime.log"
    started = time.perf_counter()
    with log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [str(REPO / "physics_app" / "physics-opt"), "-i", "input.i"],
            cwd=case_dir,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.perf_counter() - started
    (RESULTS / f"{case_name}_returncode.txt").write_text(
        f"{completed.returncode}\n", encoding="utf-8"
    )
    (RESULTS / f"{case_name}_elapsed_seconds.txt").write_text(
        f"{elapsed:.9f}\n", encoding="utf-8"
    )
    return 0


def _f(row: dict[str, str], name: str) -> float:
    return float(row[name])


def _combine_profile(
    heavy: list[dict[str, float]], fast: list[dict[str, float]]
) -> list[dict[str, float]]:
    if len(heavy) != len(fast):
        raise RuntimeError("heavy/fast profile point count mismatch")
    combined: list[dict[str, float]] = []
    for h, f in zip(heavy, fast):
        if not math.isclose(h["x"], f["x"], rel_tol=0.0, abs_tol=1.0e-12):
            raise RuntimeError("heavy/fast profile coordinate mismatch")
        ne = f["electron_density_out"]
        n_o2p = RHO * h["w_O2p"] * NA / 0.032
        n_om = RHO * h["w_Om"] * NA / 0.016
        n_op = RHO * h["w_Op"] * NA / 0.016
        charge_number_imbalance = n_o2p + n_op - n_om - ne
        combined.append(
            {
                "x": h["x"],
                "electron_density": ne,
                "potential": f["potential_from_poisson"],
                "mean_energy_eV": f["mean_energy_out"],
                "w_O2p": h["w_O2p"],
                "w_Om": h["w_Om"],
                "w_Op": h["w_Op"],
                "n_O2p": n_o2p,
                "n_Om": n_om,
                "n_Op": n_op,
                "charge_number_imbalance_m3": charge_number_imbalance,
            }
        )
    return combined


def analyze_case(case_name: str) -> tuple[dict[str, object], int]:
    case_dir = GENERATED / case_name
    p = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    rc = int((RESULTS / f"{case_name}_returncode.txt").read_text().strip())
    elapsed = float((RESULTS / f"{case_name}_elapsed_seconds.txt").read_text().strip())
    log_text = (RESULTS / f"{case_name}_runtime.log").read_text(
        encoding="utf-8", errors="replace"
    )
    result: dict[str, object] = {
        "case": case_name,
        "mode": p["mode"],
        "heavy_enabled": p["heavy_enabled"],
        "chi_e": p["chi_e"],
        "dt_fast_s": p["dt_fast_s"],
        "dt_heavy_s": p["dt_heavy_s"],
        "fast_subcycles_per_heavy_step": p["fast_subcycles_per_heavy_step"],
        "heavy_steps_requested": p["heavy_steps"],
        "elapsed_seconds": elapsed,
        "returncode": rc,
    }
    if rc != 0:
        result["classification"] = (
            "GUMMEL_DIVERGED_MAX_ITS"
            if "DIVERGED_MAX_ITS" in log_text
            else "RUNTIME_FAILURE"
        )
        result["evidence_valid"] = False
        return result, 2

    parent_rows = _rows(_find_csv(case_dir, "parent_step.csv"))
    fast_rows = _rows(_find_csv(case_dir, "fast_step.csv"))
    if len(parent_rows) < 3 or len(fast_rows) < 2:
        result["classification"] = "MISSING_TIME_HISTORY"
        result["evidence_valid"] = False
        return result, 2

    parent_physical = [row for row in parent_rows if _f(row, "time") > 0.0]
    fast_physical = [row for row in fast_rows if _f(row, "time") > 0.0]
    final_parent = parent_physical[-1]
    final_fast = fast_physical[-1]
    if (
        len(parent_physical) != HEAVY_STEPS
        or len(fast_physical) != int(p["fast_steps"])
        or not math.isclose(
            _f(final_parent, "time"), float(p["end_time_s"]), rel_tol=1.0e-10, abs_tol=1.0e-24
        )
        or not math.isclose(
            _f(final_fast, "time"), float(p["end_time_s"]), rel_tol=1.0e-10, abs_tol=1.0e-24
        )
    ):
        result["classification"] = "INCOMPLETE_HORIZON"
        result["evidence_valid"] = False
        result["parent_steps_completed"] = len(parent_physical)
        result["fast_steps_completed"] = len(fast_physical)
        return result, 2

    heavy_profile = _latest_profile(case_dir, "heavy_profile")
    fast_profile = _latest_profile(case_dir, "energy_profile")
    profile = _combine_profile(heavy_profile, fast_profile)

    dt_fast = float(p["dt_fast_s"])
    cumulative_wall = sum(
        abs(_f(row, "wall_energy_power_W_m2")) * dt_fast for row in fast_physical
    )
    cumulative_elastic = sum(
        max(_f(row, "elastic_loss_applied_W_m2"), 0.0) * dt_fast for row in fast_physical
    )
    initial_energy = _f(fast_rows[0], "energy_inventory_J_m2")
    final_energy = _f(final_fast, "energy_inventory_J_m2")
    inferred_joule = final_energy - initial_energy + cumulative_wall + cumulative_elastic

    qvol = _f(final_fast, "poisson_charge_C_m2")
    qflux = _f(final_fast, "poisson_gauss_charge_C_m2")
    gauss_defect = abs(qflux - qvol) / max(abs(qflux), abs(qvol), 1.0e-300)

    imbalance = [row["charge_number_imbalance_m3"] for row in profile]
    heavy_motion: dict[str, float] = {}
    for sp in ("O2p", "Om", "Op"):
        initial = INITIAL_W[sp]
        final_values = [row[f"w_{sp}"] for row in heavy_profile]
        if initial != 0.0:
            heavy_motion[sp] = max(abs(value - initial) for value in final_values) / abs(initial)
        else:
            heavy_motion[sp] = max(abs(value) for value in final_values)

    fp = [int(round(_f(row, "fixed_point_iterations"))) for row in fast_physical]
    result.update(
        {
            "classification": "CASE_CONVERGED",
            "evidence_valid": True,
            "parent_steps_completed": len(parent_physical),
            "fast_steps_completed": len(fast_physical),
            "total_fixed_point_iterations": int(
                round(_f(final_fast, "cumulative_fixed_point_iterations"))
            ),
            "mean_fixed_point_iterations_per_fast_step": sum(fp) / len(fp),
            "max_fixed_point_iterations_per_fast_step": max(fp),
            "final_phi_min_V": _f(final_fast, "phi_min"),
            "final_phi_max_V": _f(final_fast, "phi_max"),
            "final_n_e_min_m3": _f(final_fast, "n_e_min"),
            "final_n_e_max_m3": _f(final_fast, "n_e_max"),
            "final_mean_energy_avg_eV": _f(final_fast, "mean_energy_avg_eV"),
            "final_energy_inventory_J_m2": final_energy,
            "cumulative_wall_energy_loss_J_m2": cumulative_wall,
            "cumulative_elastic_energy_loss_J_m2": cumulative_elastic,
            "cumulative_inferred_joule_input_J_m2": inferred_joule,
            "poisson_volume_charge_C_m2": qvol,
            "poisson_gauss_charge_C_m2": qflux,
            "gauss_relative_defect": gauss_defect,
            "charge_number_imbalance_mean_m3": sum(imbalance) / len(imbalance),
            "charge_number_imbalance_max_abs_m3": max(abs(x) for x in imbalance),
            "sum_w_min": _f(final_parent, "sum_w_min"),
            "sum_w_max": _f(final_parent, "sum_w_max"),
            "heavy_motion_max_relative": heavy_motion,
            "final_profile": profile,
        }
    )
    return result, 0


def run_case(case_name: str) -> None:
    if not (REPO / "physics_app" / "physics-opt").exists():
        raise SystemExit("physics-opt missing")
    script = (
        "set -euo pipefail; source /environment; "
        "export MOOSE_DIR=/opt/physics_vendor/moose; export CRANE_DIR=/opt/physics_vendor/crane; "
        "export SQUIRREL_DIR=/opt/physics_vendor/squirrel; export ZAPDOS_DIR=/opt/physics_vendor/zapdos; "
        "export METHOD=opt; export PYTHONPATH=/workspace; "
        f"python3 /workspace/{ROOT.relative_to(REPO)}/heavy13_control.py --inner-run {case_name}"
    )
    _docker(script)
    result, code = analyze_case(case_name)
    out = RESULTS / f"{case_name}_result.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G3_HEAVY13_CASE:", case_name, result["classification"])
    print(json.dumps(result, indent=2, sort_keys=True))
    if code:
        raise SystemExit(code)


def _potential_metrics(
    anchor: list[dict[str, float]], trial: list[dict[str, float]]
) -> dict[str, float]:
    if len(anchor) != len(trial):
        raise RuntimeError("profile point count mismatch")
    delta = [b["potential"] - a["potential"] for a, b in zip(anchor, trial)]
    mean_shift = sum(delta) / len(delta)
    shape = [d - mean_shift for d in delta]
    swing = max(row["potential"] for row in anchor) - min(row["potential"] for row in anchor)
    e_anchor: list[float] = []
    e_trial: list[float] = []
    for a0, a1, b0, b1 in zip(anchor[:-1], anchor[1:], trial[:-1], trial[1:]):
        dx = a1["x"] - a0["x"]
        e_anchor.append(-(a1["potential"] - a0["potential"]) / dx)
        e_trial.append(-(b1["potential"] - b0["potential"]) / dx)
    e_scale = max(max(abs(x) for x in e_anchor), 1.0e-300)
    return {
        "potential_mean_shift_V": mean_shift,
        "potential_shape_max_abs_V": max(abs(x) for x in shape),
        "potential_shape_relative_to_anchor_swing": max(abs(x) for x in shape)
        / max(abs(swing), 1.0e-300),
        "electric_field_einf_relative": max(
            abs(a - b) for a, b in zip(e_anchor, e_trial)
        )
        / e_scale,
    }


def aggregate(root: Path) -> dict[str, object]:
    found: dict[str, dict[str, object]] = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in CASE_NAMES:
            found[name] = item
    missing = [name for name in CASE_NAMES if name not in found]
    if missing:
        raise RuntimeError(f"missing heavy13 result(s): {missing}")

    if not all(bool(found[name].get("evidence_valid")) for name in CASE_NAMES):
        return {
            "issue": 253,
            "sequence": 13,
            "classification": "HEAVY13_INVALID_EVIDENCE",
            "evidence_valid": False,
            "cases": found,
        }

    chi_dependence: dict[str, object] = {}
    for mode in ("frozen", "heavy"):
        anchor = found[f"{mode}_chi1"]
        for chi in (10, 20):
            item = found[f"{mode}_chi{chi}"]
            metrics = _potential_metrics(anchor["final_profile"], item["final_profile"])
            metrics.update(
                {
                    "charge_mean_delta_m3": float(item["charge_number_imbalance_mean_m3"])
                    - float(anchor["charge_number_imbalance_mean_m3"]),
                    "volume_charge_relative_delta": float(item["poisson_volume_charge_C_m2"])
                    / max(abs(float(anchor["poisson_volume_charge_C_m2"])), 1.0e-300)
                    - 1.0,
                    "inferred_joule_input_relative_delta": float(
                        item["cumulative_inferred_joule_input_J_m2"]
                    )
                    / max(
                        abs(float(anchor["cumulative_inferred_joule_input_J_m2"])),
                        1.0e-300,
                    )
                    - 1.0,
                }
            )
            chi_dependence[f"{mode}_chi{chi}_vs_chi1"] = metrics

    heavy_effect: dict[str, object] = {}
    for chi in (1, 10, 20):
        frozen = found[f"frozen_chi{chi}"]
        heavy = found[f"heavy_chi{chi}"]
        metrics = _potential_metrics(frozen["final_profile"], heavy["final_profile"])
        metrics.update(
            {
                "charge_mean_change_m3": float(heavy["charge_number_imbalance_mean_m3"])
                - float(frozen["charge_number_imbalance_mean_m3"]),
                "charge_max_abs_ratio": float(heavy["charge_number_imbalance_max_abs_m3"])
                / max(float(frozen["charge_number_imbalance_max_abs_m3"]), 1.0e-300),
                "volume_charge_change_C_m2": float(heavy["poisson_volume_charge_C_m2"])
                - float(frozen["poisson_volume_charge_C_m2"]),
                "heavy_motion_max_relative": heavy["heavy_motion_max_relative"],
            }
        )
        heavy_effect[f"chi{chi}_released_vs_frozen"] = metrics

    return {
        "issue": 253,
        "sequence": 13,
        "classification": "HEAVY13_AB_COMPLETE",
        "evidence_valid": True,
        "equal_final_time": True,
        "total_time_tau_epsilon_initial": FINAL_TAU,
        "heavy_dt_tau_epsilon_initial": HEAVY_DT_TAU,
        "heavy_steps": HEAVY_STEPS,
        "fast_subcycles_per_heavy_step": {"chi1": 40, "chi10": 4, "chi20": 2},
        "heavy_scope": (
            "bulk heavy transient/diffusion/drift/electromigration correction only; "
            "heavy wall loss, flow and chemistry remain OFF"
        ),
        "cases": found,
        "chi_dependence": chi_dependence,
        "heavy_effect": heavy_effect,
        "interpretation_guard": (
            "Potential-offset collapse is only evidence for bulk heavy charge redistribution. "
            "No full heavy-wall neutralization claim is allowed in Sequence 13. "
            "Energy dt-release also remains unqualified if the inferred Joule-input ledger "
            "retains strong chi dependence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("p0", "p1", "p2"))
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
        out = RESULTS / "heavy13_summary.json"
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("ISSUE253_G3_HEAVY13_CLASSIFICATION:", summary["classification"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if bool(summary["evidence_valid"]) else 2
    if args.phase:
        {"p0": p0, "p1": p1, "p2": p2}[args.phase]()
        return 0
    parser.error("one action is required")


if __name__ == "__main__":
    raise SystemExit(main())
