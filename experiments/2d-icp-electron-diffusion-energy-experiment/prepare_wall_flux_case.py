#!/usr/bin/env python3
"""Prepare a controlled electron-energy wall-flux comparison case."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BOUNDARIES = (
    "inlet outlet plasma_electrode plasma_metal plasma_right "
    "plasma_cover plasma_wafer plasma_focus_ring"
)


def rewrite_scalar(text: str, name: str, value: str) -> str:
    text, count = re.subn(
        rf"(?m)^  {re.escape(name)} = .*$",
        f"  {name} = {value}",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"failed to rewrite {name}: count={count}")
    return text


def prepare(text: str, *, mode: str, energy_factor: float) -> str:
    for name, value in (
        ("dt", "1.0e-9"),
        ("dtmin", "1.0e-9"),
        ("dtmax", "1.0e-9"),
        ("num_steps", "4"),
    ):
        text = rewrite_scalar(text, name, value)

    if mode == "accepted":
        if abs(energy_factor - 2.5) > 1.0e-15:
            raise SystemExit("accepted case is defined only for 5/2 Te")
        return text

    if mode == "native":
        if abs(energy_factor - 2.0) > 1.0e-15:
            raise SystemExit("native case is defined only for 2 Te")
        pattern = re.compile(
            r"(?ms)^  \\[electron_energy_thermal_wall_loss\\]\\n.*?^  \\[\\]\\n"
        )
        replacement = (
            "  [electron_energy_thermal_wall_loss]\\n"
            "    type = PhysicsFVElectronGroundedSheathEnergyBC\\n"
            "    variable = c_epsilon\\n"
            f"    boundary = '{BOUNDARIES}'\\n"
            "    electron_density = c_e_molar\\n"
            "    mean_electron_energy = mean_en_solved\\n"
            "    potential = zero_phi\\n"
            "    molar_energy_state = true\\n"
            "  []\\n"
        )
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise SystemExit(f"failed to restore native energy BC: count={count}")
        return text

    if mode != "functor":
        raise SystemExit(f"unknown mode: {mode}")

    expression = (
        "0.25*ce*sqrt(8.0*1.602176634e-19*((2.0/3.0)*mean_en)/"
        "(3.14159265358979323846*9.1093837139e-31))*"
        f"({energy_factor:.17g}*(2.0/3.0)*mean_en)"
    )
    material = (
        "\n  [wall_energy_flux_control]\n"
        "    type = ADParsedFunctorMaterial\n"
        "    property_name = wall_energy_flux_control\n"
        "    functor_names = 'c_e_molar mean_en_solved'\n"
        "    functor_symbols = 'ce mean_en'\n"
        f"    expression = '{expression}'\n"
        "    block = plasma\n"
        "  []\n"
    )
    existing_material = re.compile(
        r"(?ms)^  \\[electron_energy_transport_matched_wall_flux\\]\\n.*?^  \\[\\]\\n"
    )
    text, count = existing_material.subn(material.lstrip("\n"), text, count=1)
    if count != 1:
        raise SystemExit(f"failed to replace wall energy material: count={count}")

    pattern = re.compile(
        r"(?ms)^  \[electron_energy_thermal_wall_loss\]\n.*?^  \[\]\n"
    )
    replacement = (
        "  [electron_energy_thermal_wall_loss]\n"
        "    type = FVFunctorNeumannBC\n"
        "    variable = c_epsilon\n"
        f"    boundary = '{BOUNDARIES}'\n"
        "    functor = wall_energy_flux_control\n"
        "    factor = -1.0\n"
        "  []\n"
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"failed to replace energy BC: count={count}")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--mode", choices=("accepted", "native", "functor"), required=True)
    parser.add_argument("--energy-factor", type=float, required=True)
    args = parser.parse_args()

    text = args.input.read_text()
    text = prepare(text, mode=args.mode, energy_factor=args.energy_factor)
    args.input.write_text(text)
    print(
        f"WALL_FLUX_CASE_PREPARED mode={args.mode} "
        f"energy_factor={args.energy_factor:.17g} dt=1e-9 steps=4"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
