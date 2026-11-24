"""Issue #633 C2: source-bound ion wall/BC static contract checks.

These checks deliberately do NOT generate Physics objects, validate MOOSE object
warehouses, or establish P1/P2/P3. Run the candidate gate only on a rendered,
new-only scratch input after P09/P12/P13 and the C2 implementation are ready.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import re
from pathlib import Path


class ContractError(ValueError):
    """The input does not meet the explicit C2 wall handoff contract."""


NATIVE_BLOB_SHA = "793f3f24bc95bf71d0b2537288cb2ecc8a5f74fa"
INV_AVOGADRO = 1.6605390671738466e-24
GENERAL_SIDES = ("inlet", "outlet", "plasma_electrode", "plasma_metal", "plasma_right")
DIELECTRIC_SIDES = ("plasma_cover", "plasma_wafer", "plasma_focus_ring")
SURFACE_PREFIXES = ("cover", "wafer", "focus_ring")
LEGACY = {
    "O2p": ("ion_wall_flux", "ion_wall", "log_ni", "n_i_physical", "ion_mobility", "ion_wall_number_flux", 1, 0.032, ""),
    "Om": ("negative_ion_wall_flux", "negative_ion_wall", "log_nm", "n_m_physical", "negative_ion_mobility", "negative_ion_wall_number_flux", -1, 0.016, "negative_"),
    "Op": ("atomic_positive_ion_wall_flux", "atomic_positive_ion_wall", "log_nop", "n_op_physical", "atomic_positive_ion_mobility", "atomic_positive_ion_wall_number_flux", 1, 0.016, "atomic_positive_"),
}
CANONICAL_ION_ORDER = ("O2p", "Om", "Op")


def _section(text: str, name: str) -> str:
    match = re.search(r"(?m)^\[" + re.escape(name) + r"\][ \t]*$", text)
    if not match:
        raise ContractError(f"missing [{name}] section")
    tail = text[match.end():]
    end = re.search(r"(?m)^\[\][ \t]*$", tail)
    if not end:
        raise ContractError(f"unterminated [{name}] section")
    return tail[:end.start()]


def _blocks(text: str, section: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    body = _section(text, section)
    for match in re.finditer(r"(?ms)^  \[([^\]\n]+)\][ \t]*\n(.*?)^  \[\][ \t]*$", body):
        name = match.group(1)
        if name in result:
            raise ContractError(f"duplicate {section} block: {name}")
        params: dict[str, str] = {}
        for line in match.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ContractError(f"unparsed {section}/{name} input: {line}")
            key, value = (part.strip() for part in line.split("=", 1))
            if key in params:
                raise ContractError(f"duplicate parameter {section}/{name}/{key}")
            params[key] = value.strip("'\"")
        result[name] = params
    return result


def _need(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _value(obj: dict[str, str], field: str, expected: str, owner: str) -> None:
    _need(obj.get(field) == expected,
          f"{owner}: {field} expected {expected!r}, got {obj.get(field)!r}")


def _number(obj: dict[str, str], field: str, expected: float, owner: str) -> None:
    try:
        value = float(obj.get(field, ""))
    except ValueError as exc:
        raise ContractError(f"{owner}: missing/non-numeric {field}") from exc
    _need(math.isfinite(value) and math.isclose(value, expected, rel_tol=1e-12, abs_tol=0),
          f"{owner}: incorrect {field} {value!r}, expected {expected!r}")


def _sides(obj: dict[str, str], expected: tuple[str, ...], owner: str) -> None:
    actual = obj.get("boundary", "").split()
    _need(len(actual) == len(set(actual)) and set(actual) == set(expected),
          f"{owner}: wrong/duplicate/missing sideset: {actual!r}")


def _surface_current(materials: dict[str, dict[str, str]], fluxes: tuple[str, ...]) -> None:
    for label in SURFACE_PREFIXES:
        owner = f"{label}_surface_current"
        _need(owner in materials, f"missing {owner} surface-current consumer")
        current = materials[owner]
        _value(current, "type", "ADParsedFunctorMaterial", owner)
        _value(current, "property_name", f"{label}_net_surface_current_density", owner)
        _value(current, "functor_names", " ".join((*fluxes, "electron_wall_number_flux")), owner)
        _value(current, "functor_symbols", "gi gop gm ge", owner)
        _value(current, "expression", "1.602176634e-19*(gi+gop-gm-ge)", owner)


def check_native_source(raw: bytes) -> dict[str, int]:
    """Check immutable S6 source as provenance, NOT as an executable new input."""
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    _need(blob == NATIVE_BLOB_SHA, "immutable Native source blob SHA changed")
    text = raw.decode("utf-8")
    mats = _blocks(text, "FunctorMaterials")
    bcs = _blocks(text, "FVBCs")
    for species in CANONICAL_ION_ORDER:
        material_name, general_name, variable, density, mobility, flux, charge, mass, prefix = LEGACY[species]
        _need(material_name in mats, f"missing historical {species} Wall Material")
        wall = mats[material_name]
        for field, value in (("type", "PhysicsIonWallTotalFluxMaterial"),
                             ("ion_number_density", density), ("mobility", mobility),
                             ("potential", "potential"), ("gas_temperature", "T_g_fixed"),
                             ("use_element_gradient_for_potential", "true")):
            _value(wall, field, value, material_name)
        _number(wall, "charge_number", charge, material_name)
        _number(wall, "molar_mass", mass, material_name)
        _number(wall, "sticking", 1, material_name)
        _number(wall, "migration_gate_smoothing_width", 1e-3, material_name)
        _need(wall.get("output_prefix", "") == prefix, f"{material_name}: output prefix changed")
        _need(general_name in bcs, f"missing historical {species} general BC")
        normal = bcs[general_name]
        _value(normal, "type", "FVFunctorNeumannBC", general_name)
        _value(normal, "variable", variable, general_name)
        _value(normal, "functor", flux, general_name)
        _number(normal, "factor", -INV_AVOGADRO, general_name)
        _sides(normal, GENERAL_SIDES, general_name)
        for prefix_side in SURFACE_PREFIXES:
            bc_name = f"{general_name.replace('_wall', '')}_{prefix_side}_dielectric"
            _need(bc_name in bcs, f"missing historical {species} {prefix_side} BC")
            dielectric = bcs[bc_name]
            _value(dielectric, "type", "PhysicsFVLogMolarDielectricFluxBC", bc_name)
            _value(dielectric, "variable", variable, bc_name)
            _value(dielectric, "signed_number_flux", flux, bc_name)
            _sides(dielectric, ("plasma_" + prefix_side,), bc_name)
    _surface_current(mats, tuple(LEGACY[s][5] for s in ("O2p", "Op", "Om")))
    return {"material": 3, "general_fvbc": 3, "dielectric_fvbc": 9}


def check_candidate(text: str, species_ids: tuple[str, ...] = CANONICAL_ION_ORDER) -> dict[str, int]:
    """Check a rendered NEW-ONLY input contract, not its runtime instantiation."""
    _need(bool(species_ids) and len(species_ids) == len(set(species_ids)) and
          all(s in CANONICAL_ION_ORDER for s in species_ids),
          "unsupported, empty or repeated selected FV species")
    mats = _blocks(text, "FunctorMaterials")
    bcs = _blocks(text, "FVBCs")
    wall_mat_ids = [p.get("species_id", "") for p in mats.values()
                    if p.get("type") in ("IonWallFluxMaterial", "PhysicsIonWallFluxMaterial",
                                         "PhysicsIonWallTotalFluxMaterial")]
    _need(sorted(wall_mat_ids) == sorted(species_ids),
          f"duplicate, unselected, missing or legacy wall producer: {wall_mat_ids!r}")
    expected_bc_names: set[str] = set()
    for species in species_ids:
        name = f"{species}_wall"
        _need(name in mats, f"missing {name} producer")
        wall = mats[name]
        _value(wall, "type", "IonWallFluxMaterial", name)
        _value(wall, "species_id", species, name)
        _value(wall, "ion_number_density", f"{species}_number_density", name)
        _value(wall, "mobility", f"{species}_mobility", name)
        _value(wall, "potential", "potential", name)
        _value(wall, "use_element_gradient_for_potential", "true", name)
        _number(wall, "charge_number", LEGACY[species][6], name)
        _number(wall, "molar_mass", LEGACY[species][7], name)
        _number(wall, "sticking", 1, name)
        _number(wall, "migration_gate_smoothing_width", 1e-3, name)
        _need(bool(wall.get("gas_temperature")), f"{name}: missing gas temperature")
        _need("output_prefix" not in wall, f"{name}: legacy output prefix forbidden")
        flux = f"{species}_wall_number_flux"
        general_name = f"{species}_wall"
        expected_bc_names.add(general_name)
        _need(general_name in bcs, f"missing {species} general FV BC")
        normal = bcs[general_name]
        _value(normal, "type", "FVFunctorNeumannBC", general_name)
        _value(normal, "variable", f"log_{species}", general_name)
        _value(normal, "functor", flux, general_name)
        _number(normal, "factor", -INV_AVOGADRO, general_name)
        _sides(normal, GENERAL_SIDES, general_name)
        for side in SURFACE_PREFIXES:
            bc_name = f"{species}_{side}_dielectric"
            expected_bc_names.add(bc_name)
            _need(bc_name in bcs, f"missing {bc_name} dielectric BC")
            dielectric = bcs[bc_name]
            _value(dielectric, "type", "FVLogMolarDielectricFluxBC", bc_name)
            _value(dielectric, "variable", f"log_{species}", bc_name)
            _value(dielectric, "signed_number_flux", flux, bc_name)
            _need("factor" not in dielectric, f"{bc_name}: dielectric must use its own +1/N_A")
            _sides(dielectric, ("plasma_" + side,), bc_name)
    # Catch duplicate same-species wall operators under unexpected object names,
    # including old Native entries that coexist with generated C2 operators.
    for name, bc in bcs.items():
        if bc.get("variable") not in {f"log_{s}" for s in species_ids}:
            continue
        if bc.get("type") in ("FVFunctorNeumannBC", "FVLogMolarDielectricFluxBC",
                              "PhysicsFVLogMolarDielectricFluxBC"):
            _need(name in expected_bc_names, f"unexpected/duplicate ion wall BC: {name}")
    if set(species_ids) == set(CANONICAL_ION_ORDER):
        _surface_current(mats, tuple(f"{s}_wall_number_flux" for s in ("O2p", "Op", "Om")))
    return {"material": len(species_ids), "general_fvbc": len(species_ids),
            "dielectric_fvbc": 3 * len(species_ids)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mode", choices=("native-provenance", "candidate-static"), required=True)
    parser.add_argument("--species", nargs="+", default=list(CANONICAL_ION_ORDER))
    args = parser.parse_args()
    try:
        result = (check_native_source(args.input.read_bytes()) if args.mode == "native-provenance"
                  else check_candidate(args.input.read_text(encoding="utf-8"), tuple(args.species)))
    except ContractError as exc:
        parser.exit(status=1, message=f"C2_CONTRACT_FAIL: {exc}\n")
    print(f"C2_STATIC_CONTRACT_PASS (NOT P1/P2/P3): {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
