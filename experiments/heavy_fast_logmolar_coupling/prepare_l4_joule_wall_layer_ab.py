#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import prepare_l4_dt_compare as core
import prepare_l4_dt_ramp_dissociation_20ns as diss

HERE = Path(__file__).resolve().parent
GROUNDED_BOUNDARIES = (
    "inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover "
    "plasma_wafer plasma_focus_ring"
)
CASES = ("baseline", "suppress_wall_layer")


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)

    base = diss.build()
    text = base.read_text(encoding="utf-8")

    if case == "suppress_wall_layer":
        text = core.set_child_parameter(
            text,
            "energy_joule",
            "suppress_joule_on_boundaries",
            f"'{GROUNDED_BOUNDARIES}'",
        )
    else:
        block = core.child_block(text, "energy_joule")
        if "suppress_joule_on_boundaries" in block:
            raise RuntimeError("baseline unexpectedly suppresses Joule heating")

    energy_joule = core.child_block(text, "energy_joule")
    required = (
        "type = PhysicsFVElectronEnergyJouleHeating",
        "potential = potential",
        "electron_density = electron_molar_density",
        "mobility = electron_mobility",
        "diffusion = electron_diffusion",
        "state_form = molar_eV",
    )
    for token in required:
        if token not in energy_joule:
            raise RuntimeError(f"energy_joule missing required token: {token}")

    if case == "suppress_wall_layer":
        expected = f"suppress_joule_on_boundaries = '{GROUNDED_BOUNDARIES}'"
        if expected not in energy_joule:
            raise RuntimeError("suppressed case is missing the exact grounded-boundary set")
        if "axis" in GROUNDED_BOUNDARIES or "x=0" in GROUNDED_BOUNDARIES:
            raise RuntimeError("symmetry axis must never be a Joule-suppression boundary")

    out = HERE / f"full_monolithic_l4_joule_wall_layer_{case}_ti_te_2eV.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case}")
    print("base=Ti=Te=2 eV + O2 ionization + O2 dissociation")
    if case == "suppress_wall_layer":
        print("diagnostic: Joule residual suppressed only in cells directly touching grounded boundaries")
        print(f"suppressed boundaries={GROUNDED_BOUNDARIES}")
        print("x=0 symmetry axis remains unsuppressed and is not a boundary condition")
    else:
        print("diagnostic baseline: Joule residual unchanged in all cells")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=CASES)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
