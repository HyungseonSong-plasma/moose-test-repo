#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import prepare_l4_dt_compare as core
import prepare_l4_dt_ramp_ionization_20ns_compare as ion

HERE = Path(__file__).resolve().parent
GROUNDED_BOUNDARIES = (
    "inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover "
    "plasma_wafer plasma_focus_ring"
)


def build() -> Path:
    # Same 20 ns Ti=Te=2 eV ionization-only ramp as the earlier temperature test:
    #   0 -> 10 ns : 0.1 ns x 100
    #   10 -> 20 ns: 0.2 ns x 50
    # Then suppress only the Joule energy residual in the first FV cells touching
    # the eight grounded boundaries.  Poisson, electron transport, sheath particle
    # loss, ionization, and all heavy-species transport remain unchanged.
    base = ion.build("ti_te_2eV")
    text = base.read_text(encoding="utf-8")

    text = core.set_child_parameter(
        text,
        "energy_joule",
        "suppress_joule_on_boundaries",
        f"'{GROUNDED_BOUNDARIES}'",
    )

    energy_joule = core.child_block(text, "energy_joule")
    required = (
        "type = PhysicsFVElectronEnergyJouleHeating",
        "potential = potential",
        "electron_density = electron_molar_density",
        "mobility = electron_mobility",
        "diffusion = electron_diffusion",
        "state_form = molar_eV",
        f"suppress_joule_on_boundaries = '{GROUNDED_BOUNDARIES}'",
    )
    for token in required:
        if token not in energy_joule:
            raise RuntimeError(f"energy_joule missing required token: {token}")

    # Chemistry contract for this diagnostic: ionization ON, dissociation OFF.
    required_ionization = (
        "type = PhysicsElectronImpactIonizationMaterial",
        "rate_table_file = ../../physics_app/data/electron_impact/o2_ionization.txt",
        "type = PhysicsO2IonizationSourceMaterial",
        "number_source = electron_ionization_number_source",
        "source = O2p_ionization_mass_source",
        "coef = -12.06",
    )
    for token in required_ionization:
        if token not in text:
            raise RuntimeError(f"ionization-only case missing required token: {token}")

    forbidden_dissociation = (
        "PhysicsElectronImpactDissociationMaterial",
        "R_diss_O2",
        "O2_dissociation_mass_source",
        "O_dissociation_mass_source",
        "dissociation_mass_balance",
        "o2_dissociation.txt",
    )
    for token in forbidden_dissociation:
        if token in text:
            raise RuntimeError(f"dissociation leaked into no-dissociation case: {token}")

    if "axis" in GROUNDED_BOUNDARIES or "x=0" in GROUNDED_BOUNDARIES:
        raise RuntimeError("symmetry axis must never be a Joule-suppression boundary")

    out = HERE / "full_monolithic_l4_joule_wall_layer_suppress_no_dissociation_ti_te_2eV.i"
    out.write_text(text, encoding="utf-8")

    print(f"wrote {out}")
    print("case=suppress_wall_layer_no_dissociation")
    print("base=Ti=Te=2 eV + O2 ionization only")
    print("dissociation=OFF")
    print("Joule residual suppressed only in cells directly touching grounded boundaries")
    print(f"suppressed boundaries={GROUNDED_BOUNDARIES}")
    print("x=0 symmetry axis remains unsuppressed and is not a boundary condition")
    print("ramp=0.1 ns x100 then 0.2 ns x50; end_time=20 ns")
    return out


if __name__ == "__main__":
    build()
