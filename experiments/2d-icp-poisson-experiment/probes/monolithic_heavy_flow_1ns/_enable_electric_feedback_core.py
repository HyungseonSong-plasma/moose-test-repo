#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp
from experiments.Issue359_qualified_gummel_icp import heavy_continuity as hc

ALL_BOUNDARIES = (
    "inlet", "outlet", "plasma_electrode", "plasma_metal",
    "plasma_right", "plasma_cover", "plasma_wafer", "plasma_focus_ring",
)
BOUNDARY_LIST = "'" + " ".join(ALL_BOUNDARIES) + "'"
HEAVY_CHARGES = {"O2p": 1, "Om": -1, "Op": 1}
HEAVY_MOBILITY = {"O2p": "mu_O2p", "Om": "mu_Om", "Op": "mu_Op"}


def insert_absent(text: str, parent: str, name: str, body: str) -> str:
    path = f"{parent}/{name}"
    if mb.has_block(text, path):
        raise RuntimeError(f"feedback block already exists: {path}")
    return mb.insert_child_block(text, parent, body)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: enable_electric_feedback.py <case-dir>")

    case = Path(sys.argv[1]).resolve()
    path = case / "input.i"
    if not path.is_file():
        raise RuntimeError(f"missing generated monolithic input: {path}")
    text = path.read_text()

    # Dimensionless carrier used by electron particle/energy drift. Mobility
    # remains the live electron_moments.txt lookup output; no Einstein closure.
    names = mp.words(mp.get_parameter(text, "FunctorMaterials/constants", "prop_names") or "")
    values = mp.words(mp.get_parameter(text, "FunctorMaterials/constants", "prop_values") or "")
    if "carrier_one" in names:
        raise RuntimeError("carrier_one unexpectedly already exists")
    if len(names) != len(values):
        raise RuntimeError(f"constants prop_names/prop_values mismatch: {names} / {values}")
    text = mp.upsert_parameter(
        text, "FunctorMaterials/constants", "prop_names",
        "'" + " ".join((*names, "carrier_one")) + "'",
    )
    text = mp.upsert_parameter(
        text, "FunctorMaterials/constants", "prop_values",
        "'" + " ".join((*values, "1.0")) + "'",
    )

    # Electron particle flux: Gamma_e = -mu_e(table)*c_e*E - D_e(table)*grad(c_e).
    # No neutral-gas u/v advection is introduced in the electron equation.
    text = insert_absent(
        text, "FVKernels", "electron_drift",
        f"""  [electron_drift]
    type = PhysicsFVLogMolarElectrostaticDrift
    variable = log_e
    potential = phi
    mobility = electron_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = {BOUNDARY_LIST}
    block = plasma
  []""",
    )

    # Consistent two-moment energy transport: use the separately tabulated
    # electron-energy mobility. Joule heating stays OFF in this discriminator.
    text = insert_absent(
        text, "FVKernels", "energy_drift",
        f"""  [energy_drift]
    type = PhysicsFVElectrostaticDrift
    variable = c_epsilon
    potential = phi
    mobility = electron_energy_mobility
    carrier = carrier_one
    charge_number = -1
    advected_interp_method = upwind
    boundaries_to_avoid = {BOUNDARY_LIST}
    block = plasma
  []""",
    )

    # Charged-heavy bulk electrostatic drift using the live solved phi.
    for species in hc.CHARGED_HEAVY:
        text = insert_absent(
            text, "FVKernels", f"{species}_electrostatic_drift",
            f"""  [{species}_electrostatic_drift]
    type = PhysicsFVElectrostaticDrift
    variable = w_{species}
    potential = phi
    mobility = {HEAVY_MOBILITY[species]}
    carrier = rho_mat
    charge_number = {HEAVY_CHARGES[species]}
    advected_interp_method = upwind
    boundaries_to_avoid = {BOUNDARY_LIST}
    block = plasma
  []""",
        )

    # Heavy mixture-mass electromigration correction, also driven by live phi.
    for species in hc.SOLVED_HEAVY:
        text = insert_absent(
            text, "FVKernels", f"{species}_heavy_mass_em_correction",
            f"""  [{species}_heavy_mass_em_correction]
    type = PhysicsFVHeavyMassElectromigrationCorrection
    variable = w_{species}
    potential = phi
    rho = rho_mat
    ion_mass_fractions = 'w_O2p w_Om w_Op'
    ion_mobilities = 'mu_O2p mu_Om mu_Op'
    ion_charges = '1 -1 1'
    advected_interp_method = upwind
    boundaries_to_avoid = {BOUNDARY_LIST}
    block = plasma
  []""",
        )

    # Runtime evidence for the lookup-provided mobilities.
    for name, functor in (
        ("electron_mobility_avg", "electron_mobility"),
        ("electron_energy_mobility_avg", "electron_energy_mobility"),
    ):
        text = insert_absent(
            text, "Postprocessors", name,
            f"""  [{name}]
    type = ElementAverageFunctorPostprocessor
    functor = {functor}
    block = plasma
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    checks = {
        "electron_particle_drift_on": (
            mp.get_parameter(text, "FVKernels/electron_drift", "type")
            == "PhysicsFVLogMolarElectrostaticDrift"
            and mp.get_parameter(text, "FVKernels/electron_drift", "potential") == "phi"
            and mp.get_parameter(text, "FVKernels/electron_drift", "mobility") == "electron_mobility"
            and mp.get_parameter(text, "FVKernels/electron_drift", "charge_number") == "-1"
        ),
        "electron_energy_drift_on": (
            mp.get_parameter(text, "FVKernels/energy_drift", "type")
            == "PhysicsFVElectrostaticDrift"
            and mp.get_parameter(text, "FVKernels/energy_drift", "mobility")
            == "electron_energy_mobility"
            and mp.get_parameter(text, "FVKernels/energy_drift", "charge_number") == "-1"
        ),
        "no_electron_gas_advection": not mb.has_block(text, "FVKernels/electron_advection"),
        "electron_mobility_from_lookup": (
            mp.get_parameter(text, "FunctorMaterials/electron_transport", "transport_table_file")
            == "electron_moments.txt"
            and mp.get_parameter(text, "FunctorMaterials/electron_transport", "electron_mobility_output")
            == "electron_mobility"
            and mp.get_parameter(
                text, "FunctorMaterials/electron_transport", "electron_energy_mobility_output"
            ) == "electron_energy_mobility"
        ),
        "heavy_bulk_drift_on": all(
            mb.has_block(text, f"FVKernels/{s}_electrostatic_drift")
            and mp.get_parameter(text, f"FVKernels/{s}_electrostatic_drift", "potential") == "phi"
            for s in hc.CHARGED_HEAVY
        ),
        "heavy_em_mass_correction_on": all(
            mb.has_block(text, f"FVKernels/{s}_heavy_mass_em_correction")
            and mp.get_parameter(text, f"FVKernels/{s}_heavy_mass_em_correction", "potential") == "phi"
            for s in hc.SOLVED_HEAVY
        ),
        "heavy_wall_migration_live_phi": all(
            mp.get_parameter(text, f"FunctorMaterials/{s}_wall_flux", "potential") == "phi"
            for s in hc.CHARGED_HEAVY
        ),
        "joule_heating_off": not mb.has_block(text, "FVKernels/energy_joule"),
        "electron_wall_collection_unchanged": (
            mp.get_parameter(text, "FVBCs/electron_thermal_wall_loss", "potential") == "zero_phi"
            and mp.get_parameter(text, "FVBCs/electron_energy_thermal_wall_loss", "potential") == "zero_phi"
        ),
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    contract = {
        "model": "monolithic-live-electric-field-feedback",
        "electron_particle_flux": "-mu_e(table)*c_e*E - D_e(table)*grad(c_e)",
        "electron_gas_advection": False,
        "electron_particle_mobility": "electron_mobility from electron_moments.txt lookup",
        "electron_energy_mobility": "electron_energy_mobility from electron_moments.txt lookup",
        "electron_energy_drift": True,
        "electron_joule_heating": False,
        "heavy_charged_bulk_drift": True,
        "heavy_wall_one_sided_migration": True,
        "heavy_mass_em_correction": True,
        "feedback_potential": "phi",
        "physical_boundary_drift_flux_owned_by_bulk_kernel": False,
        "electron_wall_sheath_potential_feedback": False,
        "checks": checks,
        "failed_checks": failed,
        "status": "PASS" if not failed else "FAIL",
    }

    path.write_text(text)
    (case / "electric_feedback_contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(contract, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(f"electric feedback contract failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
