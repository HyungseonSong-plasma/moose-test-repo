#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from physics_harness.adapters.moose import blocks as mb
from physics_harness.adapters.moose import parameters as mp

AVOGADRO = 6.02214076e23

# Canonical Exodus/CSV field order and units.
STANDARD_FIELDS = [
    ("n_e", "1/m^3"),
    ("n_O2", "1/m^3"),
    ("n_O2s", "1/m^3"),
    ("n_O2p", "1/m^3"),
    ("n_O", "1/m^3"),
    ("n_Om", "1/m^3"),
    ("n_Op", "1/m^3"),
    ("n_Os", "1/m^3"),
    ("u", "m/s"),
    ("v", "m/s"),
    ("p", "Pa"),
    ("T_e_eV", "eV"),
    ("phi", "V"),
]

HEAVY = {
    "O2": ("w_O2_constraint", 0.032),
    "O2s": ("w_O2s", 0.032),
    "O2p": ("w_O2p", 0.032),
    "O": ("w_O", 0.016),
    "Om": ("w_Om", 0.016),
    "Op": ("w_Op", 0.016),
    "Os": ("w_Os", 0.016),
}


def add_child(text: str, parent: str, name: str, raw: str) -> str:
    path = f"{parent}/{name}"
    if mb.has_block(text, path):
        raise RuntimeError(f"standard output block already exists: {path}")
    return mb.insert_child_block(text, parent, raw)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: standardize_output.py <case-dir>")

    case = Path(sys.argv[1]).resolve()
    input_path = case / "input.i"
    if not input_path.is_file():
        raise RuntimeError(f"missing generated monolithic input: {input_path}")
    text = input_path.read_text()

    # Heavy species are stored as physical number densities, not solver mass fractions:
    # n_k = rho * w_k * N_A / M_k.
    for species, (mass_fraction, molar_mass) in HEAVY.items():
        prop = f"output_number_density_{species}"
        text = add_child(
            text,
            "FunctorMaterials",
            f"output_number_density_{species}_material",
            f"""  [output_number_density_{species}_material]
    type = ADParsedFunctorMaterial
    property_name = {prop}
    functor_names = 'rho_mat {mass_fraction}'
    functor_symbols = 'rho w'
    expression = 'rho*w*{AVOGADRO:.17g}/{molar_mass:.17g}'
    block = plasma
  []""",
        )

    # Stable output aliases. Internal nonlinear variables remain unchanged.
    output_functors = {
        "n_e": "electron_density_m3",
        "n_O2": "output_number_density_O2",
        "n_O2s": "output_number_density_O2s",
        "n_O2p": "output_number_density_O2p",
        "n_O": "output_number_density_O",
        "n_Om": "output_number_density_Om",
        "n_Op": "output_number_density_Op",
        "n_Os": "output_number_density_Os",
        "T_e_eV": "electron_temperature_eV_functor",
    }

    for variable, functor in output_functors.items():
        text = add_child(
            text,
            "AuxVariables",
            variable,
            f"""  [{variable}]
    type = MooseVariableFVReal
    block = plasma
  []""",
        )
        text = add_child(
            text,
            "AuxKernels",
            f"store_{variable}",
            f"""  [store_{variable}]
    type = FunctorAux
    variable = {variable}
    functor = {functor}
    execute_on = 'INITIAL TIMESTEP_END'
  []""",
        )

    field_names = " ".join(name for name, _ in STANDARD_FIELDS)
    text = mp.upsert_parameter(
        text,
        "VectorPostprocessors/final_profile",
        "variable",
        f"'{field_names}'",
    )
    text = mp.upsert_parameter(
        text,
        "Outputs/exodus",
        "show",
        f"'{field_names}'",
    )

    # Enforce the schema explicitly so accidental internal-state leakage is caught.
    exodus_fields = mp.words(mp.get_parameter(text, "Outputs/exodus", "show") or "")
    if exodus_fields != [name for name, _ in STANDARD_FIELDS]:
        raise RuntimeError(f"Exodus schema mismatch: {exodus_fields}")

    input_path.write_text(text)
    schema = {
        "schema": "plasma_state_v1",
        "density_basis": "number_density",
        "fields": [{"name": name, "unit": unit} for name, unit in STANDARD_FIELDS],
        "notes": {
            "heavy_density": "n_k = rho*w_k*N_A/M_k",
            "O2": "constrained species: w_O2 = 1 - sum(solved heavy mass fractions)",
            "electron_temperature": "T_e_eV = (2/3)*mean_electron_energy_eV",
        },
    }
    (case / "output_schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    print(json.dumps(schema, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
