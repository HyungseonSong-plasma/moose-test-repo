#!/usr/bin/env python3
"""Research-only ICP inlet overlay matched to the fixed-composition 100-point EEDF."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "oxygen_icp_operating_200sccm_sticking1.json"
SPECIES_TO_Y = {
    "O2_X": "Yin_O2",
    "O2_a1Delta": "Yin_O2s",
    "O_3P": "Yin_O",
    "O_1D": "Yin_Os",
}
CHARGED_INLET_ZERO = ("Yin_O2p", "Yin_Om", "Yin_Op")
FRACTIONS = tuple(SPECIES_TO_Y.values()) + CHARGED_INLET_ZERO


def replace_unique(text: str, name: str, value: str) -> str:
    pat = rf"(?m)^{re.escape(name)}\s*=\s*[^#\r\n]+$"
    hits = re.findall(pat, text)
    if len(hits) != 1:
        raise ValueError(f"require exactly one top-level {name}; found {len(hits)}")
    return re.sub(pat, f"{name} = {value}", text, count=1)


def validated_mass_fractions(config: dict) -> dict[str, float]:
    inlet = config["inlet"]
    x = inlet["mole_fractions"]
    molar = inlet["molar_masses_kg_per_mol"]
    if set(x) != set(SPECIES_TO_Y) or set(molar) != set(x):
        raise ValueError("Boltzmann four-target species set mismatch")
    if not math.isclose(sum(x.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("Boltzmann mole fractions do not sum to one")
    if not all(math.isfinite(v) and v >= 0 for v in x.values()):
        raise ValueError("invalid Boltzmann mole fraction")
    mean_molar_mass = sum(x[k] * molar[k] for k in x)
    if mean_molar_mass <= 0:
        raise ValueError("invalid mixture molar mass")
    mass = {SPECIES_TO_Y[k]: x[k] * molar[k] / mean_molar_mass for k in x}
    mass.update({k: 0.0 for k in CHARGED_INLET_ZERO})
    for k, value in mass.items():
        if not math.isclose(value, inlet["mass_fractions"][k], rel_tol=1e-12, abs_tol=1e-15):
            raise ValueError(f"mole-to-mass conversion mismatch: {k}")
    if not math.isclose(sum(mass.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("inlet mass fractions do not sum to one")
    if not math.isclose(mean_molar_mass, inlet["mean_molar_mass_kg_per_mol"], rel_tol=1e-12):
        raise ValueError("mean inlet molar mass mismatch")
    mdot = inlet["Q_sccm"] * 1e-6 / 60 * mean_molar_mass / inlet["Vm_std_m3_per_mol"]
    if not math.isclose(mdot, inlet["total_mass_flow_kg_s"], rel_tol=1e-12):
        raise ValueError("inlet mass flow inconsistent with composition")
    return mass


def apply(text: str) -> str:
    if "inlet_mdot_value" not in text or "Vm_std" not in text or "Q_std" not in text:
        raise ValueError("canonical inlet mass-flow conversion not present")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config["inlet"]["Q_sccm"] != 200:
        raise ValueError("only the approved 200 sccm research case is allowed")
    mass = validated_mass_fractions(config)
    text = replace_unique(text, "Q_sccm", str(config["inlet"]["Q_sccm"]))
    for name, value in mass.items():
        text = replace_unique(text, name, format(value, ".17g"))
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.base_input.resolve() == args.output.resolve():
        raise ValueError("refusing to overwrite the qualified reference input")
    result = apply(args.base_input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result, encoding="utf-8")
    print("OXYGEN_ICP_200SCCM_BOLTZMANN_MIXTURE_INLET_CONSTRUCTED")
    print("Existing ion and neutral bulk initial densities are unchanged.")
    print("Sticking=1 must be enabled via the separate research_uniform_sticking option.")


if __name__ == "__main__":
    main()
