"""#669 P3-X: fail-closed retirement of 8 Native electron FEM BCs and 2 materials.

The new New-only Physics/JSON contract becomes the sole proposed e wall BC /
n_e_physical / e_wall_number_flux owner. This is *source-only* ownership: actual
C++ Warehouse instantiation is a later, separately authorized Native P2 gate.
Never edit archived layers or the repository source files.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from retire_s6_ion_fv_owners import BLOCK, ROOT, CutoverError, parsed_parameters

C0 = ("rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_"
      "100us_dt1000ns__C0_chemistry_off.i")
PRESSURE_BLOCK_SHA = "f4fd7839ce47fa2728b2ffe7bc12c7790fb47e1ed8a050def68f5c77a5a2ed5e"

# Exact *original* source blocks, including closing [] and line ending. These
# are the same bytes before and after P2's independent 26-ion cutover.
OLD = {
    ("BCs", "electron_sheath"): (
        "d9ab87b8365ba483414939b7e3a7a30f39f4acd8b43b1c70a62ecf521c62ca79",
        "FEMElectronSheathBC", "log_e",
        "plasma_electrode plasma_metal plasma_right"),
    ("BCs", "electron_cover_dielectric"): (
        "1872e9cb7910fa7a746aa2ac0312a2a62f68931f17d61d411887e6312f5e0c04",
        "FEMElectronSheathBC", "log_e", "plasma_cover"),
    ("BCs", "electron_wafer_dielectric"): (
        "0f12b97314b9a0c2da88f9caa0c0512d67b9d0d7dc4ed6d664e0d51da905fe74",
        "FEMElectronSheathBC", "log_e", "plasma_wafer"),
    ("BCs", "electron_focus_ring_dielectric"): (
        "9e99d69205b7051a10394cba48f927e4aaca92e1936bc51ea678028c9028dbaa",
        "FEMElectronSheathBC", "log_e", "plasma_focus_ring"),
    ("BCs", "electron_energy_sheath"): (
        "9df1e4b83ffe87735dc753ac9c7f1772eda6e7e7e3701e81cd60f9c7b959d891",
        "FEMElectronEnergySheathBC", "log_e_energy",
        "plasma_electrode plasma_metal plasma_right"),
    ("BCs", "electron_energy_cover"): (
        "5e3c9b1853568945d1e99bc25cc7eb028f39d59b60b64824d4091a81b65b3f98",
        "FEMElectronEnergySheathBC", "log_e_energy", "plasma_cover"),
    ("BCs", "electron_energy_wafer"): (
        "fedc129efca3c592e13edb2c4a0d402693a02195029ee9cf86bd94bccc839884",
        "FEMElectronEnergySheathBC", "log_e_energy", "plasma_wafer"),
    ("BCs", "electron_energy_focus_ring"): (
        "b8007959a82a5e5f45980de34f5208356166f22d9bcd995a90fc4ba883ca5138",
        "FEMElectronEnergySheathBC", "log_e_energy", "plasma_focus_ring"),
    ("FunctorMaterials", "electron_physical_density"): (
        "33f68912653aaba28a9fd27353dc9671538c180a8e1d9accabb5c6e69e3e8b17",
        "ADParsedFunctorMaterial", None, None),
    ("FunctorMaterials", "electron_wall_flux"): (
        "cd1be5c26c3f72ec0e42d36d342849918d48c02a2a609543c15db045309d6824",
        "ESWallFluxMaterial", None, None),
}

NEW_ELECTRON_BCS = {
    "plasma_electrode plasma_metal plasma_right": {
        "e_wall": "FEMElectronSheathBC",
        "e_energy_wall": "FEMElectronEnergySheathBC",
    },
    "plasma_cover": {
        "e_cover_dielectric": "FEMElectronSheathBC",
        "e_energy_cover_dielectric": "FEMElectronEnergySheathBC",
    },
    "plasma_wafer": {
        "e_wafer_dielectric": "FEMElectronSheathBC",
        "e_energy_wafer_dielectric": "FEMElectronEnergySheathBC",
    },
    "plasma_focus_ring": {
        "e_focus_ring_dielectric": "FEMElectronSheathBC",
        "e_energy_focus_ring_dielectric": "FEMElectronEnergySheathBC",
    },
}


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def objects(source: str):
    roots = list(ROOT.finditer(source))
    for match in BLOCK.finditer(source):
        section = next((root.group(1) for root in reversed(roots)
                        if root.start() < match.start()), "")
        if section in ("BCs", "FunctorMaterials", "Variables"):
            yield section, match


def check_generated_bc_catalogue(js: dict) -> None:
    catalog = js.get("drift_diffusion_boundaries")
    if not isinstance(catalog, dict):
        raise CutoverError("P3X_JSON_BOUNDARIES_NOT_OBJECT")
    found = {}
    for region, entries in catalog.items():
        if not isinstance(entries, dict):
            raise CutoverError("P3X_JSON_BOUNDARY_GROUP_MALFORMED")
        for name, record in entries.items():
            if not isinstance(record, dict):
                raise CutoverError("P3X_JSON_BC_NOT_OBJECT")
            factory = record.get("type", "")
            if name.startswith("e_") or factory in (
                    "FEMElectronSheathBC", "FEMElectronEnergySheathBC"):
                if name in found:
                    raise CutoverError("P3X_JSON_DUPLICATE_E_BC:" + name)
                found[name] = (region, factory)
    required = {(name): (region, factory)
                for region, entries in NEW_ELECTRON_BCS.items()
                for name, factory in entries.items()}
    if found != required or len(found) != 8:
        raise CutoverError("P3X_JSON_EIGHT_E_BC_FACTORY_REGION_MISMATCH")


def inspect_electron_contract(layers: dict[str, bytes], ordered: list[str], js: dict) -> dict:
    """Return exact 10-block source identity; detect unintended parallel owners.

    The inputs are already required to match the P1-0 immutable SHA by P2,
    but this check independently characterizes the 10 electron blocks.
    """
    check_generated_bc_catalogue(js)
    names = [Path(x).name for x in ordered]
    if len(names) != 11 or len(set(names)) != 11 or C0 != names[0] or set(layers) != set(names):
        raise CutoverError("P3X_EXPECT_EXACT_ORDERED_ELEVEN_INPUTS")
    census = []
    pressure = []
    others = []
    for name in names:
        data = layers[name]
        if b"\r" in data:
            raise CutoverError("P3X_CRLF_NOT_PERMITTED:" + name)
        for section, obj in objects(data.decode("utf-8")):
            key = (section, obj["name"])
            params = parsed_parameters(obj["body"])
            if key in OLD:
                census.append((name, section, obj, params))
            elif section == "BCs" and (
                params.get("type") in ("FEMElectronSheathBC", "FEMElectronEnergySheathBC")
                or params.get("variable") in ("log_e", "log_e_energy")
            ):
                raise CutoverError("P3X_UNCHARACTERIZED_ELECTRON_BC:" + obj["name"])
            elif section == "FunctorMaterials" and (
                params.get("property_name") in ("n_e_physical", "e_wall_number_flux")
                or (params.get("type") == "ESWallFluxMaterial"
                    and params.get("species_id") == "e")
            ):
                raise CutoverError("P3X_UNCHARACTERIZED_ELECTRON_PRODUCER:" + obj["name"])
            if key == ("Variables", "pressure"):
                pressure.append((name, obj, params))
            if key in (("FunctorMaterials", "electron_molar_density"),
                       ("FunctorMaterials", "electron_molar_energy_density"),
                       ("FunctorMaterials", "electron_physical_energy_density")):
                others.append(key)
    if len(census) != 10 or len(set((section, obj["name"]) for _, section, obj, _ in census)) != 10:
        raise CutoverError("P3X_EXPECT_EXACT_TEN_SINGLE_OLD_OWNERS")
    actual = {}
    for filename, section, obj, params in census:
        key = (section, obj["name"])
        expected_sha, expected_type, variable, boundary = OLD[key]
        if filename != C0:
            raise CutoverError("P3X_E_OWNER_OUTSIDE_C0")
        actual_sha = digest(obj.group(0).encode("utf-8"))
        if actual_sha != expected_sha or params.get("type") != expected_type:
            raise CutoverError("P3X_E_OWNER_EXACT_BLOCK_SHA_OR_FACTORY_MISMATCH:" + obj["name"])
        if section == "BCs":
            if (params.get("variable"), params.get("boundary")) != (variable, boundary):
                raise CutoverError("P3X_E_BC_VARIABLE_OR_REGION_DRIFT")
            if params.get("wall_number_flux") != "e_wall_number_flux":
                raise CutoverError("P3X_E_BC_FLUX_MISMATCH")
            if variable == "log_e_energy" and params.get("mean_energy") != "e_energy_eV":
                raise CutoverError("P3X_E_ENERGY_BC_MEAN_ENERGY_MISMATCH")
        if key == ("FunctorMaterials", "electron_physical_density"):
            if params.get("property_name") != "n_e_physical":
                raise CutoverError("P3X_E_DENSITY_PROPERTY_MISMATCH")
        if key == ("FunctorMaterials", "electron_wall_flux"):
            if params.get("species_id") != "e":
                raise CutoverError("P3X_E_WALL_FLUX_SPECIES_MISMATCH")
        actual[key] = {"section": section, "name": obj["name"],
                       "old_block_sha256": actual_sha, "source_file": filename,
                       "factory": expected_type, "variable": variable, "boundary": boundary}
    if len(pressure) != 1 or pressure[0][0] != C0:
        raise CutoverError("P3X_PRESSURE_OWNER_MISSING_OR_DUPLICATE")
    if digest(pressure[0][1].group(0).encode()) != PRESSURE_BLOCK_SHA:
        raise CutoverError("P3X_NEUTRAL_PRESSURE_OWNER_CHANGED")
    if len(others) != 3 or len(set(others)) != 3:
        raise CutoverError("P3X_NON_TARGET_ELECTRON_STATE_FUNCTORS_NOT_PRESERVED")
    return {
        "status": "P3_X_EXACT_TEN_OWNER_SOURCE_PREFLIGHT_PASS",
        "C0_input_sha256": digest(layers[C0]),
        "retired_owner_receipts": [actual[k] for k in sorted(actual)],
        "retired_electron_FEM_BCs": 8,
        "retired_electron_FunctorMaterials": 2,
        "generated_electron_FEM_BC_expected": 8,
        "generated_electron_canonical_functors_expected": [
            "n_e_physical", "e_wall_number_flux"],
        "pressure_block_sha256": PRESSURE_BLOCK_SHA,
        "native_runtime": "NOT_RUN",
    }


def retire_electron_in_disposable_scratch(
    folder: Path, ordered: list[str], js: dict,
    preflight: dict, ion_receipt: dict
) -> dict:
    """Remove only the 10 exact existing owner blocks after P2 ion retirement."""
    folder = Path(folder).resolve(strict=True)
    marker = folder / ".issue633_disposable_scratch"
    if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != "issue633-scratch-only":
        raise CutoverError("P3X_NOT_A_DISPOSABLE_SCRATCH")
    names = [Path(x).name for x in ordered]
    if names[0] != C0 or len(names) != 11 or len(set(names)) != 11:
        raise CutoverError("P3X_ORDERED_INPUT_MISMATCH")
    before = {}
    for name in names:
        f = folder / name
        if f.is_symlink() or not f.is_file() or f.resolve().parent != folder:
            raise CutoverError("P3X_UNSAFE_STAGED_LAYER:" + name)
        data = f.read_bytes()
        if digest(data) != ion_receipt["files"][name]["after_sha256"]:
            raise CutoverError("P3X_POST_ION_LAYER_SHA_MISMATCH:" + name)
        before[name] = data
    observed = inspect_electron_contract(before, ordered, js)
    if (observed["retired_owner_receipts"] != preflight["retired_owner_receipts"]
            or digest(before[C0]) == preflight["C0_input_sha256"]):
        # P2 must have changed the C0 file by its approved 26-ion block deletion.
        raise CutoverError("P3X_PREFLIGHT_ELECTRON_OWNERS_DIFFER")
    src = before[C0].decode("utf-8")
    selected = [obj for section, obj in objects(src) if (section, obj["name"]) in OLD]
    if len(selected) != 10:
        raise CutoverError("P3X_EXACT_OWNER_RETIRE_COUNT_DRIFT")
    next_src = src
    for obj in reversed(selected):
        next_src = next_src[:obj.start()] + next_src[obj.end():]
    after = next_src.encode("utf-8")
    if len(after) >= len(before[C0]) or after == before[C0]:
        raise CutoverError("P3X_NO_ELECTRON_OBJECTS_REMOVED")
    if any((folder / name).read_bytes() != before[name] for name in names):
        raise CutoverError("P3X_STAGE_CHANGED_DURING_PREFLIGHT")
    (folder / C0).write_bytes(after)
    if (folder / C0).read_bytes() != after or any(
            (folder / name).read_bytes() != before[name] for name in names[1:]):
        raise CutoverError("P3X_POST_RETIRE_BYTE_READBACK_MISMATCH")
    # Independently scan complete after-state for forbidden old identities.
    for name in names:
        for section, obj in objects((folder / name).read_text(encoding="utf-8")):
            if (section, obj["name"]) in OLD:
                raise CutoverError("P3X_OLD_ELECTRON_OWNER_STILL_ACTIVE")
            params = parsed_parameters(obj["body"])
            if section == "BCs" and params.get("type") in (
                    "FEMElectronSheathBC", "FEMElectronEnergySheathBC"):
                raise CutoverError("P3X_OLD_ELECTRON_BC_REMAINS")
            if section == "FunctorMaterials" and params.get("property_name") == "n_e_physical":
                raise CutoverError("P3X_OLD_E_DENSITY_FUNCTOR_REMAINS")
            if section == "FunctorMaterials" and (
                    params.get("type") == "ESWallFluxMaterial" and params.get("species_id") == "e"):
                raise CutoverError("P3X_OLD_E_WALL_FUNCTOR_REMAINS")
    return {
        **preflight,
        "status": "P3_X_EIGHT_BC_TWO_FUNCTOR_EXACT_SOURCE_CUTOVER_PASS_NATIVE_HOLD",
        "C0_post_ion_sha256": digest(before[C0]),
        "C0_after_electron_cutover_sha256": digest(after),
        "removed_native_electron_owners": 10,
        "remaining_native_electron_FEM_BCs": 0,
        "remaining_native_electron_FunctorMaterials_for_generated_properties": 0,
        "other_ten_layers_unchanged": True,
        "non_target_byte_preservation": "PASS_EXACT_DELETION_ONLY",
        "newonly_cpp_warehouse": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }
