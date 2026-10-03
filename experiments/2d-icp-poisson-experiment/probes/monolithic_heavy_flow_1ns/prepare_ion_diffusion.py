#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.Issue359_qualified_gummel_icp import heavy_continuity as hc

ROOT = Path(__file__).resolve().parents[4]
DONOR_DIR = ROOT / "experiments/Issue91_real_qvt_r3/r3_e0"
DONOR_INPUT = DONOR_DIR / "heavy_base.i"

DT = 1.0e-8
NUM_STEPS = 10
END_TIME = DT * NUM_STEPS
FLOW_SCCM = 20.0
PRESSURE_PA = 1.333223684
TG_K = 300.0
MEAN_ENERGY_EV = 5.73276
TE_EV = (2.0 / 3.0) * MEAN_ENERGY_EV
EV_TO_K = 11604.518121550082
TE_K = TE_EV * EV_TO_K
NE_M3 = 3.218833278166041e15

MASS_FRACTIONS = {
    "O2": 0.99994,
    "O2s": 1.0e-5,
    "O2p": 1.0e-5,
    "O": 1.0e-5,
    "Om": 1.0e-5,
    "Op": 1.0e-5,
    "Os": 1.0e-5,
}


def replace_top(text: str, name: str, value: str) -> str:
    out, n = re.subn(
        rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*$",
        f"{name} = {value}",
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"expected one top-level assignment for {name}, got {n}")
    return out


def remove_top(text: str, name: str) -> str:
    return re.sub(rf"(?m)^(?!\s){re.escape(name)}\s*=\s*.*\n", "", text, count=1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare_ion_diffusion.py <case-dir>")

    case = Path(sys.argv[1]).resolve()
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)

    text = hc.promote_current_types(DONOR_INPUT.read_text())

    for name, value in (
        ("Q_sccm", FLOW_SCCM),
        ("outlet_pressure", PRESSURE_PA),
        ("T_g_value", TG_K),
        ("T_e_value", TE_K),
        ("n_e_value", NE_M3),
        ("Yin_O2", MASS_FRACTIONS["O2"]),
        ("Yin_O2s", MASS_FRACTIONS["O2s"]),
        ("Yin_O2p", MASS_FRACTIONS["O2p"]),
        ("Yin_O", MASS_FRACTIONS["O"]),
        ("Yin_Om", MASS_FRACTIONS["Om"]),
        ("Yin_Op", MASS_FRACTIONS["Op"]),
        ("Yin_Os", MASS_FRACTIONS["Os"]),
    ):
        text = replace_top(text, name, f"{value:.17g}")

    text = remove_top(text, "E0_migration")
    for path in ("Functions/phi_prescribed", "Functions/ic_w_O_transient", "ICs/ic_w_O"):
        if mb.has_block(text, path):
            text = mb.remove_block(text, path)

    for species in hc.SOLVED_HEAVY:
        text = mp.upsert_parameter(
            text,
            f"Variables/w_{species}",
            "initial_condition",
            f"{MASS_FRACTIONS[species]:.17g}",
        )

    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_names",
        "'T_g T_e n_e mu_flow zero_phi'",
    )
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/state_constants",
        "prop_values",
        "'${T_g_value} ${T_e_value} ${n_e_value} ${mu_const} 0.0'",
    )
    text = mp.upsert_parameter(
        text, "FunctorMaterials/heavy_transport", "electron_temperature", "T_e"
    )
    text = mp.upsert_parameter(
        text, "FunctorMaterials/heavy_transport", "electron_number_density", "n_e"
    )

    for species in hc.CHARGED_HEAVY:
        path = f"FVKernels/{species}_electrostatic_drift"
        if mb.has_block(text, path):
            text = mb.remove_block(text, path)
    for species in hc.SOLVED_HEAVY:
        path = f"FVKernels/{species}_heavy_mass_em_correction"
        if mb.has_block(text, path):
            text = mb.remove_block(text, path)

    text = hc.insert_surface_reactions(text, potential="zero_phi")

    if mb.has_block(text, "AuxVariables") or mb.has_block(text, "AuxKernels"):
        raise RuntimeError("heavy donor unexpectedly already contains AuxVariables/AuxKernels")

    diagnostics = '''
[AuxVariables]
  [n_O2p]
    type = MooseVariableFVReal
    block = plasma
  []
  [n_Om]
    type = MooseVariableFVReal
    block = plasma
  []
  [n_Op]
    type = MooseVariableFVReal
    block = plasma
  []
  [Dmix_O2p]
    type = MooseVariableFVReal
    block = plasma
  []
  [Dmix_Om]
    type = MooseVariableFVReal
    block = plasma
  []
  [Dmix_Op]
    type = MooseVariableFVReal
    block = plasma
  []
[]

[AuxKernels]
  [n_O2p_copy]
    type = FunctorAux
    variable = n_O2p
    functor = number_density_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_Om_copy]
    type = FunctorAux
    variable = n_Om
    functor = number_density_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [n_Op_copy]
    type = FunctorAux
    variable = n_Op
    functor = number_density_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_O2p_copy]
    type = FunctorAux
    variable = Dmix_O2p
    functor = D_mix_O2p
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_Om_copy]
    type = FunctorAux
    variable = Dmix_Om
    functor = D_mix_Om
    execute_on = 'INITIAL TIMESTEP_END'
  []
  [Dmix_Op_copy]
    type = FunctorAux
    variable = Dmix_Op
    functor = D_mix_Op
    execute_on = 'INITIAL TIMESTEP_END'
  []
[]
'''
    exec_pos = text.find("[Executioner]")
    if exec_pos < 0:
        raise RuntimeError("heavy donor is missing [Executioner]")
    text = text[:exec_pos] + diagnostics + "\n" + text[exec_pos:]

    for key, value in (
        ("dt", f"{DT:.17g}"),
        ("dtmin", f"{DT:.17g}"),
        ("dtmax", f"{DT:.17g}"),
        ("end_time", f"{END_TIME:.17g}"),
        ("num_steps", str(NUM_STEPS)),
        ("timestep_tolerance", "1.0e-18"),
        ("nl_rel_tol", "1.0e-8"),
        ("nl_abs_tol", "1.0e-11"),
        ("nl_max_its", "80"),
        ("automatic_scaling", "true"),
        ("off_diagonals_in_auto_scaling", "true"),
        ("compute_scaling_once", "false"),
    ):
        text = mp.upsert_parameter(text, "Executioner", key, value)

    text = mp.upsert_parameter(text, "Outputs", "csv", "true")
    text = mp.upsert_parameter(text, "Outputs", "exodus", "true")
    text = mp.upsert_parameter(text, "Outputs", "file_base", "ion_diffusion")
    text = mp.upsert_parameter(text, "Outputs", "execute_on", "'INITIAL TIMESTEP_END'")
    text = mp.upsert_parameter(
        text,
        "Outputs",
        "show",
        "'u v p w_O2s w_O2p w_O w_Om w_Op w_Os n_O2p n_Om n_Op Dmix_O2p Dmix_Om Dmix_Op'",
    )

    charged_diffusion_checks = {}
    for species in hc.CHARGED_HEAVY:
        path = f"FVKernels/{species}_diffusion"
        charged_diffusion_checks[f"{species}_diffusion_present"] = (
            mb.has_block(text, path)
            and mp.get_parameter(text, path, "diffusivity") == f"D_mix_{species}"
        )

    checks = {
        "electron_particle_equation_absent": (
            not mb.has_block(text, "Variables/log_e")
            and not mb.has_block(text, "FVKernels/electron_time")
            and not mb.has_block(text, "FVKernels/electron_diffusion")
        ),
        "electron_energy_equation_absent": (
            not mb.has_block(text, "Variables/c_epsilon")
            and not mb.has_block(text, "Variables/log_c_epsilon")
            and not mb.has_block(text, "FVKernels/energy_time")
            and not mb.has_block(text, "FVKernels/energy_diffusion")
        ),
        "poisson_equation_absent": (
            not mb.has_block(text, "Variables/phi")
            and not mb.has_block(text, "FVKernels/phi_diffusion")
            and not mb.has_block(text, "FVKernels/phi_charge_source")
        ),
        "bulk_electric_drift_absent": all(
            not mb.has_block(text, f"FVKernels/{s}_electrostatic_drift")
            for s in hc.CHARGED_HEAVY
        ),
        "heavy_em_correction_absent": all(
            not mb.has_block(text, f"FVKernels/{s}_heavy_mass_em_correction")
            for s in hc.SOLVED_HEAVY
        ),
        "fixed_electron_inputs_for_transport_only": (
            mp.get_parameter(text, "FunctorMaterials/heavy_transport", "electron_temperature")
            == "T_e"
            and mp.get_parameter(text, "FunctorMaterials/heavy_transport", "electron_number_density")
            == "n_e"
        ),
        "wall_migration_zero_field": all(
            mp.get_parameter(text, f"FunctorMaterials/{s}_wall_flux", "potential")
            == "zero_phi"
            for s in hc.CHARGED_HEAVY
        ),
        "dt_10ns_10steps": (
            float(mp.get_parameter(text, "Executioner", "dt") or "nan") == DT
            and float(mp.get_parameter(text, "Executioner", "end_time") or "nan") == END_TIME
            and int(mp.get_parameter(text, "Executioner", "num_steps") or "0") == NUM_STEPS
        ),
        "inlet_20_sccm": re.search(r"(?m)^Q_sccm\s*=\s*20(?:\.0+)?\s*$", text) is not None,
        "outlet_10_mTorr": re.search(
            r"(?m)^outlet_pressure\s*=\s*1\.333223684\s*$", text
        ) is not None,
        **charged_diffusion_checks,
    }

    failed = sorted(name for name, ok in checks.items() if not ok)
    contract = {
        "probe": "heavy-ion-diffusion-only-10x10ns",
        "physics": {
            "flow": True,
            "heavy_species_continuity": list(hc.SOLVED_HEAVY),
            "charged_species_focus": list(hc.CHARGED_HEAVY),
            "electron_particle_equation": False,
            "electron_energy_equation": False,
            "poisson_equation": False,
            "bulk_electric_drift": False,
            "heavy_mass_em_correction": False,
            "surface_chemistry": True,
            "charged_wall_migration": "zero because potential=zero_phi",
        },
        "transport_closure": {
            "gas_temperature_K": TG_K,
            "fixed_electron_temperature_K": TE_K,
            "fixed_electron_temperature_eV": TE_EV,
            "fixed_electron_density_m3": NE_M3,
            "transport_data_file": "transport_data.txt",
        },
        "dt_s": DT,
        "num_steps": NUM_STEPS,
        "end_time_s": END_TIME,
        "flow_sccm": FLOW_SCCM,
        "outlet_pressure_Pa": PRESSURE_PA,
        "outlet_pressure_mTorr": 10.0,
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
    }

    (case / "input.i").write_text(text)
    (case / "probe_contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n"
    )

    for src in (DONOR_DIR / "qvt.msh", DONOR_DIR / "transport_data.txt"):
        if not src.is_file():
            raise RuntimeError(f"required donor file missing: {src}")
        shutil.copy2(src, case / src.name)

    print(json.dumps(contract, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f"ion diffusion probe contract failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
