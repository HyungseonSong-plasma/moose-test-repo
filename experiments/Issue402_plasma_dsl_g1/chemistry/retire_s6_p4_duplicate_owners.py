"""#670 P4-X: retire EXACT duplicate ion coefficients, wall and current owners.

Run only after the pinned P2 ion and P3-X electron cutovers, inside a marked
S6-417/941 disposable Scratch. The seven source-object identities must match
actual P3-X input bytes. This stage neither builds PhysicsApp nor runs Native.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from retire_s6_ion_fv_owners import ROOT, BLOCK, CutoverError, parsed_parameters

C0 = ("rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_"
      "100us_dt1000ns__C0_chemistry_off.i")
BEFORE_SHA = "d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a"
AFTER_SHA = "2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490"
TARGET_SHA = {
    "constants": "f9c4beb247c2f1e7ba286aaf21919c07cc16a659cbf0d01987116506ad72bb73",
    "ion_wall_flux": "dd5ef36dfb9d64a50724492eb48728cea1dcd61a2de24102c47271519049edf5",
    "negative_ion_wall_flux": "65068da6f4fccaa8043a04dc5893cd41eccbd15db60d1e26bf19c1f6fa38c162",
    "atomic_positive_ion_wall_flux": "67d3fe76f7dbc8cfd58070808eca35ef3626e553689b68a5f3270afec0b9478e",
    "cover_surface_current": "acaa407f7dafae72a7b83f0eaefbdcbd29a292e1cb0a8275293acdb2c4bdba0f",
    "wafer_surface_current": "e523769c7b4782a7be3e5b1f926b5cdc5ec31240cc4c1df45760efca9b06b0d2",
    "focus_ring_surface_current": "b7f8870d2c6b4431fc0dff3fa90e158b64edfa5e7f0f1f68371ffc570fe442a2",
}
CARRIER_ONLY = ("  [constants]\n"
                "    type = ADGenericFunctorMaterial\n"
                "    prop_names = 'carrier_one'\n"
                "    prop_values = '1.0'\n"
                "    block = plasma\n"
                "  []\n")
EXPECTED_VALUES = {
    "O2p": (1, 0.032), "Om": (-1, 0.016), "Op": (1, 0.016),
}


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def check_json_contract(mechanism: dict) -> None:
    species = mechanism.get("species")
    if not isinstance(species, dict):
        raise CutoverError("P4X_JSON_SPECIES_MISSING")
    for name, (charge, mass) in EXPECTED_VALUES.items():
        value = species.get(name)
        if not isinstance(value, dict) or value.get("charge_number") != charge or value.get("molar_mass") != mass:
            raise CutoverError("P4X_ION_CHARGE_OR_MASS_CHANGED:" + name)
        transport = value.get("transport_coef", {})
        if transport != {"type": "constant", "file": "none", "unit": "physical",
                         "mobility": 10, "diffusivity": 0.25851999786435537}:
            raise CutoverError("P4X_TRANSPORT_CONTRACT_CHANGED:" + name)
    if mechanism.get("ion_surface_current") != {"electron_wall_number_flux": "e_wall_number_flux"}:
        raise CutoverError("P4X_SURFACE_CURRENT_ELECTRON_CHANGED")
    groups = mechanism.get("drift_diffusion_boundaries")
    if not isinstance(groups, dict) or set(groups) != {
        "inlet outlet", "plasma_electrode plasma_metal plasma_right",
        "plasma_cover", "plasma_wafer", "plasma_focus_ring"}:
        raise CutoverError("P4X_FIVE_BOUNDARY_GROUPS_CHANGED")
    for name in EXPECTED_VALUES:
        required = {name + "_wall": "FVFunctorNeumannBC",
                    name + "_cover_dielectric": "FVLogMolarDielectricFluxBC",
                    name + "_wafer_dielectric": "FVLogMolarDielectricFluxBC",
                    name + "_focus_ring_dielectric": "FVLogMolarDielectricFluxBC"}
        observed = {}
        for group, bcs in groups.items():
            if not isinstance(bcs, dict):
                raise CutoverError("P4X_BC_GROUP_INVALID")
            for key, spec in bcs.items():
                if key in required:
                    if spec != {"type": required[key]}:
                        raise CutoverError("P4X_BC_FACTORY_CHANGED:" + key)
                    observed.setdefault(key, set()).add(group)
        wall_groups = {"inlet outlet", "plasma_electrode plasma_metal plasma_right"}
        if observed != {name + "_wall": wall_groups,
                        name + "_cover_dielectric": {"plasma_cover"},
                        name + "_wafer_dielectric": {"plasma_wafer"},
                        name + "_focus_ring_dielectric": {"plasma_focus_ring"}}:
            raise CutoverError("P4X_BC_OWNER_CARDINALITY_CHANGED:" + name)


def exact_objects(text: str):
    roots = list(ROOT.finditer(text))
    for found in BLOCK.finditer(text):
        section = next((r.group(1) for r in reversed(roots)
                        if r.start() < found.start()), "")
        yield section, found


def plan_p4_duplicate_owner_cutover(layers: dict[str, bytes], ordered: list[str],
                                    mechanism: dict, *, post_p3_layer_sha: dict[str, str]) -> tuple[bytes, dict]:
    """Preflight all eleven, construct exact-byte C0 replacement without writes."""
    check_json_contract(mechanism)
    names = [Path(n).name for n in ordered]
    if (len(names) != 11 or len(set(names)) != 11 or names[0] != C0
            or set(layers) != set(names) or set(post_p3_layer_sha) != set(names)
            or any(Path(n).name != n for n in ordered)):
        raise CutoverError("P4X_ORDERED_ELEVEN_INPUTS_INVALID")
    for name in names:
        if not isinstance(layers[name], bytes) or b"\r" in layers[name]:
            raise CutoverError("P4X_INPUT_BYTES_OR_CRLF_INVALID:" + name)
        if digest(layers[name]) != post_p3_layer_sha[name]:
            raise CutoverError("P4X_PINNED_LAYER_SHA_CHANGED:" + name)
    if digest(layers[C0]) != BEFORE_SHA:
        raise CutoverError("P4X_C0_NOT_EXACT_P3X_STATE")
    text = layers[C0].decode("utf-8")
    matched = []
    for section, found in exact_objects(text):
        if section == "FunctorMaterials" and found["name"] in TARGET_SHA:
            if digest(found.group(0).encode()) != TARGET_SHA[found["name"]]:
                raise CutoverError("P4X_TARGET_FACTORY_OR_BYTES_CHANGED:" + found["name"])
            matched.append(found)
    if len(matched) != 7 or {m["name"] for m in matched} != set(TARGET_SHA):
        raise CutoverError("P4X_SEVEN_OWNER_CENSUS_CHANGED")
    constants = next(m for m in matched if m["name"] == "constants")
    params = parsed_parameters(constants["body"])
    if params.get("type") != "ADGenericFunctorMaterial" or params.get("block") != "plasma":
        raise CutoverError("P4X_CONSTANTS_NOT_WELL_FORMED")
    old_props = params.get("prop_names", "").split()
    old_vals = params.get("prop_values", "").split()
    if len(old_props) != 7 or len(old_vals) != 7 or old_props[-1] != "carrier_one" or old_vals[-1] != "1.0":
        raise CutoverError("P4X_CARRIER_ONE_NOT_EXACTLY_PRESERVED")
    after = text
    for obj in reversed(matched):
        replacement = CARRIER_ONLY if obj["name"] == "constants" else ""
        after = after[:obj.start()] + replacement + after[obj.end():]
    blob = after.encode("utf-8")
    if digest(blob) != AFTER_SHA:
        raise CutoverError("P4X_POST_C0_SHA_UNEXPECTED")
    for section, obj in exact_objects(after):
        if section == "FunctorMaterials" and obj["name"] in TARGET_SHA and obj["name"] != "constants":
            raise CutoverError("P4X_DUPLICATE_PRODUCER_SURVIVES")
    carrier = [(section, obj) for section, obj in exact_objects(after)
               if section == "FunctorMaterials" and obj["name"] == "constants"]
    if len(carrier) != 1 or carrier[0][1].group(0) != CARRIER_ONLY:
        raise CutoverError("P4X_CARRIER_PRODUCER_BROKEN")
    return blob, {
        "schema": "issue670.p4x.exact_c0_provider_cutover.v1",
        "input_c0_sha256": BEFORE_SHA,
        "output_c0_sha256": AFTER_SHA,
        "target_source_block_sha256": TARGET_SHA,
        "retired_source_materials": 6,
        "retired_duplicate_transport_coefficients": 6,
        "carrier_one_preserved": True,
        "expected_generated_wall_materials": 3,
        "expected_generated_surface_current_materials": 3,
        "non_target_10_layers_preserved": True,
        "native_P2": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def retire_p4_duplicate_owners(folder: Path, ordered: list[str], mechanism: dict,
                              *, post_p3_layer_sha: dict[str, str]) -> dict:
    """Fail closed and write C0 only after all 11-layer input identity gates."""
    folder = Path(folder).resolve(strict=True)
    if folder.name != "Issue395_powered_chemistry_ladder" or folder.parent.name != "experiments":
        raise CutoverError("P4X_NOT_EXPECTED_DISPOSABLE_FOLDER")
    marker = folder / ".issue633_disposable_scratch"
    if (marker.is_symlink() or not marker.is_file()
            or marker.read_text().strip() != "issue633-scratch-only"):
        raise CutoverError("P4X_DISPOSABLE_MARKER_REQUIRED")
    names = [Path(n).name for n in ordered]
    if len(names) != 11 or any(n != raw for n, raw in zip(names, ordered)):
        raise CutoverError("P4X_UNSAFE_ORDERED_FILE_PATH")
    paths = {n: folder / n for n in names}
    if any(p.is_symlink() or not p.is_file() or p.resolve().parent != folder for p in paths.values()):
        raise CutoverError("P4X_SYMLINK_OR_STAGED_FILE_MISSING")
    before = {n: p.read_bytes() for n, p in paths.items()}
    changed, receipt = plan_p4_duplicate_owner_cutover(
        before, ordered, mechanism, post_p3_layer_sha=post_p3_layer_sha)
    if any(p.read_bytes() != before[name] for name, p in paths.items()):
        raise CutoverError("P4X_INPUT_CHANGED_DURING_PREFLIGHT")
    paths[C0].write_bytes(changed)
    if paths[C0].read_bytes() != changed or any(paths[n].read_bytes() != before[n] for n in names[1:]):
        raise CutoverError("P4X_POST_STAGE_READBACK_FAILED")
    return receipt
