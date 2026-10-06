#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import prepare_l4_dt_compare as core
import prepare_l4_dt_ramp_ionization_20ns_compare as ramp
import prepare_l4_o2_ionization_ab as chem

HERE = Path(__file__).resolve().parent
GROUNDED_BOUNDARIES = (
    "inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover "
    "plasma_wafer plasma_focus_ring"
)
CASES = ("ionization_only", "chemistry_off")


def _suppress_wall_layer_joule(text: str) -> str:
    text = core.set_child_parameter(
        text,
        "energy_joule",
        "suppress_joule_on_boundaries",
        f"'{GROUNDED_BOUNDARIES}'",
    )
    block = core.child_block(text, "energy_joule")
    expected = f"suppress_joule_on_boundaries = '{GROUNDED_BOUNDARIES}'"
    if expected not in block:
        raise RuntimeError("missing exact grounded-boundary Joule suppression set")
    if "axis" in GROUNDED_BOUNDARIES or "x=0" in GROUNDED_BOUNDARIES:
        raise RuntimeError("symmetry axis must not be a Joule-suppression boundary")
    return text


def _build_chemistry_off_20ns() -> str:
    # Start from the established chemistry-off feedback case, then impose the
    # same Ti=Te=2 eV startup and exact 20 ns ramp used by the suppression run.
    base = chem.build("chem_off")
    text = base.read_text(encoding="utf-8")
    text = ramp._set_initial_mean_energy(text, 3.0)
    text = ramp._set_ion_temperature(text, 2.0)
    text = ramp._set_time_ramp(text)
    return text


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)

    if case == "ionization_only":
        # Ti=Te=2 eV, ne=nO2+=1e15 m^-3, ionization ON, dissociation OFF,
        # 0.1 ns x100 then 0.2 ns x50 to 20 ns.
        base = ramp.build("ti_te_2eV")
        text = base.read_text(encoding="utf-8")
    else:
        text = _build_chemistry_off_20ns()

    text = _suppress_wall_layer_joule(text)

    common_required = (
        "ion_temperature_eV = 2.0",
        "type = TimeSequenceStepper",
        "end_time = 2e-08",
        "type = PhysicsFVElectronEnergyJouleHeating",
        "potential = potential",
        "electron_density = electron_molar_density",
        "mobility = electron_mobility",
        "diffusion = electron_diffusion",
        "state_form = molar_eV",
        f"suppress_joule_on_boundaries = '{GROUNDED_BOUNDARIES}'",
    )
    for token in common_required:
        if token not in text:
            raise RuntimeError(f"common suppression contract missing: {token}")

    ionization_tokens = (
        "type = PhysicsElectronImpactIonizationMaterial",
        "rate_table_file = ../../physics_app/data/electron_impact/o2_ionization.txt",
        "type = PhysicsO2IonizationSourceMaterial",
        "number_source = electron_ionization_number_source",
        "source = O2p_ionization_mass_source",
        "v = R_ion_O2",
        "coef = -12.06",
    )
    dissociation_tokens = (
        "PhysicsElectronImpactDissociationMaterial",
        "R_diss_O2",
        "O_dissociation_mass_source",
        "o2_dissociation_energy_loss",
    )

    if case == "ionization_only":
        for token in ionization_tokens:
            if token not in text:
                raise RuntimeError(f"ionization-only contract missing: {token}")
        for token in dissociation_tokens:
            if token in text:
                raise RuntimeError(f"dissociation leaked into ionization-only case: {token}")
    else:
        for token in ionization_tokens + dissociation_tokens:
            if token in text:
                raise RuntimeError(f"chemistry leaked into chemistry-off case: {token}")

    # Attachment remains OFF in both cases.
    for token in ("R_attachment", "o2_attachment.txt", "PhysicsElectronImpactAttachmentMaterial"):
        if token in text:
            raise RuntimeError(f"attachment leaked into chemistry discriminator: {token}")

    out = HERE / f"full_monolithic_l4_joule_suppression_{case}_ti_te_2eV.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case}")
    print("Ti=2 eV; Te=2 eV; initial mean electron energy=3 eV")
    print("Joule residual suppressed only in cells touching grounded boundaries")
    print(f"suppressed boundaries={GROUNDED_BOUNDARIES}")
    print("x=0 symmetry axis remains unsuppressed and is not a boundary condition")
    print("ramp=0.1 ns x100 then 0.2 ns x50; end_time=20 ns")
    if case == "ionization_only":
        print("chemistry=O2 ionization ON; O2 dissociation OFF; attachment OFF")
    else:
        print("chemistry=OFF: ionization OFF; dissociation OFF; attachment OFF")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=CASES)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
