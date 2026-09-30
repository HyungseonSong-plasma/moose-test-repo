#!/usr/bin/env python3
"""Issue #359: qualified frozen-heavy Gummel topology on the real-QVT ICP RZ mesh.

Electron physical dt is fixed at the previously stable 56.650790 ps value.
Heavy/ion dt is an integer multiple selected by --electron-substeps.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.runtime import resolve_executable, run_physics, validate_executable

ROOT = Path(__file__).resolve().parents[2]
HEAVY_SOURCE = ROOT / "experiments/Issue21_qvt_six_species_bulk_advection"
ICP_SOURCE = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
CANONICAL_HEAVY = ROOT / "physics_app/ci/plasma_closures_oxygen_transport.txt"

FLOW_SCCM = 20.0
PRESSURE_PA = 1.333223684
TG_K = 300.0
ENERGY_REF_EV = 5.73276
ELECTRON_DT_S = 5.6650790022617894e-11
ELECTRON_SUBSTEPS_DEFAULT = 4
RELAXATION_FACTOR_DEFAULT = 0.45
RESPONSE_STRENGTH_DEFAULT = 1.0
RESPONSE_RADIUS_DEFAULT = 1
RESPONSE_MODE_DEFAULT = "graph"
# Interior-row shell magnitudes extracted from the qualified 1D bandwidth-5
# response matrix.  Truncated radii are renormalized so each multidimensional
# graph-shell correction remains row-sum preserving with unit total strength.
QUALIFIED_1D_SHELL_WEIGHTS = (
    0.33455674,
    0.24453258,
    0.18136180,
    0.13695613,
    0.10259275,
)
AVOGADRO = 6.02214076e23
R_GAS = 8.31446261815324
ELECTRON_DENSITY_REF_M3 = 1.0e16
ELEMENTARY_CHARGE_C = 1.602176634e-19
TE_PER_MEAN_EV_K = (2.0 / 3.0) * ELEMENTARY_CHARGE_C / 1.380649e-23
ALL_ELECTRON_BOUNDARIES = (
    "inlet",
    "outlet",
    "plasma_electrode",
    "plasma_metal",
    "plasma_right",
    "plasma_cover",
    "plasma_wafer",
    "plasma_focus_ring",
)
MASS_FRACTIONS = {
    "O2": 0.99994,
    "O2s": 1.0e-5,
    "O2p": 1.0e-5,
    "O": 1.0e-5,
    "Om": 1.0e-5,
    "Op": 1.0e-5,
    "Os": 1.0e-5,
}
CHARGED_MOLAR_MASSES = {"O2p": 0.032, "Om": 0.016, "Op": 0.016}
CHARGED_Z = {"O2p": 1.0, "Om": -1.0, "Op": 1.0}
INITIAL_MIXTURE_DENSITY_KG_M3 = PRESSURE_PA * 0.032 / (R_GAS * TG_K)
INITIAL_ELECTRON_DENSITY_M3 = INITIAL_MIXTURE_DENSITY_KG_M3 * AVOGADRO * sum(
    CHARGED_Z[s] * MASS_FRACTIONS[s] / CHARGED_MOLAR_MASSES[s]
    for s in ("O2p", "Om", "Op")
)
INITIAL_ELECTRON_MOLAR_M3 = INITIAL_ELECTRON_DENSITY_M3 / AVOGADRO
INITIAL_LOG_E = math.log(INITIAL_ELECTRON_MOLAR_M3)
INITIAL_EPSILON_HAT = INITIAL_ELECTRON_DENSITY_M3 / ELECTRON_DENSITY_REF_M3


class Issue359Error(RuntimeError):
    pass


FAST_MESH = """[Mesh]
  coord_type = RZ
  rz_coord_axis = Y

  [main]
    type = FileMeshGenerator
    file = 'qvt.msh'
  []
  [inlet]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = port
    new_boundary = inlet
    input = main
  []
  [outlet]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = bottom
    new_boundary = outlet
    input = inlet
  []
  [plasma_electrode]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = electrode
    new_boundary = plasma_electrode
    input = outlet
  []
  [plasma_metal]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = metal
    new_boundary = plasma_metal
    input = plasma_electrode
  []
  [plasma_right]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = right
    new_boundary = plasma_right
    input = plasma_metal
  []
  [plasma_cover]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = cover
    new_boundary = plasma_cover
    input = plasma_right
  []
  [plasma_wafer]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = wafer
    new_boundary = plasma_wafer
    input = plasma_cover
  []
  [plasma_focus_ring]
    type = SideSetsBetweenSubdomainsGenerator
    primary_block = plasma
    paired_block = focus_ring
    new_boundary = plasma_focus_ring
    input = plasma_wafer
  []
  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]"""


def _replace_top(text: str, name: str, value: str) -> str:
    out, count = re.subn(
        rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*$",
        f"{name} = {value}",
        text,
        count=1,
    )
    if count != 1:
        raise Issue359Error(f"expected one top-level {name}, found {count}")
    return out


def _remove_top(text: str, name: str) -> str:
    return re.sub(rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*\n", "", text, count=1)


def _replace_mesh(text: str) -> str:
    if not mb.has_block(text, "Mesh"):
        raise Issue359Error("qualified input lost Mesh block")
    return FAST_MESH + "\n\n" + mb.remove_block(text, "Mesh").lstrip()


def _add_aux(text: str, name: str, initial: float) -> str:
    block = f"""  [{name}]
    type = MooseVariableFVReal
    initial_condition = {initial:.17g}
  []"""
    if mb.has_block(text, "AuxVariables"):
        if mb.has_block(text, f"AuxVariables/{name}"):
            return text
        return mb.insert_child_block(text, "AuxVariables", block)
    return text + "\n[AuxVariables]\n" + block + "\n[]\n"


def _qualified_reference_case() -> Path:
    """Resolve the immutable #351 full-qualified artifact staged by CI."""
    raw = os.environ.get("ISSUE351_QUALIFIED_CASE", "")
    if not raw:
        raise Issue359Error(
            "ISSUE351_QUALIFIED_CASE is required and must point to the extracted "
            "#351 frozen-heavy qualified case"
        )
    case = Path(raw).resolve()
    required = ("electron_sub.i", "poisson_sub.i", "fast_sub.i", "o2_elastic.txt")
    missing = [name for name in required if not (case / name).is_file()]
    if missing:
        raise Issue359Error(
            f"qualified #351 reference case missing files: {missing}; case={case}"
        )
    return case


def _canonicalize_qualified_driver(text: str) -> str:
    """Remove only #355-retired Action syntax from the qualified #351 driver."""
    for name in (
        "electron_multiapp_type",
        "poisson_multiapp_type",
        "electron_state_variables",
        "poisson_transformed_variables",
        "no_restore",
    ):
        text = re.sub(
            rf"(?m)^\s*{re.escape(name)}\s*=.*\n",
            "",
            text,
            count=1,
        )
    return text


def _heavy_dt_s(electron_substeps: int) -> float:
    if electron_substeps <= 0:
        raise Issue359Error("electron_substeps must be positive")
    return ELECTRON_DT_S * float(electron_substeps)


def _configure_fast_executioner(text: str, electron_substeps: int) -> str:
    heavy_dt_s = _heavy_dt_s(electron_substeps)
    text = mp.upsert_parameter(text, "Executioner", "dt", f"{ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "dtmin", f"{ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "dtmax", f"{ELECTRON_DT_S:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "end_time", f"{heavy_dt_s:.17g}")
    text = mp.upsert_parameter(text, "Executioner", "num_steps", str(electron_substeps))
    text = mp.upsert_parameter(text, "Executioner", "timestep_tolerance", "1.0e-18")
    return text


def _electron_input(
    src: str, *, electron_substeps: int = ELECTRON_SUBSTEPS_DEFAULT
) -> str:
    text = _replace_mesh(src)
    text = mp.upsert_parameter(
        text, "Variables/log_e", "initial_condition", f"{INITIAL_LOG_E:.17g}"
    )
    text = mp.upsert_parameter(
        text,
        "Variables/n_epsilon",
        "initial_condition",
        f"{INITIAL_EPSILON_HAT:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        "AuxVariables/electron_density_out",
        "initial_condition",
        f"{INITIAL_ELECTRON_DENSITY_M3:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        "AuxVariables/mean_energy_out",
        "initial_condition",
        f"{ENERGY_REF_EV:.17g}",
    )
    text = _add_aux(text, "p_gas_from_heavy", PRESSURE_PA)
    text = _add_aux(text, "T_g_from_heavy", TG_K)

    text = mp.upsert_parameter(
        text, "FunctorMaterials/constants", "prop_names", "'carrier_one zero_flux'"
    )
    text = mp.upsert_parameter(
        text, "FunctorMaterials/constants", "prop_values", "'1.0 0.0'"
    )
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [issue359_o2_concentration]
    type = ADParsedFunctorMaterial
    property_name = c_O2
    functor_names = 'p_gas_from_heavy T_g_from_heavy'
    functor_symbols = 'prs tmp'
    expression = '0.99994*prs/(8.31446261815324*tmp)'
  []""",
    )
    text = mp.upsert_parameter(
        text, "PlasmaClosures/electron", "gas_pressure", "p_gas_from_heavy"
    )
    text = mp.upsert_parameter(
        text, "PlasmaClosures/electron", "gas_temperature", "T_g_from_heavy"
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/elastic_energy_candidate",
        "functor_names",
        "'mean_en_solved T_g_from_heavy R_elastic_O2'",
    )

    all_bcs = "'" + " ".join(ALL_ELECTRON_BOUNDARIES) + "'"
    for path in ("FVKernels/electron_drift", "FVKernels/energy_drift"):
        text = mp.upsert_parameter(text, path, "boundaries_to_avoid", all_bcs)

    if mb.has_block(text, "FVBCs"):
        text = mb.remove_block(text, "FVBCs")
    text += f"""
[FVBCs]
  [issue359_electron_sheath]
    type = PhysicsFVElectronGroundedSheathCollectionBC
    variable = log_e
    boundary = {all_bcs}
    mean_electron_energy = mean_en_solved
    potential = potential_from_poisson
    log_molar_state = true
  []
  [issue359_energy_sheath]
    type = PhysicsFVElectronGroundedSheathEnergyBC
    variable = n_epsilon
    boundary = {all_bcs}
    electron_density = electron_density_hat
    mean_electron_energy = mean_en_solved
    potential = potential_from_poisson
    energy_reference_eV = {ENERGY_REF_EV:.17g}
  []
[]
"""

    for name in (
        "wall_particle_rate_mol_m2_s",
        "wall_energy_rate_hat",
        "wall_energy_power_W_m2",
    ):
        pp = f"Postprocessors/{name}"
        if mb.has_block(text, pp):
            text = mb.remove_block(text, pp)

    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [issue359_electron_sheath_rate]
    type = SideFVFluxBCIntegral
    boundary = {all_bcs}
    fvbcs = 'issue359_electron_sheath'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )
    text = mb.insert_child_block(
        text,
        "Postprocessors",
        f"""  [issue359_energy_sheath_rate]
    type = SideFVFluxBCIntegral
    boundary = {all_bcs}
    fvbcs = 'issue359_energy_sheath'
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
    )

    return _configure_fast_executioner(text, electron_substeps)


def _response_shell_weights(radius: int) -> tuple[float, ...]:
    if radius < 1 or radius > len(QUALIFIED_1D_SHELL_WEIGHTS):
        raise Issue359Error("response radius must lie in [1, 5]")
    raw = QUALIFIED_1D_SHELL_WEIGHTS[:radius]
    total = sum(raw)
    return tuple(weight / total for weight in raw)


def _poisson_input(
    src: str,
    *,
    response_strength: float = RESPONSE_STRENGTH_DEFAULT,
    response_radius: int = RESPONSE_RADIUS_DEFAULT,
    response_mode: str = RESPONSE_MODE_DEFAULT,
    electron_substeps: int = ELECTRON_SUBSTEPS_DEFAULT,
) -> str:
    text = _replace_mesh(src)
    text = mp.upsert_parameter(
        text,
        "AuxVariables/log_e_frozen",
        "initial_condition",
        f"{INITIAL_LOG_E:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        "AuxVariables/n_epsilon_frozen",
        "initial_condition",
        f"{INITIAL_EPSILON_HAT:.17g}",
    )
    for species in ("O2p", "Om", "Op"):
        text = mp.upsert_parameter(
            text,
            f"AuxVariables/w_{species}_frozen",
            "initial_condition",
            f"{MASS_FRACTIONS[species]:.17g}",
        )
    text = _add_aux(text, "p_gas_from_heavy", PRESSURE_PA)
    text = _add_aux(text, "T_g_from_heavy", TG_K)

    text = mp.upsert_parameter(
        text, "FunctorMaterials/constants", "prop_names", "'relative_permittivity'"
    )
    text = mp.upsert_parameter(
        text, "FunctorMaterials/constants", "prop_values", "'1.0'"
    )
    # The qualified 1D response matrix is geometry-specific, but its local
    # mean-energy and susceptibility materials are geometry-independent and are
    # retained for the topology-aware ICP response correction.
    if mb.has_block(text, "FVKernels/electron_response_banded_correction"):
        text = mb.remove_block(text, "FVKernels/electron_response_banded_correction")

    text = mb.insert_child_block(
        text,
        "FVKernels",
        """  [issue359_electron_response_topology]
    type = FVElectronResponseTopologyCorrection
    variable = potential_plasma
    anchor = phi_anchor_frozen
    beta = electron_response_beta
    strength = 1.0
  []""",
    )
    if response_mode not in ("graph", "directional"):
        raise Issue359Error("response mode must be 'graph' or 'directional'")
    shell_weights = _response_shell_weights(response_radius)
    text = mp.upsert_parameter(
        text,
        "FVKernels/issue359_electron_response_topology",
        "strength",
        f"{response_strength:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/issue359_electron_response_topology",
        "graph_radius",
        str(response_radius),
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/issue359_electron_response_topology",
        "shell_weights",
        "'" + " ".join(f"{weight:.17g}" for weight in shell_weights) + "'",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/issue359_electron_response_topology",
        "directional_band",
        "true" if response_mode == "directional" else "false",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/issue359_electron_response_topology",
        "radial_component",
        "0",
    )
    text = mp.upsert_parameter(
        text,
        "FVKernels/issue359_electron_response_topology",
        "axial_component",
        "1",
    )

    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [issue359_mixture_density]
    type = ADParsedFunctorMaterial
    property_name = rho_from_heavy
    functor_names = 'p_gas_from_heavy T_g_from_heavy'
    functor_symbols = 'prs tmp'
    expression = 'prs*0.032/(8.31446261815324*tmp)'
  []""",
    )
    text = mp.upsert_parameter(
        text, "PlasmaClosures/charge", "mixture_density", "rho_from_heavy"
    )

    all_bcs = "'" + " ".join(ALL_ELECTRON_BOUNDARIES) + "'"
    if mb.has_block(text, "FVBCs"):
        text = mb.remove_block(text, "FVBCs")
    text += f"""
[FVBCs]
  [issue359_ground_all]
    type = FVDirichletBC
    variable = potential_plasma
    boundary = {all_bcs}
    value = 0.0
  []
[]
"""

    text += """
[VectorPostprocessors]
  [potential_profile]
    type = ElementValueSampler
    variable = 'potential_plasma'
    sort_by = id
    execute_on = 'FINAL'
  []
[]
"""

    return _configure_fast_executioner(text, electron_substeps)


def _driver_input(
    src: str,
    *,
    relaxation_factor: float = RELAXATION_FACTOR_DEFAULT,
    electron_substeps: int = ELECTRON_SUBSTEPS_DEFAULT,
) -> str:
    text = _canonicalize_qualified_driver(src)
    text = _replace_mesh(text)
    for species in ("O2p", "Om", "Op"):
        text = mp.upsert_parameter(
            text,
            f"AuxVariables/w_{species}_h",
            "initial_condition",
            f"{MASS_FRACTIONS[species]:.17g}",
        )
    text = mp.upsert_parameter(
        text,
        "AuxVariables/electron_density_out",
        "initial_condition",
        f"{INITIAL_ELECTRON_DENSITY_M3:.17g}",
    )
    text = mp.upsert_parameter(
        text,
        "AuxVariables/mean_energy_out",
        "initial_condition",
        f"{ENERGY_REF_EV:.17g}",
    )
    text = _add_aux(text, "p_gas_h", PRESSURE_PA)
    text = _add_aux(text, "T_g_h", TG_K)

    # Promote final Gummel state diagnostics to the driver so they survive
    # MultiApp teardown and are written into the driver's FINAL CSV.
    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [issue359_Te_diag]
    type = ADParsedFunctorMaterial
    property_name = issue359_Te_K
    functor_names = 'mean_energy_out'
    functor_symbols = 'mean_ev'
    expression = '{TE_PER_MEAN_EV_K:.17g}*mean_ev'
  []
  [issue359_charge_diag]
    type = ADParsedFunctorMaterial
    property_name = issue359_charge_density_C_m3
    functor_names = 'p_gas_h T_g_h w_O2p_h w_Om_h w_Op_h electron_density_out'
    functor_symbols = 'prs tmp wp wm wo ne'
    expression = '{ELEMENTARY_CHARGE_C:.17g}*((prs*0.032/(8.31446261815324*tmp))*{AVOGADRO:.17g}*(wp/0.032-wm/0.016+wo/0.016)-ne)'
  []""",
    )

    for block in (
        """  [issue359_phi_min]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = min
    execute_on = 'FINAL'
  []""",
        """  [issue359_phi_max]
    type = ADElementExtremeFunctorValue
    functor = potential_from_poisson
    value_type = max
    execute_on = 'FINAL'
  []""",
        """  [issue359_ne_min]
    type = ADElementExtremeFunctorValue
    functor = electron_density_out
    value_type = min
    execute_on = 'FINAL'
  []""",
        """  [issue359_ne_max]
    type = ADElementExtremeFunctorValue
    functor = electron_density_out
    value_type = max
    execute_on = 'FINAL'
  []""",
        """  [issue359_ne_avg]
    type = ElementAverageFunctorPostprocessor
    functor = electron_density_out
    execute_on = 'FINAL'
  []""",
        """  [issue359_mean_energy_min]
    type = ADElementExtremeFunctorValue
    functor = mean_energy_out
    value_type = min
    execute_on = 'FINAL'
  []""",
        """  [issue359_mean_energy_max]
    type = ADElementExtremeFunctorValue
    functor = mean_energy_out
    value_type = max
    execute_on = 'FINAL'
  []""",
        """  [issue359_mean_energy_avg]
    type = ElementAverageFunctorPostprocessor
    functor = mean_energy_out
    execute_on = 'FINAL'
  []""",
        """  [issue359_Te_min_K]
    type = ADElementExtremeFunctorValue
    functor = issue359_Te_K
    value_type = min
    execute_on = 'FINAL'
  []""",
        """  [issue359_Te_max_K]
    type = ADElementExtremeFunctorValue
    functor = issue359_Te_K
    value_type = max
    execute_on = 'FINAL'
  []""",
        """  [issue359_Te_avg_K]
    type = ElementAverageFunctorPostprocessor
    functor = issue359_Te_K
    execute_on = 'FINAL'
  []""",
        """  [issue359_charge_min]
    type = ADElementExtremeFunctorValue
    functor = issue359_charge_density_C_m3
    value_type = min
    execute_on = 'FINAL'
  []""",
        """  [issue359_charge_max]
    type = ADElementExtremeFunctorValue
    functor = issue359_charge_density_C_m3
    value_type = max
    execute_on = 'FINAL'
  []""",
        """  [issue359_charge_avg]
    type = ElementAverageFunctorPostprocessor
    functor = issue359_charge_density_C_m3
    execute_on = 'FINAL'
  []""",
        """  [issue359_charge_integral]
    type = ADElementIntegralFunctorPostprocessor
    functor = issue359_charge_density_C_m3
    execute_on = 'FINAL'
  []""",
    ):
        text = mb.insert_child_block(text, "Postprocessors", block)

    action = "GummelIteration/electron_poisson"
    text = mp.upsert_parameter(
        text, action, "relaxation_factor", f"{relaxation_factor:.17g}"
    )
    text = mp.upsert_parameter(
        text, action, "parent_to_electron_source_variables", "'p_gas_h T_g_h'"
    )
    text = mp.upsert_parameter(
        text,
        action,
        "parent_to_electron_variables",
        "'p_gas_from_heavy T_g_from_heavy'",
    )
    text = mp.upsert_parameter(
        text,
        action,
        "parent_to_poisson_source_variables",
        "'potential_from_poisson p_gas_h T_g_h w_O2p_h w_Om_h w_Op_h'",
    )
    text = mp.upsert_parameter(
        text,
        action,
        "parent_to_poisson_variables",
        "'phi_anchor_frozen p_gas_from_heavy T_g_from_heavy w_O2p_frozen w_Om_frozen w_Op_frozen'",
    )

    return _configure_fast_executioner(text, electron_substeps)


def _outer_input(
    src: str, *, electron_substeps: int = ELECTRON_SUBSTEPS_DEFAULT
) -> str:
    # Use the identical plasma-only real-QVT mesh in all four applications so
    # MultiAppCopyTransfer remains an exact elementwise transfer.
    text = _replace_mesh(src)
    if mb.has_block(text, "Materials"):
        text = mb.remove_block(text, "Materials")

    # Promote the accepted #21 heavy FV operators to their current Physics
    # registrations without changing their equations or parameters.
    text = text.replace(
        "type = QPXFVMassFractionAdvection",
        "type = PhysicsFVMassFractionAdvection",
    )
    text = text.replace(
        "type = QPXFVMixtureAveragedDiffusion",
        "type = PhysicsFVMixtureAveragedDiffusion",
    )
    for name, value in (
        ("Q_sccm", FLOW_SCCM),
        ("outlet_pressure", PRESSURE_PA),
        ("T_g_value", TG_K),
        ("Yin_O2", MASS_FRACTIONS["O2"]),
        ("Yin_O2s", MASS_FRACTIONS["O2s"]),
        ("Yin_O2p", MASS_FRACTIONS["O2p"]),
        ("Yin_O", MASS_FRACTIONS["O"]),
        ("Yin_Om", MASS_FRACTIONS["Om"]),
        ("Yin_Op", MASS_FRACTIONS["Op"]),
        ("Yin_Os", MASS_FRACTIONS["Os"]),
    ):
        text = _replace_top(text, name, f"{value:.17g}")
    text = _remove_top(text, "T_e_value")
    text = _remove_top(text, "n_e_value")

    text = mp.upsert_parameter(
        text, "FunctorMaterials/state_constants", "prop_names", "'T_g mu_flow'"
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_values",
        "'${T_g_value} ${mu_const}'",
    )
    text = _add_aux(text, "T_g_snapshot", TG_K)
    text = _add_aux(
        text, "electron_density_from_gummel", INITIAL_ELECTRON_DENSITY_M3
    )
    text = _add_aux(text, "mean_energy_from_gummel", ENERGY_REF_EV)

    text = mb.insert_child_block(
        text,
        "FunctorMaterials",
        f"""  [issue359_electron_temperature]
    type = ADParsedFunctorMaterial
    property_name = T_e_from_gummel_K
    functor_names = 'mean_energy_from_gummel'
    functor_symbols = 'mean_ev'
    expression = '{TE_PER_MEAN_EV_K:.17g}*mean_ev'
    block = plasma
  []""",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/heavy_transport",
        "electron_temperature",
        "T_e_from_gummel_K",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/heavy_transport",
        "electron_number_density",
        "electron_density_from_gummel",
    )

    text += """
[MultiApps]
  [gummel_driver]
    type = TransientMultiApp
    input_files = 'gummel_driver.i'
    execute_on = TIMESTEP_BEGIN
    no_restore = true
    sub_cycling = true
  []
[]

[Transfers]
  [issue359_heavy_snapshot]
    type = MultiAppCopyTransfer
    to_multi_app = gummel_driver
    source_variable = 'p T_g_snapshot w_O2p w_Om w_Op'
    variable = 'p_gas_h T_g_h w_O2p_h w_Om_h w_Op_h'
  []
  [issue359_fast_to_heavy]
    type = MultiAppCopyTransfer
    from_multi_app = gummel_driver
    source_variable = 'electron_density_out mean_energy_out'
    variable = 'electron_density_from_gummel mean_energy_from_gummel'
  []
[]
"""

    if mb.has_block(text, "Executioner"):
        text = mb.remove_block(text, "Executioner")
    text += f"""
[Executioner]
  type = Transient
  scheme = implicit-euler
  solve_type = NEWTON
  dt = {_heavy_dt_s(electron_substeps):.17g}
  end_time = {_heavy_dt_s(electron_substeps):.17g}
  num_steps = 1
  nl_rel_tol = 1.0e-9
  nl_abs_tol = 1.0e-11
  nl_max_its = 80
  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  petsc_options_iname = '-pc_type -pc_factor_shift_type'
  petsc_options_value = 'lu NONZERO'
[]
"""
    return text


def _construction_audit(
    outer: str,
    driver: str,
    electron: str,
    poisson: str,
    *,
    relaxation_factor: float,
    response_strength: float,
    response_radius: int,
    response_mode: str,
    electron_substeps: int,
) -> dict[str, Any]:
    all_b = set(ALL_ELECTRON_BOUNDARIES)
    checks = {
        "qualified_gummel_action_present": mb.has_block(
            driver, "GummelIteration/electron_poisson"
        ),
        "electron_and_poisson_siblings": (
            "electron_input_file = electron_sub.i" in driver
            and "poisson_input_file = poisson_sub.i" in driver
        ),
        "through_parent_potential": (
            mp.get_parameter(
                driver, "GummelIteration/electron_poisson", "potential_transfer_mode"
            )
            == "through_parent"
        ),
        "steffensen": (
            mp.get_parameter(driver, "Executioner", "fixed_point_algorithm")
            == "steffensen"
        ),
        "relaxation_factor_selected": math.isclose(
            float(
                mp.get_parameter(
                    driver,
                    "GummelIteration/electron_poisson",
                    "relaxation_factor",
                )
                or "nan"
            ),
            relaxation_factor,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        ),
        "delta_phi_contract": (
            mp.get_parameter(
                driver, "GummelIteration/electron_poisson", "manage_convergence"
            )
            == "true"
            and math.isclose(
                float(
                    mp.get_parameter(
                        driver,
                        "GummelIteration/electron_poisson",
                        "delta_phi_abs_tol",
                    )
                    or "nan"
                ),
                1.0e-6,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
        ),
        "icp_mesh_outer": "BlockDeletionGenerator" in outer
        and "block = plasma" in outer
        and not mb.has_block(outer, "Materials"),
        "icp_mesh_driver": "BlockDeletionGenerator" in driver
        and "block = plasma" in driver,
        "icp_mesh_electron": "BlockDeletionGenerator" in electron
        and "block = plasma" in electron,
        "icp_mesh_poisson": "BlockDeletionGenerator" in poisson
        and "block = plasma" in poisson,
        "current_heavy_operator_types": (
            "QPXFVMassFractionAdvection" not in outer
            and "QPXFVMixtureAveragedDiffusion" not in outer
            and outer.count("type = PhysicsFVMassFractionAdvection") == 6
            and outer.count("type = PhysicsFVMixtureAveragedDiffusion") == 6
        ),
        "heavy_20_sccm": re.search(
            r"(?m)^Q_sccm\s*=\s*20(?:\.0+)?\s*$", outer
        )
        is not None,
        "heavy_10mtorr_outlet": re.search(
            r"(?m)^outlet_pressure\s*=\s*1\.333223684\s*$", outer
        )
        is not None,
        "heavy_outlet_pressure_bc": (
            mp.get_parameter(outer, "FVBCs/outlet_p", "boundary") == "outlet"
            and mp.get_parameter(outer, "FVBCs/outlet_p", "function")
            == "${outlet_pressure}"
        ),
        "electron_particle_bc_all_boundaries": (
            set(
                mp.words(
                    mp.get_parameter(
                        electron, "FVBCs/issue359_electron_sheath", "boundary"
                    )
                    or ""
                )
            )
            == all_b
        ),
        "electron_energy_bc_all_boundaries": (
            set(
                mp.words(
                    mp.get_parameter(
                        electron, "FVBCs/issue359_energy_sheath", "boundary"
                    )
                    or ""
                )
            )
            == all_b
        ),
        "electron_bc_independent_of_heavy_flow": (
            "Q_sccm" not in electron and "outlet_pressure" not in electron
        ),
        "electron_heavy_state_symbols_frozen": (
            "gas_pressure = p_gas_from_heavy" in electron
            and "gas_temperature = T_g_from_heavy" in electron
            and "functor_names = 'mean_en_solved T_g_from_heavy R_elastic_O2'"
            in electron
            and re.search(r"\bT_g\b", electron) is None
            and re.search(r"\bp_gas\b", electron) is None
        ),
        "electron_energy_solved": all(
            mb.has_block(electron, p)
            for p in (
                "Variables/n_epsilon",
                "FVKernels/energy_time",
                "FVKernels/energy_diffusion",
                "FVKernels/energy_drift",
                "FVKernels/energy_joule",
                "FVKernels/energy_elastic_o2",
            )
        ),
        "poisson_all_ground_explicit": (
            set(
                mp.words(
                    mp.get_parameter(
                        poisson, "FVBCs/issue359_ground_all", "boundary"
                    )
                    or ""
                )
            )
            == all_b
        ),
        "geometry_specific_1d_response_removed": (
            "FVElectronResponseBandedCorrection" not in poisson
        ),
        "topology_aware_2d_response_present": (
            "type = FVElectronResponseTopologyCorrection" in poisson
            and "anchor = phi_anchor_frozen" in poisson
            and "beta = electron_response_beta" in poisson
            and math.isclose(
                float(
                    mp.get_parameter(
                        poisson,
                        "FVKernels/issue359_electron_response_topology",
                        "strength",
                    )
                    or "nan"
                ),
                response_strength,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
            and int(
                mp.get_parameter(
                    poisson,
                    "FVKernels/issue359_electron_response_topology",
                    "graph_radius",
                )
                or "0"
            )
            == response_radius
            and (
                mp.get_parameter(
                    poisson,
                    "FVKernels/issue359_electron_response_topology",
                    "directional_band",
                )
                == ("true" if response_mode == "directional" else "false")
            )
            and len(
                mp.words(
                    mp.get_parameter(
                        poisson,
                        "FVKernels/issue359_electron_response_topology",
                        "shell_weights",
                    )
                    or ""
                )
            )
            == response_radius
        ),
        "multirate_time_contract": (
            mp.get_parameter(outer, "MultiApps/gummel_driver", "sub_cycling") == "true"
            and math.isclose(
                float(mp.get_parameter(outer, "Executioner", "dt") or "nan"),
                _heavy_dt_s(electron_substeps),
                rel_tol=0.0,
                abs_tol=1.0e-18,
            )
            and int(mp.get_parameter(outer, "Executioner", "num_steps") or "0") == 1
            and all(
                math.isclose(
                    float(mp.get_parameter(inp, "Executioner", "dt") or "nan"),
                    ELECTRON_DT_S,
                    rel_tol=0.0,
                    abs_tol=1.0e-18,
                )
                and math.isclose(
                    float(mp.get_parameter(inp, "Executioner", "end_time") or "nan"),
                    _heavy_dt_s(electron_substeps),
                    rel_tol=0.0,
                    abs_tol=1.0e-18,
                )
                and int(mp.get_parameter(inp, "Executioner", "num_steps") or "0")
                == electron_substeps
                for inp in (driver, electron, poisson)
            )
        ),
        "single_Te_ownership": (
            "T_e_value" not in outer
            and "T_e_from_gummel_K" in outer
            and "mean_energy_from_gummel" in outer
        ),
        "driver_final_diagnostics_present": all(
            mb.has_block(driver, f"Postprocessors/{name}")
            for name in (
                "issue359_phi_min",
                "issue359_phi_max",
                "issue359_ne_min",
                "issue359_ne_max",
                "issue359_ne_avg",
                "issue359_mean_energy_min",
                "issue359_mean_energy_max",
                "issue359_mean_energy_avg",
                "issue359_Te_avg_K",
                "issue359_charge_min",
                "issue359_charge_max",
                "issue359_charge_avg",
                "issue359_charge_integral",
            )
        ),
        "quasi_neutral_electron_initial_condition": (
            math.isclose(
                float(
                    mp.get_parameter(
                        electron, "Variables/log_e", "initial_condition"
                    )
                    or "nan"
                ),
                INITIAL_LOG_E,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            and math.isclose(
                float(
                    mp.get_parameter(
                        electron, "Variables/n_epsilon", "initial_condition"
                    )
                    or "nan"
                ),
                INITIAL_EPSILON_HAT,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        ),
    }
    failed = sorted(k for k, ok in checks.items() if not ok)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
    }


def _stage(
    root: Path,
    *,
    relaxation_factor: float = RELAXATION_FACTOR_DEFAULT,
    response_strength: float = RESPONSE_STRENGTH_DEFAULT,
    response_radius: int = RESPONSE_RADIUS_DEFAULT,
    response_mode: str = RESPONSE_MODE_DEFAULT,
    electron_substeps: int = ELECTRON_SUBSTEPS_DEFAULT,
) -> dict[str, Any]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    qualified = _qualified_reference_case()
    outer = _outer_input(
        (HEAVY_SOURCE / "input.i").read_text(),
        electron_substeps=electron_substeps,
    )
    driver = _driver_input(
        (qualified / "fast_sub.i").read_text(),
        relaxation_factor=relaxation_factor,
        electron_substeps=electron_substeps,
    )
    electron = _electron_input(
        (qualified / "electron_sub.i").read_text(),
        electron_substeps=electron_substeps,
    )
    poisson = _poisson_input(
        (qualified / "poisson_sub.i").read_text(),
        response_strength=response_strength,
        response_radius=response_radius,
        response_mode=response_mode,
        electron_substeps=electron_substeps,
    )

    audit = _construction_audit(
        outer,
        driver,
        electron,
        poisson,
        relaxation_factor=relaxation_factor,
        response_strength=response_strength,
        response_radius=response_radius,
        response_mode=response_mode,
        electron_substeps=electron_substeps,
    )
    if audit["status"] != "PASS":
        raise Issue359Error(f"construction audit failed: {audit['failed_checks']}")

    (root / "input.i").write_text(outer)
    (root / "gummel_driver.i").write_text(driver)
    (root / "electron_sub.i").write_text(electron)
    (root / "poisson_sub.i").write_text(poisson)

    shutil.copy2(ICP_SOURCE / "qvt.msh", root / "qvt.msh")
    shutil.copy2(CANONICAL_HEAVY, root / "transport_data.txt")
    shutil.copy2(ICP_SOURCE / "electron_moments.txt", root / "electron_moments.txt")
    shutil.copy2(qualified / "o2_elastic.txt", root / "o2_elastic.txt")

    if (root / "transport_data.txt").read_bytes() != CANONICAL_HEAVY.read_bytes():
        raise Issue359Error("canonical heavy transport staging mismatch")
    if len((root / "electron_moments.txt").read_text().splitlines()) < 50:
        raise Issue359Error("real-QVT electron moment table unexpectedly short")

    meta = {
        "issue": 359,
        "qualified_parent_sha": "05fd063f98406892553e9f4929245097084c9289",
        "qualified_source": "#351 frozen-heavy dedicated-driver full qualification",
        "geometry": "real-QVT ICP RZ plasma block",
        "flow_sccm": FLOW_SCCM,
        "outlet_pressure_Pa": PRESSURE_PA,
        "gas_temperature_K": TG_K,
        "initial_charge_balance": {
            "mixture_density_kg_m3": INITIAL_MIXTURE_DENSITY_KG_M3,
            "electron_density_m3": INITIAL_ELECTRON_DENSITY_M3,
            "electron_molar_density_mol_m3": INITIAL_ELECTRON_MOLAR_M3,
            "log_e_initial": INITIAL_LOG_E,
            "n_epsilon_initial": INITIAL_EPSILON_HAT,
            "mean_energy_initial_eV": ENERGY_REF_EV,
            "formula": "ne = rho*NA*sum(z_i*w_i/M_i)",
            "reference_density_m3": ELECTRON_DENSITY_REF_M3,
        },
        "electron_boundary_set": list(ALL_ELECTRON_BOUNDARIES),
        "electron_particle_bc": "PhysicsFVElectronGroundedSheathCollectionBC",
        "electron_energy_bc": "PhysicsFVElectronGroundedSheathEnergyBC",
        "poisson_bc": "all eight plasma boundaries grounded at 0 V",
        "removed_geometry_specific_object": "FVElectronResponseBandedCorrection",
        "time_integration": {
            "heavy_dt_s": _heavy_dt_s(electron_substeps),
            "heavy_steps": 1,
            "electron_substeps_per_heavy": electron_substeps,
            "electron_dt_s": ELECTRON_DT_S,
            "electron_to_heavy_dt_ratio": 1.0 / float(electron_substeps),
            "frozen_heavy_during_electron_subcycling": True,
        },
        "gummel_acceleration": {
            "relaxation_factor": relaxation_factor,
            "fixed_point_algorithm": "steffensen",
        },
        "icp_response_correction": {
            "type": "FVElectronResponseTopologyCorrection",
            "stencil": "one-ring face neighbors",
            "row_sum_preserving": True,
            "strength": response_strength,
            "mode": response_mode,
            "graph_radius": response_radius,
            "shell_weights": list(_response_shell_weights(response_radius)),
            "directional_axes": {"radial_component": 0, "axial_component": 1},
            "weight_source": "qualified 1D bandwidth-5 interior-row shell totals",
        },
        "construction_audit": audit,
    }
    (root / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    return meta


def _read_final_diagnostics(case: Path) -> dict[str, float]:
    paths = sorted(case.glob("*_gummel_driver0_final_csv.csv"))
    if len(paths) != 1:
        raise Issue359Error(
            f"expected one Gummel driver FINAL CSV, found {len(paths)}: {paths}"
        )
    with paths[0].open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise Issue359Error(
            f"expected one Gummel driver FINAL row, found {len(rows)} in {paths[0]}"
        )
    row = {key: float(value) for key, value in rows[0].items() if key and value}
    required = (
        "fixed_point_iterations",
        "cumulative_fixed_point_iterations",
        "fp_delta_phi_max",
        "issue359_phi_min",
        "issue359_phi_max",
        "issue359_ne_min",
        "issue359_ne_max",
        "issue359_ne_avg",
        "issue359_mean_energy_min",
        "issue359_mean_energy_max",
        "issue359_mean_energy_avg",
        "issue359_Te_min_K",
        "issue359_Te_max_K",
        "issue359_Te_avg_K",
        "issue359_charge_min",
        "issue359_charge_max",
        "issue359_charge_avg",
        "issue359_charge_integral",
    )
    missing = [key for key in required if key not in row]
    if missing:
        raise Issue359Error(f"FINAL diagnostic columns missing: {missing}")

    charge_number_avg = row["issue359_charge_avg"] / ELEMENTARY_CHARGE_C
    relative_charge_imbalance = abs(charge_number_avg) / max(
        abs(row["issue359_ne_avg"]), 1.0
    )
    return {
        "fixed_point_iterations": row["fixed_point_iterations"],
        "cumulative_fixed_point_iterations": row["cumulative_fixed_point_iterations"],
        "delta_phi_max_V": row["fp_delta_phi_max"],
        "phi_min_V": row["issue359_phi_min"],
        "phi_max_V": row["issue359_phi_max"],
        "phi_span_V": row["issue359_phi_max"] - row["issue359_phi_min"],
        "electron_density_min_m3": row["issue359_ne_min"],
        "electron_density_max_m3": row["issue359_ne_max"],
        "electron_density_avg_m3": row["issue359_ne_avg"],
        "mean_energy_min_eV": row["issue359_mean_energy_min"],
        "mean_energy_max_eV": row["issue359_mean_energy_max"],
        "mean_energy_avg_eV": row["issue359_mean_energy_avg"],
        "electron_temperature_min_K": row["issue359_Te_min_K"],
        "electron_temperature_max_K": row["issue359_Te_max_K"],
        "electron_temperature_avg_K": row["issue359_Te_avg_K"],
        "charge_density_min_C_m3": row["issue359_charge_min"],
        "charge_density_max_C_m3": row["issue359_charge_max"],
        "charge_density_avg_C_m3": row["issue359_charge_avg"],
        "volume_charge_C": row["issue359_charge_integral"],
        "charge_number_imbalance_avg_m3": charge_number_avg,
        "relative_charge_imbalance_vs_ne": relative_charge_imbalance,
    }


def _read_step_iterations(case: Path) -> list[dict[str, float]]:
    paths = sorted(case.glob("*_gummel_driver0_step_csv.csv"))
    if len(paths) != 1:
        raise Issue359Error(
            f"expected one Gummel driver STEP CSV, found {len(paths)}: {paths}"
        )
    with paths[0].open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    out: list[dict[str, float]] = []
    for row in rows:
        time_s = float(row.get("time") or 0.0)
        if time_s <= 0.0:
            continue
        out.append(
            {
                "time_s": time_s,
                "fixed_point_iterations": float(row["fixed_point_iterations"]),
                "cumulative_fixed_point_iterations": float(
                    row["cumulative_fixed_point_iterations"]
                ),
                "delta_phi_max_V": float(row["fp_delta_phi_max"]),
            }
        )
    return out


def run(args: argparse.Namespace) -> int:
    exe = resolve_executable(args.physics)
    validate_executable(exe)
    root = args.results_root
    case = root / "case"
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if not (0.0 < args.relaxation_factor < 2.0):
        raise Issue359Error("relaxation factor must be in (0, 2)")
    if args.response_strength <= 0.0:
        raise Issue359Error("response strength must be positive")
    if args.response_radius < 1 or args.response_radius > 5:
        raise Issue359Error("response radius must lie in [1, 5]")
    if args.response_mode not in ("graph", "directional"):
        raise Issue359Error("response mode must be graph or directional")
    if args.electron_substeps not in (1, 2, 4, 8):
        raise Issue359Error("electron substeps must be one of 1, 2, 4, 8")
    meta = _stage(
        case,
        relaxation_factor=args.relaxation_factor,
        response_strength=args.response_strength,
        response_radius=args.response_radius,
        response_mode=args.response_mode,
        electron_substeps=args.electron_substeps,
    )

    checks: dict[str, Any] = {}
    for name in ("electron_sub.i", "poisson_sub.i", "gummel_driver.i", "input.i"):
        result = run_physics(
            exe,
            cwd=case,
            input_name=name,
            log_path=logs / f"check_{name.replace('.i', '')}.log",
            extra_args=("--check-input",),
            timeout_seconds=args.timeout,
        )
        checks[name] = {
            "returncode": result.returncode,
            "wall_seconds": result.wall_seconds,
        }
        if result.returncode != 0:
            summary = {
                "status": "CHECK_INPUT_FAIL",
                "failed_input": name,
                "checks": checks,
                "construction": meta,
            }
            (root / "summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n"
            )
            print(
                "ISSUE359_GUMMEL_ICP_SUMMARY "
                + json.dumps(summary, sort_keys=True)
            )
            return 2

    runtime = run_physics(
        exe,
        cwd=case,
        input_name="input.i",
        log_path=logs / "runtime.log",
        extra_args=("-snes_converged_reason", "-ksp_converged_reason"),
        timeout_seconds=args.timeout,
    )
    diagnostics: dict[str, float] | None = None
    step_iterations: list[dict[str, float]] | None = None
    diagnostic_error: str | None = None
    if runtime.returncode == 0:
        try:
            diagnostics = _read_final_diagnostics(case)
            step_iterations = _read_step_iterations(case)
            if len(step_iterations) != args.electron_substeps:
                raise Issue359Error(
                    f"expected {args.electron_substeps} electron physical steps, "
                    f"found {len(step_iterations)} in driver STEP CSV"
                )
        except Issue359Error as exc:
            diagnostic_error = str(exc)

    status = "RUNTIME_PASS" if runtime.returncode == 0 else "RUNTIME_FAIL"
    if runtime.returncode == 0 and (diagnostics is None or diagnostic_error is not None):
        status = "DIAGNOSTIC_FAIL"

    summary = {
        "status": status,
        "checks": checks,
        "runtime": {
            "returncode": runtime.returncode,
            "wall_seconds": runtime.wall_seconds,
        },
        "final_diagnostics": diagnostics,
        "electron_step_iterations": step_iterations,
        "diagnostic_error": diagnostic_error,
        "construction": meta,
    }
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE359_GUMMEL_ICP_SUMMARY " + json.dumps(summary, sort_keys=True))
    if runtime.returncode != 0:
        return 3
    return 0 if diagnostics is not None else 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics", required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument(
        "--relaxation-factor",
        type=float,
        default=RELAXATION_FACTOR_DEFAULT,
    )
    parser.add_argument(
        "--response-strength",
        type=float,
        default=RESPONSE_STRENGTH_DEFAULT,
    )
    parser.add_argument(
        "--response-radius",
        type=int,
        default=RESPONSE_RADIUS_DEFAULT,
    )
    parser.add_argument(
        "--response-mode",
        choices=("graph", "directional"),
        default=RESPONSE_MODE_DEFAULT,
    )
    parser.add_argument(
        "--electron-substeps",
        type=int,
        choices=(1, 2, 4, 8),
        default=ELECTRON_SUBSTEPS_DEFAULT,
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
