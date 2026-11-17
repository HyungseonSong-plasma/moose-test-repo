"""Issue #633 C2 P0-only JSON wall/BC contract and negative-controls checker.

This deliberately does not instantiate MOOSE objects. The authoritative
runtime parser/generator is PhysicsApp ChemistryData/PlasmasAction; exact-HEAD
physics-opt compile/P2 and complete warehouse checks remain separate gates.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

GENERAL = ("inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right")
DIELECTRIC = ("cover", "wafer", "focus_ring")
ION_IDS = ("O2p", "Om", "Op")
MASS = {"O2p": 0.032, "Om": 0.016, "Op": 0.016}
CHARGE = {"O2p": 1, "Om": -1, "Op": 1}
FACTOR = -1.6605390671738466e-24
WALL_FIELDS = {
    "ion_number_density", "potential", "mobility", "gas_temperature",
    "block", "molar_mass", "sticking", "ion_temperature_eV",
    "migration_gate_smoothing_width", "use_element_gradient_for_potential",
}


class C2ContractError(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise C2ContractError(reason)


def finite_num(v, lo=None, hi=None) -> bool:
    return (type(v) in (int, float) and math.isfinite(v)
            and (lo is None or v >= lo) and (hi is None or v <= hi))


def validate(overlay: dict, selected=ION_IDS) -> dict[str, int]:
    require(isinstance(overlay, dict), "JSON_OBJECT_REQUIRED")
    require(isinstance(selected, (list, tuple)) and bool(selected) and
            len(set(selected)) == len(selected) and
            set(selected) <= set(ION_IDS), "INVALID_SELECTED_SPECIES")
    species = overlay.get("species")
    require(isinstance(species, dict), "SPECIES_JSON_REQUIRED")
    with_walls = {k for k, v in species.items()
                  if isinstance(v, dict) and "ion_wall" in v}
    require(with_walls == set(selected), "SELECTED_ION_WALL_OWNER_MISMATCH")
    for ident in selected:
        record = species[ident]
        require(record.get("charge_number") == CHARGE[ident], "WRONG_ION_CHARGE_" + ident)
        wall = record["ion_wall"]
        require(isinstance(wall, dict) and set(wall) == WALL_FIELDS,
                "INVALID_ION_WALL_FIELDS_" + ident)
        for key in ("ion_number_density", "potential", "mobility", "gas_temperature", "block"):
            require(isinstance(wall[key], str) and bool(wall[key]),
                    "INVALID_WALL_FUNCTOR_OR_BLOCK_" + ident + "_" + key)
        require(wall["ion_number_density"] == ident + "_number_density",
                "WRONG_DENSITY_FUNCTOR_" + ident)
        require(wall["mobility"] == ident + "_mobility",
                "WRONG_MOBILITY_FUNCTOR_" + ident)
        require(wall["potential"] == "potential", "WALL_POTENTIAL_MISMATCH_" + ident)
        require(wall["block"] == "plasma", "WALL_BLOCK_MISMATCH_" + ident)
        require(finite_num(wall["molar_mass"], 1e-300) and
                math.isclose(wall["molar_mass"], MASS[ident], rel_tol=1e-12),
                "WRONG_WALL_MOLAR_MASS_" + ident)
        require(finite_num(wall["sticking"], 0, 1), "INVALID_STICKING_" + ident)
        for key in ("ion_temperature_eV", "migration_gate_smoothing_width"):
            require(finite_num(wall[key], 0), "INVALID_" + key + "_" + ident)
        require(type(wall["use_element_gradient_for_potential"]) is bool,
                "INVALID_GRADIENT_FLAG_" + ident)

    current = overlay.get("ion_surface_current")
    # The exact producer is explicit. In older generated DD it is the legacy
    # electron_wall_number_flux; canonical S6 scratch can publish e_wall_number_flux.
    require(isinstance(current, dict) and
            set(current) == {"electron_wall_number_flux"} and
            isinstance(current["electron_wall_number_flux"], str) and
            current["electron_wall_number_flux"] in {
                "electron_wall_number_flux", "e_wall_number_flux"},
            "INVALID_SURFACE_CURRENT_ELECTRON_CONSUMER")

    boundaries = overlay.get("boundaries")
    require(isinstance(boundaries, dict), "MISSING_BOUNDARIES")
    # A single group can own several sidesets. An electron FEM sheath operator
    # may share that group with ion FV BCs: do not falsely reject co-resident
    # electron consumers when the input's root boundaries records are merged.
    required_groups = {" ".join(GENERAL), *(f"plasma_{s}" for s in DIELECTRIC)}
    require(required_groups <= set(boundaries), "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")
    found: dict[str, dict] = {}
    all_names: set[str] = set()
    used_sides: set[str] = set()
    operator_owners: set[tuple[str, str, str]] = set()
    for sides, group in boundaries.items():
        members = sides.split()
        require(bool(members) and len(set(members)) == len(members) and
                not (set(members) & used_sides), "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")
        used_sides.update(members)
        require(isinstance(group, dict) and set(group) == {"bcs"} and
                isinstance(group["bcs"], dict), "INVALID_BC_GROUP")
        require(bool(group["bcs"]), "EMPTY_BC_GROUP")
        for name, bc in group["bcs"].items():
            require(name not in all_names, "DUPLICATE_BC_NAME_" + name)
            all_names.add(name)
            require(isinstance(bc, dict), "INVALID_BC_ENTRY_" + name)
            typ = bc.get("type")
            variable = bc.get("variable")
            require(isinstance(typ, str) and bool(typ), "INVALID_BC_TYPE_" + name)
            require(isinstance(variable, str) and bool(variable),
                    "INVALID_BC_VARIABLE_" + name)
            for side in members:
                key = (typ, variable, side)
                require(key not in operator_owners, "DUPLICATE_BC_OPERATOR_" + name)
                operator_owners.add(key)
            if typ in {"FEMElectronSheathBC", "FEMElectronEnergySheathBC"}:
                required = {"type", "variable", "wall_number_flux"}
                if typ == "FEMElectronEnergySheathBC":
                    required.add("mean_energy")
                expected_electron_variable = (
                    "log_e_energy" if typ == "FEMElectronEnergySheathBC" else "log_e")
                require(set(bc) == required and variable == expected_electron_variable and
                        bc["wall_number_flux"] == "electron_wall_number_flux" and
                        (typ != "FEMElectronEnergySheathBC" or
                         bc["mean_energy"] == "e_energy_eV"),
                        "INVALID_EXISTING_FEM_ELECTRON_BC_" + name)
                continue
            require(typ in {"FVFunctorNeumannBC", "FVLogMolarDielectricFluxBC"},
                    "UNSUPPORTED_FV_BC_TYPE_" + name)
            require(variable.startswith("log_"), "INVALID_BC_VARIABLE_" + name)
            ident = variable[4:]
            require(ident in selected, "UNSELECTED_ION_BC_" + name)
            flux = ident + "_wall_number_flux"
            found[name] = bc
            if typ == "FVFunctorNeumannBC":
                require(set(members) == set(GENERAL),
                        "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")
                require(name == ident + "_wall", "WRONG_NEUMANN_BC_NAME_" + name)
                require(set(bc) == {"type", "variable", "functor", "factor"} and
                        bc["functor"] == flux and
                        finite_num(bc["factor"]) and
                        math.isclose(bc["factor"], FACTOR, rel_tol=1e-12, abs_tol=0.0),
                        "WRONG_NEUMANN_TYPE_FLUX_FACTOR_" + name)
            else:
                side = next((s for s in DIELECTRIC
                             if members == ["plasma_" + s]), None)
                require(side is not None, "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")
                require(name == f"{ident}_{side}_dielectric",
                        "WRONG_DIELECTRIC_BC_NAME_" + name)
                require(set(bc) == {"type", "variable", "signed_number_flux"} and
                        bc["signed_number_flux"] == flux,
                        "WRONG_DIELECTRIC_TYPE_OR_SIGNED_FLUX_" + name)
    expected = {ident + "_wall" for ident in selected}
    expected |= {f"{ident}_{side}_dielectric" for ident in selected for side in DIELECTRIC}
    require(set(found) == expected, "DUPLICATE_OR_MISSING_FVBC")
    return {
        "ion_wall_materials": len(selected),
        "normal_fvbcs": len(selected),
        "dielectric_fvbcs": len(selected) * 3,
        "surface_current_consumers": 3,
        "runtime": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--species", nargs="+", default=list(ION_IDS))
    args = parser.parse_args()
    try:
        evidence = validate(json.loads(args.json.read_text()), args.species)
    except (C2ContractError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, "C2_JSON_P0_FAIL: " + str(exc) + "\n")
    print("C2_JSON_P0_PASS_NOT_RUNTIME " + json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
