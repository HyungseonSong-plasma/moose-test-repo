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
    "wall_molar_mass", "wall_sticking", "wall_ion_temperature_eV",
    "wall_use_element_gradient_for_potential",
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
    require(not any(name in overlay for name in (
        "wall_migration_gate_smoothing_width", "migration_smoothing_width")),
        "WALL_SMOOTHING_MUST_BE_MOOSE_INPUT_ROOT")
    require(isinstance(selected, (list, tuple)) and bool(selected) and
            len(set(selected)) == len(selected) and
            set(selected) <= set(ION_IDS), "INVALID_SELECTED_SPECIES")
    species = overlay.get("species")
    require(isinstance(species, dict), "SPECIES_JSON_REQUIRED")
    require(not any(isinstance(v, dict) and "ion_wall" in v for v in species.values()),
            "RETIRED_ION_WALL_WRAPPER")
    # New-run ion Wall Material is automatically selected for transported
    # charged heavy species. Geometry and gradient method live in [Plasmas].
    modern = any(isinstance(v, dict) and isinstance(v.get("transport_coef"), dict)
                 for v in species.values())
    with_walls = (
        {k for k, v in species.items()
         if k != "e" and isinstance(v, dict) and v.get("charge_number", 0) != 0
         and isinstance(v.get("transport_coef"), dict)
         and v["transport_coef"].get("type") != "none"}
        if modern else
        {k for k, v in species.items()
         if isinstance(v, dict) and any(key in v for key in
             ("wall_molar_mass", "wall_sticking", "wall_ion_temperature_eV",
              "wall_use_element_gradient_for_potential"))}
    )
    if modern:
        common = {"elements", "charge_number", "molar_mass", "temperature_eV",
                  "sticking_coefficient", "initial_number_density", "transport_coef"}
        require(all(isinstance(v, dict) and common <= set(v)
                    for v in species.values()), "INCONSISTENT_COMMON_SPECIES_TEMPLATE")
        for name, v in species.items():
            cfg = v["transport_coef"]
            require(isinstance(cfg, dict) and {"type", "file", "unit"} <= set(cfg),
                    "INCONSISTENT_TRANSPORT_TEMPLATE_" + name)
            require(finite_num(v["molar_mass"], 1e-300),
                    "INVALID_MOLAR_MASS_" + name)
            require(v["temperature_eV"] is None or finite_num(v["temperature_eV"], 0),
                    "INVALID_TEMPERATURE_EV_" + name)
            require(finite_num(v["sticking_coefficient"], 0, 1),
                    "INVALID_STICKING_" + name)
            require("wall_use_element_gradient_for_potential" not in v,
                    "WALL_GRADIENT_MUST_BE_PLASMAS_" + name)
            if cfg["type"] == "none":
                require(cfg["file"] == "none" and cfg["unit"] == "none",
                        "INVALID_NONE_TRANSPORT_" + name)
            elif cfg["type"] == "functor":
                require(cfg["file"] == "none" and cfg["unit"] == "physical",
                        "FUNCTOR_MUST_USE_PHYSICAL_UNIT_" + name)
            elif cfg["type"] == "lookup":
                require(cfg["file"] != "none" and cfg["unit"] in ("physical", "reduced"),
                        "INVALID_LOOKUP_TRANSPORT_" + name)
            else:
                require(cfg["type"] == "constant", "INVALID_TRANSPORT_TYPE_" + name)
                require(set(cfg) == {"type", "file", "unit", "mobility", "diffusivity"}
                        and cfg["file"] == "none" and cfg["unit"] == "physical",
                        "INVALID_CONSTANT_TRANSPORT_TEMPLATE_" + name)
                require(finite_num(cfg["mobility"], 0) and
                        finite_num(cfg["diffusivity"], 0),
                        "INVALID_CONSTANT_TRANSPORT_VALUE_" + name)
            if name == "e":
                require("energy_transport_coef" not in v,
                        "ENERGY_TRANSPORT_SELECTOR_MUST_BE_MOOSE_INPUT")
            for old in ("pressure", "gas_temperature", "mobility", "diffusivity",
                        "table_file", "table_units", "wall_molar_mass",
                        "wall_sticking", "wall_ion_temperature_eV"):
                require(old not in v, "RETIRED_SPECIES_FIELD_" + name + "_" + old)
    require(with_walls == set(selected), "SELECTED_ION_WALL_OWNER_MISMATCH")
    for ident in selected:
        record = species[ident]
        require(record.get("charge_number") == CHARGE[ident], "WRONG_ION_CHARGE_" + ident)
        require("ion_wall" not in record, "RETIRED_ION_WALL_WRAPPER_" + ident)
        require(not any(name in record for name in (
            "wall_migration_gate_smoothing_width", "migration_smoothing_width")),
            "WALL_SMOOTHING_MUST_BE_MOOSE_INPUT_" + ident)
        declared = {key for key in record if key.startswith("wall_")}
        if modern:
            require(declared == set(), "INVALID_ION_WALL_FIELDS_" + ident)
            require(finite_num(record["molar_mass"], 1e-300) and
                    math.isclose(record["molar_mass"], MASS[ident], rel_tol=1e-12),
                    "WRONG_WALL_MOLAR_MASS_" + ident)
            require(finite_num(record["sticking_coefficient"], 0, 1),
                    "INVALID_STICKING_" + ident)
        else:
            require(declared == WALL_FIELDS, "INVALID_ION_WALL_FIELDS_" + ident)
            require(finite_num(record["wall_molar_mass"], 1e-300) and
                    math.isclose(record["wall_molar_mass"], MASS[ident], rel_tol=1e-12),
                    "WRONG_WALL_MOLAR_MASS_" + ident)
            require(finite_num(record["wall_sticking"], 0, 1), "INVALID_STICKING_" + ident)
            require(finite_num(record["wall_ion_temperature_eV"], 0),
                    "INVALID_wall_ion_temperature_eV_" + ident)
        if not modern:
            require(type(record["wall_use_element_gradient_for_potential"]) is bool,
                    "INVALID_GRADIENT_FLAG_" + ident)
        # Potential, density, mobility, block and temperature are derived from
        # Continuity/species ID and [Plasmas], never independently wall-owned.
        for redundant in ("potential", "ion_number_density", "gas_temperature", "block"):
            require(redundant not in record,
                    "REDUNDANT_WALL_SOURCE_FIELD_" + ident + "_" + redundant)

    current = overlay.get("ion_surface_current")
    # The exact producer is explicit. In older generated DD it is the legacy
    # electron_wall_number_flux; canonical S6 scratch can publish e_wall_number_flux.
    require(isinstance(current, dict) and
            set(current) == {"electron_wall_number_flux"} and
            isinstance(current["electron_wall_number_flux"], str) and
            current["electron_wall_number_flux"] in {
                "electron_wall_number_flux", "e_wall_number_flux"},
            "INVALID_SURFACE_CURRENT_ELECTRON_CONSUMER")

    if modern:
        require("boundaries" not in overlay,
                "MODERN_BOUNDARIES_MUST_USE_DRIFT_DIFFUSION_BOUNDARIES")
        groups = overlay.get("drift_diffusion_boundaries")
        require(isinstance(groups, dict) and len(groups) == 5,
                "MODERN_BOUNDARY_GROUP_COUNT")
        general_inlet = "inlet outlet"
        general_wall = "plasma_electrode plasma_metal plasma_right"
        dielectric_groups = {"plasma_" + side for side in DIELECTRIC}
        require(set(groups) == {general_inlet, general_wall} | dielectric_groups,
                "MODERN_BOUNDARY_SIDESET_GROUP_MISMATCH")

        expected_groups = {
            general_inlet: {ident + "_wall": "FVFunctorNeumannBC"
                            for ident in selected},
            general_wall: {
                "e_wall": "FEMElectronSheathBC",
                "e_energy_wall": "FEMElectronEnergySheathBC",
                **{ident + "_wall": "FVFunctorNeumannBC" for ident in selected},
            },
        }
        for side in DIELECTRIC:
            expected_groups["plasma_" + side] = {
                "e_" + side + "_dielectric": "FEMElectronSheathBC",
                "e_energy_" + side + "_dielectric": "FEMElectronEnergySheathBC",
                **{ident + "_" + side + "_dielectric":
                   "FVLogMolarDielectricFluxBC" for ident in selected},
            }

        merged_owners: dict[str, tuple[str, set[str]]] = {}
        used_group_sides: set[str] = set()
        for label, expected in expected_groups.items():
            group = groups[label]
            require(isinstance(group, dict) and set(group) == set(expected),
                    "MODERN_BOUNDARY_OPERATOR_MISMATCH_" + label)
            sides = set(label.split())
            require(len(sides) == len(label.split()) and
                    not sides & used_group_sides,
                    "MODERN_BOUNDARY_GROUP_SIDES_OVERLAP_" + label)
            used_group_sides |= sides
            for name, bc_type in expected.items():
                spec = group[name]
                require(isinstance(spec, dict) and spec == {"type": bc_type},
                        "MODERN_BOUNDARY_REDUNDANT_FIELD_OR_TYPE_" + name)
                if name in merged_owners:
                    existing_type, old_sides = merged_owners[name]
                    require(existing_type == bc_type and not old_sides & sides,
                            "MODERN_BC_MERGE_COLLISION_" + name)
                    old_sides.update(sides)
                else:
                    merged_owners[name] = (bc_type, set(sides))

        require(len(merged_owners) == 4 * len(selected) + 8,
                "MODERN_BC_OWNER_COUNT_MISMATCH")
        for ident in selected:
            require(merged_owners[ident + "_wall"][1] ==
                    set((general_inlet + " " + general_wall).split()),
                    "MODERN_ION_GENERAL_BC_HANDOFF_" + ident)
        require(merged_owners["e_wall"][1] == set(general_wall.split()),
                "MODERN_ELECTRON_GENERAL_BC_HANDOFF")
        require(current["electron_wall_number_flux"] == "e_wall_number_flux",
                "MODERN_ELECTRON_CANONICAL_WALL_FUNCTOR")
        return {
            "ion_wall_materials": len(selected),
            "normal_fvbcs": len(selected),
            "dielectric_fvbcs": len(selected) * 3,
            "surface_current_consumers": 3,
            "runtime": "NOT_RUN",
        }

    boundaries = overlay.get("boundaries")
    require(isinstance(boundaries, dict), "MISSING_BOUNDARIES")
    # A single group can own several sidesets. An electron FEM sheath operator
    # may share that group with ion FV BCs: do not falsely reject co-resident
    # electron consumers when the input's root boundaries records are merged.
    required_dielectric = {f"plasma_{s}" for s in DIELECTRIC}
    has_general = any(set(key.split()) == set(GENERAL) and
                      len(key.split()) == len(GENERAL)
                      for key in boundaries if isinstance(key, str))
    require(required_dielectric <= set(boundaries) and has_general,
            "MISSING_EXTRA_OR_OVERLAPPING_SIDESETS")
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
